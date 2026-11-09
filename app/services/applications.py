from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, ApplicationEvent, Interview, Job, TailoredResume, User

ALLOWED_TRANSITIONS = {
    "draft": {"pending_approval", "approved", "withdrawn"},
    "pending_approval": {"approved", "draft", "withdrawn"},
    "approved": {"submitted", "withdrawn"},
    "submitted": {"interview", "assessment", "rejected", "offer", "withdrawn"},
    "interview": {"offer", "rejected", "withdrawn"},
    "assessment": {"interview", "rejected", "withdrawn"},
    "offer": set(),
    "rejected": set(),
    "withdrawn": set(),
}


def log_event(db: Session, application: Application, status: str, note: str = "") -> None:
    db.add(ApplicationEvent(application_id=application.id, status=status, note=note))
    db.commit()


def get_application(db: Session, user: User, job_id: int) -> Application | None:
    return db.scalars(
        select(Application).where(Application.user_id == user.id, Application.job_id == job_id)
    ).first()


def create_application(
    db: Session,
    user: User,
    job: Job,
    *,
    tailored_resume_id: int | None = None,
    mode: str = "manual",
    notes: str = "",
) -> Application:
    existing = get_application(db, user, job.id)
    if existing:
        raise ValueError("An application already exists for this job (duplicate prevention)")
    if tailored_resume_id:
        tailored = db.get(TailoredResume, tailored_resume_id)
        if not tailored or tailored.job_id != job.id:
            raise ValueError("Tailored resume does not belong to this job")
    application = Application(
        user_id=user.id,
        job_id=job.id,
        tailored_resume_id=tailored_resume_id,
        mode=mode,
        status="draft",
        notes=notes,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    log_event(db, application, "draft", "Application package created")
    return application


def transition(db: Session, application: Application, status: str, note: str = "") -> Application:
    allowed = ALLOWED_TRANSITIONS.get(application.status, set())
    if status not in allowed and status != application.status:
        raise ValueError(f"Invalid transition {application.status} -> {status}")
    application.status = status
    if status == "submitted" and not application.applied_at:
        application.applied_at = datetime.utcnow()
    db.commit()
    db.refresh(application)
    log_event(db, application, status, note)
    return application


def approve(db: Session, application: Application) -> Application:
    if application.status not in {"draft", "pending_approval"}:
        raise ValueError(f"Cannot approve application in status {application.status}")
    return transition(db, application, "approved", "Approved by candidate")


def submit(
    db: Session,
    application: Application,
    *,
    confirmation_id: str = "",
    authorized: bool = False,
) -> Application:
    if not authorized:
        raise ValueError(
            "Explicit authorization required. The system is drafts-only: submit through the "
            "official portal yourself, then record the confirmation ID here."
        )
    if application.status != "approved":
        raise ValueError("Application must be approved before submission")
    application.confirmation_id = confirmation_id
    return transition(
        db, application, "submitted", f"Submitted (confirmation: {confirmation_id or 'n/a'})"
    )


def record_status(db: Session, application: Application, status: str, note: str = "") -> Application:
    return transition(db, application, status, note)


def add_interview(
    db: Session,
    application: Application | None,
    job_id: int | None,
    scheduled_at: datetime | None,
    kind: str = "interview",
    notes: str = "",
) -> Interview:
    interview = Interview(
        application_id=application.id if application else None,
        job_id=job_id,
        scheduled_at=scheduled_at,
        kind=kind,
        notes=notes,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)
    return interview
