import os
import re
import json
import logging

logger = logging.getLogger(__name__)


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def merge_short_segments(segments: list[dict], min_duration: float = 1.0, max_gap: float = 2.0) -> list[dict]:
    """
    دمج المقاطع القصيرة في المقاطع السابقة.
    max_gap: أقصى فجوة زمنية (ثانية) بين نهاية المقطع السابق وبداية المقطع الحالي
    للسماح بالدمج — يمنع دمج مقاطع بعيدة زمنياً مما يسبب ظهور الترجمة مبكراً.
    """
    if not segments:
        return []
    merged = []
    for seg in segments:
        duration = seg.get("end", 0) - seg.get("start", 0)
        text = seg.get("text", "").strip()
        if not text:
            continue
        if duration < min_duration and merged:
            prev = merged[-1]
            gap = seg.get("start", 0) - prev.get("end", 0)
            if gap <= max_gap:
                prev["end"] = seg["end"]
                prev["text"] = (prev["text"].rstrip(".!?،؛") + " " + text).strip()
            else:
                # الفجوة كبيرة — لا دمج، أضف كمقطع مستقل
                merged.append(dict(seg))
        else:
            merged.append(dict(seg))
    return merged


def deduplicate_overlapping_segments(segments: list[dict], overlap_threshold: float = 0.3) -> list[dict]:
    """
    إزالة المقاطع المتداخلة القادمة من حدود الشُنكات.
    لو مقطعان متجاوران متداخلان بأكثر من overlap_threshold,
    والمقطع الأحدث هو امتداد طبيعي للأقدم مع تشابه نصي — ندمجهم.
    """
    if not segments:
        return []
    cleaned = [dict(segments[0])]
    for seg in segments[1:]:
        prev = cleaned[-1]
        overlap = prev.get("end", 0) - seg.get("start", 0)
        if overlap > overlap_threshold:
            texts_match = _texts_overlap(prev.get("text", ""), seg.get("text", ""))
            if texts_match:
                prev["end"] = max(prev["end"], seg["end"])
                prev["text"] = seg["text"]
                continue
        cleaned.append(dict(seg))
    return cleaned


def _texts_overlap(a: str, b: str) -> bool:
    """فحص تشابه نصي بين مقطعين — هل هما نفس الكلام؟"""
    a = a.strip().lower()
    b = b.strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) > 5 and len(b) > 5:
        shorter = min(a, b, key=len)
        longer = max(a, b, key=len)
        return shorter in longer or longer in shorter
    return a == b


LANGUAGE_CODES = {
    "en": "الإنجليزية",
    "es": "الإسبانية",
    "fr": "الفرنسية",
    "de": "الألمانية",
    "it": "الإيطالية",
    "pt": "البرتغالية",
    "ru": "الروسية",
    "zh": "الصينية",
    "ja": "اليابانية",
    "ko": "الكورية",
    "hi": "الهندية",
    "ar": "العربية",
    "tr": "التركية",
    "nl": "الهولندية",
    "pl": "البولندية",
    "vi": "الفيتنامية",
    "th": "التايلندية",
    "id": "الإندونيسية",
    "ms": "الماليزية",
    "sw": "السواحلية",
    "ur": "الأردية",
    "fa": "الفارسية",
    "ku": "الكردية",
    "am": "الأمهرية",
    "ti": "التغرينية",
    "so": "الصومالية",
}


def _source_lang_name(code: str) -> str:
    return LANGUAGE_CODES.get(code, f"اللغة ({code})")


def _percent_arabic(segments: list[dict]) -> float:
    total_chars = 0
    arabic_chars = 0
    for seg in segments:
        text = seg.get("text", "").strip()
        for c in text:
            total_chars += 1
            if '\u0600' <= c <= '\u06FF' or '\u0750' <= c <= '\u077F' or \
               '\u08A0' <= c <= '\u08FF' or '\uFE70' <= c <= '\uFEFF' or \
               '\uFB50' <= c <= '\uFDFF':
                arabic_chars += 1
    if total_chars == 0:
        return 0.0
    return (arabic_chars / total_chars) * 100


def translate_segments_to_arabic(
    segments: list[dict],
    video_title: str = "",
    client=None,
    source_lang: str = "",
) -> list[dict]:
    """
    ترجمة المقاطع إلى العربية باستخدام Groq Llama 3.3 70B.
    source_lang: رمز اللغة المصدر (en, es, fr, ...).
    """
    from groq import Groq

    if client is None:
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key or api_key == "your_groq_api_key_here":
            logger.warning("GROQ_API_KEY غير موجودة — لن تتم الترجمة")
            return segments
        client = Groq(api_key=api_key)

    text_parts = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if text:
            text_parts.append(text)

    if not text_parts:
        return segments

    source_label = _source_lang_name(source_lang) if source_lang else "اللغة الأصلية"

    batch_size = 18
    translated_segments = list(segments)

    model = "llama-3.3-70b-versatile"

    _SYSTEM_PROMPT = (
        "أنت مترجم محترف للعربية. ترجم النصوص من أي لغة إلى العربية الفصحى الطبيعية. "
        "أعد JSON بالضبط بنفس عدد الترجمات المطلوبة. "
        "يجب أن تكون الترجمات عربية 100% — لا تكتب أي كلمات إنجليزية في النص المترجم. "
        "الترجمة ليست حرفية — أعد صياغة المعنى بشكل طبيعي كما يتحدث العربي الفصيح. "
        'التنسيق: {"translations": ["ترجمة 1", "ترجمة 2", ...]}'
    )

    for batch_start in range(0, len(text_parts), batch_size):
        batch_texts = text_parts[batch_start:batch_start + batch_size]

        texts_json = json.dumps(batch_texts, ensure_ascii=False)

        prompt = (
            f"أنت مترجم محترف. ترجم النصوص التالية من {source_label} إلى العربية الفصحى الطبيعية.\n\n"
            "القواعد الصارمة:\n"
            "- الترجمة يجب أن تكون إعادة صياغة طبيعية للجملة كاملة، وليست ترجمة حرفية كلمة بكلمة\n"
            "- لا تكرر أي كلمات أو عبارات من نهاية الترجمة السابقة في بداية الترجمة الحالية\n"
            "- كل نص هو مقطع منفصل — ترجمه بشكل مستقل بمعناه الكامل\n"
            "- حافظ على المعنى الكامل والسياق\n"
            "- المصطلحات التقنية: استخدم المقابل العربي إن وجد (مثل 'معالج' بدل 'processor')،\n"
            "  إلا إذا كان المصطلح مشهوراً عالمياً بالإنجليزية فقط (مثل 'Wi-Fi', 'Bluetooth')\n"
            "- الأرقام والأسماء الخاصة: اتركها كما هي\n"
            "- أعد ترجمة واحدة لكل سؤال — كل سطر من النص يقابله ترجمة واحدة فقط\n"
            "- ممنوع دمج الترجمات أو إعادة صياغة أكثر من سطر في سطر واحد\n"
            f"- عدد الترجمات المطلوب: {len(batch_texts)} — أعد نفس العدد بالضبط\n"
            "- النص المترجم النهائي يجب أن يكون عربياً 100% بدون أي كلمات إنجليزية\n\n"
            "- أعد JSON فقط، بدون أي نص إضافي:\n"
            '{"translations": ["الترجمة 0", "الترجمة 1", ...]}\n\n'
            f"عنوان الفيديو: {video_title if video_title else 'غير معروف'}\n\n"
            f"النصوص:\n{texts_json}"
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            translated = response.choices[0].message.content.strip()

            translated_lines = _parse_json_translations(translated, len(batch_texts))

            if len(translated_lines) == len(batch_texts):
                for i, tline in enumerate(translated_lines):
                    idx = batch_start + i
                    if idx < len(translated_segments):
                        translated_segments[idx]["text"] = tline
            else:
                logger.warning(
                    "عدد الترجمات (%d) لا يساوي المدخل (%d) — إعادة محاولة واحدة",
                    len(translated_lines), len(batch_texts),
                )
                try:
                    retry_response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.0,
                        max_tokens=4096,
                        response_format={"type": "json_object"},
                    )
                    retry_translated = retry_response.choices[0].message.content.strip()
                    translated_lines = _parse_json_translations(retry_translated, len(batch_texts))
                except Exception as retry_err:
                    logger.warning("إعادة محاولة الترجمة فشلت: %s", retry_err)

                if len(translated_lines) == len(batch_texts):
                    for i, tline in enumerate(translated_lines):
                        idx = batch_start + i
                        if idx < len(translated_segments):
                            translated_segments[idx]["text"] = tline
                else:
                    logger.warning(
                        "بعد إعادة المحاولة: عدد الترجمات (%d) لا يزال لا يساوي المدخل (%d) — مطابقة جزئية",
                        len(translated_lines), len(batch_texts),
                    )
                    for i, tline in enumerate(translated_lines):
                        idx = batch_start + i
                        if idx < len(translated_segments):
                            translated_segments[idx]["text"] = tline
                    for i in range(len(translated_lines), len(batch_texts)):
                        idx = batch_start + i
                        if idx < len(translated_segments):
                            logger.warning(
                                "مقطع #%d لم يُترجم — النص الأصلي: '%s'",
                                idx, batch_texts[i][:80],
                            )

        except json.JSONDecodeError as e:
            logger.warning("فشل تحليل JSON من %s: %s — محاولة استخراج يدوي", model, e)
            translated_lines = _parse_numbered_response(translated if 'translated' in dir() else "", len(batch_texts))
            for i, tline in enumerate(translated_lines):
                idx = batch_start + i
                if idx < len(translated_segments):
                    translated_segments[idx]["text"] = tline
            for i in range(len(translated_lines), len(batch_texts)):
                idx = batch_start + i
                if idx < len(translated_segments):
                    logger.warning(
                        "مقطع #%d لم يُترجم (JSON فاسد) — النص الأصلي: '%s'",
                        idx, batch_texts[i][:80],
                    )
        except Exception as e:
            logger.warning("فشلت الترجمة بالموديل %s: %s", model, e)
            for i in range(len(batch_texts)):
                idx = batch_start + i
                if idx < len(translated_segments):
                    logger.warning(
                        "مقطع #%d لم يُترجم (استثناء) — النص الأصلي: '%s'",
                        idx, batch_texts[i][:80],
                    )

    return translated_segments


def verify_arabic_output(segments: list[dict]) -> bool:
    """
    التحقق من أن جميع المقاطع عربية ≥ 90%.
    يرجع True إذا كانت عربية، False إذا في نسبة إنجليزية أكبر من 10%.
    """
    low_arabic_segments = []
    for i, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if not text:
            continue
        pct = _percent_arabic([seg])
        if pct < 90:
            low_arabic_segments.append((i, text, pct))

    if low_arabic_segments:
        logger.warning(
            "%d مقطعاً نسبة العربيّة فيها أقل من 90%% — أولها: '%s' (%.0f%%)",
            len(low_arabic_segments),
            low_arabic_segments[0][1][:60],
            low_arabic_segments[0][2],
        )
        return False
    return True


def _parse_json_translations(text: str, expected_count: int) -> list[str]:
    """تحليل استجابة JSON من الموديل"""
    try:
        data = json.loads(text)
        if "translations" in data and isinstance(data["translations"], list):
            translations = data["translations"]
            if len(translations) >= expected_count:
                return [str(t).strip() for t in translations[:expected_count]]
            return [str(t).strip() for t in translations]
    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    # محاولة استخراج JSON من النص
    json_match = re.search(r'\{[^{}]*"translations"\s*:\s*\[.*?\][^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if "translations" in data and isinstance(data["translations"], list):
                return [str(t).strip() for t in data["translations"][:expected_count]]
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    # Fallback: استخراج يدوي
    return _parse_numbered_response(text, expected_count)


def _parse_numbered_response(text: str, expected_count: int) -> list[str]:
    """استخراج الترجمات من تنسيق مرقم (fallback)"""
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        cleaned = re.sub(r"^\[\d+\]\s*", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    if len(lines) >= expected_count:
        return lines[:expected_count]
    numbered = re.findall(r"\[\d+\]\s*(.+?)(?=\[\d+\]|\Z)", text, re.DOTALL)
    if numbered:
        return [n.strip() for n in numbered[:expected_count]]
    return lines


def deduplicate_text_overlap(segments: list[dict]) -> list[dict]:
    """
    إزالة التكرار النصي بين المقاطع المتجاورة.
    لو مقطع يبدأ بنفس كلام نهاية المقطع اللي قبله — نحذف الجزء المكرر من البداية.
    """
    if not segments:
        return segments
    result = [dict(segments[0])]
    for seg in segments[1:]:
        prev_text = result[-1]["text"]
        curr_text = seg["text"]
        new_text = _remove_prefix_overlap(prev_text, curr_text)
        new_seg = dict(seg)
        new_seg["text"] = new_text.strip() if new_text.strip() else curr_text
        result.append(new_seg)
    return result


def _remove_prefix_overlap(prev_text: str, curr_text: str) -> str:
    """حذف البادئة المكررة من curr_text إذا تطابقت مع نهاية prev_text"""
    prev_words = prev_text.split()
    curr_words = curr_text.split()
    if len(prev_words) < 2 or len(curr_words) < 2:
        return curr_text
    max_overlap = min(len(prev_words), len(curr_words))
    for overlap_len in range(max_overlap, 0, -1):
        prev_suffix = prev_words[-overlap_len:]
        curr_prefix = curr_words[:overlap_len]
        if prev_suffix == curr_prefix:
            return " ".join(curr_words[overlap_len:])
    return curr_text


_RTL_EMBED = "\u202B"


def _parse_srt_timestamp(ts: str) -> float:
    """تحويل توقيت SRT (00:00:01,000) إلى ثوانٍ"""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return 0.0


def parse_srt_to_segments(srt_content: str) -> list[dict]:
    """تحويل محتوى SRT نصي إلى list[dict] بنفس format {start, end, text}"""
    segments = []
    block_pattern = re.compile(
        r"(\d+)\s*\n"
        r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n"
        r"((?:.+\n?)*?)(?:\n|$)",
        re.MULTILINE,
    )
    for match in block_pattern.finditer(srt_content):
        start = _parse_srt_timestamp(match.group(2))
        end = _parse_srt_timestamp(match.group(3))
        text = match.group(4).strip().replace("\n", " ")
        if text:
            segments.append({"start": start, "end": end, "text": text})
    return segments


def max_lines_per_segment(segments: list[dict], max_lines: int = 2) -> list[dict]:
    """
    تقطيع المقاطع الطويلة (أكثر من max_lines) إلى مقاطع فرعية مع توزيع الـ timing.
    """
    if not segments:
        return segments
    result = []
    for seg in segments:
        text = seg.get("text", "").strip()
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        duration = end - start
        if not text or duration <= 0:
            result.append(dict(seg))
            continue
        # عد الأسطر — السطر ≈ 40 حرف
        est_lines = max(1, len(text) // 40)
        if est_lines <= max_lines:
            result.append(dict(seg))
            continue
        # قص المقطع الطويل
        words = text.split()
        chunk_size = max(1, len(words) // est_lines)
        chunk_dur = duration / est_lines
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            if not chunk_text.strip():
                continue
            chunk_start = start + i / len(words) * duration
            chunk_end = start + min(i + chunk_size, len(words)) / len(words) * duration
            result.append({"start": chunk_start, "end": chunk_end, "text": chunk_text})
    return result


def groq_json_to_srt(segments: list[dict]) -> str:
    if not segments:
        return ""
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(f"{_format_timestamp(start)} --> {_format_timestamp(end)}")
        lines.append(_RTL_EMBED + text)
        lines.append("")
    return "\n".join(lines)


def srt_to_vtt(srt_content: str) -> str:
    lines = srt_content.split("\n")
    vtt = ["WEBVTT\n"]
    for line in lines:
        if re.match(r"^\d+$", line.strip()):
            continue
        if "-->" in line:
            vtt.append(line.replace(",", "."))
        elif line.strip() == "":
            vtt.append("")
        else:
            vtt.append(line)
    return "\n".join(vtt)


def validate_srt(content: str) -> bool:
    pattern = re.compile(
        r"\d+\n"
        r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n"
        r".+(\n|$)",
        re.MULTILINE,
    )
    return bool(pattern.search(content))


def write_srt_file(filepath: str, content: str):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("تم كتابة ملف SRT: %s", filepath)


def write_vtt_file(filepath: str, content: str):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("تم كتابة ملف VTT: %s", filepath)
