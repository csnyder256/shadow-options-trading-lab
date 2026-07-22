"""Market Collector (docs/02 §2.3) - pulls bars for the universe + benchmark and stamps
freshness. Stale data (age > max_data_age_seconds) is treated as MISSING and excluded, which
blocks trading on the affected symbol downstream."""

from __future__ import annotations

import numpy as np

from atlas.collect.feeds import Bars, DataFeed, QuoteData


class MarketCollector:
    def __init__(self, feed: DataFeed, max_data_age_seconds: float, benchmark_symbol: str = "SPY"):
        self.feed = feed
        self.max_data_age_seconds = max_data_age_seconds
        self.benchmark_symbol = benchmark_symbol

    def collect(self, symbols: list[str], now_iso: str) -> dict[str, Bars]:
        out: dict[str, Bars] = {}
        for symbol in symbols:
            bars = self.feed.get_bars(symbol, now_iso)
            if bars is None:
                continue
            if bars.age_seconds > self.max_data_age_seconds:  # stale -> treat as missing
                continue
            out[symbol] = bars
        return out

    def benchmark_close(self, now_iso: str) -> np.ndarray | None:
        bars = self.feed.get_bars(self.benchmark_symbol, now_iso)
        return bars.close if bars is not None else None

    def quote(self, symbol: str) -> QuoteData | None:
        return self.feed.get_quote(symbol)
