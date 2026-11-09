from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import get_llm
from app.llm.prompts import OUTREACH_SYSTEM, outreach_prompt
from app.models import Job, OutreachMessage, Recruiter, TailoredResume, User

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def find_or_create_recruiter(
    db: Session,
    *,
    name: str = "",
    company: str = "",
    email: str = "",
    linkedin_url: str = "",
    role: str = "",
    source: str = "manual",
    notes: str = "",
) -> Recruiter:
    if email:
        existing = db.scalars(
            select(Recruiter).where(Recruiter.email == email, Recruiter.company == company)
        ).first()
        if existing:
            return existing
    recruiter = Recruiter(
        name=name,
        company=company,
        email=email,
        linkedin_url=linkedin_url,
        role=role,
        source=source,
        notes=notes,
    )
    db.add(recruiter)
    db.commit()
    db.refresh(recruiter)
    return recruiter


def recruiter_from_job(db: Session, job: Job) -> Recruiter | None:
    match = EMAIL_RE.search(job.description or "")
    if not match:
        return None
    email = match.group(0)
    if any(bad in email.lower() for bad in ("example.com", "yourdomain", "test@")):
        return None
    return find_or_create_recruiter(
        db,
        company=job.company,
        email=email,
        source="job_description",
        notes=f"Extracted from {job.title} posting",
    )


def _fallback_email(profile: dict, job: Job, recruiter: Recruiter | None) -> tuple[str, str, str]:
    name = profile.get("name") or "Candidate"
    top = ", ".join(profile.get("skills", [])[:5])
    greeting = f"Dear {recruiter.name}," if recruiter and recruiter.name else "Hello Hiring Team,"
    subject = f"Application for {job.title} - {name}"
    body = (
        f"{greeting}\n\n"
        f"I came across the {job.title} opportunity at {job.company} and would like to apply. "
        f"My experience includes {top}, with {profile.get('years_experience', 0):g}+ years building "
        f"production systems.\n\n"
        f"I have attached a tailored resume. I would be glad to discuss how my experience aligns "
        f"with your requirements.\n\n"
        f"Regards,\n{name}\n{profile.get('phone', '')}\n{profile.get('email', '')}"
    )
    linkedin = (
        f"Hi {recruiter.name if recruiter and recruiter.name else 'there'}, I'm interested in the "
        f"{job.title} role at {job.company}. I have {profile.get('years_experience', 0):g}+ years "
        f"of experience in {top}. Would love to connect."
    )
    return subject, body, linkedin


def draft_outreach(
    db: Session,
    user: User,
    job: Job,
    profile: dict,
    *,
    recruiter: Recruiter | None = None,
    channel: str = "email",
) -> OutreachMessage:
    recruiter = recruiter or recruiter_from_job(db, job)

    existing_query = select(OutreachMessage).where(
        OutreachMessage.user_id == user.id,
        OutreachMessage.job_id == job.id,
        OutreachMessage.channel == channel,
    )
    if recruiter is not None:
        existing_query = existing_query.where(OutreachMessage.recruiter_id == recruiter.id)
    else:
        existing_query = existing_query.where(OutreachMessage.recruiter_id.is_(None))
    existing = db.scalars(existing_query).first()
    if existing:
        return existing

    if recruiter is not None:
        cutoff = datetime.utcnow() - timedelta(days=30)
        recent_contact = db.scalars(
            select(OutreachMessage).where(
                OutreachMessage.recruiter_id == recruiter.id,
                OutreachMessage.status == "sent",
                OutreachMessage.sent_at >= cutoff,
            )
        ).first()
        if recent_contact:
            raise ValueError(
                f"Recruiter {recruiter.name or recruiter.email} was contacted within the last 30 days. "
                "Avoid repeated outreach."
            )

    tailored = db.scalars(
        select(TailoredResume).where(TailoredResume.job_id == job.id).order_by(TailoredResume.id.desc())
    ).first()
    tailored_bits = None
    if tailored:
        tailored_bits = {"summary": tailored.summary, "keywords": tailored.keywords}

    subject, body, linkedin = _fallback_email(profile, job, recruiter)

    llm = get_llm()
    if llm.usable:
        data = llm.complete_json(
            OUTREACH_SYSTEM,
            outreach_prompt(
                profile,
                {"title": job.title, "company": job.company, "location": job.location,
                 "description": job.description},
                tailored_bits,
                {"name": recruiter.name, "role": recruiter.role, "company": recruiter.company}
                if recruiter else None,
            ),
            default={},
        )
        if isinstance(data, dict):
            subject = str(data.get("subject") or subject).strip()
            body = str(data.get("body") or body).strip()
            linkedin = str(data.get("linkedin_message") or linkedin).strip()

    message = OutreachMessage(
        recruiter_id=recruiter.id if recruiter else None,
        job_id=job.id,
        user_id=user.id,
        channel=channel,
        subject=subject[:300],
        body=body if channel == "email" else linkedin,
        status="draft",
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def approve_outreach(db: Session, message: OutreachMessage) -> OutreachMessage:
    message.status = "approved"
    message.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    return message


def send_outreach(db: Session, message: OutreachMessage) -> OutreachMessage:
    if message.status not in {"approved", "draft"}:
        raise ValueError(f"Cannot send message in status {message.status}")
    if message.status == "draft":
        raise ValueError("Message requires explicit approval before sending")
    if message.channel != "email":
        message.status = "ready_to_copy"
        db.commit()
        db.refresh(message)
        return message

    from app.services.gmail import send_email

    recruiter = db.get(Recruiter, message.recruiter_id) if message.recruiter_id else None
    if not recruiter or not recruiter.email:
        raise ValueError("No recruiter email on file")
    send_email(to=recruiter.email, subject=message.subject, body=message.body)
    message.status = "sent"
    message.sent_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    return message


def draft_followup(db: Session, user: User, message: OutreachMessage, profile: dict) -> OutreachMessage:
    name = profile.get("name") or "Candidate"
    body = (
        f"Hello,\n\nI wanted to follow up on my application for the role discussed earlier. "
        f"I remain very interested and would be happy to provide any additional information.\n\n"
        f"Regards,\n{name}"
    )
    followup = OutreachMessage(
        recruiter_id=message.recruiter_id,
        job_id=message.job_id,
        user_id=user.id,
        channel=message.channel,
        subject=f"Following up: {message.subject}"[:300],
        body=body,
        status="draft",
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)
    return followup
