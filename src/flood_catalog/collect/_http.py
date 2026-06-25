"""Minimal stdlib HTTP for live collectors (no `requests` dependency).

Uses urllib, which honours HTTP(S)_PROXY env vars. For TLS behind a corporate
proxy, point ``SSL_CERT_FILE`` at the proxy CA bundle. Kept tiny on purpose;
swap in ``requests`` if you prefer (it's not required by the package).
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Optional

_UA = "flood-catalog-collector/0.1 (+research; respects robots/ToS)"


def get_text(url: str, *, headers: Optional[dict] = None, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https URLs
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def get_json(url: str, *, headers: Optional[dict] = None, timeout: float = 30.0) -> Any:
    return json.loads(get_text(url, headers=headers, timeout=timeout))
