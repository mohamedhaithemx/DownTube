@echo off
chcp 65001 >nul 2>&1
title DownTube - تثبيت تلقائي

echo.
echo ============================================================
echo   DownTube - تثبيت تلقائي
echo   تحميل فيديوهات يوتيوب مع ترجمات عربية إجبارية
echo ============================================================
echo.

:: Check Python
echo [1/4] فحص Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python غير مثبت!
    echo يرجى تثبيت Python 3.8+ من: https://www.python.org/downloads/
    echo ⚠️ تأكد من تفعيل "Add Python to PATH" أثناء التثبيت
    pause
    exit /b 1
)
echo ✅ Python متوفر

:: Check ffmpeg
echo.
echo [2/4] فحص ffmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo ❌ ffmpeg غير مثبت!
    echo.
    echo لتثبيت ffmpeg على Windows:
    echo 1. حمّل من: https://www.gyan.dev/ffmpeg/builds/
    echo 2. اختر "ffmpeg-release-essentials.zip"
    echo 3. فك الضغط وأضف المجلد إلى PATH
    echo.
    echo أو استخدم Chocolatey: choco install ffmpeg
    echo أو استخدم winget: winget install ffmpeg
    pause
    exit /b 1
)
echo ✅ ffmpeg متوفر

:: Install dependencies
echo.
echo [3/4] تثبيت المكتبات المطلوبة...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ❌ فشل تثبيت المكتبات!
    pause
    exit /b 1
)
echo ✅ تم تثبيت المكتبات

:: Install yt-dlp
echo.
echo [4/4] تحديث yt-dlp...
pip install --upgrade yt-dlp --quiet
echo ✅ yt-dlp محدّث

echo.
echo ============================================================
echo   ✅ تم التثبيت بنجاح!
echo.
echo   لتشغيل التطبيق:
echo   python app.py
echo.
echo   أو من سطر الأوامر:
echo   python app.py --cli "رابط_الفيديو"
echo ============================================================
echo.
pause
