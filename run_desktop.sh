#!/bin/bash
# تشغيل نسخة الكمبيوتر - FastAPI Desktop Server

echo "================================================"
echo "  YouTube Downloader - Desktop Version"
echo "  تحميل فيديوهات يوتيوب مع الترجمات"
echo "================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PATH="$HOME/.local/bin:$PATH"

# Check dependencies
echo ""
echo "[1/2] Checking dependencies..."
python3 -c "import yt_dlp" 2>/dev/null || { echo "Installing yt-dlp..."; pip install --break-system-packages yt-dlp; }
python3 -c "import fastapi" 2>/dev/null || { echo "Installing fastapi..."; pip install --break-system-packages fastapi uvicorn; }
python3 -c "import aiofiles" 2>/dev/null || { echo "Installing aiofiles..."; pip install --break-system-packages aiofiles; }

echo "[2/2] Starting server..."
echo ""
python3 desktop/main.py
