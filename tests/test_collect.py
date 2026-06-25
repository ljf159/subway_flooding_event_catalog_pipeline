"""Collection layer tests (offline, against bundled fixtures)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from flood_catalog.catalog import Catalog
from flood_catalog.collect.base import CollectedItem, CollectionQuery
from flood_catalog.collect.gdelt import GDELTCollector
from flood_catalog.collect.normalize import item_to_asset
from flood_catalog.collect.pipeline import CollectionPipeline
from flood_catalog.collect.rss import RSSCollector
from flood_catalog.collect.social import WeiboCollector, XCollector
from flood_catalog.models import Event, Modality
from flood_catalog.store.blobs import LocalBlobStore
from flood_catalog.store.tables import MetricsStore

SOCIAL = Path(__file__).resolve().parents[1] / "examples" / "ida_2021" / "social"
Q = CollectionQuery(terms=["subway", "flood", "Ida", "MTA", "地铁"], limit=50)


def test_rss_parses_items():
    items = RSSCollector(feeds=[str(SOCIAL / "news_rss.xml")], stub=True).collect(Q)
    assert len(items) == 2
    it = items[0]
    assert it.platform == "rss"
    assert it.source_url.startswith("https://example-news.org/")
    assert "MTA" in it.text and "subway" in it.text.lower()
    assert it.posted_at and it.posted_at.year == 2021


def test_gdelt_stub_items():
    items = GDELTCollector(stub=True, fixture=SOCIAL / "gdelt.json").collect(Q)
    assert len(items) == 2
    assert all(i.platform == "gdelt" for i in items)
    assert items[0].author == "example-localpaper.org"
    assert items[0].posted_at.tzinfo is not None


def test_x_stub_resolves_author_and_url():
    items = XCollector(stub=True, fixture=SOCIAL / "x.json").collect(Q)
    assert len(items) == 2
    assert items[0].author == "demo_rider"
    assert items[0].source_url == "https://x.com/demo_rider/status/1433000000000000001"
    assert items[0].lang == "en"


def test_weibo_stub_chinese():
    items = WeiboCollector(stub=True, fixture=SOCIAL / "weibo.json").collect(Q)
    assert items and items[0].platform == "weibo"
    assert "地铁" in items[0].text
    assert items[0].lang == "zh"
    assert items[0].posted_at and items[0].posted_at.utcoffset() is not None


def test_term_filter_excludes_nonmatching():
    none_q = CollectionQuery(terms=["zzz-not-present"], limit=50)
    assert RSSCollector(feeds=[str(SOCIAL / "news_rss.xml")], stub=True).collect(none_q) == []


def test_item_to_asset_preserves_provenance(tmp_path):
    blobs = LocalBlobStore(tmp_path / "obj")
    item = CollectedItem(
        platform="x", source_url="https://x.com/u/status/9", author="u",
        posted_at=_dt.datetime(2021, 9, 2, tzinfo=_dt.timezone.utc),
        text="subway flooding everywhere", lang="en", external_id="9",
    )
    asset = item_to_asset(item, blobs)
    assert asset.modality is Modality.TEXT
    assert asset.original_url == "https://x.com/u/status/9"
    assert asset.properties["platform"] == "x" and asset.properties["author"] == "u"
    assert asset.datetime == item.posted_at
    assert Path(asset.uri).read_text() == "subway flooding everywhere"


def _catalog(tmp_path):
    cat = Catalog(blobs=LocalBlobStore(tmp_path / "obj"), metrics=MetricsStore(":memory:"))
    cat.add_event(Event(event_id="ev1", name="Test", city="NYC", country="USA"))
    return cat


def test_pipeline_ingests_all_sources(tmp_path):
    cat = _catalog(tmp_path)
    collectors = [
        RSSCollector(feeds=[str(SOCIAL / "news_rss.xml")], stub=True),
        GDELTCollector(stub=True, fixture=SOCIAL / "gdelt.json"),
        XCollector(stub=True, fixture=SOCIAL / "x.json"),
        WeiboCollector(stub=True, fixture=SOCIAL / "weibo.json"),
    ]
    result = CollectionPipeline(cat, collectors).run("ev1", Q)
    assert result.by_platform == {"rss": 2, "gdelt": 2, "x": 2, "weibo": 2}
    assert result.new_assets == 8
    assert len(cat.assets) == 8
    # every collected asset carries platform provenance
    assert all(a.properties.get("platform") for a in cat.assets.values())


def test_pipeline_dedup_on_rerun(tmp_path):
    cat = _catalog(tmp_path)
    collectors = [GDELTCollector(stub=True, fixture=SOCIAL / "gdelt.json")]
    pipe = CollectionPipeline(cat, collectors)
    first = pipe.run("ev1", Q)
    second = pipe.run("ev1", Q)
    assert first.new_assets == 2
    assert second.new_assets == 0 and second.duplicates == 2
