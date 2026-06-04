import os
import json
import subprocess
import logging
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from faster_whisper import WhisperModel

from app.utils.validators import ERROR_MESSAGES
from app.utils.srt_converter import groq_json_to_srt, merge_short_segments, translate_segments_to_arabic

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1)

_model = None
_model_lock = threading.Lock()

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

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


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info(
                    "تحميل نموذج faster-whisper %s على %s (%s)",
                    WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
                )
                _model = WhisperModel(
                    WHISPER_MODEL_SIZE,
                    device=WHISPER_DEVICE,
                    compute_type=WHISPER_COMPUTE_TYPE,
                )
                logger.info("تم تحميل النموذج بنجاح")
    return _model


def _has_arabic(text: str) -> bool:
    for c in text:
        cp = ord(c)
        for start, end in ARABIC_RANGES:
            if start <= cp <= end:
                return True
    return False


def _get_duration(filepath: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", filepath]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return float(json.loads(r.stdout)["format"]["duration"])


def _transcribe_local(
    audio_path: str,
    total_duration: float,
    progress_callback: callable = None,
) -> tuple[list[dict], str]:
    model = _get_model()
    segments_gen, info = model.transcribe(
        audio_path,
        beam_size=5,
        vad_filter=True,
        language=None,
    )

    detected_lang = info.language
    lang_prob = info.language_probability
    logger.info("اللغة المكتشفة: %s (احتمال: %.1f%%)", detected_lang, lang_prob * 100)

    results = []
    last_pct = -1
    for seg in segments_gen:
        results.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
        if progress_callback and total_duration > 0:
            pct = min(95, (seg.end / total_duration) * 95)
            if int(pct) != last_pct:
                last_pct = int(pct)
                progress_callback(pct, 0, 0)

    return results, detected_lang


async def generate_subtitles(
    audio_path: str,
    output_dir: str,
    task_id: str,
    title: str = "",
    progress_callback: callable = None,
) -> str:
    def _sync():
        if progress_callback:
            progress_callback(2, 0, 0)

        total_duration = _get_duration(audio_path)
        if total_duration <= 0:
            raise GroqServiceError("تعذر حساب مدة الملف الصوتي")

        if progress_callback:
            progress_callback(5, 0, 0)

        segments, detected_lang = _transcribe_local(
            audio_path, total_duration, progress_callback,
        )

        if not segments:
            raise GroqServiceError("لم يتم التعرف على أي نص")

        if progress_callback:
            progress_callback(95, 0, 0)

        segments = merge_short_segments(segments)

        needs_translation = (
            detected_lang != "ar"
            and not any(_has_arabic(seg.get("text", "")) for seg in segments)
        )

        if needs_translation:
            segments = translate_segments_to_arabic(segments, video_title=title)
            segments = merge_short_segments(segments)
        else:
            logger.info("النص عربي — تخطي الترجمة عبر Llama")

        if progress_callback:
            progress_callback(98, 0, 0)

        srt_content = groq_json_to_srt(segments)
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
        logger.exception("خطأ في توليد الترجمة عبر faster-whisper")
        raise GroqServiceError(str(e))
