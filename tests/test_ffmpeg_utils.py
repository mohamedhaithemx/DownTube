"""
Tests for ffmpeg_utils.py — FFmpeg detection and path resolution.

These tests mock filesystem and shutil.which to avoid depending on
the actual FFmpeg installation on the test machine.
"""

import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from youtube_downloader.ffmpeg_utils import get_ffmpeg_path, get_ffmpeg_version
from youtube_downloader.exceptions import FFmpegNotFoundError
from youtube_downloader.config import FFMPEG_EXE


def _set_frozen(value):
    """Helper to set/unset sys.frozen for testing."""
    if value:
        sys.frozen = True  # type: ignore[attr-defined]
    else:
        if hasattr(sys, "frozen"):
            delattr(sys, "frozen")


class TestGetFFmpegPath:
    """Tests for get_ffmpeg_path()."""

    @patch("shutil.which", return_value="/usr/bin/ffmpeg")
    def test_returns_none_when_in_path(self, mock_which):
        """When FFmpeg is in system PATH, should return None."""
        _set_frozen(False)
        try:
            result = get_ffmpeg_path()
            assert result is None
            mock_which.assert_called_once_with(FFMPEG_EXE)
        finally:
            _set_frozen(False)

    @patch("shutil.which", return_value=None)
    def test_raises_when_not_found(self, mock_which):
        """When FFmpeg is not found anywhere, should raise FFmpegNotFoundError."""
        _set_frozen(False)
        try:
            with pytest.raises(FFmpegNotFoundError):
                get_ffmpeg_path()
        finally:
            _set_frozen(False)

    @patch("shutil.which", return_value=None)
    def test_bundled_frozen_path(self, mock_which):
        """When running as frozen executable with bundled FFmpeg, return its directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ffmpeg_dir = os.path.join(tmpdir, "ffmpeg")
            os.makedirs(ffmpeg_dir)
            ffmpeg_path = os.path.join(ffmpeg_dir, FFMPEG_EXE)
            # Create a dummy ffmpeg file
            with open(ffmpeg_path, "w") as f:
                f.write("dummy")

            _set_frozen(True)
            old_exe = getattr(sys, "executable", None)
            sys.executable = os.path.join(tmpdir, "app.exe")
            try:
                result = get_ffmpeg_path()
                assert result == ffmpeg_dir
            finally:
                _set_frozen(False)
                if old_exe:
                    sys.executable = old_exe

    @patch("shutil.which", return_value=None)
    def test_project_directory_fallback(self, mock_which):
        """When FFmpeg is in the project root directory, return the directory."""
        _set_frozen(False)
        try:
            # Create a temporary directory with ffmpeg binary at project root level
            with tempfile.TemporaryDirectory() as tmpdir:
                ffmpeg_path = os.path.join(tmpdir, FFMPEG_EXE)
                with open(ffmpeg_path, "w") as f:
                    f.write("dummy")

                # Patch __file__ to point inside tmpdir so the parent directory is tmpdir
                fake_file = os.path.join(tmpdir, "youtube_downloader", "ffmpeg_utils.py")
                with patch("youtube_downloader.ffmpeg_utils.__file__", fake_file):
                    result = get_ffmpeg_path()
                    # Should find ffmpeg in the root directory
                    assert result is not None
                    assert FFMPEG_EXE in os.listdir(result) or os.path.exists(os.path.join(result, FFMPEG_EXE))
        finally:
            _set_frozen(False)


class TestGetFFmpegVersion:
    """Tests for get_ffmpeg_version()."""

    @patch("subprocess.run")
    def test_returns_version_string(self, mock_run):
        """Should return the first line of ffmpeg -version output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="ffmpeg version 6.0 Copyright (c) 2000-2023\nbuilt with gcc",
        )
        result = get_ffmpeg_version()
        assert "ffmpeg version 6.0" in result

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_returns_none_when_not_found(self, mock_run):
        """Should return None when FFmpeg is not installed."""
        result = get_ffmpeg_version()
        assert result is None

    def test_returns_none_on_timeout(self):
        """Should return None when FFmpeg command times out."""
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10)):
            result = get_ffmpeg_version()
            assert result is None

    @patch("subprocess.run")
    def test_returns_none_on_nonzero_exit(self, mock_run):
        """Should return None when FFmpeg returns a non-zero exit code."""
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = get_ffmpeg_version()
        assert result is None


class TestFFmpegPathSearchOrder:
    """Verify the search order: bundled → PATH → project dir."""

    @patch("shutil.which", return_value="/usr/bin/ffmpeg")
    def test_path_checked_before_project_dir(self, mock_which):
        """When FFmpeg is in PATH, should NOT check project directory."""
        _set_frozen(False)
        try:
            result = get_ffmpeg_path()
            assert result is None  # None means PATH was sufficient
        finally:
            _set_frozen(False)

    def test_bundled_checked_before_path(self):
        """When bundled FFmpeg exists, should return its directory without checking PATH."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ffmpeg_dir = os.path.join(tmpdir, "ffmpeg")
            os.makedirs(ffmpeg_dir)
            ffmpeg_path = os.path.join(ffmpeg_dir, FFMPEG_EXE)
            with open(ffmpeg_path, "w") as f:
                f.write("dummy")

            _set_frozen(True)
            old_exe = getattr(sys, "executable", None)
            sys.executable = os.path.join(tmpdir, "app.exe")
            try:
                with patch("shutil.which") as mock_which:
                    result = get_ffmpeg_path()
                    # shutil.which should NOT be called if bundled is found
                    mock_which.assert_not_called()
                    assert result == ffmpeg_dir
            finally:
                _set_frozen(False)
                if old_exe:
                    sys.executable = old_exe
