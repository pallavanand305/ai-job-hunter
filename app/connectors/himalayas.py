from __future__ import annotations

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import parse_datetime, parse_experience, strip_html


class HimalayasConnector(BaseConnector):
    name = "himalayas"
    display_name = "Himalayas"
    notes = "Free remote job API (no key required)."

    def fetch(self) -> list[NormalizedJob]:
        params = {"limit": int(self.config.get("limit", 60))}
        jobs: list[NormalizedJob] = []
        with self._client() as client:
            response = client.get("https://himalayas.app/jobs/api", params=params)
            if response.status_code != 200:
                return []
            data = response.json()
        for item in data.get("jobs", []):
            description = strip_html(item.get("description") or item.get("excerpt") or "")
            restrictions = item.get("locationRestrictions") or []
            if isinstance(restrictions, list):
                location = ", ".join(str(x) for x in restrictions[:4]) or "Remote"
            else:
                location = str(restrictions) or "Remote"
            exp_min, exp_max = parse_experience(description)
            salary_min = _as_float(item.get("minSalary"))
            salary_max = _as_float(item.get("maxSalary"))
            jobs.append(
                NormalizedJob(
                    title=item.get("title", ""),
                    company=item.get("companyName", ""),
                    description=description,
                    location=location,
                    url=item.get("applicationLink", "") or item.get("guid", ""),
                    remote=True,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    currency=item.get("currency", "") or "",
                    experience_min=exp_min,
                    experience_max=exp_max,
                    posted_at=parse_datetime(item.get("pubDate")),
                    external_id=str(item.get("guid", "") or item.get("applicationLink", "")),
                    source_name=self.name,
                    raw={
                        "categories": item.get("categories"),
                        "seniority": item.get("seniority"),
                        "employmentType": item.get("employmentType"),
                    },
                )
            )
        return jobs


def _as_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
