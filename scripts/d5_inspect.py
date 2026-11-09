"""Inspect suspicious D-5 ALLOW jobs."""
from __future__ import annotations
import sys
sys.path.insert(0, ".")
from app.database import SessionLocal, init_db
from app.models import Job
from app.services.eligibility import eligibility_for, _detect_worldwide
from sqlalchemy import select

init_db()
db = SessionLocal()

# Find by partial title match
all_jobs = db.scalars(select(Job)).all()
targets = [
    "Distributed Systems Testing",
    "Warehouse Operative",
    "Director of National Accounts",
]
for t in targets:
    matches = [j for j in all_jobs if t.lower() in (j.title or "").lower()]
    for j in matches[:1]:
        e = eligibility_for(j.location, j.remote, j.description, j.title)
        loc_lower = (j.location or "").lower()
        desc_lower = (j.description or "").lower()[:500]
        combined = f"{loc_lower} {desc_lower}"
        ww = _detect_worldwide(combined)
        print(f"TITLE   : {j.title}")
        print(f"LOCATION: {j.location}")
        print(f"REMOTE  : {j.remote}")
        print(f"STATUS  : {e.status} | {e.reason}")
        print(f"EVIDENCE: {e.evidence}")
        print(f"WW TERM : {ww!r}")
        print(f"LOC_LOWER: {loc_lower!r}")
        print(f"DESC[:200]: {(j.description or '')[:200]}")
        print()

db.close()
