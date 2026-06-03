# DownTube — خدمة الترجمة

"""
يتولى هذا الملف كشف الترجمة وإدارتها:
- البحث عن ترجمة عربية (يدوية أو تلقائية)
- مطابقة اللغة بالبادئة (ar → ar, ar-SA, ar-EG, إلخ)
- إعادة تسمية ملفات الترجمة
"""

import os
import re
import time
import glob
import logging
from typing import Optional

from app.config import SUBTITLE_PREFERRED_FORMAT, SUBTITLE_FORMATS

logger = logging.getLogger(__name__)


def find_lang_key(available: Optional[dict], requested: str) -> Optional[str]:
    """
    البحث عن مفتاح لغة الترجمة باستخدام مطابقة البادئة.
    
    مثال: إذا طلب 'ar' سيطابق 'ar', 'ar-SA', 'ar-EG', إلخ.
    المطابقة الدقيقة لها الأولوية.
    """
    if not available:
        return None

    # مطابقة دقيقة أولاً
    if requested in available:
        return requested

    # مطابقة بالبادئة
    for key in available:
        if key.startswith(requested):
            return key

    return None


def check_subtitles(info: dict, lang: str = "ar") -> Optional[dict]:
    """
    التحقق من وجود ترجمة باللغة المطلوبة.
    
    المعاملات:
        info: قاموس معلومات الفيديو من yt-dlp
        lang: رمز اللغة المطلوبة (مثال: 'ar')
    
    Returns:
        قاموس يحتوي على: type (official/auto), key (مفتاح اللغة المطابق)
        أو None إذا لم توجد ترجمة
    """
    # التحقق من الترجمة اليدوية أولاً
    subtitles = info.get("subtitles", {})
    key = find_lang_key(subtitles, lang)
    if key:
        logger.info("ترجمة يدوية موجودة: %s", key)
        return {"type": "official", "key": key}

    # التحقق من الترجمة التلقائية
    auto_captions = info.get("automatic_captions", {})
    key = find_lang_key(auto_captions, lang)
    if key:
        logger.info("ترجمة تلقائية موجودة: %s", key)
        return {"type": "auto", "key": key}

    logger.info("لا توجد ترجمة باللغة: %s", lang)
    return None


def sanitize_filename(name: str) -> str:
    """إزالة الأحرف غير المسموحة في أسماء الملفات."""
    sanitized = re.sub(r'[<>:"/\\|?*]', "", name)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    sanitized = sanitized.strip(".")
    return sanitized


def find_subtitle_file(directory: str, max_age: int = 120) -> Optional[str]:
    """
    البحث عن ملف الترجمة الذي تم تنزيله مؤخراً.
    
    يستخدم وقت التعديل (mtime) للعثور على الملف الصحيح.
    """
    now = time.time()
    candidates = []

    for fmt in SUBTITLE_FORMATS:
        pattern = os.path.join(directory, f"*.{fmt}")
        for filepath in glob.glob(pattern):
            try:
                mtime = os.path.getmtime(filepath)
                age = now - mtime
                if age < max_age:
                    candidates.append((filepath, mtime))
            except OSError:
                continue

    if not candidates:
        return None

    # إرجاع أحدث ملف
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


def rename_subtitle_file(subtitle_path: str, video_title: str, lang_code: str) -> str:
    """
    إعادة تسمية ملف الترجمة حسب الاتفاقية:
    {العنوان}_SUBTITLE_{اللغة}.{الصيغة}
    """
    directory = os.path.dirname(subtitle_path)
    ext = os.path.splitext(subtitle_path)[1]

    safe_title = sanitize_filename(video_title)
    new_name = f"{safe_title}_SUBTITLE_{lang_code}{ext}"
    new_path = os.path.join(directory, new_name)

    # تجنب الكتابة فوق ملف موجود
    if os.path.exists(new_path) and new_path != subtitle_path:
        counter = 1
        while os.path.exists(
            os.path.join(directory, f"{safe_title}_SUBTITLE_{lang_code}_{counter}{ext}")
        ):
            counter += 1
        new_name = f"{safe_title}_SUBTITLE_{lang_code}_{counter}{ext}"
        new_path = os.path.join(directory, new_name)

    if new_path != subtitle_path:
        try:
            os.rename(subtitle_path, new_path)
            logger.info("تمت إعادة تسمية الترجمة: %s", new_name)
        except OSError as e:
            logger.error("فشل إعادة تسمية الترجمة: %s", e)
            return subtitle_path

    return new_path
