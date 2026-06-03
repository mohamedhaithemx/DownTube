"""
app.py — FastAPI web application for DownTube.

Architecture:
  - FastAPI serves both the API and the static web UI
  - WebSocket connection provides real-time progress updates
  - Background thread handles yt-dlp downloads
  - queue.Queue bridges the download thread to the WebSocket
  - State machine: IDLE → RUNNING → FINISHED → IDLE

Thread safety:
  - Download thread NEVER touches FastAPI/Starlette objects directly
  - All communication goes through queue.Queue
  - cancel_event (threading.Event) signals cancellation
"""

import os
import re
import threading
import queue
import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .config import (
    DEFAULT_DOWNLOAD_PATH,
    HOST,
    PORT,
    STATE_IDLE,
    STATE_RUNNING,
    STATE_FINISHED,
    VALID_URL_PATTERNS,
    SUPPORTED_LANGS,
    MSG_PROGRESS,
    MSG_STATUS,
    MSG_LOG,
    MSG_DONE,
    MSG_ERROR,
    MSG_INFO,
)
from .downloader import DownloadManager
from .error_handler import map_exception_to_message, check_disk_space, retry_with_backoff
from .exceptions import DownloadCancelledError

logger = logging.getLogger(__name__)


# ── Pydantic models ────────────────────────────────────────────

class DownloadRequest(BaseModel):
    url: str
    lang: str = "ar"
    subtitle_choice: str = "yes"  # "yes" or "no"


class DownloadResponse(BaseModel):
    status: str
    message: str
    title: Optional[str] = None
    filepath: Optional[str] = None
    subtitle_file: Optional[str] = None


class InfoResponse(BaseModel):
    title: str
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    filesize_estimate: Optional[int] = None
    subtitles_available: Optional[dict] = None


class AppState(BaseModel):
    state: str
    current_url: Optional[str] = None
    current_title: Optional[str] = None


# ── Application state ──────────────────────────────────────────

class _AppManager:
    """Manages download state, threads, and queue communication."""

    def __init__(self):
        self.state = STATE_IDLE
        self.current_url: Optional[str] = None
        self.current_title: Optional[str] = None
        self.cancel_event = threading.Event()
        self.message_queue: queue.Queue = queue.Queue()
        self.download_dir = DEFAULT_DOWNLOAD_PATH
        self._lock = threading.Lock()
        self._active_websockets: list[WebSocket] = []

    def reset(self):
        """Reset state to IDLE."""
        self.state = STATE_IDLE
        self.current_url = None
        self.current_title = None
        self.cancel_event.clear()
        # Drain the queue
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except queue.Empty:
                break

    def add_websocket(self, ws: WebSocket):
        self._active_websockets.append(ws)

    def remove_websocket(self, ws: WebSocket):
        if ws in self._active_websockets:
            self._active_websockets.remove(ws)

    def put_message(self, msg: dict):
        """Put a message in the queue (called from download thread)."""
        self.message_queue.put(msg)

    def get_messages(self) -> list[dict]:
        """Drain all available messages from the queue (called from main thread)."""
        messages = []
        while True:
            try:
                messages.append(self.message_queue.get_nowait())
            except queue.Empty:
                break
        return messages


manager = _AppManager()


# ── Lifespan ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown logic."""
    os.makedirs(manager.download_dir, exist_ok=True)
    logger.info("DownTube started. Download directory: %s", manager.download_dir)
    yield
    logger.info("DownTube shutting down.")


app = FastAPI(
    title="DownTube",
    description="YouTube Downloader with Arabic subtitle support",
    version="3.0.0",
    lifespan=lifespan,
)


# ── Static files ───────────────────────────────────────────────

_static_dir = os.path.join(os.path.dirname(__file__), "static")
_template_dir = os.path.join(os.path.dirname(__file__), "templates")

if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ── Helper: validate YouTube URL ──────────────────────────────

def validate_url(url: str) -> bool:
    """Check if the URL matches a valid YouTube video URL."""
    for pattern in VALID_URL_PATTERNS:
        if re.match(pattern, url):
            return True
    return False


# ── Download worker (runs in background thread) ───────────────

def _download_worker(url: str, lang: str, subtitle_choice: str):
    """
    Background thread function that performs the download.

    All progress/status updates are sent via manager.put_message().
    This function NEVER touches FastAPI objects directly.
    """
    try:
        manager.state = STATE_RUNNING
        manager.current_url = url

        # Create download directory if needed
        os.makedirs(manager.download_dir, exist_ok=True)

        # Progress callback — sends messages to the queue
        def progress_callback(msg: dict):
            manager.put_message(msg)

        # Create download manager
        dm = DownloadManager(
            cancel_event=manager.cancel_event,
            progress_callback=progress_callback,
        )

        # Extract info first (with retry)
        manager.put_message({"type": MSG_STATUS, "message": "جاري استخراج معلومات الفيديو..."})
        info = retry_with_backoff(dm.extract_info, url)
        title = info.get("title", "unknown")
        manager.current_title = title

        # Check disk space
        estimated_size = dm.estimate_filesize(info)
        if estimated_size:
            check_disk_space(manager.download_dir, estimated_size)

        # Check subtitles availability and notify UI
        sub_info = dm.get_available_subtitles(info, lang)
        if subtitle_choice == "yes" and sub_info:
            sub_type = "رسمية" if sub_info[0] == "official" else "تلقائية"
            manager.put_message({
                "type": MSG_INFO,
                "message": f"ترجمة متاحة ({sub_type}): {sub_info[1]}",
                "subtitle_type": sub_info[0],
                "subtitle_key": sub_info[1],
            })
        elif subtitle_choice == "yes" and not sub_info:
            manager.put_message({
                "type": MSG_INFO,
                "message": "لم يتم العثور على ترجمة باللغة المطلوبة",
            })

        # Execute the download (with retry)
        result = retry_with_backoff(dm.download, url, manager.download_dir, lang, subtitle_choice)

        manager.state = STATE_FINISHED
        manager.put_message({
            "type": MSG_DONE,
            "filepath": result.get("filepath"),
            "title": result.get("title"),
            "subtitle_file": result.get("subtitle_file"),
            "subtitle_type": result.get("subtitle_type"),
        })

    except DownloadCancelledError:
        manager.state = STATE_FINISHED
        manager.put_message({"type": MSG_ERROR, "message": "تم إلغاء التحميل"})

    except Exception as e:
        manager.state = STATE_FINISHED
        error_msg = map_exception_to_message(e)
        logger.exception("Download failed: %s", e)
        manager.put_message({"type": MSG_ERROR, "message": error_msg})


# ── API Routes ─────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main web UI."""
    index_path = os.path.join(_template_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>DownTube - Template not found</h1>")


@app.get("/api/state", response_model=AppState)
async def get_state():
    """Get the current download state."""
    return AppState(
        state=manager.state,
        current_url=manager.current_url,
        current_title=manager.current_title,
    )


@app.post("/api/download", response_model=DownloadResponse)
async def start_download(req: DownloadRequest):
    """Start a new download."""
    if manager.state == STATE_RUNNING:
        raise HTTPException(status_code=409, detail="تحميل جاري بالفعل")

    if not validate_url(req.url):
        raise HTTPException(status_code=400, detail="رابط يوتيوب غير صالح")

    if req.lang not in SUPPORTED_LANGS:
        raise HTTPException(status_code=400, detail=f"لغة غير مدعومة: {req.lang}")

    if req.subtitle_choice not in ("yes", "no"):
        raise HTTPException(status_code=400, detail="خيار الترجمة غير صالح")

    # Reset state
    manager.reset()

    # Start download in background thread
    thread = threading.Thread(
        target=_download_worker,
        args=(req.url, req.lang, req.subtitle_choice),
        daemon=True,
    )
    thread.start()

    return DownloadResponse(
        status="started",
        message="بدأ التحميل",
    )


@app.post("/api/cancel", response_model=DownloadResponse)
async def cancel_download():
    """Cancel the current download."""
    if manager.state != STATE_RUNNING:
        raise HTTPException(status_code=409, detail="لا يوجد تحميل جاري للإلغاء")

    manager.cancel_event.set()
    return DownloadResponse(status="cancelling", message="جاري إلغاء التحميل...")


@app.get("/api/info")
async def get_video_info(url: str):
    """Get video information without downloading."""
    if not validate_url(url):
        raise HTTPException(status_code=400, detail="رابط يوتيوب غير صالح")

    try:
        dm = DownloadManager()
        info = dm.extract_info(url)
        title = info.get("title", "unknown")

        # Gather subtitle info for all supported languages
        subtitles_available = {}
        for lang_code in SUPPORTED_LANGS:
            sub_info = dm.get_available_subtitles(info, lang_code)
            if sub_info:
                subtitles_available[lang_code] = {
                    "type": sub_info[0],
                    "key": sub_info[1],
                }

        return InfoResponse(
            title=title,
            duration=info.get("duration"),
            thumbnail=info.get("thumbnail"),
            filesize_estimate=dm.estimate_filesize(info),
            subtitles_available=subtitles_available if subtitles_available else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=map_exception_to_message(e))


@app.get("/api/download-dir")
async def get_download_dir():
    """Get the current download directory."""
    return {"directory": manager.download_dir}


@app.post("/api/download-dir")
async def set_download_dir(directory: str):
    """Set the download directory."""
    if not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail="المجلد غير موجود")
    manager.download_dir = directory
    return {"directory": manager.download_dir}


@app.get("/api/languages")
async def get_languages():
    """Get supported languages."""
    return {"languages": SUPPORTED_LANGS}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time progress updates.

    The server pushes download progress, status, and log messages
    to all connected WebSocket clients.
    """
    await websocket.accept()
    manager.add_websocket(websocket)

    try:
        # Send current state immediately
        await websocket.send_json({
            "type": "state",
            "state": manager.state,
            "current_url": manager.current_url,
            "current_title": manager.current_title,
        })

        # Main loop: drain queue messages and push to WebSocket
        import asyncio
        while True:
            messages = manager.get_messages()
            for msg in messages:
                try:
                    await websocket.send_json(msg)
                except Exception:
                    break

            await asyncio.sleep(0.1)  # Poll every 100ms (QUEUE_POLL_MS)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        manager.remove_websocket(websocket)
