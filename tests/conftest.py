# DownTube — إعدادات الاختبارات المشتركة

import pytest
from fastapi.testclient import TestClient

from app.main import app, rate_limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """تنظيف Rate Limiter قبل كل اختبار."""
    rate_limiter._requests.clear()
    yield
    rate_limiter._requests.clear()


@pytest.fixture
def client():
    """إنشاء عميل اختبار لتطبيق FastAPI."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def valid_youtube_url():
    """رابط يوتيوب صالح للاختبار."""
    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.fixture
def invalid_url():
    """رابط غير صالح للاختبار."""
    return "https://www.google.com"
