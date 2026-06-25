"""Turn a CollectedItem into an Asset for the extraction pipeline.

We store the collected snippet as a TEXT asset (content-addressed, so identical
items dedup), keep the link to the full item in ``original_url``, and carry the
social provenance (platform, author, posted_at, lang, linked media) in the
asset's ``properties`` so it survives into the graph/metrics tiers.
"""

from __future__ import annotations

from flood_catalog.collect.base import CollectedItem
from flood_catalog.models import Asset, Modality
from flood_catalog.store.blobs import LocalBlobStore


def _title(item: CollectedItem) -> str:
    first = (item.text or "").strip().splitlines()[0] if item.text.strip() else ""
    label = first[:80] + ("…" if len(first) > 80 else "")
    who = item.author or item.platform
    return f"{who}: {label}" if label else f"{item.platform} post"


def item_to_asset(item: CollectedItem, blobs: LocalBlobStore) -> Asset:
    return blobs.put_text(
        item.text,
        Modality.TEXT,
        original_url=item.source_url,
        title=_title(item),
        publisher=item.platform,
        license="source-terms-apply",   # snippet stored; full item only linked
        datetime=item.posted_at,
        properties={
            "platform": item.platform,
            "author": item.author,
            "lang": item.lang,
            "external_id": item.external_id,
            "media_urls": item.media_urls,
        },
    )
