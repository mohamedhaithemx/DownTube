# DownTube — استراتيجيات تجنب حظر يوتيوب (Anti-Block & 429)

"""
يحتوي هذا الملف على كل استراتيجيات تجنب الحظر:
- تدوير User-Agent عشوائياً
- Exponential Backoff مع Jitter
- تأخير عشوائي بين الطلبات
- دعم الكوكيز والبروكسي
"""

import random
import time
import logging
from typing import Optional, Callable, TypeVar

from app.config import (
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_MAX,
    JITTER_MAX,
    RANDOM_DELAY_MIN,
    RANDOM_DELAY_MAX,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ── قائمة User-Agents لل تدوير ───────────────────────────────
USER_AGENTS = [
    # متصفحات Chrome على Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # متصفحات Chrome على macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # متصفحات Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # متصفحات Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    # متصفحات Safari
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # أجهزة Android
    "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    # أجهزة iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]


def get_random_user_agent() -> str:
    """إرجاع User-Agent عشوائي من القائمة."""
    return random.choice(USER_AGENTS)


def get_random_delay() -> float:
    """إرجاع تأخير عشوائي بين الطلبات لتقليل بصمة الـ Bot."""
    return random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)


def calculate_backoff(attempt: int) -> float:
    """
    حساب وقت الانتظار باستخدام Exponential Backoff مع Jitter.
    
    الصيغة: min(BASE ^ attempt + random(0, JITTER), MAX)
    """
    backoff = RETRY_BACKOFF_BASE ** attempt
    jitter = random.uniform(0, JITTER_MAX)
    return min(backoff + jitter, RETRY_BACKOFF_MAX)


def retry_with_backoff(
    func: Callable[..., T],
    *args,
    max_retries: int = MAX_RETRIES,
    should_retry: Optional[Callable[[Exception], bool]] = None,
    **kwargs,
) -> T:
    """
    إعادة محاولة الدالة مع Exponential Backoff و Jitter.
    
    المعاملات:
        func: الدالة المراد تنفيذها
        max_retries: عدد المحاولات الأقصى
        should_retry: دالة تحدد هل يجب إعادة المحاولة لهذا الخطأ
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            # تأخير عشوائي قبل الطلب
            if attempt > 0:
                delay = calculate_backoff(attempt)
                logger.warning(
                    "محاولة %d/%d بعد %.1f ثانية...",
                    attempt + 1, max_retries + 1, delay
                )
                time.sleep(delay)

            return func(*args, **kwargs)

        except Exception as e:
            last_exception = e
            error_msg = str(e).lower()

            # التحقق مما إذا كان يجب إعادة المحاولة
            is_retryable = (
                "429" in error_msg
                or "403" in error_msg
                or "too many" in error_msg
                or "rate limit" in error_msg
                or isinstance(e, (ConnectionError, TimeoutError, OSError))
            )

            if should_retry:
                is_retryable = is_retryable or should_retry(e)

            if not is_retryable or attempt >= max_retries:
                logger.error("فشل نهائي في المحاولة %d: %s", attempt + 1, e)
                raise

            logger.warning("خطأ قابل لإعادة المحاولة: %s", e)

    raise last_exception  # نوع: تجاهل


def build_ytdlp_options(
    cookiefile: Optional[str] = None,
    proxy: Optional[str] = None,
    extra_opts: Optional[dict] = None,
) -> dict:
    """
    بناء خيارات yt-dlp مع استراتيجيات Anti-Block.
    
    المعاملات:
        cookiefile: مسار ملف الكوكيز
        proxy: عنوان البروكسي
        extra_opts: خيارات إضافية
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    # تدوير User-Agent
    opts["http_headers"] = {
        "User-Agent": get_random_user_agent(),
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    }

    # الكوكيز
    if cookiefile:
        opts["cookiefile"] = cookiefile

    # البروكسي
    if proxy:
        opts["proxy"] = proxy

    # خيارات إضافية
    if extra_opts:
        opts.update(extra_opts)

    return opts
