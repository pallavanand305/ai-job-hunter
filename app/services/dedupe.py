from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "lever-source", "source", "ref", "trk", "trackingid", "cid",
}


def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return url.strip().lower()
    host = parsed.netloc.lower().replace("www.", "")
    path = re.sub(r"/+$", "", parsed.path)
    return f"{parsed.scheme or 'https'}://{host}{path}".lower()


def _norm_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def job_hash(title: str, company: str, location: str, url: str = "") -> str:
    company_key = _norm_text(company)
    title_key = _norm_text(title)
    location_key = _norm_text(location)
    if company_key and title_key:
        raw = f"{title_key}|{company_key}|{location_key}"
    else:
        raw = normalize_url(url)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_duplicate(title: str, company: str, location: str, url: str, seen: set[str]) -> bool:
    key = job_hash(title, company, location, url)
    if key in seen:
        return True
    seen.add(key)
    return False
