# DownTube — مسار جلب معلومات الفيديو

"""
يحتوي على نقطة نهاية جلب معلومات الفيديو
والتحقق من وجود الترجمة العربية.
"""

import re
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models import VideoInfoRequest, VideoInfoResponse, SubtitleCheckResponse, ErrorResponse
from app.config import VALID_URL_PATTERNS, SUPPORTED_LANGS
from app.exceptions import InvalidURLError, VideoUnavailableError
from app.services.downloader import download_service
from app.services.subtitle import check_subtitles

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["معلومات الفيديو"])


def validate_youtube_url(url: str) -> bool:
    """التحقق من أن الرابط هو رابط يوتيوب صالح."""
    for pattern in VALID_URL_PATTERNS:
        if re.match(pattern, url):
            return True
    return False


@router.post(
    "/info",
    response_model=VideoInfoResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="جلب معلومات الفيديو",
)
async def get_video_info(request: VideoInfoRequest):
    """
    جلب معلومات فيديو يوتيوب بدون تحميل.
    
    يتضمن: العنوان، المدة، الصورة المصغرة، وحالة الترجمة العربية.
    """
    # التحقق من الرابط
    if not validate_youtube_url(request.url):
        raise HTTPException(status_code=400, detail="رابط يوتيوب غير صالح")

    try:
        info = download_service.extract_info(request.url)

        # التحقق من الترجمة
        subtitle_data = check_subtitles(info, "ar")
        subtitle_info = None

        if subtitle_data:
            subtitle_info = SubtitleCheckResponse(
                available=True,
                subtitle_type=subtitle_data["type"],
                subtitle_key=subtitle_data["key"],
                message=f"ترجمة {'رسمية' if subtitle_data['type'] == 'official' else 'تلقائية'} متاحة",
            )
        else:
            subtitle_info = SubtitleCheckResponse(
                available=False,
                message="لا توجد ترجمة عربية",
            )

        # تقدير حجم الملف
        filesize = info.get("filesize") or info.get("filesize_approx")
        if not filesize and info.get("duration"):
            formats = info.get("formats", [])
            best_tbr = max((f.get("tbr") or 0 for f in formats), default=0)
            if best_tbr:
                filesize = int(best_tbr * 1000 / 8 * info["duration"])

        return VideoInfoResponse(
            title=info.get("title", "بدون عنوان")[:100],
            duration=info.get("duration"),
            thumbnail=info.get("thumbnail"),
            filesize_estimate=int(filesize) if filesize else None,
            subtitle_info=subtitle_info,
        )

    except InvalidURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("فشل جلب المعلومات: %s", e)
        error_msg = str(e).lower()
        if "private" in error_msg:
            detail = "هذا الفيديو خاص"
        elif "unavailable" in error_msg:
            detail = "الفيديو غير متاح"
        elif "429" in error_msg:
            detail = "تم حظر الطلبات مؤقتاً"
        else:
            detail = f"فشل جلب المعلومات: {str(e)[:150]}"
        raise HTTPException(status_code=500, detail=detail)
