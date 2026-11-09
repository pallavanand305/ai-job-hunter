"""D-5: Sample 40 jobs from the DB and report ALLOW/BLOCK/UNCLEAR counts before and after."""
from __future__ import annotations
import sys
sys.path.insert(0, ".")

from app.database import SessionLocal, init_db
from app.models import Job
from app.services.eligibility import eligibility_for
from sqlalchemy import select, func

init_db()
db = SessionLocal()

all_jobs = db.scalars(select(Job)).all()
total = len(all_jobs)

allow_jobs = [j for j in all_jobs if eligibility_for(j.location, j.remote, j.description, j.title).status == "allowed"]
block_jobs = [j for j in all_jobs if eligibility_for(j.location, j.remote, j.description, j.title).status == "blocked"]
unclear_jobs = [j for j in all_jobs if eligibility_for(j.location, j.remote, j.description, j.title).status == "unclear"]

print(f"\n=== COUNTS (new engine) ===")
print(f"Total:  {total}")
print(f"ALLOW:  {len(allow_jobs)}")
print(f"BLOCK:  {len(block_jobs)}")
print(f"UNCLEAR:{len(unclear_jobs)}")

# Sample 20 ALLOW and 20 BLOCK
import random
random.seed(42)
sample_allow = random.sample(allow_jobs, min(20, len(allow_jobs)))
sample_block = random.sample(block_jobs, min(20, len(block_jobs)))
sample = sample_allow + sample_block

print(f"\n=== 40-JOB SAMPLE ===")
print(f"{'#':<3} {'Label':<8} {'Title'[:35]:<36} {'Company'[:20]:<21} {'Location'[:30]:<31} {'Evidence'[:50]}")
print("-" * 140)

wrong = []
for i, j in enumerate(sample, 1):
    e = eligibility_for(j.location, j.remote, j.description, j.title)
    expected = "allowed" if j in sample_allow else "blocked"
    match = "OK" if e.status == expected else "WRONG"
    if match == "WRONG":
        wrong.append((j, expected, e))
    label = f"{e.status[:5]}"
    title = (j.title or "")[:35]
    company = (j.company or "")[:20]
    location = (j.location or "")[:30]
    evidence = (e.evidence or "")[:50]
    print(f"{i:<3} {label:<8} {title:<36} {company:<21} {location:<31} {evidence}")

print(f"\n=== WRONG DECISIONS ({len(wrong)}) ===")
for j, expected, e in wrong:
    print(f"  TITLE: {j.title}")
    print(f"  LOC:   {j.location}")
    print(f"  EXPECTED: {expected}  GOT: {e.status}")
    print(f"  REASON: {e.reason}")
    print(f"  EVIDENCE: {e.evidence}")
    print()

db.close()
