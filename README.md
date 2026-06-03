# DownTube v3.0 — تحميل فيديوهات يوتيوب مع الترجمة العربية

<div align="center">

**ZET DEV — DownTube**

تحميل فيديوهات يوتيوب مع الترجمة العربية كملفات منفصلة

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-green?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-2024%2B-red?style=flat-square&logo=youtube)](https://github.com/yt-dlp/yt-dlp)

</div>

---

## الميزات

- **واجهة ويب FastAPI** — تصميم عربي RTL مع تدرجات أزرق-بنفسجي وتأثيرات متحركة
- **SSE (Server-Sent Events)** — بث تقدم التحميل في الوقت الحقيقي
- **ترجمة عربية** — كملفات منفصلة (SRT/VTT)، رسمية وتلقائية
- **5 مراحل تقدم** — جلب المعلومات → التحقق من الترجمة → تنزيل الفيديو → الترجمة → المعالجة
- **Anti-Block** — تدوير User-Agent، Exponential Backoff مع Jitter، Rate Limiting
- **دعم الكوكيز والبروكسي** — إعدادات اختيارية لتجاوز الحظر
- **مودال الترجمة** — خيار التنزيل بدون ترجمة أو الإلغاء

## هيكل المشروع

```
app/
├── __init__.py
├── main.py              # FastAPI app + Rate Limiting middleware
├── config.py            # ثوابت وإعدادات
├── exceptions.py        # استثناءات مخصصة
├── models.py            # نماذج Pydantic
├── routers/
│   ├── __init__.py
│   ├── info.py          # جلب معلومات الفيديو
│   └── download.py      # التحميل + SSE
└── services/
    ├── __init__.py
    ├── downloader.py     # منطق yt-dlp
    ├── subtitle.py       # كشف وإدارة الترجمة
    ├── anti_block.py     # استراتيجيات تجنب الحظر
    └── progress.py       # تتبع التقدم
static/
└── index.html           # الواجهة الأمامية (Tailwind + CSS animations)
tests/
├── test_info.py          # اختبارات جلب المعلومات
├── test_download.py      # اختبارات التحميل
├── test_anti_block.py    # اختبارات Rate Limiting
└── test_progress.py      # اختبارات تتبع التقدم
```

## التشغيل

```bash
git clone https://github.com/mohamedhaithemx/DownTube.git
cd DownTube
git checkout fastapi-app
pip install -r requirements.txt
python run.py
# افتح http://127.0.0.1:8554
```

## الاختبارات

```bash
pytest tests/ -v    # 53 اختبار — كلها ناجحة ✅
```

## API Endpoints

| Method | Endpoint | الوصف |
|--------|----------|-------|
| `POST` | `/api/info` | جلب معلومات الفيديو + حالة الترجمة |
| `POST` | `/api/download` | بدء التحميل |
| `POST` | `/api/cancel` | إلغاء التحميل |
| `GET`  | `/api/progress` | تتبع التقدم (SSE) |
| `GET`  | `/api/state` | حالة التحميل الحالية |

## الرخصة

MIT License
