"""
نسخة الكمبيوتر - خادم FastAPI مع واجهة ويب
Desktop Version - FastAPI Server with Web UI
"""

import os
import sys
import json
import asyncio
import logging
import tempfile
from typing import Optional

# إضافة مسار النواة المشتركة
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from core.downloader import YouTubeDownloader, DownloadStatus
from core.models import DownloadRequest, SubtitleFormat, SubtitleLanguage, VideoQuality
from core.anti_ban import anti_ban
from core.cookie_manager import cookie_manager

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="YouTube Downloader - Desktop",
    description="تطبيق تحميل فيديوهات يوتيوب مع الترجمات",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# مجلد التحميل
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "YouTube_Downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# محمل الفيديو
downloader = YouTubeDownloader(download_dir=DOWNLOAD_DIR)

# اتصال WebSocket
ws_connections: list = []


@app.get("/")
async def index():
    """الصفحة الرئيسية"""
    return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))


@app.get("/api/health")
async def health():
    """فحص حالة الخادم"""
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/video/info")
async def get_video_info(url: str):
    """جلب معلومات الفيديو"""
    try:
        info = await downloader.fetch_video_info(url)
        return {
            "title": info.title,
            "video_id": info.video_id,
            "duration": info.duration,
            "thumbnail": info.thumbnail,
            "uploader": info.uploader,
            "view_count": info.view_count,
            "description": info.description,
            "available_subtitles": [
                {
                    "language": sub.language,
                    "language_code": sub.language_code,
                    "auto_generated": sub.auto_generated,
                }
                for sub in info.available_subtitles
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/download")
async def start_download(request: DownloadRequest):
    """بدء التحميل الكامل (ترجمة + فيديو)"""
    try:
        # التحقق من حدود الجلسة
        if not anti_ban.check_session_limits():
            raise HTTPException(
                status_code=429,
                detail="تم تجاوز حد الطلبات. يرجى الانتظار قبل المحاولة مرة أخرى."
            )

        # بدء التحميل في الخلفية
        asyncio.create_task(_download_task(request))

        return {"status": "started", "message": "بدأ التحميل..."}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _download_task(request: DownloadRequest):
    """مهمة التحميل في الخلفية"""
    try:
        results = await downloader.download_full(
            url=request.url,
            subtitle_lang=request.subtitle_lang.value,
            subtitle_format=request.subtitle_format.value,
            quality=request.quality.value,
            auto_subtitle=request.auto_subtitle,
        )

        # إرسال إشعار عبر WebSocket
        await _broadcast_ws({
            "type": "download_complete",
            "video": results.get("video"),
            "subtitle": results.get("subtitle"),
        })

    except Exception as e:
        await _broadcast_ws({
            "type": "download_error",
            "error": str(e),
        })


@app.post("/api/download/subtitle")
async def download_subtitle_only(
    url: str,
    lang: SubtitleLanguage = SubtitleLanguage.ar,
    format: SubtitleFormat = SubtitleFormat.srt,
    auto: bool = True,
):
    """تحميل الترجمة فقط"""
    try:
        subtitle_file = await downloader.download_subtitle(
            url=url,
            language_code=lang.value,
            subtitle_format=format.value,
            auto_generated=auto,
        )

        if subtitle_file:
            return {
                "status": "completed",
                "file": subtitle_file,
                "message": "تم تحميل الترجمة بنجاح"
            }
        else:
            raise HTTPException(status_code=404, detail="لم يتم العثور على ترجمة باللغة المطلوبة")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/download/video")
async def download_video_only(url: str, quality: VideoQuality = VideoQuality.best):
    """تحميل الفيديو فقط"""
    try:
        video_file = await downloader.download_video(url=url, quality=quality.value)

        if video_file:
            return {
                "status": "completed",
                "file": video_file,
                "message": "تم تحميل الفيديو بنجاح"
            }
        else:
            raise HTTPException(status_code=400, detail="فشل تحميل الفيديو")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cancel")
async def cancel_download():
    """إلغاء التحميل الحالي"""
    downloader.cancel_download()
    return {"status": "cancelled", "message": "تم إلغاء التحميل"}


@app.get("/api/progress")
async def get_progress():
    """جلب حالة التقدم الحالية"""
    p = downloader.progress
    return {
        "status": p.status.value,
        "percent": p.percent,
        "speed": p.speed,
        "eta": p.eta,
        "message": p.message,
        "filename": p.filename,
    }


@app.get("/api/downloads")
async def list_downloads():
    """عرض الملفات المحملة"""
    files = []
    for filename in os.listdir(DOWNLOAD_DIR):
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.isfile(filepath):
            stat = os.stat(filepath)
            files.append({
                "name": filename,
                "path": filepath,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "type": "video" if filename.endswith(('.mp4', '.mkv', '.webm')) else "subtitle",
            })

    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"files": files, "download_dir": DOWNLOAD_DIR}


@app.get("/api/download/file")
async def download_file(path: str):
    """تحميل ملف (فتح نافذة حفظ باسم)"""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="الملف غير موجود")

    return FileResponse(
        path=path,
        filename=os.path.basename(path),
        media_type="application/octet-stream",
    )


@app.delete("/api/download/file")
async def delete_file(path: str):
    """حذف ملف"""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="الملف غير موجود")

    os.remove(path)
    return {"status": "deleted", "message": "تم حذف الملف"}


@app.get("/api/anti-ban/status")
async def anti_ban_status():
    """حالة مضاد الحظر"""
    cookies_info = cookie_manager.get_info()
    return {
        "request_count": anti_ban._request_count,
        "failed_attempts": anti_ban._failed_attempts,
        "session_active": anti_ban.check_session_limits(),
        "current_user_agent": anti_ban.get_current_user_agent()[:50] + "...",
        "current_client": anti_ban.get_current_client(),
        "current_accept_lang": anti_ban.get_current_accept_lang()[:20] + "...",
        "cookies": {
            "active": cookies_info.get("active", False),
            "size": cookies_info.get("size", 0),
            "lines": cookies_info.get("lines", 0),
            "has_youtube": cookies_info.get("has_youtube", False),
        },
    }


@app.post("/api/anti-ban/reset")
async def reset_anti_ban():
    """إعادة تعيين مضاد الحظر"""
    anti_ban.reset_session()
    return {"status": "reset", "message": "تم إعادة تعيين الجلسة"}


@app.post("/api/cookies/set")
async def set_cookies(data: dict):
    """حفظ الكوكيز عن طريق لصق المحتوى"""
    content = data.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="المحتوى فارغ")

    success = cookie_manager.set_cookies(content)
    if success:
        return {"status": "ok", "message": "تم حفظ الكوكيز بنجاح", "info": cookie_manager.get_info()}
    raise HTTPException(status_code=400, detail="فشل حفظ الكوكيز. تأكد من أن الملف يحتوي على كوكيز يوتيوب")


@app.post("/api/cookies/upload")
async def upload_cookies_file(file: UploadFile = File(...)):
    """رفع ملف الكوكيز"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="لم يتم اختيار ملف")

    content = await file.read()
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        text = content.decode('latin-1')

    success = cookie_manager.upload_cookies(text)
    if success:
        return {"status": "ok", "message": "تم رفع الكوكيز بنجاح", "info": cookie_manager.get_info()}
    raise HTTPException(status_code=400, detail="فشل حفظ الكوكيز. تأكد من أن الملف يحتوي على كوكيز يوتيوب")


@app.get("/api/cookies/status")
async def cookies_status():
    """حالة الكوكيز الحالية"""
    return cookie_manager.get_info()


@app.delete("/api/cookies/remove")
async def remove_cookies():
    """حذف الكوكيز"""
    success = cookie_manager.clear()
    if success:
        return {"status": "ok", "message": "تم حذف الكوكيز"}
    raise HTTPException(status_code=400, detail="فشل حذف الكوكيز")


# WebSocket للتحديثات اللحظية
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_connections.append(websocket)

    # تعيين callback للتقدم
    def on_progress(progress):
        asyncio.create_task(_send_progress_ws(websocket, progress))

    downloader.set_progress_callback(on_progress)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        ws_connections.remove(websocket)
        downloader.set_progress_callback(None)


async def _send_progress_ws(websocket: WebSocket, progress):
    """إرسال تقدم التحميل عبر WebSocket"""
    try:
        await websocket.send_json({
            "type": "progress",
            "status": progress.status.value,
            "percent": progress.percent,
            "speed": progress.speed,
            "eta": progress.eta,
            "message": progress.message,
            "filename": progress.filename,
        })
    except Exception:
        pass


async def _broadcast_ws(data: dict):
    """بث رسالة لجميع اتصالات WebSocket"""
    for ws in ws_connections[:]:
        try:
            await ws.send_json(data)
        except Exception:
            ws_connections.remove(ws)


# خدمة الملفات الثابتة
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


def main():
    """تشغيل الخادم"""
    import uvicorn
    print("=" * 60)
    print("  YouTube Downloader - Desktop Version")
    print("  تحميل فيديوهات يوتيوب مع الترجمات")
    print("=" * 60)
    print(f"\n  Download Directory: {DOWNLOAD_DIR}")
    print(f"  Server: http://localhost:8555")
    print(f"\n  Open your browser and go to: http://localhost:8555")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8555, log_level="info")


if __name__ == "__main__":
    main()
