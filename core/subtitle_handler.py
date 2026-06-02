"""
معالج الترجمات - تحويل ومزامنة وتنسيق
Subtitle Handler - Conversion, Sync, and Formatting
"""

import re
import os
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SubtitleInfo:
    """معلومات الترجمة"""
    language: str
    language_code: str
    auto_generated: bool
    url: str = ""
    content: str = ""


class SubtitleConverter:
    """محول الترجمات بين الصيغ المختلفة مع مزامنة دقيقة"""

    @staticmethod
    def vtt_to_srt(vtt_content: str) -> str:
        """
        تحويل ملف VTT إلى صيغة SRT
        مع الحفاظ على المزامنة الدقيقة والتوقيت
        """
        lines = vtt_content.strip().split('\n')
        srt_lines = []
        subtitle_index = 1
        i = 0

        # تخطي رأس VTT
        while i < len(lines) and not re.match(r'\d{2}:\d{2}', lines[i]):
            i += 1

        while i < len(lines):
            line = lines[i].strip()

            # البحث عن سطر التوقيت
            time_match = re.match(
                r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})',
                line
            )
            if not time_match:
                # محاولة مطابقة توقيت بدون ساعات
                time_match = re.match(
                    r'(\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}\.\d{3})',
                    line
                )
                if time_match:
                    start_time = "00:" + time_match.group(1)
                    end_time = "00:" + time_match.group(2)
                else:
                    i += 1
                    continue
            else:
                start_time = time_match.group(1)
                end_time = time_match.group(2)

            # تحويل الفاصل العشري من نقطة إلى فاصلة لـ SRT
            start_srt = start_time.replace('.', ',')
            end_srt = end_time.replace('.', ',')

            # جمع نص الترجمة
            i += 1
            text_lines = []
            while i < len(lines):
                text_line = lines[i].strip()
                if not text_line or re.match(r'\d{2}:\d{2}', text_line):
                    break
                # إزالة علامات VTT
                text_line = re.sub(r'<[^>]+>', '', text_line)
                if text_line:
                    text_lines.append(text_line)
                i += 1

            if text_lines:
                srt_lines.append(str(subtitle_index))
                srt_lines.append(f"{start_srt} --> {end_srt}")
                srt_lines.extend(text_lines)
                srt_lines.append("")
                subtitle_index += 1
            else:
                i += 1

        return '\n'.join(srt_lines)

    @staticmethod
    def srt_to_vtt(srt_content: str) -> str:
        """تحويل ملف SRT إلى صيغة VTT"""
        lines = srt_content.strip().split('\n')
        vtt_lines = ["WEBVTT", ""]

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # تخطي رقم الترجمة
            if line.isdigit():
                i += 1
                if i < len(lines):
                    time_line = lines[i].strip()
                    # تحويل الفاصل من فاصلة إلى نقطة لـ VTT
                    time_line = time_line.replace(',', '.')
                    vtt_lines.append(time_line)
                    i += 1

                    # جمع النص
                    while i < len(lines) and lines[i].strip():
                        vtt_lines.append(lines[i].strip())
                        i += 1
                    vtt_lines.append("")
            i += 1

        return '\n'.join(vtt_lines)

    @staticmethod
    def adjust_subtitle_timing(
        content: str,
        offset_ms: float = 0,
        format: str = "srt"
    ) -> str:
        """
        تعديل توقيت الترجمة بمقدار offset بالمللي ثانية
        للمزامنة الدقيقة مع الصوت
        """
        def adjust_time(time_str: str, offset: float) -> str:
            """تعديل وقت واحد"""
            # استخراج الأجزاء
            if '.' in time_str:
                main_part, ms_part = time_str.rsplit('.', 1)
            elif ',' in time_str:
                main_part, ms_part = time_str.rsplit(',', 1)
            else:
                return time_str

            h, m, s = main_part.split(':')
            total_ms = (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms_part[:3].ljust(3, '0'))
            total_ms += int(offset)

            if total_ms < 0:
                total_ms = 0

            new_h = total_ms // 3600000
            total_ms %= 3600000
            new_m = total_ms // 60000
            total_ms %= 60000
            new_s = total_ms // 1000
            new_ms = total_ms % 1000

            sep = '.' if format == 'vtt' else ','
            return f"{new_h:02d}:{new_m:02d}:{new_s:02d}{sep}{new_ms:03d}"

        lines = content.split('\n')
        adjusted_lines = []

        for line in lines:
            # البحث عن سطور التوقيت
            time_match = re.match(
                r'(\d{2}:\d{2}[:\.]\d{2}[\.\,]\d{3})\s*-->\s*(\d{2}:\d{2}[:\.]\d{2}[\.\,]\d{3})',
                line
            )
            if time_match:
                start = adjust_time(time_match.group(1), offset_ms)
                end = adjust_time(time_match.group(2), offset_ms)
                adjusted_lines.append(f"{start} --> {end}")
            else:
                adjusted_lines.append(line)

        return '\n'.join(adjusted_lines)

    @staticmethod
    def clean_subtitle(content: str) -> str:
        """
        تنظيف محتوى الترجمة من العناصر غير المرغوبة
        وإزالة التكرارات والأسطر الفارغة المتعددة
        """
        # إزالة علامات HTML/XML
        content = re.sub(r'<[^>]+>', '', content)

        # إزالة تعليمات VTT الإضافية
        content = re.sub(r'Kind:\s*\w+\n', '', content)
        content = re.sub(r'Language:\s*\w+\n', '', content)

        # إزالة الأسطر الفارغة المتعددة
        content = re.sub(r'\n{3,}', '\n\n', content)

        # إزالة المسافات الزائدة في بداية ونهاية كل سطر
        lines = [line.strip() for line in content.split('\n')]
        content = '\n'.join(lines)

        # إزالة الأسطر الفارغة في النهاية
        content = content.strip()

        return content

    @staticmethod
    def format_subtitle(content: str, format: str = "srt") -> str:
        """
        تنسيق الترجمة بشكل نظيف ومنظم
        """
        # تنظيف أولاً
        content = SubtitleConverter.clean_subtitle(content)

        if format == "vtt":
            # التأكد من وجود رأس VTT
            if not content.startswith("WEBVTT"):
                content = "WEBVTT\n\n" + content
            # توحيد الفاصل العشري
            content = content.replace(',', '.')
        elif format == "srt":
            # إزالة رأس VTT إن وجد
            content = re.sub(r'^WEBVTT.*?\n\n', '', content, flags=re.DOTALL)
            # توحيد الفاصل العشري
            content = content.replace('.', ',')

        return content

    @staticmethod
    def save_subtitle(
        content: str,
        filepath: str,
        format: str = "srt",
        offset_ms: float = 0
    ) -> str:
        """
        حفظ الترجمة في ملف بالصيغة المحددة مع المزامنة
        """
        # تعديل التوقيت إذا لزم الأمر
        if offset_ms != 0:
            content = SubtitleConverter.adjust_subtitle_timing(
                content, offset_ms, format
            )

        # تنسيق المحتوى
        content = SubtitleConverter.format_subtitle(content, format)

        # تحديد الامتداد
        ext = ".vtt" if format == "vtt" else ".srt"
        if not filepath.endswith(ext):
            filepath = os.path.splitext(filepath)[0] + ext

        # حفظ الملف
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"Subtitle saved to {filepath} (format: {format})")
        return filepath


def detect_subtitle_format(content: str) -> str:
    """كشف صيغة الترجمة تلقائياً"""
    if content.strip().startswith("WEBVTT"):
        return "vtt"
    elif re.search(r'\d{2}:\d{2}:\d{2},\d{3}\s*-->', content):
        return "srt"
    return "unknown"
