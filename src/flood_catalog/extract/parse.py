"""Document parsing: any source format -> clean text for the LLM.

Plain-text formats are read directly. Everything else (PDF, DOCX, HTML, PPTX)
goes through Docling, which preserves tables and layout -- important for the
after-action reports and government docs this catalog ingests. Docling is an
optional dependency (the ``extract`` extra).
"""

from __future__ import annotations

from pathlib import Path

_PLAINTEXT = {".txt", ".md", ".csv", ".json", ".log", ""}


def parse_to_text(path: Path | str) -> str:
    """Return the textual content of a source document.

    For rich formats this returns Docling's Markdown export (tables included).
    """
    path = Path(path)
    if path.suffix.lower() in _PLAINTEXT:
        return path.read_text(errors="replace")

    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            f"Parsing '{path.suffix}' files needs Docling. Install the extra:\n"
            "    pip install -e '.[extract]'"
        ) from exc

    result = DocumentConverter().convert(str(path))
    return result.document.export_to_markdown()
