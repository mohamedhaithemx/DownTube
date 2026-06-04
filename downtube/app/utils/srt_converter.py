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


def merge_short_segments(segments: list[dict], min_duration: float = 1.0) -> list[dict]:
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
            prev["end"] = seg["end"]
            prev["text"] = (prev["text"].rstrip(".!?،؛") + " " + text).strip()
        else:
            merged.append(dict(seg))
    return merged


def translate_segments_to_arabic(segments: list[dict], video_title: str = "", client=None) -> list[dict]:
    """
    ترجمة المقاطع إلى العربية باستخدام Groq Llama 3.3 70B.
    يُرسل النصوص على شكل JSON ويستقبل ترجمات JSON لضمان الدقة.
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

    batch_size = 50  # 70B يتعامل مع context أكبر بكفاءة
    translated_segments = list(segments)

    model = "llama-3.3-70b-versatile"

    for batch_start in range(0, len(text_parts), batch_size):
        batch_texts = text_parts[batch_start:batch_start + batch_size]

        # إرسال النصوص كـ JSON array لضمان دقة الاستجابة
        texts_json = json.dumps(batch_texts, ensure_ascii=False)

        prompt = (
            "أنت مترجم محترف. ترجم النصوص التالية من الإنجليزية إلى العربية الفصحى السهلة.\n\n"
            "القواعد:\n"
            "- الترجمة يجب أن تكون طبيعية وسلسة كما يتكلم الإنسان، ليست حرفية\n"
            "- حافظ على المعنى الكامل والسياق\n"
            "- المصطلحات التقنية: اتركها بالإنجليزية أو اكتبها بين قوسين\n"
            "- الأرقام والأسماء الخاصة: اتركها كما هي\n"
            "- أعد JSON فقط، بدون أي نص إضافي:\n"
            '{"translations": ["الترجمة 0", "الترجمة 1", ...]}\n\n'
            f"عنوان الفيديو: {video_title if video_title else 'غير معروف'}\n\n"
            f"النصوص:\n{texts_json}"
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "أنت مترجم محترف للعربية. ترجم النصوص ترجمة طبيعية سلسة. "
                            "أعد النتيجة كـ JSON فقط بالتنسيق: "
                            '{"translations": ["ترجمة 1", "ترجمة 2", ...]}'
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            translated = response.choices[0].message.content.strip()

            # محاولة تحليل JSON
            translated_lines = _parse_json_translations(translated, len(batch_texts))

            if len(translated_lines) == len(batch_texts):
                for i, tline in enumerate(translated_lines):
                    idx = batch_start + i
                    if idx < len(translated_segments):
                        translated_segments[idx]["text"] = tline
            else:
                logger.warning(
                    "عدد الترجمات (%d) لا يساوي المدخل (%d) — محاولة مطابقة جزئية",
                    len(translated_lines), len(batch_texts),
                )
                # مطابقة جزئية: املأ بقدر ما أمكن
                for i, tline in enumerate(translated_lines):
                    idx = batch_start + i
                    if idx < len(translated_segments):
                        translated_segments[idx]["text"] = tline

        except json.JSONDecodeError as e:
            logger.warning("فشل تحليل JSON من %s: %s — محاولة استخراج يدوي", model, e)
            translated_lines = _parse_numbered_response(translated if 'translated' in dir() else "", len(batch_texts))
            for i, tline in enumerate(translated_lines):
                idx = batch_start + i
                if idx < len(translated_segments):
                    translated_segments[idx]["text"] = tline
        except Exception as e:
            logger.warning("فشلت الترجمة بالموديل %s: %s", model, e)

    return translated_segments


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
        lines.append(text)
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
