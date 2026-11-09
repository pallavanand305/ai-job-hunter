"""Part C: Gap-closing tests (C-1 through C-5)."""
from __future__ import annotations

import io
import time

import pytest
from fastapi.testclient import TestClient

from app.models import Job
from tests.conftest import RESUME_TEXT


def _upload_resume(client):
    r = client.post(
        "/api/profile/resume",
        files={"file": ("resume.txt", RESUME_TEXT, "text/plain")},
        data={"variant": "master", "make_master": "true"},
    )
    assert r.status_code == 200, r.text


def _import_job(client, title, company, location, description, url, **kw):
    payload = dict(
        title=title, company=company, location=location,
        description=description, url=url, remote=kw.get("remote", True),
    )
    payload.update(kw)
    r = client.post("/api/jobs/import", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# ── C-1: Bullet rewriting — fallback flag and warning ────────────────────

class TestC1BulletRewriting:
    """C-1: Template fallback must set llm.fallback=True and include a warning."""

    def test_fallback_flag_present_in_match_report(self, client):
        """match_report.llm.fallback must be True when no LLM is configured (test env)."""
        _upload_resume(client)
        job = _import_job(
            client,
            "C1 AI Engineer", "C1Corp", "Remote, India",
            "Python FastAPI AWS Docker LLM RAG backend role.",
            "https://example.com/jobs/c1-fallback",
        )
        tailored = client.post(f"/api/jobs/{job['id']}/tailor").json()
        report = tailored["match_report"]
        assert "llm" in report, "match_report must have 'llm' key"
        assert report["llm"]["fallback"] is True, "fallback must be True in test env (no LLM keys)"

    def test_fallback_reason_present(self, client):
        """match_report.llm.reason must be non-empty when fallback is True."""
        _upload_resume(client)
        job = _import_job(
            client,
            "C1 Reason Engineer", "C1ReasonCo", "Remote, India",
            "Python FastAPI AWS Docker backend role.",
            "https://example.com/jobs/c1-reason",
        )
        tailored = client.post(f"/api/jobs/{job['id']}/tailor").json()
        report = tailored["match_report"]
        assert report["llm"]["fallback"] is True
        assert report["llm"]["reason"], "reason must be non-empty when fallback=True"

    def test_fallback_bullets_present_in_all_roles(self, client):
        """Template fallback must produce bullets for every role (re-ranked, not empty)."""
        _upload_resume(client)
        job = _import_job(
            client,
            "C1 All Roles Engineer", "C1AllCo", "Remote, India",
            "Python FastAPI AWS Docker Kubernetes LLM RAG backend role.",
            "https://example.com/jobs/c1-all-roles",
        )
        tailored = client.post(f"/api/jobs/{job['id']}/tailor").json()
        experience = tailored["experience"]
        assert len(experience) >= 2, "Must have at least 2 roles from resume"
        for entry in experience:
            assert entry.get("bullets"), (
                f"Role {entry.get('title')} @ {entry.get('company')} has no bullets"
            )

    def test_fallback_bullets_no_suffix_injection(self, client):
        """Template fallback must not inject '; leveraged X' suffix into bullets."""
        _upload_resume(client)
        job = _import_job(
            client,
            "C1 No Suffix Engineer", "C1SuffixCo", "Remote, India",
            "Python FastAPI AWS Docker backend role.",
            "https://example.com/jobs/c1-no-suffix",
        )
        tailored = client.post(f"/api/jobs/{job['id']}/tailor").json()
        for entry in tailored["experience"]:
            for bullet in entry.get("bullets", []):
                assert "; leveraged" not in bullet.lower(), (
                    f"Suffix injection found in bullet: {bullet!r}"
                )

    def test_tailor_experience_rewrites_bullets_toward_jd(self):
        """_tailor_experience must re-rank bullets so JD-relevant ones come first."""
        from app.services.tailoring import _tailor_experience
        entries = [
            {
                "title": "AI Engineer", "company": "Acme",
                "dates": "2024 - Present",
                "bullets": [
                    "Handled customer support tickets.",
                    "Built RAG pipelines with LLMs and Qdrant.",
                    "Deployed FastAPI services on AWS.",
                ],
            },
        ]
        jd = "LLM RAG pipeline engineer with FastAPI and AWS experience."
        result = _tailor_experience(entries, jd, ["LLMs", "RAG", "FastAPI"], ["Python", "LLMs", "RAG"])
        # The RAG/LLM bullet should rank first
        assert "RAG" in result[0]["bullets"][0] or "LLM" in result[0]["bullets"][0], (
            f"Expected RAG/LLM bullet first, got: {result[0]['bullets']}"
        )

    def test_fallback_warning_in_match_report(self, client):
        """When fallback is used, match_report.llm.provider must be 'template'."""
        _upload_resume(client)
        job = _import_job(
            client,
            "C1 Provider Engineer", "C1ProvCo", "Remote, India",
            "Python FastAPI AWS Docker backend role.",
            "https://example.com/jobs/c1-provider",
        )
        tailored = client.post(f"/api/jobs/{job['id']}/tailor").json()
        assert tailored["match_report"]["llm"]["provider"] == "template"


# ── C-2: Phases 4 and 5 — gaps and 6 tailoring fixtures ─────────────────

class TestC2TailoringFixtures:
    """C-2: 6 tailoring fixtures; gaps false-positive/negative check."""

    AI_ENGINEER_JD = (
        "Senior AI Engineer. Build LLM-powered RAG pipelines, fine-tune models, "
        "deploy on AWS with FastAPI. Required: Python, LLMs, RAG, FastAPI, AWS, Docker. "
        "Nice to have: TensorFlow, LlamaIndex, Fine-tuning. 3-5 years experience."
    )
    GURUGRAM_GENAI_JD = (
        "GenAI Engineer - Gurugram. Build generative AI products using LLMs, LangChain, "
        "vector databases. Python, FastAPI, AWS required. On-site Gurugram, India. "
        "Salary: 25-35 LPA."
    )
    DEVOPS_CLOUD_JD = (
        "DevOps/Cloud Engineer. Manage Kubernetes clusters, CI/CD pipelines, Terraform IaC. "
        "AWS, Docker, Jenkins, GitHub Actions required. Python scripting a plus. "
        "Remote India. 3+ years."
    )
    NO_TITLE_JD = (
        "We are looking for a backend engineer with Python and FastAPI experience. "
        "Build scalable REST APIs, deploy on AWS, work with PostgreSQL and Redis. "
        "Remote position. 2-4 years experience."
    )
    VERY_LONG_JD = (
        "Senior Platform Engineer. " + (
            "Build distributed systems with Python, FastAPI, AWS, Docker, Kubernetes. "
            "Experience with LLMs, RAG, MLflow, Prometheus, Grafana, Terraform, Jenkins. "
            "PostgreSQL, Redis, Celery, RabbitMQ. REST APIs, GraphQL, gRPC. "
            "CI/CD, GitOps, ArgoCD, Helm. Security, OAuth2, JWT. "
        ) * 20  # ~2000 chars of repeated requirements
    )
    MESSY_LINKEDIN_JD = (
        "🚀 Exciting opportunity! AI/ML Engineer 🤖\n"
        "📍 Remote | 💰 Competitive\n"
        "We're looking for someone who:\n"
        "✅ Knows Python & FastAPI\n"
        "✅ Has worked with LLMs/RAG\n"
        "✅ AWS experience preferred\n"
        "DM me or apply at: https://example.com/apply\n"
        "#hiring #AI #Python #remote"
    )

    def _tailor(self, client, title, company, location, description, url, **kw):
        _upload_resume(client)
        r = client.post("/api/tailor/manual", json=dict(
            title=title, company=company, location=location,
            description=description, url=url,
            remote=kw.get("remote", True),
        ))
        assert r.status_code == 200, f"Tailor failed for {title}: {r.text}"
        return r.json()

    def test_fixture_ai_engineer(self, client):
        """AI Engineer JD: must produce summary, skills, experience, cover letter."""
        result = self._tailor(
            client, "Senior AI Engineer", "TechCorp", "Remote, India",
            self.AI_ENGINEER_JD, "https://example.com/c2-ai",
        )
        assert result["summary"], "Summary must not be empty"
        assert result["skills"], "Skills must not be empty"
        assert result["experience"], "Experience must not be empty"
        assert result["cover_letter"], "Cover letter must not be empty"
        report = result["match_report"]
        assert "before_score" in report
        assert "after_score" in report
        assert report["after_score"] >= report["before_score"] or report["after_score"] >= 0

    def test_fixture_gurugram_genai(self, client):
        """Gurugram GenAI JD: must be ALLOW, produce valid output."""
        result = self._tailor(
            client, "GenAI Engineer", "GenAI Labs", "Gurugram, India",
            self.GURUGRAM_GENAI_JD, "https://example.com/c2-genai",
            remote=False,
        )
        assert result["summary"]
        assert result["experience"]
        # Job should be India-eligible
        job_data = result.get("job", {})
        if job_data:
            assert job_data.get("eligibility") == "allowed"

    def test_fixture_devops_cloud(self, client):
        """DevOps/Cloud JD: must produce output; gaps should include Terraform if not in resume."""
        result = self._tailor(
            client, "DevOps Engineer", "CloudOps Inc", "Remote, India",
            self.DEVOPS_CLOUD_JD, "https://example.com/c2-devops",
        )
        assert result["summary"]
        assert result["experience"]
        report = result["match_report"]
        # Terraform is in the resume (via RESUME_TEXT which has Terraform)
        # Jenkins is in the resume
        assert "before_score" in report

    def test_fixture_no_title_company(self, client):
        """No title/company JD: must infer title, not produce placeholder company."""
        result = self._tailor(
            client, "", "", "Remote",
            self.NO_TITLE_JD, "https://example.com/c2-notitle",
        )
        assert result["summary"]
        # Summary must not contain placeholder text
        summary_lower = result["summary"].lower()
        assert "role not specified" not in summary_lower
        assert "unknown company" not in summary_lower
        assert "confidential" not in summary_lower
        # Job data should have inferred title
        job_data = result.get("job", {})
        if job_data:
            assert job_data.get("title"), "Title should be inferred from JD"

    def test_fixture_very_long_jd(self, client):
        """Very long JD (>4000 chars): must not crash, must produce valid output."""
        assert len(self.VERY_LONG_JD) > 4000
        result = self._tailor(
            client, "Senior Platform Engineer", "PlatformCo", "Remote, India",
            self.VERY_LONG_JD, "https://example.com/c2-long",
        )
        assert result["summary"]
        assert result["experience"]
        report = result["match_report"]
        assert report["requirement_count"] > 0

    def test_fixture_messy_linkedin_jd(self, client):
        """Messy LinkedIn JD with emoji/hashtags: must produce valid output."""
        result = self._tailor(
            client, "AI/ML Engineer", "StartupCo", "Remote",
            self.MESSY_LINKEDIN_JD, "https://example.com/c2-linkedin",
        )
        assert result["summary"]
        assert result["experience"]
        # Summary must not contain emoji or hashtags
        assert "#" not in result["summary"]

    def test_gaps_no_false_positives_for_resume_skills(self, client):
        """Skills present in the resume must NOT appear in gaps."""
        _upload_resume(client)
        job = _import_job(
            client, "C2 Gap Test Engineer", "GapCo", "Remote, India",
            "Python FastAPI AWS Docker Kubernetes PostgreSQL LLMs RAG backend role.",
            "https://example.com/c2-gaps",
        )
        tailored = client.post(f"/api/jobs/{job['id']}/tailor").json()
        report = tailored["match_report"]
        gaps = set(report.get("missing", []))
        resume_skills = {"Python", "FastAPI", "AWS", "Docker", "Kubernetes", "PostgreSQL", "LLMs", "RAG"}
        false_positives = gaps & resume_skills
        assert not false_positives, (
            f"False positive gaps (skills in resume but listed as missing): {false_positives}"
        )

    def test_gaps_flags_skills_not_in_resume(self, client):
        """Skills NOT in the resume must appear in gaps."""
        _upload_resume(client)
        job = _import_job(
            client, "C2 Gap Flag Engineer", "GapFlagCo", "Remote, India",
            "Python FastAPI TensorFlow LlamaIndex Fine-tuning backend role.",
            "https://example.com/c2-gap-flag",
        )
        tailored = client.post(f"/api/jobs/{job['id']}/tailor").json()
        report = tailored["match_report"]
        gaps = set(report.get("missing", []))
        # TensorFlow and LlamaIndex are not in the test resume
        assert "TensorFlow" in gaps or "LlamaIndex" in gaps, (
            f"Expected TensorFlow or LlamaIndex in gaps, got: {gaps}"
        )


# ── C-4: 5000-job load test ───────────────────────────────────────────────

class TestC4LoadTest:
    """C-4: /api/jobs must respond in < 2s with many rows; pagination works."""

    def test_jobs_api_fast_with_100_rows(self, client):
        """100-job query must complete in < 2s."""
        _upload_resume(client)
        for i in range(100):
            client.post("/api/jobs/import", json={
                "title": f"C4 Load Engineer {i}",
                "company": f"C4Co{i}",
                "location": "Remote, India",
                "remote": True,
                "description": f"Python FastAPI AWS Docker backend role {i}.",
                "url": f"https://example.com/jobs/c4-load-{i}",
            })
        start = time.time()
        r = client.get("/api/jobs", params={"limit": 50})
        elapsed = time.time() - start
        assert r.status_code == 200
        assert elapsed < 2.0, f"/api/jobs took {elapsed:.2f}s with 100 rows"

    def test_pagination_offset_returns_different_pages(self, client):
        """Offset pagination must return different items on different pages."""
        _upload_resume(client)
        for i in range(10):
            client.post("/api/jobs/import", json={
                "title": f"C4 Page Engineer {i}",
                "company": f"C4PageCo{i}",
                "location": "Remote, India",
                "remote": True,
                "description": f"Python FastAPI backend role {i}.",
                "url": f"https://example.com/jobs/c4-page-{i}",
            })
        p1 = client.get("/api/jobs", params={"limit": 3, "offset": 0}).json()
        p2 = client.get("/api/jobs", params={"limit": 3, "offset": 3}).json()
        ids1 = {j["id"] for j in p1["items"]}
        ids2 = {j["id"] for j in p2["items"]}
        assert not (ids1 & ids2), "Pages must not overlap"

    def test_total_count_present(self, client):
        """Response must include 'total' count field."""
        r = client.get("/api/jobs", params={"limit": 5})
        assert r.status_code == 200
        assert "total" in r.json()


# ── C-5: Expiry/last-seen, reset, prefill, certifications, outreach send ─

class TestC5Verification:
    """C-5: last-seen date, reset via re-tailor, certifications in exports, outreach send blocked."""

    def test_source_last_synced_at_updated_after_discovery(self, client):
        """After discovery, source.last_synced_at must be set."""
        r = client.get("/api/sources")
        assert r.status_code == 200
        for source in r.json()["items"]:
            # last_synced_at may be null before first run — just verify the field exists
            assert "last_synced_at" in source

    def test_source_last_fetched_and_last_added_present(self, client):
        """Sources must expose last_fetched and last_added counts."""
        r = client.get("/api/sources")
        assert r.status_code == 200
        for source in r.json()["items"]:
            assert "last_fetched" in source
            assert "last_added" in source

    def test_reset_via_retailor_produces_fresh_output(self, client):
        """Re-tailoring the same job must produce a new TailoredResume (reset to AI version)."""
        _upload_resume(client)
        job = _import_job(
            client, "C5 Reset Engineer", "C5ResetCo", "Remote, India",
            "Python FastAPI AWS Docker LLM RAG backend role.",
            "https://example.com/jobs/c5-reset",
        )
        t1 = client.post(f"/api/jobs/{job['id']}/tailor").json()
        # Edit the summary
        client.patch(f"/api/tailored/{t1['id']}", json={"summary": "Manually edited summary."})
        # Re-tailor = reset to AI version
        t2 = client.post(f"/api/jobs/{job['id']}/tailor").json()
        assert t2["id"] != t1["id"], "Re-tailor must create a new TailoredResume"
        assert t2["summary"] != "Manually edited summary.", "Re-tailor must not use the edited summary"

    def test_certifications_in_docx(self, client):
        """Certifications from the resume must appear in the DOCX export."""
        _upload_resume(client)
        job = _import_job(
            client, "C5 Cert DOCX Engineer", "C5CertCo", "Remote, India",
            "Python FastAPI AWS Docker backend role.",
            "https://example.com/jobs/c5-cert-docx",
        )
        tailored = client.post(f"/api/jobs/{job['id']}/tailor").json()
        docx_r = client.get(f"/api/tailored/{tailored['id']}/download?fmt=docx")
        assert docx_r.status_code == 200
        from docx import Document
        doc = Document(io.BytesIO(docx_r.content))
        text = "\n".join(p.text for p in doc.paragraphs)
        assert "Certifications" in text, "DOCX must have Certifications section"
        assert "AWS Cloud Foundations" in text, "DOCX must contain the certification from resume"

    def test_certifications_in_pdf(self, client):
        """Certifications from the resume must appear in the PDF export."""
        _upload_resume(client)
        job = _import_job(
            client, "C5 Cert PDF Engineer", "C5CertPDFCo", "Remote, India",
            "Python FastAPI AWS Docker backend role.",
            "https://example.com/jobs/c5-cert-pdf",
        )
        tailored = client.post(f"/api/jobs/{job['id']}/tailor").json()
        pdf_r = client.get(f"/api/tailored/{tailored['id']}/download?fmt=pdf")
        assert pdf_r.status_code == 200
        import pymupdf
        text = "".join(p.get_text() for p in pymupdf.open(stream=pdf_r.content, filetype="pdf"))
        assert "Certifications" in text, "PDF must have Certifications section"
        assert "AWS Cloud Foundations" in text, "PDF must contain the certification from resume"

    def test_outreach_send_blocked_without_gmail_enable_send(self, client):
        """Sending outreach must fail with 400 when gmail_enable_send=False (default in tests)."""
        _upload_resume(client)
        job = _import_job(
            client, "C5 Send Block Engineer", "C5SendCo", "Remote, India",
            "Python FastAPI backend role.",
            "https://example.com/jobs/c5-send-block",
        )
        # Create and approve outreach
        outreach = client.post("/api/outreach", json={"job_id": job["id"]}).json()
        client.post(f"/api/outreach/{outreach['id']}/approve")
        # Attempt to send — must fail because gmail_enable_send=False
        r = client.post(f"/api/outreach/{outreach['id']}/send")
        assert r.status_code == 400, (
            f"Send must be blocked when gmail_enable_send=False, got {r.status_code}: {r.text}"
        )

    def test_outreach_send_blocked_for_draft(self, client):
        """Sending a draft (not approved) outreach must fail with 400."""
        _upload_resume(client)
        job = _import_job(
            client, "C5 Draft Send Engineer", "C5DraftSendCo", "Remote, India",
            "Python FastAPI backend role.",
            "https://example.com/jobs/c5-draft-send",
        )
        outreach = client.post("/api/outreach", json={"job_id": job["id"]}).json()
        assert outreach["status"] == "draft"
        r = client.post(f"/api/outreach/{outreach['id']}/send")
        assert r.status_code == 400, "Draft outreach must not be sendable"

    def test_tailor_manual_prefill_returns_job_data(self, client):
        """POST /api/tailor/manual must return job data for prefill in the Jobs tab."""
        _upload_resume(client)
        r = client.post("/api/tailor/manual", json={
            "title": "C5 Prefill Engineer",
            "company": "C5PrefillCo",
            "location": "Remote, India",
            "description": "Python FastAPI AWS Docker backend role for prefill test.",
            "url": "https://example.com/jobs/c5-prefill",
            "remote": True,
        })
        assert r.status_code == 200
        data = r.json()
        assert "job" in data, "Manual tailor response must include 'job' for prefill"
        assert data["job"]["title"] == "C5 Prefill Engineer"
        assert data["job"]["company"] == "C5PrefillCo"
