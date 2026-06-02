#!/bin/bash
# تشغيل نسخة الهاتف - Flet Mobile App

echo "================================================"
echo "  YouTube Downloader - Mobile Version"
echo "  تحميل فيديوهات يوتيوب مع الترجمات"
echo "================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PATH="$HOME/.local/bin:$PATH"

# Check dependencies
echo ""
echo "[1/2] Checking dependencies..."
python3 -c "import yt_dlp" 2>/dev/null || { echo "Installing yt-dlp..."; pip install --break-system-packages yt-dlp; }
python3 -c "import flet" 2>/dev/null || { echo "Installing flet..."; pip install --break-system-packages flet; }

echo "[2/2] Starting mobile app..."
echo ""
python3 mobile/main.py
