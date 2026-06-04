# DownTube — ZET Dev

<div dir="rtl">

**DownTube** هو تطبيق ويب لتحميل فيديوهات يوتيوب مع الترجمة العربية، مدعوم بالذكاء الاصطناعي عبر Groq API.

## المميزات

- تحميل فيديوهات يوتيوب بجودات متعددة (1080p / 720p / 480p / 360p / صوت فقط)
- تحميل الترجمة العربية تلقائياً من يوتيوب
- توليد الترجمة العربية تلقائياً باستخدام **Groq Whisper API** إذا لم تكن متوفرة
- عرض التقدم مباشر عبر WebSocket
- واجهة مستخدم عصرية باللغة العربية (تصميم Ocean-Blue)
- معبأ بالكامل كحاوية Docker
- يعمل بدون تحميل نماذج ذكاء اصطناعي محلية (خفيف وسريع)

## التقنيات المستخدمة

- **Backend:** Python 3.11 + FastAPI + yt-dlp + Groq SDK
- **Frontend:** HTML5 + CSS3 + JavaScript (بدون إطارات)
- **الاتصال المباشر:** WebSocket
- **التغليف:** Docker + docker-compose

## متطلبات التشغيل

1. **Docker** و **docker-compose** مثبتين على جهازك
2. **مفتاح Groq API** (مجاني) — احصل عليه من [console.groq.com](https://console.groq.com)

## طريقة التشغيل السريع

```bash
# 1. استنساخ المستودع
git clone <your-repo-url>
cd downtube

# 2. إنشاء ملف البيئة
cp .env.example .env
# ثم افتح .env وأضف GROQ_API_KEY الخاص بك

# 3. تشغيل التطبيق
docker-compose up --build

# 4. افتح المتصفح
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
| `FILE_TTL_MINUTES` | مدة بقاء الملفات (دقائق) | 10 |
| `MAX_DURATION_SECONDS` | أقصى مدة فيديو مسموحة | 7200 |
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

**DownTube** is a YouTube video downloader web application with Arabic subtitle support powered by AI via the Groq API.

## Features

- Download YouTube videos in multiple qualities (1080p / 720p / 480p / 360p / Audio only)
- Automatic Arabic subtitle fetching from YouTube
- AI-powered Arabic subtitle generation via **Groq Whisper API** (when unavailable)
- Real-time WebSocket progress updates
- Modern Arabic UI with Ocean-Blue design
- Fully containerized as a Docker image
- No local AI model downloads (lightweight & fast)

## Tech Stack

- **Backend:** Python 3.11 + FastAPI + yt-dlp + Groq SDK
- **Frontend:** HTML5 + CSS3 + Vanilla JavaScript
- **Real-time:** WebSocket
- **Deployment:** Docker + docker-compose

## Quick Start

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd downtube

# 2. Create environment file
cp .env.example .env
# Open .env and add your GROQ_API_KEY

# 3. Run with Docker
docker-compose up --build

# 4. Open browser
# http://localhost:8080
```

## Local Development (without Docker)

```bash
pip install -r app/requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## License

MIT License — ZET Dev
