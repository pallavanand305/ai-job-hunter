from __future__ import annotations

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import parse_datetime, parse_experience, is_remote, strip_html


class ArbeitnowConnector(BaseConnector):
    name = "arbeitnow"
    display_name = "Arbeitnow"
    notes = "Free job board API (EU-heavy, includes remote roles)."

    def fetch(self) -> list[NormalizedJob]:
        jobs: list[NormalizedJob] = []
        with self._client() as client:
            response = client.get("https://www.arbeitnow.com/api/job-board-api")
            if response.status_code != 200:
                return []
            for item in response.json().get("data", []):
                description = strip_html(item.get("description", ""))
                location = item.get("location", "")
                exp_min, exp_max = parse_experience(description)
                jobs.append(
                    NormalizedJob(
                        title=item.get("title", ""),
                        company=item.get("company_name", ""),
                        description=description,
                        location=location,
                        url=item.get("url", ""),
                        remote=bool(item.get("remote")) or is_remote(location, description),
                        experience_min=exp_min,
                        experience_max=exp_max,
                        posted_at=parse_datetime(item.get("created_at")),
                        external_id=item.get("slug", ""),
                        source_name=self.name,
                        raw={"tags": item.get("tags", []), "job_types": item.get("job_types", [])},
                    )
                )
        return jobs
