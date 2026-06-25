"""Core data model for the subway flooding event catalog.

Design principle (see ARCHITECTURE.md): every extracted fact carries provenance
back to the *exact region* of the *original asset* it came from, so a researcher
can always click through and verify the source.

The schema is intentionally *soft*: ``Claim`` is a flexible subject/predicate/
value triple and ``Event`` allows arbitrary ``extra`` attributes. This supports
the "discover first, tentatively define, keep improving" workflow -- you grow the
vocabulary in ``schema/ontology.md`` over time without breaking stored data.

Standards reused rather than reinvented:
  * PPRR emergency-management cycle  -> ``Phase``
  * W3C Web Annotation selectors     -> ``Locator``
  * PROV-O lineage                   -> ``Extraction`` / ``Verification``
  * schema.org Event / SOSA / STAC   -> field names where practical
"""

from __future__ import annotations

import datetime as _dt
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Controlled vocabularies (extend these in schema/ontology.md as you discover) #
# --------------------------------------------------------------------------- #
class Phase(str, Enum):
    """Emergency-management lifecycle (PPRR). Maps onto before/during/after."""

    PREVENTION = "prevention"      # long-term mitigation (before)
    PREPAREDNESS = "preparedness"  # readiness just before the event (before)
    RESPONSE = "response"          # actions during the event (during)
    RECOVERY = "recovery"          # restoration after the event (after)


class Modality(str, Enum):
    """The format of a raw source asset -> selects which extractor runs."""

    TEXT = "text"            # reports, articles, social posts, PDFs (parsed)
    IMAGE = "image"          # photos, ground-level imagery
    SATELLITE = "satellite"  # remote sensing rasters (COG), SAR
    VIDEO = "video"          # CCTV, news footage
    AUDIO = "audio"          # interviews, radio, briefings
    TABULAR = "tabular"      # CSV / JSON / API dumps
    GEOSPATIAL = "geospatial"  # vector GIS (GeoJSON, shapefile)


class Method(str, Enum):
    """How a fact was produced (PROV-O activity type)."""

    LLM = "llm"
    VLM = "vlm"
    ASR = "asr"        # automatic speech recognition
    RULE = "rule"      # deterministic parser / schema mapping
    HUMAN = "human"


class SelectorType(str, Enum):
    """W3C-Annotation-style selector kinds for pointing inside an asset."""

    TEXT_SPAN = "text_span"     # character offsets in extracted text
    BBOX = "bbox"               # pixel rectangle in an image/frame
    TIME_RANGE = "time_range"   # seconds into audio/video
    PAGE = "page"               # PDF page
    GEO = "geo"                 # geographic region (GeoJSON)
    ROW = "row"                 # row/field in a table
    BYTE_RANGE = "byte_range"   # raw byte offsets


# --------------------------------------------------------------------------- #
# Provenance primitives                                                        #
# --------------------------------------------------------------------------- #
class Locator(BaseModel):
    """Points at the *sub-region* of an asset a fact was extracted from.

    Only the fields relevant to ``selector_type`` need be filled. This is a
    pragmatic flattening of the W3C Web Annotation Data Model selectors.
    """

    selector_type: SelectorType
    # text_span
    start: Optional[int] = None
    end: Optional[int] = None
    quote: Optional[str] = None       # the exact text, for human display
    # bbox: [x, y, width, height] in pixels (top-left origin)
    bbox: Optional[list[float]] = None
    # time_range (seconds)
    t_start: Optional[float] = None
    t_end: Optional[float] = None
    # page (1-based)
    page: Optional[int] = None
    # geo: a GeoJSON geometry
    geo: Optional[dict[str, Any]] = None
    # tabular
    row: Optional[int] = None
    column: Optional[str] = None
    # byte_range
    byte_start: Optional[int] = None
    byte_end: Optional[int] = None


class Asset(BaseModel):
    """A raw source file (Tier 1). Content-addressed and immutable.

    ``uri`` is where the bytes live (local path, ``s3://``/R2 key, or a public
    URL we don't re-host). ``original_url`` is where it came from, for citation.
    """

    asset_id: str                        # "sha256:<hex>"
    modality: Modality
    media_type: str                      # e.g. "image/png", "text/plain"
    uri: str                             # object-store location of the bytes
    original_url: Optional[str] = None   # source link for verification/citation
    title: Optional[str] = None
    publisher: Optional[str] = None
    license: Optional[str] = None        # rights for redistribution
    rehosted: bool = True                # False => we only link, don't store bytes
    bytes: Optional[int] = None
    retrieved_at: Optional[_dt.datetime] = None
    # Spatiotemporal metadata (mainly for satellite/geo assets -> STAC items).
    bbox: Optional[list[float]] = None       # [west, south, east, north] (lon/lat)
    geometry: Optional[dict[str, Any]] = None  # GeoJSON footprint of the scene
    datetime: Optional[_dt.datetime] = None
    start_datetime: Optional[_dt.datetime] = None
    end_datetime: Optional[_dt.datetime] = None
    properties: dict[str, Any] = Field(default_factory=dict)  # extra STAC props


class Extraction(BaseModel):
    """Lineage: which model/run produced a fact (PROV-O ``wasGeneratedBy``)."""

    method: Method
    model: str = "stub"                  # e.g. "qwen2.5-vl-72b", "claude-*"
    model_version: Optional[str] = None
    prompt_hash: Optional[str] = None
    run_id: Optional[str] = None
    confidence: float = 1.0
    extracted_at: _dt.datetime = Field(default_factory=lambda: _dt.datetime.now(_dt.timezone.utc))


class Verification(BaseModel):
    """Human-in-the-loop review state."""

    human_reviewed: bool = False
    reviewer: Optional[str] = None
    reviewed_at: Optional[_dt.datetime] = None
    status: Optional[str] = None         # "confirmed" | "rejected" | "edited"


# --------------------------------------------------------------------------- #
# The catalog records                                                          #
# --------------------------------------------------------------------------- #
class Claim(BaseModel):
    """A flexible structured assertion. Keep ``predicate`` values consistent by
    promoting common ones into schema/ontology.md as the vocabulary stabilises.
    """

    subject: str                         # canonical entity id, e.g. "station:14th-St"
    predicate: str                       # e.g. "flooded_to_depth", "service_status"
    value: Optional[str] = None
    unit: Optional[str] = None           # e.g. "m", "USD", "gallons", "hours"
    time: Optional[_dt.datetime] = None  # when the asserted state held
    geo: Optional[dict[str, Any]] = None


class SourceRef(BaseModel):
    """Binds a fact to the asset + precise location it was extracted from."""

    asset_id: str
    locator: Locator


class FactRecord(BaseModel):
    """The atomic unit of the catalog: one verifiable, sourced claim about an
    event, tagged with its PPRR phase.
    """

    fact_id: str
    event_id: str
    phase: Phase
    claim: Claim
    source: SourceRef
    extraction: Extraction
    verification: Verification = Field(default_factory=Verification)
    tags: list[str] = Field(default_factory=list)


class Event(BaseModel):
    """Top-level catalog entry. Metadata + headline metrics; the rich detail
    lives in the associated ``FactRecord`` list.

    ``extra`` is the soft-schema escape hatch: stash newly-discovered attributes
    here before promoting them to first-class fields.
    """

    event_id: str
    name: str
    hazard_type: str = "flood"
    city: Optional[str] = None
    country: Optional[str] = None
    transit_system: Optional[str] = None      # e.g. "MTA NYCT", "Zhengzhou Metro"
    centroid: Optional[list[float]] = None     # [lon, lat]
    started_at: Optional[_dt.datetime] = None
    ended_at: Optional[_dt.datetime] = None
    summary: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
