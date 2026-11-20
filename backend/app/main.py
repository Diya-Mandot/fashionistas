import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from threading import Event

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.config import BACKEND_DIR, get_settings
from app.core.vision import vision_configured
from app.services.calendar_source import describe as describe_calendar
from app.db import engine, init_db
from app.integrations.anthropic_client import key_configured
from app.routers import buy_check, calendar, closet, daily, dev, health, location, scan, shop, stylist
from app.seed import seed_if_empty
from app.services.catalog import THRIFT_PATH, catalog_path
from app.services.gmail_receipts import ReceiptSyncUnavailable, sync_gmail_receipts

settings = get_settings()
UPLOADS_DIR = Path(settings.uploads_dir)
SEED_IMAGES_DIR = BACKEND_DIR / "seed_images"
CATALOG_IMAGES_DIR = BACKEND_DIR / "catalog" / "images"


async def _poll_receipts(stop: Event) -> None:
    logger = logging.getLogger("uvicorn.error")
    while not stop.is_set():
        try:
            imported = await asyncio.to_thread(sync_gmail_receipts, stop)
            if imported:
                logger.info("Imported %s Gmail receipts into the closet", imported)
        except ReceiptSyncUnavailable as exc:
            logger.warning("%s", exc)
        except Exception as exc:
            logger.warning("Gmail receipt sync failed (%s)", type(exc).__name__)
        await asyncio.sleep(settings.gmail_receipts_poll_seconds)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    Path(settings.logs_dir).mkdir(parents=True, exist_ok=True)
    init_db()
    with Session(engine) as session:
        seed_if_empty(session)
    if catalog_path() == THRIFT_PATH:
        shop.warm_cache_in_background()
    stop = Event()
    task = asyncio.create_task(_poll_receipts(stop)) if settings.gmail_receipts_enabled else None
    try:
        yield
    finally:
        if task:
            stop.set()
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(title=f"{settings.app_name} API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Demo safety: never show a raw traceback; log it and return a readable error.
    logging.getLogger("fashionistas").exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Something went wrong ({type(exc).__name__}). Try again."})


app.include_router(stylist.router)
app.include_router(health.router)
app.include_router(location.router)
app.include_router(scan.router)
app.include_router(buy_check.router)
app.include_router(shop.router)
app.include_router(closet.router)
app.include_router(calendar.router)
app.include_router(daily.router)
if settings.dev_endpoints:
    app.include_router(dev.router)

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/seed", StaticFiles(directory=Path(SEED_IMAGES_DIR)), name="seed-images")
CATALOG_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/catalog", StaticFiles(directory=CATALOG_IMAGES_DIR), name="catalog-images")
app.mount("/media/uploads", StaticFiles(directory=Path(UPLOADS_DIR)), name="uploads")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "agents_mode": settings.agents_mode,
        "decisions_mode": settings.decisions_mode,
        "key_configured": key_configured(),
        "vision_configured": vision_configured(),
        "calendar": describe_calendar(),
        "home_city": settings.home_city,
    }


# Production mode (`make start`): serve the built frontend from this same server.
FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "media/")):
            raise HTTPException(404, "Not found")
        file = FRONTEND_DIST / path
        if path and file.is_file() and FRONTEND_DIST in file.resolve().parents:
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")  # client-side routes: /closet, /scan
