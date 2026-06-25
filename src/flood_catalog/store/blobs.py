"""Tier 1: raw asset storage (content-addressed, immutable).

``LocalBlobStore`` writes bytes to a directory keyed by sha256. The interface is
deliberately S3-shaped so a future ``R2BlobStore`` (Cloudflare R2 / Backblaze B2,
both S3-compatible) drops in with no caller changes -- that's the budget path:
near-zero egress for a public download site.

For assets we are *not* allowed to re-host (copyrighted news/video), set
``rehosted=False`` and store only ``original_url`` -- the catalog keeps the fact
and the link, not the bytes.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import mimetypes
import shutil
from pathlib import Path
from typing import Optional

from flood_catalog.models import Asset, Modality


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class LocalBlobStore:
    """Filesystem-backed object store. Layout mirrors an S3 bucket."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _key(self, asset_id: str, suffix: str) -> str:
        digest = asset_id.split(":", 1)[-1]
        # shard by first two hex chars, like a CDN-friendly bucket layout
        return f"assets/{digest[:2]}/{digest}{suffix}"

    def uri(self, asset_id: str, suffix: str = "") -> str:
        return str(self.root / self._key(asset_id, suffix))

    def put_file(
        self,
        path: Path | str,
        modality: Modality,
        *,
        original_url: Optional[str] = None,
        title: Optional[str] = None,
        publisher: Optional[str] = None,
        license: Optional[str] = None,
        rehosted: bool = True,
    ) -> Asset:
        """Ingest a file, returning its :class:`Asset` record.

        If ``rehosted`` is False the bytes are *not* copied; we keep metadata and
        the link only (saves storage/budget and respects copyright).
        """
        path = Path(path)
        digest = sha256_file(path)
        asset_id = f"sha256:{digest}"
        suffix = path.suffix
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

        uri = original_url or path.as_uri()
        if rehosted:
            dest = Path(self.uri(asset_id, suffix))
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(path, dest)
            uri = str(dest)

        return Asset(
            asset_id=asset_id,
            modality=modality,
            media_type=media_type,
            uri=uri,
            original_url=original_url,
            title=title,
            publisher=publisher,
            license=license,
            rehosted=rehosted,
            bytes=path.stat().st_size,
            retrieved_at=_dt.datetime.now(_dt.timezone.utc),
        )

    def put_text(
        self,
        text: str,
        modality: Modality = Modality.TEXT,
        *,
        media_type: str = "text/plain",
        original_url: Optional[str] = None,
        title: Optional[str] = None,
        publisher: Optional[str] = None,
        license: Optional[str] = None,
        properties: Optional[dict] = None,
        datetime: Optional[_dt.datetime] = None,
    ) -> Asset:
        """Content-address and store an in-memory text snippet (e.g. a social
        post or a news headline+summary) as a TEXT asset.

        This is the collection path: we store the *snippet the source provided*
        (post text / RSS summary), set ``original_url`` to the full item, and
        leave the full article body un-rehosted. Same bytes -> same id (dedup).
        """
        data = text.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        asset_id = f"sha256:{digest}"
        dest = Path(self.uri(asset_id, ".txt"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(data)
        return Asset(
            asset_id=asset_id,
            modality=modality,
            media_type=media_type,
            uri=str(dest),
            original_url=original_url,
            title=title,
            publisher=publisher,
            license=license,
            rehosted=True,
            bytes=len(data),
            retrieved_at=_dt.datetime.now(_dt.timezone.utc),
            datetime=datetime,
            properties=properties or {},
        )

    def local_path(self, asset: Asset) -> Optional[Path]:
        """Return the on-disk path of a rehosted asset (for export/copy)."""
        if not asset.rehosted:
            return None
        suffix = Path(asset.uri).suffix
        return Path(self.uri(asset.asset_id, suffix))
