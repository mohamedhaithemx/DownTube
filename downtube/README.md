# DownTube — ZET Dev

<div dir="rtl">

**DownTube** هو تطبيق ويب لتحميل فيديوهات يوتيوب مع الترجمة العربية، مدعوم بالذكاء الاصطناعي عبر Groq API + نموذج Whisper محلي.

## المميزات

- تحميل فيديوهات يوتيوب بجودات متعددة (1080p / 720p / 480p / 360p / صوت فقط)
- تحميل الترجمة العربية تلقائياً من يوتيوب
- توليد الترجمة العربية عبر **Groq Whisper API** مع **Llama 3.3 70B** للترجمة
- نموذج Whisper محلي **faster-whisper-medium** كـ fallback
- عرض التقدم مباشر عبر WebSocket
- واجهة عصرية باللغة العربية (تصميم Dark Blue Tech)
- معبأ بالكامل كحاوية Docker

## التقنيات

- **Backend:** Python 3.11 + FastAPI + yt-dlp + Groq SDK + faster-whisper
- **Frontend:** HTML5 + CSS3 + JavaScript (بدون إطارات)
- **الاتصال المباشر:** WebSocket
- **التغليف:** Docker + docker-compose

## التشغيل السريع

```bash
# 1. استنساخ المستودع
git clone https://github.com/mohamedhaithemx/DownTube.git
cd DownTube

# 2. إنشاء ملف البيئة
cp downtube/.env.example downtube/.env
# ثم افتح .env وأضف GROQ_API_KEY

# 3. تشغيل Docker
cd downtube && docker-compose up --build
# http://localhost:8080
```

## التشغيل المحلي (بدون Docker)

```bash
# 1. تثبيت المتطلبات
pip install -r app/requirements.txt

# 2. إنشاء ملف .env
cp .env.example .env
# أضف GROQ_API_KEY في .env

# 3. تشغيل الخادم
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## متغيرات البيئة

| المتغير | الشرح | الافتراضي |
|---------|-------|-----------|
| `GROQ_API_KEY` | مفتاح Groq API (إجباري) | — |
| `WHISPER_MODEL_SIZE` | حجم النموذج المحلي | medium |
| `WHISPER_DEVICE` | الجهاز (cpu/cuda) | cpu |
| `TEMP_DIR` | مجلد الملفات المؤقتة | /tmp/downtube |
| `FILE_TTL_MINUTES` | مدة بقاء الملفات (دقائق) | 10 |
| `RATE_LIMIT` | حد الطلبات لكل دقيقة | 10/minute |

## API

| المسار | الطريقة | الوظيفة |
|--------|---------|---------|
| `/api/v1/info?url=` | GET | معلومات الفيديو |
| `/api/v1/download/video` | POST | تحميل الفيديو |
| `/api/v1/download/file/{task_id}` | GET | تحميل الملف |
| `/api/v1/download/cancel/{task_id}` | POST | إلغاء التحميل |
| `/api/v1/download/ws/{task_id}` | WebSocket | تقدم التحميل |
| `/api/v1/subtitles/download?url=` | GET | تحميل الترجمة |

## الترخيص

MIT License — ZET Dev

</div>

---

# DownTube — ZET Dev

**DownTube** is a YouTube video downloader web app with Arabic subtitles powered by AI via Groq API + local Whisper model.

## Features

- Download YouTube videos in multiple qualities (1080p / 720p / 480p / 360p / Audio only)
- Automatic Arabic subtitle fetching from YouTube
- AI-powered transcription via **Groq Whisper** + translation via **Llama 3.3 70B**
- Local fallback: **faster-whisper-medium** model (1.5 GB)
- Real-time WebSocket progress updates
- Modern Arabic UI (Dark Blue Tech design)
- Fully containerized as a Docker image

## Tech Stack

- **Backend:** Python 3.11 + FastAPI + yt-dlp + Groq SDK + faster-whisper
- **Frontend:** HTML5 + CSS3 + Vanilla JavaScript
- **Real-time:** WebSocket
- **Deployment:** Docker + docker-compose

## Quick Start

```bash
git clone https://github.com/mohamedhaithemx/DownTube.git
cd DownTube
cp downtube/.env.example downtube/.env
# Add GROQ_API_KEY to .env
cd downtube && docker-compose up --build
# http://localhost:8080
```

## License

MIT License — ZET Dev
