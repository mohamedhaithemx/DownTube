# DownTube — تحميل فيديوهات يوتيوب مع الترجمة العربية

"""
ملف الإعدادات الرئيسي — يحتوي على كل الثوابت والإعدادات
"""

import os

# ── مجلد التنزيل الافتراضي ──────────────────────────────────
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "DownTube")

# ── إعدادات الخادم ───────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 8554

# ── اللغات المدعومة ──────────────────────────────────────────
SUPPORTED_LANGS = {
    "ar": "العربية",
    "en": "English",
}

# ── صيغ الترجمة ──────────────────────────────────────────────
SUBTITLE_FORMATS = ["srt", "vtt"]
SUBTITLE_PREFERRED_FORMAT = "srt"

# ── حدود وأرقام ──────────────────────────────────────────────
MAX_TITLE_LENGTH = 100
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2       # ثوانٍ — الأساس للـ exponential backoff
RETRY_BACKOFF_MAX = 30       # حد أقصى للانتظار
JITTER_MAX = 2               # ثوانٍ — jitter عشوائي

# ── Rate Limiting ─────────────────────────────────────────────
RATE_LIMIT_REQUESTS = 10     # عدد الطلبات المسموحة
RATE_LIMIT_PERIOD = 60       # بالثواني (دقيقة واحدة)

# ── تأخير عشوائي بين الطلبات ────────────────────────────────
RANDOM_DELAY_MIN = 0.5       # ثانية
RANDOM_DELAY_MAX = 2.0       # ثانية

# ── أنماط روابط يوتيوب الصحيحة ──────────────────────────────
VALID_URL_PATTERNS = [
    r"https?://(www\.)?youtube\.com/watch\?v=[\w-]{11}",
    r"https?://(www\.)?youtube\.com/shorts/[\w-]{11}",
    r"https?://youtu\.be/[\w-]{11}",
]

# ── مراحل التحميل ────────────────────────────────────────────
PHASE_FETCH_INFO = "جلب معلومات الفيديو"
PHASE_CHECK_SUBTITLE = "التحقق من الترجمة"
PHASE_DOWNLOAD_VIDEO = "تنزيل الفيديو"
PHASE_DOWNLOAD_SUBTITLE = "تنزيل الترجمة"
PHASE_PROCESSING = "المعالجة النهائية"

# ── رسائل الحالة ─────────────────────────────────────────────
STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_FINISHED = "finished"
STATE_ERROR = "error"
