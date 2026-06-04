import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from groq import Groq

from app.utils.validators import ERROR_MESSAGES
from app.utils.srt_converter import groq_json_to_srt, merge_short_segments, translate_segments_to_arabic

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1)

GROQ_MODEL = "whisper-large-v3"
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB


class GroqServiceError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


def _get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_api_key_here":
        raise GroqServiceError(ERROR_MESSAGES["groq_no_key"])
    return Groq(api_key=api_key)


def _transcribe_file(client: Groq, filepath: str, start_time: float = 0) -> list[dict]:
    with open(filepath, "rb") as f:
        result = client.audio.transcriptions.create(
            file=(os.path.basename(filepath), f),
            model=GROQ_MODEL,
            response_format="verbose_json",
            temperature=0,
        )
    segments = []
    for seg in getattr(result, "segments", []):
        segments.append({
            "start": seg.get("start", 0) + start_time,
            "end": seg.get("end", 0) + start_time,
            "text": seg.get("text", ""),
        })
    return segments


def _split_audio(audio_path: str, output_dir: str, max_size: int = MAX_FILE_SIZE) -> list[str]:
    import subprocess
    size = os.path.getsize(audio_path)
    if size <= max_size:
        return [audio_path]

    duration_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        audio_path,
    ]
    result = subprocess.run(duration_cmd, capture_output=True, text=True)
    try:
        total_duration = float(result.stdout.strip())
    except (ValueError, TypeError):
        raise GroqServiceError("تعذر حساب مدة الملف الصوتي")

    ratio = max_size / size
    segment_duration = total_duration * ratio * 0.95

    segment_pattern = os.path.join(output_dir, "segment_%03d.mp3")
    split_cmd = [
        "ffmpeg", "-y", "-v", "quiet",
        "-i", audio_path,
        "-f", "segment",
        "-segment_time", str(segment_duration),
        "-c", "copy",
        segment_pattern,
    ]
    subprocess.run(split_cmd, check=True, capture_output=True)

    segments = sorted([
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.startswith("segment_") and f.endswith(".mp3")
    ])
    return segments


async def generate_subtitles(
    audio_path: str,
    output_dir: str,
    task_id: str,
    title: str = "",
    progress_callback: callable = None,
) -> str:
    def _sync():
        client = _get_client()
        segments = _split_audio(audio_path, output_dir)
        all_segments = []
        total = len(segments)
        for i, seg_path in enumerate(segments):
            seg_start_time = 0.0
            if i > 0:
                from app.utils.file_manager import find_audio_file
                if os.path.getsize(seg_path) > MAX_FILE_SIZE:
                    raise GroqServiceError("ملف الصوت كبير جداً حتى بعد التقسيم")
            segs = _transcribe_file(client, seg_path, start_time=seg_start_time)
            all_segments.extend(segs)
            if progress_callback:
                progress_callback(((i + 1) / total) * 100, 0, 0)
            if len(segments) > 1:
                os.remove(seg_path)

        all_segments = merge_short_segments(all_segments)
        all_segments = translate_segments_to_arabic(all_segments, video_title=title, client=client)
        all_segments = merge_short_segments(all_segments)

        srt_content = groq_json_to_srt(all_segments)
        if not srt_content.strip():
            raise GroqServiceError("لم يتم التعرف على أي نص من ملف الصوت")
        safe_title = "".join(c for c in (title or task_id) if c.isalnum() or c in " ._-").strip() or task_id
        output_path = os.path.join(output_dir, f"{safe_title}.srt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        return output_path

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(_executor, _sync)
    except GroqServiceError:
        raise
    except Exception as e:
        err_msg = str(e).lower()
        if "rate_limit" in err_msg or "rate limit" in err_msg or "429" in str(e):
            raise GroqServiceError(ERROR_MESSAGES["groq_rate_limit"])
        if "too large" in err_msg or "413" in str(e):
            raise GroqServiceError(ERROR_MESSAGES["groq_file_too_large"])
        if "api key" in err_msg.lower():
            raise GroqServiceError(ERROR_MESSAGES["groq_no_key"])
        logger.exception("خطأ في توليد الترجمة عبر Groq")
        raise GroqServiceError(ERROR_MESSAGES["internal_error"])
