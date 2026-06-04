import os
import asyncio
import logging
from pathlib import Path

import yt_dlp

from app.utils.validators import ERROR_MESSAGES
from app.utils.srt_converter import validate_srt
from app.services.groq_service import generate_subtitles as groq_generate
from app.services.youtube_service import download_audio as yt_download_audio, extract_info

logger = logging.getLogger(__name__)

SUBTITLE_RETRIES = 3
SUBTITLE_DELAY = 3


class SubtitleError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


def _ydl_subtitle_opts():
    return {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "writesubtitles": True,
        "subtitleslangs": ["ar"],
        "writeautomaticsub": True,
        "skip_download": True,
        "outtmpl": "%(title)s.%(ext)s",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "retries": 3,
    }


async def _try_ytdl_subtitles(url: str, output_dir: str) -> str | None:
    def _sync():
        opts = _ydl_subtitle_opts()
        opts["outtmpl"] = os.path.join(output_dir, "%(title)s.%(ext)s")
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                ydl.extract_info(url, download=True)
            except Exception as e:
                logger.warning("فشل تنزيل الترجمات عبر yt-dlp: %s", e)
                return None
        srt_files = list(Path(output_dir).glob("*.srt"))
        vtt_files = list(Path(output_dir).glob("*.vtt"))
        for f in srt_files + vtt_files:
            name_lower = str(f).lower()
            if "ar" in name_lower:
                return str(f)
        if srt_files:
            return str(srt_files[0])
        if vtt_files:
            return str(vtt_files[0])
        return None

    loop = asyncio.get_event_loop()
    for attempt in range(SUBTITLE_RETRIES):
        result = await loop.run_in_executor(None, _sync)
        if result:
            renamed = _rename_to_video_name(result, output_dir)
            return renamed
        if attempt < SUBTITLE_RETRIES - 1:
            await asyncio.sleep(SUBTITLE_DELAY * (attempt + 1))
    return None


def _rename_to_video_name(filepath: str, output_dir: str) -> str:
    ext = os.path.splitext(filepath)[1]
    base = os.path.splitext(os.path.basename(filepath))[0]
    parts = base.rsplit(".", 1)
    title_part = parts[0] if len(parts) > 1 else base
    new_path = os.path.join(output_dir, f"{title_part}{ext}")
    if new_path != filepath and os.path.exists(filepath):
        try:
            os.rename(filepath, new_path)
            logger.info("تمت إعادة تسمية الترجمة: %s", os.path.basename(new_path))
            return new_path
        except OSError:
            pass
    return filepath


async def fetch_subtitles(
    url: str,
    output_dir: str,
    task_id: str,
    auto_generate: bool = True,
    progress_callback: callable = None,
) -> dict:
    logger.info("محاولة جلب الترجمة العربية لـ %s", url)

    subtitle_path = await _try_ytdl_subtitles(url, output_dir)
    if subtitle_path:
        with open(subtitle_path, encoding="utf-8") as f:
            content = f.read()
        is_valid = validate_srt(content) if subtitle_path.endswith(".srt") else True
        if is_valid:
            logger.info("تم العثور على ترجمة رسمية/تلقائية: %s", subtitle_path)
            return {
                "path": subtitle_path,
                "source": "youtube" if "ar" in str(subtitle_path).lower() else "auto",
                "type": "official" if "ar" in str(subtitle_path).lower() else "auto_generated",
            }

    if not auto_generate:
        logger.info("لا توجد ترجمة والتوليد التلقائي معطّل")
        return {"path": None, "source": None, "type": "none"}

    try:
        if progress_callback:
            progress_callback(0, 0, 0, "جاري تحميل الصوت للتوليد...")

        audio_path = await yt_download_audio(url, output_dir)
        if not audio_path or not os.path.exists(audio_path):
            raise SubtitleError("فشل تحميل ملف الصوت للتوليد")

        video_title = ""
        try:
            info = await extract_info(url)
            video_title = info.get("title", "")[:100]
        except Exception:
            logger.warning("فشل جلب عنوان الفيديو للتوليد")

        if progress_callback:
            progress_callback(30, 0, 0, "جاري توليد الترجمة عبر Groq...")

        srt_path = await groq_generate(
            audio_path=audio_path,
            output_dir=output_dir,
            task_id=task_id,
            title=video_title,
            progress_callback=lambda p, s, e, msg="": progress_callback(p, s, e, msg or "جاري توليد الترجمة...") if progress_callback else None,
        )

        if srt_path and os.path.exists(srt_path):
            logger.info("تم توليد الترجمة عبر Groq: %s", srt_path)
            return {
                "path": srt_path,
                "source": "groq",
                "type": "generated",
            }

        return {"path": None, "source": None, "type": "none"}

    except Exception as e:
        logger.exception("فشل توليد الترجمة عبر Groq")
        return {"path": None, "source": None, "type": "none", "error": str(e)}
