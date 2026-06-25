"""Extraction router: send each asset to the right modality extractor.

This is the seam that lets one catalog absorb many formats -- add a new
``Modality`` + ``Extractor`` and register it here; nothing downstream changes.
"""

from __future__ import annotations

from flood_catalog.extract.base import Extractor
from flood_catalog.extract.image import ImageExtractor
from flood_catalog.extract.satellite import SatelliteExtractor
from flood_catalog.extract.text import TextExtractor
from flood_catalog.models import Asset, FactRecord, Modality


class ExtractionRouter:
    """Maps :class:`Modality` -> :class:`Extractor` instance."""

    def __init__(self, stub: bool = True, model: str | None = None) -> None:
        self.stub = stub
        self._registry: dict[Modality, Extractor] = {
            Modality.TEXT: TextExtractor(stub=stub, model=model),
            Modality.IMAGE: ImageExtractor(stub=stub, model=model),
            Modality.SATELLITE: SatelliteExtractor(stub=stub, model=model),
            # TODO: VIDEO     -> VideoExtractor (yt-dlp + Whisper + keyframe VLM)
            # TODO: AUDIO     -> AudioExtractor (Whisper -> LLM)
            # TODO: TABULAR   -> TabularExtractor (schema mapping + LLM for messy fields)
            # TODO: GEOSPATIAL-> GeoExtractor (geopandas / GDAL)
        }

    def register(self, modality: Modality, extractor: Extractor) -> None:
        self._registry[modality] = extractor

    def supports(self, modality: Modality) -> bool:
        return modality in self._registry

    def route(self, asset: Asset) -> Extractor:
        try:
            return self._registry[asset.modality]
        except KeyError as exc:  # pragma: no cover - guard for unregistered modality
            raise NotImplementedError(
                f"No extractor registered for modality '{asset.modality.value}'. "
                "Register one via ExtractionRouter.register()."
            ) from exc

    def extract(self, asset: Asset, event_id: str) -> list[FactRecord]:
        return self.route(asset).extract(asset, event_id)
