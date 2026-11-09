from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.serializers import outreach_dict, recruiter_dict
from app.database import get_db
from app.models import Job, OutreachMessage, Recruiter, User
from app.schemas import OutreachCreate, RecruiterCreate
from app.services import outreach as outreach_service
from app.services.profiles import profile_dict

router = APIRouter(tags=["outreach"])


@router.get("/api/recruiters")
def list_recruiters(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(Recruiter).order_by(Recruiter.id.desc())).all()
    return {"count": len(rows), "items": [recruiter_dict(r) for r in rows]}


@router.post("/api/recruiters")
def create_recruiter(
    payload: RecruiterCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    recruiter = outreach_service.find_or_create_recruiter(
        db,
        name=payload.name,
        company=payload.company,
        email=payload.email,
        linkedin_url=payload.linkedin_url,
        role=payload.role,
        notes=payload.notes,
        source=payload.source,
    )
    return recruiter_dict(recruiter)


@router.get("/api/outreach")
def list_outreach(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(
        select(OutreachMessage)
        .where(OutreachMessage.user_id == user.id)
        .order_by(OutreachMessage.id.desc())
    ).all()
    recruiters = {r.id: r for r in db.scalars(select(Recruiter)).all()}
    return {
        "count": len(rows),
        "items": [outreach_dict(m, recruiters.get(m.recruiter_id)) for m in rows],
    }


@router.post("/api/outreach")
def draft_outreach(
    payload: OutreachCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = db.get(Job, payload.job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    recruiter = db.get(Recruiter, payload.recruiter_id) if payload.recruiter_id else None
    try:
        message = outreach_service.draft_outreach(
            db, user, job, profile_dict(db, user), recruiter=recruiter, channel=payload.channel
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return outreach_dict(message, recruiter)


@router.post("/api/outreach/{message_id}/approve")
def approve_outreach(
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    message = db.get(OutreachMessage, message_id)
    if not message or message.user_id != user.id:
        raise HTTPException(404, "Message not found")
    outreach_service.approve_outreach(db, message)
    return outreach_dict(message, db.get(Recruiter, message.recruiter_id) if message.recruiter_id else None)


@router.post("/api/outreach/{message_id}/send")
def send_outreach(
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    message = db.get(OutreachMessage, message_id)
    if not message or message.user_id != user.id:
        raise HTTPException(404, "Message not found")
    try:
        outreach_service.send_outreach(db, message)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(400, f"Email sending unavailable: {exc}") from exc
    return outreach_dict(message, db.get(Recruiter, message.recruiter_id) if message.recruiter_id else None)


@router.post("/api/outreach/{message_id}/followup")
def followup(
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    message = db.get(OutreachMessage, message_id)
    if not message or message.user_id != user.id:
        raise HTTPException(404, "Message not found")
    followup = outreach_service.draft_followup(db, user, message, profile_dict(db, user))
    return outreach_dict(followup)
