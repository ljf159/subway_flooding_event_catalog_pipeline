"""Subway flooding event catalog pipeline.

A multi-modal, provenance-first pipeline that turns heterogeneous sources
(text, images, satellite, video, tabular) into a structured, queryable,
open catalog of subway/metro flooding events.

See ARCHITECTURE.md for the full system design.
"""

from flood_catalog.models import (
    Asset,
    Claim,
    Event,
    Extraction,
    FactRecord,
    Locator,
    Method,
    Modality,
    Phase,
    SelectorType,
    SourceRef,
    Verification,
)

__all__ = [
    "Asset",
    "Claim",
    "Event",
    "Extraction",
    "FactRecord",
    "Locator",
    "Method",
    "Modality",
    "Phase",
    "SelectorType",
    "SourceRef",
    "Verification",
]

__version__ = "0.1.0"
