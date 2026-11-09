from __future__ import annotations

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import is_remote, parse_datetime, strip_html


class LeverConnector(BaseConnector):
    name = "lever"
    display_name = "Lever"
    requires_config = True
    notes = "Public postings API. Add company tokens to config.companies (e.g. plaid, netflix)."

    def fetch(self) -> list[NormalizedJob]:
        companies = self.config.get("companies") or ["leverdemo"]
        jobs: list[NormalizedJob] = []
        with self._client() as client:
            for company in companies:
                response = client.get(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"})
                if response.status_code != 200:
                    continue
                for item in response.json() or []:
                    categories = item.get("categories") or {}
                    location = categories.get("location", "")
                    description = item.get("descriptionPlain") or strip_html(item.get("description", ""))
                    additional = item.get("additionalPlain") or strip_html(item.get("additional", ""))
                    if additional:
                        description = f"{description}\n\n{additional}"
                    jobs.append(
                        NormalizedJob(
                            title=item.get("text", ""),
                            company=company.replace("-", " ").title(),
                            description=description,
                            location=location,
                            url=item.get("hostedUrl", ""),
                            remote=is_remote(location, description),
                            posted_at=parse_datetime(item.get("createdAt")),
                            external_id=str(item.get("id", "")),
                            source_name=self.name,
                            raw={k: v for k, v in item.items() if k not in {"description", "additional"}},
                        )
                    )
        return jobs
