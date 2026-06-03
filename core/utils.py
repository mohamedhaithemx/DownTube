"""Utility functions for DownTube."""

import os
import re
import shutil
import subprocess
import platform
from pathlib import Path


def get_default_download_dir() -> str:
    """Get the default download directory for DownTube."""
    home = Path.home()
    download_dir = home / "Downloads" / "DownTube"
    download_dir.mkdir(parents=True, exist_ok=True)
    return str(download_dir)


def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from a filename."""
    # Remove characters that are invalid in filenames
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Trim whitespace and dots
    sanitized = sanitized.strip().strip('.')
    # Limit length
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized or "untitled"


def check_ffmpeg() -> dict:
    """Check if ffmpeg is available and return info."""
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            version_line = result.stdout.split('\n')[0] if result.stdout else "unknown"
            return {
                "available": True,
                "path": ffmpeg_path,
                "version": version_line
            }
        except Exception:
            return {
                "available": True,
                "path": ffmpeg_path,
                "version": "unknown"
            }
    return {
        "available": False,
        "path": None,
        "version": None
    }


def check_ytdlp() -> dict:
    """Check if yt-dlp is available and return info."""
    ytdlp_path = shutil.which('yt-dlp')
    if not ytdlp_path:
        # Check if it's installed as a Python package
        try:
            import yt_dlp
            return {
                "available": True,
                "path": yt_dlp.__file__,
                "version": yt_dlp.version.__version__,
                "method": "python"
            }
        except ImportError:
            return {
                "available": False,
                "path": None,
                "version": None,
                "method": None
            }
    
    try:
        result = subprocess.run(
            ['yt-dlp', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return {
            "available": True,
            "path": ytdlp_path,
            "version": result.stdout.strip(),
            "method": "cli"
        }
    except Exception:
        return {
            "available": True,
            "path": ytdlp_path,
            "version": "unknown",
            "method": "cli"
        }


def format_size(size_bytes: int) -> str:
    """Format bytes into human readable size."""
    if size_bytes == 0:
        return "0 B"
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.1f} {units[i]}"


def format_speed(speed: float) -> str:
    """Format download speed in human readable format."""
    if speed is None or speed <= 0:
        return "--"
    return f"{format_size(int(speed))}/s"


def format_eta(seconds: float) -> str:
    """Format ETA in human readable format."""
    if seconds is None or seconds <= 0:
        return "--"
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def is_valid_youtube_url(url: str) -> bool:
    """Check if a URL is a valid YouTube URL."""
    patterns = [
        r'^https?://(www\.)?youtube\.com/watch\?v=',
        r'^https?://(www\.)?youtube\.com/shorts/',
        r'^https?://youtu\.be/',
        r'^https?://(www\.)?youtube\.com/embed/',
        r'^https?://m\.youtube\.com/watch\?v=',
    ]
    return any(re.match(pattern, url) for pattern in patterns)


def get_system_info() -> dict:
    """Get system information."""
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "ffmpeg": check_ffmpeg(),
        "ytdlp": check_ytdlp(),
    }
