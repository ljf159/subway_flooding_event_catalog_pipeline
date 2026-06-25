"""Modality-specific extractors. Each emits provenance-bearing FactRecords."""

from flood_catalog.extract.base import Extractor
from flood_catalog.extract.image import ImageExtractor
from flood_catalog.extract.satellite import SatelliteExtractor
from flood_catalog.extract.text import TextExtractor

__all__ = ["Extractor", "ImageExtractor", "SatelliteExtractor", "TextExtractor"]
