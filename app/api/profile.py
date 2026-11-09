from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.serializers import iso
from app.database import get_db
from app.llm.client import get_llm
from app.models import Job, Resume, Skill, User
from app.schemas import ProfileUpdate
from app.services.ats import ats_score
from app.services.lexicon import find_skills, skill_category
from app.services.profiles import (
    get_master_resume,
    profile_dict,
    rebuild_profile,
    save_resume,
)
from app.services.resume_parser import extract_text_from_path

router = APIRouter(prefix="/api/profile", tags=["profile"])

ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md"}


@router.get("")
def get_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return profile_dict(db, user)


@router.put("")
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    data = payload.model_dump(exclude_unset=True)
    preferences = data.pop("preferences", None)
    for key, value in data.items():
        if value is not None:
            setattr(user, key, value)
    if preferences is not None:
        user.preferences = {
            **(user.preferences or {}),
            **preferences,
            "home_country": preferences.get("home_country") or "India",
            "outside_country_remote_only": preferences.get("outside_country_remote_only", True),
        }
    db.commit()
    db.refresh(user)
    return profile_dict(db, user)


@router.post("/skills")
def add_skills(
    skills: list[str],
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    existing = {s.name for s in db.scalars(select(Skill).where(Skill.user_id == user.id)).all()}
    for name in skills:
        if name not in existing:
            db.add(Skill(user_id=user.id, name=name, category=skill_category(name), source="manual"))
    db.commit()
    return profile_dict(db, user)


@router.post("/resume")
async def upload_resume(
    file: UploadFile = File(...),
    variant: str = Form("master"),
    make_master: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type {suffix}. Use PDF, DOCX or TXT.")
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(400, "Empty file")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Resume file is too large (maximum 10 MB)")
    try:
        resume = save_resume(
            db, user, file.filename or f"resume{suffix}", content, variant=variant, make_master=make_master
        )
    except Exception as exc:
        raise HTTPException(400, f"Could not parse resume: {exc}") from exc
    return {
        "id": resume.id,
        "filename": resume.filename,
        "variant": resume.variant,
        "is_master": resume.is_master,
        "text_chars": len(resume.content_text),
        "skills_found": len((resume.structured or {}).get("skills", [])),
        "profile": profile_dict(db, user),
    }


@router.get("/resumes")
def list_resumes(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(
        select(Resume).where(Resume.user_id == user.id).order_by(Resume.id.desc())
    ).all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "variant": r.variant,
            "is_master": r.is_master,
            "uploaded_at": iso(r.uploaded_at),
            "chars": len(r.content_text),
        }
        for r in rows
    ]


@router.post("/resumes/{resume_id}/activate")
def activate_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    resume = db.get(Resume, resume_id)
    if not resume or resume.user_id != user.id:
        raise HTTPException(404, "Resume not found")
    for other in db.scalars(select(Resume).where(Resume.user_id == user.id)).all():
        other.is_master = other.id == resume.id
    db.commit()
    rebuild_profile(db, user)
    return {"ok": True, "master_resume_id": resume.id, "profile": profile_dict(db, user)}


@router.post("/rebuild")
def rebuild(db: Session = Depends(get_db), user: User = Depends(current_user)):
    user = rebuild_profile(db, user)
    return profile_dict(db, user)


@router.get("/ats")
def ats(
    job_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    profile = profile_dict(db, user)
    if job_id:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        result = ats_score(job.description or "", profile["skills"])
        result["job"] = {"id": job.id, "title": job.title, "company": job.company}
        return result
    skills = find_skills(profile.get("resume_text", ""))
    grouped: dict[str, list[str]] = {}
    for name, category in skills.items():
        grouped.setdefault(category, []).append(name)
    return {"total_skills": len(skills), "by_category": grouped}


@router.get("/llm")
def llm_info(user: User = Depends(current_user)):
    return get_llm().info()
