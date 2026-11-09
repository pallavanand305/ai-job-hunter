from __future__ import annotations

import io

import pytest

from app.services.eligibility import eligibility_for
from tests.conftest import RESUME_TEXT


def _upload_resume(client):
    response = client.post(
        "/api/profile/resume",
        files={"file": ("resume.txt", RESUME_TEXT, "text/plain")},
        data={"variant": "master", "make_master": "true"},
    )
    assert response.status_code == 200, response.text


def test_india_eligibility_filter_and_badge(client):
    blocked_payload = {
        "title": "US Only Platform Engineer",
        "company": "Eligibility Labs",
        "location": "Remote - US only",
        "remote": True,
        "description": "Python FastAPI role. Must be based in the United States.",
        "url": "https://example.com/jobs/eligibility-us-only",
    }
    allowed_payload = {
        "title": "India Remote Platform Engineer",
        "company": "Eligibility Labs",
        "location": "Remote, India",
        "remote": True,
        "description": "Python FastAPI role. Work from anywhere in India.",
        "url": "https://example.com/jobs/eligibility-india",
    }
    blocked = client.post("/api/jobs/import", json=blocked_payload)
    allowed = client.post("/api/jobs/import", json=allowed_payload)
    assert blocked.status_code == 200, blocked.text
    assert allowed.status_code == 200, allowed.text
    assert blocked.json()["eligibility"] == "blocked"
    assert blocked.json()["india_eligible"] is False
    assert allowed.json()["eligibility"] == "allowed"
    assert allowed.json()["india_eligible"] is True

    eligible_rows = client.get("/api/jobs", params={"india_eligible": "true", "limit": 200}).json()["items"]
    ids = {item["id"] for item in eligible_rows}
    assert allowed.json()["id"] in ids
    assert blocked.json()["id"] not in ids

    blocked_rows = client.get("/api/jobs", params={"india_eligible": "false", "limit": 200}).json()["items"]
    blocked_ids = {item["id"] for item in blocked_rows}
    assert blocked.json()["id"] in blocked_ids


def test_manual_jd_infers_missing_title_and_company(client):
    _upload_resume(client)
    payload = {
        "title": "",
        "company": "",
        "location": "Remote, India",
        "description": (
            "Senior AI Platform Engineer\n"
            "Company: Inference Labs\n\n"
            "Build Python FastAPI LLM services with Docker and AWS. Python required."
        ),
        "url": "https://example.com/jobs/inferred",
        "remote": True,
    }
    response = client.post("/api/tailor/manual", json=payload)
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["job"]["title"] == "Senior AI Platform Engineer"
    assert item["job"]["company"] == "Inference Labs"
    assert "Pasted JD role" not in item["job"]["title"]
    assert "Unknown company" not in item["job"]["company"]


def test_editable_tailored_preview_regenerates_exports(client):
    _upload_resume(client)
    payload = {
        "title": "GenAI Backend Engineer",
        "company": "Edit Labs",
        "location": "Remote, India",
        "description": (
            "Python FastAPI AWS Docker LLM RAG backend role. Build APIs and deploy ML services."
        ),
        "url": "https://example.com/jobs/editable",
        "remote": True,
    }
    tailored = client.post("/api/tailor/manual", json=payload).json()
    experience = tailored["experience"]
    original_roles = len(experience)
    experience[0]["bullets"] = ["Edited by test: owned the RAG platform end to end."]
    response = client.patch(
        f"/api/tailored/{tailored['id']}",
        json={
            "summary": "Edited by test summary for the GenAI Backend Engineer role.",
            "cover_letter": "Edited by test cover letter.",
            "experience": experience[:1],
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["summary"].startswith("Edited by test summary")
    assert updated["experience"][0]["bullets"][0].startswith("Edited by test")
    assert len(updated["experience"]) == original_roles
    assert updated["match_report"]["edited"] is True

    pdf = client.get(f"/api/tailored/{tailored['id']}/download?fmt=pdf")
    assert pdf.status_code == 200
    disposition = pdf.headers.get("content-disposition", "")
    assert "Test_Candidate_GenAI_Backend_Engineer_Edit_Labs.pdf" in disposition

    import pymupdf

    text = "".join(page.get_text() for page in pymupdf.open(stream=pdf.content, filetype="pdf"))
    assert "Edited by test summary" in text
    assert "linkedin.com/in/test" in text


def test_sources_expose_fetch_health(client):
    response = client.get("/api/sources")
    assert response.status_code == 200
    item = response.json()["items"][0]
    for key in ("last_status", "last_error", "last_fetched", "last_added"):
        assert key in item


def test_gmail_is_read_only_by_default():
    from app.services import gmail

    assert gmail.SCOPES == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert gmail.status()["read_only"] is True
    with pytest.raises(RuntimeError, match="read-only"):
        gmail.send_email("test@example.com", "Subject", "Body")


def test_apac_remote_is_allowed_for_india():
    """APAC remote roles include India and should be allowed."""
    result = eligibility_for("Remote - APAC", True)
    assert result.status == "allowed"
    assert result.india_eligible is True


def test_gmail_sync_does_not_reprocess_the_same_message(client, monkeypatch):
    from uuid import uuid4

    from app.database import SessionLocal
    from app.services import gmail
    from app.services.profiles import get_or_create_user

    message_id = f"dedupe-{uuid4().hex}"

    class FakeRequest:
        def __init__(self, payload):
            self.payload = payload

        def execute(self):
            return self.payload

    class FakeMessages:
        def list(self, **_kwargs):
            return FakeRequest({"messages": [{"id": message_id}]})

        def get(self, **_kwargs):
            return FakeRequest(
                {
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "jobs@example.com"},
                            {"name": "Subject", "value": "Status update"},
                        ],
                        "body": {"data": ""},
                    }
                }
            )

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    monkeypatch.setattr(gmail, "_service", lambda: FakeService())
    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        first = gmail.sync_inbox(db, user)
        second = gmail.sync_inbox(db, user)
    finally:
        db.close()
    assert first["processed"] == 1
    assert second["processed"] == 0
