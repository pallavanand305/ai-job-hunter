from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from app.connectors.base import BaseConnector, NormalizedJob
from app.services.text_utils import parse_datetime, strip_html


class RSSConnector(BaseConnector):
    name = "rss"
    display_name = "Job alert RSS feeds"
    requires_config = True
    notes = (
        "Generic RSS/Atom job feed. Add feed URLs to config.feeds. Use this for official "
        "company career feeds or permitted alert feeds (LinkedIn/Naukri/Indeed alerts have no "
        "open apply API, so feed/email ingestion is the compliant path)."
    )

    @classmethod
    def is_configured(cls, config: dict | None = None) -> bool:
        return bool((config or {}).get("feeds") or getattr(cls, "DEFAULT_FEEDS", None))

    def _text(self, element: ET.Element, *names: str) -> str:
        for name in names:
            for child in element:
                if child.tag.split("}")[-1].lower() == name and child.text:
                    return child.text.strip()
        return ""

    def fetch(self) -> list[NormalizedJob]:
        feeds = self.config.get("feeds") or []
        jobs: list[NormalizedJob] = []
        for feed in feeds:
            try:
                with self._client() as client:
                    response = client.get(feed)
                if response.status_code != 200:
                    continue
                root = ET.fromstring(response.content)
                channel_title = ""
                for el in root.iter():
                    if el.tag.split("}")[-1].lower() == "title" and el.text:
                        channel_title = el.text.strip()
                        break
                for item in root.iter():
                    if item.tag.split("}")[-1].lower() not in {"item", "entry"}:
                        continue
                    title = self._text(item, "title")
                    link = self._text(item, "link")
                    if not link:
                        for child in item:
                            if child.tag.split("}")[-1].lower() == "link":
                                link = child.attrib.get("href", "")
                                break
                    description = strip_html(self._text(item, "description", "summary", "content"))
                    company = self.config.get("company") or channel_title
                    match = re.search(r"\bat\s+(.+)$", title, re.IGNORECASE)
                    if match:
                        company = match.group(1).strip()
                    jobs.append(
                        NormalizedJob(
                            title=title,
                            company=company,
                            description=description,
                            location=self.config.get("location", ""),
                            url=link,
                            remote=bool(self.config.get("remote", False)),
                            posted_at=parse_datetime(self._text(item, "pubDate", "published", "updated")),
                            external_id=link,
                            source_name=self.name,
                            raw={"feed": feed},
                        )
                    )
            except Exception:
                continue
        return jobs
