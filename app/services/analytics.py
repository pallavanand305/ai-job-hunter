from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.serializers import region_for, work_mode_for
from app.services.eligibility import eligibility_for
from app.models import (
    Application,
    Interview,
    Job,
    JobMatch,
    OutreachMessage,
    Recruiter,
    TailoredResume,
    User,
)


def dashboard(db: Session, user: User) -> dict:
    total_jobs = db.scalar(select(func.count(Job.id))) or 0
    scored = db.scalar(select(func.count(JobMatch.id)).where(JobMatch.user_id == user.id)) or 0
    # Strong matches: score >= 80, excluding BLOCK jobs
    strong_rows = db.execute(
        select(JobMatch, Job)
        .join(Job, JobMatch.job_id == Job.id)
        .where(JobMatch.user_id == user.id, JobMatch.score >= 80)
    ).all()
    strong = sum(
        1 for match, job in strong_rows
        if eligibility_for(job.location, job.remote, job.description, job.title).status != "blocked"
    )
    relevant = (
        db.scalar(
            select(func.count(JobMatch.id)).where(JobMatch.user_id == user.id, JobMatch.score >= 60)
        )
        or 0
    )
    tailored = db.scalar(select(func.count(TailoredResume.id)).where(TailoredResume.user_id == user.id)) or 0

    app_rows = db.execute(
        select(Application.status, func.count(Application.id))
        .where(Application.user_id == user.id)
        .group_by(Application.status)
    ).all()
    app_counts = {status: count for status, count in app_rows}
    submitted = sum(app_counts.get(s, 0) for s in ("submitted", "interview", "assessment", "offer", "rejected"))
    pending_apps = app_counts.get("draft", 0) + app_counts.get("pending_approval", 0)

    outreach_rows = db.execute(
        select(OutreachMessage.status, func.count(OutreachMessage.id))
        .where(OutreachMessage.user_id == user.id)
        .group_by(OutreachMessage.status)
    ).all()
    outreach_counts = {status: count for status, count in outreach_rows}
    pending_outreach = outreach_counts.get("draft", 0) + outreach_counts.get("approved", 0)

    interviews = (
        db.scalar(
            select(func.count(Interview.id))
            .join(Application, Interview.application_id == Application.id, isouter=True)
            .where(Application.user_id == user.id)
        )
        or 0
    )
    responses = sum(app_counts.get(s, 0) for s in ("interview", "assessment", "offer", "rejected"))
    conversion = round(100 * submitted / total_jobs, 1) if total_jobs else 0.0

    top_matches_rows = db.execute(
        select(JobMatch, Job)
        .join(Job, JobMatch.job_id == Job.id)
        .where(JobMatch.user_id == user.id)
        .order_by(JobMatch.score.desc())
        .limit(50)  # fetch extra to filter BLOCK
    ).all()
    # Exclude BLOCK jobs from top matches
    top_matches = [
        (match, job) for match, job in top_matches_rows
        if eligibility_for(job.location, job.remote, job.description, job.title).status != "blocked"
    ][:8]

    recent_apps = db.execute(
        select(Application, Job)
        .join(Job, Application.job_id == Job.id)
        .where(Application.user_id == user.id)
        .order_by(Application.id.desc())
        .limit(8)
    ).all()

    return {
        "jobs_discovered": total_jobs,
        "jobs_scored": scored,
        "relevant_jobs": relevant,
        "strong_matches": strong,
        "tailored_packages": tailored,
        "applications": app_counts,
        "applications_submitted": submitted,
        "pending_approvals": pending_apps + pending_outreach,
        "pending_applications": pending_apps,
        "pending_outreach": pending_outreach,
        "outreach": outreach_counts,
        "recruiter_responses": responses,
        "interviews_scheduled": interviews,
        "rejections": app_counts.get("rejected", 0),
        "conversion_rate": conversion,
        "recruiters": db.scalar(select(func.count(Recruiter.id))) or 0,
        "top_matches": [
            {
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "remote": job.remote,
                "work_mode": work_mode_for(job.remote),
                "region": region_for(job.location, job.remote),
                "india_eligible": eligibility_for(
                    job.location, job.remote, job.description, job.title
                ).india_eligible,
                "eligibility": eligibility_for(
                    job.location, job.remote, job.description, job.title
                ).status,
                "url": job.url,
                "score": match.score,
                "matched_skills": match.matched_skills,
                "missing_skills": match.missing_skills,
            }
            for match, job in top_matches
        ],
        "recent_applications": [
            {
                "id": application.id,
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "status": application.status,
                "applied_at": application.applied_at.isoformat() if application.applied_at else None,
            }
            for application, job in recent_apps
        ],
    }
