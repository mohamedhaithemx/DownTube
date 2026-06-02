"""
محمل الفيديوهات الرئيسي
YouTube Video Downloader with yt-dlp
"""

import os
import asyncio
import logging
import time
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from .anti_ban import anti_ban
from .subtitle_handler import SubtitleConverter, SubtitleInfo


class CancelledError(Exception):
    """رفع عند إلغاء التحميل من قبل المستخدم"""
    pass

logger = logging.getLogger(__name__)


def _extract_429_status(e: Exception) -> Optional[int]:
    """استخراج status_code 429 من رسالة الخطأ"""
    msg = str(e)
    if "429" in msg or "Too Many Requests" in msg:
        return 429
    return None


class DownloadStatus(Enum):
    """حالات التحميل"""
    IDLE = "idle"
    FETCHING_INFO = "fetching_info"
    DOWNLOADING_SUBTITLE = "downloading_subtitle"
    WAITING_ANTI_BAN = "waiting_anti_ban"
    DOWNLOADING_VIDEO = "downloading_video"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class VideoInfo:
    """معلومات الفيديو"""
    title: str = ""
    video_id: str = ""
    duration: int = 0
    thumbnail: str = ""
    description: str = ""
    uploader: str = ""
    view_count: int = 0
    available_subtitles: List[SubtitleInfo] = field(default_factory=list)
    formats: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DownloadProgress:
    """تقدم التحميل"""
    status: DownloadStatus = DownloadStatus.IDLE
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    filename: str = ""
    message: str = ""


class YouTubeDownloader:
    """
    محمل فيديوهات يوتيوب مع استراتيجيات مضادة للحظر
    """

    def __init__(self, download_dir: str = "/tmp/youtube_downloads"):
        self.download_dir = download_dir
        self._cancelled = False
        self._current_process = None
        self.progress = DownloadProgress()
        self._progress_callback: Optional[Callable] = None
        self.subtitle_converter = SubtitleConverter()

        os.makedirs(download_dir, exist_ok=True)

    def set_progress_callback(self, callback: Callable):
        """تعيين دالة callback لتحديث التقدم"""
        self._progress_callback = callback

    def _update_progress(self, **kwargs):
        """تحديث حالة التقدم"""
        for key, value in kwargs.items():
            if hasattr(self.progress, key):
                setattr(self.progress, key, value)

        if self._progress_callback:
            self._progress_callback(self.progress)

    def cancel_download(self):
        """إلغاء التحميل الحالي"""
        self._cancelled = True
        self._update_progress(status=DownloadStatus.CANCELLED, message="تم إلغاء التحميل")
        logger.info("Download cancelled by user")

        # محاولة إنهاء العملية الحالية
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                pass

    async def fetch_video_info(self, url: str) -> VideoInfo:
        """جلب معلومات الفيديو"""
        self._cancelled = False
        self._update_progress(status=DownloadStatus.FETCHING_INFO, message="جاري جلب معلومات الفيديو...")

        await anti_ban.wait_before_request()

        try:
            import yt_dlp

            ydl_opts = {
                **anti_ban.get_ydl_opts_additions(),
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }

            loop = asyncio.get_event_loop()

            def _extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, _extract_info)

            if not info:
                raise Exception("لم يتم العثور على معلومات الفيديو")

            video_info = VideoInfo(
                title=info.get('title', 'غير معروف'),
                video_id=info.get('id', ''),
                duration=info.get('duration', 0),
                thumbnail=info.get('thumbnail', ''),
                description=info.get('description', '')[:500] if info.get('description') else '',
                uploader=info.get('uploader', ''),
                view_count=info.get('view_count', 0),
            )

            # استخراج الترجمات المتاحة
            subtitles = info.get('subtitles', {})
            auto_captions = info.get('automatic_captions', {})

            for lang_code, subs in subtitles.items():
                for sub in subs:
                    video_info.available_subtitles.append(SubtitleInfo(
                        language=self._get_language_name(lang_code),
                        language_code=lang_code,
                        auto_generated=False,
                        url=sub.get('url', ''),
                    ))
                    break  # نأخذ أول صيغة فقط لكل لغة

            for lang_code, subs in auto_captions.items():
                # تجنب التكرار إذا كانت الترجمة اليدوية موجودة
                if not any(s.language_code == lang_code for s in video_info.available_subtitles):
                    for sub in subs:
                        video_info.available_subtitles.append(SubtitleInfo(
                            language=self._get_language_name(lang_code) + " (تلقائي)",
                            language_code=lang_code,
                            auto_generated=True,
                            url=sub.get('url', ''),
                        ))
                        break

            anti_ban.report_success()
            self._update_progress(status=DownloadStatus.IDLE, message="تم جلب المعلومات بنجاح")

            return video_info

        except Exception as e:
            if self._cancelled:
                raise CancelledError("تم إلغاء التحميل")
            anti_ban.report_failure(status_code=_extract_429_status(e))
            self._update_progress(status=DownloadStatus.FAILED, message=f"فشل جلب المعلومات: {str(e)}")
            raise

    async def download_subtitle(
        self,
        url: str,
        language_code: str = "ar",
        subtitle_format: str = "srt",
        auto_generated: bool = True,
    ) -> Optional[str]:
        """
        تحميل الترجمة باللغة المحددة
        """
        self._update_progress(
            status=DownloadStatus.DOWNLOADING_SUBTITLE,
            message=f"جاري تحميل الترجمة ({language_code})...",
            percent=0
        )

        if self._cancelled:
            return None

        await anti_ban.wait_before_request()

        try:
            import yt_dlp

            subtitle_key = f"{language_code}"
            write_sub = not auto_generated
            write_auto_sub = auto_generated

            # تحديد صيغة الترجمة
            sub_format = "vtt" if subtitle_format == "vtt" else "srt"

            subtitle_path = os.path.join(self.download_dir, f"subtitle_temp")

            ydl_opts = {
                **anti_ban.get_ydl_opts_additions(),
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'writesubtitles': write_sub,
                'writeautomaticsub': write_auto_sub,
                'subtitleslangs': [language_code],
                'subtitlesformat': sub_format,
                'outtmpl': subtitle_path,
                'postprocessors': [{
                    'key': 'FFmpegSubtitlesConvertor',
                    'format': sub_format,
                }] if sub_format != 'vtt' else [],
            }

            loop = asyncio.get_event_loop()

            def _download_sub():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.download([url])

            result = await loop.run_in_executor(None, _download_sub)

            self._update_progress(
                status=DownloadStatus.DOWNLOADING_SUBTITLE,
                percent=100,
                message="تم تحميل الترجمة"
            )

            anti_ban.report_success()

            # البحث عن ملف الترجمة المحمل
            subtitle_file = self._find_subtitle_file(language_code, sub_format)

            if subtitle_file and os.path.exists(subtitle_file):
                # تنظيف وتنسيق الترجمة
                with open(subtitle_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                content = self.subtitle_converter.format_subtitle(content, subtitle_format)

                # حفظ الترجمة المنسقة
                final_path = os.path.join(
                    self.download_dir,
                    f"subtitle_{language_code}.{sub_format}"
                )
                with open(final_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                # حذف الملف المؤقت
                try:
                    os.remove(subtitle_file)
                except Exception:
                    pass

                return final_path

            return None

        except Exception as e:
            if self._cancelled:
                logger.info("Subtitle download cancelled by user")
                return None
            anti_ban.report_failure(status_code=_extract_429_status(e))
            logger.error(f"Subtitle download failed: {e}")
            self._update_progress(
                status=DownloadStatus.FAILED,
                message=f"فشل تحميل الترجمة: {str(e)}"
            )
            raise

    async def download_video(
        self,
        url: str,
        quality: str = "best",
        output_filename: Optional[str] = None,
    ) -> Optional[str]:
        """
        تحميل الفيديو
        """
        self._update_progress(
            status=DownloadStatus.DOWNLOADING_VIDEO,
            message="جاري تحميل الفيديو...",
            percent=0
        )

        if self._cancelled:
            return None

        # انتظار استراتيجية مضادة للحظر بين الترجمة والفيديو
        self._update_progress(
            status=DownloadStatus.WAITING_ANTI_BAN,
            message="جاري الانتظار لتجنب الحظر..."
        )
        await anti_ban.wait_between_subtitle_and_video()

        if self._cancelled:
            return None

        try:
            import yt_dlp

            if output_filename:
                outtmpl = os.path.join(self.download_dir, output_filename)
            else:
                outtmpl = os.path.join(self.download_dir, '%(title)s.%(ext)s')

            # تحديد الجودة
            if quality == "best":
                format_spec = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            elif quality == "medium":
                format_spec = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best'
            elif quality == "low":
                format_spec = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]/best'
            else:
                format_spec = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

            ydl_opts = {
                **anti_ban.get_ydl_opts_additions(),
                'format': format_spec,
                'outtmpl': outtmpl,
                'merge_output_format': 'mp4',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                'progress_hooks': [self._progress_hook],
            }

            loop = asyncio.get_event_loop()

            def _download_video():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.download([url])

            result = await loop.run_in_executor(None, _download_video)

            if self._cancelled:
                return None

            # البحث عن ملف الفيديو المحمل
            video_file = self._find_video_file()

            self._update_progress(
                status=DownloadStatus.COMPLETED,
                percent=100,
                message="تم تحميل الفيديو بنجاح!",
                filename=video_file or ""
            )

            anti_ban.report_success()
            return video_file

        except Exception as e:
            if self._cancelled:
                logger.info("Video download cancelled by user")
                return None
            anti_ban.report_failure(status_code=_extract_429_status(e))
            logger.error(f"Video download failed: {e}")
            self._update_progress(
                status=DownloadStatus.FAILED,
                message=f"فشل تحميل الفيديو: {str(e)}"
            )
            raise

    async def download_full(
        self,
        url: str,
        subtitle_lang: str = "ar",
        subtitle_format: str = "srt",
        quality: str = "best",
        auto_subtitle: bool = True,
    ) -> Dict[str, Optional[str]]:
        """
        التدفق الكامل: جلب معلومات → تحميل ترجمة → انتظار → تحميل فيديو
        """
        results = {
            "video": None,
            "subtitle": None,
            "info": None,
        }

        try:
            # الخطوة 1: جلب معلومات الفيديو
            if not anti_ban.check_session_limits():
                raise Exception("تم تجاوز حد الجلسة. يرجى الانتظار قبل المحاولة مرة أخرى.")

            info = await self.fetch_video_info(url)
            results["info"] = info

            if self._cancelled:
                return results

            # الخطوة 2: تحميل الترجمة أولاً
            subtitle_file = await self.download_subtitle(
                url=url,
                language_code=subtitle_lang,
                subtitle_format=subtitle_format,
                auto_generated=auto_subtitle,
            )
            results["subtitle"] = subtitle_file

            if self._cancelled:
                return results

            # الخطوة 3: تحميل الفيديو (مع الانتظار التلقائي)
            video_file = await self.download_video(
                url=url,
                quality=quality,
            )
            results["video"] = video_file

            return results

        except CancelledError:
            logger.info("Full download cancelled by user")
            return results
        except Exception as e:
            logger.error(f"Full download failed: {e}")
            raise

    def _progress_hook(self, d):
        """hook لتحديث تقدم التحميل"""
        if self._cancelled:
            raise CancelledError("تم إلغاء التحميل")

        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').strip().replace('%', '')
            try:
                percent = float(percent)
            except ValueError:
                percent = 0

            speed = d.get('_speed_str', '').strip()
            eta = d.get('_eta_str', '').strip()

            self._update_progress(
                status=DownloadStatus.DOWNLOADING_VIDEO,
                percent=percent,
                speed=speed,
                eta=eta,
                downloaded_bytes=d.get('downloaded_bytes', 0),
                total_bytes=d.get('total_bytes') or d.get('total_bytes_estimate', 0),
                message=f"جاري التحميل... {percent}%"
            )

        elif d['status'] == 'finished':
            self._update_progress(
                percent=100,
                message="جاري دمج الملفات...",
            )

    def _find_subtitle_file(self, lang_code: str, fmt: str) -> Optional[str]:
        """البحث عن ملف الترجمة المحمل"""
        # تطابق دقيق: video_id.lang_code.fmt أو video_id.lang_code.fmt.part
        import re
        precise_pattern = re.compile(rf'(^|[\W_]){re.escape(lang_code)}[\W_]')
        for filename in os.listdir(self.download_dir):
            if filename.endswith(f'.{fmt}') and precise_pattern.search(filename):
                return os.path.join(self.download_dir, filename)

        # محاولة البحث بأشكال مختلفة
        for filename in os.listdir(self.download_dir):
            if filename.endswith(f'.{fmt}'):
                return os.path.join(self.download_dir, filename)

        return None

    def _find_video_file(self) -> Optional[str]:
        """البحث عن ملف الفيديو المحمل"""
        video_extensions = ('.mp4', '.mkv', '.webm', '.avi')
        latest_file = None
        latest_time = 0

        for filename in os.listdir(self.download_dir):
            if filename.endswith(video_extensions):
                filepath = os.path.join(self.download_dir, filename)
                mtime = os.path.getmtime(filepath)
                if mtime > latest_time:
                    latest_time = mtime
                    latest_file = filepath

        return latest_file

    @staticmethod
    def _get_language_name(code: str) -> str:
        """تحويل كود اللغة إلى اسم"""
        languages = {
            'ar': 'العربية',
            'en': 'English',
            'fr': 'Français',
            'de': 'Deutsch',
            'es': 'Español',
            'it': 'Italiano',
            'ja': '日本語',
            'ko': '한국어',
            'pt': 'Português',
            'ru': 'Русский',
            'tr': 'Türkçe',
            'zh': '中文',
            'hi': 'हिन्दी',
            'id': 'Bahasa Indonesia',
            'th': 'ไทย',
            'vi': 'Tiếng Việt',
        }
        return languages.get(code, code)
