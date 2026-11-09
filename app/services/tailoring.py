from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.llm import cache as llm_cache
from app.llm.client import LLMClient, get_llm
from app.llm.prompts import JD_ANALYSIS_SYSTEM, TAILOR_SYSTEM, jd_analysis_prompt, tailor_prompt
from app.llm.schemas import JDAnalysis, TailorOutput
from app.models import Job, TailoredResume, User
from app.services.ats import extract_keywords, missing_keywords, tokenize
from app.services.jd_metadata import infer_role_title
from app.services.lexicon import find_skills, norm, skill_category

logger = logging.getLogger(__name__)

GROUP_ORDER = [
    "AI/GenAI", "ML", "MLOps", "Backend", "Cloud", "DevOps", "Data",
    "Databases", "Monitoring", "Testing", "Frontend", "Architecture", "Tools", "Other",
]


def _keyword_set(text: str) -> set[str]:
    return {norm(t) for t in tokenize(text)}


def _dedupe_strings(values: list) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = norm(text)
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def filter_allowed_skills(candidate_skills: list, master_skills: list) -> list[str]:
    """Whitelist: keep only skills that exist in the master profile."""
    allowed = {norm(str(skill)): str(skill) for skill in master_skills if str(skill).strip()}
    result: list[str] = []
    seen: set[str] = set()
    for skill in candidate_skills or []:
        key = norm(str(skill))
        if key in allowed and key not in seen:
            seen.add(key)
            result.append(allowed[key])
    return result


def validate_immutable_fields(profile: dict, candidates: list[dict]) -> tuple[list[dict], list[str]]:
    """Overwrite LLM experience metadata with master facts and report mismatches."""
    originals = profile.get("experience", []) or []
    warnings: list[str] = []
    sanitized: list[dict] = []
    for candidate in candidates or []:
        match = _entry_match(candidate, originals)
        if not match:
            warnings.append(
                "Dropped LLM experience entry that did not match a real role: "
                f"{candidate.get('title') or '?'} @ {candidate.get('company') or '?'}"
            )
            continue
        copy = dict(candidate)
        for field in ("title", "company", "dates", "location"):
            original = str(match.get(field) or "")
            proposed = str(copy.get(field) or "")
            if original and proposed and norm(original) != norm(proposed):
                # Check for keyword suffix (LLM title starts with master title)
                if field == "title" and norm(proposed).startswith(norm(original)):
                    warnings.append(f"LLM added keyword suffix to title '{original}'; kept master value")
                else:
                    warnings.append(
                        f"LLM tried to change {field} for {original}; kept master value"
                    )
            copy[field] = original
        sanitized.append(copy)
    return sanitized, warnings


def apply_experience_edits(profile: dict, candidates: list[dict]) -> tuple[list[dict], list[str]]:
    """Apply bullet edits while retaining every master role and immutable facts."""
    originals = profile.get("experience", []) or []
    warnings: list[str] = []
    result: list[dict] = []
    for original in originals:
        copy = dict(original)
        match = _entry_match(original, candidates)
        if match:
            for field in ("title", "company", "dates", "location"):
                master = str(original.get(field) or "")
                proposed = str(match.get(field) or "")
                if master and proposed and norm(master) != norm(proposed):
                    warnings.append(
                        f"Edited {field} for {master} ignored; kept master value"
                    )
                copy[field] = master
            bullets = [
                str(bullet).strip()
                for bullet in (match.get("bullets") or [])
                if str(bullet).strip()
            ]
            if bullets:
                copy["bullets"] = bullets[:4]
        result.append(copy)
    for candidate in candidates or []:
        if not _entry_match(candidate, originals):
            warnings.append(
                "Dropped edited experience entry that is not in the master resume: "
                f"{candidate.get('title') or '?'} @ {candidate.get('company') or '?'}"
            )
    return result, warnings


def rank_entries(entries: list[dict], job_text: str, limit: int) -> list[dict]:
    job_tokens = _keyword_set(job_text)
    job_lower = (job_text or "").lower()
    rag_keywords = {"llm", "rag", "agent", "vector", "graph rag", "graphrag", "knowledge graph", "retrieval"}
    is_rag_jd = any(kw in job_lower for kw in rag_keywords)
    scored = []
    for entry in entries:
        blob = " ".join(
            str(entry.get(k, "")) for k in ("title", "company", "name", "tech")
        ) + " " + " ".join(entry.get("bullets", []) or [])
        tokens = _keyword_set(blob)
        overlap = len(tokens & job_tokens)
        entry_lower = blob.lower()
        if is_rag_jd and any(kw in entry_lower for kw in ("graph", "rag", "agent", "vector", "knowledge graph")):
            overlap += 100
        scored.append((overlap, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _score, entry in scored[:limit]]


_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _month_year(value: str) -> tuple[int, int]:
    match = re.search(r"([A-Za-z]{3,9})\s+(\d{4})", value)
    if match:
        month = _MONTHS.get(match.group(1).lower(), 1)
        return int(match.group(2)), month
    match = re.search(r"(\d{4})", value)
    if match:
        return int(match.group(1)), 1
    return 0, 0


def chronological_entries(entries: list[dict]) -> list[dict]:
    """Keep every role, newest first (resume order is preserved for ties)."""
    def key(entry: dict) -> tuple[int, int]:
        dates = str(entry.get("dates") or "")
        parts = re.split(r"\s+[-–—]\s+", dates, maxsplit=1)
        return _month_year(parts[0] if parts else "")

    return sorted(entries, key=key, reverse=True)


def _group_skills(skills: list[str], job_text: str, priority: list[str] | None = None) -> list[dict]:
    jd = {norm(s) for s in extract_keywords(job_text)}
    preferred = {norm(s) for s in (priority or [])}
    ranked = sorted(
        skills,
        key=lambda s: (norm(s) not in preferred, norm(s) not in jd, s),
    )
    groups: dict[str, list[str]] = {}
    for skill in ranked:
        groups.setdefault(skill_category(skill), []).append(skill)
    best_rank: dict[str, int] = {}
    for index, skill in enumerate(ranked):
        category = skill_category(skill)
        best_rank.setdefault(category, index)
    result = [
        {"category": category, "items": items}
        for category, items in groups.items()
    ]
    result.sort(key=lambda group: best_rank.get(group["category"], 10**6))
    return result[:6]


_PLACEHOLDER_COMPANIES = {"", "confidential", "unknown company", "unknown", "n/a", "not specified"}


def _has_company(job: Job) -> bool:
    company = (job.company or "").strip().lower()
    return bool(company) and company not in _PLACEHOLDER_COMPANIES


def _job_title_or_inferred(job: Job) -> str:
    title = (job.title or "").strip()
    if title and title.lower() not in {"role not specified", "untitled", "n/a"}:
        return title
    inferred = infer_role_title(job.description or "")
    return inferred or "this role"


def _fallback_summary(profile: dict, job: Job, matched: list[str]) -> str:
    years = profile.get("years_experience") or 0
    top = ", ".join(matched[:6]) or ", ".join(profile.get("skills", [])[:6])
    job_title = _job_title_or_inferred(job)
    company_phrase = f" at {job.company}" if _has_company(job) else ""
    return (
        f"With {years:g}+ years of production experience in {top}, I am targeting the "
        f"{job_title} role{company_phrase}. "
        "Focused on building reliable, well-tested systems and delivering measurable results."
    )


def _fallback_cover_letter(profile: dict, job: Job, matched: list[str]) -> str:
    name = profile.get("name") or "Candidate"
    years = profile.get("years_experience") or 0
    top = ", ".join(matched[:5]) or ", ".join(profile.get("skills", [])[:5])
    job_title = _job_title_or_inferred(job)
    company_phrase = f" at {job.company}" if _has_company(job) else ""
    return (
        f"Dear Hiring Team,\n\n"
        f"I am writing to apply for the {job_title} role{company_phrase}. "
        f"I am a {profile.get('headline') or 'software engineer'} with {years:g}+ years of "
        f"production experience, including hands-on work with {top}.\n\n"
        f"In my recent roles I have built and operated backend and AI systems end to end: "
        f"designing APIs, deploying to the cloud, automating delivery, and monitoring production "
        f"reliability. I am particularly interested in this role because it aligns closely with "
        f"the work I do best.\n\n"
        f"I would welcome the opportunity to discuss how my experience fits your requirements.\n\n"
        f"Regards,\n{name}"
    )


def _sanitize_summary(summary: str, headline: str) -> str:
    """Remove keyword stuffing and placeholder company references from summary."""
    if not summary:
        return summary
    # Remove placeholder company references (e.g. 'at Confidential', 'at Unknown Company')
    placeholder_pattern = r"\s+(?:at|@)\s+(?:Confidential|Unknown(?:\s+Company)?|N/A|Not\s+Specified|TBD)\b"
    summary = re.sub(placeholder_pattern, "", summary, flags=re.IGNORECASE).strip()
    if not headline:
        return summary
    pattern = re.escape(headline).replace(r"\|", r"\s*\|\s*")
    stripped = re.sub(r"^" + pattern + r"[.\s,]*", "", summary, flags=re.IGNORECASE).strip()
    if stripped and len(stripped) > 20:
        return stripped[0].upper() + stripped[1:] if stripped else stripped
    # Check for pipe-separated keyword lists
    if "|" in summary and len(summary.split("|")) > 3:
        items = [item.strip() for item in summary.split("|") if item.strip()]
        if items and all(len(item.split()) <= 3 for item in items):
            return ""
    return summary


def _entry_match(entry: dict, candidates: list[dict]) -> dict | None:
    company = norm(entry.get("company", ""))
    title = norm(entry.get("title", ""))
    for candidate in candidates:
        candidate_company = norm(candidate.get("company", ""))
        if company and candidate_company and (
            company == candidate_company
            or company in candidate_company
            or candidate_company in company
        ):
            return candidate
    for candidate in candidates:
        candidate_title = norm(candidate.get("title", ""))
        if title and candidate_title and title == candidate_title:
            return candidate
    return None


def _merge_experience(
    original: list[dict],
    candidates: list[dict],
    warnings: list[str] | None = None,
) -> list[dict]:
    """Apply LLM-written bullets but keep every real role and its facts unchanged."""
    result = []
    for entry in original:
        copy = dict(entry)
        match = _entry_match(entry, candidates)
        if match:
            for field in ("title", "company", "dates", "location"):
                proposed = str(match.get(field) or "")
                master = str(entry.get(field) or "")
                if master and proposed and norm(master) != norm(proposed):
                    message = f"LLM tried to change {field} for {master}; kept master value"
                    if warnings is not None:
                        warnings.append(message)
                    logger.warning(message)
            bullets = [str(b).strip() for b in (match.get("bullets") or []) if str(b).strip()]
            if bullets:
                copy["bullets"] = bullets[:4]
        result.append(copy)
    return result


def _tailor_experience(
    entries: list[dict],
    job_text: str,
    matched: list[str],
    profile_skills: list[str],
) -> list[dict]:
    """Deterministic fallback: re-rank bullets for the JD for every role. No suffix injection."""
    jd_terms = {norm(k) for k in extract_keywords(job_text or "")}
    jd_terms.update(norm(s) for s in matched)
    jd_tokens: set[str] = set()
    for term in jd_terms:
        jd_tokens.update(tokenize(term))

    result = []
    for entry in entries:
        copy = dict(entry)
        bullets = [str(b).strip() for b in (entry.get("bullets") or []) if str(b).strip()]
        scored = [
            (len(set(tokenize(bullet)) & jd_tokens), index, bullet)
            for index, bullet in enumerate(bullets)
        ]
        chosen = [
            bullet
            for _score, _index, bullet in sorted(scored, key=lambda item: (-item[0], item[1]))[:4]
        ]
        copy["bullets"] = chosen or bullets
        result.append(copy)
    return result


def _merge_projects(
    original: list[dict],
    candidates: list[dict],
    warnings: list[str] | None = None,
) -> list[dict]:
    result = []
    for entry in original:
        copy = dict(entry)
        name = norm(entry.get("name", ""))
        match = next(
            (
                candidate for candidate in candidates
                if name and norm(candidate.get("name", "")) and (
                    name == norm(candidate.get("name", ""))
                    or name in norm(candidate.get("name", ""))
                    or norm(candidate.get("name", "")) in name
                )
            ),
            None,
        )
        if match:
            proposed_name = str(match.get("name") or "")
            if proposed_name and name != norm(proposed_name) and warnings is not None:
                warnings.append(f"LLM tried to rename project {entry.get('name')}; kept master name")
            bullets = [str(b).strip() for b in (match.get("bullets") or []) if str(b).strip()]
            if bullets:
                copy["bullets"] = bullets[:3]
        result.append(copy)
    return result


def _fallback_jd_analysis(job: Job, keywords: list[str], missing: list[str]) -> JDAnalysis:
    return JDAnalysis(
        role_title=job.title or "",
        must_have_skills=_dedupe_strings(keywords)[:20],
        domain_keywords=_dedupe_strings(keywords)[:20],
        gaps=_dedupe_strings(missing),
    )


def _analysis_meaningful(analysis: JDAnalysis) -> bool:
    return bool(
        analysis.role_title.strip()
        or analysis.must_have_skills
        or analysis.nice_to_have_skills
        or analysis.tools
        or analysis.responsibilities
        or analysis.domain_keywords
    )


def _token_present(token: str, text_tokens: set[str]) -> bool:
    if token in text_tokens:
        return True
    if len(token) >= 5:
        prefix = token[:5]
        return any(
            len(candidate) >= 5 and candidate.startswith(prefix)
            for candidate in text_tokens
        )
    return False


def _term_score(
    term: str,
    text_norm: str,
    text_tokens: set[str],
    text_skills: set[str] | None = None,
) -> float:
    """Score one JD requirement against resume evidence — no loose token matching."""
    needle = norm(term)
    if needle and needle in text_norm:
        return 1.0
    # Check canonical skills first (exact match only, no partial credit)
    term_skills = find_skills(term)
    skills_in_text = text_skills if text_skills is not None else set()
    if term_skills:
        for skill in term_skills:
            if skill in skills_in_text:
                return 1.0
        # Canonical skill not in resume — no partial credit
        return 0.0
    # For non-skill terms, require ALL tokens to match exactly (no prefix matching)
    tokens = _dedupe_strings(tokenize(term))
    if not tokens:
        return 0.0
    matched = {token for token in tokens if token in text_tokens}
    return 1.0 if len(matched) == len(tokens) else 0.0


def _coverage(keywords: list, text: str) -> tuple[int, list[str], list[str]]:
    terms = _dedupe_strings(keywords)
    if not terms:
        return 0, [], []
    text_norm = norm(text)
    text_tokens = set(tokenize(text))
    text_skills = set(find_skills(text))
    scores: list[float] = []
    matched: list[str] = []
    missing: list[str] = []
    for term in terms:
        score = _term_score(term, text_norm, text_tokens, text_skills)
        scores.append(score)
        (matched if score >= 0.66 else missing).append(term)
    return round(100 * sum(scores) / len(scores)), matched, missing


def _enhance_verified_coverage(
    summary: str,
    terms: list[str],
    master_text: str,
    tailored_text: str,
    target: int,
) -> tuple[str, list[str]]:
    """Add only verified, resume-backed JD phrases when the report is below target."""
    current, _matched, _missing = _coverage(terms, tailored_text)
    if current >= target:
        return summary, []
    master_norm = norm(master_text)
    master_tokens = set(tokenize(master_text))
    master_skills = set(find_skills(master_text))
    tailored_norm = norm(tailored_text)
    tailored_tokens = set(tokenize(tailored_text))
    tailored_skills = set(find_skills(tailored_text))
    additions: list[str] = []
    for term in _dedupe_strings(terms):
        if len(term) > 80 or len(tokenize(term)) > 8:
            continue
        if _term_score(term, master_norm, master_tokens, master_skills) < 0.66:
            continue
        if _term_score(term, tailored_norm, tailored_tokens, tailored_skills) >= 0.66:
            continue
        additions.append(term)
        if len(additions) >= 8:
            break
    if not additions:
        return summary, []
    sentence = "Verified strengths relevant to this role: " + ", ".join(additions) + "."
    return f"{summary.rstrip()} {sentence}".strip(), additions


def _master_text(profile: dict) -> str:
    parts: list[str] = [
        str(profile.get("resume_text") or ""),
        str(profile.get("headline") or ""),
        str(profile.get("summary") or ""),
    ]
    parts.extend(str(skill) for skill in (profile.get("skills") or []))
    for entry in profile.get("experience") or []:
        parts.extend(str(entry.get(key) or "") for key in ("title", "company", "location", "tech"))
        parts.extend(str(bullet) for bullet in (entry.get("bullets") or []))
    for entry in profile.get("projects") or []:
        parts.extend(str(entry.get(key) or "") for key in ("name", "tech"))
        parts.extend(str(bullet) for bullet in (entry.get("bullets") or []))
    parts.extend(str(item) for item in (profile.get("education") or []))
    parts.extend(str(item) for item in (profile.get("certifications") or []))
    return "\n".join(part for part in parts if part)


def _tailored_text(
    summary: str,
    skills: list[dict],
    experience: list[dict],
    projects: list[dict],
) -> str:
    parts: list[str] = [summary]
    for group in skills:
        parts.append(str(group.get("category") or ""))
        parts.extend(str(item) for item in (group.get("items") or []))
    for entry in experience:
        parts.extend(str(entry.get(key) or "") for key in ("title", "company", "location", "tech"))
        parts.extend(str(bullet) for bullet in (entry.get("bullets") or []))
    for entry in projects:
        parts.extend(str(entry.get(key) or "") for key in ("name", "tech"))
        parts.extend(str(bullet) for bullet in (entry.get("bullets") or []))
    return "\n".join(part for part in parts if part)


def _flat_skills(groups: list[dict]) -> list[str]:
    result: list[str] = []
    for group in groups:
        result.extend(str(item) for item in (group.get("items") or []))
    return _dedupe_strings(result)


def _diff_experience(before: list[dict], after: list[dict]) -> list[dict]:
    after_map = {
        (norm(entry.get("company", "")), norm(entry.get("title", "")), norm(entry.get("dates", ""))): entry
        for entry in after
    }
    result = []
    for entry in before:
        key = (norm(entry.get("company", "")), norm(entry.get("title", "")), norm(entry.get("dates", "")))
        rewritten = after_map.get(key)
        result.append(
            {
                "title": entry.get("title") or "",
                "company": entry.get("company") or "",
                "dates": entry.get("dates") or "",
                "before": [str(item) for item in (entry.get("bullets") or [])],
                "after": [str(item) for item in ((rewritten or {}).get("bullets") or [])],
            }
        )
    return result


def _diff_projects(before: list[dict], after: list[dict]) -> list[dict]:
    after_map = {norm(entry.get("name", "")): entry for entry in after}
    result = []
    for entry in before:
        rewritten = after_map.get(norm(entry.get("name", "")))
        result.append(
            {
                "name": entry.get("name") or "",
                "before": [str(item) for item in (entry.get("bullets") or [])],
                "after": [str(item) for item in ((rewritten or {}).get("bullets") or [])],
            }
        )
    return result


def _llm_meta(llm: LLMClient, used_llm: bool, cached: dict | None = None) -> dict:
    info = llm.info()
    provider = info.get("provider") or "template"
    model = info.get("model") or "template-fallback"
    if used_llm and cached:
        provider = str(cached.get("provider") or provider)
        model = str(cached.get("model") or model)
    return {
        "provider": provider,
        "model": model,
        "fallback": not used_llm,
        "reason": "" if used_llm else (info.get("reason") or info.get("last_error") or "template fallback"),
        "chain": info.get("chain") or [],
        "cached": bool(cached),
    }


def _match_metrics(
    terms: list[str],
    master_text: str,
    tailored_text: str,
    extra_gaps: list[str] | None = None,
) -> dict:
    terms = _dedupe_strings(terms)
    before_score, _before_matched, before_missing = _coverage(terms, master_text)
    after_score, matched, missing = _coverage(terms, tailored_text)
    before_missing_set = set(before_missing)
    fixable_gaps = [term for term in missing if term not in before_missing_set]
    unverified_gaps = [term for term in missing if term in before_missing_set]
    target = int(settings.tailor_target_score or 90)
    gaps = _dedupe_strings(list(extra_gaps or []) + missing)
    return {
        "before_score": before_score,
        "after_score": after_score,
        "target_score": target,
        "target_met": after_score >= target and bool(terms),
        "requirement_count": len(terms),
        "matched": matched,
        "missing": missing,
        "fixable_gaps": fixable_gaps,
        "unverified_gaps": unverified_gaps,
        "gap_actions": (
            ([f"Add verified resume evidence for: {', '.join(fixable_gaps[:8])}"] if fixable_gaps else [])
            + ([f"Do not claim without evidence: {', '.join(unverified_gaps[:8])}"] if unverified_gaps else [])
            + (["Add explicit examples for the remaining gaps before applying."] if missing and after_score < target else [])
        ),
        "gaps": gaps,
        "keywords": terms,
    }


def refresh_match_metrics(item: TailoredResume, profile: dict) -> dict:
    """Recompute the target/coverage fields after manual resume edits."""
    report = dict(item.match_report or {})
    terms = item.keywords or report.get("keywords") or []
    extra_gaps = (report.get("jd_analysis") or {}).get("gaps") or []
    metrics = _match_metrics(
        terms,
        _master_text(profile),
        _tailored_text(item.summary, item.skills, item.experience, item.projects),
        extra_gaps,
    )
    report.update(metrics)
    return report


def _build_match_report(
    *,
    profile: dict,
    master_summary: str,
    summary: str,
    skills: list[dict],
    experience_before: list[dict],
    experience: list[dict],
    projects_before: list[dict],
    projects: list[dict],
    jd_keywords: list[str],
    analysis: JDAnalysis,
    llm: LLMClient,
    used_llm: bool,
    warnings: list[str],
    cached_llm: dict | None = None,
) -> dict:
    master_text = _master_text(profile)
    tailored_text = _tailored_text(summary, skills, experience, projects)
    terms = _dedupe_strings(jd_keywords) or _dedupe_strings(analysis.must_have_skills)
    metrics = _match_metrics(terms, master_text, tailored_text, analysis.gaps)
    estimated_pages = max(1, math.ceil(len(tailored_text) / 4200))
    return {
        **metrics,
        "jd_analysis": analysis.model_dump(),
        "diff": {
            "summary": {"before": master_summary, "after": summary},
            "experience": _diff_experience(experience_before, experience),
            "projects": _diff_projects(projects_before, projects),
            "skills": {
                "before": _dedupe_strings(profile.get("skills") or []),
                "after": _flat_skills(skills),
            },
        },
        "llm": _llm_meta(llm, used_llm, cached_llm),
        "warnings": _dedupe_strings(warnings),
        "estimated_pages": estimated_pages,
        "one_page_warning": estimated_pages > 1,
    }


def build_tailored(db: Session, user: User, job: Job, profile: dict, resume_id: int | None = None) -> TailoredResume:
    llm = get_llm()
    jd_text = job.description or ""
    keywords = extract_keywords(jd_text)
    missing = missing_keywords(jd_text, profile.get("skills", []))
    resume_hash = llm_cache.resume_version(profile)
    jd_hash = hashlib.sha256(jd_text.encode("utf-8")).hexdigest()

    master_experience = chronological_entries([dict(entry) for entry in (profile.get("experience") or [])])
    experience = [dict(entry) for entry in master_experience]
    for entry in experience:
        entry["bullets"] = (entry.get("bullets") or [])[:4]

    master_projects = rank_entries(
        [dict(entry) for entry in (profile.get("projects") or [])], jd_text, 3
    )
    projects = [dict(entry) for entry in master_projects]
    for entry in projects:
        entry["bullets"] = (entry.get("bullets") or [])[:3]

    matched = [s for s in keywords if norm(s) in {norm(x) for x in profile.get("skills", [])}]
    master_summary = str(profile.get("summary") or "")
    summary = _fallback_summary(profile, job, matched)
    cover_letter = _fallback_cover_letter(profile, job, matched)
    warnings: list[str] = []
    used_llm = False

    analysis: JDAnalysis | None = None
    cached_analysis = llm_cache.get("jd_analysis", jd_hash, resume_hash)
    if cached_analysis:
        try:
            candidate = JDAnalysis.model_validate(cached_analysis)
            if _analysis_meaningful(candidate):
                analysis = candidate
        except Exception:
            analysis = None
    if analysis is None and llm.usable:
        data = llm.complete_json(
            JD_ANALYSIS_SYSTEM,
            jd_analysis_prompt({
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "description": jd_text,
            }),
            schema=JDAnalysis,
            default=None,
        )
        if isinstance(data, dict):
            candidate = JDAnalysis.model_validate(data)
            if _analysis_meaningful(candidate):
                analysis = candidate
                llm_cache.set("jd_analysis", candidate.model_dump(), jd_hash, resume_hash)
    if analysis is None:
        analysis = _fallback_jd_analysis(job, keywords, missing)

    output: TailorOutput | None = None
    cached_llm: dict | None = None
    cached_tailor = llm_cache.get("tailor", jd_hash, resume_hash)
    if isinstance(cached_tailor, dict) and "value" in cached_tailor:
        cached_llm = {
            "provider": str(cached_tailor.get("provider") or ""),
            "model": str(cached_tailor.get("model") or ""),
        }
        cached_tailor = cached_tailor.get("value")
    if cached_tailor:
        try:
            candidate = TailorOutput.model_validate(cached_tailor)
            if candidate.meaningful():
                output = candidate
                used_llm = True
        except Exception:
            output = None
            cached_llm = None
    if output is None and llm.usable:
        data = llm.complete_json(
            TAILOR_SYSTEM,
            tailor_prompt(
                profile,
                profile.get("resume_text", ""),
                {
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "description": jd_text,
                },
                keywords,
                missing,
                analysis=analysis.model_dump(),
            ),
            schema=TailorOutput,
            default=None,
        )
        if isinstance(data, dict):
            candidate = TailorOutput.model_validate(data)
            if candidate.meaningful():
                output = candidate
                used_llm = True
                llm_cache.set(
                    "tailor",
                    {
                        "value": candidate.model_dump(),
                        "provider": llm.provider,
                        "model": llm.model,
                    },
                    jd_hash,
                    resume_hash,
                )

    skill_priority: list[str] = []
    llm_experience: list[dict] | None = None
    llm_projects: list[dict] | None = None
    if output is not None:
        if output.summary.strip():
            summary = _sanitize_summary(output.summary.strip(), profile.get("headline") or "")
        if output.cover_letter.strip():
            cover_letter = output.cover_letter.strip()
        skill_priority = filter_allowed_skills(output.skills, profile.get("skills", []))
        if output.experience:
            candidates = [entry.model_dump() for entry in output.experience]
            llm_experience, immutable_warnings = validate_immutable_fields(profile, candidates)
            warnings.extend(immutable_warnings)
        if output.projects:
            llm_projects = [entry.model_dump() for entry in output.projects]

    if llm_experience:
        experience = _merge_experience(experience, llm_experience, warnings=warnings)
    else:
        experience = _tailor_experience(
            experience, jd_text, matched, profile.get("skills", [])
        )
    if llm_projects:
        projects = _merge_projects(projects, llm_projects, warnings=warnings)

    if skill_priority:
        priority_set = {norm(skill) for skill in skill_priority}
        missing = [item for item in missing if norm(item) not in priority_set]

    skills = _group_skills(
        profile.get("skills", []),
        jd_text,
        priority=skill_priority or matched,
    )
    jd_keywords = _dedupe_strings(
        list(analysis.must_have_skills)
        + list(analysis.nice_to_have_skills)
        + list(analysis.tools)
        + list(analysis.domain_keywords)
        + keywords
    )
    summary, verified_added = _enhance_verified_coverage(
        summary,
        jd_keywords,
        _master_text(profile),
        _tailored_text(summary, skills, experience, projects),
        int(settings.tailor_target_score or 90),
    )
    report = _build_match_report(
        profile=profile,
        master_summary=master_summary,
        summary=summary,
        skills=skills,
        experience_before=master_experience,
        experience=experience,
        projects_before=master_projects,
        projects=projects,
        jd_keywords=jd_keywords,
        analysis=analysis,
        llm=llm,
        used_llm=used_llm,
        warnings=warnings,
        cached_llm=cached_llm,
    )
    report["verified_keywords_added"] = verified_added

    tailored = TailoredResume(
        job_id=job.id,
        user_id=user.id,
        resume_id=resume_id or profile.get("resume_id"),
        summary=summary,
        skills=skills,
        experience=experience,
        projects=projects,
        cover_letter=cover_letter,
        keywords=keywords,
        match_report=report,
    )
    db.add(tailored)
    db.commit()
    db.refresh(tailored)

    docx_path, pdf_path = export_tailored(tailored, profile, job)
    tailored.docx_path = str(docx_path)
    tailored.pdf_path = str(pdf_path) if pdf_path else ""
    db.commit()
    db.refresh(tailored)
    return tailored


# -- exports ------------------------------------------------------------
def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", text)[:60].strip("_") or "job"


def export_tailored(
    tailored: TailoredResume, profile: dict, job: Job | None = None
) -> tuple[Path, Path | None]:
    out_dir = Path(settings.artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = _safe(str(profile.get("name") or "Candidate"))
    role = _safe(str(job.title if job else "Role"))
    company = _safe(str(job.company if job else "Company"))
    base = f"{name}_{role}_{company}"
    docx_path = out_dir / f"{base}.docx"
    pdf_path = out_dir / f"{base}.pdf"
    _write_docx(docx_path, tailored, profile)
    try:
        _write_pdf(pdf_path, tailored, profile)
    except Exception:
        logger.exception("PDF export failed for tailored resume %s", tailored.id)
        pdf_path = None
    return docx_path, pdf_path


def _write_docx(path: Path, tailored: TailoredResume, profile: dict) -> None:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)

    doc.add_heading(profile.get("name") or "Candidate", level=0)
    headline = profile.get("headline") or ""
    if headline:
        doc.add_paragraph(headline)
    contact = " | ".join(
        x for x in [profile.get("phone"), profile.get("email"), profile.get("location")] if x
    )
    if contact:
        doc.add_paragraph(contact)
    links = profile.get("links") or {}
    if links:
        doc.add_paragraph(" | ".join(links.values()))

    doc.add_heading("Professional Summary", level=1)
    doc.add_paragraph(tailored.summary)

    doc.add_heading("Core Technical Skills", level=1)
    for group in tailored.skills:
        p = doc.add_paragraph()
        run = p.add_run(f"{group['category']}: ")
        run.bold = True
        p.add_run(", ".join(group["items"]))

    if tailored.experience:
        doc.add_heading("Work Experience", level=1)
        for entry in tailored.experience:
            p = doc.add_paragraph()
            p.add_run(entry.get("title") or "").bold = True
            meta = " | ".join(x for x in [entry.get("company"), entry.get("dates")] if x)
            if meta:
                doc.add_paragraph(meta)
            for bullet in entry.get("bullets", []):
                doc.add_paragraph(bullet, style="List Bullet")

    if tailored.projects:
        doc.add_heading("Key Projects", level=1)
        for entry in tailored.projects:
            p = doc.add_paragraph()
            p.add_run(entry.get("name") or "").bold = True
            if entry.get("tech"):
                doc.add_paragraph(entry["tech"])
            for bullet in entry.get("bullets", []):
                doc.add_paragraph(bullet, style="List Bullet")
            if entry.get("link"):
                doc.add_paragraph(entry["link"])

    education = profile.get("education") or []
    if education:
        doc.add_heading("Education", level=1)
        for line in education:
            doc.add_paragraph(line)

    certifications = profile.get("certifications") or []
    if certifications:
        doc.add_heading("Certifications", level=1)
        for line in certifications:
            doc.add_paragraph(line)

    doc.save(str(path))


_PDF_FONTS: tuple[str, str, str] | None = None


def _pdf_fonts() -> tuple[str, str, str]:
    """Return (regular, bold, italic) font names, preferring Unicode-capable Arial."""
    global _PDF_FONTS
    if _PDF_FONTS is not None:
        return _PDF_FONTS
    import os

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    base = "Helvetica"
    bold = "Helvetica-Bold"
    italic = "Helvetica-Oblique"
    fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = {
        "AppSans": ("arial.ttf", "calibri.ttf", "segoeui.ttf"),
        "AppSans-Bold": ("arialbd.ttf", "calibrib.ttf", "segoeuib.ttf"),
        "AppSans-Italic": ("ariali.ttf", "calibrii.ttf", "segoeuii.ttf"),
    }
    registered = {}
    for font_name, files in candidates.items():
        for filename in files:
            font_path = fonts_dir / filename
            if font_path.exists():
                try:
                    pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
                    registered[font_name] = True
                except Exception:
                    pass
                break
    if registered.get("AppSans"):
        base = "AppSans"
        bold = "AppSans-Bold" if registered.get("AppSans-Bold") else "AppSans"
        italic = "AppSans-Italic" if registered.get("AppSans-Italic") else "AppSans"
    _PDF_FONTS = (base, bold, italic)
    return _PDF_FONTS


def _pdf_text(value) -> str:
    text = str(value or "").replace("\ufffd", "\u00b7")
    return re.sub(r"[ \t]+", " ", text).strip()


def _write_pdf(path: Path, tailored: TailoredResume, profile: dict) -> None:
    from xml.sax.saxutils import escape

    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer

    base_font, bold_font, italic_font = _pdf_fonts()
    navy = HexColor("#17365d")
    grey = HexColor("#4b5563")
    line = HexColor("#c7d2e3")

    name_style = ParagraphStyle(
        "Name", fontName=bold_font, fontSize=16, leading=19, alignment=TA_CENTER,
        textColor=navy, spaceAfter=1,
    )
    headline_style = ParagraphStyle(
        "Headline", fontName=base_font, fontSize=9.5, leading=12, alignment=TA_CENTER,
        textColor=grey,
    )
    contact_style = ParagraphStyle(
        "Contact", fontName=base_font, fontSize=8.6, leading=11, alignment=TA_CENTER,
        textColor=grey, spaceBefore=2,
    )
    section_style = ParagraphStyle(
        "Section", fontName=bold_font, fontSize=10.2, leading=12, textColor=navy,
        spaceBefore=5, spaceAfter=1, keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "Body", fontName=base_font, fontSize=8.7, leading=11.2, textColor=HexColor("#1f2937"),
        spaceAfter=1, allowWidows=0, allowOrphans=0,
    )
    bullet_style = ParagraphStyle(
        "Bullet", parent=body_style, leftIndent=10, bulletIndent=0,
        bulletFontName=base_font, bulletFontSize=8, spaceAfter=1,
    )
    job_style = ParagraphStyle(
        "Job", fontName=bold_font, fontSize=9.4, leading=11.4, textColor=HexColor("#111827"),
        spaceBefore=3, allowWidows=0, allowOrphans=0,
    )
    meta_style = ParagraphStyle(
        "Meta", fontName=base_font, fontSize=8.4, leading=10.4, textColor=grey, spaceAfter=1,
    )
    tech_style = ParagraphStyle(
        "Tech", fontName=italic_font, fontSize=8.2, leading=10.2, textColor=grey, spaceAfter=1,
    )
    link_style = ParagraphStyle(
        "Link", fontName=base_font, fontSize=8.3, leading=10.5, textColor=HexColor("#1d4ed8"),
    )

    def section(title: str) -> list:
        return [
            Paragraph(escape(title), section_style),
            HRFlowable(width="100%", thickness=0.5, color=line, spaceBefore=0, spaceAfter=3),
        ]

    name = _pdf_text(profile.get("name") or "Candidate")
    if name.isupper():
        name = name.title()
    flow: list = [Paragraph(escape(name), name_style)]
    if profile.get("headline"):
        flow.append(Paragraph(escape(_pdf_text(profile["headline"])), headline_style))
    contact_bits = [
        _pdf_text(x) for x in [profile.get("phone"), profile.get("email"), profile.get("location")] if x
    ]
    if contact_bits:
        flow.append(Paragraph(escape("  |  ".join(contact_bits)), contact_style))
    links = profile.get("links") or {}
    if links:
        parts = []
        for _key, url in links.items():
            url = _pdf_text(url)
            if url:
                parts.append(escape(url))
        if parts:
            flow.append(Paragraph("  |  ".join(parts), contact_style))

    flow.extend(section("Professional Summary"))
    flow.append(Paragraph(escape(_pdf_text(tailored.summary)), body_style))

    flow.extend(section("Core Technical Skills"))
    for group in tailored.skills:
        flow.append(
            Paragraph(
                f"<b>{escape(group['category'])}:</b> {escape(_pdf_text(', '.join(group['items'])))}",
                body_style,
            )
        )

    def bullets(entry_bullets: list) -> list:
        return [
            Paragraph(escape(_pdf_text(b)), bullet_style, bulletText="\u2022")
            for b in entry_bullets
            if _pdf_text(b)
        ]

    if tailored.experience:
        flow.extend(section("Work Experience"))
        for entry in tailored.experience:
            title = _pdf_text(entry.get("title"))
            meta = "  |  ".join(
                _pdf_text(x) for x in [entry.get("company"), entry.get("dates")] if x
            )
            header = []
            if title:
                header.append(Paragraph(escape(title), job_style))
            if meta:
                header.append(Paragraph(escape(meta), meta_style))
            entry_bullets = bullets(entry.get("bullets") or [])
            if entry_bullets:
                header.append(entry_bullets[0])
                flow.append(KeepTogether(header))
                flow.extend(entry_bullets[1:])
            elif header:
                flow.append(KeepTogether(header))
            flow.append(Spacer(1, 2))

    if tailored.projects:
        flow.extend(section("Key Projects"))
        for entry in tailored.projects:
            header = [Paragraph(escape(_pdf_text(entry.get("name"))), job_style)]
            if entry.get("tech"):
                header.append(Paragraph(escape(_pdf_text(entry["tech"])), tech_style))
            if entry.get("link"):
                header.append(Paragraph(escape(_pdf_text(entry["link"])), link_style))
            entry_bullets = bullets((entry.get("bullets") or [])[:3])
            if entry_bullets:
                header.append(entry_bullets[0])
                flow.append(KeepTogether(header))
                flow.extend(entry_bullets[1:])
            else:
                flow.append(KeepTogether(header))
            flow.append(Spacer(1, 2))

    for title, key in (("Education", "education"), ("Certifications", "certifications")):
        items = profile.get(key) or []
        if items:
            flow.extend(section(title))
            flow.extend(bullets(items))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(base_font, 7.5)
        canvas.setFillColor(HexColor("#6b7280"))
        canvas.drawString(13 * mm, 6 * mm, name)
        canvas.drawRightString(A4[0] - 13 * mm, 6 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=13 * mm,
        rightMargin=13 * mm,
        topMargin=10 * mm,
        bottomMargin=11 * mm,
        title=f"{name} - Resume",
        author=name,
    )
    doc.build(flow, onFirstPage=footer, onLaterPages=footer)
