"""
exceptions.py — Custom exception classes for DownTube.

Each exception carries a user-friendly Arabic message by default,
but callers can override with a custom message.
"""


class DownloadCancelledError(Exception):
    """Raised when the user cancels an in-progress download."""

    def __init__(self, message="تم إلغاء التحميل"):
        self.message = message
        super().__init__(self.message)


class FFmpegNotFoundError(Exception):
    """Raised when FFmpeg binary cannot be located."""

    def __init__(self, message="لم يتم العثور على FFmpeg. يرجى تثبيته أو وضعه بجانب البرنامج"):
        self.message = message
        super().__init__(self.message)


class DiskSpaceError(Exception):
    """Raised when available disk space is insufficient."""

    def __init__(self, message="مساحة التخزين غير كافية لإكمال التحميل"):
        self.message = message
        super().__init__(self.message)


class PlaylistURLError(Exception):
    """Raised when a playlist URL is provided but only single-video mode is expected."""

    def __init__(self, message="رابط قائمة تشغيل غير مدعوم في هذا الوضع. يرجى استخدام رابط فيديو واحد"):
        self.message = message
        super().__init__(self.message)


class SubtitleNotFoundError(Exception):
    """Raised when the requested subtitle language cannot be found."""

    def __init__(self, message="لم يتم العثور على الترجمة باللغة المطلوبة"):
        self.message = message
        super().__init__(self.message)
