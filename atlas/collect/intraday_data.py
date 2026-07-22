"""Intraday (1-minute) bar data layer for the INTRADAY backtest (2026-07-08 pivot).

RH serves only ~1-3 months of REAL intraday history (older bars are interpolated flat fakes), so the
intraday backtest sources 1-minute bars from ALPACA's IEX feed: verified 2+ years deep, 260-390 bars per
RTH day, and it captures small-cap intraday volatility (e.g. PLUG 8-13%/day). IEX is a single venue (~2-3%
of tape) so some minutes are absent, but the OHLCV of present bars is real and internally consistent for a
go/no-go read. Everything here is RTH-only (09:30-16:00 America/New_York), split-adjusted, parquet-cached
per symbol (mirrors atlas/backtest/data.py for the daily panel).

NOT the live path - this is a research/backtest data source. Live intraday quotes come from the RH MCP /
Guardian as always.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

RTH_START, RTH_END = "09:30", "15:59"          # left-labeled 1-min bars: 09:30..15:59 = 390 minutes


def _client():
    from alpaca.data.historical import StockHistoricalDataClient
    import yaml

    from atlas.config_loader import FRAMEWORK_ROOT
    creds = yaml.safe_load(
        (FRAMEWORK_ROOT / "config" / "credentials.local.yaml").read_text("utf-8"))["alpaca"]
    return StockHistoricalDataClient(creds["api_key"], creds["secret_key"])


def fetch_intraday_bars(symbol: str, start: date, end: date) -> pd.DataFrame:
    """1-minute IEX bars for one symbol over [start, end], RTH-only, tz America/New_York. The SDK
    paginates internally. Returns an EMPTY frame on any failure (caller skips the symbol)."""
    try:
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        dc = _client()
        al = symbol.replace("-", ".")                       # BRK-B -> BRK.B
        req = StockBarsRequest(symbol_or_symbols=al, timeframe=TimeFrame(1, TimeFrameUnit.Minute),
                               start=datetime(start.year, start.month, start.day),
                               end=datetime(end.year, end.month, end.day), feed=DataFeed.IEX)
        bars = dc.get_stock_bars(req).data.get(al, [])
    except Exception:
        return pd.DataFrame()
    if not bars:
        return pd.DataFrame()
    df = pd.DataFrame({
        "open": [float(b.open) for b in bars], "high": [float(b.high) for b in bars],
        "low": [float(b.low) for b in bars], "close": [float(b.close) for b in bars],
        "volume": [float(b.volume) for b in bars],
    }, index=pd.DatetimeIndex([b.timestamp for b in bars]))          # UTC, tz-aware
    df.index = df.index.tz_convert("America/New_York")
    df = df.between_time(RTH_START, RTH_END)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def load_or_fetch(symbol: str, start: date, end: date, *, cache_dir: Path) -> pd.DataFrame:
    """Cached 1-min RTH bars. Parquet per symbol; refetch only when absent."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"{symbol}_1min.parquet"
    if p.exists():
        try:
            return pd.read_parquet(p)
        except Exception:
            pass
    df = fetch_intraday_bars(symbol, start, end)
    if not df.empty:
        df.to_parquet(p)
    return df


def merge_1min(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Append freshly fetched 1-min bars onto a cached frame. Pure; the nightly cache
    refresh (scripts/refresh_intraday_cache.py, opts-fix-noise-cache-refresh-v1) writes
    the result atomically. Dedupe on the timestamp index (keep="last") makes re-runs
    idempotent; dtypes are pinned to the cache's shape (float64 columns,
    tz-aware datetime64[us] index) so parquet round-trips stay byte-stable."""
    cols = ["open", "high", "low", "close", "volume"]
    if new is None or new.empty:
        return old
    new = new.reindex(columns=cols).astype("float64")
    new.index = new.index.as_unit("us")
    out = new if (old is None or old.empty) else pd.concat([old, new])
    return out[~out.index.duplicated(keep="last")].sort_index()


def aggregate(df_1min: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregate 1-min bars to N-min bars WITHIN each session (never spanning the overnight gap).
    A dip-and-pop over ~15-60 min is cleaner on 5-min than noisy 1-min; 1-min stays the cached source."""
    if df_1min.empty or minutes <= 1:
        return df_1min
    rule = f"{minutes}min"
    out = []
    for _day, g in df_1min.groupby(df_1min.index.normalize()):
        r = g.resample(rule, origin="start_day", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(how="any")
        out.append(r)
    return pd.concat(out).sort_index() if out else df_1min


def sessions(df: pd.DataFrame):
    """Yield (session_date, per-session DataFrame) in chronological order - the unit the intraday backtest
    walks (each session is independent; entries flat by its close)."""
    for day, g in df.groupby(df.index.normalize()):
        yield day.date(), g
