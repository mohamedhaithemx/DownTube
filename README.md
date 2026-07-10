<div align="center">
  <h1>DownTube</h1>
  <p><strong>YouTube Video Downloader with AI-Powered Arabic Subtitles</strong></p>
  <p>تحميل فيديوهات يوتيوب مع الترجمة العربية بالذكاء الاصطناعي</p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/Groq_Whisper-LLM-FF6600?style=flat-square&logo=groq&logoColor=white" alt="Groq">
    <img src="https://img.shields.io/badge/yt--dlp-2024%2B-EE0000?style=flat-square&logo=youtube&logoColor=white" alt="yt-dlp">
    <img src="https://img.shields.io/badge/WebSocket-Realtime-4FC08D?style=flat-square&logo=websocket&logoColor=white" alt="WebSocket">
    <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">
    <img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" alt="License">
  </p>
</div>

---

##نظرة عامة

تطبيق **DownTube** هو تطبيق ويب متكامل لتحميل فيديوهات **YouTube** مع دعم كامل للترجمة العربية:

- **تحميل بجودة عالية** — يدعم حتى 1080p H.264 مع صوت AAC
- **ترجمة عربية تلقائية** — يسحب الترجمة من يوتيوب أو يولدها بـ **Groq Whisper AI**
- **ترجمة احترافية** — ترجمة أدبية عبر **Llama 3.3 70B** تفهم السياق
- **نموذج Whisper محلي** — fallback محلي بسرعة **faster-whisper-medium** (1.5 GB)
- **دعم WebSocket** — بث مباشر لتقدم التحميل
- **واجهة RTL عربية** — تصميم Dark Blue Tech
- **Docker جاهز** — شغّل بـ أمر واحد

---

## الميزات

| الميزة | الوصف |
|--------|-------|
| تحميل الفيديو | جودات 1080p / 720p / 480p / 360p + صوت فقط |
| صوت نقي | AAC 192kbps — متوافق مع كل الأجهزة |
| ترجمة رسمية | يسحب الترجمة العربية من يوتيوب تلقائياً |
| توليد AI | **Groq Whisper** لنسخ الصوت + **Llama 70B** للترجمة |
| Whisper محلي | **faster-whisper-medium** كـ fallback عند توفر النموذج |
| بث مباشر | WebSocket يعرض نسبة التقدم والسرعة والوقت المتبقي |
| واجهة عربية | تصميم كامل RTL بألوان Dark Blue Tech |
| Docker | نشر فوري بدون تعقيدات |

---

## هيكل المشروع

```
downtube/
├── app/
│   ├── main.py                 # FastAPI + middleware + static files
│   ├── routers/
│   │   ├── info.py             # معلومات الفيديو (GET /api/v1/info)
│   │   ├── download.py         # تحميل الفيديو (POST /api/v1/download/video)
│   │   └── subtitles.py        # تحميل الترجمة فقط
│   ├── services/
│   │   ├── youtube_service.py  # منطق yt-dlp — تحميل + دمج + ضمان الصوت
│   │   ├── groq_service.py     # Groq Whisper نسخ + Llama ترجمة
│   │   └── subtitle_service.py # إدارة الترجمة (يوتيوب / توليد)
│   └── utils/
│       ├── file_manager.py     # إدارة الملفات المؤقتة + التنظيف
│       ├── srt_converter.py    # معالجة SRT + ترجمة LLM
│       ├── validators.py       # التحقق من روابط يوتيوب
│       └── cache.py            # كاشة الذاكرة
├── frontend/
│   ├── index.html              # الصفحة الرئيسية (RTL عربي)
│   ├── css/style.css           # تصميم Dark Blue Tech
│   └── js/app.js               # المنطق (WebSocket + واجهة)
├── models/whisper/             # نموذج faster-whisper-medium (محلي)
├── docker-compose.yml          # نشر Docker
├── .env.example                # قالب متغيرات البيئة
└── requirements.txt            # الاعتماديات
```

---

## التشغيل السريع

### Docker (موصى به)

```bash
# 1. استنساخ المستودع
git clone https://github.com/mohamedhaithemx/DownTube.git
cd DownTube

# 2. إعداد المتغيرات
cp downtube/.env.example downtube/.env
# افتح .env وأضف GROQ_API_KEY (مجاني من console.groq.com)

# 3. شغّل
cd downtube && docker-compose up --build
# افتح http://localhost:8080
```

### تشغيل محلي

```bash
# 1. تثبيت المتطلبات
pip install -r downtube/requirements.txt

# 2. إعداد .env
cp downtube/.env.example downtube/.env
# أضف GROQ_API_KEY

# 3. تشغيل الخادم
cd downtube && uvicorn app.main:app --host 0.0.0.0 --port 8000
# افتح http://localhost:8000
```

---

## متغيرات البيئة

| المتغير | الإجباري | الشرح | الافتراضي |
|---------|----------|-------|-----------|
| `GROQ_API_KEY` | نعم | مفتاح Groq API | — |
| `WHISPER_MODEL_SIZE` | لا | حجم النموذج المحلي | `medium` |
| `WHISPER_DEVICE` | لا | الجهاز (cpu/cuda) | `cpu` |
| `WHISPER_COMPUTE_TYPE` | لا | نوع الحوسبة | `int8` |
| `TEMP_DIR` | لا | مجلد الملفات المؤقتة | `/tmp/downtube` |
| `FILE_TTL_MINUTES` | لا | مدة بقاء الملفات | `10` |
| `MAX_DURATION_VIDEO_SUBTITLE` | لا | أقصى مدة بالثواني | `14400` |
| `RATE_LIMIT` | لا | حد الطلبات/دقيقة | `10/minute` |
| `PORT` | لا | منفذ الخادم | `8080` |

---

## API Endpoints

| المسار | الطريقة | الوظيفة |
|--------|---------|---------|
| `/api/v1/info?url=` | GET | جلب معلومات الفيديو + التنسيقات |
| `/api/v1/download/video` | POST | بدء تحميل الفيديو (يُعيد task_id) |
| `/api/v1/download/file/{task_id}` | GET | تحميل الملف النهائي |
| `/api/v1/download/cancel/{task_id}` | POST | إلغاء التحميل الجاري |
| `/api/v1/download/ws/{task_id}` | WebSocket | بث تقدم التحميل المباشر |
| `/api/v1/subtitles/download` | GET | تحميل الترجمة فقط |

---

## نظام الترجمة — ثلاث طبقات

1. **YouTube Official** — يسحب الترجمة العربية الرسمية لو موجودة
2. **YouTube Auto** — يسحب الترجمة التلقائية لو يوتيوب وفرها
3. **Groq AI Generation** — لو مفيش ترجمة:
   - يحمّل الصوت من الفيديو
   - **Whisper-large-v3** (Groq API) ينسخ الصوت لنص
   - **Llama 3.3 70B** يترجم النص لعربية طبيعية
   - **faster-whisper-medium** (محلي) كـ fallback لو Groq غير متاح

---

## التقنيات

| التقنية | الاستخدام |
|---------|-----------|
| Python 3.11+ | لغة التطوير |
| FastAPI | إطار العمل (ASGI) |
| yt-dlp | تحميل فيديوهات يوتيوب |
| Groq SDK | Whisper ASR + Llama Translation |
| faster-whisper | نموذج Whisper محلي (fallback) |
| WebSocket | بث التقدم المباشر |
| Pydantic | التحقق من البيانات |
| Docker | تغليف ونشر التطبيق |

---

## الترخيص

MIT License — ZET Dev

---

<div align="center">
  <p>Made by ZET Dev</p>
  <p>
    <a href="https://github.com/mohamedhaithemx/DownTube">GitHub</a> &bull;
    <a href="https://console.groq.com">Groq Console</a>
  </p>
</div>
