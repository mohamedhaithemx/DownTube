import os
import re
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

    batch_size = 30
    translated_segments = list(segments)

    batch_models = ["llama-3.2-3b-preview"]

    for batch_start in range(0, len(text_parts), batch_size):
        batch_texts = text_parts[batch_start:batch_start + batch_size]
        numbered = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(batch_texts))

        prompt = (
            f"أنت مترجم محترف. ترجم النص التالي من مقطع فيديو إلى العربية الفصحى الطبيعية.\n\n"
            f"عنوان الفيديو: {video_title if video_title else 'غير معروف'}\n\n"
            f"تعليمات:\n"
            f"- ترجم ترجمة طبيعية سلسة، وليس حرفية كلمة بكلمة\n"
            f"- حافظ على المعنى ولكن استخدم تعابير عربية طبيعية\n"
            f"- حافظ على علامات الترقيم العربية الصحيحة\n"
            f"- أخرج الترجمة بنفس تنسيق الإدخال: [1] النص المترجم [2] النص المترجم ... إلخ\n"
            f"- عدد الأسطر يجب أن يكون بالضبط {len(batch_texts)}\n\n"
            f"النص:\n{numbered}"
        )

        try:
            response = client.chat.completions.create(
                model=batch_models[0],
                messages=[
                    {"role": "system", "content": "أنت مترجم محترف للعربية. ترجم النصوص ترجمة طبيعية سلسة."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2048,
            )
            translated = response.choices[0].message.content.strip()
            translated_lines = _parse_numbered_response(translated, len(batch_texts))
            if len(translated_lines) == len(batch_texts):
                for i, tline in enumerate(translated_lines):
                    idx = batch_start + i
                    if idx < len(translated_segments):
                        translated_segments[idx]["text"] = tline
            else:
                logger.warning("عدد الأسطر المترجمة (%d) لا يساوي المدخل (%d)", len(translated_lines), len(batch_texts))
        except Exception as e:
            logger.warning("فشلت الترجمة بالموديل %s: %s", batch_models[0], e)

    return translated_segments


def _parse_numbered_response(text: str, expected_count: int) -> list[str]:
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
