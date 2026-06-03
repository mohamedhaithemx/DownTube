# DownTube — مسار التحميل وتتبع التقدم

"""
يحتوي على:
- نقطة نهاية بدء التحميل
- نقطة نهاية إلغاء التحميل
- نقطة نهاية تتبع التقدم عبر SSE
"""

import re
import os
import queue
import threading
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.models import DownloadRequest, DownloadResult, ErrorResponse
from app.config import (
    DEFAULT_DOWNLOAD_DIR,
    VALID_URL_PATTERNS,
    STATE_IDLE,
    STATE_RUNNING,
)
from app.services.downloader import download_service
from app.services.progress import ProgressTracker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["التحميل"])

# ── حالة التحميل العامة ──────────────────────────────────────
_download_state = STATE_IDLE
_current_title: Optional[str] = None
_progress_queue: queue.Queue = queue.Queue()


def validate_youtube_url(url: str) -> bool:
    """التحقق من أن الرابط هو رابط يوتيوب صالح."""
    for pattern in VALID_URL_PATTERNS:
        if re.match(pattern, url):
            return True
    return False


@router.post(
    "/download",
    response_model=DownloadResult,
    responses={
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    summary="بدء تحميل الفيديو",
)
async def start_download(request: DownloadRequest):
    """
    بدء تحميل فيديو يوتيوب مع الترجمة.
    
    يتم التحميل في خيط خلفي (background thread) ويمكن تتبع التقدم عبر SSE.
    """
    global _download_state, _current_title

    # التحقق من عدم وجود تحميل جاري
    if download_service.is_active:
        raise HTTPException(status_code=409, detail="يوجد تحميل جاري بالفعل")

    # التحقق من الرابط
    if not validate_youtube_url(request.url):
        raise HTTPException(status_code=400, detail="رابط يوتيوب غير صالح")

    # التحقق من اللغة
    if request.lang not in ("ar", "en"):
        raise HTTPException(status_code=400, detail="لغة غير مدعومة")

    # تنظيف قائمة الانتظار
    while not _progress_queue.empty():
        try:
            _progress_queue.get_nowait()
        except queue.Empty:
            break

    # إعادة تعيين حالة الإلغاء
    download_service.cancel_event.clear()
    _download_state = STATE_RUNNING
    _current_title = None

    # إنشاء مجلد التنزيل
    output_dir = DEFAULT_DOWNLOAD_DIR
    os.makedirs(output_dir, exist_ok=True)

    # بدء التحميل في خيط خلفي
    def _worker():
        global _download_state, _current_title
        progress = ProgressTracker(_progress_queue)
        try:
            result = download_service.download(
                url=request.url,
                output_dir=output_dir,
                lang=request.lang,
                include_subtitle=request.include_subtitle,
                cookiefile=request.cookiefile,
                proxy=request.proxy,
                progress=progress,
            )
            _current_title = result.get("title")
        except Exception as e:
            logger.exception("خطأ في الخيط الخلفي: %s", e)
        finally:
            _download_state = STATE_IDLE

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    return DownloadResult(
        success=True,
        title="جاري التحميل...",
    )


@router.post(
    "/cancel",
    summary="إلغاء التحميل",
)
async def cancel_download():
    """إلغاء التحميل الحالي."""
    if not download_service.is_active:
        raise HTTPException(status_code=409, detail="لا يوجد تحميل جاري للإلغاء")

    download_service.cancel()
    return {"status": "cancelling", "message": "جاري إلغاء التحميل..."}


@router.get(
    "/progress",
    summary="تتبع التقدم عبر SSE",
)
async def progress_stream(request: Request):
    """
    بث تحديثات التقدم في الوقت الحقيقي عبر Server-Sent Events.
    
    يرسل تحديثات تحتوي على: المرحلة، النسبة، السرعة، الوقت المتبقي.
    """
    async def event_generator():
        while True:
            # التحقق من أن العميل لا يزال متصلاً
            if await request.is_disconnected():
                break

            # سحب كل الرسائل من قائمة الانتظار
            messages = []
            while True:
                try:
                    import json
                    msg = _progress_queue.get_nowait()
                    messages.append(msg)
                except queue.Empty:
                    break

            for msg in messages:
                yield {
                    "event": msg.get("type", "progress"),
                    "data": json.dumps(msg, ensure_ascii=False),
                }

            # إذا لم تكن هناك رسائل، أرسل نبضة (heartbeat)
            if not messages:
                yield {"event": "heartbeat", "data": ""}

            await asyncio.sleep(0.15)  # 150ms بين التحديثات

    return EventSourceResponse(event_generator())


@router.get(
    "/state",
    summary="حالة التحميل الحالية",
)
async def get_state():
    """الحصول على حالة التحميل الحالية."""
    return {
        "state": _download_state,
        "title": _current_title,
        "is_active": download_service.is_active,
    }
