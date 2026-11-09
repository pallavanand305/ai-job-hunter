from __future__ import annotations

from app.models import (
    Application,
    Interview,
    Job,
    JobMatch,
    OutreachMessage,
    Recruiter,
    TailoredResume,
)
from app.services.eligibility import eligibility_for, normalize_location


INDIA_HINTS = (
    "india", "noida", "greater noida", "delhi", "new delhi", "gurgaon", "gurugram",
    "mumbai", "pune", "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata",
    "ahmedabad", "gandhinagar", "faridabad", "ghaziabad",
    "indore", "coimbatore", "kochi", "chandigarh", "lucknow", "kanpur", "nagpur",
    "mysore", "trivandrum", "jaipur",
)
US_HINTS = (
    "united states", "usa", "u.s.", "new york", "san francisco", "seattle", "austin",
    "boston", "chicago", "los angeles", "california", "texas", "washington", "atlanta",
    "denver", "us remote", "remote - us", "remote, us",
)


def iso(value):
    return value.isoformat() if value else None


def region_for(location: str | None, remote: bool = False) -> str:
    text = normalize_location(location).lower()
    if any(hint in text for hint in INDIA_HINTS):
        return "India"
    if any(hint in text for hint in US_HINTS):
        return "US"
    generic = not text or any(word in text for word in ("remote", "worldwide", "anywhere", "global"))
    if remote or generic:
        return "Global"
    return "Other"


def work_mode_for(remote: bool) -> str:
    return "Remote/WFH" if remote else "Onsite/Hybrid"


def job_dict(job: Job, match: JobMatch | None = None, *, full: bool = False) -> dict:
    eligibility = eligibility_for(job.location, job.remote, job.description, job.title)
    # Map status to user-facing badge label
    badge_map = {"allowed": "Yes", "blocked": "No", "unclear": "Unclear"}
    data = {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": normalize_location(job.location),
        "remote": job.remote,
        "work_mode": work_mode_for(job.remote),
        "region": region_for(job.location, job.remote),
        "india_eligible": eligibility.india_eligible,
        "eligibility": eligibility.status,
        "eligibility_badge": badge_map.get(eligibility.status, "Unclear"),
        "eligibility_reason": eligibility.reason,
        "eligibility_evidence": eligibility.evidence,
        "url": job.url,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "currency": job.currency,
        "experience_min": job.experience_min,
        "experience_max": job.experience_max,
        "posted_at": iso(job.posted_at),
        "fetched_at": iso(job.fetched_at),
        "last_seen_at": iso(getattr(job, "last_seen_at", None)),
        "stale": getattr(job, "stale", False),
        "source_id": job.source_id,
    }
    if full:
        data["description"] = job.description
    if match:
        data.update(
            {
                "score": match.score,
                "skill_score": match.skill_score,
                "experience_score": match.experience_score,
                "responsibility_score": match.responsibility_score,
                "salary_score": match.salary_score,
                "location_score": match.location_score,
                "matched_skills": match.matched_skills,
                "missing_skills": match.missing_skills,
                "rationale": match.rationale,
            }
        )
    return data


def match_dict(match: JobMatch, job: Job | None = None) -> dict:
    data = {
        "job_id": match.job_id,
        "score": match.score,
        "skill_score": match.skill_score,
        "experience_score": match.experience_score,
        "responsibility_score": match.responsibility_score,
        "salary_score": match.salary_score,
        "location_score": match.location_score,
        "matched_skills": match.matched_skills,
        "missing_skills": match.missing_skills,
        "rationale": match.rationale,
    }
    if job:
        data["job"] = job_dict(job)
    return data


def tailored_dict(item: TailoredResume) -> dict:
    return {
        "id": item.id,
        "job_id": item.job_id,
        "resume_id": item.resume_id,
        "summary": item.summary,
        "skills": item.skills,
        "experience": item.experience,
        "projects": item.projects,
        "cover_letter": item.cover_letter,
        "keywords": item.keywords,
        "match_report": item.match_report or {},
        "has_docx": bool(item.docx_path),
        "has_pdf": bool(item.pdf_path),
        "created_at": iso(item.created_at),
    }


def application_dict(app: Application, job: Job | None = None) -> dict:
    data = {
        "id": app.id,
        "job_id": app.job_id,
        "tailored_resume_id": app.tailored_resume_id,
        "status": app.status,
        "mode": app.mode,
        "confirmation_id": app.confirmation_id,
        "notes": app.notes,
        "applied_at": iso(app.applied_at),
        "created_at": iso(app.created_at),
        "updated_at": iso(app.updated_at),
    }
    if job:
        data["job"] = job_dict(job)
    return data


def recruiter_dict(item: Recruiter) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "company": item.company,
        "email": item.email,
        "linkedin_url": item.linkedin_url,
        "role": item.role,
        "source": item.source,
        "notes": item.notes,
        "created_at": iso(item.created_at),
    }


def outreach_dict(item: OutreachMessage, recruiter: Recruiter | None = None) -> dict:
    data = {
        "id": item.id,
        "job_id": item.job_id,
        "recruiter_id": item.recruiter_id,
        "channel": item.channel,
        "subject": item.subject,
        "body": item.body,
        "status": item.status,
        "approved_at": iso(item.approved_at),
        "sent_at": iso(item.sent_at),
        "created_at": iso(item.created_at),
    }
    if recruiter:
        data["recruiter"] = recruiter_dict(recruiter)
    return data


def interview_dict(item: Interview) -> dict:
    return {
        "id": item.id,
        "application_id": item.application_id,
        "job_id": item.job_id,
        "scheduled_at": iso(item.scheduled_at),
        "kind": item.kind,
        "notes": item.notes,
        "created_at": iso(item.created_at),
    }
