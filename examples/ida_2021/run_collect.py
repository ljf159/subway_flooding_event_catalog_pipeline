"""Offline demo of the collection layer (X / Weibo / news RSS / GDELT).

Runs all four collectors in stub mode against bundled fixtures, ingests the
collected posts/articles through the catalog (stub extraction, no keys), and
shows per-source counts + dedup on a second run.

    python examples/ida_2021/run_collect.py

For live collection use the CLI:  python -m flood_catalog.collect --help
"""

from __future__ import annotations

from pathlib import Path

from flood_catalog.catalog import Catalog
from flood_catalog.collect.base import CollectionQuery
from flood_catalog.collect.gdelt import GDELTCollector
from flood_catalog.collect.pipeline import CollectionPipeline
from flood_catalog.collect.rss import RSSCollector
from flood_catalog.collect.social import WeiboCollector, XCollector
from flood_catalog.models import Event
from flood_catalog.store.blobs import LocalBlobStore
from flood_catalog.store.tables import MetricsStore

ROOT = Path(__file__).resolve().parents[2]
SOCIAL = Path(__file__).resolve().parent / "social"
STORE = ROOT / ".catalog_store_collect"
BUILD = ROOT / "build_collect"


def main() -> None:
    catalog = Catalog(
        blobs=LocalBlobStore(STORE / "objectstore"),
        metrics=MetricsStore(STORE / "catalog.duckdb"),
    )
    catalog.add_event(Event(
        event_id="ida-2021-nyc", name="Hurricane Ida remnants — NYC subway flooding",
        city="New York City", country="USA",
    ))

    collectors = [
        RSSCollector(feeds=[str(SOCIAL / "news_rss.xml")], stub=True),
        GDELTCollector(stub=True, fixture=SOCIAL / "gdelt.json"),
        XCollector(stub=True, fixture=SOCIAL / "x.json"),
        WeiboCollector(stub=True, fixture=SOCIAL / "weibo.json"),
    ]
    pipeline = CollectionPipeline(catalog, collectors)
    query = CollectionQuery(
        terms=["subway", "flood", "Ida", "MTA", "地铁", "内涝"], limit=50,
    )

    r1 = pipeline.run("ida-2021-nyc", query)
    print("Collected (kept after filtering):")
    for platform, n in r1.by_platform.items():
        print(f"  {platform:<8} {n}")
    print(f"New assets: {r1.new_assets} · facts: {r1.facts}\n")

    print("Sample collected items (snippet stored, full item linked):")
    for a in list(catalog.assets.values())[:5]:
        p = a.properties.get("platform")
        print(f"  [{p:<6}] {a.title[:70]}")
        print(f"           → {a.original_url}")

    # Re-run the same query: everything is a duplicate (URL + content dedup).
    r2 = pipeline.run("ida-2021-nyc", query)
    print(f"\nRe-run dedup: new={r2.new_assets} duplicates_skipped={r2.duplicates}")

    out = catalog.export(BUILD)
    print(f"\nBuild written to: {out}")
    print(f"Open in a browser: {out / 'site' / 'index.html'}")


if __name__ == "__main__":
    main()
