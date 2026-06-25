"""Satellite / remote-sensing extractor.

Production path (`_infer`): open a flood/water raster (COG) with rasterio,
derive a water mask -- either thresholding a precomputed flood band (e.g. a
Sentinel-1 SAR flood product or the Global Flood Database) or NDWI on optical
green/NIR bands -- vectorize it to polygons, and emit one ``flood_extent`` fact
per polygon. The polygon (lon/lat GeoJSON) is the fact's GEO locator, so the
observation links back to the exact ground footprint. Needs the ``geo`` extra
(rasterio, shapely, pyproj).

Stub path: deterministic flood-extent polygons over NYC for the Ida example, so
the pipeline runs offline.

Imagery itself is not re-hosted -- the catalog points to it via STAC (see
store/stac.py) and the asset's ``original_url`` to a public archive.
"""

from __future__ import annotations

from flood_catalog.extract.base import Extractor, make_fact_id
from flood_catalog.models import (
    Asset,
    Claim,
    FactRecord,
    Locator,
    Method,
    Phase,
    SelectorType,
    SourceRef,
)


class SatelliteExtractor(Extractor):
    method = Method.RULE          # deterministic index/threshold -> not an LLM
    model = "stub-satellite"
    real_model = "ndwi-threshold"  # the deterministic method id, not a Claude model

    # -- stub -------------------------------------------------------------- #
    def _stub_facts(self, asset: Asset, event_id: str) -> list[FactRecord]:
        # Two illustrative flood footprints near the NYC waterfront (lon/lat).
        seeds = [
            dict(
                area_km2=3.4,
                tags=["inundation", "flood-extent"],
                geom={
                    "type": "Polygon",
                    "coordinates": [[
                        [-73.965, 40.785], [-73.945, 40.787], [-73.940, 40.772],
                        [-73.962, 40.770], [-73.965, 40.785],
                    ]],
                },
            ),
            dict(
                area_km2=1.9,
                tags=["inundation", "flood-extent"],
                geom={
                    "type": "Polygon",
                    "coordinates": [[
                        [-73.852, 40.745], [-73.832, 40.748], [-73.829, 40.735],
                        [-73.849, 40.733], [-73.852, 40.745],
                    ]],
                },
            ),
        ]
        return self._facts_from_geoms(
            asset, event_id,
            [(s["geom"], s["area_km2"], s["tags"]) for s in seeds],
            confidence=0.75,
        )

    # -- real model path --------------------------------------------------- #
    def _infer(self, asset: Asset, event_id: str) -> list[FactRecord]:
        try:
            import rasterio
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "Satellite extraction needs rasterio. Install the extra:\n"
                "    pip install -e '.[geo]'"
            ) from exc
        from flood_catalog.extract import geoutil

        props = asset.properties or {}
        with rasterio.open(asset.uri) as src:
            if "green_band" in props and "nir_band" in props:
                mask = geoutil.ndwi_water_mask(
                    src.read(int(props["green_band"])),
                    src.read(int(props["nir_band"])),
                    float(props.get("ndwi_threshold", 0.0)),
                )
            else:  # default: a single-band flood product, nonzero = flooded
                arr = src.read(int(props.get("flood_band", 1)))
                mask = arr > float(props.get("flood_threshold", 0))
            geoms = geoutil.mask_to_polygons(mask, src.transform, src.crs)

        triples = [(g, geoutil.polygon_area_km2(g), ["inundation", "flood-extent"]) for g in geoms]
        return self._facts_from_geoms(asset, event_id, triples, confidence=0.8)

    # -- shared builder ---------------------------------------------------- #
    def _facts_from_geoms(self, asset, event_id, triples, confidence) -> list[FactRecord]:
        """Build a flood_extent FactRecord per polygon, with the polygon as the
        GEO locator (provenance back to the observed ground footprint)."""
        facts: list[FactRecord] = []
        for i, (geom, area_km2, tags) in enumerate(triples):
            facts.append(
                FactRecord(
                    fact_id=make_fact_id(event_id, asset.asset_id, "flood_extent", i),
                    event_id=event_id,
                    phase=Phase.RESPONSE,
                    claim=Claim(
                        subject="area:flooded",
                        predicate="observed_flood_extent",
                        value=f"{area_km2:.2f}",
                        unit="km2",
                    ),
                    source=SourceRef(
                        asset_id=asset.asset_id,
                        locator=Locator(selector_type=SelectorType.GEO, geo=geom),
                    ),
                    extraction=self._provenance(confidence=confidence),
                    tags=list(tags),
                )
            )
        return facts
