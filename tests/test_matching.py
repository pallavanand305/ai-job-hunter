from app.models import Job
from app.services.matching import _location_score, score_job

PROFILE = {
    "headline": "AI Engineer | Python Backend | AWS",
    "summary": "AI engineer with production Python, FastAPI, AWS and MLOps experience.",
    "skills": ["Python", "FastAPI", "AWS", "Docker", "Kubernetes", "PostgreSQL", "LLMs", "RAG"],
    "years_experience": 4,
    "resume_text": "Python FastAPI AWS Docker Kubernetes PostgreSQL LLM RAG backend engineer",
    "preferences": {
        "locations": ["Noida", "Greater Noida", "Delhi", "Gurgaon", "Gurugram", "Pune", "Hyderabad", "Bangalore", "Bengaluru", "Jaipur", "Ahmedabad"],
        "home_country": "India",
        "outside_country_remote_only": True,
        "remote_ok": True,
        "min_salary": 1500000,
        "currency": "INR",
        "exclude_companies": [],
    },
}


def make_job(**overrides) -> Job:
    defaults = dict(
        id=1,
        title="Senior Python Backend Engineer",
        company="Acme",
        location="Remote, India",
        remote=True,
        description="Python FastAPI AWS Docker Kubernetes. Build REST APIs and backend services.",
        salary_min=2000000,
        salary_max=3000000,
        currency="INR",
        experience_min=3,
        experience_max=6,
    )
    defaults.update(overrides)
    return Job(**defaults)


def test_strong_match_scores_high():
    result = score_job(make_job(), PROFILE)
    assert result["score"] >= 70
    assert "Python" in result["matched_skills"]
    assert "Python" not in result["missing_skills"]
    assert result["skill_score"] > 60


def test_weak_match_scores_low():
    job = make_job(
        title="Registered Nurse",
        description="Patient care, clinical triage and hospital operations.",
        salary_min=300000,
        salary_max=400000,
        experience_min=0,
        experience_max=2,
    )
    result = score_job(job, PROFILE)
    assert result["score"] < 50


def test_excluded_company_scores_zero():
    profile = {**PROFILE, "preferences": {**PROFILE["preferences"], "exclude_companies": ["Acme"]}}
    result = score_job(make_job(), profile)
    assert result["score"] == 0


def test_weighted_components_present():
    result = score_job(make_job(), PROFILE)
    for key in ("skill_score", "experience_score", "responsibility_score", "salary_score", "location_score"):
        assert 0 <= result[key] <= 100


def test_location_rules_for_india_and_remote_only_outside():
    profile = PROFILE
    assert _location_score(make_job(location="Noida, India", remote=False), profile) == 1.0
    assert _location_score(make_job(location="Greater Noida, India", remote=False), profile) == 1.0
    assert _location_score(make_job(location="Gurugram, India", remote=False), profile) == 1.0
    assert _location_score(make_job(location="Gurgaon, India", remote=False), profile) == 1.0
    assert _location_score(make_job(location="Bengaluru, India", remote=False), profile) == 1.0
    assert _location_score(make_job(location="Bangalore, India", remote=False), profile) == 1.0
    assert _location_score(make_job(location="Pune, India", remote=False), profile) == 1.0
    assert _location_score(make_job(location="Hyderabad, India", remote=False), profile) == 1.0
    assert _location_score(make_job(location="Jaipur, India", remote=False), profile) == 1.0
    assert _location_score(make_job(location="Ahmedabad, India", remote=False), profile) == 1.0
    assert _location_score(make_job(location="Chennai, India", remote=False), profile) == 0.65
    assert _location_score(make_job(location="Austin, United States", remote=False), profile) == 0.0
    assert _location_score(make_job(location="London, United Kingdom", remote=False), profile) == 0.0
    assert _location_score(make_job(location="Remote, United States", remote=True), profile) == 0.0
    assert _location_score(make_job(location="Remote, India", remote=True), profile) == 1.0
    assert _location_score(make_job(location="Remote - Worldwide", remote=True), profile) == 1.0


def test_outside_india_onsite_ranks_below_india_onsite():
    india = score_job(make_job(location="Noida, India", remote=False), PROFILE)["score"]
    abroad = score_job(make_job(location="London, United Kingdom", remote=False), PROFILE)["score"]
    assert abroad < india


def test_ai_engineer_ranks_above_devops():
    """AI Engineer roles must rank above DevOps roles per target-role order."""
    ai_job = make_job(
        title="Senior AI Engineer",
        description="Build LLM, RAG, Python, FastAPI, AWS, Docker, Kubernetes AI systems.",
    )
    devops_job = make_job(
        title="Senior DevOps Engineer",
        description="Manage Docker, Kubernetes, Terraform, CI/CD, AWS, Python infrastructure.",
    )
    ai_score = score_job(ai_job, PROFILE)["score"]
    devops_score = score_job(devops_job, PROFILE)["score"]
    assert ai_score > devops_score, f"AI Engineer ({ai_score}) should rank above DevOps ({devops_score})"


def test_genai_engineer_ranks_above_devops_and_cloud():
    """GenAI Engineer roles must rank above DevOps/Cloud per target-role order."""
    genai_job = make_job(
        title="GenAI Engineer",
        description="Build LLM, RAG, LangChain, Python, FastAPI, AWS GenAI applications.",
    )
    devops_job = make_job(
        title="DevOps Engineer",
        description="Manage Docker, Kubernetes, Terraform, CI/CD, AWS infrastructure.",
    )
    cloud_job = make_job(
        title="Cloud Engineer",
        description="Manage AWS, EC2, S3, Lambda, RDS, ECS cloud infrastructure.",
    )
    genai_score = score_job(genai_job, PROFILE)["score"]
    devops_score = score_job(devops_job, PROFILE)["score"]
    cloud_score = score_job(cloud_job, PROFILE)["score"]
    assert genai_score > devops_score, f"GenAI ({genai_score}) should rank above DevOps ({devops_score})"
    assert genai_score > cloud_score, f"GenAI ({genai_score}) should rank above Cloud ({cloud_score})"


def test_score_breakdown_includes_role_fit():
    """The score breakdown should include role_fit dimension."""
    result = score_job(make_job(), PROFILE)
    assert "role_fit" in result
    assert 0 <= result["role_fit"] <= 100


def test_us_wfh_is_blocked_for_india_profile():
    """Remote/WFH jobs tied to the US must be blocked for an India-based user."""
    us_wfh_job = make_job(
        title="Remote Python Engineer",
        location="Remote, United States",
        remote=True,
        description="Python FastAPI remote role. Must be US-based.",
    )
    result = score_job(us_wfh_job, PROFILE)
    assert result["location_score"] == 0.0
    assert result["score"] < 30


def test_india_onsite_preferred_cities_score_higher_than_other_india():
    """Noida/Gurgaon/Delhi/Bangalore etc. should score higher than other Indian cities."""
    noida = score_job(make_job(location="Noida, India", remote=False), PROFILE)["score"]
    chennai = score_job(make_job(location="Chennai, India", remote=False), PROFILE)["score"]
    assert noida > chennai


def test_gurgaon_and_gurugram_are_equivalent():
    """Gurgaon must be treated the same as Gurugram for location scoring."""
    gurgaon_score = _location_score(make_job(location="Gurgaon, Haryana, India", remote=False), PROFILE)
    gurugram_score = _location_score(make_job(location="Gurugram, Haryana, India", remote=False), PROFILE)
    assert gurgaon_score == gurugram_score == 1.0


def test_bangalore_and_bengaluru_are_equivalent():
    """Bangalore must be treated the same as Bengaluru."""
    bangalore_score = _location_score(make_job(location="Bangalore, Karnataka, India", remote=False), PROFILE)
    bengaluru_score = _location_score(make_job(location="Bengaluru, Karnataka, India", remote=False), PROFILE)
    assert bangalore_score == bengaluru_score == 1.0
