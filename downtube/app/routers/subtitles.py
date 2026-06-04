import os
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.services.subtitle_service import fetch_subtitles
from app.utils.file_manager import get_task_dir, generate_task_id
from app.utils.validators import validate_youtube_url, ERROR_MESSAGES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/subtitles", tags=["subtitles"])


@router.get("/download")
async def download_subtitle(
    url: str = Query(..., description="رابط فيديو يوتيوب"),
    generate: bool = Query(True, description="توليد الترجمة إذا لم تكن متوفرة"),
):
    if not validate_youtube_url(url):
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES["invalid_url"])

    task_id = generate_task_id()
    output_dir = str(get_task_dir(task_id))

    try:
        result = await fetch_subtitles(
            url=url,
            output_dir=output_dir,
            task_id=task_id,
            auto_generate=generate,
        )

        if not result.get("path") or not os.path.exists(result["path"]):
            raise HTTPException(
                status_code=404,
                detail=ERROR_MESSAGES["no_subtitle"],
            )

        return FileResponse(
            path=result["path"],
            filename=os.path.basename(result["path"]),
            media_type="application/octet-stream",
            headers={
                "X-Subtitle-Type": result.get("type", "none"),
                "X-Subtitle-Source": result.get("source", "none"),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("خطأ في تنزيل الترجمة")
        raise HTTPException(status_code=500, detail=ERROR_MESSAGES["internal_error"])
