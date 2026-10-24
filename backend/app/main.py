from contextlib import asynccontextmanager
from pathlib import Path

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.config import BACKEND_DIR, get_settings
from app.core.vision import vision_configured
from app.services.calendar_source import calendar_configured
from app.db import engine, init_db
from app.integrations.openai_client import key_configured
from app.routers import calendar, closet, dev, health, location, scan, stylist
from app.seed import seed_if_empty

settings = get_settings()
UPLOADS_DIR = Path(settings.uploads_dir)
SEED_IMAGES_DIR = BACKEND_DIR / "seed_images"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (BACKEND_DIR / "logs").mkdir(exist_ok=True)
    init_db()
    with Session(engine) as session:
        seed_if_empty(session)
    yield


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
    logging.getLogger("ecostylist").exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Something went wrong ({type(exc).__name__}). Try again."})


app.include_router(stylist.router)
app.include_router(health.router)
app.include_router(location.router)
app.include_router(scan.router)
app.include_router(closet.router)
app.include_router(calendar.router)
if settings.dev_endpoints:
    app.include_router(dev.router)

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/seed", StaticFiles(directory=Path(SEED_IMAGES_DIR)), name="seed-images")
app.mount("/media/uploads", StaticFiles(directory=Path(UPLOADS_DIR)), name="uploads")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "agents_mode": settings.agents_mode,
        "decisions_mode": settings.decisions_mode,
        "key_configured": key_configured(),
        "vision_configured": vision_configured(),
        "calendar": "your calendar (iCal)" if calendar_configured() else "demo calendar",
        "home_city": settings.home_city,
    }
