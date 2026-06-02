"""
نسخة الهاتف - واجهة رسومية باستخدام Flet
Mobile Version - GUI using Flet Framework
"""

import os
import sys
import asyncio
import threading
from typing import Optional

# إضافة مسار النواة المشتركة
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flet as ft

from core.downloader import YouTubeDownloader, DownloadStatus
from core.anti_ban import anti_ban
from core.subtitle_handler import SubtitleConverter
from core.models import SubtitleFormat, SubtitleLanguage, VideoQuality


# ألوان التطبيق
class AppColors:
    PRIMARY = "#FF4444"
    PRIMARY_DARK = "#CC0000"
    BG_DARK = "#0F0F0F"
    BG_CARD = "#1A1A1A"
    BG_INPUT = "#222222"
    TEXT_PRIMARY = "#FFFFFF"
    TEXT_SECONDARY = "#AAAAAA"
    TEXT_MUTED = "#666666"
    SUCCESS = "#00C853"
    WARNING = "#FFAB00"
    DANGER = "#FF1744"
    INFO = "#448AFF"
    BORDER = "#333333"


class YouTubeDownloaderMobile:
    """تطبيق الهاتف لتحميل فيديوهات يوتيوب"""

    def __init__(self):
        self.downloader = YouTubeDownloader(download_dir=os.path.expanduser("~/YouTube_Downloads"))
        self.is_downloading = False
        self.download_thread: Optional[threading.Thread] = None

    def build(self, page: ft.Page):
        """بناء واجهة المستخدم"""
        page.title = "YouTube Downloader"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = AppColors.BG_DARK
        page.padding = 0
        page.spacing = 0
        page.scroll = ft.ScrollMode.AUTO
        page.fonts = {}

        # --- Header ---
        header = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DOWNLOAD, color=AppColors.PRIMARY, size=28),
                    ft.Column(
                        [
                            ft.Text(
                                "YouTube Downloader",
                                size=20,
                                weight=ft.FontWeight.BOLD,
                                color=AppColors.TEXT_PRIMARY,
                            ),
                            ft.Text(
                                "تحميل الفيديوهات مع الترجمات",
                                size=12,
                                color=AppColors.TEXT_SECONDARY,
                            ),
                        ],
                        spacing=2,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            padding=ft.padding.only(top=20, bottom=16, left=20, right=20),
            bgcolor=AppColors.BG_CARD,
            border=ft.border.only(bottom=ft.BorderSide(1, AppColors.BORDER)),
        )

        # --- URL Input ---
        self.url_field = ft.TextField(
            hint_text="الصق رابط يوتيوب هنا...",
            border_color=AppColors.BORDER,
            focused_border_color=AppColors.PRIMARY,
            text_style=ft.TextStyle(color=AppColors.TEXT_PRIMARY, size=14),
            hint_style=ft.TextStyle(color=AppColors.TEXT_MUTED),
            bgcolor=AppColors.BG_INPUT,
            border_radius=10,
            text_align=ft.TextAlign.RIGHT,
            content_padding=14,
            max_lines=2,
        )

        self.btn_search = ft.ElevatedButton(
            "بحث",
            icon=ft.Icons.SEARCH,
            bgcolor=AppColors.PRIMARY,
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=20, vertical=14),
            ),
            on_click=self.on_search_click,
        )

        url_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Icon(ft.Icons.LINK, color=AppColors.PRIMARY, size=18),
                         ft.Text("رابط الفيديو", size=16, weight=ft.FontWeight.BOLD)],
                        spacing=8,
                    ),
                    ft.Row(
                        [self.url_field, self.btn_search],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                ],
                spacing=12,
            ),
            padding=16,
            bgcolor=AppColors.BG_CARD,
            border_radius=12,
            border=ft.border.all(1, AppColors.BORDER),
            margin=ft.margin.only(left=12, right=12, top=12),
        )

        # --- Video Info ---
        self.video_thumbnail = ft.Image(
            src="",
            width=400,
            height=180,
            fit=ft.ImageFit.COVER,
            border_radius=10,
            visible=False,
        )

        self.video_title = ft.Text(
            "", size=16, weight=ft.FontWeight.BOLD,
            color=AppColors.TEXT_PRIMARY, max_lines=2,
        )
        self.video_uploader = ft.Text("", size=12, color=AppColors.TEXT_SECONDARY)
        self.video_duration_badge = ft.Container(
            content=ft.Text("", size=11, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.with_opacity(0.85, ft.Colors.BLACK),
            padding=ft.padding.only(left=6, right=6, top=2, bottom=2),
            border_radius=4,
            visible=False,
        )

        self.video_info_container = ft.Container(
            content=ft.Column([
                ft.Stack([
                    self.video_thumbnail,
                    ft.Container(
                        content=self.video_duration_badge,
                        alignment=ft.alignment.bottom_left,
                        padding=8,
                    ),
                ]),
                ft.Column([
                    self.video_title,
                    self.video_uploader,
                ], spacing=4, padding=ft.padding.only(top=8)),
            ]),
            padding=16,
            bgcolor=AppColors.BG_CARD,
            border_radius=12,
            border=ft.border.all(1, AppColors.BORDER),
            margin=ft.margin.only(left=12, right=12, top=12),
            visible=False,
        )

        # --- Download Options ---
        self.subtitle_lang = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="ar", label="العربية 🇸🇦", fill_color=AppColors.PRIMARY),
                ft.Radio(value="en", label="English 🇺🇸", fill_color=AppColors.PRIMARY),
            ]),
            value="ar",
        )

        self.subtitle_format = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="srt", label="SRT", fill_color=AppColors.PRIMARY),
                ft.Radio(value="vtt", label="VTT", fill_color=AppColors.PRIMARY),
            ]),
            value="srt",
        )

        self.video_quality = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="best", label="أفضل جودة", fill_color=AppColors.PRIMARY),
                ft.Radio(value="medium", label="720p", fill_color=AppColors.PRIMARY),
                ft.Radio(value="low", label="480p", fill_color=AppColors.PRIMARY),
            ]),
            value="best",
        )

        self.auto_subtitle = ft.Switch(
            label="استخدام الترجمة التلقائية",
            value=True,
            active_color=AppColors.PRIMARY,
            label_style=ft.TextStyle(size=13, color=AppColors.TEXT_SECONDARY),
        )

        self.options_container = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Icon(ft.Icons.SETTINGS, color=AppColors.PRIMARY, size=18),
                         ft.Text("خيارات التحميل", size=16, weight=ft.FontWeight.BOLD)],
                        spacing=8,
                    ),
                    # Language
                    ft.Row(
                        [ft.Icon(ft.Icons.LANGUAGE, color=AppColors.PRIMARY, size=16),
                         ft.Text("لغة الترجمة", size=14, color=AppColors.TEXT_SECONDARY)],
                        spacing=6,
                    ),
                    self.subtitle_lang,
                    ft.Divider(color=AppColors.BORDER, height=1),
                    # Format
                    ft.Row(
                        [ft.Icon(ft.Icons.CLOSED_CAPTION, color=AppColors.PRIMARY, size=16),
                         ft.Text("صيغة الترجمة", size=14, color=AppColors.TEXT_SECONDARY)],
                        spacing=6,
                    ),
                    self.subtitle_format,
                    ft.Divider(color=AppColors.BORDER, height=1),
                    # Quality
                    ft.Row(
                        [ft.Icon(ft.Icons.VIDEO_SETTINGS, color=AppColors.PRIMARY, size=16),
                         ft.Text("جودة الفيديو", size=14, color=AppColors.TEXT_SECONDARY)],
                        spacing=6,
                    ),
                    self.video_quality,
                    ft.Divider(color=AppColors.BORDER, height=1),
                    # Auto
                    self.auto_subtitle,
                ],
                spacing=10,
            ),
            padding=16,
            bgcolor=AppColors.BG_CARD,
            border_radius=12,
            border=ft.border.all(1, AppColors.BORDER),
            margin=ft.margin.only(left=12, right=12, top=12),
            visible=False,
        )

        # --- Download Buttons ---
        self.btn_download_full = ft.ElevatedButton(
            "تحميل الفيديو + الترجمة",
            icon=ft.Icons.DOWNLOAD,
            bgcolor=AppColors.PRIMARY,
            color=ft.Colors.WHITE,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=24, vertical=16),
                text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD),
            ),
            on_click=lambda _: self.start_download("full"),
        )

        self.btn_download_sub = ft.OutlinedButton(
            "ترجمة فقط",
            icon=ft.Icons.CLOSED_CAPTION,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=20, vertical=14),
                side=ft.BorderSide(2, AppColors.PRIMARY),
            ),
            on_click=lambda _: self.start_download("subtitle"),
        )

        self.buttons_container = ft.Container(
            content=ft.Row(
                [self.btn_download_full, self.btn_download_sub],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=12,
                wrap=True,
            ),
            padding=16,
            margin=ft.margin.only(left=12, right=12, top=8),
            visible=False,
        )

        # --- Progress ---
        self.progress_bar = ft.ProgressBar(
            width=float('inf'),
            height=10,
            bgcolor=AppColors.BG_INPUT,
            color=AppColors.PRIMARY,
            value=0,
            bar_radius=5,
        )

        self.progress_percent = ft.Text("0%", size=16, weight=ft.FontWeight.BOLD, color=AppColors.PRIMARY)
        self.progress_speed = ft.Text("", size=12, color=AppColors.TEXT_SECONDARY)
        self.progress_eta = ft.Text("", size=12, color=AppColors.TEXT_SECONDARY)
        self.progress_message = ft.Text("", size=13, color=AppColors.TEXT_SECONDARY, text_align=ft.TextAlign.CENTER)

        # Steps indicators
        self.step_indicators = []
        step_labels = ["جلب المعلومات", "تحميل الترجمة", "انتظار أماني", "تحميل الفيديو"]
        step_icons = [ft.Icons.SEARCH, ft.Icons.CLOSED_CAPTION, ft.Icons.TIMER, ft.Icons.MOVIE]

        for i, (label, icon) in enumerate(zip(step_labels, step_icons)):
            self.step_indicators.append(
                ft.Container(
                    content=ft.Column(
                        [ft.Icon(icon, color=AppColors.TEXT_MUTED, size=20),
                         ft.Text(label, size=10, color=AppColors.TEXT_MUTED, text_align=ft.TextAlign.CENTER)],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=4,
                    ),
                    padding=8,
                    border_radius=8,
                )
            )

        self.btn_cancel = ft.OutlinedButton(
            "إلغاء التحميل",
            icon=ft.Icons.CANCEL,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                side=ft.BorderSide(2, AppColors.DANGER),
                color=AppColors.DANGER,
            ),
            on_click=self.cancel_download,
        )

        self.progress_container = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Icon(ft.Icons.SYNC, color=AppColors.PRIMARY, size=18),
                         ft.Text("جاري التحميل...", size=16, weight=ft.FontWeight.BOLD)],
                        spacing=8,
                    ),
                    self.progress_bar,
                    ft.Row(
                        [self.progress_percent, self.progress_speed, self.progress_eta],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        self.step_indicators,
                        alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                        wrap=True,
                    ),
                    self.progress_message,
                    self.btn_cancel,
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=16,
            bgcolor=AppColors.BG_CARD,
            border_radius=12,
            border=ft.border.all(1, AppColors.BORDER),
            margin=ft.margin.only(left=12, right=12, top=12),
            visible=False,
        )

        # --- Completed ---
        self.completed_files = ft.Column(spacing=10)
        self.completed_container = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Icon(ft.Icons.CHECK_CIRCLE, color=AppColors.SUCCESS, size=18),
                         ft.Text("تم التحميل بنجاح!", size=16, weight=ft.FontWeight.BOLD)],
                        spacing=8,
                    ),
                    self.completed_files,
                ],
                spacing=12,
            ),
            padding=16,
            bgcolor=AppColors.BG_CARD,
            border_radius=12,
            border=ft.border.all(1, AppColors.SUCCESS),
            margin=ft.margin.only(left=12, right=12, top=12),
            visible=False,
        )

        # --- Build Page ---
        page.add(
            header,
            url_section,
            self.video_info_container,
            self.options_container,
            self.buttons_container,
            self.progress_container,
            self.completed_container,
            ft.Container(height=40),  # Bottom spacer
        )

        # Progress callback غير مفعل — نستخدم polling بدلاً منه
        pass

    def on_search_click(self, e):
        """البحث عن الفيديو"""
        url = self.url_field.value.strip()
        if not url:
            self._show_snackbar("الرجاء إدخال رابط يوتيوب")
            return

        page = e.page
        self.btn_search.text = "جاري البحث..."
        self.btn_search.disabled = True
        page.update()

        def _search():
            try:
                loop = asyncio.new_event_loop()
                info = loop.run_until_complete(self.downloader.fetch_video_info(url))
                loop.close()

                # تحديث واجهة المستخدم
                page.run_thread(lambda: self._update_video_info(page, info))
            except Exception as ex:
                page.run_thread(lambda: self._show_snackbar_on_page(page, f"خطأ: {str(ex)}"))
            finally:
                self.btn_search.text = "بحث"
                self.btn_search.disabled = False
                page.update()

        threading.Thread(target=_search, daemon=True).start()

    def _update_video_info(self, page, info):
        """تحديث معلومات الفيديو في الواجهة"""
        self.video_thumbnail.src = info.thumbnail
        self.video_thumbnail.visible = True
        self.video_title.value = info.title
        self.video_uploader.value = info.uploader
        self.video_duration_badge.content.value = self._format_duration(info.duration)
        self.video_duration_badge.visible = True

        self.video_info_container.visible = True
        self.options_container.visible = True
        self.buttons_container.visible = True

        page.update()

    def start_download(self, download_type: str):
        """بدء التحميل"""
        if self.is_downloading:
            self._show_snackbar("يوجد تحميل قيد التشغيل")
            return

        url = self.url_field.value.strip()
        if not url:
            self._show_snackbar("الرجاء إدخال رابط يوتيوب")
            return

        self.is_downloading = True
        self.progress_container.visible = True
        self.completed_container.visible = False
        self.progress_bar.value = 0
        self.progress_percent.value = "0%"

        page = self.buttons_container.page
        page.update()

        subtitle_lang = self.subtitle_lang.value
        subtitle_format = self.subtitle_format.value
        quality = self.video_quality.value
        auto_sub = self.auto_subtitle.value

        def _download():
            try:
                loop = asyncio.new_event_loop()
                if download_type == "full":
                    results = loop.run_until_complete(
                        self.downloader.download_full(
                            url=url,
                            subtitle_lang=subtitle_lang,
                            subtitle_format=subtitle_format,
                            quality=quality,
                            auto_subtitle=auto_sub,
                        )
                    )
                    page.run_thread(lambda: self._on_download_complete(page, results))
                else:
                    sub_file = loop.run_until_complete(
                        self.downloader.download_subtitle(
                            url=url,
                            language_code=subtitle_lang,
                            subtitle_format=subtitle_format,
                            auto_generated=auto_sub,
                        )
                    )
                    page.run_thread(lambda: self._on_download_complete(page, {"subtitle": sub_file, "video": None}))
                loop.close()
            except Exception as ex:
                page.run_thread(lambda: self._on_download_error(page, str(ex)))
            finally:
                self.is_downloading = False

        # Poll progress
        def _poll_progress():
            import time
            while self.is_downloading:
                try:
                    p = self.downloader.progress
                    page.run_thread(lambda: self._update_progress_ui(page))
                    time.sleep(0.5)
                except:
                    break

        self.download_thread = threading.Thread(target=_download, daemon=True)
        self.download_thread.start()

        threading.Thread(target=_poll_progress, daemon=True).start()

    def _update_progress_ui(self, page):
        """تحديث واجهة التقدم"""
        import copy
        p = copy.copy(self.downloader.progress)
        self.progress_bar.value = p.percent / 100
        self.progress_percent.value = f"{p.percent:.0f}%"
        self.progress_speed.value = p.speed
        self.progress_eta.value = f"متبقي: {p.eta}" if p.eta else ""
        self.progress_message.value = p.message

        # Update step colors
        step_map = {
            DownloadStatus.FETCHING_INFO: 0,
            DownloadStatus.DOWNLOADING_SUBTITLE: 1,
            DownloadStatus.WAITING_ANTI_BAN: 2,
            DownloadStatus.DOWNLOADING_VIDEO: 3,
        }

        current_step = step_map.get(p.status, -1)
        for i, container in enumerate(self.step_indicators):
            icon = container.content.controls[0]
            text = container.content.controls[1]
            if i < current_step:
                icon.color = AppColors.SUCCESS
                text.color = AppColors.SUCCESS
            elif i == current_step:
                icon.color = AppColors.PRIMARY
                text.color = AppColors.PRIMARY
            else:
                icon.color = AppColors.TEXT_MUTED
                text.color = AppColors.TEXT_MUTED

        try:
            page.update()
        except:
            pass

    def _on_download_complete(self, page, results):
        """عند اكتمال التحميل"""
        self.progress_container.visible = False
        self.completed_container.visible = True
        self.completed_files.controls.clear()

        if results.get("video"):
            self._add_file_item(page, results["video"], "video")
        if results.get("subtitle"):
            self._add_file_item(page, results["subtitle"], "subtitle")

        self.is_downloading = False
        page.update()

    def _add_file_item(self, page, filepath, file_type):
        """إضافة عنصر ملف"""
        filename = filepath.split("/")[-1] if filepath else ""
        is_video = file_type == "video"

        icon = ft.Icons.MOVIE if is_video else ft.Icons.CLOSED_CAPTION
        icon_color = AppColors.PRIMARY if is_video else AppColors.INFO
        label = "ملف فيديو" if is_video else "ملف ترجمة"

        item = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Icon(icon, color=icon_color, size=24),
                    bgcolor=ft.Colors.with_opacity(0.15, icon_color),
                    border_radius=8,
                    padding=10,
                    width=48,
                    height=48,
                    alignment=ft.alignment.center,
                ),
                ft.Column([
                    ft.Text(filename, size=13, weight=ft.FontWeight.BOLD, color=AppColors.TEXT_PRIMARY),
                    ft.Text(label, size=11, color=AppColors.TEXT_MUTED),
                ], spacing=2, expand=True),
                ft.ElevatedButton(
                    "حفظ",
                    icon=ft.Icons.SAVE,
                    bgcolor=AppColors.PRIMARY,
                    color=ft.Colors.WHITE,
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                    on_click=lambda _, p=filepath: self._save_file(page, p),
                ),
            ]),
            bgcolor=AppColors.BG_INPUT,
            border_radius=10,
            padding=12,
            border=ft.border.all(1, AppColors.BORDER),
        )

        self.completed_files.controls.append(item)

    def _save_file(self, page, filepath):
        """حفظ الملف - فتح نافذة الحفظ"""
        if not filepath or not os.path.exists(filepath):
            self._show_snackbar_on_page(page, "الملف غير موجود")
            return

        # في Flet يمكن استخدام file_picker للحفظ
        def _save_with_picker(e):
            if e.path:
                import shutil
                try:
                    shutil.copy2(filepath, e.path)
                    self._show_snackbar_on_page(page, "تم حفظ الملف بنجاح!")
                except Exception as ex:
                    self._show_snackbar_on_page(page, f"خطأ في الحفظ: {str(ex)}")

        try:
            save_dialog = ft.FilePicker(on_result=_save_with_picker)
            page.overlay.append(save_dialog)
            page.update()
            save_dialog.save_file(
                file_name=os.path.basename(filepath),
                allowed_extensions=[os.path.splitext(filepath)[1].lstrip('.')] if filepath else None,
            )
        except Exception:
            # Fallback: نسخ الملف مباشرة
            self._show_snackbar_on_page(page, f"الملف محفوظ في: {filepath}")

    def _on_download_error(self, page, error):
        """عند خطأ في التحميل"""
        self.progress_container.visible = False
        self.is_downloading = False
        page.update()
        self._show_snackbar_on_page(page, f"خطأ: {error}")

    def cancel_download(self, e):
        """إلغاء التحميل"""
        self.downloader.cancel_download()
        self.is_downloading = False
        self.progress_container.visible = False
        e.page.update()
        self._show_snackbar("تم إلغاء التحميل")

    def _show_snackbar(self, message):
        """عرض رسالة snackbar"""
        try:
            page = self.url_field.page
            if page:
                page.snack_bar = ft.SnackBar(
                    content=ft.Text(message),
                    bgcolor=AppColors.BG_CARD,
                )
                page.update()
                page.snack_bar.open = True
                page.update()
        except:
            pass

    def _show_snackbar_on_page(self, page, message):
        """عرض رسالة snackbar على صفحة محددة"""
        try:
            page.snack_bar = ft.SnackBar(
                content=ft.Text(message),
                bgcolor=AppColors.BG_CARD,
            )
            page.update()
            page.snack_bar.open = True
            page.update()
        except:
            pass

    @staticmethod
    def _format_duration(seconds):
        if not seconds:
            return "0:00"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


def main():
    """تشغيل التطبيق"""
    app = YouTubeDownloaderMobile()
    ft.app(target=app.build, view=ft.AppView.FLET_APP)


if __name__ == "__main__":
    main()
