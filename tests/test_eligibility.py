from __future__ import annotations

import pytest

from app.services.eligibility import eligibility_for, normalize_location


@pytest.mark.parametrize(
    ("location", "remote", "description", "expected"),
    [
        # India locations → ALLOW
        ("Noida, India", False, "", "allowed"),
        ("Greater Noida, India", False, "", "allowed"),
        ("Gandhinagar, Gujarat, India", False, "", "allowed"),
        ("Bengaluru, India", False, "", "allowed"),
        ("Remote, India", True, "", "allowed"),
        ("Remote (India)", True, "", "allowed"),
        ("Anywhere in India", True, "", "allowed"),
        ("India", False, "", "allowed"),
        ("Ahmedabad, India", False, "", "allowed"),
        ("Pune, India", False, "", "allowed"),
        ("Hyderabad, India", False, "", "allowed"),
        # Worldwide/global → ALLOW
        ("Remote - Worldwide", True, "", "allowed"),
        ("Remote, Global", True, "", "allowed"),
        # APAC includes India → ALLOW
        ("Remote - APAC", True, "", "allowed"),
        ("Remote (APAC)", True, "", "allowed"),
        # India mentioned in description → ALLOW
        ("Remote", True, "Candidates in India are welcome to apply", "allowed"),
        # Foreign onsite → BLOCK
        ("New York, United States", False, "", "blocked"),
        ("London, UK", False, "", "blocked"),
        ("Toronto, Canada", False, "", "blocked"),
        ("Berlin, Germany", False, "", "blocked"),
        ("Sydney, Australia", False, "", "blocked"),
        ("Singapore", False, "", "blocked"),
        # Remote restricted to non-India → BLOCK
        ("Remote - US only", True, "", "blocked"),
        ("Remote, United States", True, "", "blocked"),
        ("US Remote", True, "", "blocked"),
        ("Remote (EMEA)", True, "", "blocked"),
        ("Remote - EMEA", True, "", "blocked"),
        ("Remote", True, "Must be based in the United States", "blocked"),
        ("Remote - Canada", True, "", "blocked"),
        ("Remote - Americas", True, "", "blocked"),
        ("San Francisco, CA", False, "", "blocked"),
        # Remote with no geography → UNCLEAR
        ("Remote", True, "", "unclear"),
        ("Work from home", True, "", "unclear"),
        ("", False, "", "unclear"),
        ("Hybrid", False, "", "unclear"),
    ],
)
def test_india_eligibility_matrix(location, remote, description, expected):
    result = eligibility_for(location, remote, description)
    assert result.status == expected, (
        f"Expected {expected} for ({location!r}, remote={remote}, desc={description!r}), "
        f"got {result.status}: {result.reason}"
    )
    assert result.india_eligible is (expected == "allowed")
    assert result.reason
    assert result.evidence or expected == "unclear"


def test_normalize_location_cleans_unicode_and_whitespace():
    assert normalize_location("  Greater\u2014Noida,\n India  ") == "Greater-Noida, India"
