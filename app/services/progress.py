# DownTube — خدمة تتبع التقدم

"""
يتولى هذا الملف إدارة تتبع التقدم وإرسال تحديثات SSE:
- تتبع المراحل الخمس للتحميل
- حساب النسب المئوية الإجمالية والمرحلية
- تقدير الوقت المتبقي (ETA)
- إرسال التحديثات عبر قائمة انتظار
"""

import time
import queue
import threading
import logging
from typing import Optional

from app.config import (
    PHASE_FETCH_INFO,
    PHASE_CHECK_SUBTITLE,
    PHASE_DOWNLOAD_VIDEO,
    PHASE_DOWNLOAD_SUBTITLE,
    PHASE_PROCESSING,
)

logger = logging.getLogger(__name__)

# المراحل بالترتيب
PHASES = [
    PHASE_FETCH_INFO,        # 0
    PHASE_CHECK_SUBTITLE,    # 1
    PHASE_DOWNLOAD_VIDEO,    # 2
    PHASE_DOWNLOAD_SUBTITLE, # 3
    PHASE_PROCESSING,        # 4
]


class ProgressTracker:
    """
    متتبع تقدم التحميل.
    
    يرسل تحديثات عبر قائمة انتظار (queue.Queue) لتكون
    آمنة مع الخيوط (thread-safe).
    """

    def __init__(self, message_queue: queue.Queue):
        self.queue = message_queue
        self.current_phase_index = 0
        self.phase_percent = 0.0
        self.start_time = time.time()
        self._lock = threading.Lock()

    def _send(self, data: dict):
        """إرسال رسالة عبر قائمة الانتظار."""
        try:
            self.queue.put_nowait(data)
        except queue.Full:
            logger.warning("قائمة الانتظار ممتلئة — تم تجاهل رسالة")

    def set_phase(self, phase_index: int, message: str = ""):
        """تحديد المرحلة الحالية."""
        with self._lock:
            self.current_phase_index = phase_index
            self.phase_percent = 0.0
            phase_name = PHASES[phase_index] if phase_index < len(PHASES) else ""

            self._send({
                "type": "progress",
                "phase": phase_name,
                "phase_index": phase_index,
                "total_phases": len(PHASES),
                "phase_percent": 0.0,
                "overall_percent": self._calc_overall(),
                "speed": None,
                "eta": None,
                "message": message or phase_name,
                "state": "running",
            })

    def update_phase_progress(
        self,
        phase_percent: float,
        speed: Optional[float] = None,
        eta: Optional[int] = None,
        message: str = "",
    ):
        """تحديث نسبة التقدم داخل المرحلة الحالية."""
        with self._lock:
            self.phase_percent = min(100.0, max(0.0, phase_percent))

            self._send({
                "type": "progress",
                "phase": PHASES[self.current_phase_index] if self.current_phase_index < len(PHASES) else "",
                "phase_index": self.current_phase_index,
                "total_phases": len(PHASES),
                "phase_percent": self.phase_percent,
                "overall_percent": self._calc_overall(),
                "speed": speed,
                "eta": eta,
                "message": message,
                "state": "running",
            })

    def finish(self, message: str = "تم التحميل بنجاح!", result: Optional[dict] = None):
        """إنهاء التتبع بنجاح."""
        with self._lock:
            elapsed = time.time() - self.start_time
            data = {
                "type": "done",
                "phase": "اكتمل",
                "phase_index": len(PHASES),
                "total_phases": len(PHASES),
                "phase_percent": 100.0,
                "overall_percent": 100.0,
                "speed": None,
                "eta": 0,
                "message": message,
                "state": "finished",
                "elapsed": round(elapsed, 1),
            }
            if result:
                data["result"] = result
            self._send(data)

    def error(self, message: str):
        """إرسال رسالة خطأ."""
        with self._lock:
            self._send({
                "type": "error",
                "phase": PHASES[self.current_phase_index] if self.current_phase_index < len(PHASES) else "",
                "phase_index": self.current_phase_index,
                "total_phases": len(PHASES),
                "phase_percent": self.phase_percent,
                "overall_percent": self._calc_overall(),
                "speed": None,
                "eta": None,
                "message": message,
                "state": "error",
            })

    def info(self, message: str):
        """إرسال رسالة معلومات."""
        self._send({
            "type": "info",
            "message": message,
        })

    def _calc_overall(self) -> float:
        """حساب النسبة المئوية الإجمالية."""
        if not PHASES:
            return 0.0
        phase_weight = 100.0 / len(PHASES)
        completed = self.current_phase_index * phase_weight
        current = (self.phase_percent / 100.0) * phase_weight
        return min(100.0, round(completed + current, 1))
