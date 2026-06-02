"""
استراتيجيات تجنب حظر يوتيوب
Anti-Ban Strategies for YouTube Downloads
"""

import random
import time
import asyncio
from typing import Optional
import logging

from .cookie_manager import cookie_manager

logger = logging.getLogger(__name__)


# قائمة User-Agents متعددة للتدوير - مع كثير من iOS/Android لأنهم أقل حظراً
USER_AGENTS = [
    # Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.113 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.179 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.118 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.179 Mobile Safari/537.36",
    # iOS
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1",
    # Chrome - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome - macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
]


YOUTUBE_CLIENTS = ["web", "android"]


ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9,ar;q=0.8",
    "ar-SA,ar;q=0.9,en;q=0.8",
    "en-GB,en;q=0.9,ar;q=0.7",
    "fr-FR,fr;q=0.9,en;q=0.8",
    "de-DE,de;q=0.9,en;q=0.8",
    "es-ES,es;q=0.9,en;q=0.8",
]


class AntiBanManager:
    """
    مدير استراتيجيات تجنب الحظر
    يتحكم في التأخيرات والتدوير والحد الأقصى للطلبات
    """

    def __init__(self):
        self._last_request_time: float = 0
        self._request_count: int = 0
        self._session_start: float = time.time()
        self._current_user_agent: Optional[str] = None
        self._current_client: Optional[str] = None
        self._current_accept_lang: Optional[str] = None
        self._cooldown_until: float = 0
        self._failed_attempts: int = 0
        self._consecutive_429: int = 0

        self._has_cookies_cache = cookie_manager.is_active()

        # إعدادات الحد الأقصى
        self.max_requests_per_session = 50 if self._has_cookies_cache else 15
        self.max_requests_per_hour = 30 if self._has_cookies_cache else 10
        self.session_duration_limit = 7200 if self._has_cookies_cache else 3600

        # تأخيرات — بدون كوكيز نزودها، مع كوكيز نقللها
        self.min_delay = 3.0 if self._has_cookies_cache else 8.0
        self.max_delay = 6.0 if self._has_cookies_cache else 18.0
        self.subtitle_to_video_delay = 2.0 if self._has_cookies_cache else 10.0

    def _has_cookies(self) -> bool:
        """هل توجد كوكيز نشطة؟"""
        return cookie_manager.is_active()

    def get_random_user_agent(self) -> str:
        """الحصول على User-Agent عشوائي"""
        self._current_user_agent = random.choice(USER_AGENTS)
        logger.info(f"Selected User-Agent: {self._current_user_agent[:50]}...")
        return self._current_user_agent

    def get_current_user_agent(self) -> str:
        """الحصول على User-Agent الحالي"""
        if not self._current_user_agent:
            return self.get_random_user_agent()
        return self._current_user_agent

    def rotate_user_agent(self) -> str:
        """تدوير User-Agent جديد مختلف عن الحالي"""
        old_ua = self._current_user_agent
        new_ua = random.choice(USER_AGENTS)
        attempts = 0
        while new_ua == old_ua and attempts < 10:
            new_ua = random.choice(USER_AGENTS)
            attempts += 1
        self._current_user_agent = new_ua
        # مع الكوكيز: client = web (أفضل مع تسجيل الدخول)
        # بدون كوكيز: تدوير عشوائي بين web/android
        if self._has_cookies():
            self._current_client = "web"
        else:
            self._current_client = random.choice(YOUTUBE_CLIENTS)
        self._current_accept_lang = random.choice(ACCEPT_LANGUAGES)
        logger.info(
            f"Rotated: UA={new_ua[:30]}... Client={self._current_client} Lang={self._current_accept_lang[:15]}..."
        )
        return new_ua

    def get_current_client(self) -> str:
        """الحصول على YouTube Client الحالي"""
        if not self._current_client:
            self._current_client = random.choice(YOUTUBE_CLIENTS)
        return self._current_client

    def get_current_accept_lang(self) -> str:
        """الحصول على Accept-Language الحالي"""
        if not self._current_accept_lang:
            self._current_accept_lang = random.choice(ACCEPT_LANGUAGES)
        return self._current_accept_lang

    async def wait_before_request(self):
        """انتظار قبل الطلب لتجنب كشف البوت - مع تدوير UA"""
        # تدوير User-Agent قبل كل طلب
        self.rotate_user_agent()

        now = time.time()

        # التحقق من فترة التبريد
        if now < self._cooldown_until:
            wait_time = self._cooldown_until - now
            logger.info(f"In cooldown period. Waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
            self.rotate_user_agent()

        # حساب التأخير
        time_since_last = now - self._last_request_time
        delay = self._calculate_delay()

        if time_since_last < delay:
            wait_time = delay - time_since_last
            # إضافة jitter عشوائي أكبر
            jitter = random.uniform(0, 5.0)
            total_wait = wait_time + jitter
            logger.info(f"Rate limiting: waiting {total_wait:.1f}s before next request")
            await asyncio.sleep(total_wait)

        self._last_request_time = time.time()
        self._request_count += 1

    async def wait_between_subtitle_and_video(self):
        """
        انتظار بين تحميل الترجمة والفيديو
        تأخير أطول لمنع 429
        """
        base_delay = self.subtitle_to_video_delay
        jitter = random.uniform(3.0, 8.0)
        total_delay = base_delay + jitter

        logger.info(
            f"Waiting {total_delay:.1f}s between subtitle and video download "
            f"(anti-ban strategy)"
        )
        await asyncio.sleep(total_delay)
        self.rotate_user_agent()

    def _calculate_delay(self) -> float:
        """حساب التأخير بناءً على عدد الطلبات السابقة"""
        base_delay = random.uniform(self.min_delay, self.max_delay)

        # زيادة التأخير مع زيادة عدد الطلبات (بدأ من 3 مش 10)
        if self._request_count > 3:
            base_delay *= 1.5
        if self._request_count > 8:
            base_delay *= 2.0
        if self._request_count > 12:
            base_delay *= 3.0

        # زيادة التأخير بعد محاولات فاشلة
        if self._failed_attempts > 0:
            base_delay *= (1 + self._failed_attempts)

        return min(base_delay, 45.0)

    def check_session_limits(self) -> bool:
        """التحقق من حدود الجلسة"""
        now = time.time()
        session_duration = now - self._session_start

        # لو في 429 متكرر، نمنع الجلسة
        if self._consecutive_429 >= 2:
            logger.warning(f"Too many 429 errors ({self._consecutive_429}). Blocking session.")
            return False

        if self._request_count >= self.max_requests_per_session:
            logger.warning("Session request limit reached. Need cooldown.")
            return False

        if session_duration >= self.session_duration_limit:
            logger.warning("Session duration limit reached. Need cooldown.")
            return False

        return True

    def apply_cooldown(self, duration: Optional[float] = None):
        """تطبيق فترة تبريد"""
        has_cookies = self._has_cookies()
        if duration is None:
            duration = random.uniform(30, 60) if has_cookies else random.uniform(120, 300)
        self._cooldown_until = time.time() + duration
        logger.info(f"Applied cooldown for {duration:.1f}s")
        self.rotate_user_agent()

    def report_failure(self, status_code: Optional[int] = None):
        """الإبلاغ عن فشل في الطلب - مع كشف 429"""
        has_cookies = self._has_cookies()
        self._failed_attempts += 1

        if status_code == 429:
            self._consecutive_429 += 1
            logger.warning(f"HTTP 429 Too Many Requests! Total: {self._consecutive_429}")
            cooldown_time = random.uniform(10, 30) if has_cookies else random.uniform(60, 180) * self._consecutive_429
            self.apply_cooldown(cooldown_time)
        else:
            self._consecutive_429 = max(0, self._consecutive_429 - 1)
            logger.warning(f"Request failed (status={status_code}). Total failures: {self._failed_attempts}")

        max_fails = 5 if has_cookies else 2
        if self._failed_attempts >= max_fails:
            self.apply_cooldown(random.uniform(30, 60) if has_cookies else random.uniform(120, 300))
            self.rotate_user_agent()

    def report_success(self):
        """الإبلاغ عن نجاح الطلب"""
        self._failed_attempts = max(0, self._failed_attempts - 1)
        self._consecutive_429 = max(0, self._consecutive_429 - 1)

    def get_ydl_headers(self) -> dict:
        """الحصول على headers لـ yt-dlp بقيم متغيرة"""
        ua = self.get_current_user_agent()
        accept_lang = self._current_accept_lang or random.choice(ACCEPT_LANGUAGES)
        headers = {
            "User-Agent": ua,
            "Accept-Language": accept_lang,
        }
        # مع الكوكيز نضيف Origin و Referer عشان نحاكي المتصفح
        if self._has_cookies():
            headers["Origin"] = "https://www.youtube.com"
            headers["Referer"] = "https://www.youtube.com/"
        return headers

    def get_ydl_opts_additions(self) -> dict:
        """الحصول على خيارات yt-dlp إضافية لمضاد الحظر مع تبديل الـ Client"""
        client = self.get_current_client()
        has_cookies = self._has_cookies()
        logger.info(f"Using YouTube client: {client} (cookies={has_cookies})")

        opts = {
            "http_headers": self.get_ydl_headers(),
            "extractor_retries": 5,
            "file_access_retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 60,
        }

        # retry_sleep_functions أهدى مع الكوكيز
        if has_cookies:
            opts["retry_sleep_functions"] = {
                "http": lambda n: random.uniform(1, 3) * n,
                "fragment": lambda n: random.uniform(1, 2) * n,
            }
        else:
            opts["retry_sleep_functions"] = {
                "http": lambda n: random.uniform(5, 12) * n,
                "fragment": lambda n: random.uniform(3, 8) * n,
            }

        # إضافة cookiefile إذا في كوكيز
        if has_cookies:
            cookies_path = cookie_manager.get_cookies_path()
            if cookies_path:
                opts["cookiefile"] = cookies_path
                logger.info(f"Using cookies from: {cookies_path}")

        # إضافة extractor_args لاستخدام client مختلف (android أقل حظراً)
        if client == "android":
            opts["extractor_args"] = {"youtube": {"player_client": ["android", "web"]}}

        return opts

    def reset_session(self):
        """إعادة تعيين الجلسة"""
        self._request_count = 0
        self._session_start = time.time()
        self._failed_attempts = 0
        self._consecutive_429 = 0
        self._cooldown_until = 0
        self.rotate_user_agent()
        logger.info("Session reset with new User-Agent and Client")


anti_ban = AntiBanManager()
