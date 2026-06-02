"""
مدير ملفات الكوكيز
YouTube Cookies Manager - رفع/لصق/حذف كوكيز يوتيوب
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

COOKIES_DIR = os.path.join(os.path.expanduser("~"), ".yt-dlp", "cookies")
COOKIES_FILE = os.path.join(COOKIES_DIR, "youtube_cookies.txt")


class CookieManager:
    """إدارة كوكيز يوتيوب لرفع حد الـ 429"""

    def __init__(self):
        self._cookies_path: Optional[str] = None
        os.makedirs(COOKIES_DIR, exist_ok=True)

    def set_cookies(self, content: str) -> bool:
        """حفظ الكوكيز عن طريق لصق المحتوى"""
        if not content or not content.strip():
            logger.warning("المحتوى فارغ")
            return False

        # فحص إذا المحتوى يحتوي على كوكيز يوتيوب (بأي صيغة)
        has_youtube = False
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                continue
            if '.youtube.com' in line or 'youtube.com' in line:
                has_youtube = True
                break

        if not has_youtube:
            logger.warning("المحتوى لا يحتوي على كوكيز يوتيوب")
            return False

        try:
            with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
                f.write(content)
            self._cookies_path = COOKIES_FILE
            logger.info(f"تم حفظ الكوكيز (لصق) في {COOKIES_FILE}")
            return True
        except Exception as e:
            logger.error(f"فشل حفظ الكوكيز: {e}")
            return False

    def upload_cookies(self, file_content: str) -> bool:
        """حفظ الكوكيز عن طريق رفع ملف"""
        return self.set_cookies(file_content)

    def get_cookies_path(self) -> Optional[str]:
        """المسار الحالي لملف الكوكيز"""
        if self._cookies_path and os.path.exists(self._cookies_path):
            return self._cookies_path
        if os.path.exists(COOKIES_FILE):
            self._cookies_path = COOKIES_FILE
            return COOKIES_FILE
        return None

    def is_active(self) -> bool:
        """هل في كوكيز نشطة؟"""
        path = self.get_cookies_path()
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return bool(content.strip())
            except Exception:
                return False
        return False

    def get_info(self) -> dict:
        """معلومات عن الكوكيز الحالية"""
        path = self.get_cookies_path()
        if not path or not os.path.exists(path):
            return {
                "active": False,
                "path": None,
                "size": 0,
                "lines": 0,
                "has_youtube": False,
            }

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            lines = content.strip().split('\n')
            has_youtube = any("youtube.com" in line or ".youtube.com" in line for line in lines)
            return {
                "active": True,
                "path": path,
                "size": len(content.encode('utf-8')),
                "lines": len(lines),
                "has_youtube": has_youtube,
            }
        except Exception as e:
            return {
                "active": False,
                "path": path,
                "error": str(e),
            }

    def clear(self) -> bool:
        """حذف الكوكيز"""
        try:
            if self._cookies_path and os.path.exists(self._cookies_path):
                os.remove(self._cookies_path)
            if os.path.exists(COOKIES_FILE):
                os.remove(COOKIES_FILE)
            self._cookies_path = None
            logger.info("تم حذف الكوكيز")
            return True
        except Exception as e:
            logger.error(f"فشل حذف الكوكيز: {e}")
            return False

    def get_size_display(self) -> str:
        """حجم الكوكيز بشكل مقروء"""
        info = self.get_info()
        size = info.get("size", 0)
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    def get_lines_display(self) -> str:
        """عدد أسطر الكوكيز"""
        info = self.get_info()
        return str(info.get("lines", 0))


cookie_manager = CookieManager()
