# DownTube — التطبيق الرئيسي

"""
نقطة الدخول الرئيسية لتطبيق FastAPI.
يتضمن: إعداد التطبيق، Rate Limiting، نقاط النهاية الثابتة.
"""

import os
import time
import logging
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import HOST, PORT, RATE_LIMIT_REQUESTS, RATE_LIMIT_PERIOD
from app.exceptions import RateLimitExceededError
from app.routers import info, download
from app.services.whisper_service import preload_model

logger = logging.getLogger(__name__)

# ── Rate Limiter بسيط ─────────────────────────────────────────

class RateLimiter:
    """محدد معدل الطلبات لكل عنوان IP."""

    def __init__(self, max_requests: int = RATE_LIMIT_REQUESTS, period: int = RATE_LIMIT_PERIOD):
        self.max_requests = max_requests
        self.period = period
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, ip: str):
        """التحقق من عدم تجاوز حد الطلبات. يرفع استثناء إذا تم التجاوز."""
        now = time.time()
        # تنظيف الطلبات القديمة
        self._requests[ip] = [t for t in self._requests[ip] if now - t < self.period]

        if len(self._requests[ip]) >= self.max_requests:
            raise RateLimitExceededError()

        self._requests[ip].append(now)

    def get_remaining(self, ip: str) -> int:
        """عدد الطلبات المتبقية."""
        now = time.time()
        recent = [t for t in self._requests[ip] if now - t < self.period]
        return max(0, self.max_requests - len(recent))


rate_limiter = RateLimiter()

# ── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """بدء وإيقاف التطبيق."""
    logger.info("🚀 DownTube بدأ العمل على http://%s:%d", HOST, PORT)
    # تحميل نموذج Whisper مسبقاً في خلفية (لا يعطل بدء السيرفر)
    thread = threading.Thread(target=_preload_whisper, daemon=True)
    thread.start()
    yield
    logger.info("👋 DownTube يتوقف")


def _preload_whisper():
    """تحميل Whisper في thread منفصل."""
    try:
        preload_model()
        logger.info("تم تحميل نموذج Whisper مسبقاً")
    except Exception as e:
        logger.warning("فشل التحميل المسبق لـ Whisper: %s", e)

# ── إنشاء التطبيق ────────────────────────────────────────────

app = FastAPI(
    title="DownTube",
    description="تحميل فيديوهات يوتيوب مع الترجمة العربية",
    version="3.0.0",
    lifespan=lifespan,
)

# ── Middleware: Rate Limiting ──────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """التحقق من حد الطلبات قبل معالجة كل طلب."""
    # تجاهل الطلبات الثابتة و SSE
    path = request.url.path
    if path.startswith("/static") or path == "/" or path.endswith(".html"):
        return await call_next(request)

    # تجاهل نقطة نهاية التقدم (SSE)
    if path == "/api/progress":
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"

    try:
        rate_limiter.check(client_ip)
    except RateLimitExceededError:
        raise HTTPException(
            status_code=429,
            detail="تم تجاوز حد الطلبات. حاول مرة أخرى بعد قليل",
        )

    response = await call_next(request)
    remaining = rate_limiter.get_remaining(client_ip)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response

# ── تسجيل المسارات ──────────────────────────────────────────

app.include_router(info.router)
app.include_router(download.router)

# ── الملفات الثابتة ─────────────────────────────────────────

_static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """خدمة واجهة المستخدم الرئيسية."""
    index_path = os.path.join(_static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>DownTube — الواجهة غير موجودة</h1>")
