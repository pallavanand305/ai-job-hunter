from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import CONNECTORS, NormalizedJob
from app.models import Job, JobSource
from app.services.eligibility import eligibility_for
from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SOURCES = [
    ("greenhouse", "greenhouse", {"boards": ["gitlab", "canonical"]},
     "Public Greenhouse boards. Edit config.boards to target companies you want.", True),
    ("lever", "lever", {"companies": ["leverdemo"]},
     "Public Lever postings. Edit config.companies to target companies you want.", True),
    ("remotive", "remotive", {"search": "python", "limit": 60}, "Free remote jobs API.", True),
    ("remoteok", "remoteok", {"tags": ["python", "machine learning", "devops"]},
     "Free remote jobs API.", True),
    ("arbeitnow", "arbeitnow", {}, "Free job board API.", True),
    ("jobicy", "jobicy", {"count": 100, "industry": "dev"}, "Free remote jobs API.", True),
    ("himalayas", "himalayas", {"limit": 60}, "Free remote job API (no key required).", True),
    ("weworkremotely", "weworkremotely", {},
     "We Work Remotely RSS feeds for programming and DevOps roles.", True),
    ("pythonjobs", "pythonjobs", {}, "Official python.org job board RSS feed.", True),
    ("workingnomads", "workingnomads", {}, "Free remote-jobs API (no key required).", True),
    ("themuse", "themuse", {"pages": 3, "categories": ["Software Engineering", "Data Science"]},
     "Free public jobs API (no key required).", True),
    ("landingjobs", "landingjobs", {"limit": 100}, "Free public tech-jobs API (no key required).", True),
    ("adzuna", "adzuna", {"country": "in", "what": "python", "results": 50},
     "Adzuna API. Set ADZUNA_APP_ID and ADZUNA_APP_KEY, then enable this source.", False),
    ("jooble", "jooble", {"keywords": "python developer", "location": "India"},
     "Jooble API. Set JOOBLE_API_KEY, then enable this source.", False),
    ("linkedin", "linkedin", {"feeds": []},
     "LinkedIn alert feed. Set LINKEDIN_FEED_URL; apply on LinkedIn manually.", False),
    ("naukri", "naukri", {"feeds": []},
     "Naukri alert feed. Set NAUKRI_FEED_URL; apply on Naukri manually.", False),
    ("indeed", "indeed", {"feeds": []},
     "Indeed alert feed. Set INDEED_FEED_URL; apply on Indeed manually.", False),
    ("instahyre", "instahyre", {"feeds": []},
     "Instahyre alert feed. Set INSTAHYRE_FEED_URL; apply on Instahyre manually.", False),
    ("wellfound", "wellfound", {"feeds": []},
     "Wellfound alert feed. Set WELLFOUND_FEED_URL; apply on Wellfound manually.", False),
    ("rss", "rss", {"feeds": []},
     "Add permitted alert/company RSS feeds. LinkedIn/Naukri/Indeed have no open apply API.", False),
]


def seed_sources(db: Session) -> None:
    rows = db.scalars(select(JobSource)).all()
    existing = {s.name: s for s in rows}
    for name, kind, config, notes, enabled in DEFAULT_SOURCES:
        if name in existing:
            continue
        db.add(JobSource(name=name, kind=kind, config=config, notes=notes, enabled=enabled))
    # Migrate the old invalid Jobicy config (geo=india returns HTTP 400).
    jobicy = existing.get("jobicy")
    if jobicy and jobicy.config.get("geo"):
        migrated = dict(jobicy.config)
        migrated.pop("geo", None)
        migrated["industry"] = "dev"
        migrated.setdefault("count", 100)
        jobicy.config = migrated
    db.commit()
    # Auto-enable sources once their keys/feeds are configured.
    for row in db.scalars(select(JobSource)).all():
        cls = CONNECTORS.get(row.kind)
        if cls is None or not getattr(cls, "requires_config", False) or row.enabled:
            continue
        checker = getattr(cls, "is_configured", None)
        if checker is not None and checker(row.config or {}):
            row.enabled = True
    db.commit()


def mark_stale_jobs(db: Session) -> int:
    """Mark jobs not seen for stale_days as stale=True. Returns count marked."""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=settings.stale_days)
    jobs = db.scalars(select(Job).where(Job.last_seen_at < cutoff, Job.stale.is_(False))).all()
    for job in jobs:
        job.stale = True
    db.commit()
    return len(jobs)


def persist_jobs(db: Session, source: JobSource, jobs: list[NormalizedJob]) -> dict:
    added = 0
    skipped = 0
    now = datetime.utcnow()
    seen = {row for row in db.scalars(select(Job.dedupe_hash)).all()}
    # Build hash→id map for updating last_seen_at on re-seen jobs
    existing_map = {
        row.dedupe_hash: row
        for row in db.scalars(select(Job).where(Job.source_id == source.id)).all()
    }
    for item in jobs:
        if not item.title or not item.company:
            skipped += 1
            continue
        key = job_hash(item.title, item.company, item.location, item.url)
        if key in seen:
            # Touch last_seen_at and clear stale flag for re-seen jobs
            existing = existing_map.get(key)
            if existing:
                existing.last_seen_at = now
                existing.stale = False
            skipped += 1
            continue
        seen.add(key)
        elig = eligibility_for(
            item.location, item.remote, item.description, item.title
        ).status
        db.add(
            Job(
                source_id=source.id,
                external_id=item.external_id,
                title=item.title[:300],
                company=item.company[:200],
                location=(item.location or "")[:200],
                remote=item.remote,
                salary_min=item.salary_min,
                salary_max=item.salary_max,
                currency=(item.currency or "")[:12],
                experience_min=item.experience_min,
                experience_max=item.experience_max,
                description=item.description,
                url=item.url,
                posted_at=item.posted_at,
                last_seen_at=now,
                eligibility_status=elig,
                dedupe_hash=key,
                raw=item.raw,
            )
        )
        added += 1
    source.last_synced_at = datetime.utcnow()
    source.last_status = "ok"
    source.last_error = ""
    source.last_fetched = len(jobs)
    source.last_added = added
    db.commit()
    return {"added": added, "skipped": skipped}


def run_discovery(db: Session, only: str | None = None) -> dict:
    seed_sources(db)
    sources = db.scalars(select(JobSource).where(JobSource.enabled.is_(True))).all()
    results: dict[str, dict] = {}
    for source in sources:
        if only and source.name != only:
            continue
        connector_cls = CONNECTORS.get(source.kind)
        if not connector_cls:
            results[source.name] = {"error": f"unknown connector kind: {source.kind}"}
            continue
        try:
            connector = connector_cls(source.config or {})
            jobs = connector.fetch()
            result = persist_jobs(db, source, jobs)
            result["fetched"] = len(jobs)
            results[source.name] = result
        except Exception as exc:  # keep other sources running
            logger.warning("Discovery failed for %s: %s", source.name, exc)
            db.rollback()
            failed = db.get(JobSource, source.id)
            if failed:
                failed.last_synced_at = datetime.utcnow()
                failed.last_status = "error"
                failed.last_error = str(exc)[:1000]
                failed.last_fetched = 0
                failed.last_added = 0
                db.commit()
            results[source.name] = {"error": str(exc)}
    return results
