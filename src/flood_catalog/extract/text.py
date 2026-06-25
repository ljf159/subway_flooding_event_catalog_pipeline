"""Text / document extractor.

Production path: Docling / Unstructured to parse a PDF or HTML into clean text,
then an LLM with structured output (Pydantic + Instructor) to fill FactRecords.
Crucially, keep the character offsets so each fact links back to its exact span.

Stub path: returns a few hand-authored facts about the NYC Ida 2021 event with
``text_span`` locators, so the demo runs with no API key.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

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


def _find_fuzzy(text: str, needle: str, start_at: int = 0) -> tuple[int, int]:
    """Find ``needle`` in ``text`` allowing any whitespace between its tokens.

    Returns (start, end) byte offsets into ``text`` of the actual match, or
    (-1, -1). Robust to the line-wrapping that document parsers introduce.
    """
    tokens = needle.split()
    if not tokens:
        return -1, -1
    pattern = r"\s+".join(re.escape(t) for t in tokens)
    m = re.search(pattern, text[start_at:], flags=re.IGNORECASE)
    if not m:
        return -1, -1
    return start_at + m.start(), start_at + m.end()


class TextExtractor(Extractor):
    method = Method.LLM
    model = "stub-text"  # swap for "claude-*" / "qwen3-*" when wiring _infer

    def _stub_facts(self, asset: Asset, event_id: str) -> list[FactRecord]:
        # Read the parsed document text so we can compute *real* character spans
        # for each quote. (Production: this text comes from Docling/Unstructured.)
        text = ""
        p = Path(asset.uri)
        if p.exists():
            text = p.read_text(errors="replace")

        seeds = [
            dict(
                phase=Phase.PREPAREDNESS,
                subject="agency:NWS",
                predicate="issued_warning",
                value="first-ever flash flood emergency for NYC",
                unit=None,
                quote="the National Weather Service issued its first-ever flash flood emergency for New York City",
                tags=["warning", "forecast"],
            ),
            dict(
                phase=Phase.RESPONSE,
                subject="system:MTA-NYCT",
                predicate="service_status",
                value="suspended (most lines, overnight)",
                unit=None,
                quote="the MTA suspended service across most subway lines overnight",
                tags=["service-suspension"],
            ),
            dict(
                phase=Phase.RESPONSE,
                subject="system:MTA-NYCT",
                predicate="flooded_locations_count",
                value="46",
                unit="locations",
                quote="the system flooded in 46 locations",
                tags=["impact", "inundation"],
            ),
            dict(
                phase=Phase.RECOVERY,
                subject="system:MTA-NYCT",
                predicate="water_removed",
                value="75",
                unit="million gallons",
                quote="crews removed roughly 75 million gallons of water",
                tags=["dewatering", "pumping"],
            ),
            dict(
                phase=Phase.RECOVERY,
                subject="system:MTA-NYCT",
                predicate="infrastructure_damage_cost",
                value="128",
                unit="million USD",
                quote="damage to MTA infrastructure totaled about $128 million",
                tags=["cost", "damage"],
            ),
        ]

        facts: list[FactRecord] = []
        cursor = 0
        for i, s in enumerate(seeds):
            # Locate the quote in the document with whitespace-tolerant matching
            # (PDF/HTML extraction often wraps a sentence across lines). Record the
            # *actual* matched substring as the quote so start:end always agrees.
            start, end = _find_fuzzy(text, s["quote"], cursor)
            if start < 0:
                start, end = cursor, cursor + len(s["quote"])
                quote = s["quote"]
            else:
                quote = text[start:end]
            cursor = end
            facts.append(
                FactRecord(
                    fact_id=make_fact_id(event_id, asset.asset_id, s["predicate"], i),
                    event_id=event_id,
                    phase=s["phase"],
                    claim=Claim(
                        subject=s["subject"],
                        predicate=s["predicate"],
                        value=s["value"],
                        unit=s["unit"],
                        time=_dt.datetime(2021, 9, 2, tzinfo=_dt.timezone.utc),
                    ),
                    source=SourceRef(
                        asset_id=asset.asset_id,
                        locator=Locator(
                            selector_type=SelectorType.TEXT_SPAN,
                            start=start,
                            end=end,
                            quote=quote,
                        ),
                    ),
                    extraction=self._provenance(confidence=0.9),
                    tags=s["tags"],
                )
            )
        return facts

    # -- real model path --------------------------------------------------- #
    def _infer(self, asset: Asset, event_id: str) -> list[FactRecord]:
        from flood_catalog.extract import llm, parse

        text = parse.parse_to_text(asset.uri)
        claims = llm.extract_text(text, model=self.model_id)
        return self._facts_from_claims(asset, event_id, text, claims)

    def _facts_from_claims(self, asset, event_id, text, claims) -> list[FactRecord]:
        """Turn model claims into FactRecords, locating each verbatim quote in
        the source text to compute a real character span (provenance)."""
        facts: list[FactRecord] = []
        cursor = 0
        for i, c in enumerate(claims):
            start, end = _find_fuzzy(text, c.quote, cursor)
            if start < 0:
                start = end = None       # quote not found; keep it for display
                quote = c.quote
            else:
                quote = text[start:end]
                cursor = end
            facts.append(
                FactRecord(
                    fact_id=make_fact_id(event_id, asset.asset_id, c.predicate, i),
                    event_id=event_id,
                    phase=c.phase,
                    claim=Claim(
                        subject=c.subject, predicate=c.predicate,
                        value=c.value, unit=c.unit,
                    ),
                    source=SourceRef(
                        asset_id=asset.asset_id,
                        locator=Locator(
                            selector_type=SelectorType.TEXT_SPAN,
                            start=start, end=end, quote=quote,
                        ),
                    ),
                    extraction=self._provenance(confidence=c.confidence),
                    tags=list(c.tags),
                )
            )
        return facts
