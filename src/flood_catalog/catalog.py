"""High-level orchestration: ingest -> route -> extract -> store -> export.

This ties the three storage tiers together and produces a self-contained static
site bundle that demonstrates the provenance loop (click a fact -> highlight the
exact region of its source asset).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from flood_catalog.ingest.router import ExtractionRouter
from flood_catalog.models import Asset, Event, FactRecord
from flood_catalog.site.build import build_site
from flood_catalog.store.blobs import LocalBlobStore
from flood_catalog.store.graph import GraphStore
from flood_catalog.store.tables import MetricsStore


@dataclass
class Catalog:
    """In-memory working set + the storage backends."""

    blobs: LocalBlobStore
    metrics: MetricsStore = field(default_factory=MetricsStore)
    graph: GraphStore = field(default_factory=GraphStore)
    router: ExtractionRouter = field(default_factory=lambda: ExtractionRouter(stub=True))

    events: dict[str, Event] = field(default_factory=dict)
    assets: dict[str, Asset] = field(default_factory=dict)
    facts: list[FactRecord] = field(default_factory=list)

    # -- ingestion --------------------------------------------------------- #
    def add_event(self, event: Event) -> None:
        self.events[event.event_id] = event
        self.metrics.upsert_event(event)
        self.graph.add_event(event)

    def ingest(
        self,
        asset: Asset,
        event_id: str,
        router: ExtractionRouter | None = None,
    ) -> list[FactRecord]:
        """Store the asset, run the right extractor, persist resulting facts.

        Pass ``router`` to override the catalog's default for this one asset
        (e.g. run real extraction on a document but stub on a placeholder image).
        """
        self.assets[asset.asset_id] = asset
        self.metrics.upsert_asset(asset)
        self.graph.add_asset(asset)

        new_facts = (router or self.router).extract(asset, event_id)
        self.facts.extend(new_facts)
        self.metrics.upsert_facts(new_facts)
        self.graph.add_facts(new_facts)
        return new_facts

    # -- export ------------------------------------------------------------ #
    def export(self, out_dir: Path | str) -> Path:
        """Write the full bundle: data (parquet), graph (json/cypher), site.

        Only the subdirectories this method owns are cleared, so the export
        target can safely be separate from (or a parent of) the object store.
        """
        out = Path(out_dir)
        for sub in ("data", "graph", "site"):
            d = out / sub
            if d.exists():
                shutil.rmtree(d)
        (out / "data").mkdir(parents=True, exist_ok=True)

        # Tier 2 exports
        self.metrics.export_parquet(out / "data")
        self.metrics.con.execute(
            f"EXPORT DATABASE '{out / 'data' / 'duckdb_dump'}' (FORMAT PARQUET)"
        )
        self.graph.export_json(out / "graph")

        # Static site (Tier 3) -- inlines data, copies rehosted assets
        build_site(
            out / "site",
            events=list(self.events.values()),
            assets=self.assets,
            facts=self.facts,
            blobs=self.blobs,
        )
        return out
