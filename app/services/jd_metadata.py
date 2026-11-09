from __future__ import annotations

import re

TITLE_LINE_RE = re.compile(
    r"^(?:job\s+title|position|role|title)\s*[:\-]\s*(.+)$", re.IGNORECASE
)
HIRING_RE = re.compile(
    r"\b(?:hiring|seeking|looking for|recruiting)\s+(?:an?|the)?\s*"
    r"([A-Za-z0-9][A-Za-z0-9 /+&.,'\-]{2,80}?)(?:\s+(?:at|to|for|who|with)\b|[.!]|$)",
    re.IGNORECASE,
)
COMPANY_RE = re.compile(
    r"^(?:company|organization|organisation|employer)\s*[:\-]\s*(.+)$", re.IGNORECASE
)
AT_COMPANY_RE = re.compile(
    r"\bat\s+([A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,4})"
    r"(?=[.,;\n]|\s+(?:to|for|who|with)\b|$)"
)

HEADING_WORDS = {
    "job description", "about us", "about the role", "about the job",
    "responsibilities", "requirements", "qualifications", "who we are",
    "what you will do", "what we offer", "overview", "description",
}


def _clean(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip(" \t-:|,.;")
    text = re.sub(r"^(?:an?|the)\s+", "", text, flags=re.IGNORECASE)
    return text[:120]


def _usable_title(value: str) -> bool:
    text = _clean(value)
    if not (2 <= len(text) <= 90):
        return False
    low = text.lower()
    if low in HEADING_WORDS or low.startswith(("http", "www.", "location", "salary")):
        return False
    if "@" in text or re.search(r"\b\d{5,}\b", text):
        return False
    return bool(re.search(r"[A-Za-z]", text))


def _lines(description: str) -> list[str]:
    return [line.strip(" \t-*•") for line in (description or "").splitlines() if line.strip()]


def infer_role_title(description: str) -> str:
    lines = _lines(description)
    for line in lines[:30]:
        match = TITLE_LINE_RE.match(line)
        if match and _usable_title(match.group(1)):
            return _clean(match.group(1))
    for line in lines[:12]:
        match = HIRING_RE.search(line)
        if match and _usable_title(match.group(1)):
            return _clean(match.group(1))
    for line in lines[:5]:
        if _usable_title(line) and len(line) <= 80:
            return _clean(line)
    return ""


def infer_company(description: str) -> str:
    lines = _lines(description)
    for line in lines[:30]:
        match = COMPANY_RE.match(line)
        if match:
            company = _clean(match.group(1))
            if company:
                return company
    for line in lines[:8]:
        match = AT_COMPANY_RE.search(line)
        if match:
            company = _clean(match.group(1))
            if company.lower() not in {"scale", "least", "the", "a", "an"}:
                return company
    return ""
