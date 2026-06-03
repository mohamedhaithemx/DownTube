# DownTube — اختبارات التحميل

"""
اختبارات نقطة نهاية /api/download:
- بدء التحميل برابط صحيح
- رابط غير صحيح
- إلغاء التحميل
- تحميل جاري بالفعل
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.downloader import download_service


class TestStartDownload:
    """اختبارات بدء التحميل."""

    def test_returns_200_with_valid_url(self, client, valid_youtube_url):
        """يجب أن يقبل طلب تحميل برابط صحيح."""
        download_service.is_active = False
        resp = client.post("/api/download", json={
            "url": valid_youtube_url,
            "lang": "ar",
            "include_subtitle": True,
        })
        assert resp.status_code == 200
        # تنظيف
        download_service.is_active = False

    def test_returns_400_for_invalid_url(self, client, invalid_url):
        """يجب أن يرفض رابط غير صحيح."""
        resp = client.post("/api/download", json={
            "url": invalid_url,
            "lang": "ar",
            "include_subtitle": True,
        })
        assert resp.status_code == 400

    def test_returns_400_for_invalid_lang(self, client, valid_youtube_url):
        """يجب أن يرفض لغة غير مدعومة."""
        resp = client.post("/api/download", json={
            "url": valid_youtube_url,
            "lang": "xx",
            "include_subtitle": True,
        })
        assert resp.status_code == 400

    def test_returns_409_when_already_downloading(self, client, valid_youtube_url):
        """يجب أن يرجع 409 عند وجود تحميل جاري."""
        download_service.is_active = True
        try:
            resp = client.post("/api/download", json={
                "url": valid_youtube_url,
                "lang": "ar",
                "include_subtitle": True,
            })
            assert resp.status_code == 409
        finally:
            download_service.is_active = False

    def test_accepts_cookiefile_option(self, client, valid_youtube_url):
        """يجب أن يقبل خيار ملف الكوكيز."""
        download_service.is_active = False
        resp = client.post("/api/download", json={
            "url": valid_youtube_url,
            "lang": "ar",
            "include_subtitle": True,
            "cookiefile": "/path/to/cookies.txt",
        })
        assert resp.status_code == 200
        download_service.is_active = False

    def test_accepts_proxy_option(self, client, valid_youtube_url):
        """يجب أن يقبل خيار البروكسي."""
        download_service.is_active = False
        resp = client.post("/api/download", json={
            "url": valid_youtube_url,
            "lang": "ar",
            "include_subtitle": True,
            "proxy": "socks5://127.0.0.1:9050",
        })
        assert resp.status_code == 200
        download_service.is_active = False


class TestCancelDownload:
    """اختبارات إلغاء التحميل."""

    def test_returns_409_when_no_download(self, client):
        """يجب أن يرجع 409 عند محاولة إلغاء بدون تحميل جاري."""
        download_service.is_active = False
        resp = client.post("/api/cancel")
        assert resp.status_code == 409

    def test_cancels_active_download(self, client):
        """يجب أن يقبل إلغاء تحميل جاري."""
        download_service.is_active = True
        try:
            resp = client.post("/api/cancel")
            assert resp.status_code == 200
        finally:
            download_service.is_active = False

    def test_sets_cancel_event(self, client):
        """يجب أن يضبط حدث الإلغاء."""
        download_service.is_active = True
        try:
            resp = client.post("/api/cancel")
            assert download_service.cancel_event.is_set()
            download_service.cancel_event.clear()
        finally:
            download_service.is_active = False


class TestDownloadState:
    """اختبارات نقطة نهاية الحالة."""

    def test_returns_current_state(self, client):
        """يجب أن يرجع حالة التحميل الحالية."""
        resp = client.get("/api/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "state" in data

    def test_state_includes_is_active(self, client):
        """يجب أن تتضمن الحالة ما إذا كان هناك تحميل جاري."""
        resp = client.get("/api/state")
        data = resp.json()
        assert "is_active" in data
