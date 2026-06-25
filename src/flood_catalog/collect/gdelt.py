"""GDELT DOC 2.0 collector (free, no auth).

GDELT indexes worldwide online news in near-real-time -- excellent coverage for
disaster events across many local outlets and languages. We use the public DOC
2.0 ArtList endpoint and keep the title + link (not the article body).
Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""

from __future__ import annotations

import datetime as _dt
import urllib.parse

from flood_catalog.collect._http import get_json
from flood_catalog.collect.base import CollectedItem, Collector, CollectionQuery

_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
_FIXTURE = None  # set by tests/demo via constructor


def _parse_seendate(raw: str | None) -> _dt.datetime | None:
    if not raw:
        return None
    try:
        return _dt.datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        return None


class GDELTCollector(Collector):
    platform = "gdelt"

    def __init__(self, stub: bool = True, fixture=None) -> None:
        super().__init__(stub=stub)
        self.fixture = fixture

    def build_url(self, query: CollectionQuery) -> str:
        q = " ".join(query.terms) or "flood"
        params = {
            "query": q, "mode": "ArtList", "format": "json",
            "maxrecords": str(min(query.limit, 250)), "sort": "DateDesc",
        }
        if query.since:
            params["startdatetime"] = query.since.strftime("%Y%m%d%H%M%S")
        if query.until:
            params["enddatetime"] = query.until.strftime("%Y%m%d%H%M%S")
        return f"{_ENDPOINT}?{urllib.parse.urlencode(params)}"

    def _stub_items(self, query: CollectionQuery) -> list[CollectedItem]:
        import json
        from pathlib import Path

        data = json.loads(Path(self.fixture).read_text()) if self.fixture else {}
        return self._parse(data)

    def _fetch(self, query: CollectionQuery) -> list[CollectedItem]:  # pragma: no cover
        return self._parse(get_json(self.build_url(query)))

    def _parse(self, data: dict) -> list[CollectedItem]:
        items: list[CollectedItem] = []
        for a in data.get("articles", []):
            media = [a["socialimage"]] if a.get("socialimage") else []
            items.append(
                CollectedItem(
                    platform=self.platform,
                    source_url=a.get("url", ""),
                    author=a.get("domain"),
                    posted_at=_parse_seendate(a.get("seendate")),
                    text=a.get("title", ""),
                    lang=a.get("language"),
                    media_urls=media,
                    raw=a,
                )
            )
        return items
