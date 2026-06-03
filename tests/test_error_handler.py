"""
Tests for error_handler.py — Exception mapping, retry logic, and disk space checks.
"""

import os
import shutil
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from youtube_downloader.error_handler import (
    map_exception_to_message,
    retry_with_backoff,
    check_disk_space,
)
from youtube_downloader.exceptions import (
    DownloadCancelledError,
    FFmpegNotFoundError,
    DiskSpaceError,
    PlaylistURLError,
    SubtitleNotFoundError,
)


# ── Helper: create yt-dlp-style exceptions for testing ─────────

class _YTDLPDownloadError(Exception):
    """Simulates yt_dlp.utils.DownloadError for testing."""
    pass

# Set the module so that "yt_dlp" appears in it
_YTDLPDownloadError.__module__ = "yt_dlp.utils"


class TestMapExceptionToMessage:
    """Tests for map_exception_to_message()."""

    def test_download_cancelled(self):
        """Should return cancellation message."""
        exc = DownloadCancelledError()
        msg = map_exception_to_message(exc)
        assert "إلغاء" in msg or "التحميل" in msg

    def test_ffmpeg_not_found(self):
        """Should return FFmpeg error message."""
        exc = FFmpegNotFoundError()
        msg = map_exception_to_message(exc)
        assert "FFmpeg" in msg or "ffmpeg" in msg.lower()

    def test_disk_space_error(self):
        """Should return disk space message."""
        exc = DiskSpaceError()
        msg = map_exception_to_message(exc)
        assert "مساحة" in msg or "تخزين" in msg

    def test_playlist_url_error(self):
        """Should return playlist error message."""
        exc = PlaylistURLError()
        msg = map_exception_to_message(exc)
        assert "قائمة" in msg or "playlist" in msg.lower()

    def test_subtitle_not_found_error(self):
        """Should return subtitle not found message."""
        exc = SubtitleNotFoundError()
        msg = map_exception_to_message(exc)
        assert "ترجم" in msg or "subtitle" in msg.lower()

    def test_connection_error(self):
        """Should return network error message."""
        exc = ConnectionError("Network unreachable")
        msg = map_exception_to_message(exc)
        assert "اتصال" in msg or "إنترنت" in msg

    def test_timeout_error(self):
        """Should return timeout error message."""
        exc = TimeoutError("Connection timed out")
        msg = map_exception_to_message(exc)
        assert "اتصال" in msg or "إنترنت" in msg

    def test_permission_error(self):
        """Should return permission error message."""
        exc = PermissionError("Access denied")
        msg = map_exception_to_message(exc)
        assert "صلاحية" in msg or "كتابة" in msg

    def test_file_not_found_error(self):
        """Should return file not found message."""
        exc = FileNotFoundError("No such file")
        msg = map_exception_to_message(exc)
        assert "ملف" in msg or "عثور" in msg

    def test_custom_exception_message(self):
        """Should use custom message from exception."""
        exc = FFmpegNotFoundError("Custom FFmpeg message")
        msg = map_exception_to_message(exc)
        assert "Custom FFmpeg message" in msg

    def test_generic_exception(self):
        """Should handle unknown exceptions gracefully."""
        exc = RuntimeError("Something went wrong")
        msg = map_exception_to_message(exc)
        assert len(msg) > 0  # Should produce some message

    def test_ytdlp_private_video(self):
        """Should detect private video error from yt-dlp."""
        exc = _YTDLPDownloadError("Private video. Sign in if you've been granted access")
        msg = map_exception_to_message(exc)
        assert "خاص" in msg

    def test_ytdlp_unavailable_video(self):
        """Should detect unavailable video error."""
        exc = _YTDLPDownloadError("Video unavailable")
        msg = map_exception_to_message(exc)
        assert "غير متاح" in msg or "حذف" in msg

    def test_ytdlp_age_restricted(self):
        """Should detect age-restricted video error."""
        exc = _YTDLPDownloadError("Sign in to confirm your age. This video may be age-restricted")
        msg = map_exception_to_message(exc)
        assert "عمر" in msg or "مقيد" in msg

    def test_ytdlp_region_blocked(self):
        """Should detect region-blocked video error."""
        exc = _YTDLPDownloadError("This video is not available in your country")
        msg = map_exception_to_message(exc)
        assert "منطقة" in msg or "محظور" in msg or "country" in msg.lower()

    def test_ytdlp_rate_limited(self):
        """Should detect rate limiting (429) error."""
        exc = _YTDLPDownloadError("HTTP Error 429: Too Many Requests")
        msg = map_exception_to_message(exc)
        assert "حظر" in msg or "429" in msg

    def test_ytdlp_captcha(self):
        """Should detect captcha requirement."""
        exc = _YTDLPDownloadError("Sign in to verify you're not a bot (captcha)")
        msg = map_exception_to_message(exc)
        assert "كابتشا" in msg or "تحقق" in msg or "bot" in msg.lower()

    def test_ytdlp_generic_error(self):
        """Should handle generic yt-dlp errors."""
        exc = _YTDLPDownloadError("Some unknown yt-dlp error")
        msg = map_exception_to_message(exc)
        assert "خطأ في التحميل" in msg or "تحميل" in msg

    def test_ytdlp_live_video(self):
        """Should detect live video error."""
        exc = _YTDLPDownloadError("This is a live stream")
        msg = map_exception_to_message(exc)
        assert "بث" in msg or "مباشر" in msg


class TestRetryWithBackoff:
    """Tests for retry_with_backoff()."""

    def test_succeeds_on_first_try(self):
        """Should return result immediately if function succeeds."""
        result = retry_with_backoff(lambda: 42)
        assert result == 42

    def test_retries_on_network_error(self):
        """Should retry on ConnectionError."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success"

        result = retry_with_backoff(flaky_func, max_retries=3, backoff=[0.01, 0.01, 0.01])
        assert result == "success"
        assert call_count == 3

    def test_retries_on_timeout(self):
        """Should retry on TimeoutError."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Timed out")
            return "ok"

        result = retry_with_backoff(flaky_func, max_retries=3, backoff=[0.01, 0.01, 0.01])
        assert result == "ok"

    def test_raises_after_max_retries(self):
        """Should raise the last exception after all retries are exhausted."""
        def always_fails():
            raise ConnectionError("Permanent failure")

        with pytest.raises(ConnectionError):
            retry_with_backoff(always_fails, max_retries=2, backoff=[0.01, 0.01])

    def test_does_not_retry_cancellation(self):
        """Should NOT retry DownloadCancelledError."""
        call_count = 0

        def cancelled_func():
            nonlocal call_count
            call_count += 1
            raise DownloadCancelledError()

        with pytest.raises(DownloadCancelledError):
            retry_with_backoff(cancelled_func, max_retries=3, backoff=[0.01, 0.01, 0.01])

        # Should only be called once
        assert call_count == 1

    def test_does_not_retry_non_network_error(self):
        """Should NOT retry non-network exceptions."""
        call_count = 0

        def value_error_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Bad value")

        with pytest.raises(ValueError):
            retry_with_backoff(value_error_func, max_retries=3, backoff=[0.01, 0.01, 0.01])

        assert call_count == 1

    def test_passes_args_and_kwargs(self):
        """Should pass *args and **kwargs to the function."""
        def add(a, b, c=0):
            return a + b + c

        result = retry_with_backoff(add, 1, 2, c=3)
        assert result == 6

    def test_default_backoff_values(self):
        """Should use default RETRY_BACKOFF values."""
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError()
            return "done"

        # With default backoff [2, 5, 10], but we'll mock time.sleep
        with patch("time.sleep"):
            result = retry_with_backoff(flaky)
            assert result == "done"

    def test_retries_on_oserror(self):
        """Should retry on OSError (network-related)."""
        call_count = 0

        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("Network is unreachable")
            return "recovered"

        result = retry_with_backoff(flaky_func, max_retries=3, backoff=[0.01, 0.01, 0.01])
        assert result == "recovered"
        assert call_count == 2


class TestCheckDiskSpace:
    """Tests for check_disk_space()."""

    def test_does_not_raise_when_enough_space(self):
        """Should not raise when there is plenty of disk space."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Requesting 1 byte should always succeed
            check_disk_space(tmpdir, 1)

    def test_raises_when_insufficient_space(self):
        """Should raise DiskSpaceError when space is insufficient."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Requesting an absurdly large amount should fail
            huge_size = 10**18  # 1 exabyte
            with pytest.raises(DiskSpaceError):
                check_disk_space(tmpdir, huge_size)

    def test_includes_buffer(self):
        """Should apply 20% buffer on top of required size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            usage = shutil.disk_usage(tmpdir)
            # Request a size that is greater than 80% of available space
            # required_with_buffer = required * 1.2
            # For it to fail: required * 1.2 > usage.free
            # So: required > usage.free / 1.2
            required = int(usage.free / 1.1) + 1  # Use 1.1 instead of 1.2 to ensure failure
            with pytest.raises(DiskSpaceError):
                check_disk_space(tmpdir, required)

    def test_handles_nonexistent_directory(self):
        """Should not crash on nonexistent directory (just log warning)."""
        # This should not raise DiskSpaceError, just log a warning
        # because the function catches general exceptions
        check_disk_space("/nonexistent/path/12345", 1000)

    def test_zero_required_bytes(self):
        """Should always succeed when required_bytes is 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            check_disk_space(tmpdir, 0)  # Should not raise

    def test_small_file_always_succeeds(self):
        """Should succeed for small file sizes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            check_disk_space(tmpdir, 1024)  # 1 KB should always fit

    def test_buffer_calculation(self):
        """Verify the 20% buffer is applied correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            usage = shutil.disk_usage(tmpdir)
            # If we request exactly usage.free, it should fail
            # because buffer adds 20% on top
            with pytest.raises(DiskSpaceError):
                check_disk_space(tmpdir, usage.free)
