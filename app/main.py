from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import applications, jobs, outreach, profile, system
from app.config import settings
from app.database import SessionLocal, init_db
from app.scheduler import start_scheduler, stop_scheduler
from app.services.discovery import seed_sources
from app.services.profiles import get_or_create_user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_sources(db)
        get_or_create_user(db)
    finally:
        db.close()
    result = start_scheduler()
    logger.info("Scheduler: %s", result)
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    description="Personal AI job discovery, matching, tailoring and application assistant.",
    version="1.0.0",
    lifespan=lifespan,
)

_origins = {
    f"http://{settings.host}:{settings.port}",
    f"http://127.0.0.1:{settings.port}",
    f"http://localhost:{settings.port}",
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(outreach.router)
app.include_router(system.router)

app.mount("/static", StaticFiles(directory=str(settings.data_dir.parent / "app" / "static")), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(
        str(settings.data_dir.parent / "app" / "static" / "index.html"),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api", include_in_schema=False)
def api_root():
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/health"}
