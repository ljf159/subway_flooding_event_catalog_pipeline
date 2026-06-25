"""News RSS / Atom collector (free, no auth).

Most newsrooms (CNN, BBC, local papers) publish RSS/Atom feeds. We parse the
title + summary + link the publisher syndicates -- not the full article body.

Live: ``feeds`` are URLs, fetched over HTTP. Stub: ``feeds`` are local file
paths (the offline demo points them at fixture XML), parsed identically.
"""

from __future__ import annotations

import datetime as _dt
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from flood_catalog.collect._http import get_text
from flood_catalog.collect.base import CollectedItem, Collector, CollectionQuery


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]  # strip XML namespace


def _find_text(el, *names) -> str | None:
    for child in el:
        if _local(child.tag) in names and (child.text or "").strip():
            return child.text.strip()
    return None


def _parse_date(raw: str | None) -> _dt.datetime | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)        # RFC822 (RSS)
    except (TypeError, ValueError):
        pass
    try:
        return _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))  # ISO (Atom)
    except ValueError:
        return None


class RSSCollector(Collector):
    platform = "rss"

    def __init__(self, feeds: list[str], stub: bool = True) -> None:
        super().__init__(stub=stub)
        self.feeds = feeds

    def _stub_items(self, query: CollectionQuery) -> list[CollectedItem]:
        items: list[CollectedItem] = []
        for feed in self.feeds:
            items += self._parse_feed(Path(feed).read_text(errors="replace"))
        return items

    def _fetch(self, query: CollectionQuery) -> list[CollectedItem]:  # pragma: no cover
        items: list[CollectedItem] = []
        for url in self.feeds:
            items += self._parse_feed(get_text(url))
        return items

    # -- parsing ----------------------------------------------------------- #
    def _parse_feed(self, content: str) -> list[CollectedItem]:
        root = ET.fromstring(content)
        entries = [e for e in root.iter() if _local(e.tag) in ("item", "entry")]
        items: list[CollectedItem] = []
        for e in entries:
            title = _find_text(e, "title") or ""
            summary = _find_text(e, "description", "summary", "content") or ""
            link = self._link(e)
            date = _parse_date(_find_text(e, "pubDate", "published", "updated"))
            author = _find_text(e, "creator", "author")
            text = title if not summary else f"{title}\n\n{summary}"
            items.append(
                CollectedItem(
                    platform=self.platform, source_url=link or "",
                    author=author, posted_at=date, text=text.strip(),
                    raw={"title": title, "summary": summary},
                )
            )
        return items

    @staticmethod
    def _link(entry) -> str | None:
        for child in entry:
            if _local(child.tag) != "link":
                continue
            if child.text and child.text.strip():       # RSS: text content
                return child.text.strip()
            href = child.attrib.get("href")              # Atom: href attr
            if href and child.attrib.get("rel", "alternate") == "alternate":
                return href
        return None
