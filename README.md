<div align="center">
  <br>

  # DownTube - YouTube Downloader

  **تحميل فيديوهات يوتيوب مع الترجمات بسهولة وأمان**

  [![Python](https://img.shields.io/badge/Python-3.9%2B-ff4444?style=flat-square&logo=python&logoColor=white)](https://python.org)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
  [![yt-dlp](https://img.shields.io/badge/yt--dlp-2024%2B-282828?style=flat-square&logo=youtube&logoColor=ff4444)](https://github.com/yt-dlp/yt-dlp)
  [![Flet](https://img.shields.io/badge/Flet-0.21%2B-448aff?style=flat-square&logo=flutter&logoColor=white)](https://flet.dev)

  <br>

  **Desktop Web UI** · **Mobile App** · **Anti-Ban Protection** · **Subtitle Support**

  <br>
</div>

---

## Overview

DownTube is a powerful YouTube downloader with two interfaces:

- **Desktop Version** — Web UI built with FastAPI, modern responsive design
- **Mobile Version** — Native-looking app built with Flet framework

It downloads both **video** and **subtitles** with advanced anti-ban strategies to avoid YouTube rate limiting.

---

## Features

| Feature | Desktop | Mobile |
|---------|:-------:|:------:|
| Video Info Fetching | ✅ | ✅ |
| Video Download (best/720p/480p) | ✅ | ✅ |
| Subtitle Download (SRT/VTT) | ✅ | ✅ |
| Auto Subtitles | ✅ | ✅ |
| Anti-Ban Protection | ✅ | ✅ |
| Cookies Import | ✅ | ❌ |
| Download Manager | ✅ | ❌ |
| Dark Theme | ✅ | ✅ |

### Anti-Ban System
- User-Agent rotation (15+ browsers/devices)
- YouTube client switching (`web` / `android`)
- Smart request delays with progressive backoff
- HTTP 429 detection and automatic cooldown
- Session limits to prevent detection
- Cookie support to raise download limits

### Subtitle Features
- Download handwritten and auto-generated subtitles
- Convert between SRT and VTT formats
- Timing adjustment for perfect sync
- Clean formatting and duplicate removal

---

## Installation

### Prerequisites
- Python 3.9 or higher
- pip (Python package manager)

### Setup

```bash
# Clone the repository
git clone https://github.com/mohamedhaithemx/DownTube.git
cd DownTube

# Install dependencies
pip install -r requirements.txt

# Optional: Install FFmpeg for video merging
# Ubuntu/Debian
sudo apt install ffmpeg
# macOS
brew install ffmpeg
```

---

## Usage

### Desktop Version (Web UI)

```bash
./run_desktop.sh
# Or directly:
python3 desktop/main.py
```

Open your browser at **http://localhost:8555**

### Mobile Version (Flet App)

```bash
./run_mobile.sh
# Or directly:
python3 mobile/main.py
```

---

## Desktop Web UI

The web interface features:

- **Dark theme** with responsive RTL design
- **Real-time progress** via WebSocket
- **Step indicators** for download stages
- **Cookie manager** to import YouTube cookies
- **Download history** with file management
- **Anti-ban status** dashboard

---

## Project Structure

```
youtube-downloader/
├── core/
│   ├── __init__.py
│   ├── anti_ban.py
│   ├── cookie_manager.py
│   ├── downloader.py
│   ├── models.py
│   └── subtitle_handler.py
├── desktop/
│   ├── main.py
│   └── static/
│       ├── index.html
│       ├── script.js
│       └── style.css
├── mobile/
│   └── main.py
├── requirements.txt
├── run_desktop.sh
└── run_mobile.sh
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/api/health` | Server health check |
| `GET` | `/api/video/info` | Fetch video metadata |
| `POST` | `/api/download` | Full download (video + subtitle) |
| `POST` | `/api/download/subtitle` | Subtitle only |
| `POST` | `/api/download/video` | Video only |
| `POST` | `/api/cancel` | Cancel current download |
| `GET` | `/api/progress` | Current progress status |
| `GET` | `/api/downloads` | List downloaded files |
| `GET` | `/api/download/file` | Download a file |
| `DELETE` | `/api/download/file` | Delete a file |
| `GET` | `/api/anti-ban/status` | Anti-ban system status |
| `POST` | `/api/anti-ban/reset` | Reset anti-ban session |
| `POST` | `/api/cookies/set` | Set cookies (paste) |
| `POST` | `/api/cookies/upload` | Upload cookies file |
| `GET` | `/api/cookies/status` | Cookies status |
| `DELETE` | `/api/cookies/remove` | Remove cookies |
| `WS` | `/ws` | Real-time progress updates |

---

## Cookies (رفع حد التحميل)

YouTube يحد من التحميل المجهول بقوة. استخدام الكوكيز **يرفع الحد بشكل كبير**:

1. ثبّت إضافة [cookies.txt export](https://chromewebstore.google.com)
2. سجّل الدخول ليوتيوب في المتصفح
3. اضغط على الإضافة → **Copy** أو **Export**
4. الصق المحتوى أو ارفع الملف في الواجهة

مع الكوكيز: **~50 طلب/جلسة** | بدون: **~15 طلب/جلسة**

---

## License

MIT License — feel free to use and modify.

---

<div align="center">
  <sub>Built with ❤️ using Python, FastAPI, and Flet</sub>
  <br>
  <sub>DownTube v1.0.0</sub>
</div>
