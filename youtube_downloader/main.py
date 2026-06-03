"""
main.py — Entry point for DownTube FastAPI application.

Usage:
    python -m youtube_downloader     → Starts the web server
    python -m youtube_downloader --port 8080  → Custom port
"""

import argparse
import uvicorn
import logging

from .config import HOST, PORT


def main():
    parser = argparse.ArgumentParser(description="DownTube - YouTube Downloader")
    parser.add_argument("--host", default=HOST, help="Host to bind to")
    parser.add_argument("--port", type=int, default=PORT, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print(f"""
╔══════════════════════════════════════╗
║          DownTube v3.0.0             ║
║    YouTube Downloader + FastAPI      ║
╠══════════════════════════════════════╣
║  Open in browser:                    ║
║  http://{args.host}:{args.port}            ║
╚══════════════════════════════════════╝
""")

    uvicorn.run(
        "youtube_downloader.app:app",
        host=args.host,
        port=args.port,
        reload=args.debug,
        log_level="debug" if args.debug else "info",
    )


if __name__ == "__main__":
    main()
