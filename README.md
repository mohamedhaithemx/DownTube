# DownTube ⬇️
## تحميل فيديوهات يوتيوب مع ترجمات عربية

<p align="center">
  <strong>تطبيق محلي لتحميل فيديوهات يوتيوب مع فرض الترجمة العربية</strong>
</p>

---

## 🎯 لماذا DownTube؟

تم تطوير DownTube لحل مشكلة محددة: **تحميل فيديوهات يوتيوب مع ترجمات عربية مضمونة**.

- ❌ الحلول السحابية تفشل لأن يوتيوب يحظر عناوين IP الخاصة بمراكز البيانات
- ✅ DownTube يعمل **محلياً** على جهازك باستخدام اتصالك المنزلي
- 🔤 يفرض الترجمة العربية على كل تحميل (يدوية أو تلقائية)
- 🎬 يدمج الترجمة داخل الفيديو بصيغة MKV

---

## ✨ المميزات

| الميزة | الوصف |
|--------|-------|
| 🔤 **ترجمة عربية مضمونة** | يبحث عن ترجمات عربية يدوية أولاً، ثم تلقائية، ويدمجها في الفيديو |
| 🎬 **أفضل جودة** | يحمل أفضل جودة فيديو+صوت متوفرة |
| 📦 **صيغة MKV** | أفضل صيغة لدمج الترجمات |
| 📊 **تقدم مباشر** | عرض التقدم والسرعة والوقت المتبقي في الوقت الفعلي |
| 🌐 **واجهة عربية** | واجهة مستخدم عربية كاملة بتصميم داكن أنيق |
| 💻 **سطر أوامر** | يمكن استخدامه من سطر الأوامر أيضاً |
| 🔒 **محلي بالكامل** | يعمل على جهازك - لا يحتاج إنترنت سوى لتحميل الفيديو |

---

## 📋 المتطلبات

- **Python 3.8+**
- **ffmpeg** - ضروري لدمج الترجمة وتحويل الصيغ
- **yt-dlp** - يتم تثبيته تلقائياً مع المتطلبات

### تثبيت ffmpeg

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Fedora
sudo dnf install ffmpeg

# Arch Linux
sudo pacman -S ffmpeg
```

---

## 🚀 التثبيت والتشغيل

### الطريقة 1: من المصدر (موصى بها)

```bash
# استنساخ المستودع
git clone -b cloud-deployment https://github.com/mohamedhaithamx/DownTube.git
cd DownTube

# تثبيت المتطلبات
pip install -r requirements.txt

# تشغيل التطبيق (واجهة ويب)
python app.py

# أو تشغيل من سطر الأوامر
python app.py --cli "https://youtube.com/watch?v=VIDEO_ID"
```

### الطريقة 2: باستخدام سكريبت التشغيل

```bash
# استنساخ المستودع
git clone -b cloud-deployment https://github.com/mohamedhaithamx/DownTube.git
cd DownTube

# تشغيل سكريبت التشغيل (يفحص المتطلبات تلقائياً)
bash downtube-launcher.sh

# أو بناء السكريبت أولاً
bash build.sh 3
```

### الطريقة 3: AppImage (Linux فقط)

```bash
# بناء AppImage
bash build.sh 2

# تشغيل
chmod +x DownTube-x86_64.AppImage
./DownTube-x86_64.AppImage
```

### الطريقة 4: Docker

```bash
# بناء الصورة
docker build -t downtube .

# تشغيل
docker run -p 8555:8555 -v ~/Downloads/DownTube:/root/Downloads/DownTube downtube
```

> ⚠️ **ملاحظة**: Docker قد لا يعمل بشكل موثوق لأن يوتيوب يحظر عناوين IP لمراكز البيانات. استخدم التشغيل المحلي المباشر.

---

## 🖥️ وضع واجهة الويب

عند تشغيل `python app.py`:

1. يفتح المتصفح تلقائياً على `http://localhost:8555`
2. الصق رابط يوتيوب في حقل الإدخال
3. اضغط "تحميل الفيديو"
4. تابع التقدم في الوقت الفعلي
5. ستجد الملفات في `~/Downloads/DownTube/`

### خيارات سطر الأوامر

```bash
python app.py                    # تشغيل واجهة الويب على المنفذ 8555
python app.py --port 9000        # استخدام منفذ مختلف
python app.py --no-browser       # عدم فتح المتصفح تلقائياً
python app.py --cli "URL"        # تحميل مباشر من سطر الأوامر
python app.py --cli "URL" -o /path/to/dir  # تحديد مجلد التحميل
```

---

## 💻 وضع سطر الأوامر (CLI)

```bash
# تحميل فيديو
python app.py --cli "https://youtube.com/watch?v=dQw4w9WgXcQ"

# تحديد مجلد التحميل
python app.py --cli "https://youtube.com/watch?v=dQw4w9WgXcQ" -o ~/Videos

# مثال على المخرجات:
# ============================================================
#   DownTube - تحميل فيديوهات يوتيوب مع ترجمات عربية
# ============================================================
#
# ✅ ffmpeg: ffmpeg version 6.0
# ✅ yt-dlp: 2024.03.10
#
# 🔗 الرابط: https://youtube.com/watch?v=dQw4w9WgXcQ
# 📁 مجلد التحميل: /home/user/Downloads/DownTube
#
#   [100.0%] جاري المعالجة... | السرعة: 5.2 MB/s | المتبقي: 0:00
#
# ✅ اكتمل التحميل بنجاح!
#    الفيديو: /home/user/Downloads/DownTube/Video Title.mkv
#    الترجمة: /home/user/Downloads/DownTube/Video Title.ar.srt
#    الترجمة: ترجمات عربية يدوية متوفرة (ar)
```

---

## 🔤 استراتيجية الترجمة العربية

يعمل DownTube على فرض الترجمة العربية بالترتيب التالي:

1. **ترجمات يدوية عربية** - يبحث عن الرموز: `ar`, `ar-ar`, `ara`
2. **ترجمات تلقائية عربية** - إذا لم يجد ترجمات يدوية
3. **دمج الترجمة** - يتم تضمين الترجمة داخل ملف MKV
4. **حفظ كملف منفصل** - يحفظ أيضاً ملف `.srt` منفصل
5. **إذا لم توجد ترجمة** - يحمّل الفيديو بدون ترجمة ويعلم المستخدم

### معالجات ما بعد التحميل (Post-Processors)

```
1. FFmpegSubtitlesConvertor → تحويل الترجمة إلى SRT
2. FFmpegVideoConvertor → تحويل الفيديو إلى MKV
3. FFmpegEmbedSubtitle → دمج الترجمة في الفيديو
```

---

## 🏗️ هيكل المشروع

```
downtube/
├── app.py              # تطبيق FastAPI الرئيسي
├── core/
│   ├── __init__.py     # وحدة Core
│   ├── downloader.py   # محمل yt-dlp مع فرض الترجمة العربية
│   └── utils.py        # دوال مساعدة
├── static/
│   ├── index.html      # الصفحة الرئيسية
│   ├── style.css       # تصميم داكن
│   └── script.js       # منطق الواجهة
├── downloads/          # مجلد التحميل الافتراضي
├── requirements.txt    # متطلبات Python
├── Dockerfile          # صورة Docker (اختياري)
├── build.sh            # سكريبت بناء AppImage
├── .gitignore          # ملفات Git المتجاهلة
└── README.md           # هذا الملف
```

---

## 🔧 API Endpoints

| Endpoint | Method | الوصف |
|----------|--------|-------|
| `/` | GET | الصفحة الرئيسية |
| `/api/status` | GET | حالة النظام والمتطلبات |
| `/api/download` | POST | بدء تحميل فيديو |
| `/api/progress` | GET | بث تقدم التحميل (SSE) |
| `/api/cancel` | POST | إلغاء التحميل الحالي |
| `/api/info` | POST | معلومات الفيديو بدون تحميل |
| `/api/downloads` | GET | قائمة الملفات المحملة |
| `/api/download-dir` | POST | تغيير مجلد التحميل |

---

## ❓ الأسئلة الشائعة

### التحميل بطيء
- تأكد من اتصالك بالإنترنت
- قد يكون يوتيوب يحد من السرعة - حاول لاحقاً
- استخدم VPN إذا كان يوتيوب محظوراً في بلدك

### لا توجد ترجمة عربية
- ليس كل الفيديوهات لها ترجمات عربية
- الترجمات التلقائية قد لا تكون متوفرة دائماً
- DownTube سيخبرك إذا لم توجد ترجمة

### خطأ ffmpeg
- تأكد من تثبيت ffmpeg: `ffmpeg -version`
- على Linux: `sudo apt install ffmpeg`
- على macOS: `brew install ffmpeg`

### خطأ yt-dlp
- حدث yt-dlp: `pip install -U yt-dlp`
- يوتيوب يغير طريقة عمله باستمرار، yt-dlp يحتاج تحديث منتظم

---

## 📝 الترخيص

هذا المشروع مفتوح المصدر ومتاح للاستخدام والتوزيع بحرية.

---

<p align="center">
  صنع بـ ❤️ لمجتمع العربية
</p>
