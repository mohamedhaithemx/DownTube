"""DownTube YouTube downloader with Arabic subtitle forcing.

This module handles downloading YouTube videos with forced Arabic subtitles.
It uses yt-dlp for downloading and ffmpeg for merging/embedding.

Strategy:
1. Extract video info first to check available subtitles
2. Download with Arabic subtitles (manual first, then auto-generated)
3. Embed subtitles into MKV container
4. Also save separate .srt file for external use
5. If no Arabic subtitles available, download video anyway and inform user
"""

import os
import re
import json
import glob
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional, Callable, List, Dict
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
        self.subtitle_type = ""  # manual, auto, none
        self.error = ""
        self.stage = ""  # Current stage description
        self.start_time = None
        self.video_path = ""
        self.subtitle_path = ""
        self.duration = 0

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
            "subtitle_type": self.subtitle_type,
            "error": self.error,
            "stage": self.stage,
            "video_path": self.video_path,
            "subtitle_path": self.subtitle_path,
            "duration": self.duration,
        }


class DownTubeDownloader:
    """YouTube downloader with forced Arabic subtitles."""

    # Arabic subtitle language codes to try (in order of preference)
    ARABIC_LANG_CODES = ['ar', 'ar-ar', 'ara', 'ar-SA', 'ar-EG']

    def __init__(self, download_dir: Optional[str] = None):
        self.download_dir = download_dir or get_default_download_dir()
        self.progress = DownloadProgress()
        self._cancel_flag = False
        self._active_process = None
        self._progress_callbacks: List[Callable] = []

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
            raise KeyboardInterrupt("Download cancelled by user")

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

            # Determine stage based on what's being downloaded
            info = d.get('info', {})
            vcodec = info.get('vcodec', 'none')
            acodec = info.get('acodec', 'none')
            
            if vcodec != 'none' and acodec == 'none':
                self.progress.stage = "تحميل الفيديو..."
            elif acodec != 'none' and vcodec == 'none':
                self.progress.stage = "تحميل الصوت..."
            else:
                self.progress.stage = "جاري التحميل..."

            self._notify_progress()

        elif d['status'] == 'finished':
            self.progress.progress_percent = 100
            self.progress.stage = "جاري المعالجة ودمج الملفات..."
            self.progress.status = "processing"
            self._notify_progress()

        elif d['status'] == 'error':
            self.progress.status = "error"
            self.progress.error = "حدث خطأ أثناء التحميل"
            self._notify_progress()

    def _get_ydl_opts(self, url: str, with_subs: bool = True, cookie_path: str = None) -> dict:
        """Build yt-dlp options.
        
        Args:
            url: YouTube video URL
            with_subs: Whether to attempt downloading Arabic subtitles
            cookie_path: Optional path to cookies file for authentication
        """
        outtmpl = os.path.join(self.download_dir, '%(title)s.%(ext)s')

        postprocessors = [
            # Convert video to MKV (best container for embedded subtitles)
            {
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mkv',
            },
        ]

        if with_subs:
            postprocessors = [
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
            ]

        opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
            'merge_output_format': 'mkv',
            'outtmpl': outtmpl,
            # Arabic subtitle configuration
            'writesubtitles': with_subs,
            'writeautomaticsub': with_subs,
            'subtitleslangs': self.ARABIC_LANG_CODES if with_subs else [],
            'subtitlesformat': 'srt/vtt/best',
            # Post-processors
            'postprocessors': postprocessors,
            'progress_hooks': [self._progress_hook],
            # Additional options
            'noplaylist': True,
            'nocheckcertificate': True,
            'prefer_free_formats': False,
            'verbose': False,
            # Retries for robustness
            'retries': 5,
            'fragment_retries': 5,
            'file_access_retries': 3,
            # Socket timeouts
            'socket_timeout': 30,
            # Don't fail on subtitle errors - this is KEY so video download
            # continues even if subtitle download fails (e.g. 429 rate limit)
            'ignoreerrors': False,
            # Extractor args - try multiple clients for better compatibility
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }

        # Add cookie support if available
        if cookie_path and os.path.exists(cookie_path):
            opts['cookiefile'] = cookie_path

        return opts

    def _check_arabic_subtitles(self, info: dict) -> dict:
        """Check what Arabic subtitles are available for a video.
        
        Returns detailed info about available Arabic subtitles including
        whether they are manual or auto-generated.
        """
        result = {
            "has_manual_arabic": False,
            "has_auto_arabic": False,
            "manual_langs": [],
            "auto_langs": [],
            "available_langs": [],
            "arabic_subtitle_info": "",
            "arabic_subtitle_type": "",  # manual, auto, none
        }

        subtitles = info.get('subtitles', {})
        automatic_captions = info.get('automatic_captions', {})

        result["available_langs"] = list(subtitles.keys())

        # Check for manual Arabic subtitles
        for lang_code in self.ARABIC_LANG_CODES:
            if lang_code in subtitles:
                result["has_manual_arabic"] = True
                result["manual_langs"].append(lang_code)

        # Also check for any language starting with 'ar'
        for lang in subtitles.keys():
            if lang.startswith('ar') and lang not in result["manual_langs"]:
                result["has_manual_arabic"] = True
                result["manual_langs"].append(lang)

        # Check for auto-generated Arabic subtitles
        for lang_code in self.ARABIC_LANG_CODES:
            if lang_code in automatic_captions:
                result["has_auto_arabic"] = True
                result["auto_langs"].append(lang_code)

        for lang in automatic_captions.keys():
            if lang.startswith('ar') and lang not in result["auto_langs"]:
                result["has_auto_arabic"] = True
                result["auto_langs"].append(lang)

        # Build subtitle info message
        if result["has_manual_arabic"]:
            result["arabic_subtitle_info"] = f"ترجمة عربية يدوية متوفرة ({', '.join(result['manual_langs'])})"
            result["arabic_subtitle_type"] = "manual"
        elif result["has_auto_arabic"]:
            result["arabic_subtitle_info"] = f"ترجمة عربية تلقائية متوفرة ({', '.join(result['auto_langs'])})"
            result["arabic_subtitle_type"] = "auto"
        else:
            result["arabic_subtitle_info"] = "لا توجد ترجمات عربية - سيتم تحميل الفيديو بدون ترجمة"
            result["arabic_subtitle_type"] = "none"

        return result

    def _find_cookie_file(self) -> Optional[str]:
        """Find a YouTube cookies file for authentication.
        
        Checks common locations for exported cookies files.
        This helps bypass YouTube's bot detection on some networks.
        """
        # Check for cookies file in common locations
        home = Path.home()
        possible_paths = [
            # App directory
            Path(__file__).parent.parent / 'cookies.txt',
            Path(__file__).parent.parent / 'youtube-cookies.txt',
            # Home directory
            home / 'cookies.txt',
            home / 'youtube-cookies.txt',
            # Standard location
            home / '.config' / 'yt-dlp' / 'cookies.txt',
        ]

        for path in possible_paths:
            if path.exists() and path.stat().st_size > 0:
                return str(path)

        return None

    def _find_downloaded_files(self):
        """Find the downloaded video and subtitle files."""
        download_path = Path(self.download_dir)

        # Look for the most recently modified video file
        video_files = sorted(
            list(download_path.glob("*.mkv")) + list(download_path.glob("*.mp4")) + list(download_path.glob("*.webm")),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        
        if video_files:
            self.progress.video_path = str(video_files[0])

        # Look for Arabic subtitle files specifically
        sub_patterns = ['*.ar.srt', '*.ar-ar.srt', '*.ara.srt', '*.ar-SA.srt', '*.ar-EG.srt']
        srt_files = []
        for pattern in sub_patterns:
            srt_files.extend(sorted(
                download_path.glob(pattern),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            ))
        
        if not srt_files:
            srt_files = sorted(
                download_path.glob("*.srt"),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
        
        vtt_files = sorted(
            list(download_path.glob("*.ar.vtt")) + list(download_path.glob("*.vtt")),
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        
        all_sub_files = srt_files + vtt_files
        if all_sub_files:
            self.progress.subtitle_path = str(all_sub_files[0])

    def download(self, url: str, cookie_path: str = None) -> dict:
        """Download a YouTube video with Arabic subtitles.

        Strategy:
        1. Extract video info to check subtitle availability
        2. Download with Arabic subtitles (manual + auto-generated)
        3. Embed subtitles in MKV container
        4. Save separate .srt file
        5. If subtitle download fails, retry without subtitles
        6. Always inform the user about subtitle status
        
        Args:
            url: YouTube video URL
            cookie_path: Optional path to Netscape cookies file for auth
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
            self.progress.error = "ffmpeg غير مثبت! يرجى تثبيته أولاً\nUbuntu: sudo apt install ffmpeg\nmacOS: brew install ffmpeg\nWindows: شغّل setup.bat"
            self._notify_progress()
            return self.progress.to_dict()

        try:
            import yt_dlp

            # Find cookie file if not specified
            if not cookie_path:
                cookie_path = self._find_cookie_file()

            # Step 1: Extract video info to check subtitles
            self.progress.stage = "جاري فحص الفيديو والترجمات..."
            self._notify_progress()

            info_opts = {
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            }
            if cookie_path and os.path.exists(cookie_path):
                info_opts['cookiefile'] = cookie_path

            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                video_title = info.get('title', 'بدون عنوان')
                self.progress.video_title = video_title
                self.progress.filename = sanitize_filename(video_title)
                self.progress.duration = info.get('duration', 0)

                # Check Arabic subtitles availability
                sub_info = self._check_arabic_subtitles(info)
                has_arabic = sub_info["has_manual_arabic"] or sub_info["has_auto_arabic"]
                self.progress.subtitle_status = "found" if has_arabic else "not_found"
                self.progress.subtitle_info = sub_info["arabic_subtitle_info"]
                self.progress.subtitle_type = sub_info["arabic_subtitle_type"]
                self._notify_progress()

            # Step 2: Download with subtitles
            if has_arabic:
                self.progress.stage = "تحميل الفيديو مع الترجمة العربية..."
                self.progress.subtitle_status = "downloading"
                self._notify_progress()
            else:
                self.progress.stage = "تحميل الفيديو (بدون ترجمة عربية متوفرة)..."
                self._notify_progress()

            try:
                ydl_opts = self._get_ydl_opts(url, with_subs=has_arabic, cookie_path=cookie_path)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                # Check if subtitle was downloaded
                self._find_downloaded_files()
                if self.progress.subtitle_path and has_arabic:
                    self.progress.subtitle_status = "embedded"
                    sub_type = "يدوية" if sub_info["arabic_subtitle_type"] == "manual" else "تلقائية"
                    self.progress.subtitle_info = f"تم تضمين الترجمة العربية {sub_type} في الفيديو بنجاح"

            except Exception as sub_err:
                error_msg = str(sub_err).lower()

                # If subtitle-related error or rate limit, retry without subtitles
                if any(kw in error_msg for kw in ['subtitle', 'caption', '429', 'too many']):
                    self.progress.stage = "إعادة المحاولة بدون ترجمة..."
                    self.progress.subtitle_status = "failed"
                    self.progress.subtitle_info = "فشل تحميل الترجمة - جاري التحميل بدون ترجمة"
                    self._notify_progress()

                    # Reset progress for retry
                    self.progress.progress_percent = 0
                    self.progress.downloaded_bytes = 0
                    self.progress.total_bytes = 0

                    ydl_opts = self._get_ydl_opts(url, with_subs=False, cookie_path=cookie_path)
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                elif 'cancel' in error_msg or 'interrupt' in error_msg:
                    raise KeyboardInterrupt("تم إلغاء التحميل")
                else:
                    # For other errors, try without subtitles as a fallback
                    self.progress.stage = "جاري إعادة المحاولة بدون ترجمة..."
                    self.progress.subtitle_status = "failed"
                    self.progress.subtitle_info = "فشل - جاري التحميل بدون ترجمة"
                    self._notify_progress()

                    self.progress.progress_percent = 0
                    self.progress.downloaded_bytes = 0
                    self.progress.total_bytes = 0

                    try:
                        ydl_opts = self._get_ydl_opts(url, with_subs=False, cookie_path=cookie_path)
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([url])
                    except Exception:
                        raise

            # Find downloaded files
            self._find_downloaded_files()

            # Step 3: Try to extract subtitle from MKV as separate SRT file
            if self.progress.video_path and self.progress.subtitle_status == "embedded":
                self._extract_subtitle_from_mkv()

            self.progress.status = "complete"
            self.progress.progress_percent = 100
            self.progress.stage = "اكتمل التحميل بنجاح!"
            self._notify_progress()

        except KeyboardInterrupt:
            self.progress.status = "error"
            self.progress.error = "تم إلغاء التحميل"
            self._notify_progress()
        except Exception as e:
            error_msg = str(e)
            if "cancel" in error_msg.lower() or "interrupt" in error_msg.lower():
                self.progress.status = "error"
                self.progress.error = "تم إلغاء التحميل"
            elif "Sign in" in error_msg or "bot" in error_msg.lower():
                self.progress.status = "error"
                self.progress.error = "يوتيوب حظر الطلب - حاول مرة أخرى لاحقاً أو حدّث yt-dlp"
            elif "Video unavailable" in error_msg:
                self.progress.status = "error"
                self.progress.error = "الفيديو غير متوفر أو محذوف"
            else:
                self.progress.status = "error"
                self.progress.error = f"خطأ: {error_msg[:300]}"
            self._notify_progress()

        return self.progress.to_dict()

    def _extract_subtitle_from_mkv(self):
        """Extract embedded Arabic subtitle from MKV as a separate SRT file.
        
        This provides users with a standalone subtitle file they can use
        with any video player or for other purposes.
        """
        try:
            video_path = self.progress.video_path
            if not video_path or not os.path.exists(video_path):
                return

            # Use ffmpeg to extract subtitle
            base_name = os.path.splitext(video_path)[0]
            srt_path = f"{base_name}.ar.srt"

            # Check if SRT already exists from yt-dlp
            if os.path.exists(srt_path):
                self.progress.subtitle_path = srt_path
                return

            # Try to extract from MKV using ffmpeg
            cmd = [
                'ffmpeg', '-i', video_path,
                '-map', '0:s:0',  # First subtitle stream
                '-f', 'srt',
                srt_path,
                '-y',  # Overwrite
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0 and os.path.exists(srt_path):
                self.progress.subtitle_path = srt_path
            else:
                # Try with mkvextract if available
                mkvextract = shutil.which('mkvextract')
                if mkvextract:
                    cmd2 = [
                        'mkvextract', 'tracks', video_path,
                        f'0:{srt_path}'
                    ]
                    subprocess.run(cmd2, capture_output=True, timeout=30)
                    if os.path.exists(srt_path):
                        self.progress.subtitle_path = srt_path

        except Exception:
            # Non-critical - subtitle might already be embedded
            pass

    def cancel(self):
        """Cancel the current download."""
        self._cancel_flag = True

    def get_video_info(self, url: str) -> dict:
        """Get video info without downloading.
        
        Returns video metadata including title, duration, thumbnail,
        and detailed Arabic subtitle availability information.
        """
        try:
            import yt_dlp

            info_opts = {
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'extractor_args': {'youtube': {'player_client': ['web']}},
            }

            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                sub_info = self._check_arabic_subtitles(info)

                # Get available formats summary
                formats = info.get('formats', [])
                video_formats = [f for f in formats if f.get('vcodec') != 'none']
                best_video = max(
                    video_formats,
                    key=lambda f: f.get('height', 0) or 0,
                    default=None
                )

                duration = info.get('duration', 0)
                hours, remainder = divmod(int(duration), 3600)
                minutes, seconds = divmod(remainder, 60)
                if hours > 0:
                    duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    duration_str = f"{minutes}:{seconds:02d}"

                return {
                    "title": info.get('title', ''),
                    "duration": duration,
                    "duration_str": duration_str,
                    "thumbnail": info.get('thumbnail', ''),
                    "uploader": info.get('uploader', ''),
                    "view_count": info.get('view_count', 0),
                    "best_quality": f"{best_video.get('height', '?')}p" if best_video else "unknown",
                    "subtitles": sub_info,
                }

        except Exception as e:
            return {
                "error": str(e)[:300],
            }


# Global downloader instance
_downloader: Optional[DownTubeDownloader] = None


def get_downloader(download_dir: Optional[str] = None) -> DownTubeDownloader:
    """Get or create the global downloader instance."""
    global _downloader
    if _downloader is None or (download_dir and _downloader.download_dir != download_dir):
        _downloader = DownTubeDownloader(download_dir)
    return _downloader
