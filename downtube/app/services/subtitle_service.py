import os
import asyncio
import logging
from pathlib import Path

import yt_dlp

from app.utils.validators import ERROR_MESSAGES
from app.utils.srt_converter import (
    validate_srt,
    parse_srt_to_segments,
    groq_json_to_srt,
    deduplicate_text_overlap,
    max_lines_per_segment,
    translate_segments_to_arabic,
)
from app.services.groq_service import generate_subtitles as groq_generate
from app.services.youtube_service import download_audio as yt_download_audio, extract_info

logger = logging.getLogger(__name__)

SUBTITLE_RETRIES = 3
SUBTITLE_DELAY = 3
SUBTITLE_MAX_LINES = int(os.getenv("SUBTITLE_MAX_LINES", "2"))


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
        "subtitleslangs": ["ar", "en"],
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


async def _try_ytdl_subtitles(url: str, output_dir: str, progress_callback: callable = None) -> tuple[str | None, str | None]:
    """
    محاولة جلب الترجمات من يوتيوب.
    ترجع (filepath, detected_lang) — اللغة تكون 'ar' أو 'en' أو None.
    """

    def _report(pct: int, msg: str = ""):
        if progress_callback:
            progress_callback(pct, 0, 0, msg)

    def _sync():
        opts = _ydl_subtitle_opts()
        opts["outtmpl"] = os.path.join(output_dir, "%(title)s.%(ext)s")
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                ydl.extract_info(url, download=True)
            except Exception as e:
                logger.warning("فشل تنزيل الترجمات عبر yt-dlp: %s", e)
                return None, None

        # جمع كل ملفات الترجمة
        srt_files = list(Path(output_dir).glob("*.srt"))
        vtt_files = list(Path(output_dir).glob("*.vtt"))
        all_files = [(str(f), f.stem.lower()) for f in srt_files + vtt_files]

        if not all_files:
            return None, None

        # الأولوية: عربي > إنجليزي > أول ملف
        for filepath, stem in all_files:
            if "ar" in stem:
                return filepath, "ar"
        for filepath, stem in all_files:
            if "en" in stem or "english" in stem:
                return filepath, "en"
        return all_files[0][0], None

    _report(3, "جاري فحص الترجمات المتاحة...")
    loop = asyncio.get_event_loop()

    for attempt in range(SUBTITLE_RETRIES):
        _report(3 + attempt * 2, f"محاولة {attempt + 1} من {SUBTITLE_RETRIES}...")
        filepath, lang = await loop.run_in_executor(None, _sync)
        if filepath:
            _report(10, "تم العثور على ترجمة!")
            renamed = _rename_to_video_name(filepath, output_dir)
            return renamed, lang
        if attempt < SUBTITLE_RETRIES - 1:
            await asyncio.sleep(SUBTITLE_DELAY * (attempt + 1))

    _report(10, "لا توجد ترجمة متاحة")
    return None, None


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


async def _translate_youtube_subs(
    filepath: str,
    lang: str,
    output_dir: str,
    task_id: str,
    progress_callback: callable = None,
) -> str | None:
    """
    ترجمة ترجمة يوتيوب (إنجليزي) إلى عربية عبر Llama.
    ترجع مسار ملف SRT العربي الجديد.
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        segments = parse_srt_to_segments(content)
        if not segments:
            logger.warning("لا يوجد مقاطع في ملف الترجمة: %s", filepath)
            return None

        if progress_callback:
            progress_callback(30, 0, 0, f"جاري ترجمة {len(segments)} مقطع...")

        # ترجمة إلى عربية
        loop = asyncio.get_event_loop()
        video_title = Path(filepath).stem
        translated = await loop.run_in_executor(
            None,
            lambda: translate_segments_to_arabic(
                segments, video_title,
                source_lang=lang if lang else "en",
            ),
        )

        if progress_callback:
            progress_callback(80, 0, 0, "جاري معالجة النص المترجم...")

        # تنظيف التكرار + تحديد عدد الأسطر
        translated = deduplicate_text_overlap(translated)
        translated = max_lines_per_segment(translated, SUBTITLE_MAX_LINES)

        # توليد SRT
        srt_content = groq_json_to_srt(translated)
        if not srt_content.strip():
            logger.warning("الترجمة الناتجة فارغة")
            return None

        base = os.path.splitext(os.path.basename(filepath))[0]
        out_path = os.path.join(output_dir, f"{base}.ar.srt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        logger.info("تمت ترجمة الترجمة: %s → %s", os.path.basename(filepath), out_path)
        if progress_callback:
            progress_callback(100, 0, 0, "اكتملت الترجمة!")

        return out_path

    except Exception as e:
        logger.exception("فشلت ترجمة الترجمة: %s", e)
        return None


async def fetch_subtitles(
    url: str,
    output_dir: str,
    task_id: str,
    auto_generate: bool = True,
    progress_callback: callable = None,
) -> dict:
    logger.info("محاولة جلب الترجمة لـ %s", url)

    # ── المرحلة 1: جلب ترجمة يوتيوب (1% → 10%) ──
    subtitle_path, lang = await _try_ytdl_subtitles(url, output_dir, progress_callback)

    if subtitle_path:
        with open(subtitle_path, encoding="utf-8") as f:
            content = f.read()

        # لو عربي — استخدم مباشرة
        if lang == "ar":
            is_valid = validate_srt(content) if subtitle_path.endswith(".srt") else True
            if is_valid:
                logger.info("تم العثور على ترجمة عربية رسمية: %s", subtitle_path)
                if progress_callback:
                    progress_callback(100, 0, 0, "الترجمة العربية جاهزة!")
                return {
                    "path": subtitle_path,
                    "source": "youtube",
                    "type": "official",
                }

        # لو إنجليزي أو غيره — ترجم إلى عربية
        if progress_callback:
            progress_callback(15, 0, 0, "جاري ترجمة الترجمة إلى العربية...")

        translated_path = await _translate_youtube_subs(
            subtitle_path, lang or "en",
            output_dir, task_id,
            progress_callback,
        )
        if translated_path and os.path.exists(translated_path):
            return {
                "path": translated_path,
                "source": "youtube",
                "type": "generated",
            }

        # لو فشلت الترجمة — استخدم الترجمة الأصلية كـ fallback
        logger.warning("فشلت الترجمة — استخدام الترجمة الأصلية كـ fallback")
        if progress_callback:
            progress_callback(100, 0, 0, "استخدام الترجمة الأصلية")
        return {
            "path": subtitle_path,
            "source": "youtube",
            "type": "auto_generated",
        }

    # ── المرحلة 2: لا توجد ترجمة — توليد عبر Whisper ──
    if not auto_generate:
        logger.info("لا توجد ترجمة والتوليد التلقائي معطّل")
        return {"path": None, "source": None, "type": "none"}

    try:
        if progress_callback:
            progress_callback(12, 0, 0, "جاري تحميل الصوت للتوليد...")

        audio_path = await yt_download_audio(url, output_dir, progress_callback=progress_callback)
        if not audio_path or not os.path.exists(audio_path):
            raise SubtitleError("فشل تحميل ملف الصوت للتوليد")

        video_title = ""
        try:
            info = await extract_info(url)
            video_title = info.get("title", "")[:100]
        except Exception:
            logger.warning("فشل جلب عنوان الفيديو للتوليد")

        if progress_callback:
            progress_callback(20, 0, 0, "جاري توليد الترجمة عبر Groq...")

        srt_path = await groq_generate(
            audio_path=audio_path,
            output_dir=output_dir,
            task_id=task_id,
            title=video_title,
            progress_callback=lambda p, s, e, msg="": progress_callback(p, s, e, msg or "جاري توليد الترجمة...") if progress_callback else None,
        )

        if srt_path and os.path.exists(srt_path):
            logger.info("تم توليد الترجمة عبر Groq: %s", srt_path)

            # تطبيق max_lines_per_segment على الناتج النهائي
            if progress_callback:
                progress_callback(95, 0, 0, "جاري تنسيق الترجمة...")
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

            return {
                "path": srt_path,
                "source": "groq",
                "type": "generated",
            }

        return {"path": None, "source": None, "type": "none"}

    except Exception as e:
        logger.exception("فشل توليد الترجمة عبر Groq")
        return {"path": None, "source": None, "type": "none", "error": str(e)}
