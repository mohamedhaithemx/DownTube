# DownTube — اختبارات جلب معلومات الفيديو

"""
اختبارات نقطة نهاية /api/info:
- جلب معلومات فيديو برابط صحيح
- رابط غير صحيح
- فيديو بدون ترجمة عربية
- أخطاء الخادم
"""

import pytest
from unittest.mock import patch, MagicMock


class TestVideoInfoValidUrl:
    """اختبارات جلب معلومات الفيديو برابط صحيح."""

    def test_returns_200_with_valid_url(self, client, valid_youtube_url):
        """يجب أن يرجع 200 مع رابط صحيح."""
        mock_info = {
            "title": "فيديو اختباري",
            "duration": 300,
            "thumbnail": "https://i.ytimg.com/vi/test/thumb.jpg",
            "subtitles": {"ar": [{"url": "http://example.com/sub"}]},
            "automatic_captions": {},
        }
        with patch("app.services.downloader.download_service.extract_info", return_value=mock_info):
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            assert resp.status_code == 200

    def test_returns_video_title(self, client, valid_youtube_url):
        """يجب أن يرجع عنوان الفيديو."""
        mock_info = {
            "title": "فيديو اختباري رائع",
            "duration": 300,
            "thumbnail": "https://i.ytimg.com/vi/test/thumb.jpg",
            "subtitles": {"ar": [{"url": "http://example.com/sub"}]},
            "automatic_captions": {},
        }
        with patch("app.services.downloader.download_service.extract_info", return_value=mock_info):
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            data = resp.json()
            assert data["title"] == "فيديو اختباري رائع"

    def test_returns_duration(self, client, valid_youtube_url):
        """يجب أن يرجع مدة الفيديو."""
        mock_info = {
            "title": "Test",
            "duration": 180,
            "subtitles": {},
            "automatic_captions": {},
        }
        with patch("app.services.downloader.download_service.extract_info", return_value=mock_info):
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            data = resp.json()
            assert data["duration"] == 180

    def test_returns_thumbnail(self, client, valid_youtube_url):
        """يجب أن يرجع الصورة المصغرة."""
        mock_info = {
            "title": "Test",
            "duration": 60,
            "thumbnail": "https://i.ytimg.com/vi/test/thumb.jpg",
            "subtitles": {},
            "automatic_captions": {},
        }
        with patch("app.services.downloader.download_service.extract_info", return_value=mock_info):
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            data = resp.json()
            assert data["thumbnail"] == "https://i.ytimg.com/vi/test/thumb.jpg"

    def test_detects_arabic_subtitle(self, client, valid_youtube_url):
        """يجب أن يكشف عن وجود ترجمة عربية رسمية."""
        mock_info = {
            "title": "Test",
            "subtitles": {"ar": [{"url": "http://example.com/sub"}]},
            "automatic_captions": {},
        }
        with patch("app.services.downloader.download_service.extract_info", return_value=mock_info):
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            data = resp.json()
            assert data["subtitle_info"]["available"] is True
            assert data["subtitle_info"]["subtitle_type"] == "official"

    def test_detects_auto_subtitle(self, client, valid_youtube_url):
        """يجب أن يكشف عن وجود ترجمة تلقائية."""
        mock_info = {
            "title": "Test",
            "subtitles": {},
            "automatic_captions": {"ar-SA": [{"url": "http://example.com/sub"}]},
        }
        with patch("app.services.downloader.download_service.extract_info", return_value=mock_info):
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            data = resp.json()
            assert data["subtitle_info"]["available"] is True
            assert data["subtitle_info"]["subtitle_type"] == "auto"


class TestVideoInfoInvalidUrl:
    """اختبارات رابط غير صحيح."""

    def test_returns_400_for_non_youtube(self, client, invalid_url):
        """يجب أن يرجع 400 لرابط غير يوتيوب."""
        resp = client.post("/api/info", json={"url": invalid_url})
        assert resp.status_code == 400

    def test_returns_400_for_empty_url(self, client):
        """يجب أن يرجع 400 لرابط فارغ."""
        resp = client.post("/api/info", json={"url": ""})
        assert resp.status_code == 400

    def test_returns_400_for_vimeo(self, client):
        """يجب أن يرجع 400 لرابط فيميو."""
        resp = client.post("/api/info", json={"url": "https://vimeo.com/12345"})
        assert resp.status_code == 400

    def test_returns_400_for_random_string(self, client):
        """يجب أن يرجع 400 لنص عشوائي."""
        resp = client.post("/api/info", json={"url": "هذا ليس رابط"})
        assert resp.status_code == 400

    def test_error_message_in_arabic(self, client, invalid_url):
        """يجب أن تكون رسالة الخطأ بالعربية."""
        resp = client.post("/api/info", json={"url": invalid_url})
        data = resp.json()
        assert "غير صالح" in data["detail"] or "رابط" in data["detail"]


class TestVideoInfoNoSubtitle:
    """اختبارات فيديو بدون ترجمة عربية."""

    def test_no_subtitle_returns_available_false(self, client, valid_youtube_url):
        """يجب أن يرجع available=False عند عدم وجود ترجمة."""
        mock_info = {
            "title": "Test",
            "subtitles": {"en": [{"url": "http://example.com/sub"}]},
            "automatic_captions": {"en": [{"url": "http://example.com/sub"}]},
        }
        with patch("app.services.downloader.download_service.extract_info", return_value=mock_info):
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            data = resp.json()
            assert data["subtitle_info"]["available"] is False

    def test_no_subtitle_message(self, client, valid_youtube_url):
        """يجب أن يعرض رسالة 'لا توجد ترجمة عربية'."""
        mock_info = {
            "title": "Test",
            "subtitles": {},
            "automatic_captions": {},
        }
        with patch("app.services.downloader.download_service.extract_info", return_value=mock_info):
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            data = resp.json()
            assert "ترجم" in data["subtitle_info"]["message"] or "عربي" in data["subtitle_info"]["message"]


class TestVideoInfoServerError:
    """اختبارات أخطاء الخادم."""

    def test_returns_500_on_extraction_error(self, client, valid_youtube_url):
        """يجب أن يرجع 500 عند فشل جلب المعلومات."""
        with patch("app.services.downloader.download_service.extract_info", side_effect=Exception("Video not found")):
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            assert resp.status_code == 500

    def test_returns_500_on_private_video(self, client, valid_youtube_url):
        """يجب أن يرجع 500 مع رسالة مناسبة للفيديو الخاص."""
        with patch("app.services.downloader.download_service.extract_info", side_effect=Exception("Private video")):
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            assert resp.status_code == 500
            assert "خاص" in resp.json()["detail"]
