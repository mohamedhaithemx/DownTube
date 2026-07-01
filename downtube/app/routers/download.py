import os
import asyncio
import threading
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.youtube_service import download_video, embed_subtitles, extract_info_flat, YouTubeError
from app.services.subtitle_service import fetch_subtitles
from app.utils.file_manager import (
    get_task_dir,
    generate_task_id,
    find_video_file,
    find_subtitle_file,
    list_files,
    human_size,
    cleanup_task,
    safe_filename,
)

MAX_DURATION_VIDEO_SUBTITLE = int(os.getenv("MAX_DURATION_VIDEO_SUBTITLE", "14400"))
MAX_DURATION_SINGLE = int(os.getenv("MAX_DURATION_SINGLE", "0"))

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
    ويُبلغ عن نسبة مدمجة مع heartbeat لمنع التوقف.
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.subtitle_pct = 0.0   # 0-100
        self.video_pct = 0.0      # 0-100
        self.subtitle_weight = 0.6
        self.video_weight = 0.4
        self.last_reported = -1
        self._last_message = ""
        self._lock = asyncio.Lock()
        self._heartbeat_task = None

    async def update_subtitle(self, pct: float, message: str = None):
        async with self._lock:
            self.subtitle_pct = min(100, pct)
            if message:
                self._last_message = message
            await self._report()
            self._start_heartbeat()

    async def update_video(self, pct: float, message: str = None):
        async with self._lock:
            self.video_pct = min(100, pct)
            if message:
                self._last_message = message
            await self._report()
            self._start_heartbeat()

    async def _report(self):
        combined = self.subtitle_pct * self.subtitle_weight + self.video_pct * self.video_weight
        # نسمح بالوصول لـ 100 فقط لو كل المهام اكتملت فعلاً
        if combined >= 100 and (self.subtitle_pct < 100 or self.video_pct < 100):
            combined = 99
        combined = min(100, combined)
        if int(combined) > self.last_reported or combined >= 100:
            self.last_reported = int(combined)
            stage = self._current_stage()
            await _broadcast(self.task_id, {
                "status": "progress",
                "percent": round(combined, 1),
                "stage": stage,
                "message": self._last_message or self._current_message(stage),
            })

    def _start_heartbeat(self):
        """إعادة بث آخر قيمة كل 15 ثانية لمنع الشعور بالتوقف"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return

        async def _hb():
            try:
                await asyncio.sleep(15)
                async with self._lock:
                    combined = self.subtitle_pct * self.subtitle_weight + self.video_pct * self.video_weight
                    if combined >= 100 and (self.subtitle_pct < 100 or self.video_pct < 100):
                        combined = 99
                    combined = min(100, combined)
                    stage = self._current_stage()
                    await _broadcast(self.task_id, {
                        "status": "progress",
                        "percent": round(combined, 1),
                        "stage": stage,
                        "message": self._last_message or self._current_message(stage),
                    })
            except Exception:
                pass

        self._heartbeat_task = asyncio.create_task(_hb())

    def _current_stage(self) -> str:
        if self.subtitle_pct < 10:
            return "subtitle_fetch"
        if self.subtitle_pct < 30:
            return "audio_prep"
        if self.subtitle_pct < 75:
            return "transcribing"
        if self.subtitle_pct < 95:
            return "translating"
        return "downloading"

    def _current_message(self, stage: str = None) -> str:
        s = stage or self._current_stage()
        messages = {
            "subtitle_fetch": "جاري فحص الترجمات المتاحة...",
            "audio_prep": "جاري تحضير الصوت...",
            "transcribing": "جاري نسخ الصوت...",
            "translating": "جاري ترجمة النص...",
            "downloading": "جاري تحميل الفيديو...",
        }
        return messages.get(s, "جاري المعالجة...")


# ── Progress Callback Factories ──────────────────────────────────────

def _stage_from_msg(message: str) -> str:
    if not message:
        return "processing"
    msg_lower = message.lower()
    if "صوت" in msg_lower or "تحويل" in msg_lower or "audio" in msg_lower:
        return "audio_prep"
    if "نسخ" in msg_lower or "transcrib" in msg_lower:
        return "transcribing"
    if "ترجم" in msg_lower or "translat" in msg_lower:
        return "translating"
    if "حفظ" in msg_lower or "srt" in msg_lower or "تنسيق" in msg_lower:
        return "saving"
    if "تحميل" in msg_lower or "download" in msg_lower:
        return "downloading"
    if "فحص" in msg_lower or "ترجمات" in msg_lower or "subtitle" in msg_lower:
        return "subtitle_fetch"
    return "processing"


def _progress_cb_factory(task_id: str):
    last_pct = [-1]
    heartbeat_task = [None]

    async def _hb(pct: float, stage: str, message: str):
        try:
            await asyncio.sleep(15)
            nonlocal_result = {
                "status": "progress",
                "percent": round(pct, 1),
                "stage": stage,
                "message": message or "جاري المعالجة...",
            }
            await _broadcast(task_id, nonlocal_result)
        except Exception:
            pass

    loop = asyncio.get_running_loop()
    def cb(pct: float, speed: float, eta: float, message: str = None):
        nonlocal last_pct, heartbeat_task
        if int(pct) > last_pct[0] or pct >= 100:
            last_pct[0] = int(pct)
            stage = _stage_from_msg(message or "")
            msg = {
                "status": "downloading",
                "percent": round(pct, 1),
                "speed": speed,
                "eta": eta,
                "stage": stage,
            }
            if message:
                msg["message"] = message
            asyncio.run_coroutine_threadsafe(_broadcast(task_id, msg), loop)
            # Heartbeat — أعد بث آخر قيمة بعد 15 ثانية
            if heartbeat_task[0] and not heartbeat_task[0].done():
                try:
                    heartbeat_task[0].cancel()
                except Exception:
                    pass
            heartbeat_task[0] = asyncio.create_task(_hb(pct, stage, message))
    return cb


def _subtitle_progress_cb(tracker: CombinedProgressTracker):
    """Callback لتحديث تقدم الترجمة عبر CombinedProgressTracker"""
    loop = asyncio.get_running_loop()
    def cb(pct: float, speed: float, eta: float, message: str = None):
        asyncio.run_coroutine_threadsafe(tracker.update_subtitle(pct, message), loop)
    return cb


def _video_progress_cb(tracker: CombinedProgressTracker):
    """Callback لتحديث تقدم تحميل الفيديو عبر CombinedProgressTracker"""
    loop = asyncio.get_running_loop()
    def cb(pct: float, speed: float, eta: float, message: str = None):
        asyncio.run_coroutine_threadsafe(tracker.update_video(pct, message), loop)
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

        # ── التحقق من المدة حسب نوع التحميل ──
        needs_duration_check = (req.include_subtitles and not req.subtitle_only)
        if needs_duration_check:
            limit = MAX_DURATION_VIDEO_SUBTITLE
            if limit > 0:
                try:
                    info = await extract_info_flat(req.url, timeout=15)
                    duration = info.get("duration", 0)
                    if duration > limit:
                        max_hours = limit // 3600
                        await _broadcast(task_id, {
                            "status": "error",
                            "message": f"مدة الفيديو تتجاوز {max_hours} ساعات. يرجى استخدام تحميل فيديو فقط أو ترجمة فقط.",
                        })
                        return
                except Exception as e:
                    logger.warning("فشل التحقق من المدة: %s", e)

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
    if subtitle_file and os.path.exists(subtitle_file):
        if os.path.getsize(subtitle_file) == 0:
            logger.warning("ملف الترجمة 0 بايت — حذف: %s", subtitle_file)
            try:
                os.unlink(subtitle_file)
            except Exception:
                pass
            subtitle_file = None
        else:
            for f in list_files(task_id):
                name = f.name.lower()
                if name.endswith((".mp4", ".mkv", ".webm")) and os.path.isfile(str(f)):
                    video_base = os.path.splitext(os.path.basename(str(f)))[0]
                    sub_ext = os.path.splitext(subtitle_file)[1]
                    new_sub_name = f"{video_base}{sub_ext}"
                    new_sub_path = os.path.join(output_dir, new_sub_name)
                    if subtitle_file != new_sub_path and not os.path.exists(new_sub_path):
                        try:
                            os.rename(subtitle_file, new_sub_path)
                            logger.info("إعادة تسمية الترجمة: %s → %s",
                                        os.path.basename(subtitle_file), new_sub_name)
                            subtitle_file = new_sub_path
                        except OSError:
                            pass
                    break

    if not subtitle_file:
        await _broadcast(task_id, {
            "status": "error",
            "message": "لم يتم العثور على ترجمة صالحة",
            "subtitle_only": True,
        })
        return

    filesize = os.path.getsize(subtitle_file)

    await _broadcast(task_id, {
        "status": "done",
        "percent": 100,
        "stage": "done",
        "message": "اكتمل التحميل!",
        "task_id": task_id,
        "filename": os.path.basename(subtitle_file),
        "filesize": human_size(filesize),
        "filesize_bytes": filesize,
        "video_file": None,
        "subtitle_file": subtitle_file,
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

    # ── تحقق من الفيديو — إذا 0 بايت أو غير موجود ──
    if video_file and (not os.path.exists(video_file) or os.path.getsize(video_file) == 0):
        logger.warning("ملف الفيديو 0 بايت أو غير موجود — تجاهل: %s", video_file)
        video_file = None

    if not video_file:
        await _broadcast(task_id, {"status": "error", "message": "فشل تحميل الفيديو — الملف الناتج فارغ"})
        return

    # ── تحقق من الترجمة — تجاهل 0 بايت + إعادة تسمية ──
    if subtitle_file:
        if not os.path.exists(subtitle_file) or os.path.getsize(subtitle_file) == 0:
            logger.warning("ملف الترجمة 0 بايت أو غير موجود — تجاهل: %s", subtitle_file)
            subtitle_file = None
        else:
            video_base = os.path.splitext(os.path.basename(video_file))[0]
            sub_ext = os.path.splitext(subtitle_file)[1]
            new_sub_name = f"{video_base}{sub_ext}"
            new_sub_path = os.path.join(output_dir, new_sub_name)
            if subtitle_file != new_sub_path and not os.path.exists(new_sub_path):
                try:
                    os.rename(subtitle_file, new_sub_path)
                    subtitle_file = new_sub_path
                except OSError:
                    pass

    if not embedded and subtitle_file and not subtitle_result:
        subtitle_result = {"path": subtitle_file, "source": "found", "type": "unknown"}

    filesize = os.path.getsize(video_file)

    await _broadcast(task_id, {
        "status": "done",
        "percent": 100,
        "stage": "done",
        "message": "اكتمل التحميل!",
        "task_id": task_id,
        "filename": os.path.basename(video_file),
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

    video_error = next((e for e in errors if e[0] == "video"), None)
    if video_error and not video_file:
        await _broadcast(task_id, {"status": "error", "message": video_error[1]})
        return

    # ── تحسين الترجمة: تجاهل 0 بايت + إعادة تسمية ──
    final_subtitle_path = subtitle_path or (subtitle_result.get("path") if subtitle_result else None)
    if final_subtitle_path:
        if not os.path.exists(final_subtitle_path) or os.path.getsize(final_subtitle_path) == 0:
            logger.warning("ملف الترجمة 0 بايت أو غير موجود — تجاهل: %s", final_subtitle_path)
            try:
                if os.path.exists(final_subtitle_path):
                    os.unlink(final_subtitle_path)
            except Exception:
                pass
            final_subtitle_path = None
            subtitle_result = {"path": None, "source": None, "type": "none"}
        else:
            for f in list_files(task_id):
                name = f.name.lower()
                if name.endswith((".mp4", ".mkv", ".webm")) and os.path.isfile(str(f)):
                    video_base = os.path.splitext(os.path.basename(str(f)))[0]
                    sub_ext = os.path.splitext(final_subtitle_path)[1]
                    new_sub_name = f"{video_base}{sub_ext}"
                    new_sub_path = os.path.join(output_dir, new_sub_name)
                    if final_subtitle_path != new_sub_path and not os.path.exists(new_sub_path):
                        try:
                            os.rename(final_subtitle_path, new_sub_path)
                            logger.info("إعادة تسمية الترجمة: %s → %s",
                                        os.path.basename(final_subtitle_path), new_sub_name)
                            final_subtitle_path = new_sub_path
                        except OSError:
                            pass
                    break

    # ── التحقق من الفيديو ──
    if video_file and (not os.path.exists(video_file) or os.path.getsize(video_file) == 0):
        logger.warning("ملف الفيديو 0 بايت أو غير موجود — تجاهل: %s", video_file)
        video_file = None

    if not video_file:
        await _broadcast(task_id, {"status": "error", "message": "فشل تحميل الفيديو — الملف الناتج فارغ"})
        return

    filesize = os.path.getsize(video_file)

    await _broadcast(task_id, {
        "status": "done",
        "percent": 100,
        "stage": "done",
        "message": "اكتمل التحميل!",
        "task_id": task_id,
        "filename": os.path.basename(video_file),
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

    # التحقق من أن task_id صالح (منع traversal عبر task_id نفسه)
    safe_task = "".join(c for c in task_id if c.isalnum() or c in "-_")
    if safe_task != task_id:
        raise HTTPException(status_code=400, detail="معرف المهمة غير صالح")

    def _valid_file(p: str) -> bool:
        return bool(p) and os.path.exists(p) and os.path.isfile(p) and os.path.getsize(p) > 0

    def _safe_path(requested_filename: str) -> str | None:
        """بناء مسار آمن — التحقق من أن المسار الناتج يبقى داخل output_dir"""
        # تنظيف اسم الملف من أي مسارات نسبية
        base_name = os.path.basename(requested_filename)
        if not base_name:
            return None
        full_path = os.path.normpath(os.path.join(output_dir, base_name))
        # التحقق من أن المسار النهائي يبدأ بـ output_dir
        if not full_path.startswith(os.path.normpath(output_dir) + os.sep) and full_path != os.path.normpath(output_dir):
            return None
        return full_path

    # إذا تم تحديد اسم ملف، ابحث عنه مباشرة — بسلامة من traversal
    if filename:
        safe_filepath = _safe_path(filename)
        if safe_filepath and _valid_file(safe_filepath):
            return FileResponse(
                path=safe_filepath,
                filename=os.path.basename(safe_filepath),
                media_type="application/octet-stream",
            )

    # Fallback: بحث بنوع الملف
    if file_type == "subtitle":
        filepath = find_subtitle_file(task_id)
    else:
        filepath = _find_embedded_video(task_id) or find_video_file(task_id)

    if not filepath or not _valid_file(filepath):
        candidates = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if os.path.isfile(os.path.join(output_dir, f))
        ]
        if candidates:
            candidates.sort(key=lambda p: os.path.getsize(p), reverse=True)
            filepath = next((p for p in candidates if _valid_file(p)), None)
        else:
            filepath = None

    if not filepath:
        raise HTTPException(status_code=404, detail="الملف غير موجود أو غير صالح")

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
