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
    list_files,
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


# ── WebSocket Helpers ────────────────────────────────────────────────

async def _send_ws(ws: WebSocket, data: dict):
    try:
        await ws.send_json(data)
    except Exception:
        pass


async def _broadcast(task_id: str, data: dict):
    for ws in active_websockets.get(task_id, []):
        await _send_ws(ws, data)


# ── Combined Progress Tracker ────────────────────────────────────────

class CombinedProgressTracker:
    """
    يتتبع تقدم المهام المتوازية (ترجمة + تحميل فيديو)
    ويُبلغ عن نسبة مدمجة تتحرك بنعومة 1% في كل مرة.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.subtitle_pct = 0.0   # 0-100
        self.video_pct = 0.0      # 0-100
        self.subtitle_weight = 0.6
        self.video_weight = 0.4
        self.last_reported = -1
        self._lock = asyncio.Lock()

    async def update_subtitle(self, pct: float):
        async with self._lock:
            self.subtitle_pct = min(100, pct)
            await self._report()

    async def update_video(self, pct: float):
        async with self._lock:
            self.video_pct = min(100, pct)
            await self._report()

    async def _report(self):
        combined = self.subtitle_pct * self.subtitle_weight + self.video_pct * self.video_weight
        combined = min(99, combined)
        if int(combined) > self.last_reported:
            self.last_reported = int(combined)
            await _broadcast(self.task_id, {
                "status": "progress",
                "percent": round(combined, 1),
                "stage": self._current_stage(),
                "message": self._current_message(),
            })

    def _current_stage(self) -> str:
        if self.subtitle_pct < 5:
            return "audio_prep"
        if self.subtitle_pct < 65:
            return "transcribing"
        if self.subtitle_pct < 90:
            return "translating"
        return "downloading"

    def _current_message(self) -> str:
        stage = self._current_stage()
        messages = {
            "audio_prep": "جاري تحضير الصوت...",
            "transcribing": "جاري نسخ الصوت...",
            "translating": "جاري ترجمة النص...",
            "downloading": "جاري تحميل الفيديو...",
        }
        return messages.get(stage, "جاري المعالجة...")


# ── Progress Callback Factories ──────────────────────────────────────

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


def _subtitle_progress_cb(tracker: CombinedProgressTracker):
    """Callback لتحديث تقدم الترجمة عبر CombinedProgressTracker"""
    loop = asyncio.get_running_loop()
    def cb(pct: float, speed: float, eta: float, message: str = None):
        asyncio.run_coroutine_threadsafe(tracker.update_subtitle(pct), loop)
    return cb


def _video_progress_cb(tracker: CombinedProgressTracker):
    """Callback لتحديث تقدم تحميل الفيديو عبر CombinedProgressTracker"""
    loop = asyncio.get_running_loop()
    def cb(pct: float, speed: float, eta: float, message: str = None):
        asyncio.run_coroutine_threadsafe(tracker.update_video(pct), loop)
    return cb


# ── Routes ───────────────────────────────────────────────────────────

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
    cancel_event = cancel_events.get(task_id)

    try:
        await _broadcast(task_id, {
            "status": "info", "percent": 1,
            "stage": "starting",
            "message": "جاري البدء...",
        })
        await asyncio.sleep(0.3)

        # ── Subtitle-only mode: لا تحميل فيديو ──
        if req.subtitle_only:
            await _process_subtitle_only(task_id, req, output_dir, cancel_event)
            return

        # ── Normal flow ──
        # تحقق: هل نحتاج ترجمة مدمجة؟ إذا نعم → تسلسلي، إذا لا → متوازي
        needs_embed = req.embed_subtitles and req.include_subtitles

        if needs_embed:
            # ── Sequential: ترجمة أولاً ثم تحميل ثم دمج ──
            await _process_sequential_embed(task_id, req, output_dir, cancel_event)
        else:
            # ── Parallel: ترجمة + تحميل فيديو بالتوازي ──
            await _process_parallel(task_id, req, output_dir, cancel_event)

    except asyncio.CancelledError:
        await _broadcast(task_id, {"status": "cancelled"})
    except Exception as e:
        logger.exception("خطأ في معالجة التحميل")
        await _broadcast(task_id, {"status": "error", "message": "حدث خطأ أثناء التحميل"})
    finally:
        active_tasks.pop(task_id, None)
        cancel_events.pop(task_id, None)
        active_websockets.pop(task_id, None)


# ── Subtitle-only Processing ─────────────────────────────────────────

async def _process_subtitle_only(
    task_id: str, req: DownloadRequest, output_dir: str, cancel_event
):
    progress_cb = _progress_cb_factory(task_id)

    await _broadcast(task_id, {
        "status": "info", "percent": 2,
        "stage": "audio_prep",
        "message": "جاري جلب الترجمة...",
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
        "stage": "done",
        "message": "اكتمل التحميل!",
        "task_id": task_id,
        "filename": os.path.basename(subtitle_file) if subtitle_file else "subtitles.srt",
        "filesize": human_size(filesize),
        "filesize_bytes": filesize,
        "video_file": None,
        "subtitle_file": subtitle_file or (subtitle_result.get("path") if subtitle_result else None),
        "subtitle_type": subtitle_result.get("type", "none") if subtitle_result else "none",
        "subtitle_source": subtitle_result.get("source", None) if subtitle_result else None,
        "subtitle_only": True,
    })


# ── Sequential Processing (embed subtitles) ──────────────────────────

async def _process_sequential_embed(
    task_id: str, req: DownloadRequest, output_dir: str, cancel_event
):
    loop = asyncio.get_running_loop()
    progress_cb = _progress_cb_factory(task_id)

    # 1. جلب الترجمة أولاً
    subtitle_result = None
    if req.include_subtitles:
        await _broadcast(task_id, {
            "status": "info", "percent": 2,
            "stage": "audio_prep",
            "message": "جاري فحص الترجمات...",
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

    # 2. تحميل الفيديو
    await _broadcast(task_id, {
        "status": "info", "percent": 50,
        "stage": "downloading",
        "message": "جاري تحميل الفيديو...",
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

    # 3. دمج الترجمة
    embedded = False
    if req.embed_subtitles and subtitle_file:
        try:
            await _broadcast(task_id, {
                "status": "info", "percent": 85,
                "stage": "merging",
                "message": "جاري دمج الترجمة في الفيديو...",
            })
            video_file = await embed_subtitles(
                video_file, subtitle_file, output_dir,
                progress_callback=lambda p, s, e: asyncio.run_coroutine_threadsafe(
                    _broadcast(task_id, {
                        "status": "embedding",
                        "percent": 85 + round(p * 0.1, 1),
                        "stage": "merging",
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

    if not embedded and subtitle_file and not subtitle_result:
        subtitle_result = {"path": subtitle_file, "source": "found", "type": "unknown"}

    await _broadcast(task_id, {
        "status": "done",
        "percent": 100,
        "stage": "done",
        "message": "اكتمل التحميل!",
        "task_id": task_id,
        "filename": os.path.basename(video_file) if video_file else "video.mp4",
        "filesize": human_size(filesize),
        "filesize_bytes": filesize,
        "video_file": video_file,
        "subtitle_file": subtitle_result.get("path") if subtitle_result else None,
        "subtitle_type": subtitle_result.get("type", "none") if subtitle_result else "none",
        "subtitle_source": subtitle_result.get("source", None) if subtitle_result else None,
        "embedded": embedded,
    })


# ── Parallel Processing (non-embed) ──────────────────────────────────

async def _process_parallel(
    task_id: str, req: DownloadRequest, output_dir: str, cancel_event
):
    """
    تشغيل الترجمة وتحميل الفيديو بالتوازي.
    الترجمة تحتل 60% من التقدم الإجمالي، وتحميل الفيديو 40%.
    """
    tracker = CombinedProgressTracker(task_id)

    subtitle_result = None
    video_path = None
    errors = []

    # بدء التقدم فوراً
    await _broadcast(task_id, {
        "status": "info", "percent": 1,
        "stage": "starting",
        "message": "جاري البدء بالتحميل والترجمة بالتوازي...",
    })

    async def _run_subtitle():
        nonlocal subtitle_result
        if not req.include_subtitles:
            await tracker.update_subtitle(100)
            return
        try:
            sub_cb = _subtitle_progress_cb(tracker)
            subtitle_result = await fetch_subtitles(
                url=req.url,
                output_dir=output_dir,
                task_id=task_id,
                auto_generate=req.auto_generate,
                progress_callback=sub_cb,
            )
            await tracker.update_subtitle(100)
        except Exception as e:
            logger.warning("فشل جلب الترجمة (متوازي): %s", e)
            subtitle_result = {"path": None, "source": None, "type": "none"}
            await tracker.update_subtitle(100)
            errors.append(("subtitle", str(e)))

    async def _run_video():
        nonlocal video_path
        try:
            vid_cb = _video_progress_cb(tracker)
            video_path = await download_video(
                url=req.url,
                output_dir=output_dir,
                format_id=req.format_id,
                progress_callback=vid_cb,
                cancel_event=cancel_event,
            )
            await tracker.update_video(100)
        except asyncio.CancelledError:
            raise
        except YouTubeError as e:
            errors.append(("video", e.message))
            await tracker.update_video(100)
        except Exception as e:
            errors.append(("video", str(e)))
            await tracker.update_video(100)

    # تشغيل المهام بالتوازي
    subtitle_task = asyncio.create_task(_run_subtitle())
    video_task = asyncio.create_task(_run_video())

    await asyncio.gather(subtitle_task, video_task, return_exceptions=True)

    if cancel_event and cancel_event.is_set():
        await _broadcast(task_id, {"status": "cancelled"})
        return

    # جمع النتائج
    video_file = video_path
    # مسار الترجمة: استخدم subtitle_result مباشرة أو ابحث عن الملف
    subtitle_path = None
    if subtitle_result and subtitle_result.get("path"):
        subtitle_path = subtitle_result.get("path")
    elif subtitle_result:
        # ابحث عن ملف الترجمة في مجلد المهمة
        found = find_subtitle_file(task_id)
        if found:
            subtitle_path = found
            subtitle_result = {"path": found, "source": "found", "type": "unknown"}

    if not video_file:
        video_file = find_video_file(task_id)
    if not video_file:
        candidates = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if os.path.isfile(os.path.join(output_dir, f))
        ]
        if candidates:
            video_file = max(candidates, key=os.path.getsize)

    # التحقق من أخطاء الفيديو
    video_error = next((e for e in errors if e[0] == "video"), None)
    if video_error and not video_file:
        await _broadcast(task_id, {"status": "error", "message": video_error[1]})
        return

    filesize = os.path.getsize(video_file) if video_file and os.path.exists(video_file) else 0

    # التأكد من إرسال مسار الترجمة الصحيح
    final_subtitle_path = subtitle_path or (subtitle_result.get("path") if subtitle_result else None)

    await _broadcast(task_id, {
        "status": "done",
        "percent": 100,
        "stage": "done",
        "message": "اكتمل التحميل!",
        "task_id": task_id,
        "filename": os.path.basename(video_file) if video_file else "video.mp4",
        "filesize": human_size(filesize),
        "filesize_bytes": filesize,
        "video_file": video_file,
        "subtitle_file": final_subtitle_path,
        "subtitle_type": subtitle_result.get("type", "none") if subtitle_result else "none",
        "subtitle_source": subtitle_result.get("source", None) if subtitle_result else None,
        "embedded": False,
    })


# ── File Download Route ──────────────────────────────────────────────

@router.get("/file/{task_id}")
async def download_file(
    task_id: str,
    file_type: str = Query("video", description="video أو subtitle"),
    filename: str = Query(None, description="اسم ملف محدد للتحميل"),
):
    output_dir = str(get_task_dir(task_id))

    # إذا تم تحديد اسم ملف، ابحث عنه مباشرة
    if filename:
        direct_path = os.path.join(output_dir, filename)
        if os.path.exists(direct_path) and os.path.isfile(direct_path):
            return FileResponse(
                path=direct_path,
                filename=filename,
                media_type="application/octet-stream",
            )

    # Fallback: بحث بنوع الملف
    if file_type == "subtitle":
        filepath = find_subtitle_file(task_id)
    else:
        # للفيديو: فضّل الملف المدمج (_embedded) إن وجد
        filepath = _find_embedded_video(task_id) or find_video_file(task_id)

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


def _find_embedded_video(task_id: str) -> str | None:
    """إيجاد ملف الفيديو المدمج (_embedded) إن وجد"""
    for f in list_files(task_id):
        name = f.name.lower()
        if "_embedded" in name and f.suffix.lower() in {".mp4", ".mkv", ".webm", ".avi", ".mov"}:
            return str(f)
    return None


# ── Cancel Route ─────────────────────────────────────────────────────

@router.post("/cancel/{task_id}")
async def cancel_download(task_id: str):
    if task_id not in active_tasks and task_id not in cancel_events:
        raise HTTPException(status_code=409, detail="لا يوجد تحميل نشط لهذه المهمة")
    cancel_events.get(task_id, threading.Event()).set()
    cleanup_task(task_id)
    return {"status": "cancelled"}


# ── WebSocket for Progress ───────────────────────────────────────────

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
