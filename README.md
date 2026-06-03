<div align="center">
  <br>

  # DownTube v3.0 — YouTube Downloader

  **تحميل فيديوهات يوتيوب مع الترجمات بسهولة وأمان**

  [![Python](https://img.shields.io/badge/Python-3.10%2B-ff4444?style=flat-square&logo=python&logoColor=white)](https://python.org)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
  [![yt-dlp](https://img.shields.io/badge/yt--dlp-2024%2B-282828?style=flat-square&logo=youtube&logoColor=ff4444)](https://github.com/yt-dlp/yt-dlp)

  <br>

  **FastAPI Web UI** · **WebSocket Progress** · **Arabic Subtitles** · **Comprehensive Tests**

  <br>
</div>

---

## Overview

DownTube is a YouTube video downloader with a clean FastAPI web interface. It supports downloading videos with Arabic (and English) subtitles as **separate files** — not embedded — for maximum compatibility.

---

## Features

- **FastAPI Web UI** — Modern dark-themed RTL interface
- **Real-time progress** — WebSocket-based live download progress
- **Arabic subtitle support** — Downloads official and auto-generated subtitles separately
- **Subtitle detection** — Uses file modification time (mtime) for reliable subtitle matching
- **Language prefix matching** — Supports language variants (ar, ar-SA, ar-EG, etc.)
- **Disk space check** — 20% buffer before download starts
- **Retry with backoff** — Network errors retried up to 3 times with [2, 5, 10]s delays
- **FFmpeg auto-detection** — Searches bundled → PATH → project directory
- **Cancellation support** — Cancel any download in progress

---

## Installation

### Prerequisites
- Python 3.10 or higher
- FFmpeg (for video merging)

### Setup

```bash
# Clone the repository
git clone https://github.com/mohamedhaithemx/DownTube.git
cd DownTube
git checkout fastapi-app

# Install dependencies
pip install -r requirements.txt

# Install FFmpeg
# Ubuntu/Debian
sudo apt install ffmpeg
# macOS
brew install ffmpeg
# Windows — download from https://ffmpeg.org/download.html
```

---

## Usage

```bash
# Start the web server
python run.py

# Or with custom options
python -m youtube_downloader --port 8080 --host 0.0.0.0

# Debug mode
python -m youtube_downloader --debug
```

Open your browser at **http://127.0.0.1:8554**

---

## Project Structure

```
youtube_downloader/
├── __init__.py
├── __main__.py          # python -m entry point
├── main.py              # Server startup (uvicorn)
├── app.py               # FastAPI app, routes, WebSocket
├── config.py            # All constants
├── downloader.py        # yt-dlp download logic
├── subtitle_manager.py  # Subtitle file detection and renaming
├── error_handler.py     # Exception mapping + retry logic
├── exceptions.py        # Custom exception classes
├── ffmpeg_utils.py      # FFmpeg detection and path resolution
├── assets/
│   └── icon.ico
├── templates/
│   └── index.html       # Web UI
└── static/              # CSS/JS assets
tests/
├── __init__.py
├── test_config.py
├── test_exceptions.py
├── test_ffmpeg_utils.py
├── test_downloader.py
├── test_subtitle_manager.py
├── test_error_handler.py
└── test_app.py
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/api/state` | Current download state |
| `POST` | `/api/download` | Start download |
| `POST` | `/api/cancel` | Cancel current download |
| `GET` | `/api/info?url=` | Get video metadata |
| `GET` | `/api/languages` | Supported languages |
| `GET` | `/api/download-dir` | Get download directory |
| `POST` | `/api/download-dir` | Set download directory |
| `WS` | `/ws` | Real-time progress updates |

---

## Architecture

### Threading Model
- Download runs in a **background thread** (NOT asyncio)
- Communication via `queue.Queue` — background thread NEVER touches FastAPI objects
- Cancellation via `threading.Event`
- State machine: `IDLE → RUNNING → FINISHED → IDLE`

### Subtitle Handling
- Subtitles saved as **separate files** (`.srt`/`.vtt`) alongside the video
- Detection uses **file modification time** (not title string matching)
- Language matching uses **prefix matching** (ar → ar, ar-SA, ar-EG)
- Naming convention: `{title}_SUBTITLE_{lang}.{format}`

---

## Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_downloader.py -v
```

---

## License

MIT License — feel free to use and modify.

---

<div align="center">
  <sub>Built with ❤️ using Python, FastAPI, and yt-dlp</sub>
  <br>
  <sub>DownTube v3.0.0</sub>
</div>
