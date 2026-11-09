from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache

from app.services.lexicon import STOPWORDS, find_skills, norm

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,30}")


@lru_cache(maxsize=2048)
def _tokenize_cached(text: str) -> tuple[str, ...]:
    tokens = []
    for raw in TOKEN_RE.findall(text):
        low = raw.lower().strip(".-")
        if len(low) < 2 or low in STOPWORDS:
            continue
        tokens.append(low)
    return tuple(tokens)


def tokenize(text: str) -> list[str]:
    return list(_tokenize_cached(text or ""))


def extract_keywords(text: str, limit: int = 60) -> list[str]:
    """Return canonical skills first, then frequent domain tokens."""
    skills = find_skills(text)
    keywords: list[str] = list(skills.keys())

    counts = Counter(tokenize(text))
    seen_norm = {norm(k) for k in keywords}
    for token, count in counts.most_common(200):
        if len(keywords) >= limit:
            break
        if count < 2 and not re.search(r"[+#.]", token):
            continue
        key = token.upper() if token in {"aws", "gcp", "sql", "nlp", "api", "ci", "cd"} else token
        if norm(key) in seen_norm:
            continue
        seen_norm.add(norm(key))
        keywords.append(key)
    return keywords[:limit]


def missing_keywords(jd_text: str, profile_skills: list[str]) -> list[str]:
    jd = find_skills(jd_text)
    have = {norm(s) for s in profile_skills}
    return [skill for skill in jd if norm(skill) not in have]


def matched_keywords(jd_text: str, profile_skills: list[str]) -> list[str]:
    jd = find_skills(jd_text)
    have = {norm(s) for s in profile_skills}
    return [skill for skill in jd if norm(skill) in have]


def ats_score(jd_text: str, profile_skills: list[str]) -> dict:
    jd_skills = list(find_skills(jd_text).keys())
    matched = matched_keywords(jd_text, profile_skills)
    missing = missing_keywords(jd_text, profile_skills)
    total = len(jd_skills) or 1
    score = round(100 * len(matched) / total, 1)
    return {
        "score": score,
        "jd_skills": jd_skills,
        "matched": matched,
        "missing": missing,
    }
