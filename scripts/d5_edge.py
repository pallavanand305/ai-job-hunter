import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.eligibility import eligibility_for
cases = [
    ("Irvine, CA", False, "", ""),
    ("Baltimore, MD", False, "", ""),
    ("Remote, United States", True, "must be based in est timezone", ""),
    ("Home based - EMEA", False, "", ""),
    ("Würzburg", False, "", ""),
]
for loc, remote, desc, title in cases:
    r = eligibility_for(loc, remote, desc, title)
    print(f"loc={loc!r:30s} -> {r.status:8s} ev={r.evidence!r}")
