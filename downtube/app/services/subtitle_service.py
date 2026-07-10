import os
import asyncio
import logging
from pathlib import Path

from app.utils.validators import ERROR_MESSAGES
from app.utils.srt_converter import (
    validate_srt,
    parse_srt_to_segments,
    groq_json_to_srt,
    deduplicate_text_overlap,
    max_lines_per_segment,
)
from app.services.groq_service import generate_subtitles as groq_generate
from app.services.youtube_service import download_audio as yt_download_audio, extract_info

logger = logging.getLogger(__name__)

SUBTITLE_MAX_LINES = int(os.getenv("SUBTITLE_MAX_LINES", "2"))


class SubtitleError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


async def fetch_subtitles(
    url: str,
    output_dir: str,
    task_id: str,
    auto_generate: bool = True,
    progress_callback: callable = None,
) -> dict:
    """
    توليد الترجمة العربية فوراً بدون البحث عن ترجمات يوتيوب.
    يقوم بتحميل الصوت ثم توليد الترجمة العربية مباشرة عبر Groq Whisper.
    """
    logger.info("بدء توليد الترجمة العربية فوراً لـ %s", url)

    def _report(pct: int, speed: float = 0, eta: float = 0, msg: str = ""):
        if progress_callback:
            progress_callback(pct, speed, eta, msg)

    if not auto_generate:
        logger.info("التوليد التلقائي معطّل")
        return {"path": None, "source": None, "type": "none"}

    try:
        # ── المرحلة 1: تحميل الصوت (0% → 20%) ──
        _report(2, 0, 0, "جاري تحميل الصوت لتوليد الترجمة العربية...")

        audio_path = await yt_download_audio(url, output_dir, progress_callback=progress_callback)
        if not audio_path or not os.path.exists(audio_path):
            raise SubtitleError("فشل تحميل ملف الصوت للتوليد")

        _report(20, 0, 0, "تم تحميل الصوت — جاري بدء التوليد...")

        # ── المرحلة 2: جلب عنوان الفيديو ──
        video_title = ""
        try:
            info = await extract_info(url)
            video_title = info.get("title", "")[:100]
        except Exception:
            logger.warning("فشل جلب عنوان الفيديو للتوليد — سيُستخدم اسم افتراضي")

        # ── المرحلة 3: توليد الترجمة العربية عبر Groq Whisper (20% → 95%) ──
        _report(22, 0, 0, "جاري توليد الترجمة العربية عبر Whisper...")

        srt_path = await groq_generate(
            audio_path=audio_path,
            output_dir=output_dir,
            task_id=task_id,
            title=video_title,
            progress_callback=lambda p, s, e, msg="": progress_callback(
                22 + (p * 0.73), s, e, msg or "جاري توليد الترجمة العربية..."
            ) if progress_callback else None,
        )

        if srt_path and os.path.exists(srt_path):
            logger.info("تم توليد الترجمة العربية: %s", srt_path)

            # ── المرحلة 4: تنسيق الترجمة (95% → 100%) ──
            _report(95, 0, 0, "جاري تنسيق الترجمة العربية...")
            try:
                with open(srt_path, encoding="utf-8") as f:
                    srt_content = f.read()
                segs = parse_srt_to_segments(srt_content)
                if segs:
                    segs = max_lines_per_segment(segs, SUBTITLE_MAX_LINES)
                    new_srt = groq_json_to_srt(segs)
                    with open(srt_path, "w", encoding="utf-8") as f:
                        f.write(new_srt)
            except Exception as e:
                logger.warning("فشل تنسيق الأسطر: %s", e)

            _report(100, 0, 0, "اكتملت الترجمة العربية!")
            return {
                "path": srt_path,
                "source": "groq",
                "type": "generated",
            }

        _report(100, 0, 0, "لم يتم توليد ترجمة")
        return {"path": None, "source": None, "type": "none"}

    except Exception as e:
        logger.exception("فشل توليد الترجمة العربية: %s", e)
        return {"path": None, "source": None, "type": "none", "error": str(e)}
