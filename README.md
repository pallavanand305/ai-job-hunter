# AI Job Hunter

Personal AI-powered job discovery, matching, tailoring and application tracker.  
Built for a single user running locally. Never auto-submits anything.

---

## What it does

| Feature | Detail |
|---------|--------|
| **Job discovery** | 20 connectors (Greenhouse, Lever, Remotive, RemoteOK, Himalayas, Jobicy, WeWorkRemotely, PythonJobs, WorkingNomads, TheMuse, LandingJobs, Arbeitnow, Adzuna, Jooble, LinkedIn/Naukri/Indeed/Instahyre/Wellfound alert feeds) |
| **India eligibility** | Classifies every job as ALLOW / BLOCK / UNCLEAR based on hiring geography, not company country. Onsite India, remote-worldwide, remote-India all = ALLOW. US-only, UK-only, EMEA = BLOCK. Stored in an indexed DB column for fast filtering. |
| **Matching** | Weighted scoring (skills 35%, experience 20%, responsibilities 20%, salary 15%, location 10%) × role-fit × target-role priority. AI/GenAI roles rank above DevOps/Cloud. |
| **Tailoring** | LLM (Gemini → Groq → template fallback) tailors summary, skills, bullets for all roles toward the JD. No fabrication — facts only from your master resume. |
| **PDF + DOCX export** | ATS-friendly single-column layout. Reading order: Summary → Skills → Experience → Projects → Education → Certifications. |
| **Application tracker** | draft → approved → submitted flow. Manual submit only (`authorized: true` required). Nothing is auto-sent. |
| **Stale expiry** | Jobs not seen for 30 days are marked stale and hidden by default. Toggle with "Show stale". |
| **Gmail integration** | Read-only by default. Classifies inbox for interview/assessment/rejection/offer. Sending disabled unless `GMAIL_ENABLE_SEND=true`. |

---

## Quick start

```powershell
# 1. Clone and create venv
git clone https://github.com/pallavanand305/ai-job-hunter.git
cd ai-job-hunter
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# 2. Copy and edit env
copy .env.example .env
# Set GEMINI_API_KEY and/or GROQ_API_KEY

# 3. Start
.\.venv\Scripts\python.exe run.py

# 4. Open browser
# http://127.0.0.1:8088
```

---

## Configuration (`.env`)

| Key | Default | Purpose |
|-----|---------|---------|
| `GEMINI_API_KEY` | — | Primary LLM (free tier at https://aistudio.google.com) |
| `GROQ_API_KEY` | — | Secondary LLM fallback (free tier at https://console.groq.com) |
| `LLM_MAX_TOKENS` | 4096 | Max output tokens per LLM call |
| `LLM_DAILY_CALL_LIMIT` | 200 | Daily LLM call cap (free-tier guard) |
| `TAILOR_TARGET_SCORE` | 90 | Target match % before adding verified keywords |
| `STALE_DAYS` | 30 | Days before unseen jobs are marked stale |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | — | Free Adzuna API |
| `JOOBLE_API_KEY` | — | Free Jooble API |
| `LINKEDIN_FEED_URL` etc. | — | RSS alert feed URLs |
| `GMAIL_ENABLE_SEND` | false | Enable outreach sending via Gmail |
| `HOST` / `PORT` | 127.0.0.1 / 8088 | Server bind |

---

## Preferred on-site cities (score 1.0)

Noida, Greater Noida, Delhi, Gurgaon/Gurugram, Bangalore/Bengaluru, Hyderabad, Pune, Mumbai, Ahmedabad, Gandhinagar.  
Other Indian cities score 0.65. Non-India onsite = 0.0. India-eligible remote = 1.0. UNCLEAR remote = 0.4.

City aliases: Gurgaon = Gurugram, Bangalore = Bengaluru, Bombay = Mumbai.

---

## Eligibility classification

The company's home country does **not** decide eligibility — only the stated hiring geography does.

| Label | Meaning |
|-------|---------|
| **ALLOW** | Onsite/hybrid in India; remote worldwide/global; remote-India; remote APAC/Asia; India listed among several countries |
| **BLOCK** | Onsite outside India; remote restricted to a specific country/region that excludes India; "authorized to work in" clauses for non-India |
| **UNCLEAR** | Remote with no stated geography; timezone-only preference |

Default Jobs view shows ALLOW + UNCLEAR. "Show blocked" toggle reveals BLOCK.

---

## Tailoring rules

- **Never fabricates** — all bullets, skills and metrics come from your uploaded master resume
- Job titles in experience are **immutable** (locked to master resume values)
- Template fallback shows a visible warning when no LLM is configured
- Skills limited to ≤ 6 JD-relevant categories, whitelist from your master resume
- GraphRAG/LLM projects automatically ranked first for RAG/LLM/agent JDs
- Salary-less jobs never hidden, even with a minimum salary preference set

---

## Target-role priority order

1. AI Engineer
2. GenAI Engineer
3. Python Backend Engineer
4. MLOps Engineer
5. DevOps Engineer
6. Cloud Engineer
7. Software Engineer

Change via **Profile → Preferred roles** or `DEFAULT_ROLES` in `.env`.

---

## Running tests

```powershell
.\scripts\check.ps1
```

Expected: `269 passed, 1 warning` + `All checks passed.`

---

## Safety

- Never auto-submits applications
- Never auto-sends outreach messages
- Gmail sending disabled by default (`GMAIL_ENABLE_SEND=false`)
- CORS restricted to loopback
- Upload size capped at 10 MB
- App binds to `127.0.0.1` only — do not expose publicly without authentication

---

## File structure

```
app/
  api/          FastAPI routers (jobs, applications, outreach, profile, system)
  connectors/   Job source connectors (20 sources)
  llm/          LLM client, providers, cache, rate limiter, prompts, schemas
  services/     Business logic (tailoring, matching, eligibility, discovery, profiles…)
  static/       Vanilla JS SPA (index.html, app.js, styles.css)
  models.py     SQLAlchemy models
  config.py     Pydantic settings
data/
  jobhunter.db  SQLite database
  artifacts/    Generated PDFs and DOCX files
scripts/
  check.ps1     Full CI check (compile + pytest + JS lint)
tests/          Pytest test suite (269 tests)
```

---

## Status

See `AUDIT_REPORT.md` for the full audit trail and `PROGRESS.md` for the change log.
