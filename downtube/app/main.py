import os
import asyncio
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.routers import info, download, subtitles
from app.utils.file_manager import ensure_temp_dir, TEMP_DIR, cleanup_task

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DownTube — ZET Dev قيد التشغيل")
    ensure_temp_dir()

    # ── تحميل النماذج المحلية مسبقاً في الخلفية ──
    async def _warm_load():
        try:
            from app.services.groq_service import initialize_whisper_model
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, initialize_whisper_model)
            logger.info("تم تحميل نموذج faster-whisper مسبقاً")
        except Exception as e:
            logger.warning("فشل تحميل النموذج مسبقاً: %s — سيُحمّل عند أول طلب", e)

    asyncio.create_task(_warm_load())
    logger.info("DownTube ready — models loading in background")

    yield
    logger.info("DownTube يتوقف")
    for d in TEMP_DIR.iterdir():
        if d.is_dir():
            cleanup_task(d.name)


limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])

app = FastAPI(
    title="DownTube — ZET Dev",
    description="تحميل فيديوهات يوتيوب (حتى 20 ساعة) مع الترجمة العربية الفورية",
    version="3.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR.mkdir(parents=True, exist_ok=True)

app.include_router(info.router)
app.include_router(download.router)
app.include_router(subtitles.router)

if FRONTEND_DIR.exists():
    css_dir = FRONTEND_DIR / "css"
    js_dir = FRONTEND_DIR / "js"
    if css_dir.exists():
        app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
    if js_dir.exists():
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")


@app.get("/")
async def root():
    if INDEX_HTML.exists():
        content = INDEX_HTML.read_text(encoding="utf-8")
        return Response(content=content, media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})
    return HTMLResponse(content="<h1>DownTube — ZET Dev</h1><p>جاري التحميل...</p>")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0", "developer": "ZET Dev"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("خطأ غير متوقع: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "حدث خطأ داخلي. يرجى المحاولة مرة أخرى."},
    )
