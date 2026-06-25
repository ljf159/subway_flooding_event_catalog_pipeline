"""Real model backend: Claude (Anthropic SDK) for text + vision extraction.

Used by ``TextExtractor._infer`` / ``ImageExtractor._infer`` when an extractor
runs with ``stub=False``. Requires the ``extract`` optional dependency
(``pip install -e '.[extract]'``) and ``ANTHROPIC_API_KEY`` in the environment.

Provenance-preserving contract: the model returns the **verbatim quote** (text)
or a **pixel bounding box** (image) for each claim. We never trust the model for
character offsets -- the caller locates the returned quote in the source text to
compute the span. This keeps every fact verifiable against its exact source
region (see ARCHITECTURE.md §3).

The Anthropic SDK is imported lazily so this module (and its response schemas)
load even when ``anthropic`` isn't installed (stub mode, tests).
"""

from __future__ import annotations

import base64
from typing import Optional

from pydantic import BaseModel, Field

from flood_catalog.models import Phase

#: Default extraction model. Opus 4.8 is the most capable; swap to a cheaper
#: model (e.g. claude-haiku-4-5) per call via the ``model`` argument for scale.
DEFAULT_MODEL = "claude-opus-4-8"


# --------------------------------------------------------------------------- #
# Structured-output schemas (what the model must return)                       #
# --------------------------------------------------------------------------- #
class _TextClaim(BaseModel):
    phase: Phase
    subject: str = Field(description="Canonical entity id, e.g. 'station:14th-St'")
    predicate: str = Field(description="Relation, snake_case, e.g. 'flooded_to_depth'")
    value: Optional[str] = None
    unit: Optional[str] = Field(default=None, description="e.g. 'm', 'USD', 'hours'")
    quote: str = Field(description="The exact verbatim text span this claim is drawn from")
    tags: list[str] = Field(default_factory=list)
    confidence: float


class TextExtraction(BaseModel):
    facts: list[_TextClaim]


class _ImageClaim(BaseModel):
    phase: Phase
    subject: str
    predicate: str
    value: Optional[str] = None
    unit: Optional[str] = None
    bbox: list[float] = Field(description="[x, y, width, height] in pixels, top-left origin")
    tags: list[str] = Field(default_factory=list)
    confidence: float


class ImageExtraction(BaseModel):
    facts: list[_ImageClaim]


# --------------------------------------------------------------------------- #
# Prompts                                                                      #
# --------------------------------------------------------------------------- #
_SHARED_GUIDANCE = (
    "You are building a catalog of subway/metro flooding events. Extract only "
    "facts grounded in the source. Tag each with its emergency-management phase "
    "(PPRR): prevention, preparedness (before), response (during), recovery "
    "(after). Use canonical 'type:slug' subjects (e.g. 'station:14th-St', "
    "'system:MTA-NYCT', 'agency:NWS'). Keep predicates snake_case and put any "
    "unit in the separate 'unit' field. Set confidence in [0,1]. Do not invent "
    "facts; omit anything not supported by the source."
)

_TEXT_SYSTEM = (
    _SHARED_GUIDANCE
    + " For each fact, 'quote' MUST be copied verbatim (character-for-character) "
    "from the document so it can be located and highlighted as evidence."
)

_IMAGE_SYSTEM = (
    _SHARED_GUIDANCE
    + " For each fact, 'bbox' MUST be the pixel rectangle [x, y, width, height] "
    "(top-left origin) of the region in the image that shows the evidence, using "
    "the image's actual pixel dimensions given in the prompt."
)


# --------------------------------------------------------------------------- #
# Client                                                                       #
# --------------------------------------------------------------------------- #
def _client():
    try:
        import anthropic  # lazy: only needed for real inference
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "Real extraction needs the Anthropic SDK. Install the extra:\n"
            "    pip install -e '.[extract]'\n"
            "and set ANTHROPIC_API_KEY."
        ) from exc
    return anthropic.Anthropic()  # resolves ANTHROPIC_API_KEY from the environment


# --------------------------------------------------------------------------- #
# Extraction calls                                                             #
# --------------------------------------------------------------------------- #
def extract_text(text: str, *, model: str = DEFAULT_MODEL) -> list[_TextClaim]:
    """Extract grounded claims (each with a verbatim quote) from document text."""
    client = _client()
    response = client.messages.parse(
        model=model,
        max_tokens=8000,
        system=_TEXT_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract every flooding-event fact from this document. "
                    "Copy each supporting quote verbatim.\n\n<document>\n"
                    f"{text}\n</document>"
                ),
            }
        ],
        output_format=TextExtraction,
    )
    return response.parsed_output.facts


def extract_image(
    image_bytes: bytes,
    media_type: str,
    width: int,
    height: int,
    *,
    model: str = DEFAULT_MODEL,
) -> list[_ImageClaim]:
    """Extract grounded claims (each with a pixel bbox) from a photo/frame.

    ``media_type`` must be a raster type the vision API accepts
    (image/jpeg, image/png, image/gif, image/webp).
    """
    client = _client()
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    response = client.messages.parse(
        model=model,
        max_tokens=4000,
        system=_IMAGE_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"This image is {width}x{height} pixels. Extract every "
                            "flooding-event fact you can see, with a pixel bbox for "
                            "each region of evidence."
                        ),
                    },
                ],
            }
        ],
        output_format=ImageExtraction,
    )
    return response.parsed_output.facts
