from __future__ import annotations

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import parse_datetime, parse_experience, strip_html


class RemoteOKConnector(BaseConnector):
    name = "remoteok"
    display_name = "RemoteOK"
    notes = "Free remote job API. Optional config.tags filter (e.g. python, ml)."

    def fetch(self) -> list[NormalizedJob]:
        jobs: list[NormalizedJob] = []
        wanted = {t.lower() for t in self.config.get("tags", [])}
        with self._client() as client:
            response = client.get("https://remoteok.com/api")
            if response.status_code != 200:
                return []
            data = response.json()
            for item in data:
                if not isinstance(item, dict) or "position" not in item:
                    continue
                tags = [str(t) for t in item.get("tags", [])]
                if wanted and not wanted.intersection({t.lower() for t in tags}):
                    continue
                description = strip_html(item.get("description", ""))
                exp_min, exp_max = parse_experience(description)
                jobs.append(
                    NormalizedJob(
                        title=item.get("position", ""),
                        company=item.get("company", ""),
                        description=description,
                        location=item.get("location") or "Remote",
                        url=item.get("url") or item.get("apply_url", ""),
                        remote=True,
                        salary_min=float(item["salary_min"]) if item.get("salary_min") else None,
                        salary_max=float(item["salary_max"]) if item.get("salary_max") else None,
                        currency="USD",
                        experience_min=exp_min,
                        experience_max=exp_max,
                        posted_at=parse_datetime(item.get("date")),
                        external_id=str(item.get("id", "")),
                        source_name=self.name,
                        raw={"tags": tags},
                    )
                )
        return jobs
