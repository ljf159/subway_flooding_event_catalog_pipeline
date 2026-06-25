"""Collection layer: source connectors that feed the extractor pipeline.

A ``Collector`` fetches posts/articles from one source (X, Weibo, news RSS,
GDELT) for an event's query and yields normalized :class:`CollectedItem`s. The
items are then turned into ``Asset``s (``normalize.item_to_asset``) and handed to
the existing ``Catalog.ingest`` -> extract -> FactRecord pipeline, so all the
provenance / storage / STAC machinery is reused. Collection only adds *where the
data comes from*.

We only ever collect and store the **snippet the source provides** (the post
text, or an article's title + summary from RSS/GDELT) plus the link to the full
item -- never a scraped full article body. That respects copyright/ToS and keeps
storage small (see ARCHITECTURE.md §5, "store what's yours, link what isn't").

Each concrete collector supports a ``stub`` mode that reads a local fixture, so
the whole pipeline runs offline with no API keys.
"""

from __future__ import annotations

import abc
import datetime as _dt
from typing import Any, Optional

from pydantic import BaseModel, Field


class CollectedItem(BaseModel):
    """One normalized post or article from a source."""

    platform: str                       # "x" | "weibo" | "rss" | "gdelt"
    source_url: str                     # link to the full original item
    external_id: Optional[str] = None   # platform-native id (tweet id, etc.)
    author: Optional[str] = None
    posted_at: Optional[_dt.datetime] = None
    text: str = ""                      # the post text / headline + summary
    lang: Optional[str] = None
    media_urls: list[str] = Field(default_factory=list)  # linked, not downloaded
    raw: dict[str, Any] = Field(default_factory=dict)    # original payload (audit)


class CollectionQuery(BaseModel):
    """What to collect for an event."""

    terms: list[str] = Field(default_factory=list)  # keywords (any-match)
    since: Optional[_dt.datetime] = None
    until: Optional[_dt.datetime] = None
    lang: Optional[str] = None
    limit: int = 50

    def matches(self, item: CollectedItem) -> bool:
        if self.lang and item.lang and self.lang != item.lang:
            return False
        if self.since and item.posted_at and item.posted_at < self.since:
            return False
        if self.until and item.posted_at and item.posted_at > self.until:
            return False
        if self.terms:
            hay = (item.text or "").lower()
            if not any(t.lower() in hay for t in self.terms):
                return False
        return True


class Collector(abc.ABC):
    """Base class. One subclass per source."""

    platform: str = "source"

    def __init__(self, stub: bool = True) -> None:
        self.stub = stub

    def collect(self, query: CollectionQuery) -> list[CollectedItem]:
        items = self._stub_items(query) if self.stub else self._fetch(query)
        kept = [it for it in items if query.matches(it)]
        return kept[: query.limit]

    # -- to implement ------------------------------------------------------ #
    @abc.abstractmethod
    def _stub_items(self, query: CollectionQuery) -> list[CollectedItem]:
        """Read a local fixture (offline / tests)."""

    def _fetch(self, query: CollectionQuery) -> list[CollectedItem]:  # pragma: no cover
        """Live fetch from the source's API/feed."""
        raise NotImplementedError(
            f"{type(self).__name__}._fetch is not implemented. Run with stub=True."
        )
