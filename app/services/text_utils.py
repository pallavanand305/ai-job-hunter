from __future__ import annotations

import html
import re


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|li|div|h\d)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


CURRENCY_SYMBOLS = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP"}


def parse_salary(text: str) -> tuple[float | None, float | None, str]:
    """Best-effort annual salary parser. Returns (min, max, currency)."""
    if not text:
        return None, None, ""
    raw = clean_text(text)
    currency = ""
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in raw:
            currency = code
            break
    low = raw.lower()
    if not currency:
        if re.search(r"\b(inr|rs\.?|rupees|lpa|lakh|lac)\b", low):
            currency = "INR"
        elif re.search(r"\b(usd|us\$|dollars?)\b", low):
            currency = "USD"
        elif re.search(r"\b(eur|euros?)\b", low):
            currency = "EUR"
        elif re.search(r"\b(gbp|pounds?)\b", low):
            currency = "GBP"

    lpa_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakh|lac)", low)
    if lpa_match:
        return float(lpa_match.group(1)) * 100_000, float(lpa_match.group(2)) * 100_000, "INR"
    single_lpa = re.search(r"(\d+(?:\.\d+)?)\s*(?:lpa|lakh|lac)", low)
    if single_lpa:
        value = float(single_lpa.group(1)) * 100_000
        return value, value, "INR"

    numbers = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", raw)]
    numbers = [n for n in numbers if n >= 1000]
    if not numbers:
        return None, None, currency
    if currency == "INR":
        numbers = [n * 100_000 if n < 100 else n for n in numbers]
    if len(numbers) >= 2:
        return min(numbers[:2]), max(numbers[:2]), currency
    return numbers[0], numbers[0], currency


def parse_experience(text: str) -> tuple[float | None, float | None]:
    if not text:
        return None, None
    low = clean_text(text).lower()
    rng = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", low)
    if rng:
        return float(rng.group(1)), float(rng.group(2))
    plus = re.search(r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)", low)
    if plus:
        return float(plus.group(1)), None
    single = re.search(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)", low)
    if single:
        value = float(single.group(1))
        return value, value
    return None, None


def is_remote(location: str, description: str = "") -> bool:
    haystack = f"{location} {description[:500]}".lower()
    return any(k in haystack for k in ("remote", "work from home", "anywhere", "distributed"))


def parse_datetime(value) -> "datetime | None":
    from datetime import datetime, timezone

    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:  # milliseconds
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        pass
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%d", "%d %b %Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=None)
        except Exception:
            continue
    return None
