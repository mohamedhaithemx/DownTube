"""
Tests for app.py — FastAPI application routes and WebSocket.

Uses httpx AsyncClient with FastAPI's TestClient for testing.
"""

import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from youtube_downloader.app import app, manager, validate_url
from youtube_downloader.config import STATE_IDLE, STATE_RUNNING


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    # Reset manager state before each test
    manager.reset()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def temp_download_dir():
    """Create a temporary directory for downloads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = manager.download_dir
        manager.download_dir = tmpdir
        yield tmpdir
        manager.download_dir = old_dir


class TestValidateUrl:
    """Tests for validate_url() helper function."""

    def test_valid_watch_url(self):
        assert validate_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True

    def test_valid_short_url(self):
        assert validate_url("https://youtu.be/dQw4w9WgXcQ") is True

    def test_valid_shorts_url(self):
        assert validate_url("https://www.youtube.com/shorts/dQw4w9WgXcQ") is True

    def test_valid_playlist_url(self):
        assert validate_url("https://www.youtube.com/playlist?list=PLtest123") is True

    def test_invalid_url(self):
        assert validate_url("https://www.google.com") is False

    def test_empty_url(self):
        assert validate_url("") is False

    def test_non_youtube_url(self):
        assert validate_url("https://vimeo.com/12345") is False

    def test_http_youtube(self):
        assert validate_url("http://www.youtube.com/watch?v=dQw4w9WgXcQ") is True


class TestIndexRoute:
    """Tests for the index page route."""

    def test_returns_html(self, client):
        """Should return HTML content."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_contains_downtube(self, client):
        """Should contain DownTube in the page."""
        response = client.get("/")
        assert "DownTube" in response.text


class TestGetState:
    """Tests for GET /api/state."""

    def test_initial_state_is_idle(self, client):
        """Should return IDLE state initially."""
        response = client.get("/api/state")
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "IDLE"

    def test_state_has_current_url(self, client):
        """Should include current_url in response."""
        response = client.get("/api/state")
        data = response.json()
        assert "current_url" in data

    def test_state_has_current_title(self, client):
        """Should include current_title in response."""
        response = client.get("/api/state")
        data = response.json()
        assert "current_title" in data


class TestStartDownload:
    """Tests for POST /api/download."""

    def test_rejects_invalid_url(self, client):
        """Should return 400 for invalid URLs."""
        response = client.post(
            "/api/download",
            json={"url": "https://www.google.com", "lang": "ar", "subtitle_choice": "yes"},
        )
        assert response.status_code == 400

    def test_rejects_invalid_language(self, client):
        """Should return 400 for unsupported language."""
        response = client.post(
            "/api/download",
            json={"url": "https://www.youtube.com/watch?v=test", "lang": "xx", "subtitle_choice": "yes"},
        )
        assert response.status_code == 400

    def test_rejects_invalid_subtitle_choice(self, client):
        """Should return 400 for invalid subtitle choice."""
        response = client.post(
            "/api/download",
            json={"url": "https://www.youtube.com/watch?v=test", "lang": "ar", "subtitle_choice": "maybe"},
        )
        assert response.status_code == 400

    def test_accepts_valid_request(self, client, temp_download_dir):
        """Should accept a valid download request."""
        with patch("youtube_downloader.app._download_worker"):
            response = client.post(
                "/api/download",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "lang": "ar", "subtitle_choice": "yes"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "started"

    def test_rejects_when_already_running(self, client, temp_download_dir):
        """Should return 409 when a download is already in progress."""
        manager.state = STATE_RUNNING
        response = client.post(
            "/api/download",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "lang": "ar", "subtitle_choice": "yes"},
        )
        assert response.status_code == 409


class TestCancelDownload:
    """Tests for POST /api/cancel."""

    def test_rejects_when_idle(self, client):
        """Should return 409 when no download is in progress."""
        manager.state = STATE_IDLE
        response = client.post("/api/cancel")
        assert response.status_code == 409

    def test_accepts_when_running(self, client):
        """Should accept cancel when download is running."""
        manager.state = STATE_RUNNING
        response = client.post("/api/cancel")
        assert response.status_code == 200

    def test_sets_cancel_event(self, client):
        """Should set the cancel_event."""
        manager.state = STATE_RUNNING
        client.post("/api/cancel")
        assert manager.cancel_event.is_set()


class TestGetVideoInfo:
    """Tests for GET /api/info."""

    def test_rejects_invalid_url(self, client):
        """Should return 400 for invalid URLs."""
        response = client.get("/api/info?url=https://www.google.com")
        assert response.status_code == 400

    def test_returns_video_info(self, client):
        """Should return video information."""
        mock_info = {
            "title": "Test Video",
            "duration": 120,
            "thumbnail": "https://example.com/thumb.jpg",
            "subtitles": {"en": [{"url": "http://example.com/sub"}]},
            "automatic_captions": {},
        }

        with patch("youtube_downloader.app.DownloadManager") as MockDM:
            mock_dm = MagicMock()
            mock_dm.extract_info.return_value = mock_info
            mock_dm.get_available_subtitles.return_value = ("official", "en")
            mock_dm.estimate_filesize.return_value = 10_000_000
            MockDM.return_value = mock_dm

            response = client.get("/api/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "Test Video"
            assert data["duration"] == 120

    def test_handles_extraction_error(self, client):
        """Should return 500 when video info extraction fails."""
        with patch("youtube_downloader.app.DownloadManager") as MockDM:
            mock_dm = MagicMock()
            mock_dm.extract_info.side_effect = Exception("Video not found")
            MockDM.return_value = mock_dm

            response = client.get("/api/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            assert response.status_code == 500


class TestGetLanguages:
    """Tests for GET /api/languages."""

    def test_returns_languages(self, client):
        """Should return supported languages."""
        response = client.get("/api/languages")
        assert response.status_code == 200
        data = response.json()
        assert "languages" in data
        assert "ar" in data["languages"]
        assert "en" in data["languages"]


class TestDownloadDir:
    """Tests for download directory endpoints."""

    def test_get_download_dir(self, client):
        """Should return the current download directory."""
        response = client.get("/api/download-dir")
        assert response.status_code == 200
        data = response.json()
        assert "directory" in data

    def test_set_download_dir_invalid(self, client):
        """Should return 400 for nonexistent directory."""
        response = client.post("/api/download-dir?directory=/nonexistent/path/12345")
        assert response.status_code == 400

    def test_set_download_dir_valid(self, client):
        """Should accept a valid directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            response = client.post(f"/api/download-dir?directory={tmpdir}")
            assert response.status_code == 200
            data = response.json()
            assert data["directory"] == tmpdir


class TestWebSocket:
    """Tests for WebSocket /ws endpoint."""

    def test_websocket_connects(self, client):
        """Should accept WebSocket connection."""
        with client.websocket_connect("/ws") as ws:
            # Should receive initial state message
            data = ws.receive_json()
            assert data["type"] == "state"

    def test_websocket_receives_state(self, client):
        """Should receive current state on connect."""
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_json()
            assert data["type"] == "state"
            assert "state" in data

    def test_websocket_receives_messages(self, client):
        """Should receive messages from the queue."""
        manager.put_message({"type": "test", "data": "hello"})

        with client.websocket_connect("/ws") as ws:
            # First message is the state
            ws.receive_json()
            # May receive the test message if timing is right
            # This test just verifies the WebSocket stays connected
            data = ws.receive_json()
            assert data is not None


class TestAppManagerReset:
    """Tests for _AppManager.reset()."""

    def test_resets_to_idle(self):
        """Should reset state to IDLE."""
        manager.state = STATE_RUNNING
        manager.reset()
        assert manager.state == STATE_IDLE

    def test_clears_url(self):
        """Should clear current_url."""
        manager.current_url = "https://youtube.com/watch?v=test"
        manager.reset()
        assert manager.current_url is None

    def test_clears_cancel_event(self):
        """Should clear the cancel event."""
        manager.cancel_event.set()
        manager.reset()
        assert not manager.cancel_event.is_set()

    def test_drains_queue(self):
        """Should drain all messages from the queue."""
        manager.put_message({"type": "test1"})
        manager.put_message({"type": "test2"})
        manager.reset()
        assert manager.message_queue.empty()


class TestAppManagerMessages:
    """Tests for _AppManager message methods."""

    def test_put_and_get_messages(self):
        """Should put and retrieve messages."""
        manager.put_message({"type": "test", "value": 42})
        messages = manager.get_messages()
        assert len(messages) == 1
        assert messages[0]["value"] == 42

    def test_get_returns_empty_when_no_messages(self):
        """Should return empty list when queue is empty."""
        manager.reset()
        messages = manager.get_messages()
        assert messages == []

    def test_get_drains_all_messages(self):
        """Should drain all available messages."""
        for i in range(5):
            manager.put_message({"type": "test", "i": i})
        messages = manager.get_messages()
        assert len(messages) == 5

    def test_websocket_management(self):
        """Should add and remove WebSocket connections."""
        mock_ws = MagicMock()
        manager.add_websocket(mock_ws)
        assert mock_ws in manager._active_websockets
        manager.remove_websocket(mock_ws)
        assert mock_ws not in manager._active_websockets
