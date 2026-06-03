#!/bin/bash
# DownTube - Linux/macOS Setup Script
# تحميل فيديوهات يوتيوب مع ترجمات عربية إجبارية

set -e

echo ""
echo "============================================================"
echo "  DownTube - تثبيت تلقائي"
echo "  تحميل فيديوهات يوتيوب مع ترجمات عربية إجبارية"
echo "============================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check Python
echo "[1/4] فحص Python..."
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo -e "${RED}❌ Python غير مثبت!${NC}"
    echo "يرجى تثبيت Python 3.8+ من: https://www.python.org/downloads/"
    exit 1
fi
echo -e "${GREEN}✅ Python متوفر: $($PYTHON --version)${NC}"

# Check ffmpeg
echo ""
echo "[2/4] فحص ffmpeg..."
if command -v ffmpeg &> /dev/null; then
    echo -e "${GREEN}✅ ffmpeg متوفر$(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f3)${NC}"
else
    echo -e "${RED}❌ ffmpeg غير مثبت!${NC}"
    echo ""
    echo "لتثبيت ffmpeg:"
    echo "  Ubuntu/Debian: sudo apt install ffmpeg"
    echo "  Fedora: sudo dnf install ffmpeg"
    echo "  macOS: brew install ffmpeg"
    echo "  Arch: sudo pacman -S ffmpeg"
    exit 1
fi

# Install dependencies
echo ""
echo "[3/4] تثبيت المكتبات المطلوبة..."
$PYTHON -m pip install -r requirements.txt --quiet 2>/dev/null || \
    $PYTHON -m pip install -r requirements.txt
echo -e "${GREEN}✅ تم تثبيت المكتبات${NC}"

# Install/update yt-dlp
echo ""
echo "[4/4] تحديث yt-dlp..."
$PYTHON -m pip install --upgrade yt-dlp --quiet 2>/dev/null || \
    $PYTHON -m pip install --upgrade yt-dlp
echo -e "${GREEN}✅ yt-dlp محدّث${NC}"

echo ""
echo "============================================================"
echo -e "  ${GREEN}✅ تم التثبيت بنجاح!${NC}"
echo ""
echo "  لتشغيل التطبيق بواجهة رسومية:"
echo "    $PYTHON app.py"
echo ""
echo "  أو من سطر الأوامر:"
echo "    $PYTHON app.py --cli \"رابط_الفيديو\""
echo "============================================================"
echo ""
