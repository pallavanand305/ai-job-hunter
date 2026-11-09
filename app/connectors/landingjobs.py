from __future__ import annotations

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import parse_datetime, parse_experience, strip_html


class LandingJobsConnector(BaseConnector):
    name = "landingjobs"
    display_name = "Landing.jobs"
    notes = "Free public tech-jobs API (no key required)."

    def fetch(self) -> list[NormalizedJob]:
        limit = int(self.config.get("limit", 100))
        with self._client() as client:
            response = client.get("https://landing.jobs/api/v1/jobs", params={"limit": limit})
            if response.status_code != 200:
                return []
            data = response.json()
        jobs: list[NormalizedJob] = []
        for item in data if isinstance(data, list) else []:
            url = item.get("url", "")
            company = ""
            if "/at/" in url:
                company = url.split("/at/", 1)[1].split("/", 1)[0].replace("-", " ").title()
            description = strip_html(
                " ".join(
                    str(item.get(key) or "")
                    for key in ("role_description", "main_requirements", "nice_to_have")
                )
            )
            location = ", ".join(
                ", ".join(part for part in (loc.get("city"), loc.get("country_code")) if part)
                for loc in item.get("locations") or []
            ) or "Remote"
            exp_min, exp_max = parse_experience(description)
            jobs.append(
                NormalizedJob(
                    title=item.get("title", ""),
                    company=company,
                    description=description,
                    location=location,
                    url=url,
                    remote=bool(item.get("remote")) or "remote" in location.lower(),
                    salary_min=_as_float(item.get("gross_salary_low")),
                    salary_max=_as_float(item.get("gross_salary_high")),
                    currency=item.get("currency_code", "") or "",
                    experience_min=exp_min,
                    experience_max=exp_max,
                    posted_at=parse_datetime(item.get("published_at") or item.get("created_at")),
                    external_id=str(item.get("id", "") or url),
                    source_name=self.name,
                    raw={"type": item.get("type", "")},
                )
            )
        return jobs


def _as_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
