from __future__ import annotations

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import is_remote, parse_datetime, parse_experience, strip_html


class TheMuseConnector(BaseConnector):
    name = "themuse"
    display_name = "The Muse"
    notes = "Free public jobs API (no key required)."

    def fetch(self) -> list[NormalizedJob]:
        categories = self.config.get("categories") or ["Software Engineering", "Data Science"]
        pages = int(self.config.get("pages", 3))
        jobs: list[NormalizedJob] = []
        seen: set[str] = set()
        with self._client() as client:
            for category in categories:
                for page in range(1, pages + 1):
                    response = client.get(
                        "https://www.themuse.com/api/public/jobs",
                        params={"page": page, "category": category},
                    )
                    if response.status_code != 200:
                        break
                    results = response.json().get("results", [])
                    if not results:
                        break
                    for item in results:
                        ref = (item.get("refs") or {}).get("landing_page", "")
                        if ref in seen:
                            continue
                        seen.add(ref)
                        description = strip_html(item.get("contents") or "")
                        location = ", ".join(
                            part.get("name", "")
                            for part in item.get("locations") or []
                            if part.get("name")
                        ) or "Remote"
                        exp_min, exp_max = parse_experience(description)
                        jobs.append(
                            NormalizedJob(
                                title=item.get("name", ""),
                                company=(item.get("company") or {}).get("name", ""),
                                description=description,
                                location=location,
                                url=ref,
                                remote=is_remote(location, description),
                                experience_min=exp_min,
                                experience_max=exp_max,
                                posted_at=parse_datetime(item.get("publication_date")),
                                external_id=str(item.get("id", "") or ref),
                                source_name=self.name,
                                raw={
                                    "category": category,
                                    "levels": [level.get("name") for level in item.get("levels") or []],
                                },
                            )
                        )
        return jobs
