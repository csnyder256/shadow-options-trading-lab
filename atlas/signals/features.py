"""Pure-numpy technical indicators (docs/04, docs/08).

Deterministic, reproducible, and unit-tested. Each function returns a full-length float
array aligned to the input, with np.nan during the warm-up period. Wilder smoothing is used
for RSI / ATR / ADX to match the conventional definitions. We deliberately implement these
ourselves rather than depend on TA-Lib's C library - "better reproducibility than any
library gives" (docs/08) and one fewer fragile Windows build dependency.
"""

from __future__ import annotations

import numpy as np

ArrayLike = np.ndarray | list[float]


def _arr(x: ArrayLike) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if a.ndim != 1:
        raise ValueError("expected a 1-D series")
    return a


def sma(values: ArrayLike, period: int) -> np.ndarray:
    v = _arr(values)
    out = np.full(v.shape, np.nan)
    if len(v) < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(v, period)
    out[period - 1:] = windows.mean(axis=1)
    return out


def rolling_std(values: ArrayLike, period: int, ddof: int = 0) -> np.ndarray:
    v = _arr(values)
    out = np.full(v.shape, np.nan)
    if len(v) < period:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(v, period)
    out[period - 1:] = windows.std(axis=1, ddof=ddof)
    return out


def ema(values: ArrayLike, period: int) -> np.ndarray:
    v = _arr(values)
    out = np.full(v.shape, np.nan)
    if len(v) < period:
        return out
    alpha = 2.0 / (period + 1.0)
    out[period - 1] = v[:period].mean()  # seed with SMA
    for i in range(period, len(v)):
        out[i] = v[i] * alpha + out[i - 1] * (1.0 - alpha)
    return out


def rsi(close: ArrayLike, period: int = 14) -> np.ndarray:
    c = _arr(close)
    out = np.full(c.shape, np.nan)
    if len(c) <= period:
        return out
    delta = np.diff(c)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    def _rsi(g: float, l: float) -> float:
        if l == 0:
            return 100.0
        rs = g / l
        return 100.0 - 100.0 / (1.0 + rs)
    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period + 1, len(c)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def true_range(high: ArrayLike, low: ArrayLike, close: ArrayLike) -> np.ndarray:
    h, l, c = _arr(high), _arr(low), _arr(close)
    tr = np.full(h.shape, np.nan)
    tr[0] = h[0] - l[0]
    prev_close = c[:-1]
    hl = h[1:] - l[1:]
    hc = np.abs(h[1:] - prev_close)
    lc = np.abs(l[1:] - prev_close)
    tr[1:] = np.maximum.reduce([hl, hc, lc])
    return tr


def _wilder(series: np.ndarray, period: int) -> np.ndarray:
    """Wilder's running average, seeded with the simple mean of the first `period` values."""
    out = np.full(series.shape, np.nan)
    valid = series[~np.isnan(series)]
    if len(valid) < period:
        return out
    start = int(np.argmax(~np.isnan(series)))  # first non-nan index
    first = start + period - 1
    out[first] = series[start:first + 1].mean()
    for i in range(first + 1, len(series)):
        out[i] = (out[i - 1] * (period - 1) + series[i]) / period
    return out


def atr(high: ArrayLike, low: ArrayLike, close: ArrayLike, period: int = 14) -> np.ndarray:
    tr = true_range(high, low, close)
    return _wilder(tr, period)


def adx(high: ArrayLike, low: ArrayLike, close: ArrayLike, period: int = 14) -> np.ndarray:
    h, l, c = _arr(high), _arr(low), _arr(close)
    n = len(h)
    out = np.full(h.shape, np.nan)
    if n < 2 * period + 1:
        return out
    up = h[1:] - h[:-1]
    down = l[:-1] - l[1:]
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(h, l, c)[1:]
    # Pad back to length n (index 0 has no DM/TR contribution).
    plus_dm = np.concatenate([[np.nan], plus_dm])
    minus_dm = np.concatenate([[np.nan], minus_dm])
    tr_full = np.concatenate([[np.nan], tr])
    atr_s = _wilder(tr_full, period)
    plus_s = _wilder(plus_dm, period)
    minus_s = _wilder(minus_dm, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * plus_s / atr_s
        minus_di = 100.0 * minus_s / atr_s
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    out = _wilder(dx, period)
    return out


def vwap(high: ArrayLike, low: ArrayLike, close: ArrayLike, volume: ArrayLike,
         period: int = 20) -> np.ndarray:
    """Rolling `period`-bar volume-weighted average price (the recent VALUE AREA).

    On DAILY bars a *cumulative* (since-inception) VWAP is meaningless as a support/value level:
    for any uptrending name it sits far below price (e.g. ~31 while price is ~55), which makes
    every name read as "extended above VWAP" and silently poisons (a) the analyst's bear case,
    (b) the quality-score `location` component, and (c) the picker's `pullback_in_uptrend`
    detector (which needs price within ~1.5% of VWAP - impossible vs a year-long average).
    A rolling window is what "price vs VWAP" is supposed to mean. Cumulative is kept ONLY as a
    short-history fallback (< period bars), where the window can't form yet."""
    h, l, c, vol = _arr(high), _arr(low), _arr(close), _arr(volume)
    out = np.full(c.shape, np.nan)
    if len(c) == 0:
        return out
    typical = (h + l + c) / 3.0
    pv = typical * vol
    if len(c) < period:
        cum_pv, cum_v = np.cumsum(pv), np.cumsum(vol)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(cum_v > 0, cum_pv / cum_v, np.nan)
    pv_w = np.lib.stride_tricks.sliding_window_view(pv, period).sum(axis=1)
    v_w = np.lib.stride_tricks.sliding_window_view(vol, period).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[period - 1:] = np.where(v_w > 0, pv_w / v_w, np.nan)
    return out


def vwap_session(high: ArrayLike, low: ArrayLike, close: ArrayLike, volume: ArrayLike,
                 session_id: ArrayLike) -> np.ndarray:
    """Session-ANCHORED cumulative VWAP: Σ(typical·vol)/Σ(vol), RESET at each new session_id (2026-07-08,
    intraday). Unlike the daily rolling `vwap`, the intraday session VWAP is THE most-watched intraday value
    level - the floor intraday mean-reversion buys reclaims of. `session_id` is a per-bar group key (e.g. the
    session date); the cumulation restarts whenever it changes. Causal (bar i uses only same-session data ≤ i)."""
    h, l, c, vol = _arr(high), _arr(low), _arr(close), _arr(volume)
    sid = np.asarray(session_id)
    typ = (h + l + c) / 3.0
    out = np.full(c.shape, np.nan)
    cum_pv = 0.0
    cum_v = 0.0
    cur = None
    for i in range(len(c)):
        if cur is None or sid[i] != cur:
            cur = sid[i]
            cum_pv = 0.0
            cum_v = 0.0
        cum_pv += typ[i] * vol[i]
        cum_v += vol[i]
        out[i] = cum_pv / cum_v if cum_v > 0 else c[i]
    return out


def bollinger(close: ArrayLike, period: int = 20, num_std: float = 2.0):
    mid = sma(close, period)
    sd = rolling_std(close, period)
    return mid, mid + num_std * sd, mid - num_std * sd


def volume_zscore(volume: ArrayLike, window: int = 20) -> np.ndarray:
    v = _arr(volume)
    out = np.full(v.shape, np.nan)
    if len(v) < window:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(v, window)
    mean = windows.mean(axis=1)
    std = windows.std(axis=1, ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.where(std > 0, (v[window - 1:] - mean) / std, 0.0)
    out[window - 1:] = z
    return out


def gap_pct(prev_close: float, today_open: float) -> float:
    if prev_close <= 0:
        return 0.0
    return (today_open - prev_close) / prev_close * 100.0


def relative_strength(close: ArrayLike, benchmark_close: ArrayLike, period: int = 20) -> float:
    """Symbol return minus benchmark return over `period` bars (>0 == outperforming)."""
    c, b = _arr(close), _arr(benchmark_close)
    if len(c) <= period or len(b) <= period:
        return 0.0
    sym_ret = c[-1] / c[-1 - period] - 1.0
    bench_ret = b[-1] / b[-1 - period] - 1.0
    return (sym_ret - bench_ret) * 100.0


# --- Buy-low / sell-high rebuild (2026-07-07, M4). Three SCALE-FREE, trailing-rolling additions for the
# instrument-agnostic price-action core (they generalize unchanged to crypto): Connors RSI-2 (fast oversold
# oscillator), Bollinger %b (mean-reversion depth in volatility units), and the Kaufman efficiency ratio
# (trend-vs-chop regime). Each returns a full-length nan-warmup array like the rest of this module.

def rsi2(close: ArrayLike) -> np.ndarray:
    """Connors RSI-2 - a very fast oversold/overbought oscillator (the canonical mean-reversion trigger).
    Just rsi() with period 2; a named alias so the buy-low core reads clearly and the period is fixed."""
    return rsi(close, 2)


def pct_b(close: ArrayLike, period: int = 20, num_std: float = 2.0) -> np.ndarray:
    """Bollinger %b = (close - lower) / (upper - lower). 0 = on the lower band, 1 = on the upper band,
    <0 = below the lower band (a deep, buyable dip in volatility units - scale-free by construction)."""
    c = _arr(close)
    _, upper, lower = bollinger(c, period, num_std)
    width = upper - lower
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(width > 0, (c - lower) / width, np.nan)


def efficiency_ratio(close: ArrayLike, period: int = 10) -> np.ndarray:
    """Kaufman Efficiency Ratio over `period` bars = |net move| / sum(|bar-to-bar moves|). ~1 == a clean
    directional trend, ~0 == chop/range. Bounded [0,1], so it reads the SAME on any instrument. Drives the
    regime switch (trend -> early-wave momentum; range -> dip mean-reversion)."""
    c = _arr(close)
    out = np.full(c.shape, np.nan)
    if len(c) <= period:
        return out
    net = np.abs(c[period:] - c[:-period])                       # |c[t] - c[t-period]|, aligned to index t
    absdiff = np.abs(np.diff(c))                                 # |c[i] - c[i-1]|
    path = np.lib.stride_tricks.sliding_window_view(absdiff, period).sum(axis=1)  # sum of `period` diffs
    with np.errstate(divide="ignore", invalid="ignore"):
        out[period:] = np.where(path > 0, net / path, 0.0)
    return out
