import re

YOUTUBE_URL_PATTERNS = [
    r"^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]{11}",
    r"^https?://youtu\.be/[\w-]{11}",
    r"^https?://(?:www\.)?youtube\.com/shorts/[\w-]{11}",
    r"^https?://(?:www\.)?youtube\.com/embed/[\w-]{11}",
    r"^https?://(?:www\.)?youtube\.com/watch\?v=[\w-]{11}&",
    r"^https?://m\.youtube\.com/watch\?v=[\w-]{11}",
]

YOUTUBE_URL_REGEX = re.compile(
    r"^(https?://)?(www\.|m\.)?"
    r"(youtube\.com|youtu\.be)"
    r"(/(watch\?v=|shorts/|embed/)|/)?"
    r"[\w-]{11}"
    r"([&\w=%-?]*)?$"
)

SUPPORTED_LANGS = {"ar": "العربية", "en": "English"}


def validate_youtube_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    return bool(YOUTUBE_URL_REGEX.match(url))


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{11})",
        r"^([\w-]{11})$",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def validate_lang(lang: str) -> bool:
    return lang in SUPPORTED_LANGS


ERROR_MESSAGES: dict[str, str] = {
    "invalid_url": "رابط يوتيوب غير صالح. يرجى إدخال رابط فيديو يوتيوب صحيح.",
    "private": "هذا الفيديو خاص ولا يمكن تحميله.",
    "unavailable": "الفيديو غير متاح أو محذوف.",
    "age_restricted": "هذا الفيديو مقيد بالسن ولا يمكن تحميله.",
    "geo_restricted": "هذا الفيديو غير متاح في منطقتك.",
    "timeout": "انتهت مهلة الاتصال، يرجى المحاولة مجدداً.",
    "not_found": "لم يتم العثور على الفيديو.",
    "no_subtitle": "لا توجد ترجمة عربية متاحة لهذا الفيديو.",
    "groq_no_key": "يرجى إضافة GROQ_API_KEY في ملف .env للحصول على الترجمة التلقائية.",
    "groq_rate_limit": "تم تجاوز حد الاستخدام المجاني من Groq، يرجى المحاولة لاحقاً.",
    "groq_file_too_large": "ملف الصوت كبير جداً، جاري التقسيم والمعالجة...",
    "duration_exceeded": "مدة الفيديو تتجاوز {max_hours} ساعات. يرجى اختيار فيديو أقصر.",
    "basic_timeout": "تعذر جلب المعلومات الأساسية للفيديو. حاول مرة أخرى.",
    "formats_timeout": "تعذر جلب خيارات الجودة. سيتم استخدام الجودة الافتراضية.",
    "info_timeout": "انتهت مهلة جلب معلومات الفيديو. الفيديو قد يكون طويلاً جداً أو أن الخادم مشغول.",
    "ffmpeg_error": "خطأ في معالجة الفيديو.",
    "internal_error": "حدث خطأ داخلي. يرجى المحاولة مرة أخرى.",
    "download_failed": "فشل تحميل الفيديو.",
}
