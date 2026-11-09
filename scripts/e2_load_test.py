"""E-2: Load 5000 jobs into DB and measure /api/jobs response time."""
from __future__ import annotations
import sys, time
sys.path.insert(0, ".")

from app.database import SessionLocal, init_db
from app.models import Job
from app.services.dedupe import job_hash
from sqlalchemy import select, func

init_db()
db = SessionLocal()

existing = db.scalar(select(func.count(Job.id)))
print(f"Existing jobs: {existing}")

# Insert up to 5000 total
target = 5000
needed = max(0, target - existing)
print(f"Inserting {needed} synthetic jobs...")

if needed > 0:
    batch = []
    for i in range(needed):
        loc = ["Remote, India", "Noida, India", "Bangalore, India", "Remote, United States",
               "Remote - Worldwide", "London, UK", "Remote"][i % 7]
        remote = i % 7 in (0, 2, 4, 6)
        key = job_hash(f"Bulk Job {i}", f"BulkCo{i % 100}", loc)
        batch.append(Job(
            title=f"Bulk Job {i}",
            company=f"BulkCo{i % 100}",
            location=loc,
            remote=remote,
            description=f"Python FastAPI AWS Docker Kubernetes backend engineer role {i}.",
            dedupe_hash=key,
            raw={"bulk": True},
        ))
        if len(batch) >= 500:
            db.add_all(batch)
            db.commit()
            batch = []
    if batch:
        db.add_all(batch)
        db.commit()

total = db.scalar(select(func.count(Job.id)))
print(f"Total jobs after insert: {total}")
db.close()

# Measure /api/jobs via FastAPI TestClient
import os
os.environ["DATABASE_URL"] = f"sqlite:///./data/jobhunter.db"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["LLM_CACHE_ENABLED"] = "false"

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    # Default view (BLOCK hidden, stale hidden, limit=50)
    runs = []
    for _ in range(3):
        t0 = time.time()
        r = client.get("/api/jobs", params={"limit": 50})
        runs.append(time.time() - t0)
    avg = sum(runs) / len(runs)
    print(f"\n/api/jobs (limit=50, default filters): {avg*1000:.0f}ms avg ({min(runs)*1000:.0f}–{max(runs)*1000:.0f}ms)")
    print(f"  Returned {r.json()['count']} items, total={r.json()['total']}")

    # show_stale=true, show_blocked=true, limit=200
    runs2 = []
    for _ in range(3):
        t0 = time.time()
        r2 = client.get("/api/jobs", params={"limit": 200, "show_stale": "true", "show_blocked": "true"})
        runs2.append(time.time() - t0)
    avg2 = sum(runs2) / len(runs2)
    print(f"/api/jobs (limit=200, all visible): {avg2*1000:.0f}ms avg")
    print(f"  Returned {r2.json()['count']} items, total={r2.json()['total']}")

    # Dashboard
    runs3 = []
    for _ in range(3):
        t0 = time.time()
        client.get("/api/dashboard")
        runs3.append(time.time() - t0)
    avg3 = sum(runs3) / len(runs3)
    print(f"/api/dashboard: {avg3*1000:.0f}ms avg")

print("\nE-2 DONE")
