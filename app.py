"""DownTube - Local YouTube Downloader with Arabic Subtitles.

FastAPI web application that runs locally on the user's machine.
"""

import os
import sys
import json
import asyncio
import argparse
import threading
import webbrowser
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core.downloader import DownTubeDownloader, get_downloader
from core.utils import (
    get_default_download_dir,
    check_ffmpeg,
    check_ytdlp,
    is_valid_youtube_url,
    get_system_info,
    format_size,
)

# Create FastAPI app
app = FastAPI(title="DownTube", version="1.0.0")

# Global state
_download_thread: Optional[threading.Thread] = None
_progress_events = []
_progress_lock = threading.Lock()
_downloader_instance: Optional[DownTubeDownloader] = None


def get_app_downloader() -> DownTubeDownloader:
    global _downloader_instance
    if _downloader_instance is None:
        _downloader_instance = DownTubeDownloader()
        _downloader_instance.add_progress_callback(_on_progress_update)
    return _downloader_instance


def _on_progress_update(data: dict):
    """Called when download progress updates. Pushes to SSE listeners."""
    with _progress_lock:
        _progress_events.append(data)


# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main page."""
    html_path = Path(__file__).parent / "static" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>DownTube - Static files not found</h1>")


@app.get("/api/status")
async def get_status():
    """Get system status and dependency info."""
    ffmpeg = check_ffmpeg()
    ytdlp = check_ytdlp()
    downloader = get_app_downloader()

    return JSONResponse({
        "ffmpeg": ffmpeg,
        "ytdlp": ytdlp,
        "download_dir": downloader.download_dir,
        "ready": ffmpeg["available"] and ytdlp["available"],
    })


@app.post("/api/download")
async def start_download(request: Request):
    """Start a YouTube video download."""
    global _download_thread

    body = await request.json()
    url = body.get("url", "").strip()
    download_dir = body.get("download_dir", "").strip()

    if not url:
        return JSONResponse({"error": "يرجى إدخال رابط الفيديو"}, status_code=400)

    if not is_valid_youtube_url(url):
        return JSONResponse({"error": "رابط يوتيوب غير صالح"}, status_code=400)

    downloader = get_app_downloader()
    if download_dir:
        downloader.download_dir = download_dir
        Path(download_dir).mkdir(parents=True, exist_ok=True)

    # Check if already downloading
    if _download_thread and _download_thread.is_alive():
        return JSONResponse({"error": "يوجد تحميل قيد التشغيل بالفعل"}, status_code=409)

    # Start download in background thread
    _download_thread = threading.Thread(
        target=downloader.download,
        args=(url,),
        daemon=True
    )
    _download_thread.start()

    return JSONResponse({"status": "started", "message": "بدأ التحميل..."})


@app.get("/api/progress")
async def stream_progress():
    """Stream download progress via Server-Sent Events (SSE)."""
    async def event_generator():
        last_index = 0
        while True:
            # Check for new progress events
            with _progress_lock:
                new_events = _progress_events[last_index:]
                last_index = len(_progress_events)

            for event_data in new_events:
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                # If download is complete or errored, send final event and stop
                if event_data.get("status") in ("complete", "error"):
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/cancel")
async def cancel_download():
    """Cancel the current download."""
    downloader = get_app_downloader()
    downloader.cancel()
    return JSONResponse({"status": "cancelled", "message": "تم إلغاء التحميل"})


@app.post("/api/info")
async def get_video_info(request: Request):
    """Get video info without downloading."""
    body = await request.json()
    url = body.get("url", "").strip()

    if not url:
        return JSONResponse({"error": "يرجى إدخال رابط الفيديو"}, status_code=400)

    downloader = get_app_downloader()
    info = downloader.get_video_info(url)

    if "error" in info:
        return JSONResponse({"error": info["error"]}, status_code=400)

    return JSONResponse(info)


@app.get("/api/downloads")
async def list_downloads():
    """List downloaded files."""
    downloader = get_app_downloader()
    download_path = Path(downloader.download_dir)

    files = []
    if download_path.exists():
        for f in sorted(download_path.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file() and f.suffix in ('.mkv', '.mp4', '.webm', '.srt', '.vtt'):
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "size": format_size(stat.st_size),
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": "video" if f.suffix in ('.mkv', '.mp4', '.webm') else "subtitle",
                    "path": str(f),
                })

    return JSONResponse({"files": files, "download_dir": downloader.download_dir})


@app.post("/api/download-dir")
async def set_download_dir(request: Request):
    """Set the download directory."""
    body = await request.json()
    download_dir = body.get("download_dir", "").strip()

    if not download_dir:
        return JSONResponse({"error": "يرجى إدخال مسار صالح"}, status_code=400)

    try:
        Path(download_dir).mkdir(parents=True, exist_ok=True)
        downloader = get_app_downloader()
        downloader.download_dir = download_dir
        return JSONResponse({"status": "ok", "download_dir": download_dir})
    except Exception as e:
        return JSONResponse({"error": f"خطأ في إنشاء المجلد: {str(e)}"}, status_code=400)


def run_cli(url: str, download_dir: Optional[str] = None):
    """Run in CLI mode - download a video directly from command line."""
    print("=" * 60)
    print("  DownTube - تحميل فيديوهات يوتيوب مع ترجمات عربية")
    print("=" * 60)
    print()

    # Check dependencies
    ffmpeg_info = check_ffmpeg()
    ytdlp_info = check_ytdlp()

    if not ffmpeg_info["available"]:
        print("❌ ffmpeg غير مثبت! يرجى تثبيته أولاً")
        print("   sudo apt install ffmpeg  (Ubuntu/Debian)")
        print("   brew install ffmpeg       (macOS)")
        return 1

    print(f"✅ ffmpeg: {ffmpeg_info.get('version', 'OK')}")
    print(f"✅ yt-dlp: {ytdlp_info.get('version', 'OK')}")
    print()

    if not is_valid_youtube_url(url):
        print(f"❌ رابط غير صالح: {url}")
        return 1

    print(f"🔗 الرابط: {url}")
    print(f"📁 مجلد التحميل: {download_dir or get_default_download_dir()}")
    print()

    # Create downloader
    downloader = DownTubeDownloader(download_dir)

    def on_progress(data):
        status = data.get("status", "")
        percent = data.get("progress_percent", 0)
        speed = data.get("speed", "--")
        eta = data.get("eta", "--")
        stage = data.get("stage", "")

        # Clear line and print progress
        print(f"\r  [{percent:5.1f}%] {stage} | السرعة: {speed} | المتبقي: {eta}", end="", flush=True)

        if status in ("complete", "error"):
            print()  # New line

    downloader.add_progress_callback(on_progress)

    # Run download
    result = downloader.download(url)

    print()
    if result["status"] == "complete":
        print("✅ اكتمل التحميل بنجاح!")
        if result.get("video_path"):
            print(f"   الفيديو: {result['video_path']}")
        if result.get("subtitle_path"):
            print(f"   الترجمة: {result['subtitle_path']}")
        print(f"   الترجمة: {result.get('subtitle_info', '')}")
        return 0
    else:
        print(f"❌ فشل التحميل: {result.get('error', 'خطأ غير معروف')}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="DownTube - تحميل فيديوهات يوتيوب مع ترجمات عربية"
    )
    parser.add_argument(
        "--cli",
        metavar="URL",
        help="تشغيل في وضع سطر الأوامر مع رابط الفيديو"
    )
    parser.add_argument(
        "--output", "-o",
        metavar="DIR",
        help="مجلد التحميل"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8555,
        help="منفذ الخادم (الافتراضي: 8555)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="عدم فتح المتصفح تلقائياً"
    )

    args = parser.parse_args()

    # CLI mode
    if args.cli:
        sys.exit(run_cli(args.cli, args.output))

    # Web mode
    import uvicorn

    port = args.port

    # Check dependencies
    ffmpeg_info = check_ffmpeg()
    ytdlp_info = check_ytdlp()

    print("=" * 60)
    print("  DownTube - تحميل فيديوهات يوتيوب مع ترجمات عربية")
    print("=" * 60)
    print()

    if not ffmpeg_info["available"]:
        print("⚠️  تحذير: ffmpeg غير مثبت! لن تتمكن من دمج الترجمة")
        print("   ثبته من: sudo apt install ffmpeg")
    else:
        print(f"✅ ffmpeg: {ffmpeg_info.get('version', 'OK')}")

    if not ytdlp_info["available"]:
        print("⚠️  تحذير: yt-dlp غير مثبت!")
    else:
        print(f"✅ yt-dlp: {ytdlp_info.get('version', 'OK')}")

    print()
    print(f"🌐 الخادم يعمل على: http://localhost:{port}")
    print(f"📁 مجلد التحميل: {get_app_downloader().download_dir}")
    print()
    print("اضغط Ctrl+C لإيقاف الخادم")
    print()

    # Auto-open browser
    if not args.no_browser:
        def open_browser():
            import time
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=open_browser, daemon=True).start()

    # Start server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
