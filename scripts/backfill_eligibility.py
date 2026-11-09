"""Backfill eligibility_status for all jobs that have it empty."""
from __future__ import annotations
import sys
sys.path.insert(0, ".")
from app.database import SessionLocal, init_db
from app.models import Job
from app.services.eligibility import eligibility_for
from sqlalchemy import select, func

init_db()
db = SessionLocal()

total = db.scalar(select(func.count(Job.id)))
empty = db.scalar(select(func.count(Job.id)).where(
    (Job.eligibility_status == None) | (Job.eligibility_status == "")
))
print(f"Total: {total}  Empty eligibility_status: {empty}")

jobs = db.scalars(select(Job).where(
    (Job.eligibility_status == None) | (Job.eligibility_status == "")
)).all()

batch_size = 500
for i, job in enumerate(jobs):
    job.eligibility_status = eligibility_for(
        job.location, job.remote, job.description, job.title
    ).status
    if (i + 1) % batch_size == 0:
        db.commit()
        print(f"  Backfilled {i+1}/{len(jobs)}...")

db.commit()
print(f"Done. Backfilled {len(jobs)} rows.")
db.close()
