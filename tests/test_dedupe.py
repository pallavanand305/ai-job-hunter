from app.services.dedupe import job_hash, normalize_url


def test_same_job_same_hash():
    a = job_hash("Senior Python Engineer", "Acme Inc", "Remote")
    b = job_hash("senior python engineer", "ACME INC.", "remote")
    assert a == b


def test_different_jobs_differ():
    a = job_hash("Backend Engineer", "Acme", "Noida")
    b = job_hash("Frontend Engineer", "Acme", "Noida")
    assert a != b


def test_normalize_url_strips_trailing_slash():
    assert normalize_url("https://Example.com/jobs/1/") == normalize_url("https://example.com/jobs/1")
