"""Tier 2 (geo): a STAC catalog for satellite / remote-sensing assets.

STAC (SpatioTemporal Asset Catalog) is the standard way to make geospatial
assets searchable. We emit a plain-JSON STAC 1.0.0 Catalog + one Item per
satellite scene -- no dependency on pystac, so it stays a set of static files
that any STAC client (or stac-browser) can read. The imagery itself is *linked*
(the Item's ``source`` asset href points at a public archive), not re-hosted.

Each Item records the scene footprint/bbox/datetime and the ids of the
flood-extent facts derived from it, tying the geo catalog to the event graph.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from flood_catalog.extract.geoutil import bbox_of
from flood_catalog.models import Asset, FactRecord

STAC_VERSION = "1.0.0"
CATALOG_ID = "subway-flooding-events"


def _iso(dt) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


class StacStore:
    def __init__(self) -> None:
        self.items: dict[str, dict] = {}  # item_id -> STAC Item

    def item_id(self, asset: Asset) -> str:
        return "scene-" + asset.asset_id.split(":", 1)[-1][:12]

    def add_item(
        self, asset: Asset, event_id: str, facts: Iterable[FactRecord] = ()
    ) -> str:
        """Register a STAC Item for a satellite asset and its derived facts."""
        item_id = self.item_id(asset)
        bbox = asset.bbox
        if bbox is None and asset.geometry is not None:
            bbox = bbox_of(asset.geometry)

        properties: dict = {
            "datetime": _iso(asset.datetime),
            "event_id": event_id,
            **asset.properties,
        }
        if asset.start_datetime:
            properties["start_datetime"] = _iso(asset.start_datetime)
        if asset.end_datetime:
            properties["end_datetime"] = _iso(asset.end_datetime)
        fact_ids = [f.fact_id for f in facts]
        if fact_ids:
            properties["derived:flood_extent_fact_ids"] = fact_ids

        self.items[item_id] = {
            "type": "Feature",
            "stac_version": STAC_VERSION,
            "id": item_id,
            "geometry": asset.geometry,
            "bbox": bbox,
            "properties": properties,
            "collection": CATALOG_ID,
            "assets": {
                "source": {
                    "href": asset.original_url or asset.uri,
                    "type": asset.media_type,
                    "title": asset.title,
                    "roles": ["data"],
                }
            },
            "links": [
                {"rel": "root", "href": "../catalog.json"},
                {"rel": "parent", "href": "../catalog.json"},
                {"rel": "collection", "href": "../catalog.json"},
            ],
        }
        return item_id

    def export_json(self, out_dir: Path | str) -> None:
        out = Path(out_dir)
        (out / "items").mkdir(parents=True, exist_ok=True)
        for item_id, item in self.items.items():
            (out / "items" / f"{item_id}.json").write_text(
                json.dumps(item, indent=2, default=str)
            )

        catalog = {
            "type": "Catalog",
            "stac_version": STAC_VERSION,
            "id": CATALOG_ID,
            "description": "Subway/metro flooding events — satellite scenes and "
            "derived flood extents.",
            "links": [
                {"rel": "root", "href": "./catalog.json"},
                {"rel": "self", "href": "./catalog.json"},
                *[
                    {"rel": "item", "href": f"./items/{item_id}.json"}
                    for item_id in self.items
                ],
            ],
        }
        (out / "catalog.json").write_text(json.dumps(catalog, indent=2))
