import os
import asyncio
import json
import logging
import subprocess
import shlex
import re
import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import yt_dlp

from app.utils.validators import ERROR_MESSAGES

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

YDL_OPTS_BASE = {
    "quiet": True,
    "no_warnings": True,
    "nocheckcertificate": True,
    "extract_flat": False,
    "retries": 5,
    "fragment_retries": 5,
    "socket_timeout": 120,
    "extractor_args": {"youtube": {"skip": ["dash", "hls", "webpage", "comments"]}},
    "sleep_interval_requests": 0.5,
    "concurrent_fragment_downloads": 8,
    "throttledratelimit": 100000,
    "buffersize": "16K",
}

YDL_RETRIES = 4
YDL_DELAY = 3


class YouTubeError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


def _map_ydl_error(err_msg: str) -> str:
    err_lower = err_msg.lower()
    if "private video" in err_lower or "private" in err_lower:
        return ERROR_MESSAGES["private"]
    if "video unavailable" in err_lower or "deleted" in err_lower:
        return ERROR_MESSAGES["unavailable"]
    if "age" in err_lower or "restricted" in err_lower:
        return ERROR_MESSAGES["age_restricted"]
    if "geo" in err_lower or "geo-restricted" in err_lower or "not available in your country" in err_lower:
        return ERROR_MESSAGES["geo_restricted"]
    if "timeout" in err_lower or "timed out" in err_lower:
        return ERROR_MESSAGES["timeout"]
    if "not found" in err_lower or "404" in err_lower:
        return ERROR_MESSAGES["not_found"]
    return ERROR_MESSAGES["download_failed"]


def _make_ydl_opts(**extra) -> dict:
    opts = {**YDL_OPTS_BASE}
    opts["user_agent"] = random.choice(USER_AGENTS)
    opts.update(extra)
    return opts


def _ydl_opts_to_cli(opts: dict) -> list[str]:
    args = []
    for key, value in opts.items():
        if key == "quiet" and value:
            args.append("--quiet")
        elif key == "no_warnings" and value:
            args.append("--no-warnings")
        elif key == "nocheckcertificate" and value:
            args.append("--no-check-certificates")
        elif key == "extract_flat" and value:
            args.append("--extract-flat")
        elif key == "retries" and isinstance(value, int):
            args.extend(["--retries", str(value)])
        elif key == "fragment_retries" and isinstance(value, int):
            args.extend(["--fragment-retries", str(value)])
        elif key == "socket_timeout" and isinstance(value, int):
            args.extend(["--socket-timeout", str(value)])
        elif key == "user_agent" and value:
            args.extend(["--user-agent", value])
        elif key == "extractor_args" and isinstance(value, dict):
            for extractor, extractor_opts in value.items():
                for opt_key, opt_values in extractor_opts.items():
                    joined = ",".join(opt_values) if isinstance(opt_values, list) else str(opt_values)
                    args.extend(["--extractor-args", f"{extractor}:{opt_key}={joined}"])
        elif key == "sleep_interval_requests":
            args.extend(["--sleep-requests", str(value)])
    return args


async def _run_ytdlp(url: str, extra_args: list[str] | None = None, timeout: int = 120) -> dict[str, Any]:
    process = None
    try:
        base_opts = _make_ydl_opts()
        cli_args = _ydl_opts_to_cli(base_opts)
        cmd = ["yt-dlp", "--dump-json", "--no-playlist", *cli_args]
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(url)

        logger.debug("تشغيل yt-dlp: %s", " ".join(cmd))

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )

        if process.returncode == 0 and stdout:
            return json.loads(stdout.decode("utf-8"))

        error_msg = stderr.decode("utf-8", errors="replace") if stderr else ""
        raise YouTubeError(_map_ydl_error(error_msg), status_code=404)

    except asyncio.TimeoutError:
        raise YouTubeError(ERROR_MESSAGES["timeout"], status_code=408)

    except json.JSONDecodeError:
        raise YouTubeError(ERROR_MESSAGES["internal_error"], status_code=500)

    except Exception as e:
        if isinstance(e, YouTubeError):
            raise
        logger.exception("خطأ غير متوقع في yt-dlp")
        raise YouTubeError(ERROR_MESSAGES["internal_error"], status_code=500)

    finally:
        if process and process.returncode is None:
            try:
                process.kill()
            except Exception:
                pass


async def _extract_info_impl(url: str, timeout: int = 180) -> dict[str, Any]:
    loop = asyncio.get_event_loop()

    def _sync():
        opts = _make_ydl_opts(
            format="best[height<=1080]+bestaudio/best",
            socket_timeout=30,
            noplaylist=True,
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_executor, _sync),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise YouTubeError(ERROR_MESSAGES["timeout"], status_code=408)
    except yt_dlp.utils.DownloadError as e:
        raise YouTubeError(_map_ydl_error(str(e)), status_code=404)
    except Exception as e:
        logger.exception("خطأ غير متوقع في extract_info")
        raise YouTubeError(ERROR_MESSAGES["internal_error"], status_code=500)


async def extract_info_flat(url: str, timeout: int = 45) -> dict[str, Any]:
    loop = asyncio.get_event_loop()

    def _sync():
        opts = _make_ydl_opts(
            noplaylist=True,
            socket_timeout=15,
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_executor, _sync),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise YouTubeError(ERROR_MESSAGES["timeout"], status_code=408)
    except yt_dlp.utils.DownloadError as e:
        raise YouTubeError(_map_ydl_error(str(e)), status_code=404)
    except Exception as e:
        logger.exception("خطأ غير متوقع في extract_info_flat")
        raise YouTubeError(ERROR_MESSAGES["internal_error"], status_code=500)


async def extract_info(url: str, timeout: int = 180) -> dict[str, Any]:
    for attempt in range(YDL_RETRIES):
        try:
            return await _extract_info_impl(url, timeout=timeout)
        except YouTubeError as e:
            if attempt < YDL_RETRIES - 1:
                logger.warning("محاولة extract_info %d/%d فشلت: %s", attempt + 1, YDL_RETRIES, str(e)[:100])
                await asyncio.sleep(YDL_DELAY * (attempt + 1))
                continue
            raise
    raise YouTubeError(ERROR_MESSAGES["timeout"], status_code=408)


async def download_video(
    url: str,
    output_dir: str,
    format_id: str = "best",
    progress_callback: callable = None,
    cancel_event: asyncio.Event = None,
) -> str:
    def progress_hook(d: dict):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = (downloaded / total) * 100
                speed = d.get("speed", 0) or 0
                eta = d.get("eta", 0) or 0
                if progress_callback:
                    progress_callback(pct, speed, eta)
        elif d.get("status") == "finished":
            if progress_callback:
                progress_callback(100, 0, 0)

    def _sync_download():
        if format_id == "audio-only":
            fmt = "bestaudio/best"
        elif not any(c in format_id for c in "+/|,"):
            fmt = f"{format_id}+bestaudio[ext=m4a][acodec^=mp4a]/best[ext=mp4]/best"
        else:
            fmt = format_id
        postprocessors = []
        if format_id == "audio-only":
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            })
        opts = _make_ydl_opts(
            outtmpl=f"{output_dir}/%(title)s.%(ext)s",
            format=fmt,
            merge_output_format="mp4",
            progress_hooks=[progress_hook],
            postprocessors=postprocessors,
            continuedl=True,
            noprogress=False,
        )
        if cancel_event:
            opts["nooverwrites"] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
            for f in sorted(os.listdir(output_dir), key=lambda x: os.path.getmtime(os.path.join(output_dir, x)), reverse=True):
                if f.endswith((".mp4", ".mkv", ".webm", ".avi", ".mov")):
                    return os.path.join(output_dir, f)
            return os.path.join(output_dir, "output.mp4")

    for attempt in range(YDL_RETRIES):
        try:
            loop = asyncio.get_event_loop()
            filename = await loop.run_in_executor(_executor, _sync_download)
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError()
            return filename
        except asyncio.CancelledError:
            raise
        except yt_dlp.utils.DownloadError as e:
            if attempt < YDL_RETRIES - 1:
                logger.warning("محاولة تحميل %d/%d فشلت", attempt + 1, YDL_RETRIES)
                await asyncio.sleep(YDL_DELAY * (attempt + 1))
                continue
            raise YouTubeError(_map_ydl_error(str(e)), status_code=400)
        except Exception as e:
            if isinstance(e, YouTubeError):
                raise
            logger.exception("خطأ في تحميل الفيديو")
            raise YouTubeError(ERROR_MESSAGES["download_failed"], status_code=500)

    raise YouTubeError(ERROR_MESSAGES["timeout"], status_code=408)


async def download_audio(
    url: str,
    output_dir: str,
    progress_callback: callable = None,
) -> str:
    def progress_hook(d: dict):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = (downloaded / total) * 100
                speed = d.get("speed", 0) or 0
                eta = d.get("eta", 0) or 0
                if progress_callback:
                    progress_callback(pct, speed, eta)
        elif d.get("status") == "finished":
            if progress_callback:
                progress_callback(100, 0, 0)

    def _sync_dl():
        opts = _make_ydl_opts(
            outtmpl=f"{output_dir}/%(title)s.%(ext)s",
            format="bestaudio/best",
            postprocessors=[{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            progress_hooks=[progress_hook],
            continuedl=True,
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename.rsplit(".", 1)[0] + ".mp3"

    for attempt in range(YDL_RETRIES):
        try:
            loop = asyncio.get_event_loop()
            filename = await asyncio.wait_for(
                loop.run_in_executor(_executor, _sync_dl),
                timeout=7200  # ساعتان للفيديوهات الطويلة (حتى 20 ساعة)
            )
            return filename
        except asyncio.TimeoutError:
            if attempt < YDL_RETRIES - 1:
                logger.warning("محاولة تحميل الصوت %d/%d فشلت (مهلة)", attempt + 1, YDL_RETRIES)
                await asyncio.sleep(YDL_DELAY * (attempt + 1))
                continue
            raise YouTubeError(ERROR_MESSAGES["timeout"], status_code=408)
        except asyncio.CancelledError:
            raise
        except yt_dlp.utils.DownloadError as e:
            if attempt < YDL_RETRIES - 1:
                logger.warning("محاولة تحميل الصوت %d/%d فشلت", attempt + 1, YDL_RETRIES)
                await asyncio.sleep(YDL_DELAY * (attempt + 1))
                continue
            raise YouTubeError(_map_ydl_error(str(e)), status_code=400)
        except YouTubeError:
            raise
        except Exception as e:
            logger.exception("خطأ في تحميل الصوت")
            if attempt < YDL_RETRIES - 1:
                await asyncio.sleep(YDL_DELAY * (attempt + 1))
                continue
            raise YouTubeError(ERROR_MESSAGES["download_failed"], status_code=500)

    raise YouTubeError(ERROR_MESSAGES["timeout"], status_code=408)


async def embed_subtitles(
    video_path: str,
    subtitle_path: str,
    output_dir: str,
    progress_callback: callable = None,
    cancel_event: "threading.Event" = None,
) -> str:
    def _sync_embed():
        base, ext = os.path.splitext(os.path.basename(video_path))
        output_path = os.path.join(output_dir, f"{base}_embedded{ext}")

        # Method 1: Soft subtitles via mov_text (instant, no re-encode)
        cmd_soft = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", subtitle_path,
            "-c:v", "copy",
            "-c:a", "copy",
            "-c:s", "mov_text",
            "-metadata:s:s:0", "language=ara",
            output_path,
        ]
        logger.info("محاولة دمج soft subtitles عبر mov_text")
        result_soft = subprocess.run(cmd_soft, capture_output=True, text=True, timeout=600)
        if result_soft.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info("تم الدمج بنجاح عبر mov_text (soft)")
            return output_path

        # Method 2: Hardsub via subtitles filter (slow but reliable)
        logger.warning("mov_text فشل، تجربة hardsub: %s", result_soft.stderr)
        output_path = os.path.join(output_dir, f"{base}_embedded{ext}")
        total_duration = 0
        dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path]
        dur_result = subprocess.run(dur_cmd, capture_output=True, text=True, timeout=30)
        try:
            total_duration = float(dur_result.stdout.strip())
        except (ValueError, TypeError):
            total_duration = 0

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"subtitles={shlex.quote(subtitle_path)}",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "copy",
            output_path,
        ]
        process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)

        last_pct = -1
        time_pattern = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
        while True:
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break
            if cancel_event and cancel_event.is_set():
                process.kill()
                raise RuntimeError("تم إلغاء دمج الترجمة")

            m = time_pattern.search(line)
            if m and total_duration > 0:
                hh, mm, ss, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                current_time = hh * 3600 + mm * 60 + ss + ms / 100
                pct = min(99, (current_time / total_duration) * 100)
                if int(pct) != last_pct:
                    last_pct = int(pct)
                    if progress_callback:
                        progress_callback(pct, 0, 0)

        returncode = process.wait()
        if returncode != 0:
            raise RuntimeError(f"فشل دمج الترجمة (hardsub): خطأ {returncode}")
        return output_path

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _sync_embed)
