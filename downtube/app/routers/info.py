import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException, Query

from app.services.youtube_service import extract_info, extract_info_flat, YouTubeError
from app.utils.validators import validate_youtube_url, extract_video_id, ERROR_MESSAGES
from app.utils.cache import info_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/info", tags=["info"])

MAX_DURATION_VIDEO_SUBTITLE = int(os.getenv("MAX_DURATION_VIDEO_SUBTITLE", "72000"))
MAX_DURATION_SINGLE = int(os.getenv("MAX_DURATION_SINGLE", "72000"))
BASIC_TIMEOUT = int(os.getenv("BASIC_TIMEOUT_SECONDS", "30"))
FORMATS_TIMEOUT = int(os.getenv("INFO_TIMEOUT_SECONDS", "120"))


@router.get("")
async def get_video_info(url: str = Query(..., description="رابط فيديو يوتيوب")):
    if not validate_youtube_url(url):
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES["invalid_url"])

    video_id = extract_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES["invalid_url"])

    cached = info_cache.get(video_id)
    if cached is not None:
        return cached

    try:
        basic = await asyncio.wait_for(extract_info_flat(url), timeout=BASIC_TIMEOUT)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail=ERROR_MESSAGES["basic_timeout"])
    except YouTubeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    result = _build_basic_response(basic, video_id)

    try:
        full = await asyncio.wait_for(extract_info(url), timeout=FORMATS_TIMEOUT)
        result.update(_build_formats_response(full))
    except (asyncio.TimeoutError, YouTubeError) as e:
        logger.warning("فشل جلب الصيغ للفيديو %s: %s", video_id, str(e))

    info_cache.set(video_id, result)

    return result


@router.get("/formats")
async def get_video_formats(url: str = Query(..., description="رابط فيديو يوتيوب")):
    if not validate_youtube_url(url):
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES["invalid_url"])

    video_id = extract_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES["invalid_url"])

    try:
        full = await asyncio.wait_for(extract_info(url), timeout=FORMATS_TIMEOUT)
    except asyncio.TimeoutError:
        return _empty_formats(ERROR_MESSAGES["formats_timeout"])
    except YouTubeError as e:
        return _empty_formats(e.message)

    return _build_formats_response(full)


def _build_basic_response(basic: dict, video_id: str) -> dict:
    return {
        "title": basic.get("title", "بدون عنوان"),
        "thumbnail": basic.get("thumbnail", ""),
        "duration": basic.get("duration", 0),
        "channel": basic.get("channel", basic.get("uploader", "غير معروف")),
        "channel_url": basic.get("channel_url", ""),
        "view_count": basic.get("view_count", 0),
        "video_id": video_id,
        "formats": [],
        "audio_formats": [],
        "has_arabic_subtitles": False,
        "has_auto_subtitles": False,
        "subtitle_info": {"manual": False, "auto": False},
        "formats_loaded": False,
        "max_duration_video_subtitle": MAX_DURATION_VIDEO_SUBTITLE,
        "max_duration_single": MAX_DURATION_SINGLE,
    }


def _build_formats_response(full: dict) -> dict:
    formats = []
    seen_heights = set()
    for h in (1080, 720, 480, 360):
        for f in full.get("formats", []):
            if f.get("height") == h and f.get("ext") == "mp4" and h not in seen_heights:
                seen_heights.add(h)
                formats.append({
                    "format_id": f["format_id"],
                    "label": f"{h}p",
                    "ext": "mp4",
                    "size": f.get("filesize") or f.get("filesize_approx") or 0,
                })
                break

    audio_formats = []
    for f in full.get("formats", []):
        if f.get("vcodec") == "none" and f.get("acodec") != "none":
            abr = f.get("abr", 0)
            audio_formats.append({
                "format_id": f.get("format_id"),
                "label": f"{int(abr)}kbps" if abr else "Audio",
                "ext": f.get("ext", "mp3"),
                "size": f.get("filesize") or f.get("filesize_approx") or 0,
            })
            break

    subtitle_info = []
    subtitles = full.get("subtitles", {}) or {}
    automatic = full.get("automatic_captions", {}) or {}
    has_arabic_manual = "ar" in subtitles or "ara" in subtitles
    has_arabic_auto = "ar" in automatic or "ara" in automatic

    return {
        "formats": formats[:5],
        "audio_formats": audio_formats[:3],
        "has_arabic_subtitles": has_arabic_manual,
        "has_auto_subtitles": has_arabic_auto,
        "subtitle_info": {
            "manual": has_arabic_manual,
            "auto": has_arabic_auto,
        },
        "formats_loaded": True,
    }


def _empty_formats(error_msg: str) -> dict:
    return {
        "formats": [],
        "audio_formats": [],
        "has_arabic_subtitles": False,
        "has_auto_subtitles": False,
        "subtitle_info": {"manual": False, "auto": False},
        "formats_loaded": False,
        "error": error_msg,
    }
