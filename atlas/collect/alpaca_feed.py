"""AlpacaDataFeed - real market data behind the DataFeed interface (docs/02 §2.4).

Free Alpaca plan: IEX feed, ~15-min delayed. Fetches DAILY bars (enough history for the 200-SMA) for
the WHOLE universe in ONE batched multi-symbol request, and CACHES them ACROSS cycles for
`bar_cache_ttl_seconds` (daily bars barely move intraday) - so a large universe (Phase 2) is NOT
re-downloaded every 120s cycle, only once per TTL. Lazy-imports alpaca-py so the package imports
without it installed; a `client` may be injected (tests / a pre-built client).

Freshness: this is a DAILY-cadence strategy, so the latest available daily bar is treated as "current"
(assume_fresh) rather than being failed by the intraday max_data_age_seconds gate - that 60s gate is
meant to catch a frozen INTRADAY feed. For true intraday trading you'd switch to minute bars.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from atlas.collect.feeds import Bars, DataFeed, QuoteData


class AlpacaDataFeed(DataFeed):
    def __init__(self, api_key: str, secret_key: str, symbols: list[str], *,
                 lookback_days: int = 400, assume_fresh: bool = True, min_bars: int = 30,
                 bar_cache_ttl_seconds: float = 3600.0, symbols_per_request: int = 200,
                 allow_on_demand: bool = False, client=None, feed=None):
        if client is None:                                  # live path; lazy-import alpaca-py
            from alpaca.data.enums import DataFeed as _Feed
            from alpaca.data.historical import StockHistoricalDataClient
            client = StockHistoricalDataClient(api_key, secret_key)
            feed = _Feed.IEX
        self._dc = client
        self._feed = feed
        self._symbols = list(symbols)
        self._lookback_days = lookback_days
        self._assume_fresh = assume_fresh
        self._min_bars = min_bars
        self._bar_cache_ttl = float(bar_cache_ttl_seconds)
        self._chunk = max(1, int(symbols_per_request))
        # On-demand fetch (universe-decoupling, 2026-06-29): when True, get_bars for a symbol OUTSIDE the
        # seeded universe (a >$100 scanner survivor) fetches that symbol individually and adds it to the
        # batched-refresh set. Default OFF keeps the feed seeded-only (today's behavior, byte-identical).
        self.allow_on_demand = bool(allow_on_demand)
        self._last_fetch_iso: str | None = None
        self._cache: dict[str, Bars] = {}

    def _within_ttl(self, now_iso: str) -> bool:
        """True if the cached daily bars are still fresh enough to reuse (skip the re-download)."""
        if not self._cache or self._last_fetch_iso is None:
            return False
        try:
            elapsed = (datetime.fromisoformat(now_iso)
                       - datetime.fromisoformat(self._last_fetch_iso)).total_seconds()
        except ValueError:
            return False
        return 0 <= elapsed < self._bar_cache_ttl

    def _fetch(self, symbols: list[str]) -> dict:
        """Daily-bar fetch -> {symbol: [bar, ...]}, CHUNKED so a large universe doesn't blow the request
        URI limit: alpaca-py puts the symbol list in the GET query, so a few-thousand-name request
        returns HTTP 414 (hit live by the dynamic_screen universe). Symbols are fetched in batches of
        `symbols_per_request` and merged. Overridable for tests."""
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        end = datetime.now(timezone.utc) - timedelta(minutes=20)    # respect the 15-min delay
        start = end - timedelta(days=self._lookback_days)
        out: dict = {}
        for i in range(0, len(symbols), self._chunk):
            req = StockBarsRequest(symbol_or_symbols=symbols[i:i + self._chunk], timeframe=TimeFrame.Day,
                                   start=start, end=end, feed=self._feed)
            out.update(self._dc.get_stock_bars(req).data)
        return out

    def _bars_from(self, sym: str, bl) -> Bars | None:
        """Build a Bars from an Alpaca bar list (shared by the batched refresh + on-demand fetch)."""
        if len(bl) < self._min_bars:
            return None
        last_ts = bl[-1].timestamp
        age = 0.0 if self._assume_fresh else (datetime.now(timezone.utc) - last_ts).total_seconds()
        return Bars(
            symbol=sym,
            open_=np.array([b.open for b in bl], dtype=float),
            high=np.array([b.high for b in bl], dtype=float),
            low=np.array([b.low for b in bl], dtype=float),
            close=np.array([b.close for b in bl], dtype=float),
            volume=np.array([b.volume for b in bl], dtype=float),
            as_of=last_ts.isoformat(), age_seconds=age,
        )

    def _refresh(self, now_iso: str) -> None:
        if self._within_ttl(now_iso):
            return                                          # reuse cache (no full-history re-download)
        data = self._fetch(self._symbols)
        cache: dict[str, Bars] = {}
        for sym in self._symbols:
            b = self._bars_from(sym, data.get(sym, []))
            if b is not None:
                cache[sym] = b
        self._cache = cache
        self._last_fetch_iso = now_iso

    def get_bars(self, symbol: str, now_iso: str) -> Bars | None:
        self._refresh(now_iso)
        # On-demand: a scanner survivor OUTSIDE the seeded universe (decoupled mode). Fetch it once and
        # add it to the batched-refresh set so later TTL refreshes keep it. If it's already in _symbols
        # (seeded, or fetched earlier) we never re-trigger this - a genuine no-data name just returns None.
        if self.allow_on_demand and symbol not in self._cache and symbol not in self._symbols:
            self._symbols.append(symbol)
            b = self._bars_from(symbol, self._fetch([symbol]).get(symbol, []))
            if b is not None:
                self._cache[symbol] = b
        return self._cache.get(symbol)

    def get_quote(self, symbol: str) -> QuoteData | None:
        # When the market is closed the live IEX quote can be wide/stale, so for consistent shadow
        # fills we use the latest daily close as the reference (tight, marketable synthetic quote).
        bars = self._cache.get(symbol)
        if bars is None:
            return None
        last = float(bars.close[-1])
        return QuoteData(symbol, bid=last - 0.01, ask=last, last=last)
