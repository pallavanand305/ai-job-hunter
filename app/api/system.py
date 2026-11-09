from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.serializers import iso
from app.config import settings
from app.connectors import CONNECTORS
from app.database import get_db
from app.llm.client import get_llm
from app.models import Application, Job, JobMatch, JobSource, TailoredResume, User
from app.schemas import SourceUpdate
from app.scheduler import scheduler_status, start_scheduler, stop_scheduler, _daily_pipeline
from app.services.analytics import dashboard
from app.services.discovery import seed_sources
from app.services.profiles import profile_dict

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm": get_llm().info(),
        "scheduler": scheduler_status(),
    }


@router.get("/api/dashboard")
def get_dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    data = dashboard(db, user)
    data["profile"] = {
        "name": user.name,
        "headline": user.headline,
        "location": user.location,
        "skills": len(profile_dict(db, user)["skills"]),
    }
    data["llm"] = get_llm().info()
    return data


@router.get("/api/llm/info")
def llm_info():
    return get_llm().info()


@router.post("/api/llm/test")
def llm_test():
    llm = get_llm()
    return {"results": llm.test_all(), "info": llm.info()}


@router.get("/api/sources")
def list_sources(db: Session = Depends(get_db), user: User = Depends(current_user)):
    seed_sources(db)
    rows = db.scalars(select(JobSource).order_by(JobSource.id)).all()
    return {
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "kind": s.kind,
                "display_name": getattr(CONNECTORS.get(s.kind), "display_name", s.kind),
                "config": s.config,
                "enabled": s.enabled,
                "requires_config": bool(getattr(CONNECTORS.get(s.kind), "requires_config", False)),
                "is_configured": _is_configured(s.kind, s.config),
                "notes": s.notes,
                "last_synced_at": iso(s.last_synced_at),
                "last_status": s.last_status,
                "last_error": s.last_error,
                "last_fetched": s.last_fetched,
                "last_added": s.last_added,
            }
            for s in rows
        ]
    }


@router.put("/api/sources/{source_id}")
def update_source(
    source_id: int,
    payload: SourceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    source = db.get(JobSource, source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    if payload.enabled is not None:
        source.enabled = payload.enabled
    if payload.config is not None:
        source.config = payload.config
    db.commit()
    db.refresh(source)
    return {
        "id": source.id,
        "name": source.name,
        "kind": source.kind,
        "config": source.config,
        "enabled": source.enabled,
    }


@router.get("/api/scheduler/status")
def get_scheduler_status(user: User = Depends(current_user)):
    return scheduler_status()


@router.post("/api/scheduler/start")
def scheduler_start(user: User = Depends(current_user)):
    return start_scheduler()


@router.post("/api/scheduler/stop")
def scheduler_stop(user: User = Depends(current_user)):
    stop_scheduler()
    return {"running": False}


@router.post("/api/scheduler/run")
def scheduler_run_now(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _daily_pipeline()
    return scheduler_status()


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(db: Session = Depends(get_db)):
    total_jobs = db.scalar(select(func.count(Job.id))) or 0
    scored = db.scalar(select(func.count(JobMatch.id))) or 0
    strong = db.scalar(select(func.count(JobMatch.id)).where(JobMatch.score >= 80)) or 0
    relevant = db.scalar(select(func.count(JobMatch.id)).where(JobMatch.score >= 60)) or 0
    tailored = db.scalar(select(func.count(TailoredResume.id))) or 0
    apps = db.scalar(select(func.count(Application.id))) or 0
    enabled_sources = db.scalar(select(func.count(JobSource.id)).where(JobSource.enabled.is_(True))) or 0
    lines = [
        "# HELP jobhunter_jobs_discovered Total jobs stored",
        "# TYPE jobhunter_jobs_discovered gauge",
        f"jobhunter_jobs_discovered {total_jobs}",
        "# HELP jobhunter_jobs_scored Total job matches scored",
        "# TYPE jobhunter_jobs_scored gauge",
        f"jobhunter_jobs_scored {scored}",
        "# HELP jobhunter_strong_matches Matches scoring 80 or above",
        "# TYPE jobhunter_strong_matches gauge",
        f"jobhunter_strong_matches {strong}",
        "# HELP jobhunter_relevant_jobs Matches scoring 60 or above",
        "# TYPE jobhunter_relevant_jobs gauge",
        f"jobhunter_relevant_jobs {relevant}",
        "# HELP jobhunter_tailored_resumes Tailored resume packages created",
        "# TYPE jobhunter_tailored_resumes gauge",
        f"jobhunter_tailored_resumes {tailored}",
        "# HELP jobhunter_applications Applications tracked",
        "# TYPE jobhunter_applications gauge",
        f"jobhunter_applications {apps}",
        "# HELP jobhunter_sources_enabled Enabled discovery sources",
        "# TYPE jobhunter_sources_enabled gauge",
        f"jobhunter_sources_enabled {enabled_sources}",
    ]
    return "\n".join(lines) + "\n"


def _is_configured(kind: str, config: dict | None) -> bool:
    cls = CONNECTORS.get(kind)
    checker = getattr(cls, "is_configured", None)
    if checker is None:
        return True
    try:
        return bool(checker(config or {}))
    except Exception:
        return False


@router.get("/api/gmail/status")
def gmail_status(user: User = Depends(current_user)):
    from app.services.gmail import status

    return status()


@router.get("/api/gmail/auth-url")
def gmail_auth_url(user: User = Depends(current_user)):
    from app.services.gmail import get_auth_url

    try:
        return {"url": get_auth_url()}
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/gmail/callback")
def gmail_callback(
    code: str | None = None, state: str | None = None, error: str | None = None
):
    if error:
        return {"ok": False, "error": error}
    if not code:
        raise HTTPException(400, "Missing code")
    from app.services.gmail import exchange_code

    try:
        exchange_code(code, state)
    except Exception as exc:
        raise HTTPException(400, f"Token exchange failed: {exc}") from exc
    return {"ok": True, "message": "Gmail connected. You can close this tab."}


@router.post("/api/gmail/sync")
def gmail_sync(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    from app.services.gmail import sync_inbox

    try:
        return sync_inbox(db, user)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
