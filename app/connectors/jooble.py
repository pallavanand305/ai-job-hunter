from __future__ import annotations

from app.config import settings
from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import is_remote, parse_datetime, parse_experience, parse_salary, strip_html


class JoobleConnector(BaseConnector):
    name = "jooble"
    display_name = "Jooble"
    requires_config = True
    notes = "Free Jooble API. Set JOOBLE_API_KEY; keywords/location configurable."

    @classmethod
    def is_configured(cls, config: dict | None = None) -> bool:
        cfg = config or {}
        return bool(cfg.get("api_key") or settings.jooble_api_key)

    def fetch(self) -> list[NormalizedJob]:
        cfg = self.config
        api_key = cfg.get("api_key") or settings.jooble_api_key
        if not api_key:
            return []
        payload = {
            "keywords": cfg.get("keywords") or "python developer",
            "location": cfg.get("location") or settings.default_user_location,
        }
        with self._client() as client:
            response = client.post(f"https://jooble.org/api/{api_key}", json=payload)
            if response.status_code != 200:
                return []
            try:
                data = response.json()
            except ValueError:
                return []
        jobs: list[NormalizedJob] = []
        for item in data.get("jobs", []):
            description = strip_html(item.get("snippet", ""))
            location = item.get("location", "") or ""
            salary_min, salary_max, currency = parse_salary(item.get("salary", ""))
            exp_min, exp_max = parse_experience(description)
            jobs.append(
                NormalizedJob(
                    title=item.get("title", ""),
                    company=item.get("company", "") or item.get("source", ""),
                    description=description,
                    location=location,
                    url=item.get("link", ""),
                    remote=is_remote(location, description),
                    salary_min=salary_min,
                    salary_max=salary_max,
                    currency=currency,
                    experience_min=exp_min,
                    experience_max=exp_max,
                    posted_at=parse_datetime(item.get("updated")),
                    external_id=str(item.get("id", "") or item.get("link", "")),
                    source_name=self.name,
                    raw={"type": item.get("type", "")},
                )
            )
        return jobs
