import os
import asyncio
import threading
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.youtube_service import download_video, embed_subtitles, YouTubeError
from app.services.subtitle_service import fetch_subtitles
from app.utils.file_manager import (
    get_task_dir,
    generate_task_id,
    find_video_file,
    find_subtitle_file,
    human_size,
    cleanup_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/download", tags=["download"])

active_tasks: dict[str, asyncio.Event] = {}
active_websockets: dict[str, list[WebSocket]] = {}
cancel_events: dict[str, threading.Event] = {}


class DownloadRequest(BaseModel):
    url: str
    format_id: str = "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a][acodec^=mp4a]/best[ext=mp4]/best"
    include_subtitles: bool = True
    auto_generate: bool = True
    embed_subtitles: bool = False
    subtitle_only: bool = False
    task_id: Optional[str] = None


async def _send_ws(ws: WebSocket, data: dict):
    try:
        await ws.send_json(data)
    except Exception:
        pass


async def _broadcast(task_id: str, data: dict):
    for ws in active_websockets.get(task_id, []):
        await _send_ws(ws, data)


def _progress_cb_factory(task_id: str):
    loop = asyncio.get_running_loop()
    def cb(pct: float, speed: float, eta: float, message: str = None):
        msg = {
            "status": "downloading",
            "percent": round(pct, 1),
            "speed": speed,
            "eta": eta,
        }
        if message:
            msg["message"] = message
        asyncio.run_coroutine_threadsafe(_broadcast(task_id, msg), loop)
    return cb


@router.post("/video")
async def start_download(req: DownloadRequest):
    from app.utils.validators import validate_youtube_url, ERROR_MESSAGES

    if not validate_youtube_url(req.url):
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES["invalid_url"])

    task_id = req.task_id or generate_task_id()
    if task_id in active_tasks:
        raise HTTPException(status_code=409, detail="هناك تحميل قيد التشغيل بالفعل لهذه المهمة")

    active_tasks[task_id] = asyncio.Event()
    cancel_events[task_id] = threading.Event()

    asyncio.create_task(_process_download(task_id, req))

    return {"task_id": task_id, "status": "started"}


async def _process_download(task_id: str, req: DownloadRequest):
    output_dir = str(get_task_dir(task_id))
    loop = asyncio.get_running_loop()
    progress_cb = _progress_cb_factory(task_id)
    cancel_event = cancel_events.get(task_id)

    try:
        await _broadcast(task_id, {"status": "info", "percent": 0, "message": "جاري البدء..."})
        await asyncio.sleep(0.5)

        # ── Subtitle-only mode: skip video download entirely ──
        if req.subtitle_only:
            await _broadcast(task_id, {
                "status": "info", "percent": 10, "message": "جاري جلب الترجمة..."
            })
            subtitle_result = None
            try:
                subtitle_result = await fetch_subtitles(
                    url=req.url,
                    output_dir=output_dir,
                    task_id=task_id,
                    auto_generate=True,
                    progress_callback=progress_cb,
                )
            except Exception as e:
                logger.warning("فشل جلب الترجمة: %s", e)
                subtitle_result = {"path": None, "source": None, "type": "none"}

            if cancel_event and cancel_event.is_set():
                await _broadcast(task_id, {"status": "cancelled"})
                return

            subtitle_file = find_subtitle_file(task_id)
            filesize = os.path.getsize(subtitle_file) if subtitle_file and os.path.exists(subtitle_file) else 0
            await _broadcast(task_id, {
                "status": "done",
                "percent": 100,
                "message": "اكتمل التحميل!",
                "filename": os.path.basename(subtitle_file) if subtitle_file else "subtitles.srt",
                "filesize": human_size(filesize),
                "filesize_bytes": filesize,
                "video_file": None,
                "subtitle_file": subtitle_result.get("path") if subtitle_result else None,
                "subtitle_type": subtitle_result.get("type", "none") if subtitle_result else "none",
                "subtitle_source": subtitle_result.get("source", None) if subtitle_result else None,
                "subtitle_only": True,
            })
            return

        # ── Normal flow: subtitles + video ──
        subtitle_result = None
        if req.include_subtitles:
            await _broadcast(task_id, {
                "status": "info", "percent": 5, "message": "جاري فحص الترجمات..."
            })
            try:
                subtitle_result = await fetch_subtitles(
                    url=req.url,
                    output_dir=output_dir,
                    task_id=task_id,
                    auto_generate=req.auto_generate,
                    progress_callback=progress_cb,
                )
            except Exception as e:
                logger.warning("فشل جلب الترجمة: %s", e)
                subtitle_result = {"path": None, "source": None, "type": "none"}

        if cancel_event and cancel_event.is_set():
            await _broadcast(task_id, {"status": "cancelled"})
            return

        await _broadcast(task_id, {
            "status": "downloading",
            "percent": 20,
            "message": "جاري تحميل الفيديو..."
        })

        try:
            video_path = await download_video(
                url=req.url,
                output_dir=output_dir,
                format_id=req.format_id,
                progress_callback=progress_cb,
                cancel_event=cancel_event,
            )
        except asyncio.CancelledError:
            await _broadcast(task_id, {"status": "cancelled"})
            return
        except YouTubeError as e:
            await _broadcast(task_id, {"status": "error", "message": e.message})
            return

        if cancel_event and cancel_event.is_set():
            await _broadcast(task_id, {"status": "cancelled"})
            return

        video_file = video_path
        subtitle_file = find_subtitle_file(task_id) if subtitle_result and subtitle_result.get("path") else None

        if not video_file:
            video_file = find_video_file(task_id)
        if not video_file:
            video_file_candidates = [
                os.path.join(output_dir, f)
                for f in os.listdir(output_dir)
                if os.path.isfile(os.path.join(output_dir, f))
            ]
            if video_file_candidates:
                video_file = max(video_file_candidates, key=os.path.getsize)

        # ── Embed subtitles into video if requested ──
        embedded = False
        if req.embed_subtitles and subtitle_file:
            try:
                await _broadcast(task_id, {
                    "status": "info", "percent": 70, "message": "جاري دمج الترجمة في الفيديو..."
                })
                video_file = await embed_subtitles(
                    video_file, subtitle_file, output_dir,
                    progress_callback=lambda p, s, e: asyncio.run_coroutine_threadsafe(
                        _broadcast(task_id, {
                            "status": "embedding",
                            "percent": 70 + round(p * 0.25, 1),
                            "message": f"جاري دمج الترجمة... {round(p)}%"
                        }), loop
                    ),
                    cancel_event=cancel_event,
                )
                subtitle_result = None
                embedded = True
            except asyncio.CancelledError:
                await _broadcast(task_id, {"status": "cancelled"})
                return
            except Exception as e:
                logger.warning("فشل دمج الترجمة: %s", e)

        filesize = os.path.getsize(video_file) if video_file and os.path.exists(video_file) else 0

        if subtitle_file and not subtitle_result:
            subtitle_result = {"path": subtitle_file, "source": "found", "type": "unknown"}

        await _broadcast(task_id, {
            "status": "done",
            "percent": 100,
            "message": "اكتمل التحميل!",
            "filename": os.path.basename(video_file) if video_file else "video.mp4",
            "filesize": human_size(filesize),
            "filesize_bytes": filesize,
            "video_file": video_file,
            "subtitle_file": subtitle_result.get("path") if subtitle_result else None,
            "subtitle_type": subtitle_result.get("type", "none") if subtitle_result else "none",
            "subtitle_source": subtitle_result.get("source", None) if subtitle_result else None,
            "embedded": embedded,
        })

    except asyncio.CancelledError:
        await _broadcast(task_id, {"status": "cancelled"})
    except Exception as e:
        logger.exception("خطأ في معالجة التحميل")
        await _broadcast(task_id, {"status": "error", "message": "حدث خطأ أثناء التحميل"})
    finally:
        active_tasks.pop(task_id, None)
        cancel_events.pop(task_id, None)
        active_websockets.pop(task_id, None)


@router.get("/file/{task_id}")
async def download_file(task_id: str, file_type: str = Query("video", description="video أو subtitle")):
    output_dir = str(get_task_dir(task_id))
    if file_type == "subtitle":
        filepath = find_subtitle_file(task_id)
    else:
        filepath = find_video_file(task_id)

    if not filepath or not os.path.exists(filepath):
        candidates = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
        if candidates:
            filepath = max(candidates, key=os.path.getsize)
        else:
            raise HTTPException(status_code=404, detail="الملف غير موجود")

    return FileResponse(
        path=filepath,
        filename=os.path.basename(filepath),
        media_type="application/octet-stream",
    )


@router.post("/cancel/{task_id}")
async def cancel_download(task_id: str):
    if task_id not in active_tasks and task_id not in cancel_events:
        raise HTTPException(status_code=409, detail="لا يوجد تحميل نشط لهذه المهمة")
    cancel_events.get(task_id, threading.Event()).set()
    cleanup_task(task_id)
    return {"status": "cancelled"}


@router.websocket("/ws/{task_id}")
async def websocket_progress(websocket: WebSocket, task_id: str):
    await websocket.accept()
    if task_id not in active_websockets:
        active_websockets[task_id] = []
    active_websockets[task_id].append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if task_id in active_websockets:
            try:
                active_websockets[task_id].remove(websocket)
            except ValueError:
                pass
