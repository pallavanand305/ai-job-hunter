"""E-3: Hard eligibility set — 31 examples with traps, mixed signals, exclusions."""
from __future__ import annotations

import pytest

from app.services.eligibility import eligibility_for

HARD_SET = [
    # --- Traps (substring / ambiguity) ---
    ("Backend Engineer",  "Remote - Indiana, USA",          True,  "",                                                                          "blocked"),
    ("Data Engineer",     "Indianapolis, IN",               False, "",                                                                          "blocked"),
    ("ML Engineer",       "Remote - Georgia",               True,  "",                                                                          "blocked"),
    ("SRE",               "Remote - Jordan",                True,  "",                                                                          "blocked"),
    ("Platform Engineer", "Remote - Kenya",                 True,  "",                                                                          "blocked"),
    ("Backend Engineer",  "Remote, Indonesia",              True,  "",                                                                          "blocked"),
    ("DevOps Engineer",   "Remote - Chennai",               True,  "",                                                                          "allowed"),

    # --- Location says one thing, description says another ---
    ("AI Engineer", "Remote - US",     True,  "We also hire in India and select APAC countries via contractor agreements.",  "allowed"),
    ("AI Engineer", "Remote",          True,  "Candidates from anywhere in the world are welcome. We are distributed across 40 countries.", "allowed"),
    ("AI Engineer", "Remote",          True,  "Must be authorized to work in the United States.",                            "blocked"),
    ("AI Engineer", "Remote",          True,  "We only hire in the US, UK and Canada.",                                      "blocked"),
    ("AI Engineer", "Remote",          True,  "Relocation to Germany is required within 6 months.",                          "blocked"),
    ("AI Engineer", "Remote - Europe", True,  "Applications from India are welcome too.",                                    "allowed"),
    ("AI Engineer", "Remote",          True,  "Open to candidates in Europe, the Middle East and India.",                    "allowed"),
    ("AI Engineer", "Remote",          True,  "Employer of record available in 80+ countries including India.",              "allowed"),

    # --- Explicit exclusions ---
    ("Python Developer", "Remote (Asia)",       True,  "",                                                                  "allowed"),
    ("Python Developer", "Remote (Asia)",       True,  "Excluding India and China due to entity restrictions.",             "blocked"),
    ("Python Developer", "Remote - Worldwide",  True,  "Not open to candidates based in India.",                            "blocked"),
    ("Python Developer", "Remote - APAC",       True,  "Candidates based in Australia or New Zealand only.",                "blocked"),

    # --- Regional labels ---
    ("Cloud Engineer", "Remote - North America",                              True,  "",                                                "blocked"),
    ("Cloud Engineer", "EMEA (Remote)",                                       True,  "",                                                "blocked"),
    ("Cloud Engineer", "Remote - Worldwide (excluding sanctioned countries)", True,  "",                                                "allowed"),
    ("Cloud Engineer", "Remote - Global",                                     True,  "Must be able to work US business hours.",          "allowed"),

    # --- On-site / hybrid ---
    ("Backend Engineer", "Hybrid - London",                    False, "",                                                              "blocked"),
    ("Backend Engineer", "San Francisco, CA or Remote",        True,  "",                                                              "blocked"),
    ("Backend Engineer", "Bangalore, India (Hybrid)",          False, "Reports to our US headquarters team.",                          "allowed"),
    ("Backend Engineer", "Pune (On-site)",                     False, "US client; shifts 6pm to 3am IST.",                             "allowed"),
    ("Backend Engineer", "Mumbai or Remote (India)",           True,  "",                                                              "allowed"),

    # --- Genuinely unclear ---
    ("ML Engineer", "Remote", True,  "Overlap with PST working hours required.",                                "unclear"),
    ("ML Engineer", "Remote", True,  "Our office is in Berlin, but we are flexible about where you work.",     "unclear"),
    ("ML Engineer", "Remote", True,  "No visa sponsorship available.",                                         "unclear"),
]


@pytest.mark.parametrize("title,location,remote,desc,expected", HARD_SET)
def test_hard_set(title, location, remote, desc, expected):
    result = eligibility_for(location, remote, desc, title)
    assert result.status == expected, (
        f"\nTitle:    {title!r}\n"
        f"Location: {location!r}\n"
        f"Remote:   {remote}\n"
        f"Desc:     {desc!r}\n"
        f"Expected: {expected!r}  Got: {result.status!r}\n"
        f"Reason:   {result.reason}\n"
        f"Evidence: {result.evidence!r}"
    )
