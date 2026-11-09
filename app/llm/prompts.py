"""Prompt templates. Guardrails: never fabricate candidate facts."""

TRUTH_RULES = """You are an assistant helping a candidate apply for jobs.
HARD RULES:
- NEVER invent skills, employers, job titles, dates, degrees, certifications, metrics or achievements.
- Only use facts present in the CANDIDATE PROFILE or RESUME.
- If a requirement is not supported by the candidate's facts, do not claim it; omit it or phrase it as a gap.
- Do not exaggerate seniority or years of experience.
- Output must be truthful, concise and professional.
"""

JD_ANALYSIS_SYSTEM = (
    TRUTH_RULES
    + """
You analyse a job description. Return strict JSON only with keys:
role_title (string), seniority (string), must_have_skills (array of strings),
nice_to_have_skills (array of strings), tools (array of strings),
responsibilities (array of strings), domain_keywords (array of strings),
gaps (array of strings). Extract only what the JD states. Do not invent requirements.
"""
)

TAILOR_SYSTEM = (
    TRUTH_RULES
    + """
You tailor resumes to a job description. Return strict JSON only with keys:
summary (string), skills (array of strings), experience (array of objects with
title, company, dates, bullets[array]), projects (array of objects with name,
tech, bullets[array]), cover_letter (string), gaps (array of strings).
IMMUTABLE FACTS: company, job title, dates, location, education, certifications and
contact details must be copied exactly from the resume. Never rewrite or infer them.
For experience: include EVERY role from the resume, newest first. Use the master
title, company and dates exactly. Reorder bullets by JD relevance and rephrase them
using the JD's wording and responsibilities, but only with facts already in the
resume. For skills: use only skills present in the candidate profile, ordered by
relevance to this JD; never add a skill the candidate does not have. Rephrase projects
only lightly (10-20% wording changes) without changing names or technologies. Keep
bullets achievement-oriented and truthful. Max 6 skill groups. Do not add education,
certifications, contact details or new sections to the JSON.
"""
)


def jd_analysis_prompt(job: dict) -> str:
    return f"""JOB:
Title: {job.get('title')}
Company: {job.get('company')}
Location: {job.get('location')}
Description:
{(job.get('description') or '')[:8000]}

Return the JD analysis JSON now.
"""

OUTREACH_SYSTEM = (
    TRUTH_RULES
    + """
You write short recruiter outreach. Return strict JSON only with keys:
subject (string), body (string), linkedin_message (string).
Keep the email under 150 words, warm, specific to the role and truthful.
"""
)

CLASSIFY_SYSTEM = """Classify a recruitment email. Return strict JSON only with keys:
category (one of: interview, assessment, rejection, offer, recruiter_response, other),
company (string or null), role (string or null), interview_at (ISO-8601 string or null),
summary (string), suggested_reply (string). Be conservative; never invent dates.
"""


def tailor_prompt(
    profile: dict,
    resume_text: str,
    job: dict,
    keywords: list[str],
    missing: list[str],
    analysis: dict | None = None,
) -> str:
    return f"""CANDIDATE PROFILE:
{profile}

RESUME (source of truth):
{resume_text[:9000]}

JOB:
Title: {job.get('title')}
Company: {job.get('company')}
Location: {job.get('location')}
Description:
{(job.get('description') or '')[:7000]}

JD ANALYSIS (structured):
{analysis or 'n/a'}

JD KEYWORDS: {keywords}
KEYWORDS MISSING FROM PROFILE (do not fake them): {missing}

Produce the tailored resume JSON. Keep every real employer, title, date and location
from the resume; do not drop roles or change their metadata. Rewrite each
work-experience bullet so it matches this JD's language, required skills and
responsibilities, without inventing any fact or metric. Reorder bullets by relevance.
Use only real candidate skills, ordered by JD relevance. Rephrase project bullets only
lightly (10-20%). Also write a tailored cover letter. Never add skills the candidate
does not have.
"""


def outreach_prompt(profile: dict, job: dict, tailored: dict | None, recruiter: dict | None) -> str:
    return f"""CANDIDATE:
{profile}

JOB:
Title: {job.get('title')}
Company: {job.get('company')}
Location: {job.get('location')}
Description excerpt: {(job.get('description') or '')[:2500]}

TAILORED HIGHLIGHTS:
{tailored or 'n/a'}

RECRUITER:
{recruiter or 'unknown (write to the hiring team)'}

Write the outreach JSON.
"""


def classify_prompt(sender: str, subject: str, snippet: str) -> str:
    return f"FROM: {sender}\nSUBJECT: {subject}\nBODY:\n{snippet[:4000]}"
