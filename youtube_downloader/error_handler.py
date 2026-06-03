"""
error_handler.py — Exception-to-message mapping and retry logic for DownTube.

Responsibilities:
  - Map any exception to a user-friendly Arabic message
  - Retry network operations with exponential backoff
  - Check available disk space before downloads
"""

import os
import shutil
import logging
import time
from typing import Callable, TypeVar

from .exceptions import (
    DownloadCancelledError,
    FFmpegNotFoundError,
    DiskSpaceError,
    PlaylistURLError,
    SubtitleNotFoundError,
)
from .config import MAX_RETRIES, RETRY_BACKOFF, DISK_SPACE_BUFFER_PERCENT

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ── Network-related exception types for retry logic ────────────
_NETWORK_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def map_exception_to_message(exc: Exception) -> str:
    """
    Convert any exception into a user-friendly Arabic message.

    Parameters
    ----------
    exc : Exception
        The exception to map.

    Returns
    -------
    str
        Human-readable Arabic error message.
    """
    if isinstance(exc, DownloadCancelledError):
        return exc.message

    if isinstance(exc, FFmpegNotFoundError):
        return exc.message

    if isinstance(exc, DiskSpaceError):
        return exc.message

    if isinstance(exc, PlaylistURLError):
        return exc.message

    if isinstance(exc, SubtitleNotFoundError):
        return exc.message

    # yt-dlp specific errors
    exc_name = type(exc).__name__
    exc_module = type(exc).__module__ or ""

    if "yt_dlp" in exc_module:
        msg = str(exc).lower()
        if "private" in msg:
            return "هذا الفيديو خاص ولا يمكن تحميله"
        if "unavailable" in msg or "removed" in msg:
            return "هذا الفيديو غير متاح أو تم حذفه"
        if "captcha" in msg:
            return "يطلب يوتيوب تحقق بشري (كابتشا). حاول لاحقاً"
        if "age" in msg and "restrict" in msg:
            return "هذا الفيديو مقيد بالعمر ولا يمكن تحميله"
        if "429" in msg or "too many" in msg:
            return "تم حظر الطلبات مؤقتاً. حاول مرة أخرى بعد قليل"
        if "sign in" in msg or "login" in msg:
            return "هذا الفيديو يتطلب تسجيل الدخول"
        if "country" in msg or "region" in msg or "blocked" in msg:
            return "هذا الفيديو محظور في منطقتك"
        if "live" in msg:
            return "لا يمكن تحميل البث المباشر حالياً"
        # Generic yt-dlp error
        return f"خطأ في التحميل: {str(exc)[:200]}"

    # Network errors
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return "خطأ في الاتصال بالإنترنت. تأكد من اتصالك وحاول مرة أخرى"

    # File system errors
    if isinstance(exc, PermissionError):
        return "ليس لديك صلاحية الكتابة في مجلد التحميل"
    if isinstance(exc, FileNotFoundError):
        return "لم يتم العثور على الملف المطلوب"

    # Generic fallback
    return f"حدث خطأ غير متوقع: {type(exc).__name__}: {str(exc)[:150]}"


def retry_with_backoff(
    func: Callable[..., T],
    *args,
    max_retries: int = MAX_RETRIES,
    backoff: list[int] | None = None,
    **kwargs,
) -> T:
    """
    Retry a function on network-related errors with exponential backoff.

    Only retries on network-related exceptions (ConnectionError, TimeoutError, OSError).
    Other exceptions are re-raised immediately.

    Parameters
    ----------
    func : callable
        The function to call.
    *args :
        Positional arguments for func.
    max_retries : int
        Maximum number of retry attempts.
    backoff : list[int], optional
        Delay in seconds before each retry. Defaults to RETRY_BACKOFF.
    **kwargs :
        Keyword arguments for func.

    Returns
    -------
    Whatever func returns.

    Raises
    ------
    Exception
        Re-raises the last exception if all retries fail.
    """
    if backoff is None:
        backoff = RETRY_BACKOFF

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except _NETWORK_EXCEPTIONS as e:
            last_exception = e
            if attempt < max_retries:
                delay = backoff[min(attempt, len(backoff) - 1)]
                logger.warning(
                    "Network error on attempt %d/%d: %s. Retrying in %ds...",
                    attempt + 1,
                    max_retries + 1,
                    str(e),
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "All %d attempts failed for %s", max_retries + 1, func.__name__
                )
        except DownloadCancelledError:
            raise  # Never retry a user cancellation
        except Exception:
            raise  # Re-raise non-network exceptions immediately

    raise last_exception  # type: ignore[misc]


def check_disk_space(directory: str, required_bytes: int) -> None:
    """
    Verify that enough disk space is available.

    Applies a buffer percentage on top of the required size to account
    for temporary files and merging overhead.

    Parameters
    ----------
    directory : str
        Target directory for the download.
    required_bytes : int
        Estimated download size in bytes.

    Raises
    ------
    DiskSpaceError
        If available space is less than required_bytes * (1 + buffer%).
    """
    try:
        usage = shutil.disk_usage(directory)
        buffer_multiplier = 1 + DISK_SPACE_BUFFER_PERCENT / 100
        required_with_buffer = int(required_bytes * buffer_multiplier)

        if usage.free < required_with_buffer:
            free_gb = usage.free / (1024**3)
            required_gb = required_with_buffer / (1024**3)
            raise DiskSpaceError(
                f"مساحة التخزين غير كافية. المتاح: {free_gb:.1f} جيجا، المطلوب: {required_gb:.1f} جيجا"
            )
    except DiskSpaceError:
        raise
    except Exception as e:
        logger.warning("Could not check disk space: %s", e)
        # Don't block the download if we can't check disk space
