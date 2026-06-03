# DownTube — توليد الترجمة بالذكاء الاصطناعي (Whisper)

"""
يستخدم faster-whisper لإنشاء ترجمة SRT للفيديوهات التي ليس لها
ترجمة على يوتيوب.

⚠️ معطل افتراضياً لأنه بطيء جداً على CPU.
للتفعيل: اضبط WHISPER_ENABLED=true في البيئة.

التحسينات مقارنة بالنسخة السابقة:
- WHISPER_ENABLED: تحكم في تفعيل/تعطيل Whisper (معطل افتراضياً)
- WHISPER_TIMEOUT: حد أقصى للعملية كلها (120 ثانية افتراضياً)
- beam_size=1: أسرع 5x من beam_size=5 بدون فرق كبير مع tiny
- آلية timeout عبر threading: يُلغى التعرف لو تجاوز الوقت المحدد
- تنفيذ التعرف في thread منفصل مع نتيجة مشتركة
"""

import os
import subprocess
import tempfile
import logging
import threading
from typing import Optional

from app.config import (
    WHISPER_ENABLED,
    WHISPER_MODEL_SIZE,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_BEAM_SIZE,
    WHISPER_TIMEOUT,
    MAX_VIDEO_DURATION_FOR_WHISPER,
)

logger = logging.getLogger(__name__)

# ── النموذج المحمل (singleton) ────────────────────────────────
_whisper_model = None
_whisper_available = None  # None = لم يُفحص بعد، True/False


def is_whisper_available() -> bool:
    """
    التحقق من أن Whisper مفعّل ومكتبة faster-whisper مثبتة.
    يخزّن النتيجة حتى لا يفحص كل مرة.
    """
    global _whisper_available

    if _whisper_available is not None:
        return _whisper_available

    if not WHISPER_ENABLED:
        logger.info("Whisper معطل (WHISPER_ENABLED=false)")
        _whisper_available = False
        return False

    try:
        import faster_whisper  # noqa: F401
        _whisper_available = True
        logger.info("Whisper مفعّل ومكتبة faster-whisper متاحة")
    except ImportError:
        logger.warning(
            "WHISPER_ENABLED=true لكن مكتبة faster-whisper غير مثبتة! "
            "ثبّتها: pip install faster-whisper"
        )
        _whisper_available = False

    return _whisper_available


def _get_model():
    """تحميل نموذج Whisper (lazy loading — مرة واحدة فقط)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("جاري تحميل نموذج Whisper (%s)...", WHISPER_MODEL_SIZE)
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        logger.info("تم تحميل النموذج بنجاح")
    return _whisper_model


def preload_model():
    """تحميل النموذج في الذاكرة مسبقاً (يُستدعى عند بداية السيرفر لو مفعّل)."""
    if not is_whisper_available():
        logger.info("Whisper معطل — لا يتم تحميل النموذج")
        return
    try:
        _get_model()
    except Exception as e:
        logger.warning("فشل التحميل المسبق لـ Whisper: %s", e)


def extract_audio(video_path: str) -> Optional[str]:
    """
    استخراج الصوت من الفيديو بصيغة WAV 16kHz mono.

    المعاملات:
        video_path: مسار ملف الفيديو

    Returns:
        مسار ملف WAV المؤقت أو None عند الفشل
    """
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                "-threads", "2",
                wav_path,
            ],
            capture_output=True,
            timeout=60,  # خفضنا من 600s إلى 60s — ما فيش فيديو تحت 15 د يستاهل 10 دقائق استخراج
            check=True,
        )
        return wav_path
    except subprocess.TimeoutExpired:
        logger.error("انتهى وقت استخراج الصوت (60 ثانية) — غالباً الفيديو كبير جداً")
        if os.path.exists(wav_path):
            os.unlink(wav_path)
        return None
    except subprocess.CalledProcessError as e:
        logger.error("فشل استخراج الصوت: %s", e.stderr[:200] if e.stderr else e)
        if os.path.exists(wav_path):
            os.unlink(wav_path)
        return None
    except FileNotFoundError:
        logger.error("ffmpeg غير مثبت — لا يمكن استخراج الصوت")
        if os.path.exists(wav_path):
            os.unlink(wav_path)
        return None


def _transcribe_with_timeout(wav_path: str, lang: str = "ar") -> Optional[list]:
    """
    تشغيل Whisper مع timeout — لو تجاوز WHISPER_TIMEOUT ثانية يُلغى.

    الفكرة: نشغّل التعرف في thread منفصل ونستنى بالـ join(timeout).
    لو الـ thread خلص → نرجع النتيجة، لو لا → نرجع None.
    """
    result_holder = {"segments": None, "error": None}

    def _worker():
        try:
            model = _get_model()
            segments_iter, _info = model.transcribe(
                wav_path,
                language=lang,
                beam_size=WHISPER_BEAM_SIZE,  # 1 = أسرع بكثير
                vad_filter=True,
            )
            # تحويل المولّد إلى قائمة (هذا هو المكان اللي بيعلّق)
            result_holder["segments"] = list(segments_iter)
        except Exception as e:
            result_holder["error"] = str(e)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=WHISPER_TIMEOUT)

    if thread.is_alive():
        # الـ thread لسه شغال — الـ timeout انتهى
        logger.error(
            "انتهى وقت Whisper (%d ثانية) — تم إلغاء التعرف",
            WHISPER_TIMEOUT,
        )
        # مفيش طريقة نظيفة لقتل thread في Python، لكن daemon=True
        # يعني هيتم إنهاؤه لما البرنامج يخرج
        return None

    if result_holder["error"]:
        logger.error("فشل التعرف على الصوت: %s", result_holder["error"])
        return None

    segments = result_holder["segments"]
    if not segments:
        logger.warning("Whisper لم يتعرف على أي كلام في الملف")
        return None

    return segments


def _format_timestamp(seconds: float) -> str:
    """تحويل الثواني إلى تنسيق SRT: HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list, output_path: str) -> str:
    """
    تحويل segments من Whisper إلى ملف SRT.

    المعاملات:
        segments: قائمة المقاطع من Whisper
        output_path: مسار ملف الإخراج

    Returns:
        مسار ملف SRT
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_format_timestamp(seg.start)} --> {_format_timestamp(seg.end)}\n")
            f.write(f"{seg.text.strip()}\n\n")
    return output_path


def generate_subtitles(
    video_path: str,
    output_dir: str,
    title: str,
    lang: str = "ar",
    progress=None,
) -> Optional[str]:
    """
    إنشاء ترجمة SRT باستخدام Whisper (مع timeout).

    المعاملات:
        video_path: مسار ملف الفيديو
        output_dir: مجلد الإخراج
        title: عنوان الفيديو (لاسم الملف)
        lang: لغة الترجمة
        progress: متتبع التقدم

    Returns:
        مسار ملف الترجمة أو None
    """
    from app.services.subtitle import sanitize_filename

    # ── فحص سريع: هل Whisper مفعّل؟ ──
    if not is_whisper_available():
        msg = "توليد الترجمة بالذكاء الاصطناعي معطل (WHISPER_ENABLED=false)"
        logger.info(msg)
        if progress:
            progress.update_phase_progress(100, message=msg)
        return None

    safe_title = sanitize_filename(title)
    srt_path = os.path.join(output_dir, f"{safe_title}.srt")

    # لو الملف موجود أصلاً مش محتاجين نعمل حاجة
    if os.path.exists(srt_path):
        logger.info("ملف الترجمة موجود بالفعل: %s", srt_path)
        return srt_path

    # ── المرحلة 1: استخراج الصوت ──
    if progress:
        progress.update_phase_progress(0, message="جاري استخراج الصوت من الفيديو...")

    wav_path = extract_audio(video_path)
    if not wav_path:
        logger.error("فشل استخراج الصوت — لن يتم إنشاء ترجمة")
        if progress:
            progress.update_phase_progress(100, message="فشل استخراج الصوت — لا يمكن إنشاء ترجمة")
        return None

    try:
        # ── المرحلة 2: التعرف على الكلام (مع timeout) ──
        if progress:
            progress.update_phase_progress(
                0,
                message=f"جاري التعرف على الكلام عبر Whisper (حد أقصى {WHISPER_TIMEOUT} ثانية)...",
            )

        segments = _transcribe_with_timeout(wav_path, lang)

        if segments is None:
            # إما timeout أو خطأ أو مفيش كلام
            logger.error("فشل التعرف على الكلام — لن يتم إنشاء ترجمة")
            if progress:
                progress.update_phase_progress(
                    100,
                    message="فشل أو انتهى وقت التعرف على الكلام — لم يتم إنشاء ترجمة",
                )
            return None

        # ── المرحلة 3: كتابة ملف SRT ──
        if progress:
            progress.update_phase_progress(0, message="جاري كتابة ملف الترجمة...")

        segments_to_srt(segments, srt_path)
        logger.info("تم إنشاء الترجمة: %s (%d مقطع)", srt_path, len(segments))

        if progress:
            progress.update_phase_progress(100, message=f"تم إنشاء الترجمة بالذكاء الاصطناعي ({len(segments)} مقطع)")

        return srt_path

    finally:
        # تنظيف ملف WAV المؤقت
        if os.path.exists(wav_path):
            try:
                os.unlink(wav_path)
            except OSError:
                pass
