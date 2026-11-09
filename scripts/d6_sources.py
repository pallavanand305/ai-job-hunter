"""D-6: Per-source ALLOW/BLOCK/UNCLEAR report."""
from __future__ import annotations
import sys
sys.path.insert(0, ".")
from app.database import SessionLocal, init_db
from app.models import Job, JobSource
from app.services.eligibility import eligibility_for, _detect_countries
from sqlalchemy import select
from collections import defaultdict

init_db()
db = SessionLocal()

sources = {s.id: s.name for s in db.scalars(select(JobSource)).all()}
all_jobs = db.scalars(select(Job)).all()

tally: dict[str, dict] = defaultdict(lambda: {"allowed": 0, "blocked": 0, "unclear": 0, "total": 0})
country_allow: dict[str, int] = defaultdict(int)

for j in all_jobs:
    src = sources.get(j.source_id, "manual")
    e = eligibility_for(j.location, j.remote, j.description, j.title)
    tally[src]["total"] += 1
    tally[src][e.status] += 1
    if e.status == "allowed":
        loc_countries = _detect_countries((j.location or "").lower())
        if loc_countries and "IN" not in loc_countries:
            cc = next(iter(loc_countries))
            country_allow[cc] += 1
        elif "IN" in loc_countries:
            country_allow["India"] += 1
        else:
            country_allow["Unknown/Global"] += 1

print(f"\n=== PER-SOURCE REPORT ===")
print(f"{'Source':<22} {'Total':>6} {'ALLOW':>6} {'BLOCK':>6} {'UNCLEAR':>8} {'Block%':>7}")
print("-" * 65)
mostly_block = []
for src, t in sorted(tally.items(), key=lambda x: -x[1]["total"]):
    total = t["total"]
    if total == 0:
        continue
    block_pct = 100 * t["blocked"] / total
    print(f"{src:<22} {total:>6} {t['allowed']:>6} {t['blocked']:>6} {t['unclear']:>8} {block_pct:>6.0f}%")
    if block_pct >= 60 and total >= 5:
        mostly_block.append((src, block_pct, total))

print(f"\n=== SOURCES MOSTLY BLOCK (>=60%) ===")
for src, pct, total in sorted(mostly_block, key=lambda x: -x[1]):
    print(f"  {src:<22} {pct:.0f}% block  ({total} jobs)")

print(f"\n=== COUNTRIES OF FOREIGN ALLOW JOBS ===")
for cc, n in sorted(country_allow.items(), key=lambda x: -x[1])[:20]:
    print(f"  {cc}: {n}")

db.close()
