"""End-to-end demo: NYC Hurricane Ida (Sept 1-2, 2021) subway flooding.

Runs the full pipeline offline (stub extractors, no API keys) and writes a
static site to ``build/site`` plus Parquet + graph exports. Open
``build/site/index.html`` in a browser and click a fact to see its source region
highlighted -- the provenance loop.

    python examples/ida_2021/run_demo.py
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from flood_catalog.catalog import Catalog
from flood_catalog.models import Event, Modality
from flood_catalog.store.blobs import LocalBlobStore
from flood_catalog.store.tables import MetricsStore

ROOT = Path(__file__).resolve().parents[2]
SOURCES = Path(__file__).resolve().parent / "sources"
BUILD = ROOT / "build"                 # published artifacts (regenerated each run)
STORE = ROOT / ".catalog_store"        # object store + working DB (persisted)


def main() -> None:
    object_store = LocalBlobStore(STORE / "objectstore")
    catalog = Catalog(
        blobs=object_store,
        metrics=MetricsStore(STORE / "catalog.duckdb"),
    )

    catalog.add_event(
        Event(
            event_id="ida-2021-nyc",
            name="Hurricane Ida remnants — NYC subway flooding",
            city="New York City",
            country="USA",
            transit_system="MTA New York City Transit",
            centroid=[-73.97, 40.75],
            started_at=_dt.datetime(2021, 9, 1, 20, tzinfo=_dt.timezone.utc),
            ended_at=_dt.datetime(2021, 9, 7, tzinfo=_dt.timezone.utc),
            summary=(
                "Record rainfall from the remnants of Hurricane Ida flooded the "
                "NYC subway in dozens of locations, prompting an overnight "
                "system-wide service suspension and a multi-day recovery."
            ),
        )
    )

    # --- ingest heterogeneous sources -> structured, provenance-bearing facts ---
    text_asset = object_store.put_file(
        SOURCES / "mta_ida_report.txt",
        Modality.TEXT,
        title="MTA / NWS Ida summary brief (illustrative)",
        original_url="https://new.mta.info/",
        publisher="MTA (paraphrased)",
        license="illustrative-demo-text",
    )
    image_asset = object_store.put_file(
        SOURCES / "flooded_station.svg",
        Modality.IMAGE,
        title="Flooded station platform (illustrative)",
        original_url="https://www.flickr.com/",
        license="illustrative-demo-image",
    )

    f1 = catalog.ingest(text_asset, "ida-2021-nyc")
    f2 = catalog.ingest(image_asset, "ida-2021-nyc")
    print(f"Extracted {len(f1)} facts from text, {len(f2)} from image.")

    out = catalog.export(BUILD)

    # --- show the tabular tier answering an analytics query ---
    print("\nSample SQL over the metrics tier (DuckDB):")
    rows = catalog.metrics.query(
        "SELECT phase, count(*) AS facts FROM facts GROUP BY phase ORDER BY 1"
    )
    for phase, n in rows:
        print(f"  {phase:<13} {n}")

    print(f"\nBuild written to: {out}")
    print(f"Open in a browser: {out / 'site' / 'index.html'}")


if __name__ == "__main__":
    main()
