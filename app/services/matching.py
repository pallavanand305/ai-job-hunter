from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job, JobMatch, User
from app.services.eligibility import eligibility_for
from app.services.embeddings import similarity
from app.services.lexicon import find_skills, norm
from app.services.text_utils import parse_experience, parse_salary
from app.services.ats import tokenize

WEIGHTS = {
    "skills": 0.35,
    "experience": 0.20,
    "responsibilities": 0.20,
    "salary": 0.15,
    "location": 0.10,
}

CURRENCY_TO_INR = {"INR": 1.0, "USD": 84.0, "EUR": 91.0, "GBP": 107.0, "": 1.0}
CURRENCY_CONVERSION_NOTE = "(salary converted to INR approximately)"

# Skills that appear in almost every tech JD; they should not dominate a match.
GENERIC_SKILLS = {
    "Git", "CI/CD", "SQL", "Agile", "Linux", "REST APIs", "Microservices",
    "System Design", "Caching", "Rate Limiting", "Unit Testing", "Integration Testing",
    "TDD", "OAuth2", "JWT", "API Design", "Serverless",
}

TECH_TITLE_TOKENS = {
    "engineer", "engineering", "developer", "software", "backend", "back", "python",
    "ai", "ml", "machine", "learning", "data", "mlops", "devops", "cloud", "platform",
    "sre", "infrastructure", "architect", "genai", "llm", "scientist", "fullstack",
    "full-stack", "api", "systems", "automation",
}

NON_TECH_TITLE_TOKENS = {
    "manager", "director", "analyst", "sales", "marketing", "accountant", "nurse",
    "recruiter", "finance", "fp&a", "product", "designer", "support", "customer",
    "success", "legal", "hr", "consultant", "specialist", "owner", "coordinator",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _to_inr(amount: float | None, currency: str) -> float | None:
    if amount is None:
        return None
    return amount * CURRENCY_TO_INR.get((currency or "").upper(), 1.0)


def _skill_score(job: Job, profile_skills: list[str]) -> tuple[float, list[str], list[str]]:
    description = (job.description or "")[:8000]
    jd_skills = list(find_skills(description).keys())
    title = (job.title or "").lower()
    weights: dict[str, float] = {}
    for skill in jd_skills:
        weight = 1.0
        if skill.lower() in title or norm(skill) in norm(title):
            weight = 3.0
        elif skill.lower() in description.lower()[:600]:
            weight = 2.0
        if skill in GENERIC_SKILLS:
            weight *= 0.4
        weights[skill] = weight

    have = {norm(s) for s in profile_skills}
    matched = [s for s in jd_skills if norm(s) in have]
    missing = [s for s in jd_skills if norm(s) not in have]

    if not jd_skills:
        return 0.1, [], []

    total_weight = sum(weights.values())
    matched_weight = sum(weights[s] for s in matched)
    coverage = matched_weight / total_weight if total_weight else 0.0

    # reward breadth of overlap a little, without punishing a rich profile
    breadth = len(matched) / max(1, min(len(jd_skills), 12))
    score = _clamp(0.75 * coverage + 0.25 * breadth)
    missing.sort(key=lambda s: -weights.get(s, 1))
    return score, matched, missing[:15]


def _experience_score(job: Job, profile: dict) -> float:
    years = float(profile.get("years_experience") or 0)
    exp_min, exp_max = job.experience_min, job.experience_max
    if exp_min is None:
        exp_min, exp_max = parse_experience(job.description or "")
    if exp_min is None:
        return 0.8
    if years >= exp_min:
        if exp_max is not None and years > exp_max + 3:
            return 0.8
        return 1.0
    if exp_min <= 0:
        return 0.8
    return _clamp(years / exp_min)


def _responsibility_score(job: Job, profile: dict, skill_score: float) -> float:
    profile_text = " ".join(
        [
            profile.get("headline", "") or "",
            profile.get("summary", "") or "",
            " ".join(profile.get("skills", [])),
            (profile.get("resume_text", "") or "")[:4000],
        ]
    )
    description = (job.description or "")[:8000]
    cos = similarity(profile_text, description)
    # hashing cosine on short vs long text is low; rescale to a usable 0..1
    embedding_fit = _clamp(cos * 2.4)
    profile_tokens = set(tokenize(profile_text))
    job_tokens = set(tokenize(description))
    if job_tokens:
        overlap = len(profile_tokens & job_tokens) / max(1, len(job_tokens))
        embedding_fit = _clamp(0.75 * embedding_fit + 0.25 * min(1.0, overlap * 4))
    # Responsibilities follow demonstrated technical overlap plus language similarity.
    score = _clamp(0.5 * skill_score + 0.5 * embedding_fit)
    return max(0.1, score)


def _salary_score(job: Job, profile: dict) -> float:
    prefs = profile.get("preferences") or {}
    min_salary = float(prefs.get("min_salary") or 0)
    if not min_salary:
        return 0.8
    currency = prefs.get("currency") or job.currency or "INR"
    job_min = _to_inr(job.salary_min, job.currency)
    job_max = _to_inr(job.salary_max, job.currency)
    if job_min is None and job_max is None:
        parsed_min, parsed_max, parsed_currency = parse_salary(job.description or "")
        job_min = _to_inr(parsed_min, parsed_currency or job.currency)
        job_max = _to_inr(parsed_max, parsed_currency or job.currency)
    target = _to_inr(min_salary, currency) or min_salary
    if job_min is None and job_max is None:
        return 0.5
    high = job_max or job_min or 0
    low = job_min or job_max or 0
    if high < target:
        return _clamp(high / target)
    if low >= target:
        return 1.0
    return 0.85


# Preferred on-site cities (score 1.0 when matched by user preferences)
# Exactly: Noida, Greater Noida, Delhi, Gurgaon/Gurugram, Bangalore, Hyderabad,
#          Pune, Mumbai, Ahmedabad, Gandhinagar
# NCR: Delhi, Noida, Greater Noida, Gurgaon, Faridabad, Ghaziabad
PREFERRED_CITIES = (
    "noida", "greater noida", "delhi", "new delhi",
    "gurgaon", "gurugram",
    "bangalore", "bengaluru",
    "hyderabad", "pune", "mumbai", "bombay",
    "ahmedabad", "gandhinagar",
    # NCR extras
    "faridabad", "ghaziabad",
)

# All Indian cities/regions recognised as India (for _is_india_location)
INDIA_LOCATION_HINTS = PREFERRED_CITIES + (
    "india", "bharat",
    "chennai", "kolkata", "calcutta",
    "jaipur", "indore", "coimbatore", "kochi", "cochin",
    "chandigarh", "lucknow", "kanpur", "nagpur", "mysore", "mysuru",
    "trivandrum", "thiruvananthapuram", "surat", "vadodara", "baroda",
    "bhopal", "visakhapatnam", "vizag", "nashik", "aurangabad",
    "varanasi", "patna", "ranchi", "raipur", "dehradun",
    "guwahati", "bhubaneswar", "ncr",
)
REMOTE_LOCATION_WORDS = (
    "remote", "worldwide", "anywhere", "global", "home based", "home-based",
    "work from home", "wfh",
)


def _is_india_location(text: str) -> bool:
    return any(hint in text for hint in INDIA_LOCATION_HINTS)


def _is_remote_job(job: Job) -> bool:
    return bool(job.remote) or any(word in (job.location or "").lower() for word in REMOTE_LOCATION_WORDS)


def _outside_india_onsite(job: Job, profile: dict) -> bool:
    prefs = profile.get("preferences") or {}
    home = str(prefs.get("home_country") or "India").lower()
    if home not in {"india", "in"}:
        return False
    if _is_remote_job(job):
        return False
    location = (job.location or "").lower()
    return bool(location) and not _is_india_location(location)


LOCATION_ALIASES = {
    "gurgaon": "gurugram",
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "madras": "chennai",
    "calcutta": "kolkata",
    "baroda": "vadodara",
    "cochin": "kochi",
    "trivandrum": "thiruvananthapuram",
    "mysore": "mysuru",
    "poona": "pune",
}


def _normalize_city(text: str) -> str:
    """Normalize city names so aliases match (e.g., Gurgaon = Gurugram)."""
    text = text.lower().strip()
    for alias, canonical in LOCATION_ALIASES.items():
        text = text.replace(alias, canonical)
    return text


def _location_score(job: Job, profile: dict) -> float:
    prefs = profile.get("preferences") or {}
    locations = [str(loc).lower() for loc in prefs.get("locations", []) if loc]
    remote_ok = bool(prefs.get("remote_ok", True))
    home = str(prefs.get("home_country") or "India").lower()
    outside_remote_only = bool(prefs.get("outside_country_remote_only", True))
    job_location = _normalize_city(job.location or "")
    remote = _is_remote_job(job)
    eligibility = eligibility_for(job.location, job.remote, job.description, job.title)

    # BLOCK → 0.0 (excluded from strong/top matches)
    if home in {"india", "in"} and eligibility.status == "blocked":
        return 0.0
    # India-eligible remote → 1.0
    if remote and remote_ok and eligibility.status == "allowed":
        return 1.0
    # UNCLEAR remote → 0.4
    if remote and remote_ok and eligibility.status == "unclear":
        return 0.4
    if not job_location:
        return 0.4

    if home in {"india", "in"}:
        if _is_india_location(job_location):
            # Check if job location matches a preferred city (score 1.0)
            for loc in locations:
                loc_norm = _normalize_city(loc)
                for token in (part.strip() for part in loc_norm.replace("/", ",").split(",")):
                    if token and token in job_location:
                        return 1.0
            # Preferred city in job location even if not in user prefs list
            job_loc_norm = _normalize_city(job_location)
            if any(city in job_loc_norm for city in PREFERRED_CITIES):
                return 1.0
            # Other Indian city → 0.65
            return 0.65
        return 0.0 if outside_remote_only else 0.2

    for loc in locations:
        tokens = [tok.strip() for tok in loc.split(",") if tok.strip()]
        if loc in job_location or job_location in loc:
            return 1.0
        if tokens and all(tok in job_location for tok in tokens):
            return 1.0
    return 0.3


def _role_fit(job: Job, profile: dict) -> float:
    title = job.title or ""
    title_tokens = set(tokenize(title))
    if not title_tokens:
        return 0.4
    prefs = profile.get("preferences") or {}
    targets = [str(t) for t in prefs.get("roles", []) if t]
    if profile.get("headline"):
        targets.append(profile["headline"])
    best = 0.0
    for target in targets:
        target_tokens = set(tokenize(target))
        if not target_tokens:
            continue
        containment = len(target_tokens & title_tokens) / len(target_tokens)
        jaccard = len(target_tokens & title_tokens) / len(target_tokens | title_tokens)
        best = max(best, 0.7 * containment + 0.3 * jaccard)
    embedding_fit = similarity(title, " ".join(targets))
    fit = _clamp(0.7 * best + 0.3 * min(1.0, embedding_fit * 2.5))
    is_tech = bool(title_tokens & TECH_TITLE_TOKENS)
    is_non_tech = bool(title_tokens & NON_TECH_TITLE_TOKENS)
    if is_non_tech and not is_tech:
        fit *= 0.25
    elif is_tech and not is_non_tech:
        fit = max(fit, 0.55)
    return _clamp(fit)


def _target_role_priority(title: str, target_roles: list[str]) -> float:
    """Multiplier based on target-role order. Earlier matches get a higher boost."""
    if not target_roles:
        return 1.0
    title_tokens = set(tokenize(title))
    for index, role in enumerate(target_roles):
        role_tokens = set(tokenize(role.lower()))
        if role_tokens & title_tokens:
            n = max(len(target_roles) - 1, 1)
            return 1.0 + 0.15 * (1.0 - index / n)
    return 1.0


def score_job(job: Job, profile: dict) -> dict:
    skill_score, matched, missing = _skill_score(job, profile.get("skills", []))
    experience_score = _experience_score(job, profile)
    responsibility_score = _responsibility_score(job, profile, skill_score)
    salary_score = _salary_score(job, profile)
    location_score = _location_score(job, profile)
    role_fit = _role_fit(job, profile)
    eligibility = eligibility_for(job.location, job.remote, job.description, job.title)

    prefs = profile.get("preferences") or {}
    target_roles = [str(t).strip() for t in prefs.get("roles", []) if t]

    weighted = (
        WEIGHTS["skills"] * skill_score
        + WEIGHTS["experience"] * experience_score
        + WEIGHTS["responsibilities"] * responsibility_score
        + WEIGHTS["salary"] * salary_score
        + WEIGHTS["location"] * location_score
    )
    # Feasibility gate: an onsite role in another country should not outrank a remote fit.
    total = 100 * weighted * (0.5 + 0.5 * role_fit) * (0.65 + 0.35 * location_score)
    total *= _target_role_priority(job.title or "", target_roles)
    outside_onsite = _outside_india_onsite(job, profile)
    if outside_onsite:
        total *= 0.25
    if eligibility.status == "blocked":
        total *= 0.2

    excluded = {c.strip().lower() for c in prefs.get("exclude_companies", []) if c}
    if excluded and (job.company or "").strip().lower() in excluded:
        total = 0.0

    strengths = ", ".join(matched[:6]) or "general fit"
    gaps = ", ".join(missing[:4])
    rationale = f"Strong overlap on {strengths}."
    if gaps:
        rationale += f" Gaps to address: {gaps}."
    if job.remote or _is_remote_job(job):
        rationale += " Remote-friendly role."
    if outside_onsite:
        rationale += " Onsite outside India; you prefer remote for international roles."
    if eligibility.status == "blocked":
        rationale += f" {eligibility.reason}"
    elif eligibility.status == "unclear":
        rationale += " India eligibility unclear; verify before applying."
    if salary_score < 0.5:
        currency = (job.currency or "").upper()
        note = f" {CURRENCY_CONVERSION_NOTE}" if currency and currency != "INR" else ""
        rationale += f" Salary may be below your target.{note}"

    return {
        "score": round(total, 1),
        "skill_score": round(skill_score * 100, 1),
        "experience_score": round(experience_score * 100, 1),
        "responsibility_score": round(responsibility_score * 100, 1),
        "salary_score": round(salary_score * 100, 1),
        "location_score": round(location_score * 100, 1),
        "role_fit": round(role_fit * 100, 1),
        "matched_skills": matched,
        "missing_skills": missing,
        "rationale": rationale,
    }


def run_matching(db: Session, user: User, profile: dict, job_ids: list[int] | None = None) -> dict:
    stmt = select(Job)
    if job_ids:
        stmt = stmt.where(Job.id.in_(job_ids))
    jobs = db.scalars(stmt).all()
    existing = {
        m.job_id: m
        for m in db.scalars(select(JobMatch).where(JobMatch.user_id == user.id)).all()
    }
    scored = 0
    for job in jobs:
        result = score_job(job, profile)
        match = existing.get(job.id)
        if match is None:
            match = JobMatch(job_id=job.id, user_id=user.id)
            db.add(match)
        match.score = result["score"]
        match.skill_score = result["skill_score"]
        match.experience_score = result["experience_score"]
        match.responsibility_score = result["responsibility_score"]
        match.salary_score = result["salary_score"]
        match.location_score = result["location_score"]
        match.matched_skills = result["matched_skills"]
        match.missing_skills = result["missing_skills"]
        match.rationale = result["rationale"]
        scored += 1
    db.commit()
    return {"scored": scored}
