from __future__ import annotations

import pytest

from app.config import settings
from app.llm.client import LLMClient
from app.llm.providers import ProviderError
from app.services.tailoring import (
    _enhance_verified_coverage,
    _group_skills,
    _match_metrics,
    _merge_experience,
    _tailor_experience,
    chronological_entries,
    filter_allowed_skills,
    validate_immutable_fields,
)
from tests.conftest import RESUME_TEXT


def test_chronological_entries_keeps_every_role_newest_first():
    entries = [
        {"company": "Old Corp", "dates": "Aug 2021 - Sep 2023"},
        {"company": "New Corp", "dates": "May 2026 - Present"},
        {"company": "Middle Corp", "dates": "May 2025 \u2013 Oct 2025"},
        {"company": "Recent Corp", "dates": "Nov 2025 - Feb 2026"},
    ]
    ordered = chronological_entries(entries)
    assert [entry["company"] for entry in ordered] == [
        "New Corp",
        "Recent Corp",
        "Middle Corp",
        "Old Corp",
    ]
    assert len(ordered) == len(entries)


def test_chronological_entries_falls_back_to_resume_order_without_dates():
    entries = [{"company": "First"}, {"company": "Second"}, {"company": "Third"}]
    assert [entry["company"] for entry in chronological_entries(entries)] == [
        "First",
        "Second",
        "Third",
    ]


def test_tailor_experience_keeps_every_role_and_no_suffix():
    entries = [
        {
            "title": "Backend Engineer",
            "company": "Acme",
            "dates": "May 2024 - Present",
            "tech": "Python, Kubernetes",
            "bullets": ["Built internal APIs.", "Improved service reliability."],
        },
        {
            "title": "Support Engineer",
            "company": "Old Co",
            "dates": "Jan 2022 - Apr 2024",
            "tech": "",
            "bullets": ["Handled customer tickets."],
        },
    ]
    output = _tailor_experience(
        entries,
        "Kubernetes and Python backend platform role",
        ["Python", "Kubernetes"],
        ["Python", "Kubernetes", "Docker"],
    )
    assert len(output) == 2
    assert output[0]["title"] == "Backend Engineer"
    assert output[0]["company"] == "Acme"
    assert output[0]["dates"] == "May 2024 - Present"
    assert len(output[0]["bullets"]) >= 1
    assert "leveraged" not in " ".join(output[0]["bullets"]).lower()
    assert output[1]["bullets"] == ["Handled customer tickets."]


def test_merge_experience_applies_llm_bullets_without_changing_real_metadata():
    original = [
        {"title": "Backend Engineer", "company": "Acme", "dates": "2024 - Present", "bullets": ["Old"]},
        {"title": "Engineer", "company": "Beta", "dates": "2022 - 2024", "bullets": ["Keep"]},
    ]
    llm = [
        {"title": "Senior Backend Engineer", "company": "Acme", "dates": "Wrong", "bullets": ["Tailored JD bullet"]},
    ]
    output = _merge_experience(original, llm)
    assert len(output) == 2
    assert output[0]["title"] == "Backend Engineer"
    assert output[0]["dates"] == "2024 - Present"
    assert output[0]["bullets"] == ["Tailored JD bullet"]
    assert output[1]["bullets"] == ["Keep"]


def test_group_skills_puts_jd_priority_first():
    groups = _group_skills(
        ["LLMs", "Python", "Kubernetes"],
        "Kubernetes Python platform role",
        priority=["Kubernetes"],
    )
    assert "Kubernetes" in groups[0]["items"]


def test_filter_allowed_skills_strips_unknown_skills():
    assert filter_allowed_skills(
        ["Python", "Kubernetes", "InventedSkill", "python"],
        ["Python", "Kubernetes", "Docker"],
    ) == ["Python", "Kubernetes"]


def test_validate_immutable_fields_overwrites_llm_metadata_and_warns():
    profile = {
        "experience": [
            {
                "title": "Backend Engineer",
                "company": "Acme",
                "dates": "May 2024 - Present",
                "location": "Noida",
                "bullets": ["Built APIs."],
            }
        ]
    }
    candidates = [
        {
            "title": "Senior Architect",
            "company": "Acme",
            "dates": "2020 - 2026",
            "location": "Remote",
            "bullets": ["Designed reliable APIs."],
        }
    ]
    sanitized, warnings = validate_immutable_fields(profile, candidates)
    assert sanitized[0]["title"] == "Backend Engineer"
    assert sanitized[0]["dates"] == "May 2024 - Present"
    assert sanitized[0]["location"] == "Noida"
    assert sanitized[0]["bullets"] == ["Designed reliable APIs."]
    assert any("title" in warning for warning in warnings)
    assert any("dates" in warning for warning in warnings)


def test_llm_reports_template_fallback_when_keys_missing(monkeypatch):
    monkeypatch.setattr(settings, "llm_primary_provider", "gemini")
    monkeypatch.setattr(settings, "llm_primary_model", "gemini-test-model")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "llm_secondary_provider", "groq")
    monkeypatch.setattr(settings, "llm_secondary_model", "groq-test-model")
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "llm_allow_ollama", False)
    client = LLMClient()
    info = client.info()
    assert info["fallback"] is True
    assert info["provider"] == "template"
    assert "API key is not configured" in info["reason"]
    assert client.complete_json("system", "prompt", default={"fallback": True}) == {"fallback": True}

def test_match_metrics_flags_verified_90_target_and_unverified_gaps():
    relevant = ["Python", "FastAPI", "AWS", "Kubernetes", "Docker", "PostgreSQL", "MLOps"]
    report = _match_metrics(relevant, RESUME_TEXT, RESUME_TEXT)
    assert report["target_score"] == 90
    assert report["target_met"] is True
    assert report["after_score"] >= 90
    assert report["unverified_gaps"] == []

    nurse = ["Python", "Registered Nurse License", "Patient Care", "Electronic Health Records"]
    report = _match_metrics(nurse, RESUME_TEXT, RESUME_TEXT)
    assert report["target_met"] is False
    assert report["after_score"] < 90
    assert "Registered Nurse License" in report["unverified_gaps"]
    assert any("Do not claim without evidence" in action for action in report["gap_actions"])


def test_enhancement_only_adds_resume_backed_keywords():
    terms = ["Python", "Registered Nurse License", "Patient Care"]
    summary, added = _enhance_verified_coverage("", terms, RESUME_TEXT, "", 90)
    assert "Python" in added
    assert "Registered Nurse License" not in added
    assert "Patient Care" not in added
    assert "Registered Nurse License" not in summary

def test_retry_after_is_capped_to_keep_requests_responsive(monkeypatch):
    class RateLimitedProvider:
        name = "test"
        model = "test-model"

        def complete(self, system, prompt, *, json_mode, temperature):
            raise ProviderError("rate limited", status_code=429, retryable=True, retry_after=49.0)

    waits: list[float] = []
    monkeypatch.setattr(settings, "llm_max_retries", 1)
    monkeypatch.setattr(settings, "llm_max_retry_wait_seconds", 5.0)
    monkeypatch.setattr("app.llm.client.time.sleep", waits.append)
    client = object.__new__(LLMClient)
    client.rate_limiter = type("NoLimit", (), {"acquire": lambda self: None})()
    client.last_error = ""
    with pytest.raises(ProviderError):
        client._call(
            RateLimitedProvider(),
            "system",
            "prompt",
            json_mode=True,
            temperature=0.0,
        )
    assert waits == [5.0]


def test_before_score_below_100_when_jd_has_unmatched_skills():
    """The untailored master must be able to score below 100% when the JD has skills the candidate lacks."""
    jd_terms = ["Python", "FastAPI", "AWS", "TensorFlow", "LlamaIndex", "Fine-tuning"]
    report = _match_metrics(jd_terms, RESUME_TEXT, RESUME_TEXT)
    assert report["before_score"] < 100
    assert report["after_score"] < 100
    assert "TensorFlow" in report["missing"]
    assert "LlamaIndex" in report["missing"]
    assert "Fine-tuning" in report["missing"]
    assert report["target_met"] is False


def test_preferred_skills_lack_count_as_gaps():
    """Skills not in the master resume must count as gaps, not get partial credit."""
    from app.services.tailoring import _term_score
    from app.services.lexicon import find_skills, norm
    from app.services.ats import tokenize

    text_norm = norm(RESUME_TEXT)
    text_tokens = set(tokenize(RESUME_TEXT))
    text_skills = set(find_skills(RESUME_TEXT))

    # TensorFlow is a canonical skill not in the resume
    assert _term_score("TensorFlow", text_norm, text_tokens, text_skills) == 0.0
    # LlamaIndex is a canonical skill not in the resume
    assert _term_score("LlamaIndex", text_norm, text_tokens, text_skills) == 0.0
    # Fine-tuning is a canonical skill not in the resume
    assert _term_score("Fine-tuning", text_norm, text_tokens, text_skills) == 0.0
    # Python IS in the resume
    assert _term_score("Python", text_norm, text_tokens, text_skills) == 1.0


def test_group_skills_limited_to_six_categories():
    """Skills must be limited to about 6 JD-relevant categories."""
    skills = [
        "Python", "FastAPI", "AWS", "Docker", "Kubernetes", "PostgreSQL",
        "LLMs", "RAG", "MLflow", "Jenkins", "Terraform", "Redis",
        "React", "TypeScript", "GraphQL", "Prometheus",
    ]
    groups = _group_skills(skills, "Python FastAPI AWS Docker Kubernetes LLM RAG", priority=["Python", "LLMs"])
    assert len(groups) <= 6


def test_sanitize_summary_strips_headline_keyword_string():
    """The summary must not repeat the headline keyword string."""
    from app.services.tailoring import _sanitize_summary
    headline = "AI Engineer | Python Backend | AWS | DevOps | MLOps"
    stuffed = "AI Engineer | Python Backend | AWS | DevOps | MLOps with 4+ years of experience."
    result = _sanitize_summary(stuffed, headline)
    assert "AI Engineer | Python Backend | AWS | DevOps | MLOps" not in result
    assert len(result) > 20


def test_fallback_summary_omits_unknown_company():
    """When company is unknown, the summary should not include 'at Confidential'."""
    from app.models import Job
    from app.services.tailoring import _fallback_summary
    job = Job(id=1, title="AI Engineer", company="", description="Build LLM systems.", dedupe_hash="x")
    profile = {"headline": "AI Engineer", "years_experience": 4, "skills": ["Python", "LLMs"]}
    summary = _fallback_summary(profile, job, ["Python", "LLMs"])
    assert "at " not in summary
    assert "Confidential" not in summary
    assert "Unknown" not in summary


def test_fallback_summary_infers_title_from_jd():
    """When title is empty, the summary should infer the title from the JD."""
    from app.models import Job
    from app.services.tailoring import _fallback_summary
    job = Job(id=1, title="", company="Acme", description="Job Title: Senior GenAI Engineer\nBuild LLM systems.", dedupe_hash="x")
    profile = {"headline": "AI Engineer", "years_experience": 4, "skills": ["Python", "LLMs"]}
    summary = _fallback_summary(profile, job, ["Python", "LLMs"])
    assert "GenAI Engineer" in summary
    assert "at Acme" in summary


def test_rank_entries_prefers_graphrag_for_rag_jds():
    """GraphRAG project should be selected for LLM/RAG/agent/vector-DB JDs."""
    from app.services.tailoring import rank_entries
    entries = [
        {"name": "FastAPI Platform", "tech": "FastAPI PostgreSQL AWS Docker", "bullets": ["Built async API."]},
        {"name": "GraphRAG System", "tech": "LangChain Qdrant Neo4j", "bullets": ["Built knowledge graph RAG pipeline."]},
        {"name": "CI/CD Pipeline", "tech": "Jenkins Docker Terraform", "bullets": ["Set up pipelines."]},
    ]
    jd = "We need an LLM engineer with RAG, agents, vector databases and LangChain experience."
    ranked = rank_entries(entries, jd, 2)
    assert ranked[0]["name"] == "GraphRAG System"
