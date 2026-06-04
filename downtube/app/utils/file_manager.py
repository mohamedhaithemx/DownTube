import os
import shutil
import uuid
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TEMP_DIR = Path("/tmp/downtube")
FILE_TTL_MINUTES = 10


def ensure_temp_dir():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def generate_task_id() -> str:
    return str(uuid.uuid4())


def get_task_dir(task_id: str) -> Path:
    d = TEMP_DIR / task_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_files(task_id: str) -> list[Path]:
    d = get_task_dir(task_id)
    return [f for f in d.iterdir() if f.is_file()]


def find_video_file(task_id: str) -> str | None:
    exts = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
    for f in list_files(task_id):
        if f.suffix.lower() in exts:
            return str(f)
    return None


def find_subtitle_file(task_id: str) -> str | None:
    exts = {".srt", ".vtt"}
    for f in list_files(task_id):
        if f.suffix.lower() in exts:
            return str(f)
    return None


def find_audio_file(task_id: str) -> str | None:
    exts = {".mp3", ".m4a", ".aac", ".opus", ".wav", ".webm"}
    for f in list_files(task_id):
        if f.suffix.lower() in exts:
            return str(f)
    return None


def cleanup_task(task_id: str):
    d = TEMP_DIR / task_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
        logger.info("تنظيف الملفات المؤقتة للمهمة %s", task_id)


async def cleanup_task_after_delay(task_id: str, delay_minutes: int = FILE_TTL_MINUTES):
    await asyncio.sleep(delay_minutes * 60)
    cleanup_task(task_id)


def safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in " ._-").strip() or "video"


def human_size(bytes_val: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"
