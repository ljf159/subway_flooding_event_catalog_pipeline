"""Real-model extraction plumbing, exercised offline.

We don't call Claude in tests; we monkeypatch the model functions and verify the
*plumbing* around them -- that returned claims become FactRecords with correct
provenance (text spans located in the source, image bboxes preserved, the real
model id recorded). The actual API call is a thin wrapper tested by inspection.
"""

from __future__ import annotations

import base64
from pathlib import Path

from flood_catalog.extract import llm, parse
from flood_catalog.extract.image import ImageExtractor
from flood_catalog.extract.imageutil import image_size
from flood_catalog.extract.text import TextExtractor
from flood_catalog.models import Method, Modality, Phase, SelectorType
from flood_catalog.store.blobs import LocalBlobStore

SOURCES = Path(__file__).resolve().parents[1] / "examples" / "ida_2021" / "sources"

# 1x1 transparent PNG (IHDR width=1 height=1) for the header-parser test.
_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_parse_plaintext_reads_directly():
    text = parse.parse_to_text(SOURCES / "mta_ida_report.txt")
    assert "Hurricane Ida" in text


def test_image_size_svg_and_png(tmp_path):
    assert image_size(SOURCES / "flooded_station.svg") == (960, 640)
    png = tmp_path / "x.png"
    png.write_bytes(_PNG_1x1)
    assert image_size(png) == (1, 1)


def test_text_infer_builds_spans_and_records_model(tmp_path, monkeypatch):
    blobs = LocalBlobStore(tmp_path / "obj")
    asset = blobs.put_file(SOURCES / "mta_ida_report.txt", Modality.TEXT)

    # Fake the model: return one claim whose quote is verbatim from the doc.
    quote = "the system flooded in 46 locations"
    monkeypatch.setattr(
        llm, "extract_text",
        lambda text, model: [
            llm._TextClaim(
                phase=Phase.RESPONSE, subject="system:MTA-NYCT",
                predicate="flooded_locations_count", value="46", unit="locations",
                quote=quote, tags=["impact"], confidence=0.9,
            )
        ],
    )

    extractor = TextExtractor(stub=False)
    facts = extractor._infer(asset, "ev1")
    assert len(facts) == 1
    f = facts[0]
    loc = f.source.locator
    assert loc.selector_type is SelectorType.TEXT_SPAN
    # the located span matches the source document exactly
    assert (SOURCES / "mta_ida_report.txt").read_text()[loc.start:loc.end] == quote
    # provenance records the real model + method, not the stub label
    assert f.extraction.model == "claude-opus-4-8"
    assert f.extraction.method is Method.LLM


def test_text_infer_handles_quote_not_found(tmp_path, monkeypatch):
    blobs = LocalBlobStore(tmp_path / "obj")
    asset = blobs.put_file(SOURCES / "mta_ida_report.txt", Modality.TEXT)
    monkeypatch.setattr(
        llm, "extract_text",
        lambda text, model: [
            llm._TextClaim(
                phase=Phase.RECOVERY, subject="x", predicate="y",
                quote="a sentence that is not present in the document",
                confidence=0.5,
            )
        ],
    )
    f = TextExtractor(stub=False)._infer(asset, "ev1")[0]
    assert f.source.locator.start is None  # not found -> no span, quote kept
    assert f.source.locator.quote


def test_image_infer_preserves_bbox(tmp_path, monkeypatch):
    blobs = LocalBlobStore(tmp_path / "obj")
    asset = blobs.put_file(SOURCES / "flooded_station.svg", Modality.IMAGE)
    monkeypatch.setattr(
        llm, "extract_image",
        lambda data, media_type, width, height, model: [
            llm._ImageClaim(
                phase=Phase.RESPONSE, subject="station:platform",
                predicate="visible_water_depth", bbox=[10.0, 20.0, 30.0, 40.0],
                confidence=0.7,
            )
        ],
    )
    f = ImageExtractor(stub=False)._infer(asset, "ev1")[0]
    assert f.source.locator.selector_type is SelectorType.BBOX
    assert f.source.locator.bbox == [10.0, 20.0, 30.0, 40.0]
    assert f.extraction.method is Method.VLM


def test_confidence_is_clamped(tmp_path, monkeypatch):
    blobs = LocalBlobStore(tmp_path / "obj")
    asset = blobs.put_file(SOURCES / "mta_ida_report.txt", Modality.TEXT)
    monkeypatch.setattr(
        llm, "extract_text",
        lambda text, model: [
            llm._TextClaim(phase=Phase.RESPONSE, subject="x", predicate="y",
                           quote="Hurricane Ida", confidence=1.8)
        ],
    )
    f = TextExtractor(stub=False)._infer(asset, "ev1")[0]
    assert 0.0 <= f.extraction.confidence <= 1.0
