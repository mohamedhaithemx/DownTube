"""
downloader.py — yt-dlp download logic for DownTube.

Responsibilities:
  - Extract video info (title, formats, subtitles)
  - Find available subtitles for a given language
  - Estimate file size before download
  - Execute download with progress reporting
  - Handle cancellation via threading.Event

Thread safety:
  - DownloadManager methods are called from background threads.
  - Progress updates are sent via a callback (queue-based in FastAPI mode).
  - cancel_event is checked inside the progress hook.
"""

import os
import re
import time
import logging
from typing import Callable, Any

import yt_dlp

from .config import (
    MAX_TITLE_LENGTH,
    MAX_RETRIES,
    RETRY_BACKOFF,
    SUPPORTED_LANGS,
    SUBTITLE_PREFERRED_FORMAT,
    VALID_URL_PATTERNS,
)
from .exceptions import (
    DownloadCancelledError,
    PlaylistURLError,
)
from .ffmpeg_utils import get_ffmpeg_path

logger = logging.getLogger(__name__)


def find_lang_key(available: dict, requested: str) -> str | None:
    """
    Find a matching subtitle language key using prefix matching.

    For example, if requested='ar', it will match 'ar', 'ar-SA', 'ar-EG', etc.

    Parameters
    ----------
    available : dict
        Dictionary of available subtitles from yt-dlp (key → subtitle info).
    requested : str
        Requested language code (e.g. 'ar', 'en').

    Returns
    -------
    str or None
        The matched key from available, or None if no match.
    """
    if not available:
        return None

    # Exact match first
    if requested in available:
        return requested

    # Prefix match (e.g., 'ar' matches 'ar-SA', 'ar-EG')
    for key in available:
        if key.startswith(requested):
            return key

    return None


class DownloadManager:
    """
    Manages YouTube video downloads using yt-dlp.

    This class is designed to be used from a background thread.
    Progress updates are communicated via a callback function.
    Cancellation is handled via a threading.Event.
    """

    def __init__(
        self,
        cancel_event: "threading.Event | None" = None,
        progress_callback: "Callable[[dict], None] | None" = None,
    ):
        """
        Parameters
        ----------
        cancel_event : threading.Event, optional
            Set this event to cancel the download.
        progress_callback : callable, optional
            Called with a dict message for each progress update.
        """
        self.cancel_event = cancel_event
        self.progress_callback = progress_callback

    def _send(self, message: dict) -> None:
        """Send a message via the progress callback if available."""
        if self.progress_callback:
            self.progress_callback(message)

    def _check_cancelled(self) -> None:
        """Raise DownloadCancelledError if the cancel event is set."""
        if self.cancel_event and self.cancel_event.is_set():
            raise DownloadCancelledError()

    def extract_info(self, url: str) -> dict:
        """
        Extract video information without downloading.

        Parameters
        ----------
        url : str
            YouTube video URL.

        Returns
        -------
        dict
            Video info dictionary from yt-dlp.

        Raises
        ------
        PlaylistURLError
            If the URL is a playlist.
        yt_dlp.utils.DownloadError
            If the video cannot be accessed.
        """
        # Check for playlist URL
        if "playlist?list=" in url:
            raise PlaylistURLError()

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info

    def get_available_subtitles(
        self, info: dict, lang: str
    ) -> tuple[str, str] | None:
        """
        Check if subtitles are available for the given language.

        Parameters
        ----------
        info : dict
            Video info from extract_info().
        lang : str
            Language code (e.g. 'ar', 'en').

        Returns
        -------
        tuple or None
            (subtitle_type, matched_key) where subtitle_type is 'official' or 'auto',
            or None if no subtitles found.
        """
        # Check manually uploaded subtitles first
        subtitles = info.get("subtitles", {})
        key = find_lang_key(subtitles, lang)
        if key:
            return ("official", key)

        # Check auto-generated subtitles
        auto_captions = info.get("automatic_captions", {})
        key = find_lang_key(auto_captions, lang)
        if key:
            return ("auto", key)

        return None

    def estimate_filesize(self, info: dict) -> int | None:
        """
        Estimate the file size of the video in bytes.

        Uses three strategies in order:
        1. filesize from info dict
        2. filesize_approx from info dict
        3. Calculate from format tbr * duration

        Parameters
        ----------
        info : dict
            Video info from extract_info().

        Returns
        -------
        int or None
            Estimated size in bytes, or None if cannot estimate.
        """
        # Strategy 1: Direct filesize
        filesize = info.get("filesize")
        if filesize:
            return filesize

        # Strategy 2: Approximate filesize
        filesize_approx = info.get("filesize_approx")
        if filesize_approx:
            return int(filesize_approx)

        # Strategy 3: Calculate from best format's tbr * duration
        duration = info.get("duration")
        if duration:
            formats = info.get("formats", [])
            best_tbr = 0
            for fmt in formats:
                tbr = fmt.get("tbr")
                if tbr and tbr > best_tbr:
                    best_tbr = tbr
            if best_tbr:
                # tbr is in kbps, duration in seconds → bytes
                return int(best_tbr * 1000 / 8 * duration)

        return None

    def _make_progress_hook(self) -> Callable:
        """
        Create a yt-dlp progress hook that:
        - Sends progress updates via callback
        - Checks for cancellation
        """

        def progress_hook(d: dict) -> None:
            self._check_cancelled()

            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0
                eta = d.get("eta") or 0

                percent = 0
                if total > 0:
                    percent = downloaded / total * 100

                self._send({
                    "type": "progress",
                    "percent": round(percent, 1),
                    "downloaded": downloaded,
                    "total": total,
                    "speed": speed,
                    "eta": eta,
                })

            elif d["status"] == "finished":
                self._send({
                    "type": "status",
                    "message": "جاري دمج الملفات...",
                })

        return progress_hook

    def download(
        self,
        url: str,
        output_dir: str,
        lang: str = "ar",
        subtitle_choice: str = "yes",
    ) -> dict:
        """
        Download a YouTube video.

        Parameters
        ----------
        url : str
            YouTube video URL.
        output_dir : str
            Directory to save the downloaded files.
        lang : str
            Subtitle language code (default: 'ar').
        subtitle_choice : str
            'yes' to download with subtitles, 'no' for video only.

        Returns
        -------
        dict
            Result with keys: 'filepath', 'title', 'subtitle_file' (or None),
            'subtitle_type' (or None).

        Raises
        ------
        DownloadCancelledError
            If cancelled during download.
        """
        self._check_cancelled()

        # Get FFmpeg path
        ffmpeg_location = get_ffmpeg_path()

        # Extract info first
        self._send({"type": "status", "message": "جاري استخراج معلومات الفيديو..."})
        info = self.extract_info(url)
        title = info.get("title", "unknown")[:MAX_TITLE_LENGTH]

        self._send({"type": "status", "message": f"جاري تحميل: {title}"})

        # Check for subtitles
        subtitle_info = None
        write_subtitles = False
        subtitle_lang_key = None

        if subtitle_choice == "yes":
            subtitle_info = self.get_available_subtitles(info, lang)
            if subtitle_info:
                write_subtitles = True
                subtitle_lang_key = subtitle_info[1]
                sub_type = "رسمية" if subtitle_info[0] == "official" else "تلقائية"
                self._send({
                    "type": "log",
                    "message": f"سيتم تحميل الترجمة ({sub_type}): {subtitle_lang_key}",
                })
            else:
                self._send({
                    "type": "log",
                    "message": "لم يتم العثور على ترجمة باللغة المطلوبة. سيتم تحميل الفيديو بدون ترجمة.",
                })

        # Build yt-dlp options
        output_template = os.path.join(output_dir, "%(title).100s.%(ext)s")

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "outtmpl": output_template,
            "progress_hooks": [self._make_progress_hook()],
            "quiet": False,
            "no_warnings": True,
            "noplaylist": True,
        }

        # FFmpeg location
        if ffmpeg_location is not None:
            ydl_opts["ffmpeg_location"] = ffmpeg_location

        # Subtitle options
        if write_subtitles and subtitle_lang_key:
            ydl_opts["writesubtitles"] = True
            ydl_opts["subtitleslangs"] = [subtitle_lang_key]
            ydl_opts["subtitlesformat"] = SUBTITLE_PREFERRED_FORMAT

        # Execute download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            self._check_cancelled()
            ydl.download([url])

        # Find the downloaded video file
        video_file = self._find_downloaded_file(output_dir, title, ".mp4")

        # Find subtitle file if requested
        subtitle_file = None
        subtitle_type = None
        if write_subtitles and subtitle_info:
            from .subtitle_manager import find_subtitle_file, rename_subtitle_file
            sub_path = find_subtitle_file(output_dir, title)
            if sub_path:
                subtitle_file = rename_subtitle_file(
                    sub_path, title, subtitle_lang_key
                )
                subtitle_type = subtitle_info[0]

        self._send({
            "type": "done",
            "filepath": video_file,
            "title": title,
            "subtitle_file": subtitle_file,
            "subtitle_type": subtitle_type,
        })

        return {
            "filepath": video_file,
            "title": title,
            "subtitle_file": subtitle_file,
            "subtitle_type": subtitle_type,
        }

    def _find_downloaded_file(
        self, directory: str, title: str, extension: str
    ) -> str | None:
        """
        Find the most recently downloaded file matching the title and extension.

        Uses modification time to find the correct file (not title string matching),
        as per the specification.
        """
        import glob

        pattern = os.path.join(directory, f"*{extension}")
        files = glob.glob(pattern)

        if not files:
            return None

        # Sort by modification time, most recent first
        files.sort(key=os.path.getmtime, reverse=True)

        # Return the most recently modified file
        for f in files:
            mtime = os.path.getmtime(f)
            age = time.time() - mtime
            # Only consider files modified within the last 60 seconds
            if age < 60:
                return f

        # Fallback: return the most recent file anyway
        return files[0]
