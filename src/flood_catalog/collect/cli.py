"""On-demand collection CLI:  python -m flood_catalog.collect ...

Examples
--------
Live news collection (free sources):
    python -m flood_catalog.collect --event ida-2021-nyc \
        --term "subway flood" --term "MTA Ida" \
        --rss https://feeds.bbci.co.uk/news/rss.xml --gdelt --out build

Offline demo against bundled fixtures:
    python -m flood_catalog.collect --event ida-2021-nyc --stub \
        --fixtures-dir examples/ida_2021/social \
        --rss examples/ida_2021/social/news_rss.xml --gdelt --x --weibo

X / Weibo live need $X_BEARER_TOKEN / $WEIBO_ACCESS_TOKEN. Extraction runs in
stub mode unless --real-extract (needs the extract extra + ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path

from flood_catalog.catalog import Catalog
from flood_catalog.collect.base import CollectionQuery
from flood_catalog.collect.gdelt import GDELTCollector
from flood_catalog.collect.pipeline import CollectionPipeline
from flood_catalog.collect.rss import RSSCollector
from flood_catalog.collect.social import WeiboCollector, XCollector
from flood_catalog.ingest.router import ExtractionRouter
from flood_catalog.models import Event
from flood_catalog.store.blobs import LocalBlobStore
from flood_catalog.store.tables import MetricsStore


def _dt_arg(s: str | None) -> _dt.datetime | None:
    return _dt.datetime.fromisoformat(s) if s else None


def build_collectors(args) -> list:
    fx = Path(args.fixtures_dir) if args.fixtures_dir else None
    collectors = []
    if args.rss:
        collectors.append(RSSCollector(feeds=args.rss, stub=args.stub))
    if args.gdelt:
        collectors.append(GDELTCollector(stub=args.stub, fixture=fx and fx / "gdelt.json"))
    if args.x:
        collectors.append(XCollector(stub=args.stub, fixture=fx and fx / "x.json"))
    if args.weibo:
        collectors.append(WeiboCollector(stub=args.stub, fixture=fx and fx / "weibo.json"))
    return collectors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="flood-collect", description=__doc__)
    p.add_argument("--event", required=True, help="event id, e.g. ida-2021-nyc")
    p.add_argument("--event-name", help="event display name (if creating it)")
    p.add_argument("--term", action="append", default=[], dest="terms", help="keyword (repeatable)")
    p.add_argument("--rss", action="append", default=[], help="RSS/Atom feed URL (or file path with --stub)")
    p.add_argument("--gdelt", action="store_true", help="collect from GDELT news index")
    p.add_argument("--x", action="store_true", help="collect from X (needs $X_BEARER_TOKEN)")
    p.add_argument("--weibo", action="store_true", help="collect from Weibo (needs $WEIBO_ACCESS_TOKEN)")
    p.add_argument("--since", help="ISO datetime lower bound")
    p.add_argument("--until", help="ISO datetime upper bound")
    p.add_argument("--lang", help="language filter, e.g. en / zh")
    p.add_argument("--limit", type=int, default=50, help="max items per source")
    p.add_argument("--stub", action="store_true", help="offline: read fixtures instead of live APIs")
    p.add_argument("--fixtures-dir", help="dir with gdelt.json / x.json / weibo.json (for --stub)")
    p.add_argument("--real-extract", action="store_true", help="run real Claude extraction (else stub)")
    p.add_argument("--store", default=".catalog_store", help="object store + duckdb dir")
    p.add_argument("--out", help="export the catalog bundle to this dir")
    args = p.parse_args(argv)

    store = Path(args.store)
    catalog = Catalog(
        blobs=LocalBlobStore(store / "objectstore"),
        metrics=MetricsStore(store / "catalog.duckdb"),
        router=ExtractionRouter(stub=not args.real_extract),
    )
    catalog.add_event(Event(event_id=args.event, name=args.event_name or args.event))

    collectors = build_collectors(args)
    if not collectors:
        p.error("pick at least one source: --rss / --gdelt / --x / --weibo")

    query = CollectionQuery(
        terms=args.terms, since=_dt_arg(args.since), until=_dt_arg(args.until),
        lang=args.lang, limit=args.limit,
    )
    result = CollectionPipeline(catalog, collectors).run(args.event, query)

    print("Collected (kept after filtering):")
    for platform, n in result.by_platform.items():
        print(f"  {platform:<8} {n}")
    print(f"New assets: {result.new_assets} · duplicates skipped: {result.duplicates} "
          f"· facts: {result.facts}")

    if args.out:
        out = catalog.export(args.out)
        print(f"Exported bundle to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
