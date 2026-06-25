"""Read image pixel dimensions without a hard Pillow dependency.

The VLM is told the image's pixel size so it can return pixel bounding boxes.
We try Pillow first (handles every raster format), then fall back to tiny
header parsers for the common web formats and SVG so the demo/tests work with
no extra install.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path


def image_size(path: Path | str) -> tuple[int, int]:
    """Return (width, height) in pixels. Raises if it can't be determined."""
    path = Path(path)
    data = path.read_bytes()

    if path.suffix.lower() == ".svg":
        size = _svg_size(data)
        if size:
            return size

    # Pillow if available -- most reliable across formats.
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001 - fall through to header parsing
        pass

    for parser in (_png_size, _gif_size, _jpeg_size):
        size = parser(data)
        if size:
            return size

    raise RuntimeError(
        f"Could not determine image dimensions for {path.name}. "
        "Install Pillow (the 'extract' extra) for full format support."
    )


def _svg_size(data: bytes) -> tuple[int, int] | None:
    head = data[:2048].decode("utf-8", errors="replace")
    w = re.search(r'width="([0-9.]+)', head)
    h = re.search(r'height="([0-9.]+)', head)
    if w and h:
        return int(float(w.group(1))), int(float(h.group(1)))
    vb = re.search(r'viewBox="[0-9.\s]*?([0-9.]+)\s+([0-9.]+)"', head)
    if vb:
        return int(float(vb.group(1))), int(float(vb.group(2)))
    return None


def _png_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    return None


def _gif_size(data: bytes) -> tuple[int, int] | None:
    if data[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", data[6:10])
        return w, h
    return None


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        i += 2 + length
    return None
