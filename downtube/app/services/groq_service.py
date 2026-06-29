import os
import re
import json
import subprocess
import logging
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from faster_whisper import WhisperModel

from app.utils.srt_converter import (
    groq_json_to_srt,
    merge_short_segments,
    deduplicate_overlapping_segments,
    deduplicate_text_overlap,
    translate_segments_to_arabic,
    verify_arabic_output,
    _percent_arabic,
)

logger = logging.getLogger(__name__)

# ── Thread Pools ─────────────────────────────────────────────────────
# CPU-intensive tasks (local whisper, ffmpeg processing)
_cpu_executor = ThreadPoolExecutor(max_workers=1)

# ── Global Model for Local Fallback ─────────────────────────────────
_model = None
_model_lock = threading.Lock()

# ── Settings ────────────────────────────────────────────────────────
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "medium")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_MODEL_DIR = os.getenv("WHISPER_MODEL_DIR", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

CHUNK_DURATION_SEC = 540  # 9 دقائق — أقصى مدة لكل جزء
MAX_CONCURRENT_CHUNKS = 3  # أقصى عدد أجزاء بالتوازي (إدارة الذاكرة)
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"

ARABIC_RANGES = [
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFE70, 0xFEFF),
    (0xFB50, 0xFDFF),
]


class GroqServiceError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


# ── Helpers ──────────────────────────────────────────────────────────

def _has_arabic(text: str) -> bool:
    for c in text:
        cp = ord(c)
        for start, end in ARABIC_RANGES:
            if start <= cp <= end:
                return True
    return False


def _get_audio_mime(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    return {
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".webm": "audio/webm",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".opus": "audio/ogg",
    }.get(ext, "audio/mpeg")


def _get_duration(filepath: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", filepath]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return float(json.loads(r.stdout)["format"]["duration"])


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                model_path = WHISPER_MODEL_SIZE

                # إذا كان WHISPER_MODEL_DIR محدد — نستخدم cached path
                if WHISPER_MODEL_DIR:
                    model_path = WHISPER_MODEL_DIR
                    if not os.path.exists(model_path):
                        logger.info(
                            "النموذج غير موجود في %s — جاري التحميل...",
                            model_path,
                        )
                        os.makedirs(model_path, exist_ok=True)
                        _download_model(WHISPER_MODEL_SIZE, model_path)

                logger.info(
                    "تحميل نموذج faster-whisper %s على %s (%s)",
                    WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
                )
                _model = WhisperModel(
                    model_path,
                    device=WHISPER_DEVICE,
                    compute_type=WHISPER_COMPUTE_TYPE,
                    download_root=WHISPER_MODEL_DIR or None,
                )
                logger.info("تم تحميل النموذج بنجاح")
    return _model


def _download_model(model_size: str, target_dir: str):
    """تحميل نموذج faster-whisper إلى target_dir"""
    try:
        from huggingface_hub import snapshot_download

        repo_id = f"guillaumeklf/faster-whisper-{model_size}"
        logger.info("جاري تحميل النموذج من %s ...", repo_id)
        snapshot_download(
            repo_id=repo_id,
            local_dir=target_dir,
            local_dir_use_symlinks=False,
            resume_download=True,
        )
        logger.info("تم تحميل النموذج إلى %s", target_dir)
    except Exception as e:
        logger.warning(
            "فشل تحميل النموذج: %s — سيتم استخدام التحميل التلقائي",
            e,
        )


def initialize_whisper_model():
    """تحميل النموذج المحلي مسبقاً لتجنب التأخير في أول طلب"""
    _get_model()


# ── Audio Preprocessing ──────────────────────────────────────────────

async def preprocess_audio(input_path: str) -> str:
    """
    تحويل الصوت إلى 16kHz mono 64kbps mp3.
    Whisper يحتاج فقط 16kHz mono — الباقي هدر.
    64kbps يضمن جودة كافية لـ Groq Whisper API مقارنة بـ 32kbps.
    """
    output_path = str(Path(input_path).with_suffix(".preprocessed.mp3"))

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "16000",       # 16kHz sample rate
        "-ac", "1",           # mono
        "-b:a", "64k",        # 64kbps bitrate (كان 32k — ضعيف جداً لـ Groq)
        "-map_metadata", "-1",
        output_path,
    ]

    def _run():
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.warning("فشل تحويل الصوت: %s — استخدام الملف الأصلي", result.stderr[:200])
            return input_path
        # تحقق أن الملف الناتج أصغر ومقبول
        orig_size = os.path.getsize(input_path)
        new_size = os.path.getsize(output_path)
        if new_size == 0:
            logger.warning("الملف المحول فارغ — استخدام الملف الأصلي")
            os.unlink(output_path)
            return input_path
        logger.info("تحويل الصوت: %s → %s (%.1fMB → %.1fMB)",
                     os.path.basename(input_path), os.path.basename(output_path),
                     orig_size / 1e6, new_size / 1e6)
        return output_path

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_cpu_executor, _run)


# ── Audio Chunking ───────────────────────────────────────────────────

async def split_audio_chunks(
    audio_path: str,
    chunk_duration_sec: int = CHUNK_DURATION_SEC,
) -> list[tuple[str, float]]:
    """
    تقسيم ملف الصوت إلى أجزاء بحجم أقصى chunk_duration_sec.
    يحاول القسمة عند فترات الصمت لتجنب قطع الجمل.
    كل عنصر: (مسار_الملف, وقت_البداية_الفعلي)
    """
    total_duration = _get_duration(audio_path)

    if total_duration <= chunk_duration_sec:
        logger.info("الصوت أقل من %d ثانية — لا حاجة للتقسيم", chunk_duration_sec)
        return [(audio_path, 0.0)]

    # كشف نقاط الصمت
    silence_points = _detect_silence_points(audio_path)

    # حساب نقاط التقسيم
    split_points = []
    current_start = 0.0

    while current_start + chunk_duration_sec < total_duration:
        ideal_end = current_start + chunk_duration_sec

        # إيجاد أقرب نقطة صمت للوقت المثالي
        best_point = _find_nearest_silence(silence_points, ideal_end, window=30.0)
        if best_point is None:
            best_point = ideal_end

        # تأكد أن التقسيم لا يكرر نفس النقطة
        if best_point <= current_start + 10:
            best_point = current_start + chunk_duration_sec

        split_points.append(best_point)
        current_start = best_point

    # استخراج الأجزاء باستخدام FFmpeg
    chunk_files = []
    prev_point = 0.0
    base_path = Path(audio_path)

    for i, sp in enumerate(split_points):
        chunk_path = str(base_path.with_suffix(f".chunk{i}.mp3"))
        await _extract_chunk(audio_path, prev_point, sp, chunk_path)
        chunk_files.append((chunk_path, prev_point))
        prev_point = sp

    # الجزء الأخير
    chunk_path = str(base_path.with_suffix(f".chunk{len(split_points)}.mp3"))
    await _extract_chunk(audio_path, prev_point, total_duration, chunk_path)
    chunk_files.append((chunk_path, prev_point))

    logger.info("تم تقسيم الصوت (%.0f ثانية) إلى %d جزء", total_duration, len(chunk_files))
    return chunk_files


def _detect_silence_points(
    audio_path: str, noise_db: float = -30, min_silence_dur: float = 0.5
) -> list[float]:
    """كشف نقاط نهاية الصمت باستخدام FFmpeg silencedetect"""
    cmd = [
        "ffmpeg", "-i", audio_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_dur}",
        "-f", "null", "-",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        silence_ends = []
        for line in result.stderr.split("\n"):
            if "silence_end" in line:
                match = re.search(r"silence_end:\s*([\d.]+)", line)
                if match:
                    silence_ends.append(float(match.group(1)))
        logger.info("تم العثور على %d نقطة صمت", len(silence_ends))
        return silence_ends
    except Exception as e:
        logger.warning("فشل كشف الصمت: %s — سيتم التقسيم بالتساوي", e)
        return []


def _find_nearest_silence(
    silence_points: list[float], target: float, window: float = 30.0
) -> float | None:
    """إيجاد أقرب نقطة صمت للوقت المطلوب ضمن نافذة"""
    if not silence_points:
        return None

    best = None
    best_diff = window

    for sp in silence_points:
        diff = abs(sp - target)
        if diff < best_diff:
            best_diff = diff
            best = sp

    return best


async def _extract_chunk(
    audio_path: str, start: float, end: float, output_path: str
):
    """استخراج جزء من الصوت باستخدام FFmpeg مع دقة عالية في التحديد الزمني.
    - يحاول copy أولاً سريعاً
    - لو الـ start_time الفعلي للـ chunk أبعد من 0.1 ثانية → يعيد ترميز بالضبط
    - في النهاية يتأكد إن الملف صالح
    """
    duration = end - start

    def _probe_start_time(filepath: str) -> float | None:
        """استعلام عن وقت البداية الفعلي للملف"""
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_entries", "format=start_time", filepath],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                return float(data.get("format", {}).get("start_time", 0))
        except Exception:
            pass
        return None

    def _reencode(start: float, duration: float, output_path: str):
        """إعادة ترميز دقيقة — -ss قبل -i مع الترميز يعطي بداية مضبوطة"""
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", audio_path,
            "-t", str(duration),
            "-ar", "16000",
            "-ac", "1",
            "-b:a", "64k",
            output_path,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise GroqServiceError(f"فشل استخراج الجزء: {r.stderr[:200]}")
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise GroqServiceError(f"الجزء الناتج فارغ: {output_path}")

    def _verify_chunk(filepath: str) -> bool:
        """تحقق أن الملف موجود وصالح"""
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return False
        actual = _probe_start_time(filepath)
        if actual is None:
            return True  # لا يمكن الفحص — اقبل
        if actual > 0.1:
            logger.debug("chunk start_time=%.2f (>0.1) — غير دقيق", actual)
            return False
        duration_ok = _probe_duration_near(filepath, duration, tolerance=1.0)
        if not duration_ok:
            logger.debug("chunk duration غير مطابق — سيعاد")
            return False
        return True

    def _probe_duration_near(filepath: str, expected: float, tolerance: float = 1.0) -> bool:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_entries", "format=duration", filepath],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                data = json.loads(r.stdout)
                actual = float(data.get("format", {}).get("duration", 0))
                return abs(actual - expected) <= tolerance
        except Exception:
            pass
        return True  # لا يمكن الفحص — اقبل

    def _run():
        # ── محاولة copy أولاً ──
        cmd_copy = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", audio_path,
            "-t", str(duration),
            "-c", "copy",
            output_path,
        ]
        result = subprocess.run(cmd_copy, capture_output=True, text=True, timeout=120)

        copy_ok = (
            result.returncode == 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 0
        )

        if copy_ok and _verify_chunk(output_path):
            return

        # copy غير دقيق — احذف الملف الخاطئ وحاول re-encode
        if os.path.exists(output_path):
            try:
                os.unlink(output_path)
            except Exception:
                pass

        logger.debug("copy غير دقيق للجزء %.0f-%.0f — إعادة ترميز", start, end)
        _reencode(start, duration, output_path)

        if not _verify_chunk(output_path):
            raise GroqServiceError(f"chunk بعد re-encode لسه غير صالح: {output_path}")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_cpu_executor, _run)


# ── Groq Whisper API Transcription ───────────────────────────────────

async def _transcribe_chunk_groq(
    chunk_path: str, offset: float
) -> tuple[list[dict], str]:
    """
    نسخ جزء صوتي باستخدام Groq Whisper API.
    النموذج: whisper-large-v3-turbo (أسرع + جودة عالية).
    """
    from groq import Groq

    api_key = GROQ_API_KEY
    if not api_key or api_key == "your_groq_api_key_here":
        raise GroqServiceError("GROQ_API_KEY غير موجودة")

    client = Groq(api_key=api_key)

    def _call():
        with open(chunk_path, "rb") as f:
            mime = _get_audio_mime(chunk_path)
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(chunk_path), f, mime),
                model=GROQ_WHISPER_MODEL,
                response_format="verbose_json",
                temperature=0,
            )
        return transcription

    loop = asyncio.get_event_loop()
    try:
        transcription = await asyncio.wait_for(
            loop.run_in_executor(None, _call),
            timeout=120
        )
    except asyncio.TimeoutError:
        raise GroqServiceError("Groq Whisper API لم يستجب خلال 120 ثانية")

    # استخراج الشرائح مع تصحيح الـ timestamps
    segments = []
    detected_lang = getattr(transcription, "language", "unknown")

    segs_raw = transcription.segments if hasattr(transcription, "segments") else None
    if segs_raw:
        for seg in segs_raw:
            if isinstance(seg, dict):
                text = (seg.get("text") or "").strip()
                start = seg.get("start", 0) + offset
                end = seg.get("end", 0) + offset
            else:
                text = (getattr(seg, "text", None) or "").strip()
                start = getattr(seg, "start", 0) + offset
                end = getattr(seg, "end", 0) + offset
            if text:
                segments.append({"start": start, "end": end, "text": text})
    else:
        # Fallback: شريحة واحدة من النص الكامل
        full_text = ""
        duration = 0
        if isinstance(transcription, dict):
            full_text = (transcription.get("text") or "").strip()
            duration = transcription.get("duration", 0)
        else:
            full_text = (getattr(transcription, "text", None) or "").strip()
            duration = getattr(transcription, "duration", 0)
        if full_text:
            segments.append({"start": offset, "end": offset + duration, "text": full_text})

    return segments, detected_lang


# ── Local Fallback Transcription ─────────────────────────────────────

async def _transcribe_chunk_local(
    chunk_path: str, offset: float
) -> tuple[list[dict], str]:
    """نسخ جزء صوتي باستخدام faster-whisper المحلي (fallback)"""

    def _call():
        model = _get_model()
        segments_gen, info = model.transcribe(
            chunk_path,
            beam_size=5,
            vad_filter=True,
            language=None,
        )

        detected_lang = info.language
        results = []
        for seg in segments_gen:
            results.append({
                "start": seg.start + offset,
                "end": seg.end + offset,
                "text": seg.text.strip(),
            })
        return results, detected_lang

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_cpu_executor, _call)


# ── Smooth Progress Helper ───────────────────────────────────────────

class _SmoothProgress:
    """تتبع التقدم بنعومة — يُبلغ فقط عند تغير النسبة بمقدار 1% على الأقل"""

    def __init__(self, callback, start_pct: float, end_pct: float):
        self.callback = callback
        self.start_pct = start_pct
        self.end_pct = end_pct
        self.last_reported = -1

    def update(self, fraction: float, message: str = "", stage: str = ""):
        """fraction: 0.0 إلى 1.0"""
        pct = self.start_pct + fraction * (self.end_pct - self.start_pct)
        pct = max(self.start_pct, min(self.end_pct, pct))

        if int(pct) > self.last_reported:
            self.last_reported = int(pct)
            if self.callback:
                self.callback(pct, 0, 0, message)

    def finish(self, message: str = ""):
        pct = self.end_pct
        if int(pct) > self.last_reported:
            self.last_reported = int(pct)
            if self.callback:
                self.callback(pct, 0, 0, message)


# ── Main Generate Subtitles Function ─────────────────────────────────

async def generate_subtitles(
    audio_path: str,
    output_dir: str,
    task_id: str,
    title: str = "",
    progress_callback: callable = None,
) -> str:
    """
    توليد الترجمة بالمسار التالي:
    preprocess_audio → split_to_chunks → [Groq Whisper لكل chunk بالتوازي]
    → merge_results → translate_if_needed → SRT
    """
    # تحقق من وجود ملف الصوت
    if not audio_path or not os.path.exists(audio_path):
        raise GroqServiceError("ملف الصوت غير موجود")

    # تحقق من Groq API key
    use_groq = bool(GROQ_API_KEY and GROQ_API_KEY != "your_groq_api_key_here")
    if use_groq:
        logger.info("سيتم استخدام Groq Whisper API (%s)", GROQ_WHISPER_MODEL)
    else:
        logger.info("GROQ_API_KEY غير موجودة — سيتم استخدام faster-whisper المحلي")

    # ── Stage 1: Audio Prep (1% → 8%) ──
    progress = _SmoothProgress(progress_callback, 1, 8)
    progress.update(0.0, "جاري تحضير الصوت...", "audio_prep")

    try:
        # 1. معالجة مسبقة للصوت
        preprocessed_path = await preprocess_audio(audio_path)
        progress.update(0.5, "تم تحويل الصوت", "audio_prep")

        # 2. تقسيم إلى أجزاء
        chunks = await split_audio_chunks(preprocessed_path)
        total_chunks = len(chunks)
        progress.update(1.0, f"تم تقسيم الصوت إلى {total_chunks} جزء", "audio_prep")

        # ── Stage 2: Transcription (8% → 65%) ──
        transcribe_progress = _SmoothProgress(progress_callback, 8, 65)

        all_segments = []
        detected_lang = "unknown"
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHUNKS)
        completed_count = [0]
        lock = asyncio.Lock()

        async def _process_chunk(chunk_path: str, offset: float, chunk_idx: int):
            nonlocal detected_lang
            async with semaphore:
                segments = []
                lang = "unknown"

                try:
                    if use_groq:
                        try:
                            segments, lang = await _transcribe_chunk_groq(chunk_path, offset)
                        except Exception as e:
                            logger.warning("Groq API فشل للجزء %d: %s — إعادة المحاولة...", chunk_idx, e)
                            # Retry مرة واحدة
                            try:
                                segments, lang = await _transcribe_chunk_groq(chunk_path, offset)
                            except Exception as e2:
                                logger.warning("إعادة المحاولة فشلت: %s — استخدام local fallback", e2)
                                segments, lang = await _transcribe_chunk_local(chunk_path, offset)
                    else:
                        segments, lang = await _transcribe_chunk_local(chunk_path, offset)

                except Exception as e:
                    logger.error("فشل كامل للجزء %d: %s — تخطي", chunk_idx, e)
                    segments = []
                    lang = "unknown"
                finally:
                    # حذف ملف الجزء فوراً بعد المعالجة (إدارة الذاكرة)
                    try:
                        if "chunk" in chunk_path and os.path.exists(chunk_path):
                            os.unlink(chunk_path)
                            logger.debug("تم حذف الجزء المؤقت: %s", os.path.basename(chunk_path))
                    except Exception:
                        pass

                    # تحديث التقدم
                    async with lock:
                        all_segments.extend(segments)
                        if lang != "unknown":
                            detected_lang = lang
                        completed_count[0] += 1
                        done = completed_count[0]

                    fraction = done / total_chunks if total_chunks > 0 else 1.0
                    msg = f"جارٍ نسخ الجزء {done} من {total_chunks}..."
                    transcribe_progress.update(fraction, msg, "transcribing")

        # تشغيل جميع الأجزاء بالتوازي (مع semaphore)
        tasks = [
            _process_chunk(chunk_path, offset, i)
            for i, (chunk_path, offset) in enumerate(chunks)
        ]
        await asyncio.gather(*tasks)

        transcribe_progress.finish("تم نسخ الصوت بالكامل")

        # حذف الملف المحوّل مسبقاً
        if preprocessed_path != audio_path and os.path.exists(preprocessed_path):
            try:
                os.unlink(preprocessed_path)
            except Exception:
                pass

        if not all_segments:
            raise GroqServiceError("لم يتم التعرف على أي نص")

        # ── Stage 3: Merge & Sort (65% → 68%) ──
        if progress_callback:
            progress_callback(66, 0, 0, "جاري ترتيب المقاطع...")

        all_segments.sort(key=lambda s: s["start"])
        all_segments = deduplicate_overlapping_segments(all_segments)
        all_segments = merge_short_segments(all_segments)

        if progress_callback:
            progress_callback(68, 0, 0, "جاري فحص الحاجة للترجمة...")

        # ── Stage 4: Translation (68% → 90%) ──
        # الترجمة للعربية — تتم دائماً إلا لو 90%+ من النص عربي فعلاً
        pct_arabic = _percent_arabic(all_segments)
        needs_translation = pct_arabic < 90

        if needs_translation:
            if progress_callback:
                progress_callback(70, 0, 0, "جاري ترجمة النص...")
            loop = asyncio.get_event_loop()
            all_segments = await loop.run_in_executor(
                None,
                lambda: translate_segments_to_arabic(
                    all_segments, title,
                    source_lang=detected_lang if detected_lang != "unknown" else "",
                ),
            )
            all_segments = merge_short_segments(all_segments)

            # ── التحقق: لو الترجمة لسه فيها إنجليزي → إعادة ترجمة ببرومبت أشد ──
            if not verify_arabic_output(all_segments):
                logger.warning("الترجمة تحتوي على إنجليزية — إعادة ترجمة ببرومبت أشد")
                if progress_callback:
                    progress_callback(80, 0, 0, "إعادة ترجمة المقاطع غير العربية...")
                all_segments = await loop.run_in_executor(
                    None,
                    lambda: translate_segments_to_arabic(
                        all_segments, title + " (إعادة)",
                        source_lang="",
                    ),
                )
                all_segments = merge_short_segments(all_segments)
                if not verify_arabic_output(all_segments):
                    logger.warning("بعض المقاطع لا تزال تحتوي على إنجليزية بعد إعادة المحاولة")

            if progress_callback:
                progress_callback(90, 0, 0, "تمت الترجمة")
        else:
            logger.info("النص عربي (%d%%) — تخطي الترجمة عبر Llama", int(pct_arabic))
            if progress_callback:
                progress_callback(90, 0, 0, "لا حاجة للترجمة")

        # إزالة التكرار النصي بين المقاطع المتجاورة
        all_segments = deduplicate_text_overlap(all_segments)

        # ── Stage 5: Generate SRT (90% → 100%) ──
        if progress_callback:
            progress_callback(92, 0, 0, "جاري حفظ ملف الترجمة...")

        srt_content = groq_json_to_srt(all_segments)
        if not srt_content.strip():
            raise GroqServiceError("لم يتم التعرف على أي نص من ملف الصوت")

        safe_title = "".join(
            c for c in (title or task_id) if c.isalnum() or c in " ._-"
        ).strip() or task_id
        output_path = os.path.join(output_dir, f"{safe_title}.srt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        if progress_callback:
            progress_callback(100, 0, 0, "اكتملت الترجمة")

        return output_path

    except GroqServiceError:
        raise
    except Exception as e:
        logger.exception("خطأ في توليد الترجمة")
        raise GroqServiceError(str(e))


# ── Legacy local-only transcription (kept for direct use) ────────────

def _transcribe_local(
    audio_path: str,
    total_duration: float,
    progress_callback: callable = None,
) -> tuple[list[dict], str]:
    """نسخ محلي باستخدام faster-whisper (الطريقة القديمة)"""
    model = _get_model()
    segments_gen, info = model.transcribe(
        audio_path,
        beam_size=5,
        vad_filter=True,
        language=None,
    )

    detected_lang = info.language
    lang_prob = info.language_probability
    logger.info("اللغة المكتشفة: %s (احتمال: %.1f%%)", detected_lang, lang_prob * 100)

    results = []
    last_pct = -1
    for seg in segments_gen:
        results.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
        if progress_callback and total_duration > 0:
            pct = min(95, (seg.end / total_duration) * 95)
            if int(pct) != last_pct:
                last_pct = int(pct)
                progress_callback(pct, 0, 0)

    return results, detected_lang
