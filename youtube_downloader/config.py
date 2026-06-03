"""
config.py — All constants for DownTube.
No runtime logic here; every value is a simple constant.
"""

import os
import platform

# ── Download paths ──────────────────────────────────────────────
DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "Downloads", "DownTube")

# ── Supported subtitle languages ────────────────────────────────
# Keys are what yt-dlp uses; values are display names.
SUPPORTED_LANGS = {
    "ar": "العربية (Arabic)",
    "en": "English",
}

# ── Subtitle formats ────────────────────────────────────────────
SUBTITLE_FORMATS = ["srt", "vtt"]
SUBTITLE_PREFERRED_FORMAT = "srt"

# ── Limits ──────────────────────────────────────────────────────
MAX_TITLE_LENGTH = 100
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 5, 10]  # seconds

# ── URL validation ─────────────────────────────────────────────
VALID_URL_PATTERNS = [
    r"https?://(www\.)?youtube\.com/watch\?v=[\w-]{11}",
    r"https?://(www\.)?youtube\.com/shorts/[\w-]{11}",
    r"https?://youtu\.be/[\w-]{11}",
    r"https?://(www\.)?youtube\.com/playlist\?list=[\w-]+",
]

# ── Queue / timing ─────────────────────────────────────────────
QUEUE_POLL_MS = 100
DIALOG_WAIT_TIMEOUT_S = 300
SUBTITLE_SEARCH_MAX_AGE_S = 60

# ── Disk space ─────────────────────────────────────────────────
DISK_SPACE_BUFFER_PERCENT = 20  # 20 % extra buffer

# ── FFmpeg ─────────────────────────────────────────────────────
FFMPEG_DIR_NAME = "ffmpeg"
FFMPEG_EXE = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"

# ── Server ─────────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 8554

# ── State machine ──────────────────────────────────────────────
STATE_IDLE = "IDLE"
STATE_RUNNING = "RUNNING"
STATE_FINISHED = "FINISHED"

# ── WebSocket message types ────────────────────────────────────
MSG_PROGRESS = "progress"
MSG_STATUS = "status"
MSG_LOG = "log"
MSG_MODE = "mode"
MSG_DONE = "done"
MSG_ERROR = "error"
MSG_SUBTITLE_CHOICE = "subtitle_choice"
MSG_INFO = "info"
