# DownTube — الاستثناءات المخصصة


class DownTubeError(Exception):
    """الاستثناء الأساسي للتطبيق."""
    pass


class InvalidURLError(DownTubeError):
    """رابط يوتيوب غير صالح."""

    def __init__(self, url: str = ""):
        self.url = url
        super().__init__(f"رابط يوتيوب غير صالح: {url}")


class SubtitleNotFoundError(DownTubeError):
    """لم يتم العثور على ترجمة عربية."""

    def __init__(self, lang: str = "ar"):
        self.lang = lang
        super().__init__(f"لا توجد ترجمة باللغة: {lang}")


class VideoUnavailableError(DownTubeError):
    """الفيديو غير متاح أو محظور."""

    def __init__(self, reason: str = ""):
        self.reason = reason
        super().__init__(f"الفيديو غير متاح: {reason}")


class RateLimitExceededError(DownTubeError):
    """تم تجاوز حد الطلبات."""

    def __init__(self):
        super().__init__("تم تجاوز حد الطلبات. حاول مرة أخرى بعد قليل")


class DownloadCancelledError(DownTubeError):
    """تم إلغاء التحميل."""

    def __init__(self):
        super().__init__("تم إلغاء التحميل")


class FFmpegNotFoundError(DownTubeError):
    """لم يتم العثور على FFmpeg."""

    def __init__(self):
        super().__init__("لم يتم العثور على FFmpeg. يرجى تثبيته")
