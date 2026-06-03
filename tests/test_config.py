"""
Tests for config.py — verify all constants are defined and have expected values.
"""

import os
import pytest

from youtube_downloader.config import (
    DEFAULT_DOWNLOAD_PATH,
    SUPPORTED_LANGS,
    SUBTITLE_FORMATS,
    SUBTITLE_PREFERRED_FORMAT,
    MAX_TITLE_LENGTH,
    MAX_RETRIES,
    RETRY_BACKOFF,
    VALID_URL_PATTERNS,
    QUEUE_POLL_MS,
    DIALOG_WAIT_TIMEOUT_S,
    SUBTITLE_SEARCH_MAX_AGE_S,
    DISK_SPACE_BUFFER_PERCENT,
    FFMPEG_DIR_NAME,
    FFMPEG_EXE,
    HOST,
    PORT,
    STATE_IDLE,
    STATE_RUNNING,
    STATE_FINISHED,
    MSG_PROGRESS,
    MSG_STATUS,
    MSG_LOG,
    MSG_MODE,
    MSG_DONE,
    MSG_ERROR,
    MSG_SUBTITLE_CHOICE,
    MSG_INFO,
)


class TestDefaultDownloadPath:
    """DEFAULT_DOWNLOAD_PATH should point to ~/Downloads/DownTube."""

    def test_is_string(self):
        assert isinstance(DEFAULT_DOWNLOAD_PATH, str)

    def test_contains_downloads(self):
        assert "Downloads" in DEFAULT_DOWNLOAD_PATH or "downloads" in DEFAULT_DOWNLOAD_PATH.lower()

    def test_contains_downtube(self):
        assert "DownTube" in DEFAULT_DOWNLOAD_PATH

    def test_is_absolute(self):
        assert os.path.isabs(DEFAULT_DOWNLOAD_PATH)


class TestSupportedLangs:
    """SUPPORTED_LANGS must include Arabic and English."""

    def test_is_dict(self):
        assert isinstance(SUPPORTED_LANGS, dict)

    def test_has_arabic(self):
        assert "ar" in SUPPORTED_LANGS

    def test_has_english(self):
        assert "en" in SUPPORTED_LANGS

    def test_arabic_display_name(self):
        assert "Arabic" in SUPPORTED_LANGS["ar"] or "عرب" in SUPPORTED_LANGS["ar"]

    def test_english_display_name(self):
        assert "English" in SUPPORTED_LANGS["en"]


class TestSubtitleFormats:
    """SUBTITLE_FORMATS should list supported subtitle file extensions."""

    def test_is_list(self):
        assert isinstance(SUBTITLE_FORMATS, list)

    def test_contains_srt(self):
        assert "srt" in SUBTITLE_FORMATS

    def test_contains_vtt(self):
        assert "vtt" in SUBTITLE_FORMATS

    def test_preferred_format_is_srt(self):
        assert SUBTITLE_PREFERRED_FORMAT == "srt"


class TestLimits:
    """Verify numerical limit constants."""

    def test_max_title_length(self):
        assert MAX_TITLE_LENGTH == 100

    def test_max_retries(self):
        assert MAX_RETRIES == 3

    def test_retry_backoff_values(self):
        assert RETRY_BACKOFF == [2, 5, 10]

    def test_retry_backoff_length(self):
        assert len(RETRY_BACKOFF) == MAX_RETRIES


class TestUrlPatterns:
    """VALID_URL_PATTERNS should match various YouTube URL formats."""

    def test_is_list(self):
        assert isinstance(VALID_URL_PATTERNS, list)

    def test_not_empty(self):
        assert len(VALID_URL_PATTERNS) > 0

    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/playlist?list=PLtest123",
    ])
    def test_valid_urls_match(self, url):
        import re
        matched = any(re.match(p, url) for p in VALID_URL_PATTERNS)
        assert matched, f"URL should match: {url}"

    @pytest.mark.parametrize("url", [
        "https://www.google.com",
        "not a url",
        "https://vimeo.com/12345",
        "",
    ])
    def test_invalid_urls_do_not_match(self, url):
        import re
        matched = any(re.match(p, url) for p in VALID_URL_PATTERNS)
        assert not matched, f"URL should NOT match: {url}"


class TestTimingConstants:
    """Verify timing-related constants."""

    def test_queue_poll_ms(self):
        assert QUEUE_POLL_MS == 100

    def test_dialog_wait_timeout(self):
        assert DIALOG_WAIT_TIMEOUT_S == 300

    def test_subtitle_search_max_age(self):
        assert SUBTITLE_SEARCH_MAX_AGE_S == 60


class TestDiskSpace:
    """Disk space buffer should be 20%."""

    def test_buffer_percent(self):
        assert DISK_SPACE_BUFFER_PERCENT == 20


class TestFFmpegConstants:
    """FFmpeg-related constants."""

    def test_ffmpeg_dir_name(self):
        assert FFMPEG_DIR_NAME == "ffmpeg"

    def test_ffmpeg_exe_is_string(self):
        assert isinstance(FFMPEG_EXE, str)
        assert len(FFMPEG_EXE) > 0


class TestServerConstants:
    """Server host and port."""

    def test_host(self):
        assert HOST == "127.0.0.1"

    def test_port(self):
        assert PORT == 8554


class TestStateMachine:
    """State machine constants."""

    def test_idle(self):
        assert STATE_IDLE == "IDLE"

    def test_running(self):
        assert STATE_RUNNING == "RUNNING"

    def test_finished(self):
        assert STATE_FINISHED == "FINISHED"

    def test_states_are_distinct(self):
        states = {STATE_IDLE, STATE_RUNNING, STATE_FINISHED}
        assert len(states) == 3


class TestMessageTypes:
    """WebSocket message type constants."""

    def test_all_are_strings(self):
        for msg_type in [MSG_PROGRESS, MSG_STATUS, MSG_LOG, MSG_MODE, MSG_DONE, MSG_ERROR, MSG_SUBTITLE_CHOICE, MSG_INFO]:
            assert isinstance(msg_type, str)

    def test_all_are_unique(self):
        types = [MSG_PROGRESS, MSG_STATUS, MSG_LOG, MSG_MODE, MSG_DONE, MSG_ERROR, MSG_SUBTITLE_CHOICE, MSG_INFO]
        assert len(set(types)) == len(types)
