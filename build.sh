#!/bin/bash
# DownTube AppImage Build Script
# Creates a self-contained Linux AppImage with Python, yt-dlp, and ffmpeg

set -e

APP_NAME="DownTube"
APP_DIR="AppDir"
BUILD_DIR="build_appimage"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================"
echo "  DownTube AppImage Builder"
echo "================================================"
echo ""

# Check dependencies
check_deps() {
    echo "Checking build dependencies..."
    
    if ! command -v python3 &> /dev/null; then
        echo "❌ python3 not found. Please install Python 3."
        exit 1
    fi
    echo "✅ python3: $(python3 --version)"
    
    if ! command -v ffmpeg &> /dev/null; then
        echo "❌ ffmpeg not found. Please install ffmpeg."
        exit 1
    fi
    echo "✅ ffmpeg: $(ffmpeg -version 2>&1 | head -1)"
    
    if ! python3 -c "import yt_dlp" &> /dev/null; then
        echo "❌ yt-dlp Python package not found. Installing..."
        pip install yt-dlp
    fi
    echo "✅ yt-dlp: $(python3 -c "import yt_dlp; print(yt_dlp.version.__version__)")"
}

# Build AppImage using appimage-builder
build_with_appimage_builder() {
    echo ""
    echo "Building with appimage-builder..."
    
    if ! command -v appimage-builder &> /dev/null; then
        echo "appimage-builder not found. Installing..."
        pip install appimage-builder
    fi
    
    # Create AppImage recipe
    cat > "$SCRIPT_DIR/AppImageBuilder.yml" << 'RECIPE'
version: 1
AppDir:
  path: ./AppDir
  app_info:
    id: com.downtube.app
    name: DownTube
    icon: utilities-terminal
    version: 1.0.0
    exec: usr/bin/python3
    exec_args: "$APPDIR/usr/src/app/app.py $@"
  pacman:
    arch: []
  apt:
    arch:
    - amd64
    allow_unauthenticated: true
    sources:
    - sourceline: deb http://archive.ubuntu.com/ubuntu/ jammy main restricted universe multiverse
    include:
    - python3
    - ffmpeg
    - libgl1
    - libglib2.0-0
  files:
    exclude:
    - usr/share/man
    - usr/share/doc
    - usr/include
  runtime:
    env:
      PATH: "$APPDIR/usr/bin:$PATH"
      PYTHONPATH: "$APPDIR/usr/src/app:$APPDIR/usr/lib/python3/dist-packages:$PYTHONPATH"
      QT_QPA_PLATFORM: offscreen
AppImage:
  arch: x86_64
  file_name: DownTube-x86_64.AppImage
RECIPE
    
    # Build
    appimage-builder --recipe AppImageBuilder.yml
    
    echo ""
    echo "✅ AppImage created: DownTube-x86_64.AppImage"
}

# Build AppImage using manual approach
build_manual() {
    echo ""
    echo "Building AppImage manually..."
    
    rm -rf "$BUILD_DIR" "$APP_DIR"
    mkdir -p "$BUILD_DIR" "$APP_DIR"
    
    # Use python-appimage base
    PYTHON_APPIMAGE="python3.11-cp311-x86_64.AppImage"
    PYTHON_APPIMAGE_URL="https://github.com/niess/python-appimage/releases/download/python3.11/python3.11.4-cp311-x86_64.AppImage"
    
    if [ ! -f "$BUILD_DIR/$PYTHON_APPIMAGE" ]; then
        echo "Downloading Python AppImage base..."
        wget -q "$PYTHON_APPIMAGE_URL" -O "$BUILD_DIR/$PYTHON_APPIMAGE"
        chmod +x "$BUILD_DIR/$PYTHON_APPIMAGE"
    fi
    
    # Extract the Python AppImage
    echo "Extracting Python AppImage..."
    cd "$BUILD_DIR"
    ./"$PYTHON_APPIMAGE" --appimage-extract
    cd "$SCRIPT_DIR"
    
    cp -r "$BUILD_DIR/squashfs-root"/* "$APP_DIR/"
    
    # Install Python dependencies
    echo "Installing Python dependencies..."
    "$APP_DIR/AppRun" -m pip install --no-cache-dir \
        yt-dlp \
        fastapi \
        uvicorn
    
    # Copy application code
    echo "Copying application code..."
    mkdir -p "$APP_DIR/usr/src/app"
    cp -r core/ "$APP_DIR/usr/src/app/"
    cp -r static/ "$APP_DIR/usr/src/app/"
    cp app.py "$APP_DIR/usr/src/app/"
    cp requirements.txt "$APP_DIR/usr/src/app/"
    
    # Copy ffmpeg
    echo "Bundling ffmpeg..."
    FFMPEG_PATH=$(which ffmpeg)
    FFPROBE_PATH=$(which ffprobe)
    mkdir -p "$APP_DIR/usr/bin"
    cp "$FFMPEG_PATH" "$APP_DIR/usr/bin/"
    cp "$FFPROBE_PATH" "$APP_DIR/usr/bin/"
    chmod +x "$APP_DIR/usr/bin/ffmpeg" "$APP_DIR/usr/bin/ffprobe"
    
    # Create AppRun
    cat > "$APP_DIR/AppRun" << 'APPRUN'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="$HERE/usr/bin:$PATH"
export PYTHONPATH="$HERE/usr/src/app:$HERE/usr/lib/python3.11/site-packages:$PYTHONPATH"
export LD_LIBRARY_PATH="$HERE/usr/lib:$HERE/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"
exec "$HERE/usr/bin/python3" "$HERE/usr/src/app/app.py" "$@"
APPRUN
    chmod +x "$APP_DIR/AppRun"
    
    # Update desktop entry
    mkdir -p "$APP_DIR/usr/share/applications"
    cat > "$APP_DIR/usr/share/applications/downtube.desktop" << 'DESKTOP'
[Desktop Entry]
Name=DownTube
Comment=YouTube Downloader with Arabic Subtitles
Exec=AppRun
Icon=utilities-terminal
Type=Application
Categories=AudioVideo;Network;
Terminal=true
DESKTOP
    
    # Build the AppImage
    echo "Building AppImage..."
    
    if ! command -v appimagetool &> /dev/null; then
        echo "Downloading appimagetool..."
        wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O "$BUILD_DIR/appimagetool"
        chmod +x "$BUILD_DIR/appimagetool"
        APPIMAGETOOL="$BUILD_DIR/appimagetool"
    else
        APPIMAGETOOL="appimagetool"
    fi
    
    "$APPIMAGETOOL" "$APP_DIR" "DownTube-x86_64.AppImage"
    
    echo ""
    echo "✅ AppImage created: DownTube-x86_64.AppImage"
}

# Simple standalone script approach (no AppImage, just a launcher script)
build_standalone() {
    echo ""
    echo "Creating standalone launcher script..."
    
    cat > "$SCRIPT_DIR/downtube-launcher.sh" << 'LAUNCHER'
#!/bin/bash
# DownTube Launcher Script
# This script checks dependencies and runs DownTube

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "================================================"
echo "  DownTube - YouTube Downloader with Arabic Subtitles"
echo "================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed!${NC}"
    echo "   Install it from: https://www.python.org/downloads/"
    exit 1
fi
echo -e "${GREEN}✅ Python: $(python3 --version)${NC}"

# Check ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}❌ ffmpeg is not installed!${NC}"
    echo "   Install it:"
    echo "   Ubuntu/Debian: sudo apt install ffmpeg"
    echo "   macOS: brew install ffmpeg"
    echo "   Fedora: sudo dnf install ffmpeg"
    exit 1
fi
echo -e "${GREEN}✅ ffmpeg: $(ffmpeg -version 2>&1 | head -1)${NC}"

# Check yt-dlp
if ! python3 -c "import yt_dlp" &> /dev/null; then
    echo -e "${YELLOW}⚠️  yt-dlp not found. Installing...${NC}"
    pip install yt-dlp
fi
echo -e "${GREEN}✅ yt-dlp: $(python3 -c "import yt_dlp; print(yt_dlp.version.__version__)")${NC}"

# Check FastAPI
if ! python3 -c "import fastapi" &> /dev/null; then
    echo -e "${YELLOW}⚠️  FastAPI not found. Installing dependencies...${NC}"
    pip install -r "$SCRIPT_DIR/requirements.txt"
fi

# Run the app
echo ""
echo "Starting DownTube..."
echo ""
cd "$SCRIPT_DIR"
python3 app.py "$@"
LAUNCHER
    
    chmod +x "$SCRIPT_DIR/downtube-launcher.sh"
    echo "✅ Standalone launcher created: downtube-launcher.sh"
}

# Main
echo "Choose build method:"
echo "  1) AppImage (requires appimagetool)"
echo "  2) Manual AppImage (uses python-appimage)"
echo "  3) Standalone launcher script (recommended for simplicity)"
echo ""

BUILD_METHOD="${1:-3}"

case "$BUILD_METHOD" in
    1)
        check_deps
        build_with_appimage_builder
        ;;
    2)
        check_deps
        build_manual
        ;;
    3)
        check_deps
        build_standalone
        ;;
    *)
        echo "Invalid option. Use 1, 2, or 3."
        exit 1
        ;;
esac

echo ""
echo "================================================"
echo "  Build complete!"
echo "================================================"
