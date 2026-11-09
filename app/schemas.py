from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Preferences(BaseModel):
    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    home_country: str = "India"
    outside_country_remote_only: bool = True
    remote_ok: bool = True
    min_salary: int = 0
    currency: str = "INR"
    seniority: str = ""
    exclude_companies: list[str] = Field(default_factory=list)
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    headline: str | None = None
    summary: str | None = None
    years_experience: float | None = None
    links: dict[str, str] | None = None
    preferences: Preferences | None = None


class JobImport(BaseModel):
    title: str
    company: str
    location: str = ""
    description: str = ""
    url: str = ""
    remote: bool = False
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str = ""
    experience_min: float | None = None
    experience_max: float | None = None
    posted_at: datetime | None = None
    source_name: str = "manual"


class ManualTailorRequest(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    description: str
    url: str = ""
    remote: bool = False


class TailoredUpdate(BaseModel):
    summary: str | None = None
    skills: list[dict] | None = None
    experience: list[dict] | None = None
    projects: list[dict] | None = None
    cover_letter: str | None = None


class RecruiterCreate(BaseModel):
    name: str = ""
    company: str = ""
    email: str = ""
    linkedin_url: str = ""
    role: str = ""
    notes: str = ""
    source: str = "manual"


class OutreachCreate(BaseModel):
    job_id: int
    recruiter_id: int | None = None
    channel: str = "email"


class ApplicationCreate(BaseModel):
    job_id: int
    tailored_resume_id: int | None = None
    mode: str = "manual"
    notes: str = ""


class ApplicationStatusUpdate(BaseModel):
    status: str
    note: str = ""


class RecruiterResponse(BaseModel):
    id: int
    name: str
    company: str
    email: str
    linkedin_url: str
    role: str
    source: str

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: int
    title: str
    company: str
    location: str
    remote: bool
    url: str
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str
    experience_min: float | None = None
    experience_max: float | None = None
    posted_at: datetime | None = None
    score: float | None = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    config: dict[str, Any] | None = None
