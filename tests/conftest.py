from __future__ import annotations

import os
from pathlib import Path

# Use a temp-dir DB so CI (GitHub Actions) always has write access.
# Locally we still use data/test_jobhunter.db so the behaviour is the same.
_CI = os.environ.get("CI", "").lower() in {"true", "1", "yes"}

if _CI:
    import tempfile
    _tmp = tempfile.mkdtemp()
    TEST_DB = Path(_tmp) / "test_jobhunter.db"
else:
    TEST_DB = Path("data/test_jobhunter.db")
    if TEST_DB.exists():
        try:
            TEST_DB.unlink()
        except PermissionError:
            pass  # another process holds it

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_PRIMARY_PROVIDER"] = ""
os.environ["LLM_SECONDARY_PROVIDER"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["LLM_CACHE_ENABLED"] = "false"
os.environ["DEFAULT_USER_NAME"] = "Test Candidate"
os.environ["DEFAULT_USER_EMAIL"] = "test@example.com"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


RESUME_TEXT = """Test Candidate
AI Engineer | Python Backend | AWS | DevOps | MLOps
+91-9000000000 | test@example.com | Noida, India | linkedin.com/in/test | github.com/test

PROFESSIONAL SUMMARY
AI Engineer with 4 years of production experience building Python backend and ML systems.

CORE TECHNICAL SKILLS
AI / GenAI: LLMs, RAG, Qdrant, LangChain
Python & Backend: Python, FastAPI, Django REST Framework, SQLAlchemy, Celery, REST APIs
AWS Cloud: EC2, S3, Lambda, EKS, RDS, CloudWatch, SageMaker
DevOps & CI/CD: Docker, Kubernetes, Jenkins, GitHub Actions, Terraform
Databases: PostgreSQL, Redis
MLOps: MLflow, Model Deployment, Model Monitoring

WORK EXPERIENCE
Artificial Intelligence Engineer
May 2024 - Present
Acme AI | Full-time | Noida
- Built RAG pipelines with LLMs and Qdrant.
- Deployed FastAPI services on AWS.

Software Engineer
Jan 2022 - Apr 2024
Beta Corp | Full-time | Remote
- Built REST APIs with Python and FastAPI.
- Set up CI/CD with Docker and GitHub Actions.

KEY PROJECTS
fastapi-aws-platform | FastAPI - PostgreSQL - AWS - Docker
github.com/test/fastapi-aws-platform
- Async FastAPI service with SQLAlchemy and Redis caching.

EDUCATION
M.Tech - Computer Science
2020 - 2022
Test University

CERTIFICATIONS
AWS Cloud Foundations
"""
