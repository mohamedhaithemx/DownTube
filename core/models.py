"""
نماذج البيانات للـ API
"""

from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from enum import Enum


class SubtitleFormat(str, Enum):
    srt = "srt"
    vtt = "vtt"


class VideoQuality(str, Enum):
    best = "best"
    medium = "medium"
    low = "low"


class SubtitleLanguage(str, Enum):
    ar = "ar"
    en = "en"


class DownloadRequest(BaseModel):
    """طلب التحميل"""
    url: str
    subtitle_lang: SubtitleLanguage = SubtitleLanguage.ar
    subtitle_format: SubtitleFormat = SubtitleFormat.srt
    quality: VideoQuality = VideoQuality.best
    auto_subtitle: bool = True


class VideoInfoResponse(BaseModel):
    """استجابة معلومات الفيديو"""
    title: str
    video_id: str
    duration: int
    thumbnail: str
    uploader: str
    available_subtitles: List[dict]
    description: str = ""


class ProgressResponse(BaseModel):
    """استجابة التقدم"""
    status: str
    percent: float
    speed: str = ""
    eta: str = ""
    message: str
    filename: str = ""
