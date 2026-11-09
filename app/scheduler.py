from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.services.analytics import dashboard
from app.services.discovery import mark_stale_jobs, run_discovery
from app.services.matching import run_matching
from app.services.profiles import get_or_create_user, profile_dict

logger = logging.getLogger(__name__)

_scheduler = None
_last_run: dict = {}


def _daily_pipeline() -> None:
    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        discovery = run_discovery(db)
        stale_count = mark_stale_jobs(db)
        matched = run_matching(db, user, profile_dict(db, user))
        _last_run["daily"] = {
            "at": datetime.utcnow().isoformat(),
            "discovery": discovery,
            "stale_marked": stale_count,
            "matching": matched,
        }
        logger.info("Daily pipeline done: %s", _last_run["daily"])
    except Exception as exc:  # pragma: no cover
        logger.exception("Daily pipeline failed: %s", exc)
    finally:
        db.close()


def _rematch() -> None:
    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        run_matching(db, user, profile_dict(db, user))
        _last_run["match"] = datetime.utcnow().isoformat()
    except Exception as exc:  # pragma: no cover
        logger.exception("Rematch failed: %s", exc)
    finally:
        db.close()


def _gmail_sync() -> None:
    db = SessionLocal()
    try:
        from app.services.gmail import sync_inbox

        user = get_or_create_user(db)
        result = sync_inbox(db, user)
        _last_run["gmail"] = {"at": datetime.utcnow().isoformat(), "result": result}
    except Exception as exc:
        _last_run["gmail"] = {"at": datetime.utcnow().isoformat(), "error": str(exc)}
    finally:
        db.close()


def start_scheduler() -> dict:
    global _scheduler
    if not settings.scheduler_enabled:
        return {"running": False, "reason": "SCHEDULER_ENABLED=false"}
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except Exception:
        return {"running": False, "reason": "APScheduler not installed (pip install apscheduler)"}
    if _scheduler and _scheduler.running:
        return {"running": True, "reason": "already running"}
    _scheduler = BackgroundScheduler(timezone=settings.timezone)
    _scheduler.add_job(
        _daily_pipeline,
        CronTrigger(hour=settings.discovery_hour, minute=settings.discovery_minute),
        id="daily_pipeline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        _rematch,
        IntervalTrigger(minutes=settings.match_interval_minutes),
        id="rematch",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )
    if settings.google_enabled and Path(settings.google_token_file).exists():
        _scheduler.add_job(
            _gmail_sync,
            IntervalTrigger(minutes=settings.gmail_sync_minutes),
            id="gmail_sync",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=1800,
        )
    _scheduler.start()
    logger.info("Scheduler started")
    return {"running": True, "reason": "started"}


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None


def scheduler_status() -> dict:
    jobs = []
    if _scheduler and _scheduler.running:
        for job in _scheduler.get_jobs():
            jobs.append({"id": job.id, "next_run": str(job.next_run_time)})
    return {
        "running": bool(_scheduler and _scheduler.running),
        "enabled": settings.scheduler_enabled,
        "timezone": settings.timezone,
        "daily_at": f"{settings.discovery_hour:02d}:{settings.discovery_minute:02d}",
        "jobs": jobs,
        "last_runs": _last_run,
    }
