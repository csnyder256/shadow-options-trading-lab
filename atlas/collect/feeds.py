"""Data feeds behind one interface (docs/02 §2.4). The SyntheticFeed generates deterministic
bars so the end-to-end SimBroker run is fully offline; AlpacaDataFeed/FinnhubNewsFeed (live,
keyed) are added in M3/M4 behind the same interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Bars:
    symbol: str
    open_: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    as_of: str            # ISO timestamp of the last bar
    age_seconds: float    # freshness (collector stamps this)


@dataclass(frozen=True)
class QuoteData:
    symbol: str
    bid: float
    ask: float
    last: float


@dataclass(frozen=True)
class NewsItem:
    datetime_iso: str   # ISO timestamp of the article
    headline: str
    summary: str
    source: str
    url: str


@dataclass(frozen=True)
class NewsBundle:
    """Recent news for one symbol for one cycle. `fetched` is True only when the provider was
    actually reached (vs offline / degraded / no feed configured) - used for the audit trail and
    to distinguish 'feed down' from 'genuinely no news'. Either way the analyst scores news ~50."""

    symbol: str
    items: tuple[NewsItem, ...]
    as_of: str
    fetched: bool

    def as_dicts(self) -> list[dict[str, str]]:
        return [
            {"datetime_iso": i.datetime_iso, "headline": i.headline,
             "summary": i.summary, "source": i.source, "url": i.url}
            for i in self.items
        ]


class DataFeed(ABC):
    @abstractmethod
    def get_bars(self, symbol: str, now_iso: str) -> Bars | None: ...

    @abstractmethod
    def get_quote(self, symbol: str) -> QuoteData | None: ...


class NewsFeed(ABC):
    @abstractmethod
    def get_news(self, symbol: str, now_iso: str) -> NewsBundle: ...


class NullNewsFeed(NewsFeed):
    """No news source (offline / synthetic runs). Always returns an empty, unfetched bundle so the
    analyst scores news as NEUTRAL (~50) rather than treating absence as bad news."""

    def get_news(self, symbol: str, now_iso: str) -> NewsBundle:
        return NewsBundle(symbol, (), now_iso, fetched=False)


class EarningsFeed(ABC):
    @abstractmethod
    def days_to_earnings(self, symbol: str, now_iso: str) -> int | None:
        """Signed calendar days from today to the symbol's NEAREST earnings date (negative = it
        already reported, positive = upcoming). None when unknown / none in window / feed down - 
        which the blackout treats as 'no earnings constraint' (fail-open is acceptable here because
        earnings risk is a refinement, not a core safety invariant)."""
        ...


class NullEarningsFeed(EarningsFeed):
    """No earnings calendar (offline / synthetic runs). Always None -> the earnings blackout is
    simply not applied (its prior, inert behavior)."""

    def days_to_earnings(self, symbol: str, now_iso: str) -> int | None:
        return None


class SyntheticFeed(DataFeed):
    """Deterministic generated data. By default a flat series; symbols in `breakout_symbols`
    get a clean uptrend-breakout-on-volume so a candidate appears. age_seconds is configurable
    to exercise the stale-data gate."""

    def __init__(
        self,
        symbols: list[str],
        *,
        n_bars: int = 260,
        breakout_symbols: tuple[str, ...] = (),
        age_seconds: float = 0.0,
    ):
        self.symbols = symbols
        self.n_bars = n_bars
        self.breakout_symbols = set(breakout_symbols)
        self.age_seconds = age_seconds

    def get_bars(self, symbol: str, now_iso: str) -> Bars | None:
        if symbol not in self.symbols:
            return None
        n = self.n_bars
        idx = float(abs(hash(symbol)) % 50)  # deterministic per-symbol price offset
        if symbol in self.breakout_symbols:
            close = 100.0 + idx + np.arange(n) * 0.2
            close[-1] = close[-2] + 4.0
            high = close + 0.5
            low = close - 0.5
            open_ = close - 0.1
            volume = np.full(n, 1_000_000.0)
            volume[-1] = 5_000_000.0
        else:
            base = np.full(n, 100.0 + idx)  # flat -> no setups (only breakout_symbols produce candidates)
            close = base
            high = base + 0.3
            low = base - 0.3
            open_ = base
            volume = np.full(n, 1_000_000.0)
        return Bars(symbol, open_, high, low, close, volume, now_iso, self.age_seconds)

    def get_quote(self, symbol: str) -> QuoteData | None:
        bars = self.get_bars(symbol, "")
        if bars is None:
            return None
        last = float(bars.close[-1])
        # Tight/marketable synthetic quote so a limit at last fills in the offline e2e.
        return QuoteData(symbol, bid=last - 0.02, ask=last, last=last)
