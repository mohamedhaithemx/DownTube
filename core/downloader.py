"""DownTube YouTube downloader with Arabic subtitle forcing."""

import os
import json
import asyncio
import threading
import time
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

from .utils import (
    get_default_download_dir,
    sanitize_filename,
    format_size,
    format_speed,
    format_eta,
    is_valid_youtube_url,
    check_ffmpeg,
)


class DownloadProgress:
    """Track download progress state."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.status = "idle"  # idle, downloading, processing, complete, error
        self.progress_percent = 0.0
        self.speed = 0.0
        self.eta = 0.0
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.filename = ""
        self.video_title = ""
        self.subtitle_status = "pending"  # pending, downloading, found, not_found, embedded, failed
        self.subtitle_info = ""
        self.error = ""
        self.stage = ""  # Current stage description
        self.start_time = None
        self.video_path = ""
        self.subtitle_path = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "progress_percent": round(self.progress_percent, 1),
            "speed": format_speed(self.speed),
            "eta": format_eta(self.eta),
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "downloaded_str": format_size(self.downloaded_bytes),
            "total_str": format_size(self.total_bytes) if self.total_bytes else "--",
            "filename": self.filename,
            "video_title": self.video_title,
            "subtitle_status": self.subtitle_status,
            "subtitle_info": self.subtitle_info,
            "error": self.error,
            "stage": self.stage,
            "video_path": self.video_path,
            "subtitle_path": self.subtitle_path,
        }


class DownTubeDownloader:
    """YouTube downloader with forced Arabic subtitles."""

    # Arabic subtitle language codes to try
    ARABIC_LANG_CODES = ['ar', 'ar-ar', 'ara']

    def __init__(self, download_dir: Optional[str] = None):
        self.download_dir = download_dir or get_default_download_dir()
        self.progress = DownloadProgress()
        self._cancel_flag = False
        self._active_download = None
        self._progress_callbacks = []

        # Ensure download directory exists
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)

    def add_progress_callback(self, callback: Callable):
        """Add a callback to be called on progress updates."""
        self._progress_callbacks.append(callback)

    def _notify_progress(self):
        """Notify all progress callbacks."""
        data = self.progress.to_dict()
        for callback in self._progress_callbacks:
            try:
                callback(data)
            except Exception:
                pass

    def _progress_hook(self, d):
        """yt-dlp progress hook."""
        if self._cancel_flag:
            raise Exception("Download cancelled by user")

        if d['status'] == 'downloading':
            self.progress.status = "downloading"
            self.progress.speed = d.get('speed') or 0
            self.progress.eta = d.get('eta') or 0

            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)

            self.progress.total_bytes = total
            self.progress.downloaded_bytes = downloaded

            if total > 0:
                self.progress.progress_percent = (downloaded / total) * 100

            # Determine stage
            info = d.get('info', {})
            if info and info.get('vcodec') != 'none' and info.get('acodec') == 'none':
                self.progress.stage = "جاري تحميل الفيديو..."
            elif info and info.get('acodec') != 'none' and info.get('vcodec') == 'none':
                self.progress.stage = "جاري تحميل الصوت..."
            else:
                self.progress.stage = "جاري التحميل..."

            self._notify_progress()

        elif d['status'] == 'finished':
            self.progress.progress_percent = 100
            self.progress.stage = "جاري المعالجة..."
            self.progress.status = "processing"
            self._notify_progress()

        elif d['status'] == 'error':
            self.progress.status = "error"
            self.progress.error = "حدث خطأ أثناء التحميل"
            self._notify_progress()

    def _get_ydl_opts_with_subs(self, url: str) -> dict:
        """Build yt-dlp options with Arabic subtitle forcing."""
        outtmpl = os.path.join(self.download_dir, '%(title)s.%(ext)s')

        opts = {
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mkv',
            'outtmpl': outtmpl,
            # Arabic subtitle configuration
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': self.ARABIC_LANG_CODES,
            'subtitlesformat': 'srt/vtt/best',
            # Post-processors
            'postprocessors': [
                # Convert subtitles to SRT first
                {
                    'key': 'FFmpegSubtitlesConvertor',
                    'format': 'srt',
                },
                # Convert video to MKV
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mkv',
                },
                # Embed subtitles into video
                {
                    'key': 'FFmpegEmbedSubtitle',
                },
            ],
            'progress_hooks': [self._progress_hook],
            # Additional options
            'noplaylist': True,
            'nocheckcertificate': True,
            'prefer_free_formats': False,
            'verbose': False,
            # Retries
            'retries': 3,
            'fragment_retries': 3,
            # Don't fail on subtitle errors
            'ignoreerrors': False,
        }

        return opts

    def _get_ydl_opts_no_subs(self, url: str) -> dict:
        """Build yt-dlp options WITHOUT subtitles (fallback)."""
        outtmpl = os.path.join(self.download_dir, '%(title)s.%(ext)s')

        opts = {
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mkv',
            'outtmpl': outtmpl,
            # No subtitles
            'writesubtitles': False,
            'writeautomaticsub': False,
            # Post-processors
            'postprocessors': [
                # Convert video to MKV
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mkv',
                },
            ],
            'progress_hooks': [self._progress_hook],
            # Additional options
            'noplaylist': True,
            'nocheckcertificate': True,
            'prefer_free_formats': False,
            'verbose': False,
            # Retries
            'retries': 3,
            'fragment_retries': 3,
        }

        return opts

    def _check_arabic_subtitles(self, info: dict) -> dict:
        """Check what Arabic subtitles are available for a video."""
        result = {
            "has_manual_arabic": False,
            "has_auto_arabic": False,
            "available_langs": [],
            "arabic_subtitle_info": "",
        }

        subtitles = info.get('subtitles', {})
        automatic_captions = info.get('automatic_captions', {})

        result["available_langs"] = list(subtitles.keys())

        # Check for manual Arabic subtitles
        for lang_code in self.ARABIC_LANG_CODES:
            if lang_code in subtitles:
                result["has_manual_arabic"] = True
                result["arabic_subtitle_info"] = f"ترجمات عربية يدوية متوفرة ({lang_code})"
                break

        # Check for auto-generated Arabic subtitles
        if not result["has_manual_arabic"]:
            for lang_code in self.ARABIC_LANG_CODES:
                if lang_code in automatic_captions:
                    result["has_auto_arabic"] = True
                    result["arabic_subtitle_info"] = f"ترجمات عربية تلقائية متوفرة ({lang_code})"
                    break

        if not result["has_manual_arabic"] and not result["has_auto_arabic"]:
            result["arabic_subtitle_info"] = "لا توجد ترجمات عربية متوفرة"

        return result

    def download(self, url: str) -> dict:
        """Download a YouTube video with Arabic subtitles.

        Strategy:
        1. Try downloading with Arabic subtitles
        2. If subtitle download fails, retry without subtitles
        3. Always inform the user about subtitle status
        """
        self._cancel_flag = False
        self.progress.reset()
        self.progress.start_time = datetime.now()
        self.progress.status = "downloading"
        self.progress.stage = "جاري التحضير..."

        # Validate URL
        if not is_valid_youtube_url(url):
            self.progress.status = "error"
            self.progress.error = "رابط يوتيوب غير صالح"
            self._notify_progress()
            return self.progress.to_dict()

        # Check ffmpeg
        ffmpeg_info = check_ffmpeg()
        if not ffmpeg_info["available"]:
            self.progress.status = "error"
            self.progress.error = "ffmpeg غير مثبت! يرجى تثبيته أولاً"
            self._notify_progress()
            return self.progress.to_dict()

        try:
            import yt_dlp

            # First, extract info to check subtitles
            self.progress.stage = "جاري فحص الفيديو..."
            self._notify_progress()

            info_opts = {
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
            }

            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                video_title = info.get('title', 'Untitled')
                self.progress.video_title = video_title
                self.progress.filename = sanitize_filename(video_title)

                # Check Arabic subtitles availability
                sub_info = self._check_arabic_subtitles(info)
                self.progress.subtitle_status = "found" if (sub_info["has_manual_arabic"] or sub_info["has_auto_arabic"]) else "not_found"
                self.progress.subtitle_info = sub_info["arabic_subtitle_info"]
                self._notify_progress()

            # Try downloading with subtitles first
            self.progress.stage = "جاري تحميل الفيديو مع الترجمة العربية..."
            self.progress.subtitle_status = "downloading"
            self._notify_progress()

            try:
                ydl_opts = self._get_ydl_opts_with_subs(url)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                # Check if subtitle file was actually created
                self._find_downloaded_files()
                if self.progress.subtitle_path:
                    self.progress.subtitle_status = "embedded"
                    self.progress.subtitle_info = "تم تضمين الترجمة العربية في الفيديو ✅"
                elif self.progress.subtitle_status != "not_found":
                    # Subtitle was supposed to exist but wasn't downloaded
                    self.progress.subtitle_status = "failed"
                    self.progress.subtitle_info = "فشل تحميل الترجمة العربية - تم تحميل الفيديو بدون ترجمة"

            except Exception as sub_err:
                error_msg = str(sub_err).lower()

                # If the error is specifically about subtitles, try without them
                if 'subtitle' in error_msg or '429' in error_msg:
                    self.progress.stage = "جاري إعادة المحاولة بدون ترجمة..."
                    self.progress.subtitle_status = "failed"
                    self.progress.subtitle_info = "فشل تحميل الترجمة - جاري التحميل بدون ترجمة"
                    self._notify_progress()

                    # Reset progress for retry
                    self.progress.progress_percent = 0
                    self.progress.downloaded_bytes = 0
                    self.progress.total_bytes = 0

                    # Download without subtitles
                    ydl_opts = self._get_ydl_opts_no_subs(url)
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                else:
                    # Re-raise non-subtitle errors
                    raise

            # Find the downloaded files
            self._find_downloaded_files()

            self.progress.status = "complete"
            self.progress.progress_percent = 100
            self.progress.stage = "اكتمل التحميل!"
            self._notify_progress()

        except Exception as e:
            error_msg = str(e)
            if "cancel" in error_msg.lower():
                self.progress.status = "error"
                self.progress.error = "تم إلغاء التحميل"
            else:
                self.progress.status = "error"
                self.progress.error = f"خطأ: {error_msg[:200]}"
            self._notify_progress()

        return self.progress.to_dict()

    def _find_downloaded_files(self):
        """Find the downloaded video and subtitle files."""
        download_path = Path(self.download_dir)

        # Look for the most recently modified MKV file
        mkv_files = sorted(
            download_path.glob("*.mkv"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        if mkv_files:
            self.progress.video_path = str(mkv_files[0])

        # Look for subtitle files (prefer Arabic ones)
        srt_files = sorted(
            download_path.glob("*.ar.srt"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        if not srt_files:
            srt_files = sorted(
                download_path.glob("*.srt"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
        vtt_files = sorted(
            download_path.glob("*.ar.vtt"),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        if not vtt_files:
            vtt_files = sorted(
                download_path.glob("*.vtt"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
        sub_files = srt_files + vtt_files
        if sub_files:
            self.progress.subtitle_path = str(sub_files[0])

    def cancel(self):
        """Cancel the current download."""
        self._cancel_flag = True

    def get_video_info(self, url: str) -> dict:
        """Get video info without downloading."""
        try:
            import yt_dlp

            info_opts = {
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
            }

            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                sub_info = self._check_arabic_subtitles(info)

                # Get available formats summary
                formats = info.get('formats', [])
                best_video = max(
                    (f for f in formats if f.get('vcodec') != 'none'),
                    key=lambda f: f.get('height', 0) or 0,
                    default=None
                )

                return {
                    "title": info.get('title', ''),
                    "duration": info.get('duration', 0),
                    "thumbnail": info.get('thumbnail', ''),
                    "uploader": info.get('uploader', ''),
                    "view_count": info.get('view_count', 0),
                    "best_quality": f"{best_video.get('height', '?')}p" if best_video else "unknown",
                    "subtitles": sub_info,
                }

        except Exception as e:
            return {
                "error": str(e)[:200],
            }


# Global downloader instance
_downloader: Optional[DownTubeDownloader] = None


def get_downloader(download_dir: Optional[str] = None) -> DownTubeDownloader:
    """Get or create the global downloader instance."""
    global _downloader
    if _downloader is None or (download_dir and _downloader.download_dir != download_dir):
        _downloader = DownTubeDownloader(download_dir)
    return _downloader
