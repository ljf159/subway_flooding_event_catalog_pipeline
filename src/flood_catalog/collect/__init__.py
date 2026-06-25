"""Collection layer: source connectors that feed the extractor pipeline.

Collectors (RSS, GDELT, X, Weibo) fetch posts/articles for an event, normalize
them to Assets, and hand them to Catalog.ingest. See base.Collector.
"""

from flood_catalog.collect.base import CollectedItem, Collector, CollectionQuery
from flood_catalog.collect.gdelt import GDELTCollector
from flood_catalog.collect.normalize import item_to_asset
from flood_catalog.collect.pipeline import CollectionPipeline, CollectionResult
from flood_catalog.collect.rss import RSSCollector
from flood_catalog.collect.social import WeiboCollector, XCollector

__all__ = [
    "CollectedItem",
    "Collector",
    "CollectionQuery",
    "CollectionPipeline",
    "CollectionResult",
    "GDELTCollector",
    "RSSCollector",
    "WeiboCollector",
    "XCollector",
    "item_to_asset",
]
