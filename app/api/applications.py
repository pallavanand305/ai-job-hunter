from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.serializers import application_dict, interview_dict, iso
from app.database import get_db
from app.models import Application, ApplicationEvent, Interview, Job, TailoredResume, User
from app.schemas import ApplicationCreate, ApplicationStatusUpdate
from app.services import applications as app_service

router = APIRouter(tags=["applications"])


class SubmitPayload(BaseModel):
    confirmation_id: str = ""
    authorized: bool = False


class InterviewCreate(BaseModel):
    application_id: int | None = None
    job_id: int | None = None
    scheduled_at: datetime | None = None
    kind: str = "interview"
    notes: str = ""


@router.get("/api/applications")
def list_applications(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    rows = db.execute(
        select(Application, Job)
        .join(Job, Application.job_id == Job.id)
        .where(Application.user_id == user.id)
        .order_by(Application.id.desc())
    ).all()
    return {"count": len(rows), "items": [application_dict(app, job) for app, job in rows]}


@router.post("/api/applications")
def create_application(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = db.get(Job, payload.job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    tailored_id = payload.tailored_resume_id
    if not tailored_id:
        latest = db.scalars(
            select(TailoredResume)
            .where(TailoredResume.job_id == job.id, TailoredResume.user_id == user.id)
            .order_by(TailoredResume.id.desc())
        ).first()
        tailored_id = latest.id if latest else None
    try:
        application = app_service.create_application(
            db, user, job, tailored_resume_id=tailored_id, mode=payload.mode, notes=payload.notes
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return application_dict(application, job)


@router.get("/api/applications/{application_id}")
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    application = db.get(Application, application_id)
    if not application or application.user_id != user.id:
        raise HTTPException(404, "Application not found")
    job = db.get(Job, application.job_id)
    events = db.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application.id)
        .order_by(ApplicationEvent.id.desc())
    ).all()
    data = application_dict(application, job)
    data["events"] = [
        {"status": e.status, "note": e.note, "created_at": iso(e.created_at)} for e in events
    ]
    return data


@router.post("/api/applications/{application_id}/approve")
def approve_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    application = db.get(Application, application_id)
    if not application or application.user_id != user.id:
        raise HTTPException(404, "Application not found")
    try:
        app_service.approve(db, application)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return application_dict(application, db.get(Job, application.job_id))


@router.post("/api/applications/{application_id}/submit")
def submit_application(
    application_id: int,
    payload: SubmitPayload,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    application = db.get(Application, application_id)
    if not application or application.user_id != user.id:
        raise HTTPException(404, "Application not found")
    try:
        app_service.submit(
            db, application, confirmation_id=payload.confirmation_id, authorized=payload.authorized
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return application_dict(application, db.get(Job, application.job_id))


@router.post("/api/applications/{application_id}/status")
def update_status(
    application_id: int,
    payload: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    application = db.get(Application, application_id)
    if not application or application.user_id != user.id:
        raise HTTPException(404, "Application not found")
    try:
        app_service.record_status(db, application, payload.status, payload.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return application_dict(application, db.get(Job, application.job_id))


@router.get("/api/interviews")
def list_interviews(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.execute(
        select(Interview)
        .join(Application, Interview.application_id == Application.id, isouter=True)
        .where(Application.user_id == user.id)
        .order_by(Interview.id.desc())
    ).scalars().all()
    return {"count": len(rows), "items": [interview_dict(i) for i in rows]}


@router.post("/api/interviews")
def create_interview(
    payload: InterviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    application = db.get(Application, payload.application_id) if payload.application_id else None
    if application and application.user_id != user.id:
        raise HTTPException(404, "Application not found")
    interview = app_service.add_interview(
        db, application, payload.job_id, payload.scheduled_at, payload.kind, payload.notes
    )
    return interview_dict(interview)
