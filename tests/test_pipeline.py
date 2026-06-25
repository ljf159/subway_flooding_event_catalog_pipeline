"""Tests for the core model + pipeline invariants.

The most important invariant: *every fact is traceable to a source region*.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flood_catalog.catalog import Catalog
from flood_catalog.ingest.router import ExtractionRouter
from flood_catalog.models import (
    Event,
    FactRecord,
    Modality,
    Phase,
    SelectorType,
)
from flood_catalog.store.blobs import LocalBlobStore
from flood_catalog.store.tables import MetricsStore

SOURCES = Path(__file__).resolve().parents[1] / "examples" / "ida_2021" / "sources"


@pytest.fixture
def catalog(tmp_path):
    cat = Catalog(
        blobs=LocalBlobStore(tmp_path / "obj"),
        metrics=MetricsStore(":memory:"),
    )
    cat.add_event(Event(event_id="ev1", name="Test event", city="NYC", country="USA"))
    return cat


def test_text_facts_have_text_span_provenance(catalog):
    asset = catalog.blobs.put_file(SOURCES / "mta_ida_report.txt", Modality.TEXT)
    facts = catalog.ingest(asset, "ev1")
    assert facts, "expected at least one fact from the text source"
    for f in facts:
        assert isinstance(f, FactRecord)
        # every fact points back to the asset it came from
        assert f.source.asset_id == asset.asset_id
        loc = f.source.locator
        assert loc.selector_type is SelectorType.TEXT_SPAN
        # the recorded span actually matches the source document
        text = (SOURCES / "mta_ida_report.txt").read_text()
        assert text[loc.start:loc.end] == loc.quote


def test_image_facts_have_bbox_provenance(catalog):
    asset = catalog.blobs.put_file(SOURCES / "flooded_station.svg", Modality.IMAGE)
    facts = catalog.ingest(asset, "ev1")
    assert facts
    for f in facts:
        loc = f.source.locator
        assert loc.selector_type is SelectorType.BBOX
        assert loc.bbox and len(loc.bbox) == 4


def test_every_fact_has_phase_and_provenance(catalog):
    for name, mod in [("mta_ida_report.txt", Modality.TEXT),
                      ("flooded_station.svg", Modality.IMAGE)]:
        asset = catalog.blobs.put_file(SOURCES / name, mod)
        for f in catalog.ingest(asset, "ev1"):
            assert isinstance(f.phase, Phase)
            assert 0.0 <= f.extraction.confidence <= 1.0
            assert f.extraction.method is not None


def test_content_addressing_is_stable(catalog):
    a1 = catalog.blobs.put_file(SOURCES / "mta_ida_report.txt", Modality.TEXT)
    a2 = catalog.blobs.put_file(SOURCES / "mta_ida_report.txt", Modality.TEXT)
    assert a1.asset_id == a2.asset_id  # same bytes -> same id (dedupe)


def test_router_rejects_unregistered_modality():
    router = ExtractionRouter(stub=True)
    assert router.supports(Modality.TEXT)
    assert not router.supports(Modality.VIDEO)  # VIDEO has no extractor yet


def test_metrics_roundtrip(catalog):
    asset = catalog.blobs.put_file(SOURCES / "mta_ida_report.txt", Modality.TEXT)
    catalog.ingest(asset, "ev1")
    rows = catalog.metrics.query("SELECT count(*) FROM facts")
    assert rows[0][0] > 0
