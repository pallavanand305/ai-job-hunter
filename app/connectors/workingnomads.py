from __future__ import annotations

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import parse_datetime, parse_experience, strip_html


class WorkingNomadsConnector(BaseConnector):
    name = "workingnomads"
    display_name = "Working Nomads"
    notes = "Free public remote-jobs API (no key required)."

    def fetch(self) -> list[NormalizedJob]:
        with self._client() as client:
            response = client.get("https://www.workingnomads.com/api/exposed_jobs/")
            if response.status_code != 200:
                return []
            data = response.json()
        jobs: list[NormalizedJob] = []
        for item in data if isinstance(data, list) else []:
            description = strip_html(item.get("description") or "")
            exp_min, exp_max = parse_experience(description)
            jobs.append(
                NormalizedJob(
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    description=description,
                    location=item.get("location", "") or "Remote",
                    url=item.get("url", ""),
                    remote=True,
                    experience_min=exp_min,
                    experience_max=exp_max,
                    posted_at=parse_datetime(item.get("pub_date")),
                    external_id=str(item.get("url", "")),
                    source_name=self.name,
                    raw={
                        "category": item.get("category_name", ""),
                        "tags": item.get("tags", ""),
                    },
                )
            )
        return jobs
