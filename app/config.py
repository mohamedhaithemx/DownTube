# DownTube — تحميل فيديوهات يوتيوب مع الترجمة العربية

"""
ملف الإعدادات الرئيسي — يحتوي على كل الثوابت والإعدادات
"""

import os

# ── مجلد التنزيل الافتراضي ──────────────────────────────────
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "DownTube")

# ── إعدادات الخادم ───────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 9999

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
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 3       # ثوانٍ — الأساس للـ exponential backoff
RETRY_BACKOFF_MAX = 60       # حد أقصى للانتظار
JITTER_MAX = 3               # ثوانٍ — jitter عشوائي

# ── Rate Limiting ─────────────────────────────────────────────
RATE_LIMIT_REQUESTS = 10     # عدد الطلبات المسموحة
RATE_LIMIT_PERIOD = 60       # بالثواني (دقيقة واحدة)

# ── تأخير عشوائي بين الطلبات ────────────────────────────────
RANDOM_DELAY_MIN = 2.0       # ثانية
RANDOM_DELAY_MAX = 5.0       # ثانية

# ── تأخير بين المراحل (لمنع حظر يوتيوب) ────────────────────
INTER_PHASE_DELAY_MIN = 4.0  # ثواني — delay بين extract_info والتحميل
INTER_PHASE_DELAY_MAX = 8.0  # ثواني
PRE_DOWNLOAD_DELAY_MIN = 3.0 # ثواني — delay قبل yt-dlp download
PRE_DOWNLOAD_DELAY_MAX = 6.0 # ثواني

# ── إعدادات Whisper (لتوليد الترجمة بالذكاء الاصطناعي) ────
WHISPER_MODEL_SIZE = "tiny"              # tiny, base, small, medium, large
WHISPER_DEVICE = "cpu"                   # cpu أو cuda
WHISPER_COMPUTE_TYPE = "int8"            # int8, float16, float32
MAX_VIDEO_DURATION_FOR_WHISPER = 900     # 15 دقيقة (بالثواني)

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
