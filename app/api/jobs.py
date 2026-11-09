from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.serializers import INDIA_HINTS, US_HINTS, job_dict, match_dict, tailored_dict
from app.database import get_db
from app.models import Job, JobMatch, JobSource, TailoredResume, User
from app.schemas import JobImport, ManualTailorRequest, TailoredUpdate
from app.services.ats import extract_keywords, missing_keywords
from app.services.dedupe import job_hash
from app.services.discovery import run_discovery
from app.services.eligibility import eligibility_for
from app.services.jd_metadata import infer_company, infer_role_title
from app.services.matching import run_matching
from app.services.profiles import profile_dict
from app.services.lexicon import norm
from app.services.tailoring import (
    apply_experience_edits,
    build_tailored,
    export_tailored,
    filter_allowed_skills,
    refresh_match_metrics,
)

router = APIRouter(tags=["jobs"])


@router.get("/api/jobs")
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    q: str | None = None,
    min_score: float | None = None,
    remote: bool | None = None,
    region: str | None = None,
    india_eligible: bool | None = None,
    show_blocked: bool = False,
    show_stale: bool = False,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    stmt = (
        select(Job, JobMatch)
        .outerjoin(JobMatch, and_(JobMatch.job_id == Job.id, JobMatch.user_id == user.id))
        .order_by(func.coalesce(JobMatch.score, -1).desc(), Job.id.desc())
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.company.ilike(like), Job.description.ilike(like)))
    if min_score is not None:
        stmt = stmt.where(JobMatch.score >= min_score)
    if remote is not None:
        stmt = stmt.where(Job.remote.is_(remote))
    # Push stale filter to SQL (fast index scan)
    if not show_stale:
        stmt = stmt.where(or_(Job.stale.is_(False), Job.stale.is_(None)))
    # Push eligibility filter to SQL when column is populated
    if not show_blocked and india_eligible is None and not region:
        stmt = stmt.where(Job.eligibility_status != "blocked")
    if india_eligible is not None:
        if india_eligible:
            stmt = stmt.where(Job.eligibility_status == "allowed")
        else:
            stmt = stmt.where(Job.eligibility_status.in_(["blocked", "unclear"]))
    if region:
        key = region.lower()
        india_loc = or_(*[Job.location.ilike(f"%{hint}%") for hint in INDIA_HINTS])
        us_loc = or_(*[Job.location.ilike(f"%{hint}%") for hint in US_HINTS])
        if key == "india":
            stmt = stmt.where(india_loc)
        elif key == "us":
            stmt = stmt.where(us_loc)
        elif key == "global":
            stmt = stmt.where(Job.remote.is_(True), ~or_(india_loc, us_loc))
        elif key == "preferred":
            stmt = stmt.where(
                or_(india_loc, Job.remote.is_(True), Job.location.ilike("%remote%")),
                Job.eligibility_status != "blocked",
            )
        elif key == "india_wfh":
            stmt = stmt.where(
                india_loc,
                or_(Job.remote.is_(True), Job.location.ilike("%remote%")),
            )
    rows = db.execute(stmt.limit(5000)).all()
    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "count": len(page),
        "total": total,
        "items": [job_dict(job, match) for job, match in page],
    }


@router.get("/api/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    match = db.scalars(
        select(JobMatch).where(JobMatch.job_id == job.id, JobMatch.user_id == user.id)
    ).first()
    data = job_dict(job, match, full=True)
    data["keywords"] = extract_keywords(job.description or "")
    data["missing_keywords"] = missing_keywords(job.description or "", profile_dict(db, user)["skills"])
    return data


@router.post("/api/jobs/import")
def import_job(
    payload: JobImport,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    source = db.scalars(select(JobSource).where(JobSource.name == payload.source_name)).first()
    if not source:
        source = JobSource(
            name=payload.source_name, kind="manual", config={}, enabled=False,
            notes="Manually imported job listings",
        )
        db.add(source)
        db.commit()
        db.refresh(source)
    key = job_hash(payload.title, payload.company, payload.location, payload.url)
    existing = db.scalars(select(Job).where(Job.dedupe_hash == key)).first()
    if existing:
        raise HTTPException(409, f"Duplicate job already stored (id={existing.id})")
    job = Job(
        source_id=source.id,
        title=payload.title[:300],
        company=payload.company[:200],
        location=payload.location[:200],
        remote=payload.remote,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        currency=payload.currency,
        experience_min=payload.experience_min,
        experience_max=payload.experience_max,
        description=payload.description,
        url=payload.url,
        posted_at=payload.posted_at,
        eligibility_status=eligibility_for(
            payload.location, payload.remote, payload.description, payload.title
        ).status,
        dedupe_hash=key,
        raw={"imported": True},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    run_matching(db, user, profile_dict(db, user), job_ids=[job.id])
    match = db.scalars(
        select(JobMatch).where(JobMatch.job_id == job.id, JobMatch.user_id == user.id)
    ).first()
    return job_dict(job, match, full=True)


@router.post("/api/jobs/discover")
def discover(
    only: str | None = None,
    rematch: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    results = run_discovery(db, only=only)
    matched = run_matching(db, user, profile_dict(db, user)) if rematch else None
    return {"sources": results, "matching": matched}


@router.post("/api/matches/run")
def matches_run(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return run_matching(db, user, profile_dict(db, user))


@router.get("/api/matches")
def matches_list(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    min_score: float = 0,
    limit: int = Query(50, le=200),
):
    rows = db.execute(
        select(JobMatch, Job)
        .join(Job, JobMatch.job_id == Job.id)
        .where(JobMatch.user_id == user.id, JobMatch.score >= min_score)
        .order_by(JobMatch.score.desc())
        .limit(limit)
    ).all()
    return {"count": len(rows), "items": [match_dict(match, job) for match, job in rows]}


@router.post("/api/jobs/{job_id}/tailor")
def tailor(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    profile = profile_dict(db, user)
    if not profile.get("resume_text"):
        raise HTTPException(400, "Upload a resume before tailoring")
    tailored = build_tailored(db, user, job, profile)
    return tailored_dict(tailored)


@router.post("/api/tailor/manual")
def tailor_manual(
    payload: ManualTailorRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    description = payload.description.strip()
    if len(description) < 40:
        raise HTTPException(400, "Paste the full job description (at least 40 characters)")
    profile = profile_dict(db, user)
    if not profile.get("resume_text"):
        raise HTTPException(400, "Upload a resume before tailoring")

    title = payload.title.strip() or infer_role_title(description) or ""
    company = payload.company.strip() or infer_company(description) or ""
    location = payload.location.strip() or ("Remote" if payload.remote else "")
    base_key = job_hash(title, company, location, payload.url)
    key = hashlib.sha256(f"{base_key}|{description[:4000]}".encode("utf-8")).hexdigest()
    job = db.scalars(select(Job).where(Job.dedupe_hash == key)).first()
    if not job:
        job = Job(
            title=title[:300],
            company=company[:200],
            location=location[:200],
            remote=payload.remote,
            description=description,
            url=payload.url,
            eligibility_status=eligibility_for(
                location, payload.remote, description, title
            ).status,
            dedupe_hash=key,
            raw={"manual_jd": True, "source_label": "Pasted JD"},
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    tailored = build_tailored(db, user, job, profile)
    data = tailored_dict(tailored)
    data["job"] = job_dict(job, full=True)
    return data


@router.get("/api/jobs/{job_id}/tailored")
def job_tailored(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    item = db.scalars(
        select(TailoredResume)
        .where(TailoredResume.job_id == job_id, TailoredResume.user_id == user.id)
        .order_by(TailoredResume.id.desc())
    ).first()
    if not item:
        raise HTTPException(404, "No tailored resume for this job")
    return tailored_dict(item)


@router.patch("/api/tailored/{tailored_id}")
def update_tailored(
    tailored_id: int,
    payload: TailoredUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    item = db.get(TailoredResume, tailored_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "Tailored resume not found")
    profile = profile_dict(db, user)
    report = dict(item.match_report or {})
    warnings = list(report.get("warnings") or [])

    if payload.summary is not None:
        item.summary = payload.summary.strip()
    if payload.cover_letter is not None:
        item.cover_letter = payload.cover_letter.strip()
    if payload.skills is not None:
        groups = []
        for group in payload.skills:
            items = filter_allowed_skills(
                group.get("items") or [], profile.get("skills", [])
            )
            if items:
                groups.append(
                    {
                        "category": str(group.get("category") or "Other")[:80],
                        "items": items,
                    }
                )
        item.skills = groups
    if payload.experience is not None:
        sanitized, immutable_warnings = apply_experience_edits(
            profile, payload.experience
        )
        item.experience = sanitized
        warnings.extend(immutable_warnings)
    if payload.projects is not None:
        master = {
            norm(entry.get("name", "")): entry
            for entry in (profile.get("projects") or [])
        }
        projects = []
        for entry in payload.projects:
            original = master.get(norm(entry.get("name", "")))
            if not original:
                warnings.append(
                    f"Dropped edited project that is not in the master resume: "
                    f"{entry.get('name') or '?'}"
                )
                continue
            projects.append(
                {
                    **original,
                    "bullets": [
                        str(bullet).strip()
                        for bullet in (entry.get("bullets") or [])
                        if str(bullet).strip()
                    ][:3],
                }
            )
        item.projects = projects

    report = refresh_match_metrics(item, profile)
    report["warnings"] = list(dict.fromkeys(w for w in warnings if w))
    report["edited"] = True
    item.match_report = report

    job = db.get(Job, item.job_id)
    docx_path, pdf_path = export_tailored(item, profile, job)
    item.docx_path = str(docx_path)
    item.pdf_path = str(pdf_path) if pdf_path else ""
    db.commit()
    db.refresh(item)
    data = tailored_dict(item)
    data["job"] = job_dict(job, full=True) if job else None
    return data


@router.get("/api/tailored/{tailored_id}/download")
def download_tailored(
    tailored_id: int,
    fmt: str = "pdf",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    item = db.get(TailoredResume, tailored_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "Tailored resume not found")
    path = item.pdf_path if fmt.lower() == "pdf" else item.docx_path
    if not path or not Path(path).exists():
        raise HTTPException(404, f"{fmt} export not available")
    media = (
        "application/pdf"
        if fmt.lower() == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    filename = Path(path).name
    return FileResponse(path, media_type=media, filename=filename)
