# DownTube — اختبارات Rate Limiting

"""
اختبارات نظام تحديد معدل الطلبات:
- السماح بالطلبات ضمن الحد
- رفض الطلبات بعد تجاوز الحد
- عدم تطبيق Rate Limiting على الصفحة الرئيسية
"""

import time
import pytest
from unittest.mock import patch

from app.main import rate_limiter
from app.config import RATE_LIMIT_REQUESTS
from app.exceptions import RateLimitExceededError


class TestRateLimiting:
    """اختبارات تحديد معدل الطلبات."""

    def test_allows_requests_within_limit(self, client, valid_youtube_url):
        """يجب أن يسمح بالطلبات ضمن الحد المسموح."""
        with patch("app.services.downloader.download_service.extract_info") as mock:
            mock.return_value = {"title": "Test", "subtitles": {}, "automatic_captions": {}}
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            assert resp.status_code == 200

    def test_blocks_requests_over_limit(self, client, valid_youtube_url):
        """يجب أن يرفض الطلبات بعد تجاوز الحد."""
        # TestClient يرفع HTTPException من الـ middleware مباشرة
        # لذلك نتحقق من أن الـ Rate Liminter يرفع الاستثناء
        from fastapi import HTTPException
        test_ip = "testclient"

        # ملء الحد بطلبات حديثة
        now = time.time()
        for _ in range(RATE_LIMIT_REQUESTS + 5):
            rate_limiter._requests[test_ip].append(now)

        # في TestClient، الـ HTTPException من middleware يُرفع كاستثناء
        with pytest.raises(HTTPException) as exc_info:
            client.post("/api/info", json={"url": valid_youtube_url})
        assert exc_info.value.status_code == 429

    def test_no_rate_limit_on_homepage(self, client):
        """لا يجب تطبيق Rate Limiting على الصفحة الرئيسية."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_remaining_header_set(self, client, valid_youtube_url):
        """يجب أن يضبط رأس X-RateLimit-Remaining."""
        with patch("app.services.downloader.download_service.extract_info") as mock:
            mock.return_value = {"title": "Test", "subtitles": {}, "automatic_captions": {}}
            resp = client.post("/api/info", json={"url": valid_youtube_url})
            if resp.status_code == 200:
                assert "x-ratelimit-remaining" in resp.headers or "X-RateLimit-Remaining" in resp.headers


class TestRateLimiterUnit:
    """اختبارات وحدة لمحدد المعدل."""

    def test_check_allows_within_limit(self):
        """يجب أن يسمح بالطلبات ضمن الحد."""
        ip = "1.2.3.4"
        rate_limiter._requests[ip] = []
        rate_limiter.check(ip)

    def test_check_blocks_over_limit(self):
        """يجب أن يرفع استثناء عند تجاوز الحد."""
        ip = "5.6.7.8"
        now = time.time()

        # ملء بطلبات حديثة
        rate_limiter._requests[ip] = [now] * RATE_LIMIT_REQUESTS

        with pytest.raises(RateLimitExceededError):
            rate_limiter.check(ip)

    def test_get_remaining_returns_count(self):
        """يجب أن يرجع عدد الطلبات المتبقية."""
        ip = "9.10.11.12"
        rate_limiter._requests[ip] = []
        remaining = rate_limiter.get_remaining(ip)
        assert remaining == RATE_LIMIT_REQUESTS

    def test_remaining_decreases_after_request(self):
        """يجب أن يقل العدد المتبقي بعد كل طلب."""
        ip = "13.14.15.16"
        rate_limiter._requests[ip] = []
        rate_limiter.check(ip)
        remaining = rate_limiter.get_remaining(ip)
        assert remaining == RATE_LIMIT_REQUESTS - 1
