<div align="center">
  <h1>🎥 DownTube</h1>
  <p><strong>YouTube Video Downloader with AI-Powered Arabic Subtitles</strong></p>
  <p>تحميل فيديوهات يوتيوب بجودة عالية مع الترجمة العربية المدعومة بالذكاء الاصطناعي</p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.111%2B-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
    <img src="https://img.shields.io/badge/Groq_Whisper-LLM-FF6600?style=flat-square&logo=groq&logoColor=white" alt="Groq">
    <img src="https://img.shields.io/badge/yt--dlp-2024%2B-EE0000?style=flat-square&logo=youtube&logoColor=white" alt="yt-dlp">
    <img src="https://img.shields.io/badge/WebSocket-Realtime-4FC08D?style=flat-square&logo=websocket&logoColor=white" alt="WebSocket">
    <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">
    <img src="https://img.shields.io/badge/License-MIT-yellow?style=flat-square" alt="License">
  </p>
</div>

---

## 📋 نظرة عامة

تطبيق **DownTube** هو تطبيق ويب متكامل لتحميل فيديوهات **YouTube** مع دعم كامل للترجمة العربية، يجمع بين القوة والإتقان:

- **تحميل بجودة عالية** — يدعم حتى 1080p H.264 مع صوت AAC نقي
- **ترجمة عربية تلقائية** — يسحب الترجمة من يوتيوب أو يولدها بـ **Groq Whisper AI**
- **ترجمة احترافية** — مش مجرد نسخ، بل ترجمة أدبية عبر **Llama 70B** تفهم السياق
- **ضمان وجود الصوت** — الحل الجذري: دمج video+audio تلقائياً مع codecs متوافقة
- **دعم WebSocket** — بث مباشر لتقدم التحميل بدون تأخير
- **واجهة RTL عربية** — تصميم Ocean-Blue أنيق بالكامل
- **Docker جاهز** — شغّل بـ أمر واحد

---

## ✨ الميزات الأساسية

| الميزة | الوصف |
|--------|-------|
| 🎬 **تحميل الفيديو** | جودات 1080p / 720p / 480p / 360p + صوت فقط |
| 🔊 **صوت نقي** | AAC 192kbps — شغال على كل الأجهزة، بدون تشويش |
| 📝 **ترجمة رسمية** | يسحب الترجمة العربية من يوتيوب تلقائياً |
| 🤖 **توليد AI** | يستخدم **Groq Whisper** لنسخ الصوت إذا مفيش ترجمة |
| 🌐 **ترجمة أدبية** | **Llama 3.3 70B** يترجم النص ترجمة طبيعية مش حرفية |
| ⚡ **بث مباشر** | WebSocket يعرض نسبة التقدم والسرعة والوقت المتبقي |
| 🎨 **واجهة عربية** | تصميم كامل RTL بألوان محيطية أنيقة |
| 🐳 **Docker** | نشر فوري بدون تعقيدات |

---

## 🏗️ هيكل المشروع

```
downtube/
├── app/
│   ├── main.py                 # FastAPI app + middleware + static files
│   ├── routers/
│   │   ├── info.py             # جلب معلومات الفيديو (GET /api/v1/info)
│   │   ├── download.py         # تحميل الفيديو (POST /api/v1/download/video)
│   │   └── subtitles.py        # تحميل الترجمة فقط
│   ├── services/
│   │   ├── youtube_service.py  # منطق yt-dlp — تحميل + دمج + ضمان الصوت
│   │   ├── groq_service.py     # Groq Whisper نسخ + Llama ترجمة
│   │   └── subtitle_service.py # إدارة الترجمة (يوتيوب / توليد)
│   └── utils/
│       ├── file_manager.py     # إدارة الملفات المؤقتة + التنظيف
│       ├── srt_converter.py    # معالجة SRT + ترجمة LLM
│       └── validators.py       # التحقق من روابط يوتيوب
├── frontend/
│   ├── index.html              # الصفحة الرئيسية (RTL عربي)
│   ├── css/style.css           # تصميم Ocean-Blue
│   └── js/app.js               # المنطق (WebSocket + واجهة)
├── docker-compose.yml          # نشر Docker
├── .env.example                # قالب متغيرات البيئة
└── requirements.txt            # الاعتماديات
```

---

## 🚀 التشغيل السريع

### 🐳 باستخدام Docker (موصى به)

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

### 💻 تشغيل محلي

```bash
# 1. متطلبات
pip install -r downtube/requirements.txt

# 2. إعداد .env
cp downtube/.env.example downtube/.env
# أضف GROQ_API_KEY

# 3. شغّل
uvicorn downtube.app.main:app --host 0.0.0.0 --port 8000
# افتح http://localhost:8000
```

---

## ⚙️ متغيرات البيئة

| المتغير | الإجباري | الشرح | الافتراضي |
|---------|----------|-------|-----------|
| `GROQ_API_KEY` | ✅ | مفتاح Groq API | — |
| `WHISPER_MODEL` | ❌ | موديل Whisper | `whisper-large-v3` |
| `FILE_TTL_MINUTES` | ❌ | مدة بقاء الملفات | `10` |
| `MAX_DURATION_SECONDS` | ❌ | أقصى مدة فيديو | `7200` |
| `RATE_LIMIT` | ❌ | حد الطلبات/دقيقة | `10/minute` |

---

## 📡 API Endpoints

| المسار | الطريقة | الوظيفة |
|--------|---------|---------|
| `/api/v1/info?url=` | `GET` | جلب معلومات الفيديو + التنسيقات المتاحة |
| `/api/v1/download/video` | `POST` | بدء تحميل الفيديو (يُعيد task_id) |
| `/api/v1/download/file/{task_id}` | `GET` | تحميل الملف النهائي (فيديو / ترجمة) |
| `/api/v1/download/cancel/{task_id}` | `POST` | إلغاء التحميل الجاري |
| `/api/v1/download/ws/{task_id}` | `WebSocket` | بث تقدم التحميل المباشر |
| `/api/v1/subtitles/download` | `GET` | تحميل الترجمة فقط |

---

## 🔊 نظام الصوت — الهندسة

المشكلة الكلاسيكية في أدوات تحميل يوتيوب: **الفيديو بينزل من غير صوت**.

**DownTube** يحلّها جذرياً:

1. **دمج تلقائي**: `bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/bestaudio`
   - فيديو: H.264 (متوافق مع كل شيء)
   - صوت: AAC في m4a (أعلى جودة متاحة)
   - لو مفيش m4a: يختار أعلى جودة صوت ويحوّله لـ AAC

2. **تحويل مضمون**: `FFmpegAudioConvertor` بجودة 192kbps
   - لو الصوت أصلاً AAC ← ما يعمل حاجة (zero re-encode)
   - لو الصوت Opus/Vorbis ← يحوّله لـ AAC 192kbps نظيف

3. **كوديكات متوافقة**: H.264 + AAC في MP4 — تشتغل على:
   - ✅ ويندوز (Windows Media Player, VLC, MPC-HC)
   - ✅ ماك (QuickTime, IINA, VLC)
   - ✅ لينكس (VLC, MPV)
   - ✅ أندرويد / iOS
   - ✅ متصفحات (Chrome, Firefox, Edge, Safari)

---

## 🤖 نظام الترجمة — الهندسة

### ثلاث طبقات:

1. **YouTube Official** — يسحب الترجمة العربية الرسمية لو موجودة (SRT/VTT)
2. **YouTube Auto** — يسحب الترجمة التلقائية لو يوتيوب وفرها
3. **Groq AI Generation** — لو مفيش ترجمة خالص:
   - ⬇️ يحمّل الصوت من الفيديو
   - 🎙️ **Whisper-large-v3** (Groq API) ينسخ الصوت لنص إنجليزي
   - 🌐 **Llama 3.3 70B** يترجم النص لعربية فصحى طبيعية
   - ✂️ يدمج المقاطع القصيرة عشان الترجمة تكون مريحة للقراءة
   - 💾 يحفظ الملف بنفس اسم الفيديو

---

## 🛠️ التقنيات المستخدمة

| التقنية | الاستخدام |
|---------|-----------|
| **Python 3.11+** | لغة التطوير |
| **FastAPI** | إطار العمل (ASGI) |
| **yt-dlp** | تحميل فيديوهات يوتيوب |
| **Groq SDK** | Whisper ASR (نسخ الكلام) + Llama (ترجمة) |
| **WebSocket** | بث تقدم التحميل المباشر |
| **Pydantic** | التحقق من البيانات |
| **Docker** | تغليف ونشر التطبيق |
| **HTML5 + CSS3 + JS** | واجهة المستخدم (بدون إطارات) |

---

## 📜 الترخيص

**MIT License** — ZET Dev

استخدم، عدّل، وزّع بحرية.

---

<div align="center">
  <p>Made by ZET Dev</p>
  <p>
    <a href="https://github.com/mohamedhaithemx/DownTube">GitHub</a> •
    <a href="https://console.groq.com">Groq Console</a>
  </p>
</div>
