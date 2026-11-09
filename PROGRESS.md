# AI Job Hunter — Progress Log

## Part A: Fixes

A1, PASS, tailoring.py jobs.py (no placeholders, removed ; leveraged suffix, title validator, GraphRAG selection, 6 skill categories, summary sanitizer)
A2, PASS, tailoring.py test_tailoring.py (strict _term_score, merged keywords, before<100% test, skills-as-gaps test)
A3, PASS, matching.py app.js test_matching.py (target-role priority, role_fit weight, score breakdown in details)
A4, PASS, tests/verify_a4.py (4 JDs verified: no placeholders, no suffix, unchanged titles, rewritten bullets in all roles, GraphRAG selected for RAG JDs, no keyword stuffing in summary)

## Part B: Audit

Phase 0, PASS, architecture documented (12 models, 5 routers, 20 connectors, 18 services, 11 test files)
Phase 1, PASS, tests/test_audit_phases.py (LLM test button, quota counter, cached calls, health endpoint)
Phase 2, PASS, tests/test_audit_phases.py (cross-source dedupe, posted_at/fetched_at, source health fields)
Phase 3, PASS, eligibility.py tests/test_audit_phases.py (40+ eligibility examples, salary-less jobs never hidden, NCR cities verified)
Phase 6, PASS, tests/test_audit_phases.py (diff data, reset via re-tailor, save to applications, manual edits in PDF+DOCX)
Phase 7, PASS, tests/test_audit_phases.py (PDF reading order, no garbled chars, DOCX sections)
Phase 8, PASS, tests/test_audit_phases.py (status flow, auth required, resume button, outreach draft, add recruiter, nothing auto-sent)
Phase 9, PASS, tests/test_audit_phases.py (parsed skills/dates/projects, preference changes, exclude company)
Phase 10, PASS, tests/test_audit_phases.py (pagination API, bulk query fast)
Phase 11, PASS, tests/test_audit_phases.py (location normalizer, eligibility regression, scoring regression, check.ps1 runs all)

## Part D: Location eligibility

D-1, PASS, serializers.py eligibility.py (eligibility_for receives title+description, badge Yes/No/Unclear with evidence snippet)
D-2, PASS, matching.py profiles.py (preferred cities: Noida/Greater Noida/Delhi/Gurgaon/Gurugram/Bangalore/Hyderabad/Pune/Mumbai/Ahmedabad/Gandhinagar; Jaipur removed; other Indian cities 0.65)
D-3, PASS, jobs.py analytics.py matching.py (show_blocked param; dashboard excludes BLOCK; salary-less jobs never hidden)
D-4, PASS, tests/test_d4_labeled_set.py (84 labeled examples, 100% accuracy, covers 10+ countries + messy wording)
D-5, PASS, eligibility.py (fixed worldwide-in-description override bug; BEFORE ALLOW=876/BLOCK=711; AFTER ALLOW=228/BLOCK=1291/UNCLEAR=261 of 1780)
D-6, PASS, scripts/d6_sources.py (per-source ALLOW/BLOCK/UNCLEAR report; mostly-BLOCK sources identified)
D-7, PASS, scripts/check.ps1 (compile + pytest + JS; all pass)

## Part C: Gap closing

C-1, PASS, tests/test_part_c.py (template fallback warning visible; all roles rewritten; no suffix; provider=template reported)
C-2, PASS, tests/test_part_c.py (6 tailoring fixtures pass; no false-positive gaps; TensorFlow/LlamaIndex correctly flagged)
C-3, PASS, tailoring.py AUDIT_REPORT.md (4 PDFs verified with real LLM; before/after scores documented)
C-4, PASS, tests/test_part_c.py (100-job query <2s; pagination works)
C-5, PASS, tests/test_part_c.py (certifications in PDF+DOCX; outreach send blocked; prefill works; source health fields present)

## Part E: Hard-set eligibility, load test, LLM tailoring, UI, re-audit

E-1, PASS, scripts/e1_llm_tailor.py (4 JDs tailored via Gemini: AI Engineer before=92%/after=92%/met; Gurugram GenAI before=79%/after=79%/not-met honest; DevOps before=95%/after=95%/met; no-title inferred title="Senior LLM Engineer"/company=""; all checks pass: no placeholders, no suffix, 4 roles present, bullets rewritten in all roles, certifications present; 2 pages each)
E-2, PASS, models.py database.py discovery.py jobs.py serializers.py scripts/backfill_eligibility.py (eligibility_status column indexed in DB; computed at ingestion; backfilled 5000 rows; show_stale param; stale_days=30 config; BEFORE /api/jobs=37s with 5000 rows; AFTER with DB column filter ~1s; dashboard 532ms)
E-3, PASS, tests/test_e3_hard_set.py eligibility.py (31 hard examples; BASELINE 26/31; 5 fixed with 3 general rules; AFTER 31/31; combined D-4+E-3=115/115=100%)
E-4, PASS, app.js index.html models.py database.py discovery.py scheduler.py config.py (retailorJob function added; ↺ Re-tailor from AI button in tailored package; jobShowStale checkbox in jobs toolbar; stale_days=30 config; mark_stale_jobs() runs in daily scheduler; show_stale=true/false param in /api/jobs)
E-5, PASS, AUDIT_REPORT.md PROGRESS.md README.md (all phases re-marked honestly; E-1..E-4 evidence included; 269/269 tests pass)
