#!/usr/bin/env python3
# DownTube — نقطة تشغيل التطبيق

import argparse
import uvicorn
import logging

from app.config import PORT as DEFAULT_PORT


def main():
    parser = argparse.ArgumentParser(description="DownTube — تحميل فيديوهات يوتيوب")
    parser.add_argument("--host", default="127.0.0.1", help="عنوان المضيف")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="رقم المنفذ")
    parser.add_argument("--debug", action="store_true", help="وضع التصحيح")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print(f"""
╔══════════════════════════════════════════╗
║            ZET DEV — DownTube            ║
║     تحميل فيديوهات يوتيوب مع الترجمة     ║
╠══════════════════════════════════════════╣
║  افتح في المتصفح:                        ║
║  http://{args.host}:{args.port}                ║
╚══════════════════════════════════════════╝
""")

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.debug,
        log_level="debug" if args.debug else "info",
    )


if __name__ == "__main__":
    main()
