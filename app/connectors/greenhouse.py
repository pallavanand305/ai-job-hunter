from __future__ import annotations

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import is_remote, parse_datetime, strip_html


class GreenhouseConnector(BaseConnector):
    name = "greenhouse"
    display_name = "Greenhouse"
    requires_config = True
    notes = "Public job board API. Add company board tokens to config.boards (e.g. gitlab, canonical)."

    def fetch(self) -> list[NormalizedJob]:
        boards = self.config.get("boards") or ["gitlab", "canonical"]
        jobs: list[NormalizedJob] = []
        with self._client() as client:
            for board in boards:
                response = client.get(
                    f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
                    params={"content": "true"},
                )
                if response.status_code != 200:
                    continue
                for item in response.json().get("jobs", []):
                    location = (item.get("location") or {}).get("name", "")
                    description = strip_html(item.get("content", ""))
                    jobs.append(
                        NormalizedJob(
                            title=item.get("title", ""),
                            company=board.replace("-", " ").title(),
                            description=description,
                            location=location,
                            url=item.get("absolute_url", ""),
                            remote=is_remote(location, description),
                            posted_at=parse_datetime(item.get("updated_at")),
                            external_id=str(item.get("id", "")),
                            source_name=self.name,
                            raw=item,
                        )
                    )
        return jobs
