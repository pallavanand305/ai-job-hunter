from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

import httpx


@dataclass
class NormalizedJob:
    title: str
    company: str
    description: str = ""
    location: str = ""
    url: str = ""
    remote: bool = False
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str = ""
    experience_min: float | None = None
    experience_max: float | None = None
    posted_at: datetime | None = None
    external_id: str = ""
    source_name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class BaseConnector:
    name: ClassVar[str] = "base"
    display_name: ClassVar[str] = "Base"
    requires_config: ClassVar[bool] = False
    notes: ClassVar[str] = ""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    def fetch(self) -> list[NormalizedJob]:  # pragma: no cover - interface
        raise NotImplementedError

    @staticmethod
    def _client() -> httpx.Client:
        return httpx.Client(
            timeout=25,
            follow_redirects=True,
            headers={
                "User-Agent": "AIJobHunter/1.0 (personal job search assistant)",
                "Accept": "application/json, text/plain, */*",
            },
        )
