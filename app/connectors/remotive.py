from __future__ import annotations

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import parse_datetime, parse_experience, parse_salary, strip_html


class RemotiveConnector(BaseConnector):
    name = "remotive"
    display_name = "Remotive"
    notes = "Free remote job API. Configure config.search (e.g. python, fastapi, mlops)."

    def fetch(self) -> list[NormalizedJob]:
        search = self.config.get("search", "python")
        limit = int(self.config.get("limit", 60))
        jobs: list[NormalizedJob] = []
        with self._client() as client:
            response = client.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": search, "limit": limit},
            )
            if response.status_code != 200:
                return []
            for item in response.json().get("jobs", []):
                description = strip_html(item.get("description", ""))
                salary_min, salary_max, currency = parse_salary(item.get("salary", ""))
                exp_min, exp_max = parse_experience(description)
                jobs.append(
                    NormalizedJob(
                        title=item.get("title", ""),
                        company=item.get("company_name", ""),
                        description=description,
                        location=item.get("candidate_required_location", "Remote"),
                        url=item.get("url", ""),
                        remote=True,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        currency=currency,
                        experience_min=exp_min,
                        experience_max=exp_max,
                        posted_at=parse_datetime(item.get("publication_date")),
                        external_id=str(item.get("id", "")),
                        source_name=self.name,
                        raw={
                            "tags": item.get("tags", []),
                            "category": item.get("category", ""),
                            "job_type": item.get("job_type", ""),
                        },
                    )
                )
        return jobs
