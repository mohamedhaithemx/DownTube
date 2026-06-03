# DownTube — نماذج Pydantic

from typing import Optional
from pydantic import BaseModel, Field


class VideoInfoRequest(BaseModel):
    """طلب جلب معلومات الفيديو."""
    url: str = Field(..., description="رابط يوتيوب")


class DownloadRequest(BaseModel):
    """طلب بدء التحميل."""
    url: str = Field(..., description="رابط يوتيوب")
    lang: str = Field(default="ar", description="لغة الترجمة")
    include_subtitle: bool = Field(default=True, description="تحميل الترجمة؟")
    cookiefile: Optional[str] = Field(default=None, description="مسار ملف الكوكيز")
    proxy: Optional[str] = Field(default=None, description="عنوان البروكسي")


class SubtitleCheckResponse(BaseModel):
    """نتيجة التحقق من الترجمة."""
    available: bool
    subtitle_type: Optional[str] = None  # "official" أو "auto"
    subtitle_key: Optional[str] = None   # مفتاح اللغة المطابق
    message: str


class VideoInfoResponse(BaseModel):
    """معلومات الفيديو."""
    title: str
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    filesize_estimate: Optional[int] = None
    subtitle_info: Optional[SubtitleCheckResponse] = None


class ProgressMessage(BaseModel):
    """رسالة تقدم التحميل عبر SSE."""
    phase: str
    phase_index: int      # 0-4
    total_phases: int = 5
    phase_percent: float = 0.0
    overall_percent: float = 0.0
    speed: Optional[float] = None       # بايت/ثانية
    eta: Optional[int] = None           # ثوانٍ
    message: str
    state: str = "running"


class DownloadResult(BaseModel):
    """نتيجة التحميل النهائية."""
    success: bool
    title: Optional[str] = None
    video_file: Optional[str] = None
    subtitle_file: Optional[str] = None
    subtitle_type: Optional[str] = None
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """رسالة خطأ."""
    error: str
    detail: Optional[str] = None
