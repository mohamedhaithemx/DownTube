# DownTube — خدمة التحميل الرئيسية

"""
يتولى هذا الملف منطق التحميل الكامل باستخدام yt-dlp:
- جلب معلومات الفيديو
- التحقق من الترجمة
- تنزيل الفيديو والترجمة كملفين منفصلين
- تتبع التقدم وإرسال التحديثات
"""

import os
import time
import shutil
import threading
import logging
from typing import Optional

import yt_dlp

from app.config import (
    DEFAULT_DOWNLOAD_DIR,
    MAX_TITLE_LENGTH,
    SUBTITLE_PREFERRED_FORMAT,
    PHASE_FETCH_INFO,
    PHASE_CHECK_SUBTITLE,
    PHASE_DOWNLOAD_VIDEO,
    PHASE_DOWNLOAD_SUBTITLE,
    PHASE_PROCESSING,
)
from app.exceptions import (
    InvalidURLError,
    VideoUnavailableError,
    DownloadCancelledError,
    FFmpegNotFoundError,
)
from app.services.anti_block import (
    build_ytdlp_options,
    retry_with_backoff,
    get_random_delay,
)
from app.services.subtitle import check_subtitles, find_subtitle_file, rename_subtitle_file
from app.services.progress import ProgressTracker

logger = logging.getLogger(__name__)


def _find_ffmpeg_path() -> Optional[str]:
    """البحث عن FFmpeg في النظام. يرجع None إذا كان في PATH."""
    if shutil.which("ffmpeg"):
        return None  # yt-dlp سيجده تلقائياً

    # البحث بجانب الملف التنفيذي أو مجلد المشروع
    import sys
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        bundled = os.path.join(base, "ffmpeg", "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if os.path.isfile(bundled):
            return os.path.dirname(bundled)

    return None


class DownloadService:
    """خدمة التحميل الرئيسية — تُستخدم من خيط خلفي (background thread)."""

    def __init__(self):
        self.cancel_event = threading.Event()
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    @is_active.setter
    def is_active(self, value: bool):
        self._active = value

    def cancel(self):
        """إلغاء التحميل الحالي."""
        self.cancel_event.set()

    def _check_cancelled(self):
        """رفع استثناء إذا تم الإلغاء."""
        if self.cancel_event.is_set():
            raise DownloadCancelledError()

    def extract_info(self, url: str, cookiefile: Optional[str] = None, proxy: Optional[str] = None) -> dict:
        """
        جلب معلومات الفيديو بدون تحميل.
        
        المعاملات:
            url: رابط يوتيوب
            cookiefile: مسار ملف الكوكيز (اختياري)
            proxy: عنوان البروكسي (اختياري)
        """
        self._check_cancelled()

        # تأخير عشوائي قبل الطلب
        time.sleep(get_random_delay())

        opts = build_ytdlp_options(
            cookiefile=cookiefile,
            proxy=proxy,
            extra_opts={"extract_flat": False},
        )

        # محاولة مع إعادة المحاولة عند 429/403
        def _do_extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = retry_with_backoff(_do_extract)
        return info

    def download(
        self,
        url: str,
        output_dir: str,
        lang: str = "ar",
        include_subtitle: bool = True,
        cookiefile: Optional[str] = None,
        proxy: Optional[str] = None,
        progress: Optional[ProgressTracker] = None,
    ) -> dict:
        """
        تنزيل فيديو يوتيوب مع الترجمة.
        
        المعاملات:
            url: رابط يوتيوب
            output_dir: مجلد الحفظ
            lang: لغة الترجمة
            include_subtitle: تحميل الترجمة؟
            cookiefile: مسار ملف الكوكيز
            proxy: عنوان البروكسي
            progress: متتبع التقدم
        
        Returns:
            قاموس بنتائج التحميل
        """
        self.cancel_event.clear()
        self._active = True

        try:
            return self._do_download(
                url, output_dir, lang, include_subtitle, cookiefile, proxy, progress
            )
        except DownloadCancelledError:
            if progress:
                progress.error("تم إلغاء التحميل")
            return {"success": False, "error": "تم إلغاء التحميل"}
        except Exception as e:
            logger.exception("فشل التحميل: %s", e)
            if progress:
                progress.error(self._map_error(e))
            return {"success": False, "error": self._map_error(e)}
        finally:
            self._active = False

    def _do_download(
        self,
        url: str,
        output_dir: str,
        lang: str,
        include_subtitle: bool,
        cookiefile: Optional[str],
        proxy: Optional[str],
        progress: Optional[ProgressTracker],
    ) -> dict:
        """المنطق الداخلي للتحميل."""

        # ── المرحلة 0: جلب معلومات الفيديو ──────────────
        if progress:
            progress.set_phase(0, "جاري جلب معلومات الفيديو...")

        info = self.extract_info(url, cookiefile, proxy)
        title = info.get("title", "unknown")[:MAX_TITLE_LENGTH]
        self._check_cancelled()

        if progress:
            progress.update_phase_progress(100, message=f"تم جلب المعلومات: {title}")

        # ── المرحلة 1: التحقق من الترجمة ──────────────────
        if progress:
            progress.set_phase(1, "جاري التحقق من الترجمة...")

        subtitle_info = None
        if include_subtitle:
            subtitle_info = check_subtitles(info, lang)

            if subtitle_info:
                sub_type = "رسمية" if subtitle_info["type"] == "official" else "تلقائية"
                if progress:
                    progress.update_phase_progress(
                        100,
                        message=f"ترجمة {sub_type} متاحة: {subtitle_info['key']}"
                    )
            else:
                if progress:
                    progress.update_phase_progress(
                        100,
                        message="لا توجد ترجمة عربية"
                    )
                    progress.info("NO_SUBTITLE")

        self._check_cancelled()

        # ── المرحلة 2: تنزيل الفيديو ─────────────────────
        if progress:
            progress.set_phase(2, "جاري تنزيل الفيديو...")

        os.makedirs(output_dir, exist_ok=True)
        ffmpeg_location = _find_ffmpeg_path()

        output_template = os.path.join(output_dir, "%(title).100s.%(ext)s")
        extra_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": output_template,
        }

        # إعداد خيارات الترجمة
        write_subtitles = False
        subtitle_lang_key = None
        if include_subtitle and subtitle_info:
            write_subtitles = True
            subtitle_lang_key = subtitle_info["key"]
            extra_opts["writesubtitles"] = True
            extra_opts["subtitleslangs"] = [subtitle_lang_key]
            extra_opts["subtitlesformat"] = SUBTITLE_PREFERRED_FORMAT

        if ffmpeg_location is not None:
            extra_opts["ffmpeg_location"] = ffmpeg_location

        # بناء خيارات yt-dlp مع الـ progress hook
        def make_progress_hook():
            def hook(d):
                self._check_cancelled()
                if d["status"] == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0)
                    speed = d.get("speed") or 0
                    eta = d.get("eta") or 0

                    percent = 0
                    if total > 0:
                        percent = downloaded / total * 100

                    if progress:
                        progress.update_phase_progress(
                            percent,
                            speed=speed,
                            eta=eta,
                            message=f"تنزيل الفيديو: {percent:.0f}%"
                        )
                elif d["status"] == "finished":
                    if progress:
                        progress.update_phase_progress(100, message="تم تنزيل الفيديو، جاري الدمج...")
            return hook

        opts = build_ytdlp_options(
            cookiefile=cookiefile,
            proxy=proxy,
            extra_opts={
                **extra_opts,
                "progress_hooks": [make_progress_hook()],
                "quiet": False,
                "no_warnings": False,
            },
        )

        # تنفيذ التحميل مع إعادة المحاولة
        def _do_download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        retry_with_backoff(_do_download)
        self._check_cancelled()

        # ── المرحلة 3: تنزيل/معالجة الترجمة ──────────────
        subtitle_file = None
        subtitle_type = None

        if progress:
            progress.set_phase(3, "جاري معالجة الترجمة...")

        if write_subtitles and subtitle_info:
            sub_path = find_subtitle_file(output_dir)
            if sub_path:
                subtitle_file = rename_subtitle_file(sub_path, title, subtitle_lang_key)
                subtitle_type = subtitle_info["type"]
                if progress:
                    progress.update_phase_progress(100, message="تمت معالجة الترجمة")
            else:
                if progress:
                    progress.update_phase_progress(100, message="لم يتم العثور على ملف الترجمة")
        else:
            if progress:
                progress.update_phase_progress(100, message="تم تخطي الترجمة")

        self._check_cancelled()

        # ── المرحلة 4: المعالجة النهائية ──────────────────
        if progress:
            progress.set_phase(4, "جاري المعالجة النهائية...")

        # البحث عن ملف الفيديو المحمل
        video_file = self._find_video_file(output_dir, title)

        if progress:
            progress.update_phase_progress(100, message="اكتمل التحميل!")

        # إرسال نتيجة نهائية
        result = {
            "success": True,
            "title": title,
            "video_file": video_file,
            "subtitle_file": subtitle_file,
            "subtitle_type": subtitle_type,
        }

        if progress:
            progress.finish("تم التحميل بنجاح!", result=result)

        return result

    def _find_video_file(self, directory: str, title: str) -> Optional[str]:
        """البحث عن ملف الفيديو المحمل مؤخراً."""
        pattern = os.path.join(directory, "*.mp4")
        files = [f for f in glob.glob(pattern) if os.path.isfile(f)]

        if not files:
            return None

        # أحدث ملف
        files.sort(key=os.path.getmtime, reverse=True)
        now = time.time()

        for f in files:
            if now - os.path.getmtime(f) < 300:  # أقل من 5 دقائق
                return f

        return files[0]

    def _map_error(self, exc: Exception) -> str:
        """تحويل الاستثناءات إلى رسائل عربية."""
        msg = str(exc).lower()

        if "private" in msg:
            return "هذا الفيديو خاص ولا يمكن تحميله"
        if "unavailable" in msg or "removed" in msg:
            return "هذا الفيديو غير متاح أو تم حذفه"
        if "captcha" in msg:
            return "يطلب يوتيوب تحقق بشري (كابتشا). حاول لاحقاً"
        if "429" in msg or "too many" in msg:
            return "تم حظر الطلبات مؤقتاً. حاول مرة أخرى بعد قليل"
        if "403" in msg:
            return "تم رفض الوصول. حاول مع كوكيز أو بروكسي"
        if "age" in msg and "restrict" in msg:
            return "هذا الفيديو مقيد بالعمر ولا يمكن تحميله"
        if "sign in" in msg:
            return "هذا الفيديو يتطلب تسجيل الدخول"
        if "country" in msg or "region" in msg or "blocked" in msg:
            return "هذا الفيديو محظور في منطقتك"
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return "خطأ في الاتصال. تأكد من الإنترنت وحاول مرة أخرى"
        if isinstance(exc, DownloadCancelledError):
            return "تم إلغاء التحميل"

        return f"حدث خطأ: {str(exc)[:200]}"


# ── مثيل عام (singleton) ────────────────────────────────────
download_service = DownloadService()


import glob  # تأكد من الاستيراد
