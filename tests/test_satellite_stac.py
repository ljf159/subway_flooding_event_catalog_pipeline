"""Satellite extractor + STAC store tests.

Stub extraction, STAC item construction, geo provenance, and the catalog/STAC
integration all run with no geo deps. The real raster path (rasterio/shapely) is
covered by guarded tests that skip when those optional deps aren't installed.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from flood_catalog.catalog import Catalog
from flood_catalog.extract.geoutil import bbox_of
from flood_catalog.extract.satellite import SatelliteExtractor
from flood_catalog.ingest.router import ExtractionRouter
from flood_catalog.models import Asset, Event, Modality, SelectorType
from flood_catalog.store.blobs import LocalBlobStore
from flood_catalog.store.stac import StacStore
from flood_catalog.store.tables import MetricsStore

SOURCES = Path(__file__).resolve().parents[1] / "examples" / "ida_2021" / "sources"

_POLY = {
    "type": "Polygon",
    "coordinates": [[
        [-74.05, 40.68], [-73.78, 40.68], [-73.78, 40.82],
        [-74.05, 40.82], [-74.05, 40.68],
    ]],
}


def _sat_asset(tmp_path, rehosted=False):
    blobs = LocalBlobStore(tmp_path / "obj")
    a = blobs.put_file(
        SOURCES / "ida_s2_scene.json", Modality.SATELLITE,
        original_url="https://example.org/scene", rehosted=rehosted,
    )
    a.geometry = _POLY
    a.bbox = [-74.05, 40.68, -73.78, 40.82]
    a.datetime = _dt.datetime(2021, 9, 2, 15, 40, tzinfo=_dt.timezone.utc)
    return a


# -- extractor ------------------------------------------------------------- #
def test_satellite_stub_facts_have_geo_locators(tmp_path):
    asset = _sat_asset(tmp_path)
    facts = SatelliteExtractor(stub=True).extract(asset, "ev1")
    assert facts
    for f in facts:
        loc = f.source.locator
        assert loc.selector_type is SelectorType.GEO
        assert loc.geo["type"] == "Polygon"
        assert f.claim.unit == "km2" and float(f.claim.value) > 0
        assert f.source.asset_id == asset.asset_id


def test_router_supports_satellite():
    router = ExtractionRouter(stub=True)
    assert router.supports(Modality.SATELLITE)
    assert isinstance(router.route(_make_min_asset()), SatelliteExtractor)


def _make_min_asset():
    return Asset(asset_id="sha256:x", modality=Modality.SATELLITE,
                 media_type="image/tiff", uri="x")


# -- geoutil (no deps) ----------------------------------------------------- #
def test_bbox_of_polygon():
    assert bbox_of(_POLY) == [-74.05, 40.68, -73.78, 40.82]


# -- STAC store ------------------------------------------------------------ #
def test_stac_item_structure_and_links(tmp_path):
    asset = _sat_asset(tmp_path)
    store = StacStore()
    facts = SatelliteExtractor(stub=True).extract(asset, "ev1")
    item_id = store.add_item(asset, "ev1", facts)

    item = store.items[item_id]
    assert item["type"] == "Feature"
    assert item["stac_version"] == "1.0.0"
    assert item["geometry"]["type"] == "Polygon"
    assert item["bbox"] == [-74.05, 40.68, -73.78, 40.82]
    # imagery is linked, not re-hosted
    assert item["assets"]["source"]["href"] == "https://example.org/scene"
    # tied back to the derived facts in the event graph
    assert item["properties"]["derived:flood_extent_fact_ids"] == [f.fact_id for f in facts]

    store.export_json(tmp_path / "stac")
    catalog = json.loads((tmp_path / "stac" / "catalog.json").read_text())
    assert catalog["type"] == "Catalog"
    assert {"rel": "item", "href": f"./items/{item_id}.json"} in catalog["links"]
    assert (tmp_path / "stac" / "items" / f"{item_id}.json").exists()


def test_bbox_computed_from_geometry_when_absent(tmp_path):
    asset = _sat_asset(tmp_path)
    asset.bbox = None  # force derivation from geometry
    store = StacStore()
    iid = store.add_item(asset, "ev1")
    assert store.items[iid]["bbox"] == [-74.05, 40.68, -73.78, 40.82]


# -- catalog integration --------------------------------------------------- #
def test_catalog_builds_stac_item_and_exports(tmp_path):
    cat = Catalog(blobs=LocalBlobStore(tmp_path / "obj"), metrics=MetricsStore(":memory:"))
    cat.add_event(Event(event_id="ev1", name="Test", city="NYC", country="USA"))
    asset = _sat_asset(tmp_path)
    facts = cat.ingest(asset, "ev1")
    assert facts and len(cat.stac.items) == 1

    out = cat.export(tmp_path / "build")
    assert (out / "stac" / "catalog.json").exists()
    # satellite imagery wasn't copied into the site (link-only)
    assert not list((out / "site" / "assets").glob("*")) if (out / "site" / "assets").exists() else True


# -- real raster path (skips without geo deps) ----------------------------- #
def test_mask_to_polygons_real(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    import numpy as np
    from affine import Affine

    from flood_catalog.extract.geoutil import mask_to_polygons

    mask = np.zeros((4, 4), dtype="uint8")
    mask[1:3, 1:3] = 1  # a 2x2 flooded block
    transform = Affine.translation(-74.0, 40.8) * Affine.scale(0.01, -0.01)
    geoms = mask_to_polygons(mask, transform, "EPSG:4326")
    assert geoms and geoms[0]["type"] == "Polygon"
