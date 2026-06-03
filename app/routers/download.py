# DownTube — مسار التحميل وتتبع التقدم

"""
يحتوي على:
- نقطة نهاية بدء التحميل
- نقطة نهاية إلغاء التحميل
- نقطة نهاية تتبع التقدم عبر SSE
"""

import re
import os
import uuid
import time
import queue
import threading
import asyncio
import logging
import mimetypes
from urllib.parse import quote
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
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

# ── خريطة التنزيلات لخدمة الملفات ──────────────────────────
_download_map: dict[str, dict] = {}
_DOWNLOAD_EXPIRY = 600  # 10 دقائق


def _cleanup_expired_downloads():
    """حذف التنزيلات منتهية الصلاحية."""
    now = time.time()
    expired = [k for k, v in _download_map.items() if now - v["created_at"] > _DOWNLOAD_EXPIRY]
    for k in expired:
        del _download_map[k]
    logger.debug("تنظيف: تم حذف %d تنزيلات منتهية", len(expired))


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
            download_id = uuid.uuid4().hex[:12]
            result = download_service.download(
                url=request.url,
                output_dir=output_dir,
                lang=request.lang,
                include_subtitle=request.include_subtitle,
                cookiefile=request.cookiefile,
                proxy=request.proxy,
                progress=progress,
                download_id=download_id,
            )
            _current_title = result.get("title")
            _cleanup_expired_downloads()
            video_file = result.get("video_file")
            subtitle_file = result.get("subtitle_file")
            logger.debug("video_file=%s subtitle_file=%s", video_file, subtitle_file)
            if video_file and os.path.isfile(video_file):
                _download_map[download_id] = {
                    "video": video_file,
                    "subtitle": subtitle_file if subtitle_file and os.path.isfile(subtitle_file) else None,
                    "title": result.get("title", "video"),
                    "created_at": time.time(),
                }
                logger.debug("download_map[%s] stored: video=%s subtitle=%s",
                             download_id, video_file,
                             subtitle_file if subtitle_file and os.path.isfile(subtitle_file) else None)
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


@router.get(
    "/download/{download_id}/{file_type}",
    summary="تحميل ملف الفيديو أو الترجمة",
)
async def serve_file(download_id: str, file_type: str):
    """
    خدمة ملف الفيديو أو الترجمة المحمل مع فتح نافذة Save As.
    
    المسارات:
        download_id: معرف التحميل
        file_type: video أو subtitle
    """
    if file_type not in ("video", "subtitle"):
        raise HTTPException(status_code=400, detail="نوع ملف غير صالح")

    entry = _download_map.get(download_id)
    if not entry:
        raise HTTPException(status_code=404, detail="الملف غير موجود أو انتهت صلاحيته")

    file_path = entry.get(file_type)
    if not file_path:
        raise HTTPException(status_code=404, detail="هذا الملف غير متاح")

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="الملف غير موجود على السيرفر")

    filename = os.path.basename(file_path)
    media_type, _ = mimetypes.guess_type(file_path)
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )
