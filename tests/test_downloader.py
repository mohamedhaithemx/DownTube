"""
Tests for downloader.py — DownloadManager, find_lang_key, and download logic.

These tests mock yt-dlp to avoid actual YouTube API calls.
"""

import os
import time
import tempfile
import threading
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from youtube_downloader.downloader import DownloadManager, find_lang_key
from youtube_downloader.exceptions import DownloadCancelledError, PlaylistURLError


class TestFindLangKey:
    """Tests for the find_lang_key() helper function."""

    def test_exact_match(self):
        """Should return the exact key when it exists."""
        available = {"ar": {}, "en": {}, "fr": {}}
        assert find_lang_key(available, "ar") == "ar"

    def test_prefix_match_ar_sa(self):
        """Should match 'ar' to 'ar-SA' via prefix matching."""
        available = {"ar-SA": {}, "en": {}}
        assert find_lang_key(available, "ar") == "ar-SA"

    def test_prefix_match_ar_eg(self):
        """Should match 'ar' to 'ar-EG' via prefix matching."""
        available = {"ar-EG": {}, "en": {}}
        assert find_lang_key(available, "ar") == "ar-EG"

    def test_no_match(self):
        """Should return None when no matching language is found."""
        available = {"en": {}, "fr": {}, "de": {}}
        assert find_lang_key(available, "ar") is None

    def test_empty_available(self):
        """Should return None when available dict is empty."""
        assert find_lang_key({}, "ar") is None

    def test_none_available(self):
        """Should return None when available is None."""
        assert find_lang_key(None, "ar") is None

    def test_exact_match_preferred_over_prefix(self):
        """When both exact and prefix matches exist, exact should win."""
        available = {"ar": {}, "ar-SA": {}, "ar-EG": {}}
        assert find_lang_key(available, "ar") == "ar"

    def test_en_prefix_match(self):
        """Should match 'en' to 'en-GB' via prefix matching."""
        available = {"en-GB": {}, "fr": {}}
        assert find_lang_key(available, "en") == "en-GB"


class TestDownloadManagerInit:
    """Tests for DownloadManager initialization."""

    def test_default_init(self):
        """Should initialize with no cancel_event or callback."""
        dm = DownloadManager()
        assert dm.cancel_event is None
        assert dm.progress_callback is None

    def test_with_cancel_event(self):
        """Should accept a cancel_event."""
        event = threading.Event()
        dm = DownloadManager(cancel_event=event)
        assert dm.cancel_event is event

    def test_with_progress_callback(self):
        """Should accept a progress_callback."""
        callback = MagicMock()
        dm = DownloadManager(progress_callback=callback)
        assert dm.progress_callback is callback


class TestExtractInfo:
    """Tests for DownloadManager.extract_info()."""

    @patch("youtube_downloader.downloader.yt_dlp.YoutubeDL")
    def test_extracts_info_successfully(self, mock_ydl_class):
        """Should return video info dict from yt-dlp."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {"title": "Test Video", "duration": 120}
        mock_ydl_class.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_class.return_value.__exit__ = MagicMock(return_value=False)

        dm = DownloadManager()
        info = dm.extract_info("https://www.youtube.com/watch?v=test123")
        assert info["title"] == "Test Video"

    def test_raises_on_playlist_url(self):
        """Should raise PlaylistURLError for playlist URLs."""
        dm = DownloadManager()
        with pytest.raises(PlaylistURLError):
            dm.extract_info("https://www.youtube.com/playlist?list=PLtest123")


class TestGetAvailableSubtitles:
    """Tests for DownloadManager.get_available_subtitles()."""

    def test_official_subtitle_found(self):
        """Should return ('official', key) when official subtitles exist."""
        info = {
            "subtitles": {"ar": [{"url": "http://example.com/sub"}]},
            "automatic_captions": {},
        }
        dm = DownloadManager()
        result = dm.get_available_subtitles(info, "ar")
        assert result == ("official", "ar")

    def test_auto_subtitle_found(self):
        """Should return ('auto', key) when only auto-generated subtitles exist."""
        info = {
            "subtitles": {},
            "automatic_captions": {"ar-SA": [{"url": "http://example.com/sub"}]},
        }
        dm = DownloadManager()
        result = dm.get_available_subtitles(info, "ar")
        assert result == ("auto", "ar-SA")

    def test_no_subtitle_found(self):
        """Should return None when no subtitles are available."""
        info = {"subtitles": {}, "automatic_captions": {}}
        dm = DownloadManager()
        result = dm.get_available_subtitles(info, "ar")
        assert result is None

    def test_official_preferred_over_auto(self):
        """Official subtitles should be preferred over auto-generated."""
        info = {
            "subtitles": {"ar": [{"url": "http://example.com/sub"}]},
            "automatic_captions": {"ar": [{"url": "http://example.com/auto"}]},
        }
        dm = DownloadManager()
        result = dm.get_available_subtitles(info, "ar")
        assert result[0] == "official"


class TestEstimateFilesize:
    """Tests for DownloadManager.estimate_filesize()."""

    def test_direct_filesize(self):
        """Should use direct filesize when available."""
        info = {"filesize": 10_000_000}
        dm = DownloadManager()
        assert dm.estimate_filesize(info) == 10_000_000

    def test_approx_filesize(self):
        """Should use filesize_approx when direct filesize is not available."""
        info = {"filesize_approx": 8_500_000}
        dm = DownloadManager()
        assert dm.estimate_filesize(info) == 8_500_000

    def test_tbr_calculation(self):
        """Should calculate from tbr * duration when no direct size is available."""
        info = {
            "duration": 120,
            "formats": [
                {"tbr": 1000},  # 1000 kbps
            ],
        }
        dm = DownloadManager()
        result = dm.estimate_filesize(info)
        # 1000 kbps * 1000 / 8 * 120 seconds = 15,000,000 bytes
        assert result == 15_000_000

    def test_returns_none_when_no_info(self):
        """Should return None when no size information is available."""
        info = {}
        dm = DownloadManager()
        assert dm.estimate_filesize(info) is None

    def test_filesize_preferred_over_approx(self):
        """Direct filesize should be preferred over approx."""
        info = {"filesize": 10_000_000, "filesize_approx": 8_000_000}
        dm = DownloadManager()
        assert dm.estimate_filesize(info) == 10_000_000


class TestCheckCancelled:
    """Tests for cancellation checking via cancel_event."""

    def test_raises_when_cancelled(self):
        """Should raise DownloadCancelledError when cancel_event is set."""
        event = threading.Event()
        event.set()
        dm = DownloadManager(cancel_event=event)
        with pytest.raises(DownloadCancelledError):
            dm._check_cancelled()

    def test_does_not_raise_when_not_cancelled(self):
        """Should not raise when cancel_event is not set."""
        event = threading.Event()
        dm = DownloadManager(cancel_event=event)
        dm._check_cancelled()  # Should not raise

    def test_does_not_raise_when_no_event(self):
        """Should not raise when cancel_event is None."""
        dm = DownloadManager()
        dm._check_cancelled()  # Should not raise


class TestProgressHook:
    """Tests for the yt-dlp progress hook."""

    def test_sends_progress_on_downloading(self):
        """Should send progress message during download."""
        messages = []
        dm = DownloadManager(progress_callback=lambda m: messages.append(m))
        hook = dm._make_progress_hook()

        hook({
            "status": "downloading",
            "total_bytes": 1000,
            "downloaded_bytes": 500,
            "speed": 100,
            "eta": 5,
        })

        assert len(messages) == 1
        assert messages[0]["type"] == "progress"
        assert messages[0]["percent"] == 50.0

    def test_sends_status_on_finished(self):
        """Should send status message when download finishes."""
        messages = []
        dm = DownloadManager(progress_callback=lambda m: messages.append(m))
        hook = dm._make_progress_hook()

        hook({"status": "finished"})

        assert len(messages) == 1
        assert messages[0]["type"] == "status"

    def test_checks_cancel_in_hook(self):
        """Should raise DownloadCancelledError in hook when cancelled."""
        event = threading.Event()
        event.set()
        dm = DownloadManager(cancel_event=event)
        hook = dm._make_progress_hook()

        with pytest.raises(DownloadCancelledError):
            hook({"status": "downloading", "downloaded_bytes": 0})


class TestSendMethod:
    """Tests for _send() method."""

    def test_sends_via_callback(self):
        """Should send message via progress_callback."""
        messages = []
        dm = DownloadManager(progress_callback=lambda m: messages.append(m))
        dm._send({"type": "test", "data": 123})
        assert len(messages) == 1
        assert messages[0]["data"] == 123

    def test_no_error_without_callback(self):
        """Should not raise when progress_callback is None."""
        dm = DownloadManager()
        dm._send({"type": "test"})  # Should not raise
