"""Image / VLM extractor.

Production path: a vision-language model (Claude / GPT-4o, or open Qwen2.5-VL /
Llama-3.2-Vision / Pixtral) returns structured JSON *with bounding boxes*; for
crisp object localisation add Grounding DINO / OWL-ViT. Keep each bbox so the
fact links back to the exact region of the photo.

Stub path: returns facts with ``bbox`` locators positioned over the demo image
(a 960x640 placeholder "flooded station" scene rendered as SVG).
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


class ImageExtractor(Extractor):
    method = Method.VLM
    model = "stub-vlm"  # swap for "qwen2.5-vl-72b" / "claude-*" when wiring _infer

    def _stub_facts(self, asset: Asset, event_id: str) -> list[FactRecord]:
        # bbox = [x, y, width, height] in pixels over the 960x640 demo image.
        seeds = [
            dict(
                phase=Phase.RESPONSE,
                subject="station:platform",
                predicate="visible_water_depth",
                value="above platform edge",
                unit=None,
                bbox=[120.0, 360.0, 720.0, 220.0],
                tags=["inundation", "visual-evidence"],
                conf=0.78,
            ),
            dict(
                phase=Phase.RESPONSE,
                subject="asset:turnstiles",
                predicate="submerged",
                value="partially",
                unit=None,
                bbox=[40.0, 300.0, 240.0, 180.0],
                tags=["asset-damage"],
                conf=0.66,
            ),
            dict(
                phase=Phase.RESPONSE,
                subject="people:passengers",
                predicate="present_in_floodwater",
                value="2 visible",
                unit="persons",
                bbox=[600.0, 280.0, 200.0, 240.0],
                tags=["safety", "exposure"],
                conf=0.71,
            ),
        ]

        facts: list[FactRecord] = []
        for i, s in enumerate(seeds):
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
                    ),
                    source=SourceRef(
                        asset_id=asset.asset_id,
                        locator=Locator(
                            selector_type=SelectorType.BBOX,
                            bbox=s["bbox"],
                        ),
                    ),
                    extraction=self._provenance(confidence=s["conf"]),
                    tags=s["tags"],
                )
            )
        return facts

    # -- real model path --------------------------------------------------- #
    def _infer(self, asset: Asset, event_id: str) -> list[FactRecord]:
        from pathlib import Path

        from flood_catalog.extract import llm
        from flood_catalog.extract.imageutil import image_size

        path = Path(asset.uri)
        width, height = image_size(path)
        claims = llm.extract_image(
            path.read_bytes(), asset.media_type, width, height, model=self.model_id
        )
        return self._facts_from_claims(asset, event_id, claims)

    def _facts_from_claims(self, asset, event_id, claims) -> list[FactRecord]:
        """Turn model claims into FactRecords, keeping each pixel bbox as the
        source locator (provenance)."""
        facts: list[FactRecord] = []
        for i, c in enumerate(claims):
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
                            selector_type=SelectorType.BBOX, bbox=list(c.bbox),
                        ),
                    ),
                    extraction=self._provenance(confidence=c.confidence),
                    tags=list(c.tags),
                )
            )
        return facts
