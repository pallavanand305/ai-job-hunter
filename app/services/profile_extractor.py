from __future__ import annotations

import re
from datetime import date

from app.services.lexicon import find_skills, skill_category

SECTION_ALIASES = {
    "summary": ["professional summary", "summary", "profile", "objective", "about"],
    "skills": ["core technical skills", "technical skills", "skills", "core skills", "technologies"],
    "experience": ["work experience", "professional experience", "experience", "employment history"],
    "projects": ["key projects", "projects", "personal projects", "selected projects"],
    "education": ["education", "academic background", "qualifications"],
    "certifications": ["certifications", "certificates", "licenses & certifications"],
}

MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1
    )
}
DATE_RANGE_RE = re.compile(
    r"((?:[A-Za-z]{3,9}\.?\s+)?(?:19|20)\d{2})\s*(?:-|\u2013|\u2014|to)\s*"
    r"((?:[A-Za-z]{3,9}\.?\s+)?(?:19|20)\d{2}|[Pp]resent|[Cc]urrent)",
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{3,5}\)?[\s\-]?)\d{3}[\s\-]?\d{3,4}")
URL_RE = re.compile(
    r"(https?://[^\s|,]+|(?:www\.)?(?:[A-Za-z0-9\-]+\.)+"
    r"(?:com|io|dev|ai|net|org|me|app|in|co|tech|xyz|site|page|link|blog)(?:/[^\s|,]*)?)"
)
BULLET_RE = re.compile(
    r"^[\u2022\u25cf\u25aa\u2023\u2043\u25e6\-\*\u00b7\uf0b7\ufffd]\s*"
)
DEGREE_RE = re.compile(r"^(B\.?Tech|M\.?Tech|B\.?E|M\.?E|Bachelor|Master|MBA|BSc|MSc|PhD)\b", re.IGNORECASE)


def _heading_key(line: str) -> str | None:
    low = line.strip().lower().rstrip(":")
    for key, aliases in SECTION_ALIASES.items():
        if low in aliases:
            return key
    return None


def _parse_month(token: str) -> tuple[int, int] | None:
    token = token.strip().replace(".", "")
    m = re.match(r"([A-Za-z]{3,9})\s+(\d{4})$", token)
    if m:
        mon = MONTHS.get(m.group(1).lower())
        if mon:
            return int(m.group(2)), mon
        return int(m.group(2)), 1
    m = re.match(r"(\d{4})$", token)
    if m:
        return int(m.group(1)), 1
    return None


def _span(entry: re.Match[str]) -> tuple[tuple[int, int], tuple[int, int]] | None:
    start = _parse_month(entry.group(1))
    if not start:
        return None
    end_token = entry.group(2)
    if end_token.lower() in {"present", "current"}:
        today = date.today()
        end = (today.year, today.month)
    else:
        end = _parse_month(end_token)
    if not end:
        return None
    return start, end


def _months_between(start: tuple[int, int], end: tuple[int, int]) -> int:
    return max(0, (end[0] - start[0]) * 12 + (end[1] - start[1]))


def total_experience_years(text: str) -> float:
    """Union of all date ranges, so overlapping roles are not double counted."""
    intervals = []
    for entry in DATE_RANGE_RE.finditer(text):
        span = _span(entry)
        if span:
            start, end = span
            intervals.append(((start[0] * 12 + start[1]), (end[0] * 12 + end[1])))
    if not intervals:
        return 0.0
    intervals.sort()
    merged: list[list[int]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    months = sum(e - s for s, e in merged)
    return round(months / 12.0, 1)


def split_sections(text: str) -> dict[str, str]:
    lines = [ln.rstrip() for ln in text.splitlines()]
    sections: dict[str, list[str]] = {}
    current = "header"
    for line in lines:
        key = _heading_key(line)
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _clean_line(line: str) -> str:
    return BULLET_RE.sub("", line.strip()).strip()


def _company_display(raw: str) -> str:
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    if not parts:
        return ""
    company = parts[0]
    location = ""
    for part in parts[1:]:
        if not re.fullmatch(r"(full[- ]?time|part[- ]?time|contract|intern(ship)?|temporary)", part, re.I):
            location = part
    return f"{company} \u00b7 {location}" if location else company


def parse_experience(experience_text: str) -> list[dict]:
    """Parse title/date/company blocks and merge wrapped bullet lines."""
    items: list[tuple[str, bool]] = []
    pending_bullet = False
    for raw in experience_text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if BULLET_RE.fullmatch(stripped):
            pending_bullet = True
            continue
        clean = _clean_line(raw)
        if clean:
            items.append((clean, pending_bullet or BULLET_RE.match(stripped) is not None))
            pending_bullet = False

    date_indices = [i for i, (text, _) in enumerate(items) if DATE_RANGE_RE.search(text)]
    if not date_indices:
        return []

    entries: list[dict] = []
    for pos, date_idx in enumerate(date_indices):
        start = date_idx - 1 if date_idx > 0 and not items[date_idx - 1][1] else date_idx
        end = date_indices[pos + 1] - 2 if pos + 1 < len(date_indices) else len(items) - 1
        end = max(end, date_idx)

        title = items[start][0] if start < date_idx else ""
        date_line = items[date_idx][0]
        match = DATE_RANGE_RE.search(date_line)
        dates = match.group(0).replace("\u2013", "-").replace("\u2014", "-") if match else date_line

        company_raw = ""
        bullet_start = date_idx + 1
        remainder = (date_line[: match.start()] + " " + date_line[match.end():]).strip(" |") if match else ""
        if remainder:
            company_raw = remainder
        elif date_idx + 1 <= end and not items[date_idx + 1][1]:
            company_raw = items[date_idx + 1][0]
            bullet_start = date_idx + 2

        bullets: list[str] = []
        for idx in range(bullet_start, end + 1):
            text, is_bullet = items[idx]
            if DATE_RANGE_RE.search(text):
                continue
            if is_bullet or not bullets:
                bullets.append(text)
            else:
                bullets[-1] = f"{bullets[-1].rstrip()} {text}".strip()

        entries.append(
            {
                "title": title.strip(),
                "company": _company_display(company_raw),
                "dates": dates.strip(),
                "bullets": bullets,
            }
        )
    return entries


def _clean_sep(text: str) -> str:
    return re.sub(r"\s*[\ufffd\u2022\u00b7]+\s*", " \u00b7 ", text).strip(" \u00b7")


def parse_projects(projects_text: str) -> list[dict]:
    """Project blocks start with 'Name | Tech'; wrapped lines extend the last bullet."""
    entries: list[dict] = []
    current: dict | None = None
    last_was_bullet = False
    pending_bullet = False
    for raw in projects_text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if BULLET_RE.fullmatch(stripped):
            pending_bullet = True
            continue
        clean = _clean_line(raw)
        if not clean:
            continue
        is_bullet = pending_bullet or BULLET_RE.match(stripped) is not None
        pending_bullet = False
        is_link = clean.lower().startswith(("http", "www.", "github.com")) or "github.com/" in clean.lower()

        if is_link:
            if current is None:
                current = {"name": clean, "tech": "", "bullets": [], "link": ""}
                entries.append(current)
            current["link"] = clean
            last_was_bullet = False
            continue

        if not is_bullet and "|" in clean:
            name_part, tech_part = clean.split("|", 1)
            current = {
                "name": _clean_sep(name_part),
                "tech": _clean_sep(tech_part),
                "bullets": [],
                "link": "",
            }
            entries.append(current)
            last_was_bullet = False
            continue

        if current is None:
            current = {"name": clean, "tech": "", "bullets": [], "link": ""}
            entries.append(current)
            last_was_bullet = False
            continue

        if is_bullet:
            current["bullets"].append(clean)
            last_was_bullet = True
        elif current["bullets"] and last_was_bullet:
            current["bullets"][-1] = f"{current['bullets'][-1].rstrip()} {clean}".strip()
        elif not current["bullets"]:
            current["tech"] = f"{current['tech']} {clean}".strip() if current["tech"] else clean
        else:
            current["bullets"].append(clean)
            last_was_bullet = True
    return entries


def parse_contact(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    header = " ".join(lines[:4])
    header_without_email = EMAIL_RE.sub(" ", header)
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(header)
    urls = URL_RE.findall(header_without_email)
    links: dict[str, str] = {}
    for url in urls:
        if not url.startswith("http"):
            url = "https://" + url
        low = url.lower()
        if "linkedin" in low:
            links["linkedin"] = url
        elif "github" in low:
            links["github"] = url
        elif "gmail.com" not in low and "@" not in low:
            links.setdefault("portfolio", url)

    location = ""
    for line in lines[:5]:
        for part in re.split(r"[|\u00b7\u2022]", line):
            part = part.strip()
            if not part or "@" in part or "http" in part.lower() or re.search(r"\d{4,}", part):
                continue
            if "," in part and len(part) < 60:
                location = part
                break
        if location:
            break

    name = lines[0] if lines and len(lines[0]) < 70 else ""
    if name.isupper():
        name = name.title()
    headline = ""
    if len(lines) > 1 and ("|" in lines[1] or any(k in lines[1].lower() for k in ("engineer", "developer", "analyst"))):
        headline = lines[1]

    return {
        "name": name,
        "email": email.group(0) if email else "",
        "phone": phone.group(0).strip() if phone else "",
        "location": location,
        "headline": headline,
        "links": links,
    }


def parse_education(education_text: str) -> list[str]:
    entries: list[str] = []
    for raw in education_text.splitlines():
        clean = _clean_line(raw)
        if not clean:
            continue
        is_date = bool(DATE_RANGE_RE.search(clean))
        if is_date and entries:
            entries[-1] = f"{entries[-1]} \u00b7 {clean}"
        elif entries and DATE_RANGE_RE.search(entries[-1]) and not DEGREE_RE.match(clean):
            entries[-1] = f"{entries[-1]} \u00b7 {clean}"
        else:
            entries.append(clean)
    return entries


def parse_resume(text: str) -> dict:
    sections = split_sections(text)
    contact = parse_contact(text)
    skills = find_skills(text)
    experience = parse_experience(sections.get("experience", ""))
    projects = parse_projects(sections.get("projects", ""))
    certifications = [
        _clean_line(ln)
        for ln in sections.get("certifications", "").splitlines()
        if _clean_line(ln)
    ]
    education = parse_education(sections.get("education", ""))
    return {
        **contact,
        "summary": sections.get("summary", "").strip(),
        "skills": list(skills.keys()),
        "skill_categories": {s: skill_category(s) for s in skills},
        "experience": experience,
        "projects": projects,
        "education": education,
        "certifications": certifications,
        "years_experience": total_experience_years(sections.get("experience", "") or text),
        "sections": sections,
    }
