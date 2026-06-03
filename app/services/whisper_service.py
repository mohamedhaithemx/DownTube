# DownTube — توليد الترجمة بالذكاء الاصطناعي (Whisper)

"""
يستخدم faster-whisper لإنشاء ترجمة SRT للفيديوهات التي ليس لها
ترجمة على يوتيوب.
"""

import os
import subprocess
import tempfile
import logging
from typing import Optional

from app.config import WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, MAX_VIDEO_DURATION_FOR_WHISPER

logger = logging.getLogger(__name__)

_whisper_model = None


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("جاري تحميل نموذج Whisper (%s)...", WHISPER_MODEL_SIZE)
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        logger.info("تم تحميل النموذج بنجاح")
    return _whisper_model


def preload_model():
    """تحميل النموذج في الذاكرة (يُستدعى عند بداية السيرفر)."""
    _get_model()


def extract_audio(video_path: str) -> Optional[str]:
    """استخراج الصوت من الفيديو بصيغة WAV 16kHz mono."""
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path,
             "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1",
             "-threads", "2",
             wav_path],
            capture_output=True,
            timeout=600,
            check=True,
        )
        return wav_path
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.error("فشل استخراج الصوت: %s", e)
        if os.path.exists(wav_path):
            os.unlink(wav_path)
        return None


def transcribe(wav_path: str, lang: str = "ar") -> Optional[list]:
    """تشغيل Whisper على ملف الصوت وإرجاع الـ segments."""
    try:
        model = _get_model()
        segments, _info = model.transcribe(
            wav_path,
            language=lang,
            beam_size=5,
            vad_filter=True,
        )
        return list(segments)
    except Exception as e:
        logger.error("فشل التعرف على الصوت: %s", e)
        return None


def _format_timestamp(seconds: float) -> str:
    """تحويل الثواني إلى تنسيق SRT: HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list, output_path: str) -> str:
    """تحويل segments من Whisper إلى ملف SRT."""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_format_timestamp(seg.start)} --> {_format_timestamp(seg.end)}\n")
            f.write(f"{seg.text.strip()}\n\n")
    return output_path


def generate_subtitles(
    video_path: str,
    output_dir: str,
    title: str,
    lang: str = "ar",
    progress=None,
) -> Optional[str]:
    """
    إنشاء ترجمة SRT باستخدام Whisper.

    المعاملات:
        video_path: مسار ملف الفيديو
        output_dir: مجلد الإخراج
        title: عنوان الفيديو (لاسم الملف)
        lang: لغة الترجمة
        progress: متتبع التقدم

    Returns:
        مسار ملف الترجمة أو None
    """
    from app.services.subtitle import sanitize_filename

    safe_title = sanitize_filename(title)
    srt_path = os.path.join(output_dir, f"{safe_title}.srt")

    if os.path.exists(srt_path):
        logger.info("ملف الترجمة موجود بالفعل: %s", srt_path)
        return srt_path

    if progress:
        progress.update_phase_progress(0, message="جاري استخراج الصوت من الفيديو...")

    wav_path = extract_audio(video_path)
    if not wav_path:
        logger.error("فشل استخراج الصوت — لن يتم إنشاء ترجمة")
        return None

    try:
        if progress:
            progress.update_phase_progress(
                0, message="جاري التعرف على الكلام عبر Whisper (قد يستغرق عدة دقائق)..."
            )

        segments = transcribe(wav_path, lang)
        if not segments:
            logger.error("فشل التعرف على الكلام — لن يتم إنشاء ترجمة")
            return None

        if progress:
            progress.update_phase_progress(0, message="جاري كتابة ملف الترجمة...")

        segments_to_srt(segments, srt_path)
        logger.info("تم إنشاء الترجمة: %s (%d مقطع)", srt_path, len(segments))

        if progress:
            progress.update_phase_progress(100, message="تم إنشاء الترجمة بالذكاء الاصطناعي")

        return srt_path
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)
