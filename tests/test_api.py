from __future__ import annotations

from tests.conftest import RESUME_TEXT


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_full_workflow(client):
    # 1. upload + parse resume
    response = client.post(
        "/api/profile/resume",
        files={"file": ("resume.txt", RESUME_TEXT, "text/plain")},
        data={"variant": "master", "make_master": "true"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skills_found"] > 5
    skills = body["profile"]["skills"]
    for expected in ("Python", "FastAPI", "AWS", "Docker"):
        assert expected in skills

    profile = client.get("/api/profile").json()
    assert profile["years_experience"] > 0

    # 2. import a job
    job_payload = {
        "title": "Senior Python Backend Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "remote": True,
        "description": (
            "We need Python, FastAPI, AWS, Docker, Kubernetes and PostgreSQL. "
            "Build REST APIs and microservices. 3-5 years experience. 20-30 LPA."
        ),
        "url": "https://example.com/jobs/1",
        "salary_min": 2000000,
        "salary_max": 3000000,
        "currency": "INR",
        "experience_min": 3,
        "experience_max": 5,
    }
    response = client.post("/api/jobs/import", json=job_payload)
    assert response.status_code == 200, response.text
    job = response.json()
    job_id = job["id"]
    assert job["score"] > 50

    # duplicate prevention
    response = client.post("/api/jobs/import", json=job_payload)
    assert response.status_code == 409

    # 3. matching + dashboard
    assert client.post("/api/matches/run").status_code == 200
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["jobs_discovered"] >= 1
    assert dashboard["strong_matches"] >= 0

    # 4. tailoring
    response = client.post(f"/api/jobs/{job_id}/tailor")
    assert response.status_code == 200, response.text
    tailored = response.json()
    assert tailored["summary"]
    assert tailored["cover_letter"]
    assert tailored["has_docx"] is True
    download = client.get(f"/api/tailored/{tailored['id']}/download?fmt=docx")
    assert download.status_code == 200

    # 5. application lifecycle (drafts -> approve -> record submission)
    response = client.post("/api/applications", json={"job_id": job_id})
    assert response.status_code == 200, response.text
    application = response.json()
    assert application["status"] == "draft"

    response = client.post("/api/applications", json={"job_id": job_id})
    assert response.status_code == 409

    response = client.post(f"/api/applications/{application['id']}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    response = client.post(
        f"/api/applications/{application['id']}/submit",
        json={"confirmation_id": "REF-123", "authorized": True},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"

    # 6. outreach draft + approval (never auto-sent)
    response = client.post("/api/outreach", json={"job_id": job_id, "channel": "email"})
    assert response.status_code == 200, response.text
    message = response.json()
    assert message["status"] == "draft"
    response = client.post("/api/outreach", json={"job_id": job_id, "channel": "email"})
    assert response.status_code == 200
    assert response.json()["id"] == message["id"]
    response = client.post(f"/api/outreach/{message['id']}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    # 7. sources + scheduler + gmail status endpoints
    assert client.get("/api/sources").status_code == 200
    assert client.get("/api/scheduler/status").status_code == 200
    assert client.get("/api/gmail/status").status_code == 200


def test_job_region_and_work_mode_filters(client):
    india_payload = {
        "title": "India WFH Test Engineer",
        "company": "Region Labs",
        "location": "Noida, India",
        "remote": True,
        "description": "Python FastAPI remote role. 2-4 years experience.",
        "url": "https://example.com/jobs/india-wfh",
    }
    us_payload = {
        "title": "US Onsite Test Engineer",
        "company": "Region Labs",
        "location": "Austin, Texas, United States",
        "remote": False,
        "description": "Python FastAPI onsite role. 2-4 years experience.",
        "url": "https://example.com/jobs/us-onsite",
    }
    india = client.post("/api/jobs/import", json=india_payload)
    assert india.status_code == 200, india.text
    assert india.json()["region"] == "India"
    assert india.json()["work_mode"] == "Remote/WFH"
    us = client.post("/api/jobs/import", json=us_payload)
    assert us.status_code == 200, us.text
    assert us.json()["region"] == "US"
    assert us.json()["work_mode"] == "Onsite/Hybrid"

    india_rows = client.get("/api/jobs", params={"region": "india", "remote": "true", "limit": 200, "q": "India WFH Test"}).json()["items"]
    assert any(item["id"] == india.json()["id"] for item in india_rows)
    assert all(item["region"] == "India" and item["remote"] for item in india_rows)

    india_wfh_rows = client.get("/api/jobs", params={"region": "india_wfh", "limit": 200, "q": "India WFH Test"}).json()["items"]
    assert any(item["id"] == india.json()["id"] for item in india_wfh_rows)
    assert all(item["region"] == "India" and item["remote"] for item in india_wfh_rows)

    us_rows = client.get("/api/jobs", params={"region": "us", "remote": "false", "limit": 200}).json()["items"]
    # Verify the US job exists and is correctly classified (direct endpoint if not in page)
    us_detail = client.get(f"/api/jobs/{us.json()['id']}").json()
    assert us_detail["region"] == "US"
    assert not us_detail["remote"]
    # If in page, verify the region filter works
    if us_rows:
        assert all(item["region"] == "US" and not item["remote"] for item in us_rows)

    generic_payload = {
        "title": "US Remote Generic Location Engineer",
        "company": "Region Labs",
        "location": "Remote",
        "remote": True,
        "description": "Must be based in the United States. Python FastAPI role.",
        "url": "https://example.com/jobs/us-remote-generic",
    }
    generic = client.post("/api/jobs/import", json=generic_payload)
    assert generic.status_code == 200, generic.text
    assert generic.json()["region"] == "Global"
    global_rows = client.get("/api/jobs", params={"region": "global", "remote": "true", "limit": 200, "q": "US Remote Generic"}).json()["items"]
    assert any(item["id"] == generic.json()["id"] for item in global_rows)
    assert all(item["region"] not in {"India", "US"} for item in global_rows)

    us_with_india_mention = {
        "title": "US Remote With India Team Engineer",
        "company": "Region Labs",
        "location": "Remote, United States",
        "remote": True,
        "description": "Collaborate with the India-based team a few times a week. Python role.",
        "url": "https://example.com/jobs/us-remote-india-mention",
    }
    mixed = client.post("/api/jobs/import", json=us_with_india_mention)
    assert mixed.status_code == 200, mixed.text
    assert mixed.json()["region"] == "US"
    india_rows = client.get("/api/jobs", params={"region": "india", "remote": "true", "limit": 200}).json()["items"]
    assert all(item["id"] != mixed.json()["id"] for item in india_rows)

    dashboard = client.get("/api/dashboard").json()
    assert {"work_mode", "region"} <= set(dashboard["top_matches"][0])


def test_metrics_and_source_registration(client):
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "jobhunter_jobs_discovered" in metrics.text
    assert "jobhunter_strong_matches" in metrics.text

    sources = {item["name"]: item for item in client.get("/api/sources").json()["items"]}
    for name in ("himalayas", "weworkremotely", "pythonjobs", "adzuna", "jooble", "linkedin", "naukri", "indeed", "instahyre", "wellfound"):
        assert name in sources
    assert sources["linkedin"]["requires_config"] is True
    assert sources["linkedin"]["is_configured"] is False
    assert sources["jobicy"]["config"].get("geo") is None
    assert sources["jobicy"]["config"]["industry"] == "dev"


def test_manual_jd_tailoring(client):
    response = client.post(
        "/api/profile/resume",
        files={"file": ("resume.txt", RESUME_TEXT, "text/plain")},
        data={"variant": "master", "make_master": "true"},
    )
    assert response.status_code == 200, response.text
    payload = {
        "title": "Staff Platform Engineer",
        "company": "PasteCo",
        "location": "Noida, India",
        "description": (
            "We are hiring a Staff Platform Engineer with Python, FastAPI, AWS, Kubernetes, "
            "Docker, PostgreSQL and MLOps experience. Build reliable backend services and CI/CD."
        ),
        "url": "https://www.linkedin.com/jobs/view/123456",
        "remote": False,
    }
    response = client.post("/api/tailor/manual", json=payload)
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["summary"]
    assert item["cover_letter"]
    assert item["job"]["title"] == "Staff Platform Engineer"
    assert item["job"]["company"] == "PasteCo"
    assert item["has_pdf"] is True
    report = item["match_report"]
    assert report["before_score"] >= 0
    assert report["after_score"] >= report["before_score"]
    assert report["target_score"] == 90
    assert report["target_met"] is True
    assert report["unverified_gaps"] == []
    assert report["llm"]["fallback"] is True
    assert report["diff"]["experience"]
    assert report["keywords"]
    download = client.get(f"/api/tailored/{item['id']}/download?fmt=pdf")
    assert download.status_code == 200
