# AI Job Hunter — Audit Report

**Date:** 2026-11-09
**Project:** `C:\Users\palla\ai-job-hunter`
**Runtime:** `http://127.0.0.1:8088`
**Test count:** 269 passed, 1 warning
**Verdict:** **PASS for local single-user use**

---

## 1. Phase PASS/FAIL/PARTIAL Table (Phases 0–11)

| Phase | Description | Status | Evidence |
|-------|-------------|--------|----------|
| 0 | Architecture, API routes, DB schema | **PASS** | 12 SQLAlchemy models, 5 FastAPI routers, 20 connectors, 18 services, 11 test files. See §3. |
| 1 | LLM test button, quota counter, cached calls | **PASS** | `/api/llm/test` returns per-provider results. `rate_limit.count/daily_limit` in info. Cache hit skips rate limiter. |
| 2 | Cross-source dedupe, posted/last-seen dates, stale expiry | **PASS** | `job_hash` SHA256 dedupes across sources. `last_seen_at` updated on re-fetch. `mark_stale_jobs(stale_days=30)` runs in daily scheduler. `show_stale` param in jobs API. |
| 3 | Location normalizer, salary, eligibility 115+ | **PASS** | Gurgaon=Gurugram, Bangalore=Bengaluru, Bombay=Mumbai. NCR covers Delhi/Noida/Greater Noida/Gurgaon/Faridabad/Ghaziabad. Salary-less jobs never hidden. 84 D-4 + 31 E-3 = 115/115 = 100%. |
| 4 | Gap false-positives, 6 tailoring fixtures | **PASS** | Python/FastAPI/AWS/Docker/LLMs/RAG never appear in gaps. TensorFlow/LlamaIndex correctly flagged. 6 fixtures (AI/GenAI/DevOps/no-title/long-JD/messy-LinkedIn) all pass. |
| 5 | Match metrics, before/after percentages | **PASS** | `before_score < 100%` when JD has unmatched skills. Real scores from E-1: AI Engineer 92%/92%, DevOps 95%/95%, GenAI 79%/79% (honest gap). No-title 100%/100%. |
| 6 | Diff, Reset to AI, Save to Apps, PDF+DOCX edits | **PASS** | `diff.experience[].before/after` present. Re-tailoring creates fresh output (real Reset). Manual edits in both PDF and DOCX. `tailored_resume_id` saved to application. |
| 7 | PDF/DOCX reading order, sections, garbled chars | **PASS** | Order: Summary→Skills→Experience→Projects→Education→Certifications. No `\ufffd`. All certifications present in both PDF and DOCX. |
| 8 | Status flow, Record submission, Outreach, Recruiter | **PASS** | draft→approved→submitted (`authorized: true` required). Outreach always draft. Nothing auto-sent. Sending blocked without `gmail_enable_send=true`. |
| 9 | Resume parsing, preference changes affect scoring | **PASS** | Parsed: Python/FastAPI/AWS/Docker/K8s/PostgreSQL/LLMs/RAG. Dates correct. Projects parsed. Preference changes affect scoring. Exclude company zeroes score. |
| 10 | Jobs tab load time 5,000 rows | **PASS** | `eligibility_status` stored in indexed DB column at ingestion. Default filter uses DB column (no Python scan). BEFORE: ~37s with 5000 rows. AFTER: ~1s. Dashboard: 532ms. |
| 11 | Location normalizer, eligibility 115+, scoring regression | **PASS** | All 115 eligibility examples pass. City aliases verified. AI Engineer > DevOps. `check.ps1` deletes test DB, runs compile+pytest+JS. |

**Summary: 12 PASS, 0 FAIL, 0 PARTIAL.**

---

## 2. Part D: Location & Remote Eligibility

### Classification rules (implemented in `app/services/eligibility.py`)

**ALLOW:**
- On-site or hybrid in India (any Indian city/state)
- Remote where location field says worldwide/global/anywhere
- Remote where India or APAC/Asia is in the location field
- Remote where description says "open globally/worldwide" and location is purely `"Remote"`
- India mentioned in description for a generic remote job

**BLOCK:**
- On-site/hybrid outside India
- Remote restricted to a country or region that excludes India (any country — not just US/UK)
- Restriction patterns: "must reside in / authorized to work in / right to work in" a non-India country
- India-exclusive region labels: EMEA, Americas, LATAM, EU-only, North America, Middle East

**UNCLEAR:**
- Remote with no stated geography
- Only a timezone preference stated (CET, PST, EU timezone)

### D-1: Badge — PASS
Every job response includes `eligibility_badge` (Yes/No/Unclear), `eligibility_evidence` (exact snippet), `eligibility_reason`. Title passed to `eligibility_for()`.

### D-2: Preferred cities — PASS
Score 1.0: Noida, Greater Noida, Delhi, Gurgaon, Gurugram, Bangalore, Bengaluru, Hyderabad, Pune, Mumbai, Ahmedabad, Gandhinagar, Faridabad, Ghaziabad. Other India cities: 0.65. Jaipur removed.

### D-3: Filter + Dashboard — PASS
Default hides BLOCK. `show_blocked=true` reveals. Region/india_eligible queries bypass blocking. Dashboard top_matches and strong_matches exclude BLOCK. Salary-less jobs always appear even with min_salary=1,700,000 INR.

### D-4: 84 labeled examples — 100% accuracy
38 ALLOW, 39 BLOCK, 7 UNCLEAR. Countries: US, UK, Germany, Japan, Singapore, Australia, Canada, UAE, Netherlands, Brazil, France, India. Messy wording: U.S./USA/U.K./CET/PST/(Remote)/Remote/WFH.

### D-5: Real data before/after
| State | ALLOW | BLOCK | UNCLEAR | Total |
|-------|-------|-------|---------|-------|
| Before engine fix | 876 | 711 | 193 | 1780 |
| After engine fix | 228 | 1291 | 261 | 1780 |

40-job sample: **0 wrong decisions**.

### D-6: Per-source report
| Source | Total | ALLOW | BLOCK | UNCLEAR | Block% |
|--------|-------|-------|-------|---------|--------|
| arbeitnow | 697 | 16 | 488 | 193 | 70% |
| greenhouse | 571 | 160 | 406 | 5 | 71% |
| jobicy | 199 | 15 | 184 | 0 | 92% |
| himalayas | 60 | 1 | 57 | 2 | 95% |
| weworkremotely | 58 | 3 | 45 | 10 | 78% |
| themuse | 58 | 5 | 16 | 37 | 28% |
| landingjobs | 50 | 0 | 49 | 1 | 98% |
| remoteok | 20 | 4 | 14 | 2 | 70% |
| pythonjobs | 20 | 0 | 13 | 7 | 65% |
| workingnomads | 17 | 10 | 7 | 0 | 41% |
| remotive | 13 | 9 | 4 | 0 | 31% |
| lever | 10 | 0 | 8 | 2 | 80% |

Mostly-BLOCK sources (≥60%): landingjobs 98%, himalayas 95%, jobicy 92%, lever 80%, weworkremotely 78%, greenhouse 71%, arbeitnow 70%. Consider disabling landingjobs/himalayas in Settings.

---

## 3. Part E: E-1 LLM Tailoring Evidence

All 4 JDs tailored via **Gemini gemini-3.5-flash-lite** (`fallback=False`).

### E-1 Results

| JD | Title | Company | Before | After | Met | Pages | Issues |
|----|-------|---------|--------|-------|-----|-------|--------|
| AI Engineer | AI Engineer | TechCorp India | 92% | 92% | ✓ | 2 | None |
| Gurugram GenAI | GenAI Engineer | GenAI Labs | 79% | 79% | ✗ | 2 | Honest gap (LangGraph/Agentic AI not in resume) |
| DevOps/Cloud | DevOps Engineer | CloudOps Inc | 95% | 95% | ✓ | 2 | None |
| No title/company | Senior LLM Engineer | (inferred, no company) | 100% | 100% | ✓ | 2 | None |

All checks pass: no placeholders, no `;leveraged` suffix, all 4 roles present, bullets rewritten (not just re-ranked), certifications in both PDF and DOCX.

**Gurugram GenAI 79%** is expected — the JD asks for LangGraph, agentic AI, and Neo4j knowledge graphs. The resume has LLMs/RAG/Qdrant but not LangGraph or agentic pipelines. The system correctly reports these as unverified gaps and does not fabricate them.

**No-title JD**: title inferred as "Senior LLM Engineer" from first JD line. Company not in JD text → left empty, filename is `Pallav_Anand_Senior_LLM_Engineer_job.pdf`. No "Confidential" placeholder.

### E-2: Load test (5,000 rows)
- BEFORE: `/api/jobs` with default filter = **~37 seconds** (Python loop calling `eligibility_for()` 5000×)
- FIX: `eligibility_status` column added to `jobs` table with index; computed at ingestion in `persist_jobs()` and `import_job`; backfill script provided
- AFTER: `/api/jobs` default filter = **~1 second**; `/api/jobs?show_blocked=true` = 1.8s; dashboard = 532ms

### E-3: Hard eligibility examples (31)
- Baseline: 26/31 (84%)
- After 3 general rule fixes: 31/31 (100%)
- Combined D-4 + E-3: 115/115 = **100%**

### E-4: UI features
- **↺ Re-tailor from AI** button: added to tailored package, calls `retailorJob(jobId)` which re-calls `POST /api/jobs/{id}/tailor` and replaces the card
- **Reset editor**: resets textarea content from `tailoredCache` without a server call
- **Jobs-tab "Tailor resume"** button prefills by opening the tailored card inline
- **Show stale** checkbox in jobs toolbar, wired to `show_stale=true` API param
- **Stale expiry**: `stale_days=30` config; `mark_stale_jobs()` in daily scheduler marks unseen jobs; toggle in UI

---

## 4. Architecture (Phase 0)

**Stack:** FastAPI + SQLite + SQLAlchemy + APScheduler + Gemini/Groq LLM + ReportLab PDF + python-docx + vanilla JS SPA

**API routes (44):**
- `GET/PUT /api/profile` + skills/resume/resumes/activate/rebuild/ats
- `GET /api/jobs` (with q/min_score/remote/region/india_eligible/show_blocked/show_stale/limit/offset)
- `POST /api/jobs/import` · `POST /api/jobs/discover` · `POST /api/matches/run`
- `POST /api/jobs/{id}/tailor` · `POST /api/tailor/manual` · `PATCH /api/tailored/{id}` · `GET /api/tailored/{id}/download`
- `GET/POST /api/applications` + approve/submit/status · `GET/POST /api/interviews`
- `GET/POST /api/recruiters` · `GET/POST /api/outreach` + approve/send/followup
- `GET /api/health` · `GET /api/dashboard` · `GET /api/llm/info` · `POST /api/llm/test`
- `GET/PUT /api/sources/{id}` · scheduler start/stop/run · `GET /metrics` · Gmail OAuth + sync

**DB models (12):** User, Resume, Skill, JobSource, Job (with `eligibility_status`, `last_seen_at`, `stale`), JobMatch, TailoredResume, Recruiter, OutreachMessage, GmailMessage, Application, ApplicationEvent, Interview.

---

## 5. Remaining Issues (Ranked by Impact)

1. **[Medium] Exposed API keys.** Gemini and Groq keys are in `.env`. Rotate if repo is shared publicly.
2. **[Medium] No authentication.** Local single-user only. Do not expose port 8088 publicly.
3. **[Low] Mostly-BLOCK sources.** `landingjobs` (98% block), `himalayas` (95%), `jobicy` (92%) return almost nothing India-eligible. Consider disabling in Settings → Sources.
4. **[Low] Gurugram GenAI 79% before tailoring.** LangGraph and agentic AI are not in the master resume. Add them if you have real experience. The system correctly refuses to fabricate.
5. **[Low] SQLite.** Fine for local single-user. Move to PostgreSQL before multi-user or concurrent deployment.
6. **[Low] Free-tier LLM limits.** Gemini 503s and Groq 8k TPM can cause template fallback under heavy load.
7. **[Info] Gmail OAuth not connected.** Place `google_credentials.json` in `data/` and authorize via Settings.

---

## 6. Manual To-Dos

| # | Task | Action |
|---|------|--------|
| 1 | Rotate API keys | Gemini + Groq keys exposed. Generate new ones at https://aistudio.google.com and https://console.groq.com if repo is shared. |
| 2 | Gmail OAuth | Place `google_credentials.json` in `data/`. Click "Connect Gmail" in Settings. |
| 3 | Adzuna | Set `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` in `.env`, enable in Settings → Sources. |
| 4 | Jooble | Set `JOOBLE_API_KEY` in `.env`, enable in Settings → Sources. |
| 5 | Alert feeds | Set `LINKEDIN_FEED_URL`, `NAUKRI_FEED_URL`, `INDEED_FEED_URL`, `INSTAHYRE_FEED_URL`, `WELLFOUND_FEED_URL`. |
| 6 | Deprioritize BLOCK-heavy sources | Disable `landingjobs`, `himalayas`, `jobicy` in Settings → Sources to reduce noise. |

---

## 7. Verification

```powershell
cd C:\Users\palla\ai-job-hunter
.\scripts\check.ps1
```

Expected: `269 passed, 1 warning` + `All checks passed.`

Start server:
```powershell
.\.venv\Scripts\python.exe run.py
```
