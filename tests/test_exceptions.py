"""
Tests for exceptions.py — verify custom exceptions and their default messages.
"""

import pytest

from youtube_downloader.exceptions import (
    DownloadCancelledError,
    FFmpegNotFoundError,
    DiskSpaceError,
    PlaylistURLError,
    SubtitleNotFoundError,
)


class TestDownloadCancelledError:
    """DownloadCancelledError tests."""

    def test_default_message(self):
        exc = DownloadCancelledError()
        assert exc.message == "تم إلغاء التحميل"
        assert str(exc) == "تم إلغاء التحميل"

    def test_custom_message(self):
        exc = DownloadCancelledError("Custom cancel message")
        assert exc.message == "Custom cancel message"
        assert str(exc) == "Custom cancel message"

    def test_is_exception(self):
        assert issubclass(DownloadCancelledError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(DownloadCancelledError):
            raise DownloadCancelledError()

    def test_can_be_caught_as_exception(self):
        with pytest.raises(Exception):
            raise DownloadCancelledError()


class TestFFmpegNotFoundError:
    """FFmpegNotFoundError tests."""

    def test_default_message(self):
        exc = FFmpegNotFoundError()
        assert "FFmpeg" in exc.message or "ffmpeg" in exc.message.lower()

    def test_custom_message(self):
        exc = FFmpegNotFoundError("FFmpeg missing!")
        assert exc.message == "FFmpeg missing!"

    def test_is_exception(self):
        assert issubclass(FFmpegNotFoundError, Exception)


class TestDiskSpaceError:
    """DiskSpaceError tests."""

    def test_default_message(self):
        exc = DiskSpaceError()
        assert "مساحة" in exc.message or "تخزين" in exc.message

    def test_custom_message(self):
        exc = DiskSpaceError("No space left")
        assert exc.message == "No space left"

    def test_is_exception(self):
        assert issubclass(DiskSpaceError, Exception)


class TestPlaylistURLError:
    """PlaylistURLError tests."""

    def test_default_message(self):
        exc = PlaylistURLError()
        assert "قائمة" in exc.message or "playlist" in exc.message.lower()

    def test_custom_message(self):
        exc = PlaylistURLError("No playlists allowed")
        assert exc.message == "No playlists allowed"

    def test_is_exception(self):
        assert issubclass(PlaylistURLError, Exception)


class TestSubtitleNotFoundError:
    """SubtitleNotFoundError tests."""

    def test_default_message(self):
        exc = SubtitleNotFoundError()
        assert "ترجم" in exc.message or "subtitle" in exc.message.lower()

    def test_custom_message(self):
        exc = SubtitleNotFoundError("No sub found")
        assert exc.message == "No sub found"

    def test_is_exception(self):
        assert issubclass(SubtitleNotFoundError, Exception)


class TestExceptionsAreDistinct:
    """All custom exceptions should be distinct types."""

    def test_all_different_types(self):
        types = {
            DownloadCancelledError,
            FFmpegNotFoundError,
            DiskSpaceError,
            PlaylistURLError,
            SubtitleNotFoundError,
        }
        assert len(types) == 5

    def test_catching_specific_type_does_not_catch_others(self):
        with pytest.raises(FFmpegNotFoundError):
            try:
                raise FFmpegNotFoundError()
            except DownloadCancelledError:
                pytest.fail("Should not catch DownloadCancelledError")
            except DiskSpaceError:
                pytest.fail("Should not catch DiskSpaceError")
