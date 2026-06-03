"""
ffmpeg_utils.py — FFmpeg detection and path resolution.

Search order:
  1. Bundled directory (next to frozen executable or project root)
  2. System PATH
  3. Project directory

Returns None when FFmpeg is available via system PATH (yt-dlp can find it automatically).
Returns a directory string when FFmpeg is found in a specific location.
Raises FFmpegNotFoundError when FFmpeg cannot be found anywhere.
"""

import os
import shutil
import subprocess
import sys

from .exceptions import FFmpegNotFoundError
from .config import FFMPEG_DIR_NAME, FFMPEG_EXE


def get_ffmpeg_path() -> str | None:
    """
    Locate the FFmpeg binary.

    Returns
    -------
    str or None
        - None  → FFmpeg is in the system PATH (yt-dlp will find it).
        - str   → Directory containing FFmpeg (must be passed to yt-dlp via
                   ffmpeg_location option).

    Raises
    ------
    FFmpegNotFoundError
        When FFmpeg cannot be found anywhere.
    """
    # 1. Bundled with frozen executable (PyInstaller)
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        bundled = os.path.join(base, FFMPEG_DIR_NAME, FFMPEG_EXE)
        if os.path.isfile(bundled):
            return os.path.dirname(bundled)

    # 2. Check project-level ffmpeg directory (development mode)
    project_ffmpeg = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", FFMPEG_DIR_NAME, FFMPEG_EXE
    )
    project_ffmpeg = os.path.normpath(project_ffmpeg)
    if os.path.isfile(project_ffmpeg):
        return os.path.dirname(project_ffmpeg)

    # 3. System PATH
    if shutil.which(FFMPEG_EXE):
        # yt-dlp can find it via PATH automatically
        return None

    # 4. Check project root directory directly
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root_ffmpeg = os.path.join(root_dir, FFMPEG_EXE)
    if os.path.isfile(root_ffmpeg):
        return root_dir

    raise FFmpegNotFoundError()


def get_ffmpeg_version() -> str | None:
    """
    Return the FFmpeg version string, or None if FFmpeg is not available.
    """
    try:
        result = subprocess.run(
            [FFMPEG_EXE, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            first_line = result.stdout.split("\n")[0]
            return first_line.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None
