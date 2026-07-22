"""Volatility analytics: realized (historical) vol, IV-vs-HV, IV rank/percentile.

All functions are deterministic given their inputs. Realized-vol estimators come
from the standard literature (close-to-close; Yang-Zhang, which is robust to
overnight gaps). IV rank/percentile need a history of past implied vol, which is
sourced from the local snapshot store (see app/store.py) and degrades gracefully
when not enough history exists yet.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from atlas.options.vendor.models import OHLC  # VENDORED: was `from app.models import OHLC`

TRADING_DAYS = 252


def log_returns(closes: Sequence[float]) -> List[float]:
    out: List[float] = []
    for i in range(1, len(closes)):
        prev, cur = closes[i - 1], closes[i]
        if prev > 0 and cur > 0:
            out.append(math.log(cur / prev))
    return out


def _stdev(values: Sequence[float]) -> Optional[float]:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(var)


def realized_vol_close_to_close(
    closes: Sequence[float], window: int = 30, trading_days: int = TRADING_DAYS
) -> Optional[float]:
    """Annualized close-to-close realized volatility (decimal)."""
    if len(closes) < 2:
        return None
    rets = log_returns(closes[-(window + 1):]) if window else log_returns(closes)
    sd = _stdev(rets)
    if sd is None:
        return None
    return sd * math.sqrt(trading_days)


def realized_vol_yang_zhang(
    bars: Sequence[OHLC], window: int = 30, trading_days: int = TRADING_DAYS
) -> Optional[float]:
    """Annualized Yang-Zhang realized volatility (decimal).

    Combines overnight, open-to-close, and Rogers-Satchell variances. Robust to
    opening gaps and drift. Needs at least ~3 usable days.
    """
    if len(bars) < 3:
        return None
    use = list(bars[-(window + 1):]) if window else list(bars)
    if len(use) < 3:
        use = list(bars)

    overnight: List[float] = []   # ln(O_i / C_{i-1})
    open_close: List[float] = []  # ln(C_i / O_i)
    rs: List[float] = []          # Rogers-Satchell term

    for i in range(1, len(use)):
        prev, cur = use[i - 1], use[i]
        if min(prev.close, cur.open, cur.high, cur.low, cur.close) <= 0:
            continue
        o = math.log(cur.open / prev.close)
        c = math.log(cur.close / cur.open)
        u = math.log(cur.high / cur.open)
        d = math.log(cur.low / cur.open)
        overnight.append(o)
        open_close.append(c)
        rs.append(u * (u - c) + d * (d - c))

    n = len(rs)
    if n < 2:
        return None

    sigma_o = _stdev(overnight)
    sigma_c = _stdev(open_close)
    if sigma_o is None or sigma_c is None:
        return None
    var_o = sigma_o ** 2
    var_c = sigma_c ** 2
    var_rs = sum(rs) / n

    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    yz_var = var_o + k * var_c + (1.0 - k) * var_rs
    if yz_var <= 0:
        # Fall back to close-to-close if the estimator goes non-positive.
        return realized_vol_close_to_close([b.close for b in use], window, trading_days)
    return math.sqrt(yz_var * trading_days)


def hv_from_bars(bars: Sequence[OHLC], window: int) -> Optional[float]:
    """Best-available realized vol: Yang-Zhang, falling back to close-to-close."""
    hv = realized_vol_yang_zhang(bars, window)
    if hv is None:
        hv = realized_vol_close_to_close([b.close for b in bars], window)
    return hv


def atm_iv_from_pairs(
    underlying: float, pairs: Sequence[Tuple[float, Optional[float]]]
) -> Optional[float]:
    """Implied vol of the strike nearest the underlying (the ATM IV)."""
    best: Optional[float] = None
    best_dist = float("inf")
    for strike, iv in pairs:
        if iv is None or iv <= 0:
            continue
        dist = abs(strike - underlying)
        if dist < best_dist:
            best_dist = dist
            best = iv
    return best


def iv_vs_hv_ratio(iv: Optional[float], hv: Optional[float]) -> Optional[float]:
    """IV / HV. <1 = options cheap vs realized movement; >1 = expensive."""
    if iv is None or hv is None or hv <= 0:
        return None
    return iv / hv


def iv_rank(current: Optional[float], history: Sequence[float]) -> Optional[float]:
    """IV Rank (0-100): position of current IV within its historical [min, max].

    Returns None if there isn't enough history or the range is degenerate.
    """
    if current is None or len(history) < 10:
        return None
    lo, hi = min(history), max(history)
    if hi - lo < 1e-9:
        return None
    return max(0.0, min(100.0, (current - lo) / (hi - lo) * 100.0))


def iv_percentile(current: Optional[float], history: Sequence[float]) -> Optional[float]:
    """IV Percentile (0-100): share of historical days with IV below current."""
    if current is None or len(history) < 10:
        return None
    below = sum(1 for v in history if v < current)
    return below / len(history) * 100.0

