"""India-eligibility engine for job postings.

The company's home country does NOT decide eligibility.
The hiring geography stated for the role decides it.

Classification:
  ALLOW   — on-site/hybrid in India, or remote open to India/worldwide/APAC
  BLOCK   — restricted to a country/region that excludes India
  UNCLEAR — remote with no stated geography, or timezone-only preference
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# ── India location hints ─────────────────────────────────────────────────
INDIA_HINTS = (
    "india", "bharat", "hindustan",
    "noida", "greater noida", "delhi", "new delhi", "gurgaon", "gurugram",
    "faridabad", "ghaziabad", "ncr",
    "mumbai", "bombay", "pune", "bangalore", "bengaluru",
    "hyderabad", "chennai", "kolkata", "calcutta",
    "ahmedabad", "gandhinagar", "jaipur", "indore",
    "coimbatore", "kochi", "cochin", "chandigarh",
    "lucknow", "kanpur", "nagpur", "mysore", "mysuru", "trivandrum",
    "thiruvananthapuram", "surat", "vadodara", "baroda", "bhopal",
    "visakhapatnam", "vizag", "kochi", "kozhikode", "thrissur",
    "nashik", "aurangabad", "varanasi", "patna", "ranchi",
    "raipur", "dehradun", "shimla", "jodhpur", "ajmer",
    "guwahati", "siliguri", "jamshedpur", "bhubaneswar", "bhubaneshwar",
)

# ── Worldwide / global terms ──────────────────────────────────────────────
WORLDWIDE_TERMS = (
    "worldwide", "world-wide", "anywhere", "any where", "global", "globally",
    "any country", "any location", "any location", "all countries",
    "work from anywhere", "open to candidates globally",
    "open to all", "open globally", "around the world",
    "across the world", "from anywhere in the world",
    "distributed team", "distributed globally",
    "remote - worldwide", "remote, worldwide",
    "remote, anywhere", "remote - anywhere",
    "remote, any country", "remote - any country",
)

# ── India-inclusive regions (APAC, Asia) ─────────────────────────────────
INDIA_INCLUSIVE_REGIONS = (
    "apac", "asia pacific", "asia-pacific", "asia",
    "south asia", "south asian", "indian subcontinent",
    "indo-pacific",
)

# ── India-exclusive regions ───────────────────────────────────────────────
INDIA_EXCLUSIVE_REGIONS = (
    "emea", "emeia",
    "europe", "european union", "eu only", "eu-only",
    "north america", "north american",
    "latin america", "latam", "latam only",
    "americas", "the americas",
    "middle east", "mena",
    "north america only", "europe only",
)

# ── Timezone-only terms ───────────────────────────────────────────────────
TIMEZONE_TERMS = (
    "timezone", "time zone", "time-zone",
    "overlap", "hours overlap",
    "cet", "pst", "est", "gmt", "utc", "aedt", "kst", "jst",
    "business hours", "working hours",
    "eu timezone", "us timezone", "apac timezone",
    "emea timezone", "cet hours", "pst hours", "est hours",
    "gmt hours", "timezone overlap",
)

# ── Comprehensive country list ────────────────────────────────────────────
# Maps country names, aliases, and major foreign cities → ISO 2-letter code
# India is "IN" — any other code means "not India"
_COUNTRY_TERMS: dict[str, str] = {}

def _add(*aliases: str, code: str) -> None:
    for a in aliases:
        _COUNTRY_TERMS[a.lower()] = code

# North America
_add("united states", "usa", "u.s.", "u.s.a.", "us", "america", "united states of america", code="US")
_add("new york", "san francisco", "los angeles", "seattle", "austin", "boston",
     "chicago", "atlanta", "denver", "houston", "dallas", "washington dc",
     "miami", "san diego", "portland", "phoenix", "philadelphia",
     "san jose", "salt lake city", "minneapolis", "detroit", "nashville",
     "orlando", "tampa", "raleigh", "charlotte", "las vegas",
     "irvine", "baltimore", "pittsburgh", "cincinnati", "cleveland",
     "kansas city", "st louis", "new orleans", "richmond", "sacramento",
     code="US")
_add("california", "texas", "florida", "washington", "oregon", "new jersey",
     "massachusetts", "virginia", "illinois", "georgia", "arizona",
     "colorado", "north carolina", "michigan", "pennsylvania", "ohio",
     "minnesota", "indiana", "tennessee", "maryland", "wisconsin",
     "missouri", "arizona", "connecticut", "nevada", "utah",
     "new hampshire", "new mexico", "kansas", "iowa", "nebraska",
     "oklahoma", "louisiana", "kentucky", "alabama", "south carolina",
     "idaho", "montana", "wyoming", "colorado", "vermont", "maine",
     "rhode island", "delaware", "hawaii", "alaska", "west virginia",
     "mississippi", "arkansas", "north dakota", "south dakota",
     code="US")
# US state abbreviations (2-letter, word-boundary matched)
_add("ca", "tx", "ny", "fl", "wa", "or", "nj", "ma", "va", "il", "ga", "az",
     "co", "nc", "mi", "pa", "oh", "mn", "in", "tn", "md", "wi", "mo",
     "ct", "nv", "ut", "nh", "nm", "ks", "ia", "ne", "ok", "la", "ky",
     "al", "sc", "id", "mt", "wy", "vt", "me", "ri", "de", "hi", "ak",
     "wv", "ms", "ar", "nd", "sd", "dc",
     code="US")

_add("canada", "toronto", "vancouver", "montreal", "calgary", "ottawa",
     "edmonton", "winnipeg", "quebec city", "hamilton",
     "ontario", "quebec", "british columbia", "alberta", "manitoba",
     "saskatchewan", "nova scotia", "new brunswick",
     code="CA")
_add("mexico", "mexico city", "guadalajara", "monterrey", code="MX")

# South America
_add("brazil", "são paulo", "sao paulo", "rio de janeiro", "rio",
     "brasilia", "belo horizonte", code="BR")
_add("argentina", "buenos aires", "cordoba", code="AR")
_add("chile", "santiago", code="CL")
_add("colombia", "bogota", "bogotá", "medellin", code="CO")
_add("peru", "lima", code="PE")
_add("uruguay", "montevideo", code="UY")
_add("ecuador", "quito", "guayaquil", code="EC")
_add("venezuela", "caracas", code="VE")

# Europe
_add("united kingdom", "uk", "u.k.", "great britain", "britain",
     "england", "scotland", "wales", "northern ireland",
     "london", "manchester", "edinburgh", "glasgow", "birmingham",
     "liverpool", "bristol", "leeds", "sheffield", "newcastle",
     "cardiff", "belfast",
     code="GB")
_add("ireland", "dublin", "cork", "galway", code="IE")
_add("germany", "berlin", "munich", "münchen", "frankfurt", "hamburg",
     "cologne", "köln", "stuttgart", "düsseldorf", "dusseldorf",
     "dresden", "leipzig", "dortmund", "essen", "bremen", "hannover",
     "nuremberg", "nürnberg", "duisburg", "bochum", "wuppertal",
     "bielefeld", "bonn", "münster", "karlsruhe", "mannheim",
     "augsburg", "wiesbaden", "gelsenkirchen", "mönchengladbach",
     "braunschweig", "kiel", "chemnitz", "aachen", "halle",
     "magdeburg", "freiburg", "krefeld", "lübeck", "oberhausen",
     "erfurt", "mainz", "rostock", "kassel", "hagen", "hamm",
     "saarbrücken", "mülheim", "potsdam", "ludwigshafen", "oldenburg",
     "leverkusen", "osnabrück", "solingen", "heidelberg", "herne",
     "neuss", "darmstadt", "paderborn", "regensburg", "ingolstadt",
     "würzburg", "wolfsburg", "heilbronn", "ulm", "pforzheim",
     "schweinfurt", "pulsnitz", "karben",
     code="DE")
_add("france", "paris", "lyon", "marseille", "toulouse", "nice", "bordeaux",
     "lille", "nantes",
     code="FR")
_add("spain", "madrid", "barcelona", "valencia", "seville", "sevilla",
     "bilbao", "malaga", "málaga",
     code="ES")
_add("portugal", "lisbon", "lisboa", "porto", code="PT")
_add("netherlands", "amsterdam", "rotterdam", "the hague", "hague",
     "utrecht", "eindhoven",
     code="NL")
_add("belgium", "brussels", "brussels", "antwerp", "ghent", code="BE")
_add("switzerland", "zurich", "zürich", "geneva", "basel", "bern", "lausanne",
     code="CH")
_add("sweden", "stockholm", "gothenburg", "malmo", "malmö", "uppsala", code="SE")
_add("norway", "oslo", "bergen", "trondheim", code="NO")
_add("denmark", "copenhagen", "københavn", "aarhus", "odense", code="DK")
_add("finland", "helsinki", "espoo", "tampere", "turku", code="FI")
_add("poland", "warsaw", "warszawa", "krakow", "kraków", "lodz", "wroclaw",
     code="PL")
_add("italy", "rome", "roma", "milan", "milano", "naples", "napoli",
     "turin", "torino", "florence", "firenze", "bologna",
     code="IT")
_add("austria", "vienna", "wien", "graz", "linz", "salzburg", code="AT")
_add("czech republic", "czechia", "prague", "praha", "brno", code="CZ")
_add("greece", "athens", "thessaloniki", "patras", code="GR")
_add("hungary", "budapest", "debrecen", code="HU")
_add("romania", "bucharest", "cluj", "constanta", code="RO")
_add("bulgaria", "sofia", "plovdiv", code="BG")
_add("croatia", "zagreb", "split", code="HR")
_add("serbia", "belgrade", "beograd", "novi sad", code="RS")
_add("slovakia", "bratislava", "kosice", "košice", code="SK")
_add("slovenia", "ljubljana", "maribor", code="SI")
_add("lithuania", "vilnius", "kaunas", code="LT")
_add("latvia", "riga", code="LV")
_add("estonia", "tallinn", "tartu", code="EE")
_add("iceland", "reykjavik", "reykjavík", code="IS")
_add("luxembourg", "luxembourg city", code="LU")
_add("malta", "valletta", code="MT")
_add("cyprus", "nicosia", "limassol", code="CY")

# Middle East
_add("uae", "united arab emirates", "dubai", "abu dhabi", "sharjah",
     code="AE")
_add("saudi arabia", "riyadh", "jeddah", "mecca", "medina", code="SA")
_add("qatar", "doha", code="QA")
_add("kuwait", "kuwait city", code="KW")
_add("bahrain", "manama", code="BH")
_add("oman", "muscat", code="OM")
_add("jordan", "amman", code="JO")
_add("lebanon", "beirut", code="LB")
_add("israel", "tel aviv", "jerusalem", "haifa", code="IL")
_add("turkey", "türkiye", "istanbul", "ankara", "izmir", "bursa", code="TR")
_add("egypt", "cairo", "alexandria", "giza", code="EG")

# Africa
_add("south africa", "johannesburg", "cape town", "durban", "pretoria", code="ZA")
_add("nigeria", "lagos", "abuja", "kano", code="NG")
_add("kenya", "nairobi", "mombasa", code="KE")
_add("ghana", "accra", "kumasi", code="GH")
_add("ethiopia", "addis ababa", code="ET")
_add("morocco", "casablanca", "rabat", "marrakech", code="MA")
_add("tunisia", "tunis", code="TN")

# Asia (non-India)
_add("japan", "tokyo", "osaka", "kyoto", "nagoya", "sapporo", "fukuoka", code="JP")
_add("south korea", "korea", "seoul", "busan", "incheon", "daegu", code="KR")
_add("china", "beijing", "shanghai", "shenzhen", "guangzhou", "chengdu",
     "hangzhou", "nanjing", "wuhan", "xian", "xi'an",
     code="CN")
_add("hong kong", "hong kong", code="HK")
_add("taiwan", "taipei", "kaohsiung", "taichung", code="TW")
_add("singapore", "singapore city", code="SG")
_add("malaysia", "kuala lumpur", "penang", "george town", "johor bahru", code="MY")
_add("indonesia", "jakarta", "surabaya", "bandung", "medan", code="ID")
_add("thailand", "bangkok", "chiang mai", "phuket", code="TH")
_add("vietnam", "hanoi", "ho chi minh", "saigon", "da nang", code="VN")
_add("philippines", "manila", "cebu", "davao", "makati", code="PH")
_add("pakistan", "karachi", "lahore", "islamabad", code="PK")
_add("bangladesh", "dhaka", "chittagong", code="BD")
_add("sri lanka", "colombo", "kandy", code="LK")
_add("nepal", "kathmandu", "pokhara", code="NP")
_add("myanmar", "yangon", "mandalay", code="MM")
_add("cambodia", "phnom penh", "siem reap", code="KH")

# Oceania
_add("australia", "sydney", "melbourne", "brisbane", "perth", "adelaide",
     "canberra", "hobart", "darwin", "gold coast",
     code="AU")
_add("new zealand", "auckland", "wellington", "christchurch", "hamilton", code="NZ")

# Russia & Central Asia
_add("russia", "moscow", "saint petersburg", "st petersburg", "novosibirsk",
     "yekaterinburg", "kazan",
     code="RU")
_add("kazakhstan", "almaty", "astana", "nur-sultan", code="KZ")
_add("uzbekistan", "tashkent", code="UZ")

# Build combined regex for efficient single-pass detection
_TERMS_LONGEST_FIRST = sorted(_COUNTRY_TERMS, key=len, reverse=True)
_COUNTRY_RE = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(t) for t in _TERMS_LONGEST_FIRST) + r")(?![a-z])",
    re.IGNORECASE,
)


# ── India-exclusion patterns (checked before positive location signals) ────
# These explicitly say India is NOT welcome — must override APAC/worldwide/India-in-desc.
INDIA_EXCLUSION_PATTERNS = (
    r"\bexclud(?:ing|ed)\s+india\b",
    r"\bnot\s+open\s+to\s+(?:candidates|applicants)?\s*(?:based\s+)?in\s+india\b",
    r"\bno\s+(?:candidates|applicants|hiring)\s+(?:from|in|based\s+in)\s+india\b",
    r"\bindia\s+(?:not\s+)?(?:excluded|not\s+eligible|not\s+supported|not\s+available)\b",
    r"\bexcept\s+india\b",
    r"\bother\s+than\s+india\b",
)

# ── Flexibility qualifiers (soften a foreign office mention) ─────────────
# When location is generic remote and desc only mentions a foreign city with
# one of these phrases, treat as UNCLEAR rather than BLOCKED.
FLEXIBILITY_PHRASES = (
    r"\bflexible\s+(?:about|on|regarding|with)\s+(?:where|location|remote|work\s+location)\b",
    r"\bopen\s+to\s+(?:fully\s+)?remote\b",
    r"\bremote(?:-first|\s+first|\s+friendly)\b",
    r"\bwork\s+from\s+anywhere\b",
    r"\blocation\s+(?:is\s+)?flexible\b",
    r"\bno\s+relocation\s+required\b",
)


def _detect_india_exclusion(text: str) -> str:
    """Return evidence if text explicitly excludes India, else empty string."""
    for pattern in INDIA_EXCLUSION_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return ""


def _has_flexibility_qualifier(text: str) -> bool:
    """Return True if text contains a phrase that softens a foreign office mention."""
    for pattern in FLEXIBILITY_PHRASES:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# ── Restriction patterns ─────────────────────────────────────────────────
RESTRICTION_PATTERNS = (
    r"\b(?:must|need to|required to|have to)\s+(?:be\s+)?(?:based|located|residing|resident|living)\s+in\s+([a-z .,'\-]{2,60})",
    r"\b(?:only\s+)?(?:candidates|applicants|residents|individuals)\s+(?:based\s+)?in\s+([a-z .,'\-]{2,60})",
    r"\bopen\s+(?:only\s+)?to\s+(?:candidates|applicants|residents)\s+(?:in|from)\s+([a-z .,'\-]{2,60})",
    r"\bremote\s*(?:only\s+)?(?:within|in)\s+(?:the\s+)?([a-z .,'\-]{2,60})",
    r"\bauthori[sz]ed to work in\s+(?:the\s+)?([a-z .,'\-]{2,60})",
    r"\beligible to work in\s+(?:the\s+)?([a-z .,'\-]{2,60})",
    r"\bright to work in\s+(?:the\s+)?([a-z .,'\-]{2,60})",
    r"\bwork permit (?:required|needed) (?:in|for)\s+(?:the\s+)?([a-z .,'\-]{2,60})",
    r"\b(?:citizens|citizenship|pr|permanent resid)(?:\s+of)?\s+([a-z .,'\-]{2,60})",
    r"\b(?:only|restricted to)\s+([a-z .,'\-]{2,60})\s+(?:only|residents?)\b",
)


@dataclass(frozen=True)
class Eligibility:
    status: str  # "allowed", "blocked", "unclear"
    india_eligible: bool
    reason: str
    evidence: str

    def as_dict(self) -> dict:
        return asdict(self)


def normalize_location(value: str | None) -> str:
    text = str(value or "").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[\u00a0\t\r\n]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains(text: str, hints: tuple[str, ...]) -> str:
    for hint in hints:
        if re.search(r"(?<![a-z])" + re.escape(hint) + r"(?![a-z])", text):
            return hint
    return ""


def _detect_india(text: str) -> str:
    """Return the India hint found, or empty string."""
    return _contains(text, INDIA_HINTS)


def _detect_worldwide(text: str) -> str:
    """Return the worldwide term found, or empty string."""
    return _contains(text, WORLDWIDE_TERMS)


def _detect_countries(text: str) -> set[str]:
    """Detect all country ISO codes mentioned in text (single regex pass)."""
    if not text:
        return set()
    found: set[str] = set()
    for match in _COUNTRY_RE.finditer(text):
        code = _COUNTRY_TERMS.get(match.group(1).lower())
        if code:
            found.add(code)
    return found


def _is_timezone_preference(text: str, region: str) -> bool:
    """Check if a region mention is actually a timezone preference."""
    idx = text.find(region)
    if idx < 0:
        return False
    after = text[idx + len(region):][:40]
    return bool(re.search(
        r"\b(timezone|time zone|time-zone|hours|overlap|tz|cet|pst|est|gmt|utc|business hours|working hours)\b",
        after,
    ))


def _detect_timezone_only(text: str) -> bool:
    """Check if text only contains timezone-related terms (no country/region)."""
    return bool(_contains(text, TIMEZONE_TERMS))


def _detect_restrictions(text: str) -> tuple[str, str]:
    """Return (restriction_target, evidence) if a restriction pattern matches.
    Skips matches where the captured target is purely a timezone term.
    """
    _tz_only = re.compile(
        r"^\s*(cet|pst|est|gmt|utc|aedt|kst|jst|bst|ist|aest|timezone|time zone|\w+ timezone|\w+ time zone)\s*$",
        re.IGNORECASE,
    )
    for pattern in RESTRICTION_PATTERNS:
        match = re.search(pattern, text)
        if match:
            target = match.group(1).strip().rstrip(".,;")
            # Skip if the captured target is purely a timezone abbreviation/term
            if _tz_only.match(target):
                continue
            return target, match.group(0)
    return "", ""


def _is_remote(text: str, remote: bool) -> bool:
    return bool(remote) or bool(re.search(
        r"\b(remote|work from home|wfh|fully remote|remote-first)\b", text
    ))


def eligibility_for(
    location: str | None,
    remote: bool = False,
    description: str | None = None,
    title: str | None = None,
) -> Eligibility:
    """Classify a job's India eligibility.

    ALLOW: onsite/hybrid in India, or remote open to India/worldwide/APAC
    BLOCK: restricted to a country/region that excludes India
    UNCLEAR: remote with no stated geography, or timezone-only preference
    """
    loc = normalize_location(location).lower()
    desc = normalize_location(description).lower()[:4000]
    title_text = normalize_location(title).lower() if title else ""
    combined = f"{title_text} {loc} {desc}".strip()
    is_remote = _is_remote(loc, remote)
    is_hybrid = bool(re.search(r"\bhybrid\b", loc))

    # 0. India explicitly excluded in description → BLOCK immediately
    #    (must run before positive signals so "Excluding India" overrides APAC/worldwide/India-in-desc)
    india_exclusion_ev = _detect_india_exclusion(desc)
    if india_exclusion_ev:
        return Eligibility("blocked", False,
                           "Description explicitly excludes India.",
                           india_exclusion_ev)

    # 1. India in location → ALLOW (onsite, hybrid, or remote in India)
    india_in_loc = _detect_india(loc)
    if india_in_loc:
        mode = "Remote" if is_remote else ("Hybrid" if is_hybrid else "On-site")
        return Eligibility("allowed", True, f"{mode} role in India.", india_in_loc)

    # 2. Worldwide/global in location field only → ALLOW (strong signal)
    #    But first check if description restricts to non-India.
    worldwide_in_loc = _detect_worldwide(loc)
    if worldwide_in_loc:
        # Description restriction overrides worldwide location
        restriction_target, restriction_ev = _detect_restrictions(combined)
        if restriction_target and not _detect_india(restriction_target) and not _detect_worldwide(restriction_target):
            return Eligibility("blocked", False,
                               f"Role requires {restriction_target} despite worldwide location.",
                               restriction_ev)
        return Eligibility("allowed", True,
                           "Remote role is open worldwide.", worldwide_in_loc)

    # 3. India mentioned in description → ALLOW
    india_in_desc = _detect_india(desc)
    if india_in_desc:
        return Eligibility("allowed", True,
                           "India is mentioned in the job description.",
                           india_in_desc)

    # 4. India-inclusive region (APAC, Asia, South Asia) in location → ALLOW
    #    But description restriction overrides the region.
    incl_region = _contains(loc, INDIA_INCLUSIVE_REGIONS)
    if incl_region:
        if not _is_timezone_preference(combined, incl_region):
            # Check if description restricts to specific non-India countries
            restriction_target, restriction_ev = _detect_restrictions(combined)
            if restriction_target and not _detect_india(restriction_target) and not _detect_worldwide(restriction_target):
                return Eligibility("blocked", False,
                                   f"Region {incl_region} but description restricts to {restriction_target}.",
                                   restriction_ev)
            return Eligibility("allowed", True,
                               f"Role covers {incl_region} which includes India.",
                               incl_region)

    # 5. Restriction patterns → BLOCK (if target is not India)
    restriction_target, restriction_ev = _detect_restrictions(combined)
    if restriction_target:
        if _detect_india(restriction_target):
            return Eligibility("allowed", True,
                               "Restriction includes India.",
                               restriction_ev)
        # Check if the restriction target is a worldwide term
        if _detect_worldwide(restriction_target):
            return Eligibility("allowed", True,
                               "Restriction is worldwide.",
                               restriction_ev)
        return Eligibility("blocked", False,
                           f"Role requires {restriction_target}.",
                           restriction_ev)

    # 6. Non-India country in location → BLOCK
    loc_countries = _detect_countries(loc)
    if loc_countries and "IN" not in loc_countries:
        # Pick first detected country for the message
        country_code = next(iter(loc_countries))
        if is_remote:
            return Eligibility("blocked", False,
                               f"Remote role is tied to a non-India location.",
                               loc)
        return Eligibility("blocked", False,
                           "On-site/hybrid role is outside India.",
                           loc)

    # 7. Non-India exclusive region in location → BLOCK
    for region in INDIA_EXCLUSIVE_REGIONS:
        if region in loc and not _is_timezone_preference(combined, region):
            return Eligibility("blocked", False,
                               f"Region '{region}' excludes India.",
                               region)

    # 7b. Worldwide signal in description (before step 8 country scan)
    #     Catches "distributed across N countries", "from anywhere in the world", etc.
    if is_remote:
        worldwide_in_desc_early = _detect_worldwide(desc[:1000])
        if worldwide_in_desc_early:
            return Eligibility("allowed", True,
                               "Remote role with worldwide signal in description.",
                               worldwide_in_desc_early)

    # 8. Non-India country in description header (first 500 chars) → BLOCK
    # Strip HTML tags before checking to avoid false positives from HTML boilerplate
    desc_clean = re.sub(r"<[^>]+>", " ", desc)
    desc_header = desc_clean[:500]
    desc_countries = _detect_countries(desc_header)
    if desc_countries and "IN" not in desc_countries:
        # If location is generic remote and description has a flexibility qualifier,
        # the foreign city is just the company HQ — treat as UNCLEAR.
        if is_remote and not loc_countries and _has_flexibility_qualifier(desc):
            return Eligibility("unclear", False,
                               "Remote role; foreign office mentioned but flexibility stated.",
                               desc_header[:80])
        return Eligibility("blocked", False,
                           "Job description names a non-India country without worldwide/India mention.",
                           desc_header[:80])

    # 9. Non-India exclusive region in description → BLOCK
    for region in INDIA_EXCLUSIVE_REGIONS:
        if region in desc[:500] and not _is_timezone_preference(combined, region):
            return Eligibility("blocked", False,
                               f"Region '{region}' in description excludes India.",
                               region)

    # 10. Remote with no detected geography → check description for worldwide, then UNCLEAR
    if is_remote:
        if _detect_timezone_only(combined) and not loc_countries:
            tz_ev = _contains(combined, TIMEZONE_TERMS)
            return Eligibility("unclear", False,
                               "Remote role with only timezone preference stated.",
                               tz_ev or loc or "remote")
        if not loc or loc in {"remote", "work from home", "wfh", "fully remote",
                              "remote/wfh", "(remote)", "remote first"}:
            # Only when location is purely generic: check description for worldwide signal
            worldwide_in_desc = _detect_worldwide(desc[:1000])
            if worldwide_in_desc:
                return Eligibility("allowed", True,
                                   "Remote role with worldwide signal in description.",
                                   worldwide_in_desc)
            india_in_desc2 = _detect_india(desc)
            if india_in_desc2:
                return Eligibility("allowed", True,
                                   "India mentioned in description for generic remote role.",
                                   india_in_desc2)
            return Eligibility("unclear", False,
                               "Remote role with no stated geography.",
                               loc or "remote")

    # 11. No location or unrecognizable → UNCLEAR
    if not loc:
        return Eligibility("unclear", False, "Location is not specified.", "")

    if is_hybrid and not is_remote:
        return Eligibility("unclear", False,
                           "Hybrid role location is not specific enough.",
                           loc)

    return Eligibility("unclear", False,
                       "Location eligibility could not be determined.",
                       loc)
