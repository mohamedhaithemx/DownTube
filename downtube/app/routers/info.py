import logging

from fastapi import APIRouter, HTTPException, Query

from app.services.youtube_service import extract_info, YouTubeError
from app.utils.validators import validate_youtube_url, extract_video_id, ERROR_MESSAGES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/info", tags=["info"])


@router.get("")
async def get_video_info(url: str = Query(..., description="رابط فيديو يوتيوب")):
    if not validate_youtube_url(url):
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES["invalid_url"])

    video_id = extract_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES["invalid_url"])

    try:
        info = await extract_info(url)
    except YouTubeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    formats = []
    for f in info.get("formats", []):
        height = f.get("height") or 0
        ext = f.get("ext", "")
        filesize = f.get("filesize") or f.get("filesize_approx") or 0
        format_note = f.get("format_note", "")
        if height >= 1080 or (ext == "mp4" and height >= 720):
            label = f"{height}p"
            if "HDR" in format_note:
                label = f"{height}p HDR"
            formats.append({
                "format_id": f.get("format_id"),
                "label": label,
                "ext": ext,
                "size": filesize,
                "note": format_note,
            })

    audio_formats = []
    for f in info.get("formats", []):
        if f.get("vcodec") == "none" and f.get("acodec") != "none":
            abr = f.get("abr", 0)
            audio_formats.append({
                "format_id": f.get("format_id"),
                "label": f"{int(abr)}kbps" if abr else "Audio",
                "ext": f.get("ext", "mp3"),
                "size": f.get("filesize") or f.get("filesize_approx") or 0,
            })

    subtitle_info = []
    subtitles = info.get("subtitles", {}) or {}
    automatic = info.get("automatic_captions", {}) or {}
    has_arabic_manual = "ar" in subtitles or "ara" in subtitles
    has_arabic_auto = "ar" in automatic or "ara" in automatic

    return {
        "title": info.get("title", "بدون عنوان"),
        "thumbnail": info.get("thumbnail", ""),
        "duration": info.get("duration", 0),
        "channel": info.get("channel", info.get("uploader", "غير معروف")),
        "channel_url": info.get("channel_url", ""),
        "view_count": info.get("view_count", 0),
        "video_id": video_id,
        "formats": formats[:5],
        "audio_formats": audio_formats[:3],
        "has_arabic_subtitles": has_arabic_manual,
        "has_auto_subtitles": has_arabic_auto,
        "subtitle_info": {
            "manual": has_arabic_manual,
            "auto": has_arabic_auto,
        },
    }
