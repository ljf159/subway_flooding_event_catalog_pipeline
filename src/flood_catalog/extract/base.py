"""Extractor interface.

Every extractor consumes one :class:`Asset` and emits a list of
:class:`FactRecord` -- the *same* output shape regardless of modality. That
uniformity is what lets a single catalog absorb many input formats.

Each concrete extractor supports a ``stub`` mode that returns deterministic,
hand-authored facts so the whole pipeline runs offline with no API keys. The
real model call lives behind ``_infer`` and raises a clear error until wired up.
"""

from __future__ import annotations

import abc
import hashlib

from flood_catalog.models import (
    Asset,
    Extraction,
    FactRecord,
    Method,
)


def make_fact_id(event_id: str, asset_id: str, predicate: str, ordinal: int) -> str:
    """Stable, content-derived id so re-runs don't create duplicates."""
    raw = f"{event_id}|{asset_id}|{predicate}|{ordinal}"
    return "fact:" + hashlib.sha1(raw.encode()).hexdigest()[:16]


class Extractor(abc.ABC):
    """Base class. Subclass per modality."""

    #: PROV-O activity type recorded on every fact this extractor emits.
    method: Method = Method.RULE
    #: Identifier of the underlying model (override in subclasses).
    model: str = "stub"

    def __init__(self, stub: bool = True) -> None:
        self.stub = stub

    # -- public API -------------------------------------------------------- #
    def extract(self, asset: Asset, event_id: str) -> list[FactRecord]:
        """Return facts extracted from ``asset`` for ``event_id``."""
        if self.stub:
            return self._stub_facts(asset, event_id)
        return self._infer(asset, event_id)

    # -- helpers for subclasses ------------------------------------------- #
    def _provenance(self, confidence: float = 1.0) -> Extraction:
        return Extraction(
            method=self.method,
            model=self.model,
            model_version="stub" if self.stub else None,
            confidence=confidence,
        )

    # -- to be implemented by subclasses ---------------------------------- #
    @abc.abstractmethod
    def _stub_facts(self, asset: Asset, event_id: str) -> list[FactRecord]:
        """Deterministic offline facts (demo / tests / CI)."""

    def _infer(self, asset: Asset, event_id: str) -> list[FactRecord]:  # pragma: no cover
        """Real model inference. Wire this up to a VLM/LLM/ASR backend.

        Replace ``raise`` with a call to your provider, then parse the model's
        structured output into FactRecord objects (preserving the locator!).
        """
        raise NotImplementedError(
            f"{type(self).__name__}._infer is not wired to a model yet. "
            "Run with stub=True, or implement the model call here."
        )
