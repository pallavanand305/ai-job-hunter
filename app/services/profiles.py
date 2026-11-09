from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Resume, Skill, User
from app.services.lexicon import canonical_skill, skill_category
from app.services.profile_extractor import parse_resume


def default_preferences() -> dict:
    return {
        "roles": settings.roles,
        "locations": [
            # Preferred on-site cities (score 1.0)
            "Noida", "Greater Noida", "Delhi", "Gurgaon", "Gurugram",
            "Bangalore", "Bengaluru", "Hyderabad", "Pune", "Mumbai",
            "Ahmedabad", "Gandhinagar",
        ],
        "home_country": "India",
        "outside_country_remote_only": True,
        "remote_ok": settings.default_remote_ok,
        "min_salary": settings.default_min_salary,
        "currency": settings.default_currency,
        "seniority": "",
        "exclude_companies": [],
        "must_have_skills": [],
        "nice_to_have_skills": [],
    }


def get_or_create_user(db: Session) -> User:
    user = db.scalars(select(User).order_by(User.id)).first()
    if user:
        return user
    user = User(
        name=settings.default_user_name,
        email=settings.default_user_email,
        location=settings.default_user_location,
        headline="AI Engineer | Python Backend | AWS | DevOps | MLOps",
        preferences=default_preferences(),
        links={},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_master_resume(db: Session, user: User) -> Resume | None:
    return db.scalars(
        select(Resume).where(Resume.user_id == user.id).order_by(Resume.is_master.desc(), Resume.id.desc())
    ).first()


def save_resume(
    db: Session,
    user: User,
    filename: str,
    content: bytes,
    *,
    variant: str = "master",
    make_master: bool = False,
) -> Resume:
    from app.services.resume_parser import extract_text

    text = extract_text(filename, content)
    parsed = parse_resume(text)
    if make_master:
        for existing in db.scalars(select(Resume).where(Resume.user_id == user.id)).all():
            existing.is_master = False

    resume = Resume(
        user_id=user.id,
        filename=filename,
        variant=variant,
        content_text=text,
        structured=parsed,
        is_master=make_master or not get_master_resume(db, user),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    if resume.is_master:
        apply_parsed_profile(db, user, parsed)
    return resume


def upsert_skills(db: Session, user: User, skill_names: list[str], source: str = "resume") -> None:
    existing = {s.name for s in db.scalars(select(Skill).where(Skill.user_id == user.id)).all()}
    for name in skill_names:
        canonical = canonical_skill(name)
        if canonical in existing:
            continue
        db.add(
            Skill(
                user_id=user.id,
                name=canonical,
                category=skill_category(canonical),
                source=source,
            )
        )
        existing.add(canonical)


def apply_parsed_profile(db: Session, user: User, parsed: dict) -> User:
    user.name = parsed.get("name") or user.name
    user.email = parsed.get("email") or user.email
    user.phone = parsed.get("phone") or user.phone
    user.location = parsed.get("location") or user.location
    user.headline = parsed.get("headline") or user.headline
    user.summary = parsed.get("summary") or user.summary
    user.years_experience = parsed.get("years_experience") or user.years_experience
    links = dict(user.links or {})
    links.update({k: v for k, v in (parsed.get("links") or {}).items() if v})
    user.links = links
    upsert_skills(db, user, parsed.get("skills", []))
    db.commit()
    db.refresh(user)
    return user


def rebuild_profile(db: Session, user: User) -> User:
    resume = get_master_resume(db, user)
    if not resume:
        return user
    parsed = resume.structured or parse_resume(resume.content_text)
    resume.structured = parsed
    db.add(resume)
    db.commit()
    return apply_parsed_profile(db, user, parsed)


def profile_dict(db: Session, user: User) -> dict:
    resume = get_master_resume(db, user)
    skills = [s.name for s in db.scalars(select(Skill).where(Skill.user_id == user.id)).all()]
    parsed_skills = (resume.structured or {}).get("skills", []) if resume else []
    merged = list(dict.fromkeys([*skills, *parsed_skills]))
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "location": user.location,
        "headline": user.headline,
        "summary": user.summary,
        "years_experience": user.years_experience,
        "links": user.links or {},
        "preferences": user.preferences or default_preferences(),
        "skills": merged,
        "resume_text": resume.content_text if resume else "",
        "resume_id": resume.id if resume else None,
        "resume_variant": resume.variant if resume else "",
        "experience": (resume.structured or {}).get("experience", []) if resume else [],
        "projects": (resume.structured or {}).get("projects", []) if resume else [],
        "education": (resume.structured or {}).get("education", []) if resume else [],
        "certifications": (resume.structured or {}).get("certifications", []) if resume else [],
    }


def store_upload(filename: str, content: bytes) -> Path:
    safe = Path(filename).name
    dest = Path(settings.uploads_dir) / safe
    dest.write_bytes(content)
    return dest
