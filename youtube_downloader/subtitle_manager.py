"""
subtitle_manager.py — Subtitle file detection and renaming for DownTube.

Key design decisions:
  - Subtitle detection uses file modification time (mtime) NOT title string matching.
  - Language matching uses prefix matching for variants (ar, ar-SA, ar-EG, etc.).
  - Subtitles are saved as SEPARATE files (.srt/.vtt), NOT embedded in the video.
"""

import os
import time
import glob
import re
import logging

from .config import SUBTITLE_FORMATS, SUBTITLE_SEARCH_MAX_AGE_S

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """
    Remove characters that are illegal in file names.

    Parameters
    ----------
    name : str
        Raw title or name string.

    Returns
    -------
    str
        Sanitized string safe for use as a file name.
    """
    # Remove characters illegal on Windows / macOS / Linux
    sanitized = re.sub(r'[<>:"/\\|?*]', "", name)
    # Collapse multiple spaces
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    # Remove leading/trailing dots
    sanitized = sanitized.strip(".")
    return sanitized


def find_subtitle_file(directory: str, video_title: str) -> str | None:
    """
    Find the subtitle file that was just downloaded alongside the video.

    Strategy: Use file modification time (mtime) to find the most recently
    created subtitle file in the download directory. We do NOT rely on
    title string matching because yt-dlp may produce slightly different
    file names than the video title.

    Parameters
    ----------
    directory : str
        The download directory.
    video_title : str
        The video title (used as a hint, not for exact matching).

    Returns
    -------
    str or None
        Path to the subtitle file, or None if not found.
    """
    now = time.time()
    candidates = []

    for fmt in SUBTITLE_FORMATS:
        pattern = os.path.join(directory, f"*.{fmt}")
        for filepath in glob.glob(pattern):
            try:
                mtime = os.path.getmtime(filepath)
                age = now - mtime
                if age < SUBTITLE_SEARCH_MAX_AGE_S:
                    candidates.append((filepath, mtime))
            except OSError:
                continue

    if not candidates:
        return None

    # Return the most recently modified subtitle file
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def rename_subtitle_file(
    subtitle_path: str, video_title: str, lang_code: str
) -> str:
    """
    Rename a subtitle file to follow the naming convention:
        {title}_SUBTITLE_{lang}.{format}

    Parameters
    ----------
    subtitle_path : str
        Current path of the subtitle file.
    video_title : str
        Title of the video (will be sanitized).
    lang_code : str
        Language code (e.g. 'ar', 'en', 'ar-EG').

    Returns
    -------
    str
        New path of the renamed subtitle file.
    """
    directory = os.path.dirname(subtitle_path)
    original_name = os.path.basename(subtitle_path)
    ext = os.path.splitext(original_name)[1]  # e.g. '.srt', '.vtt'

    safe_title = sanitize_filename(video_title)
    new_name = f"{safe_title}_SUBTITLE_{lang_code}{ext}"
    new_path = os.path.join(directory, new_name)

    # Avoid overwriting existing files
    if os.path.exists(new_path) and new_path != subtitle_path:
        counter = 1
        while os.path.exists(
            os.path.join(directory, f"{safe_title}_SUBTITLE_{lang_code}_{counter}{ext}")
        ):
            counter += 1
        new_name = f"{safe_title}_SUBTITLE_{lang_code}_{counter}{ext}"
        new_path = os.path.join(directory, new_name)

    if new_path != subtitle_path:
        try:
            os.rename(subtitle_path, new_path)
            logger.info("Renamed subtitle: %s → %s", subtitle_path, new_path)
        except OSError as e:
            logger.error("Failed to rename subtitle: %s", e)
            return subtitle_path  # Return original path on failure

    return new_path
