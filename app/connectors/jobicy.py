from __future__ import annotations

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import parse_datetime, parse_experience, strip_html


class JobicyConnector(BaseConnector):
    name = "jobicy"
    display_name = "Jobicy"
    notes = "Free remote job API. Use config.industry (for example dev); geo=india is rejected by the API."

    def fetch(self) -> list[NormalizedJob]:
        params = {"count": int(self.config.get("count", 50))}
        if self.config.get("geo"):
            params["geo"] = self.config["geo"]
        if self.config.get("industry"):
            params["industry"] = self.config["industry"]
        jobs: list[NormalizedJob] = []
        with self._client() as client:
            response = client.get("https://jobicy.com/api/v2/remote-jobs", params=params)
            if response.status_code != 200:
                return []
            for item in response.json().get("jobs", []):
                description = strip_html(item.get("jobDescription", ""))
                exp_min, exp_max = parse_experience(description)
                jobs.append(
                    NormalizedJob(
                        title=item.get("jobTitle", ""),
                        company=item.get("companyName", ""),
                        description=description,
                        location=item.get("jobGeo", "Remote"),
                        url=item.get("url", ""),
                        remote=True,
                        salary_min=float(item["annualSalaryMin"]) if item.get("annualSalaryMin") else None,
                        salary_max=float(item["annualSalaryMax"]) if item.get("annualSalaryMax") else None,
                        currency=item.get("salaryCurrency", "USD"),
                        experience_min=exp_min,
                        experience_max=exp_max,
                        posted_at=parse_datetime(item.get("pubDate")),
                        external_id=str(item.get("id", "")),
                        source_name=self.name,
                        raw={"jobLevel": item.get("jobLevel", "")},
                    )
                )
        return jobs
