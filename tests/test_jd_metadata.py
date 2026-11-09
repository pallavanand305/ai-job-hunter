from __future__ import annotations

from app.services.jd_metadata import infer_company, infer_role_title


def test_infer_title_and_company_from_hiring_sentence():
    description = (
        "We are hiring a Staff Platform Engineer to join our team at Acme Labs. "
        "You will build reliable Python services on AWS."
    )
    assert infer_role_title(description) == "Staff Platform Engineer"
    assert infer_company(description) == "Acme Labs"


def test_infer_title_from_explicit_label():
    description = "Job Title: Senior MLOps Engineer\nCompany: Example AI\nPython and Kubernetes required."
    assert infer_role_title(description) == "Senior MLOps Engineer"
    assert infer_company(description) == "Example AI"


def test_infer_title_from_first_meaningful_line():
    description = "GenAI Backend Engineer\n\nAbout us\nWe build LLM products with Python and FastAPI."
    assert infer_role_title(description) == "GenAI Backend Engineer"


def test_infer_helpers_never_return_known_placeholders():
    title = infer_role_title("Python FastAPI AWS Docker backend role")
    company = infer_company("Python FastAPI AWS Docker backend role")
    assert title != "Pasted JD role"
    assert company != "Unknown company"
