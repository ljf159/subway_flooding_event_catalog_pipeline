"""Geospatial helpers for the satellite extractor.

Turns a boolean water/flood mask raster into GeoJSON polygons in lon/lat, and
computes polygon areas. Heavy geo deps (rasterio, shapely, pyproj) are imported
lazily and only needed on the real extraction path (the ``geo`` extra); stub mode
and the STAC store don't require them.
"""

from __future__ import annotations

from typing import Any


def mask_to_polygons(mask, transform, src_crs) -> list[dict[str, Any]]:
    """Vectorize a boolean mask into GeoJSON Polygon geometries (EPSG:4326).

    ``mask`` is a 2D boolean/uint8 array (True/1 = flooded), ``transform`` is the
    raster's affine transform, ``src_crs`` its CRS. Returns lon/lat geometries.
    """
    import numpy as np
    import rasterio.features
    import rasterio.warp

    mask = np.asarray(mask).astype("uint8")
    geoms: list[dict[str, Any]] = []
    for geom, value in rasterio.features.shapes(mask, mask=mask.astype(bool), transform=transform):
        if not value:
            continue
        geoms.append(rasterio.warp.transform_geom(src_crs, "EPSG:4326", geom, precision=6))
    return geoms


def ndwi_water_mask(green, nir, threshold: float = 0.0):
    """Normalized Difference Water Index water mask from optical bands.

    NDWI = (green - nir) / (green + nir); water is typically NDWI > 0.
    """
    import numpy as np

    green = np.asarray(green, dtype="float32")
    nir = np.asarray(nir, dtype="float32")
    denom = green + nir
    ndwi = np.where(denom != 0, (green - nir) / denom, -1.0)
    return ndwi > threshold


def polygon_area_km2(geometry: dict[str, Any]) -> float:
    """Approximate area of a lon/lat GeoJSON geometry, in square kilometres.

    Uses an equal-area projection (World Mollweide) for a defensible number
    without assuming a UTM zone.
    """
    from shapely.geometry import shape
    from shapely.ops import transform as shp_transform
    from pyproj import Transformer

    geom = shape(geometry)
    to_equal_area = Transformer.from_crs("EPSG:4326", "ESRI:54009", always_xy=True).transform
    return shp_transform(to_equal_area, geom).area / 1_000_000.0


def bbox_of(geometry: dict[str, Any]) -> list[float]:
    """[west, south, east, north] of a GeoJSON geometry (no deps)."""
    xs: list[float] = []
    ys: list[float] = []

    def walk(coords) -> None:
        if isinstance(coords, (int, float)):
            return
        if coords and isinstance(coords[0], (int, float)):
            xs.append(coords[0])
            ys.append(coords[1])
        else:
            for c in coords:
                walk(c)

    walk(geometry.get("coordinates", []))
    return [min(xs), min(ys), max(xs), max(ys)]
