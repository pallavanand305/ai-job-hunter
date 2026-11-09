from app.services.ats import ats_score, extract_keywords, missing_keywords
from app.services.lexicon import find_skills
from app.services.text_utils import parse_experience, parse_salary


def test_find_skills_extracts_canonical_names():
    text = "We use Python, FastAPI, postgres, k8s and AWS Lambda."
    skills = find_skills(text)
    assert "Python" in skills
    assert "FastAPI" in skills
    assert "PostgreSQL" in skills
    assert "Kubernetes" in skills
    assert "AWS" in skills


def test_missing_keywords():
    jd = "Senior Python engineer with FastAPI, Kubernetes and Terraform experience."
    missing = missing_keywords(jd, ["Python", "FastAPI"])
    assert "Kubernetes" in missing
    assert "Terraform" in missing
    assert "Python" not in missing


def test_ats_score_range():
    result = ats_score("Python FastAPI AWS Docker", ["Python", "FastAPI"])
    assert 0 <= result["score"] <= 100
    assert set(result["matched"]) == {"Python", "FastAPI"}


def test_extract_keywords_returns_skills_first():
    keywords = extract_keywords("Python FastAPI AWS Python FastAPI LLM RAG pipelines")
    assert {"Python", "FastAPI", "AWS", "LLMs", "RAG"}.issubset(set(keywords))


def test_parse_salary_lpa():
    low, high, currency = parse_salary("12-18 LPA")
    assert currency == "INR"
    assert low == 1_200_000
    assert high == 1_800_000


def test_parse_salary_usd():
    low, high, currency = parse_salary("$120,000 - $160,000")
    assert currency == "USD"
    assert low == 120_000
    assert high == 160_000


def test_parse_experience():
    assert parse_experience("3-5 years of experience") == (3.0, 5.0)
    assert parse_experience("5+ years") == (5.0, None)
