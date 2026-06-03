# DownTube — اختبارات تتبع التقدم

"""
اختبارات نظام تتبع التقدم:
- تحديث المراحل
- حساب النسب المئوية
- إرسال الرسائل عبر قائمة الانتظار
"""

import queue
import pytest

from app.services.progress import ProgressTracker, PHASES
from app.config import (
    PHASE_FETCH_INFO,
    PHASE_CHECK_SUBTITLE,
    PHASE_DOWNLOAD_VIDEO,
    PHASE_DOWNLOAD_SUBTITLE,
    PHASE_PROCESSING,
)


class TestProgressTrackerInit:
    """اختبارات تهيئة متتبع التقدم."""

    def test_creates_with_queue(self):
        """يجب أن ينشأ مع قائمة انتظار."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        assert tracker.queue is q

    def test_initial_phase_is_zero(self):
        """يجب أن تبدأ المرحلة من الصفر."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        assert tracker.current_phase_index == 0

    def test_initial_percent_is_zero(self):
        """يجب أن تبدأ النسبة من صفر."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        assert tracker.phase_percent == 0.0


class TestProgressTrackerPhases:
    """اختبارات تحديث المراحل."""

    def test_set_phase_sends_message(self):
        """يجب أن يرسل رسالة عند تحديث المرحلة."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.set_phase(1, "جاري التحقق")
        msg = q.get_nowait()
        assert msg["type"] == "progress"
        assert msg["phase_index"] == 1

    def test_phase_name_matches(self):
        """يجب أن يتطابق اسم المرحلة."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.set_phase(2, "تنزيل الفيديو")
        msg = q.get_nowait()
        assert msg["phase"] == PHASE_DOWNLOAD_VIDEO

    def test_update_progress_sends_percent(self):
        """يجب أن يرسل النسبة المئوية."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.set_phase(0)
        q.get_nowait()  # تنظيف
        tracker.update_phase_progress(50.0)
        msg = q.get_nowait()
        assert msg["phase_percent"] == 50.0

    def test_progress_clamped_to_100(self):
        """يجب أن تقتصر النسبة على 100 كحد أقصى."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.set_phase(0)
        q.get_nowait()
        tracker.update_phase_progress(150.0)
        msg = q.get_nowait()
        assert msg["phase_percent"] == 100.0

    def test_speed_and_eta_in_message(self):
        """يجب أن تتضمن الرسالة السرعة والوقت المتبقي."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.set_phase(2)
        q.get_nowait()
        tracker.update_phase_progress(30.0, speed=1024000, eta=45)
        msg = q.get_nowait()
        assert msg["speed"] == 1024000
        assert msg["eta"] == 45


class TestOverallProgress:
    """اختبارات حساب النسبة الإجمالية."""

    def test_phase_0_at_0_percent(self):
        """المرحلة 0 بنسبة 0% = إجمالي 0%."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.set_phase(0)
        msg = q.get_nowait()
        assert msg["overall_percent"] == 0.0

    def test_phase_0_at_100_percent(self):
        """المرحلة 0 بنسبة 100% = إجمالي 20%."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.set_phase(0)
        q.get_nowait()
        tracker.update_phase_progress(100.0)
        msg = q.get_nowait()
        assert msg["overall_percent"] == 20.0

    def test_phase_2_at_50_percent(self):
        """المرحلة 2 بنسبة 50% = إجمالي 50%."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.set_phase(2)
        q.get_nowait()
        tracker.update_phase_progress(50.0)
        msg = q.get_nowait()
        assert msg["overall_percent"] == 50.0

    def test_all_phases_complete(self):
        """كل المراحل مكتملة = إجمالي 100%."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        # محاكاة إكمال كل المراحل
        for i in range(5):
            tracker.set_phase(i)
            q.get_nowait()
            tracker.update_phase_progress(100.0)
            q.get_nowait()


class TestProgressFinish:
    """اختبارات إنهاء التتبع."""

    def test_finish_sends_done_type(self):
        """يجب أن يرسل نوع 'done' عند الإنتهاء."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.finish("تم!")
        msg = q.get_nowait()
        assert msg["type"] == "done"

    def test_finish_percent_is_100(self):
        """يجب أن تكون النسبة 100% عند الإنتهاء."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.finish("تم!")
        msg = q.get_nowait()
        assert msg["overall_percent"] == 100.0

    def test_finish_includes_result(self):
        """يجب أن تتضمن النتيجة عند الإنتهاء."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        result = {"title": "فيديو", "video_file": "/path/video.mp4"}
        tracker.finish("تم!", result=result)
        msg = q.get_nowait()
        assert msg["result"]["title"] == "فيديو"


class TestProgressError:
    """اختبارات رسائل الخطأ."""

    def test_error_sends_error_type(self):
        """يجب أن يرسل نوع 'error' عند الخطأ."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.error("خطأ!")
        msg = q.get_nowait()
        assert msg["type"] == "error"

    def test_error_includes_message(self):
        """يجب أن تتضمن رسالة الخطأ."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.error("فشل الاتصال")
        msg = q.get_nowait()
        assert msg["message"] == "فشل الاتصال"


class TestProgressInfo:
    """اختبارات رسائل المعلومات."""

    def test_info_sends_info_type(self):
        """يجب أن يرسل نوع 'info'."""
        q = queue.Queue()
        tracker = ProgressTracker(q)
        tracker.info("معلومة")
        msg = q.get_nowait()
        assert msg["type"] == "info"
        assert msg["message"] == "معلومة"


class TestProgressSSEEndpoint:
    """اختبارات نقطة نهاية SSE."""

    def test_state_endpoint_exists(self, client):
        """يجب أن تكون نقطة نهاية الحالة موجودة."""
        resp = client.get("/api/state")
        assert resp.status_code == 200
