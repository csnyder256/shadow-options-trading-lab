"""Market Collector + data feeds (docs/02 §2.3). Collects and freshness-stamps OHLCV/quote
data; stale data (older than max_data_age_seconds) is treated as missing and blocks trading on
the affected symbol. The SyntheticFeed makes the end-to-end run fully offline (no API key)."""

from atlas.collect.feeds import (
    Bars,
    DataFeed,
    EarningsFeed,
    NewsBundle,
    NewsFeed,
    NewsItem,
    NullEarningsFeed,
    NullNewsFeed,
    SyntheticFeed,
)
from atlas.collect.market_collector import MarketCollector

__all__ = [
    "Bars", "DataFeed", "SyntheticFeed", "MarketCollector",
    "NewsFeed", "NullNewsFeed", "NewsBundle", "NewsItem",
    "EarningsFeed", "NullEarningsFeed",
]
