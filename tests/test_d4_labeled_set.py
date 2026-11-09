"""D-4: Labeled test set of 80+ examples for India eligibility classifier.

Each entry: (title, location, description_snippet, expected_label)
expected_label: "allowed" | "blocked" | "unclear"

Rules:
  ALLOW  = on-site/hybrid in India; remote open to India/worldwide/global/anywhere/APAC/Asia;
            India listed among several countries; Indian company WFH.
  BLOCK  = remote restricted to a country/region excluding India; must reside/authorized/right
            to work in a non-India country; on-site/hybrid outside India.
  UNCLEAR = remote with no stated geography; only a timezone preference.
"""
from __future__ import annotations

import pytest
from app.services.eligibility import eligibility_for

# fmt: off
LABELED_EXAMPLES = [
    # ── ALLOW: India on-site / hybrid ────────────────────────────────────
    ("SWE", "Noida, India",          "",                                                    "allowed"),
    ("SWE", "Greater Noida, India",  "",                                                    "allowed"),
    ("SWE", "Delhi, India",          "",                                                    "allowed"),
    ("SWE", "Gurgaon, India",        "",                                                    "allowed"),
    ("SWE", "Gurugram, India",       "",                                                    "allowed"),
    ("SWE", "Bangalore, India",      "",                                                    "allowed"),
    ("SWE", "Bengaluru, India",      "",                                                    "allowed"),
    ("SWE", "Hyderabad, India",      "",                                                    "allowed"),
    ("SWE", "Pune, India",           "",                                                    "allowed"),
    ("SWE", "Mumbai, India",         "",                                                    "allowed"),
    ("SWE", "Ahmedabad, India",      "",                                                    "allowed"),
    ("SWE", "Gandhinagar, India",    "",                                                    "allowed"),
    ("SWE", "Work from home, Bangalore", "",                                                "allowed"),
    ("SWE", "Noida hybrid",         "",                                                    "allowed"),
    ("SWE", "Gurugram on-site",     "",                                                    "allowed"),

    # ── ALLOW: Remote open to India / worldwide ───────────────────────────
    ("SWE", "Remote, India",         "",                                                    "allowed"),
    ("SWE", "Remote - Worldwide",    "",                                                    "allowed"),
    ("SWE", "Remote, worldwide",     "",                                                    "allowed"),
    ("SWE", "Remote - anywhere",     "",                                                    "allowed"),
    ("SWE", "Remote, anywhere in the world", "",                                            "allowed"),
    ("SWE", "Remote (APAC)",         "",                                                    "allowed"),
    ("SWE", "Remote - APAC",         "",                                                    "allowed"),
    ("SWE", "Remote, Asia",          "",                                                    "allowed"),
    ("SWE", "Remote/WFH",            "Open to candidates across Asia including India.",     "allowed"),
    ("SWE", "Remote",                "Remote, global team, any country.",                   "allowed"),
    ("SWE", "Remote - US or India",  "",                                                    "allowed"),
    ("SWE", "Remote - US, Canada, India", "",                                               "allowed"),
    ("SWE", "Remote",                "Candidates in India are welcome to apply.",           "allowed"),
    ("SWE", "Remote",                "We are open to candidates globally.",                 "allowed"),
    ("SWE", "Remote",                "Work from anywhere in the world.",                    "allowed"),
    # Foreign companies explicitly open to India
    ("SWE", "(Remote)",              "Singapore company open to candidates across Asia including India.", "allowed"),
    ("SWE", "Remote",                "Japanese company, remote, global team, any country.", "allowed"),
    ("SWE", "Remote",                "German startup, fully remote, worldwide.",            "allowed"),
    ("SWE", "Remote",                "Australian company, remote, APAC timezones.",        "allowed"),
    ("SWE", "Remote - Global",       "",                                                    "allowed"),
    ("SWE", "Remote, Global",        "",                                                    "allowed"),
    ("SWE", "Fully Remote",          "Open to all countries.",                              "allowed"),
    ("SWE", "Remote",                "Distributed team, any location.",                    "allowed"),

    # ── BLOCK: Remote restricted to a single non-India country ───────────
    ("SWE", "Remote - US",           "",                                                    "blocked"),
    ("SWE", "Remote, United States", "",                                                    "blocked"),
    ("SWE", "Remote (UK only)",      "",                                                    "blocked"),
    ("SWE", "Remote, UK",            "",                                                    "blocked"),
    ("SWE", "Remote, U.K.",          "",                                                    "blocked"),
    ("SWE", "Remote, Germany",       "",                                                    "blocked"),
    ("SWE", "Remote - Canada",       "",                                                    "blocked"),
    ("SWE", "Remote, Australia only","",                                                    "blocked"),
    ("SWE", "Remote - Netherlands",  "",                                                    "blocked"),
    ("SWE", "Remote - UAE",          "",                                                    "blocked"),
    ("SWE", "Remote - Brazil",       "",                                                    "blocked"),
    ("SWE", "Remote - Singapore (citizens/PR only)", "",                                    "blocked"),
    ("SWE", "Remote, USA",           "",                                                    "blocked"),
    ("SWE", "Remote, U.S.",          "",                                                    "blocked"),
    ("SWE", "US Remote",             "",                                                    "blocked"),
    ("SWE", "Remote - US only",      "",                                                    "blocked"),
    ("SWE", "Remote, California only","",                                                   "blocked"),

    # ── BLOCK: Remote restricted to a region excluding India ─────────────
    ("SWE", "Remote - EMEA",         "",                                                    "blocked"),
    ("SWE", "Remote - Americas",     "",                                                    "blocked"),
    ("SWE", "Remote - LATAM",        "",                                                    "blocked"),
    ("SWE", "Remote - EU only",      "",                                                    "blocked"),
    ("SWE", "Remote (EMEA)",         "",                                                    "blocked"),
    ("SWE", "Remote - North America","",                                                    "blocked"),

    # ── BLOCK: Must reside / authorized to work ───────────────────────────
    ("SWE", "Remote",                "Must be authorized to work in the US.",               "blocked"),
    ("SWE", "Remote",                "Must be authorized to work in the United States.",    "blocked"),
    ("SWE", "Remote",                "Candidates must be based in the United Kingdom.",     "blocked"),
    ("SWE", "Remote",                "You must have the right to work in Germany.",         "blocked"),
    ("SWE", "Remote",                "Eligible to work in Canada required.",                "blocked"),

    # ── BLOCK: On-site / hybrid outside India ────────────────────────────
    ("SWE", "New York, United States","",                                                   "blocked"),
    ("SWE", "London, United Kingdom", "",                                                   "blocked"),
    ("SWE", "Toronto, Canada",        "",                                                   "blocked"),
    ("SWE", "Berlin, Germany",        "",                                                   "blocked"),
    ("SWE", "Sydney, Australia",      "",                                                   "blocked"),
    ("SWE", "Tokyo hybrid",           "",                                                   "blocked"),
    ("SWE", "Singapore",              "",                                                   "blocked"),
    ("SWE", "Dubai on-site",          "",                                                   "blocked"),
    ("SWE", "Amsterdam, Netherlands", "",                                                   "blocked"),
    ("SWE", "São Paulo, Brazil",      "",                                                   "blocked"),
    ("SWE", "Tokyo, Japan",           "",                                                   "blocked"),

    # ── UNCLEAR: Remote with no geography ────────────────────────────────
    ("SWE", "Remote",                "",                                                    "unclear"),
    ("SWE", "Work from home",        "",                                                    "unclear"),
    ("SWE", "(Remote)",              "",                                                    "unclear"),
    ("SWE", "Remote/WFH",            "",                                                    "unclear"),

    # ── UNCLEAR: Timezone-only preference ────────────────────────────────
    ("SWE", "Remote",                "Remote - EU timezone overlap preferred.",             "unclear"),
    ("SWE", "Remote",                "Remote - CET hours.",                                 "unclear"),
    ("SWE", "Remote",                "PST timezone preferred.",                             "unclear"),
]
# fmt: on

assert len(LABELED_EXAMPLES) >= 80, f"Need >= 80 examples, got {len(LABELED_EXAMPLES)}"


def _run_all() -> tuple[int, int, dict, list]:
    """Returns (correct, total, confusion, misclassified)."""
    labels = ("allowed", "blocked", "unclear")
    confusion: dict[str, dict[str, int]] = {
        exp: {pred: 0 for pred in labels} for exp in labels
    }
    misclassified = []
    correct = 0
    for title, location, description, expected in LABELED_EXAMPLES:
        result = eligibility_for(location, False, description, title)
        # remote flag: infer from location/description
        is_remote = any(
            w in (location + " " + description).lower()
            for w in ("remote", "wfh", "work from home", "anywhere", "worldwide", "global")
        )
        result = eligibility_for(location, is_remote, description, title)
        pred = result.status
        confusion[expected][pred] += 1
        if pred == expected:
            correct += 1
        else:
            misclassified.append({
                "title": title,
                "location": location,
                "description": description[:80],
                "expected": expected,
                "got": pred,
                "reason": result.reason,
                "evidence": result.evidence,
            })
    return correct, len(LABELED_EXAMPLES), confusion, misclassified


class TestD4LabeledSet:
    """D-4: 80+ labeled examples, accuracy >= 95%, confusion table, misclassified list."""

    def test_accuracy_at_least_95_percent(self):
        """Eligibility classifier must achieve >= 95% accuracy on the labeled set."""
        correct, total, confusion, misclassified = _run_all()
        accuracy = correct / total
        # Print confusion table and misclassified for visibility
        print(f"\nAccuracy: {correct}/{total} = {accuracy:.1%}")
        print("\nConfusion matrix (rows=expected, cols=predicted):")
        labels = ("allowed", "blocked", "unclear")
        header = f"{'':10s}" + "".join(f"{l:10s}" for l in labels)
        print(header)
        for exp in labels:
            row = f"{exp:10s}" + "".join(f"{confusion[exp][pred]:10d}" for pred in labels)
            print(row)
        if misclassified:
            print(f"\nMisclassified ({len(misclassified)}):")
            for m in misclassified:
                print(f"  [{m['expected']} → {m['got']}] loc={m['location']!r} "
                      f"desc={m['description']!r} reason={m['reason']!r}")
        assert accuracy >= 0.95, (
            f"Accuracy {accuracy:.1%} ({correct}/{total}) below 95%.\n"
            f"Misclassified:\n" +
            "\n".join(
                f"  [{m['expected']}→{m['got']}] {m['location']!r} / {m['description']!r}"
                for m in misclassified
            )
        )

    def test_all_allow_examples_classified(self):
        """All ALLOW examples must be classified (not crash)."""
        for title, location, description, expected in LABELED_EXAMPLES:
            if expected == "allowed":
                is_remote = any(
                    w in (location + " " + description).lower()
                    for w in ("remote", "wfh", "work from home", "anywhere", "worldwide", "global")
                )
                result = eligibility_for(location, is_remote, description, title)
                assert result.status in ("allowed", "blocked", "unclear")

    def test_all_block_examples_classified(self):
        """All BLOCK examples must be classified (not crash)."""
        for title, location, description, expected in LABELED_EXAMPLES:
            if expected == "blocked":
                is_remote = any(
                    w in (location + " " + description).lower()
                    for w in ("remote", "wfh", "work from home", "anywhere", "worldwide", "global")
                )
                result = eligibility_for(location, is_remote, description, title)
                assert result.status in ("allowed", "blocked", "unclear")

    def test_labeled_set_has_80_plus_examples(self):
        """The labeled set must have at least 80 examples."""
        assert len(LABELED_EXAMPLES) >= 80

    def test_labeled_set_covers_all_three_labels(self):
        """The labeled set must include ALLOW, BLOCK, and UNCLEAR examples."""
        labels = {exp for _, _, _, exp in LABELED_EXAMPLES}
        assert "allowed" in labels
        assert "blocked" in labels
        assert "unclear" in labels
