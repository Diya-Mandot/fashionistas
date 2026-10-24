from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.config import BACKEND_DIR, get_settings
from app.db import engine, init_db
from app.routers import calendar, closet, dev, health
from app.seed import seed_if_empty

settings = get_settings()
UPLOADS_DIR = BACKEND_DIR / "uploads"
SEED_IMAGES_DIR = BACKEND_DIR / "seed_images"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    UPLOADS_DIR.mkdir(exist_ok=True)
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

app.include_router(closet.router)
app.include_router(calendar.router)
app.include_router(health.router)
if settings.dev_endpoints:
    app.include_router(dev.router)

UPLOADS_DIR.mkdir(exist_ok=True)
app.mount("/media/seed", StaticFiles(directory=Path(SEED_IMAGES_DIR)), name="seed-images")
app.mount("/media/uploads", StaticFiles(directory=Path(UPLOADS_DIR)), name="uploads")


@app.get("/api/health")
def health_status() -> dict:
    return {
        "status": "ok",
        "agents_mode": settings.agents_mode,
        "decisions_mode": settings.decisions_mode,
    }
