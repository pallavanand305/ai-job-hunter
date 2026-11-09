from __future__ import annotations

from app.connectors.base import NormalizedJob
from app.connectors.rss import RSSConnector


class WeWorkRemotelyConnector(RSSConnector):
    name = "weworkremotely"
    display_name = "We Work Remotely"
    requires_config = False
    notes = "Free RSS feeds for remote programming and DevOps roles."

    DEFAULT_FEEDS = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    ]

    def fetch(self) -> list[NormalizedJob]:
        original = self.config
        self.config = {**original, "feeds": original.get("feeds") or self.DEFAULT_FEEDS}
        try:
            jobs = super().fetch()
        finally:
            self.config = original
        for job in jobs:
            job.source_name = self.name
        return jobs
