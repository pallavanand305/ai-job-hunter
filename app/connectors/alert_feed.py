from __future__ import annotations

from app.config import settings
from app.connectors.base import NormalizedJob
from app.connectors.rss import RSSConnector


class AlertFeedConnector(RSSConnector):
    """Permitted job-alert feeds for platforms without an official apply API.

    Point config.feeds (or the matching environment variable) at an RSS/Atom
    URL produced from your own alert emails/integration. Application always
    stays manual on the platform.
    """

    name = "alert_feed"
    display_name = "Job alert feed"
    requires_config = True
    env_attr = ""
    notes = "RSS/Atom alert feed. Configure feeds; application stays manual on the platform."

    @classmethod
    def is_configured(cls, config: dict | None = None) -> bool:
        feeds = (config or {}).get("feeds") or []
        if feeds:
            return True
        return bool(getattr(settings, cls.env_attr, "") if cls.env_attr else "")

    def _feeds(self) -> list[str]:
        feeds = list(self.config.get("feeds") or [])
        if not feeds and self.env_attr:
            url = getattr(settings, self.env_attr, "")
            if url:
                feeds = [url]
        return [f for f in feeds if f]

    def fetch(self) -> list[NormalizedJob]:
        feeds = self._feeds()
        if not feeds:
            return []
        original = self.config
        self.config = {**original, "feeds": feeds}
        try:
            jobs = super().fetch()
        finally:
            self.config = original
        for job in jobs:
            job.source_name = self.name
        return jobs


class LinkedInConnector(AlertFeedConnector):
    name = "linkedin"
    display_name = "LinkedIn (alert feed)"
    env_attr = "linkedin_feed_url"
    notes = (
        "LinkedIn has no open apply API. Add a permitted job-alert RSS URL via "
        "LINKEDIN_FEED_URL or config.feeds; apply on LinkedIn manually."
    )


class NaukriConnector(AlertFeedConnector):
    name = "naukri"
    display_name = "Naukri (alert feed)"
    env_attr = "naukri_feed_url"
    notes = (
        "Naukri has no open apply API. Add a permitted job-alert RSS URL via "
        "NAUKRI_FEED_URL or config.feeds; apply on Naukri manually."
    )


class IndeedConnector(AlertFeedConnector):
    name = "indeed"
    display_name = "Indeed (alert feed)"
    env_attr = "indeed_feed_url"
    notes = (
        "Indeed has no public apply API. Add a permitted job-alert RSS URL via "
        "INDEED_FEED_URL or config.feeds; apply on Indeed manually."
    )


class InstahyreConnector(AlertFeedConnector):
    name = "instahyre"
    display_name = "Instahyre (alert feed)"
    env_attr = "instahyre_feed_url"
    notes = (
        "Instahyre has no public apply API. Add a permitted alert RSS URL via "
        "INSTAHYRE_FEED_URL or config.feeds; apply on Instahyre manually."
    )


class WellfoundConnector(AlertFeedConnector):
    name = "wellfound"
    display_name = "Wellfound (alert feed)"
    env_attr = "wellfound_feed_url"
    notes = (
        "Wellfound blocks direct RSS scraping. Add a permitted alert RSS URL via "
        "WELLFOUND_FEED_URL or config.feeds; apply on Wellfound manually."
    )
