import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from groq import Groq

from app.utils.validators import ERROR_MESSAGES
from app.utils.srt_converter import groq_json_to_srt, merge_short_segments, translate_segments_to_arabic

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1)
_parallel_executor = ThreadPoolExecutor(max_workers=3)

GROQ_MODEL = "whisper-large-v3"
MAX_FILE_SIZE = 25 * 1024 * 1024

ARABIC_RANGES = [
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFE70, 0xFEFF),
    (0xFB50, 0xFDFF),
]


class GroqServiceError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


def _get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "your_groq_api_key_here":
        raise GroqServiceError(ERROR_MESSAGES["groq_no_key"])
    return Groq(api_key=api_key)


def _has_arabic(text: str) -> bool:
    for c in text:
        cp = ord(c)
        for start, end in ARABIC_RANGES:
            if start <= cp <= end:
                return True
    return False


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


def _transcribe_parallel(segments_with_times: list[tuple[str, float]], progress_callback) -> list[dict]:
    total = len(segments_with_times)
    if total == 0:
        return []
    if total == 1:
        client = _get_client()
        segs = _transcribe_file(client, segments_with_times[0][0], segments_with_times[0][1])
        if progress_callback:
            progress_callback(80, 0, 0)
        return segs

    results = [None] * total

    def transcribe_one(idx: int, path: str, start: float) -> list[dict]:
        c = _get_client()
        return _transcribe_file(c, path, start)

    futures = {}
    with ThreadPoolExecutor(max_workers=min(3, total)) as pool:
        for i, (path, start) in enumerate(segments_with_times):
            futures[pool.submit(transcribe_one, i, path, start)] = i

        for f in as_completed(futures):
            idx = futures[f]
            try:
                results[idx] = f.result()
            except Exception as e:
                logger.error("فشل transcribe للجزء %d: %s", idx, e)
                raise
            if progress_callback:
                pct = 10 + ((idx + 1) / total) * 70
                progress_callback(pct, 0, 0)

    merged = []
    for seg_list in results:
        if seg_list:
            merged.extend(seg_list)
    return merged


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


def _get_duration(filepath: str) -> float:
    import subprocess, json
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", filepath]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return float(json.loads(r.stdout)["format"]["duration"])


async def generate_subtitles(
    audio_path: str,
    output_dir: str,
    task_id: str,
    title: str = "",
    progress_callback: callable = None,
) -> str:
    def _sync():
        client = _get_client()

        if progress_callback:
            progress_callback(2, 0, 0)

        segment_paths = _split_audio(audio_path, output_dir)

        if progress_callback:
            progress_callback(5, 0, 0)

        # Compute durations + start times for each segment
        seg_info = []
        for seg_path in segment_paths:
            duration = _get_duration(seg_path)
            seg_info.append((seg_path, duration))

        seg_start_time = 0.0
        segments_with_times = []
        for seg_path, duration in seg_info:
            segments_with_times.append((seg_path, seg_start_time))
            seg_start_time += duration

        # Parallel transcription
        all_segments = _transcribe_parallel(segments_with_times, progress_callback)

        if progress_callback:
            progress_callback(82, 0, 0)

        all_segments = merge_short_segments(all_segments)

        # Check if translation is needed
        needs_translation = not any(_has_arabic(seg.get("text", "")) for seg in all_segments)

        if needs_translation:
            if progress_callback:
                progress_callback(85, 0, 0)
            all_segments = translate_segments_to_arabic(all_segments, video_title=title, client=client)
            all_segments = merge_short_segments(all_segments)
        else:
            logger.info("النص عربي، تخطي الترجمة عبر Llama")

        if progress_callback:
            progress_callback(95, 0, 0)

        srt_content = groq_json_to_srt(all_segments)
        if not srt_content.strip():
            raise GroqServiceError("لم يتم التعرف على أي نص من ملف الصوت")
        safe_title = "".join(c for c in (title or task_id) if c.isalnum() or c in " ._-").strip() or task_id
        output_path = os.path.join(output_dir, f"{safe_title}.srt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        if progress_callback:
            progress_callback(100, 0, 0)

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
