"""Run collectors for an event, dedup, and ingest into the catalog.

Each collected item becomes a TEXT asset and flows through the normal
``Catalog.ingest`` -> extract -> FactRecord path. Dedup is on the source URL and
on content hash (the blob store is content-addressed), so re-running collection
for the same event doesn't double-count.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from flood_catalog.catalog import Catalog
from flood_catalog.collect.base import Collector, CollectionQuery
from flood_catalog.collect.normalize import item_to_asset
from flood_catalog.ingest.router import ExtractionRouter


@dataclass
class CollectionResult:
    by_platform: dict[str, int] = field(default_factory=dict)  # items kept per source
    new_assets: int = 0
    duplicates: int = 0
    facts: int = 0


class CollectionPipeline:
    def __init__(
        self,
        catalog: Catalog,
        collectors: list[Collector],
        *,
        router: ExtractionRouter | None = None,
    ) -> None:
        self.catalog = catalog
        self.collectors = collectors
        self.router = router  # override extraction (e.g. stub text) per collected asset

    def run(self, event_id: str, query: CollectionQuery) -> CollectionResult:
        result = CollectionResult()
        seen_urls = {
            a.original_url for a in self.catalog.assets.values() if a.original_url
        }
        for collector in self.collectors:
            items = collector.collect(query)
            result.by_platform[collector.platform] = len(items)
            for item in items:
                if item.source_url and item.source_url in seen_urls:
                    result.duplicates += 1
                    continue
                asset = item_to_asset(item, self.catalog.blobs)
                if asset.asset_id in self.catalog.assets:  # identical content seen
                    result.duplicates += 1
                    continue
                facts = self.catalog.ingest(asset, event_id, router=self.router)
                if item.source_url:
                    seen_urls.add(item.source_url)
                result.new_assets += 1
                result.facts += len(facts)
        return result
