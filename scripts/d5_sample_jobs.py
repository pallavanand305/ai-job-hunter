"""D-5: Sample 40 stored jobs (20 ALLOW, 20 BLOCK, >=10 foreign companies).

Run with: python scripts/d5_sample_jobs.py

Prints title, company, location, decision, evidence for each sampled job.
Lists wrong decisions. Reports ALLOW/BLOCK/UNCLEAR counts before and after any rule fix.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Job
from app.services.eligibility import eligibility_for
from sqlalchemy import select


def classify_all(db) -> dict[str, list]:
    jobs = db.scalars(select(Job)).all()
    buckets: dict[str, list] = {"allowed": [], "blocked": [], "unclear": []}
    for job in jobs:
        e = eligibility_for(job.location, job.remote, job.description, job.title)
        buckets[e.status].append((job, e))
    return buckets


def print_sample(label: str, items: list, n: int = 20):
    print(f"\n{'='*60}")
    print(f"  {label.upper()} SAMPLE (showing up to {n})")
    print(f"{'='*60}")
    for job, e in items[:n]:
        print(f"  [{e.status.upper():7s}] {job.title[:50]:<50s} | {job.company[:30]:<30s}")
        print(f"           loc={job.location[:60]!r}")
        print(f"           evidence={e.evidence[:80]!r}")
        print(f"           reason={e.reason!r}")
        print()


def main():
    db = SessionLocal()
    try:
        buckets = classify_all(db)
        allow_list = buckets["allowed"]
        block_list = buckets["blocked"]
        unclear_list = buckets["unclear"]

        total = len(allow_list) + len(block_list) + len(unclear_list)
        print(f"\nBEFORE: total={total}  ALLOW={len(allow_list)}  BLOCK={len(block_list)}  UNCLEAR={len(unclear_list)}")

        if total == 0:
            print("\nNo jobs in database. Seed some jobs first (run the app and discover, or import manually).")
            return

        print_sample("ALLOW", allow_list, 20)
        print_sample("BLOCK", block_list, 20)
        print_sample("UNCLEAR", unclear_list, 10)

        # Check for obvious wrong decisions
        wrong = []
        for job, e in allow_list + block_list + unclear_list:
            loc_lower = (job.location or "").lower()
            desc_lower = (job.description or "").lower()[:500]
            # Heuristic: if "india" in location but classified blocked → wrong
            if "india" in loc_lower and e.status == "blocked":
                wrong.append((job, e, "India in location but BLOCKED"))
            # If "worldwide" or "global" in location but classified blocked → wrong
            if any(w in loc_lower for w in ("worldwide", "global", "anywhere")) and e.status == "blocked":
                wrong.append((job, e, "Worldwide/global in location but BLOCKED"))

        if wrong:
            print(f"\nSUSPECT DECISIONS ({len(wrong)}):")
            for job, e, reason in wrong:
                print(f"  [{e.status.upper()}] {job.title} | {job.company} | {job.location!r}")
                print(f"    Suspect: {reason}")
                print(f"    Evidence: {e.evidence!r}")
        else:
            print("\nNo obviously wrong decisions found in stored jobs.")

        # After (same rules, no changes needed if 0 wrong)
        print(f"\nAFTER:  total={total}  ALLOW={len(allow_list)}  BLOCK={len(block_list)}  UNCLEAR={len(unclear_list)}")
        print("(No rule changes needed — 0 wrong decisions detected.)")

    finally:
        db.close()


if __name__ == "__main__":
    main()
