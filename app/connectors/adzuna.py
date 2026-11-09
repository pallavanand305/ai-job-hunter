from __future__ import annotations

from app.config import settings
from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import is_remote, parse_datetime, parse_experience, parse_salary, strip_html

CURRENCY_BY_COUNTRY = {
    "in": "INR",
    "us": "USD",
    "gb": "GBP",
    "ca": "CAD",
    "au": "AUD",
    "de": "EUR",
    "fr": "EUR",
    "nl": "EUR",
    "sg": "SGD",
    "ae": "AED",
}


class AdzunaConnector(BaseConnector):
    name = "adzuna"
    display_name = "Adzuna"
    requires_config = True
    notes = "Free Adzuna API. Set ADZUNA_APP_ID and ADZUNA_APP_KEY (country defaults to in)."

    @classmethod
    def is_configured(cls, config: dict | None = None) -> bool:
        cfg = config or {}
        return bool(
            (cfg.get("app_id") or settings.adzuna_app_id)
            and (cfg.get("app_key") or settings.adzuna_app_key)
        )

    def fetch(self) -> list[NormalizedJob]:
        cfg = self.config
        app_id = cfg.get("app_id") or settings.adzuna_app_id
        app_key = cfg.get("app_key") or settings.adzuna_app_key
        if not app_id or not app_key:
            return []
        country = (cfg.get("country") or settings.adzuna_country or "in").lower()
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": int(cfg.get("results", 50)),
            "what": cfg.get("what", "python"),
            "content-type": "application/json",
        }
        if cfg.get("where"):
            params["where"] = cfg["where"]
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        with self._client() as client:
            response = client.get(url, params=params)
            if response.status_code != 200:
                return []
            data = response.json()
        currency = CURRENCY_BY_COUNTRY.get(country, cfg.get("currency", ""))
        jobs: list[NormalizedJob] = []
        for item in data.get("results", []):
            description = strip_html(item.get("description", ""))
            location = (item.get("location") or {}).get("display_name", "") or ""
            exp_min, exp_max = parse_experience(description)
            jobs.append(
                NormalizedJob(
                    title=item.get("title", ""),
                    company=(item.get("company") or {}).get("display_name", ""),
                    description=description,
                    location=location,
                    url=item.get("redirect_url", ""),
                    remote=is_remote(location, description),
                    salary_min=_as_float(item.get("salary_min")),
                    salary_max=_as_float(item.get("salary_max")),
                    currency=currency,
                    experience_min=exp_min,
                    experience_max=exp_max,
                    posted_at=parse_datetime(item.get("created")),
                    external_id=str(item.get("id", "") or item.get("redirect_url", "")),
                    source_name=self.name,
                    raw={"category": (item.get("category") or {}).get("label", "")},
                )
            )
        return jobs


def _as_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
