import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import yt_dlp

from app.utils.validators import ERROR_MESSAGES

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

YDL_OPTS_BASE = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "extract_flat": False,
    "user_agent": USER_AGENT,
    "retries": 3,
    "fragment_retries": 3,
    "socket_timeout": 30,
}

YDL_RETRIES = 3
YDL_DELAY = 3


class YouTubeError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


def _map_ydl_error(err_msg: str) -> str:
    err_lower = err_msg.lower()
    if "private video" in err_lower or "private" in err_lower:
        return ERROR_MESSAGES["private"]
    if "video unavailable" in err_lower or "deleted" in err_lower:
        return ERROR_MESSAGES["unavailable"]
    if "age" in err_lower or "restricted" in err_lower:
        return ERROR_MESSAGES["age_restricted"]
    if "geo" in err_lower or "geo-restricted" in err_lower or "not available in your country" in err_lower:
        return ERROR_MESSAGES["geo_restricted"]
    if "timeout" in err_lower or "timed out" in err_lower:
        return ERROR_MESSAGES["timeout"]
    if "not found" in err_lower or "404" in err_lower:
        return ERROR_MESSAGES["not_found"]
    return ERROR_MESSAGES["download_failed"]


async def extract_info(url: str) -> dict[str, Any]:
    def _sync_extract():
        opts = {**YDL_OPTS_BASE}
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    for attempt in range(YDL_RETRIES):
        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(_executor, _sync_extract)
            return info
        except yt_dlp.utils.DownloadError as e:
            err_msg = str(e)
            if attempt < YDL_RETRIES - 1:
                logger.warning("محاولة %d/%d فشلت: %s", attempt + 1, YDL_RETRIES, err_msg)
                await asyncio.sleep(YDL_DELAY * (attempt + 1))
                continue
            raise YouTubeError(_map_ydl_error(err_msg), status_code=403 if "private" in err_msg.lower() else 404)
        except Exception as e:
            logger.exception("خطأ غير متوقع في extract_info")
            raise YouTubeError(ERROR_MESSAGES["internal_error"], status_code=500)

    raise YouTubeError(ERROR_MESSAGES["timeout"], status_code=408)


async def download_video(
    url: str,
    output_dir: str,
    format_id: str = "best",
    progress_callback: callable = None,
    cancel_event: asyncio.Event = None,
) -> str:
    def progress_hook(d: dict):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = (downloaded / total) * 100
                speed = d.get("speed", 0) or 0
                eta = d.get("eta", 0) or 0
                if progress_callback:
                    progress_callback(pct, speed, eta)
        elif d.get("status") == "finished":
            if progress_callback:
                progress_callback(100, 0, 0)

    def _sync_download():
        if format_id == "audio-only":
            fmt = "bestaudio/best"
        elif not any(c in format_id for c in "+/|,"):
            fmt = f"{format_id}+bestaudio[ext=m4a]/bestaudio/best[ext=mp4]/best"
        else:
            fmt = format_id
        postprocessors = []
        if format_id == "audio-only":
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            })
        else:
            postprocessors.append({
                "key": "FFmpegAudioConvertor",
                "preferredcodec": "aac",
                "preferredquality": "192",
            })
        opts = {
            **YDL_OPTS_BASE,
            "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
            "format": fmt,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
            "postprocessors": postprocessors,
        }
        if cancel_event:
            opts["nooverwrites"] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
            for f in sorted(os.listdir(output_dir), key=lambda x: os.path.getmtime(os.path.join(output_dir, x)), reverse=True):
                if f.endswith((".mp4", ".mkv", ".webm", ".avi", ".mov")):
                    return os.path.join(output_dir, f)
            return os.path.join(output_dir, "output.mp4")

    for attempt in range(YDL_RETRIES):
        try:
            loop = asyncio.get_event_loop()
            filename = await loop.run_in_executor(_executor, _sync_download)
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError()
            return filename
        except asyncio.CancelledError:
            raise
        except yt_dlp.utils.DownloadError as e:
            if attempt < YDL_RETRIES - 1:
                logger.warning("محاولة تحميل %d/%d فشلت", attempt + 1, YDL_RETRIES)
                await asyncio.sleep(YDL_DELAY * (attempt + 1))
                continue
            raise YouTubeError(_map_ydl_error(str(e)), status_code=400)
        except Exception as e:
            if isinstance(e, YouTubeError):
                raise
            logger.exception("خطأ في تحميل الفيديو")
            raise YouTubeError(ERROR_MESSAGES["download_failed"], status_code=500)

    raise YouTubeError(ERROR_MESSAGES["timeout"], status_code=408)


async def download_audio(
    url: str,
    output_dir: str,
    progress_callback: callable = None,
) -> str:
    def progress_hook(d: dict):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = (downloaded / total) * 100
                speed = d.get("speed", 0) or 0
                eta = d.get("eta", 0) or 0
                if progress_callback:
                    progress_callback(pct, speed, eta)
        elif d.get("status") == "finished":
            if progress_callback:
                progress_callback(100, 0, 0)

    def _sync_dl():
        opts = {
            **YDL_OPTS_BASE,
            "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "progress_hooks": [progress_hook],
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename.rsplit(".", 1)[0] + ".mp3"

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _sync_dl)
