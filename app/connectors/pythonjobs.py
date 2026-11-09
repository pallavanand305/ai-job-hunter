from __future__ import annotations

from app.connectors.base import NormalizedJob
from app.connectors.rss import RSSConnector


class PythonJobsConnector(RSSConnector):
    name = "pythonjobs"
    display_name = "Python.org Job Board"
    requires_config = False
    notes = "Official python.org job board RSS feed."

    DEFAULT_FEEDS = ["https://www.python.org/jobs/feed/rss/"]

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
