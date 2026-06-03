"""
Tests for subtitle_manager.py — Subtitle file detection and renaming.
"""

import os
import time
import tempfile
import pytest
from unittest.mock import patch

from youtube_downloader.subtitle_manager import (
    sanitize_filename,
    find_subtitle_file,
    rename_subtitle_file,
)


class TestSanitizeFilename:
    """Tests for sanitize_filename()."""

    def test_removes_illegal_chars(self):
        """Should remove < > : " / \\ | ? * characters."""
        assert sanitize_filename('test<>:"/\\|?*file') == "testfile"

    def test_collapses_spaces(self):
        """Should collapse multiple spaces into one."""
        assert sanitize_filename("test   file   name") == "test file name"

    def test_strips_dots(self):
        """Should strip leading/trailing dots."""
        assert sanitize_filename("..test..") == "test"

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        assert sanitize_filename("  test  ") == "test"

    def test_normal_filename(self):
        """Should leave normal filenames unchanged."""
        assert sanitize_filename("My Video Title") == "My Video Title"

    def test_empty_string(self):
        """Should handle empty string."""
        assert sanitize_filename("") == ""

    def test_only_illegal_chars(self):
        """Should handle string of only illegal characters."""
        assert sanitize_filename('<>:"/\\|?*') == ""

    def test_mixed_content(self):
        """Should handle mixed legal and illegal characters."""
        result = sanitize_filename('Video: "Best of 2024" | Part 1/2')
        assert ":" not in result
        assert '"' not in result
        assert "|" not in result
        assert "/" not in result
        assert "Video" in result


class TestFindSubtitleFile:
    """Tests for find_subtitle_file()."""

    def test_finds_recent_srt_file(self):
        """Should find a recently created .srt file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a recent subtitle file
            srt_path = os.path.join(tmpdir, "video_subtitle.srt")
            with open(srt_path, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\nTest subtitle\n")

            result = find_subtitle_file(tmpdir, "video")
            assert result is not None
            assert result.endswith(".srt")

    def test_finds_recent_vtt_file(self):
        """Should find a recently created .vtt file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vtt_path = os.path.join(tmpdir, "video_subtitle.vtt")
            with open(vtt_path, "w") as f:
                f.write("WEBVTT\n\n00:00:00.000 --> 00:00:05.000\nTest subtitle\n")

            result = find_subtitle_file(tmpdir, "video")
            assert result is not None
            assert result.endswith(".vtt")

    def test_returns_none_for_old_files(self):
        """Should return None when subtitle files are too old (> 60s)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            srt_path = os.path.join(tmpdir, "old_subtitle.srt")
            with open(srt_path, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\nOld\n")

            # Set modification time to 2 minutes ago
            old_time = time.time() - 120
            os.utime(srt_path, (old_time, old_time))

            result = find_subtitle_file(tmpdir, "video")
            assert result is None

    def test_returns_none_for_empty_directory(self):
        """Should return None when no subtitle files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = find_subtitle_file(tmpdir, "video")
            assert result is None

    def test_returns_most_recent_when_multiple(self):
        """Should return the most recently modified subtitle file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two subtitle files with different times
            srt1 = os.path.join(tmpdir, "video1.srt")
            srt2 = os.path.join(tmpdir, "video2.srt")

            with open(srt1, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\nFirst\n")
            # Make srt1 slightly older
            time.sleep(0.1)

            with open(srt2, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\nSecond\n")

            result = find_subtitle_file(tmpdir, "video")
            assert result is not None
            assert os.path.basename(result) == "video2.srt"

    def test_ignores_non_subtitle_files(self):
        """Should ignore files that are not .srt or .vtt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a non-subtitle file
            txt_path = os.path.join(tmpdir, "readme.txt")
            with open(txt_path, "w") as f:
                f.write("Not a subtitle")

            result = find_subtitle_file(tmpdir, "video")
            assert result is None


class TestRenameSubtitleFile:
    """Tests for rename_subtitle_file()."""

    def test_renames_to_convention(self):
        """Should rename to {title}_SUBTITLE_{lang}.{format}."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original = os.path.join(tmpdir, "original.srt")
            with open(original, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\nTest\n")

            result = rename_subtitle_file(original, "My Video", "ar")
            assert "My Video_SUBTITLE_ar.srt" in result

    def test_preserves_extension(self):
        """Should keep the original subtitle format extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original = os.path.join(tmpdir, "original.vtt")
            with open(original, "w") as f:
                f.write("WEBVTT\n")

            result = rename_subtitle_file(original, "My Video", "ar")
            assert result.endswith(".vtt")

    def test_handles_duplicate_names(self):
        """Should add counter suffix when target file already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the target name first
            existing = os.path.join(tmpdir, "My Video_SUBTITLE_ar.srt")
            with open(existing, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\nExisting\n")

            # Create the file to rename
            original = os.path.join(tmpdir, "original.srt")
            with open(original, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\nNew\n")

            result = rename_subtitle_file(original, "My Video", "ar")
            assert "My Video_SUBTITLE_ar_1.srt" in result

    def test_sanitizes_title(self):
        """Should sanitize the title in the new filename."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original = os.path.join(tmpdir, "original.srt")
            with open(original, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\nTest\n")

            result = rename_subtitle_file(original, 'Video: "Test"', "en")
            # Colon and quotes should be removed
            assert ":" not in os.path.basename(result)
            assert '"' not in os.path.basename(result)

    def test_returns_original_on_rename_failure(self):
        """Should return original path if rename fails (e.g., permission error)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original = os.path.join(tmpdir, "original.srt")
            with open(original, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\nTest\n")

            with patch("youtube_downloader.subtitle_manager.os.rename", side_effect=OSError("Permission denied")):
                result = rename_subtitle_file(original, "My Video", "ar")
                # Should return original path on failure
                assert result == original

    def test_same_path_no_rename(self):
        """Should not rename if the file already has the correct name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "My Video_SUBTITLE_ar.srt")
            with open(target, "w") as f:
                f.write("1\n00:00:00,000 --> 00:00:05,000\nTest\n")

            result = rename_subtitle_file(target, "My Video", "ar")
            assert result == target
