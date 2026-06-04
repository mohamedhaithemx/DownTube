import os
import shutil
import uuid
import asyncio
import logging
import glob as glob_module
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


def cleanup_chunk_files(task_id: str):
    """
    حذف ملفات الأجزاء المؤقتة (chunk*, preprocessed*) لمهمة معينة.
    يُستخدم بعد انتهاء المعالجة لتحرير الذاكرة فوراً.
    """
    d = TEMP_DIR / task_id
    if not d.exists():
        return

    patterns = ["chunk*", "preprocessed*", "*.chunk*"]
    removed = 0
    for pattern in patterns:
        for f in d.glob(pattern):
            try:
                if f.is_file():
                    f.unlink()
                    removed += 1
            except Exception:
                pass

    if removed > 0:
        logger.info("تم حذف %d ملف مؤقت للمهمة %s", removed, task_id)


def cleanup_temp_audio(task_id: str):
    """
    حذف ملفات الصوت المؤقتة (mp3, m4a) بعد الانتهاء من النسخ.
    يحافظ على ملفات الفيديو والترجمة فقط.
    """
    d = TEMP_DIR / task_id
    if not d.exists():
        return

    audio_exts = {".mp3", ".m4a", ".aac", ".opus", ".wav"}
    removed = 0
    for f in d.iterdir():
        if f.is_file() and f.suffix.lower() in audio_exts:
            try:
                f.unlink()
                removed += 1
            except Exception:
                pass

    if removed > 0:
        logger.info("تم حذف %d ملف صوتي مؤقت للمهمة %s", removed, task_id)


def safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in " ._-").strip() or "video"


def human_size(bytes_val: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def get_temp_usage() -> dict:
    """إرجاع معلومات استخدام المساحة المؤقتة"""
    if not TEMP_DIR.exists():
        return {"total_size_mb": 0, "task_count": 0}

    total_size = 0
    task_count = 0
    for d in TEMP_DIR.iterdir():
        if d.is_dir():
            task_count += 1
            for f in d.rglob("*"):
                if f.is_file():
                    try:
                        total_size += f.stat().st_size
                    except Exception:
                        pass

    return {
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "task_count": task_count,
    }
