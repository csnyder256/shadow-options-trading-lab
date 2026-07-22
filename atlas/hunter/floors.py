"""FLOOR MAP - multi-family demand-zone engine for the Floor Hunter (P1a).

Pure: numpy arrays in, `FloorMap` out. No IO, no clock, no config reads. The SAME function runs in
the replay gate and the live Hunter, so replay==live by construction.

CAUSALITY IS STRUCTURAL, NOT PROCEDURAL. `build_floor_map(..., asof_idx=i)` slices every input to
[:i+1] internally before computing anything; the peek-detector test feeds poisoned future bars and
asserts the output is unchanged. Prior-day levels come from the caller (known pre-open); premarket
levels are optional (live-only - the Alpaca IEX cache is RTH-only, so replay runs without them and
live can only be STRONGER than the tested config).

Level families and weights follow the approved plan (research-calibrated; see the ledger):
  session VWAP (2.0; only 1.0 when falling)  ·  catalyst-anchored AVWAP (2.0)  ·  prior-day low /
  close (2.0 / 1.5) and prior-day high-as-support (1.5)  ·  premarket low (2.0) / high (1.0)  ·
  30-min opening-range low (1.0, valid only once formed)  ·  intraday fractal swing lows (1.0 each,
  max 2 counted, must be >= min_age old)  ·  volume shelves / HVN edges from 1-min volume-at-price
  (1.0; LVN = veto tag)  ·  round numbers (1.0 below $20, 0.5 above).
Standalone Fibonacci is DROPPED (tests no better than random); the 40-60% retrace-of-the-catalyst-leg
survives only as a DEPTH measure the stalker gates on (`FloorMap.retrace_frac`).

Zone modifiers (applied to the summed family weights): +1 first test today; -2 tested >= 3x today
(liquidity consumed); -2 zone below BOTH VWAPs (bear regime - no longs). The midday penalty is
time-of-day, so it lives in the stalker, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from atlas.signals import features as F
from atlas.signals.price_action import swing_lows

OR_MINUTES = 30                       # 30-min opening range (15-min ORs break both ways 56% of days)
_OPEN_MIN = 9 * 60 + 30               # 09:30 ET in minutes-of-day


@dataclass(frozen=True)
class FloorParams:
    zone_half_width_atr5m: float = 0.30
    zone_half_width_frac: float = 0.0015
    zone_min_families: int = 2
    zone_min_score: float = 3.0
    max_chase_atr5m: float = 0.35
    swing_k: int = 3                  # fractal half-width on 1-min lows
    swing_min_age_bars: int = 30      # a pivot must be >= 30 min old to count as a defended level
    swing_max_count: int = 2
    shelf_bin_atr5m: float = 0.30     # volume-at-price bin width = max(this*ATR5m, 0.001*price)
    shelf_bin_frac: float = 0.001
    shelf_hvn_mult: float = 1.5       # bin mass >= this * median bin mass => HVN shelf
    shelf_lvn_mult: float = 0.5       # bin mass <= this * median bin mass => LVN (veto tag)
    round_grid_lt20: float = 0.50     # round-number grid below $20 ...
    round_grid_lt50: float = 1.00     # ... $20-50 ...
    round_grid_ge50: float = 5.00     # ... and above $50
    vwap_slope_bars: int = 15         # session-VWAP rising = VWAP now > VWAP 15 one-min bars ago
    search_below_daily_atr: float = 1.0   # primary zone must sit within this many DAILY ATR below price
    search_above_atr5m: float = 0.5   # collect levels up to this far ABOVE price (zone may straddle)


@dataclass(frozen=True)
class Level:
    family: str
    price: float
    weight: float


@dataclass(frozen=True)
class DemandZone:
    top: float
    bottom: float
    score: float                      # summed distinct-family weights + modifiers
    families: tuple[str, ...]         # distinct families in the zone (sorted)
    levels: tuple[Level, ...] = field(repr=False, default=())
    touches_today: int = 0            # completed tests of the zone before asof
    first_test: bool = True
    in_lvn: bool = False              # zone center sits in a low-volume node => first-touch veto tag
    below_both_vwaps: bool = False

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0


@dataclass(frozen=True)
class FloorMap:
    zones: tuple[DemandZone, ...]     # score-ranked, best first; () when nothing qualifies
    max_chase: float                  # primary.top + max_chase_atr5m*ATR5m (nan when no zones)
    atr5m: float
    session_vwap: float
    vwap_rising: bool
    avwap_catalyst: float             # anchored VWAP from the catalyst/session anchor
    hod: float
    impulse_low: float                # low of the catalyst leg (anchor..HOD)
    retrace_frac: float               # how much of the leg the CURRENT price has retraced (0..1+, nan if no leg)
    lvns: tuple[float, ...] = ()

    @property
    def primary(self) -> DemandZone | None:
        return self.zones[0] if self.zones else None


def _atr5m_asof(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> float:
    """5-min ATR14 from today's 1-min bars, with graceful degradation early in the session:
    full ATR14 once ~75 min have printed, else the mean 5-min true range, else a 1-min proxy."""
    n = len(c)
    if n == 0:
        return float("nan")
    m = n // 5
    if m >= 2:
        h5 = np.array([h[i * 5:(i + 1) * 5].max() for i in range(m)])
        l5 = np.array([l[i * 5:(i + 1) * 5].min() for i in range(m)])
        c5 = np.array([c[(i + 1) * 5 - 1] for i in range(m)])
        a = F.atr(h5, l5, c5, 14)
        if not np.isnan(a[-1]) and a[-1] > 0:
            return float(a[-1])
        tr = F.true_range(h5, l5, c5)
        tr = tr[~np.isnan(tr)]
        if len(tr) and tr.mean() > 0:
            return float(tr.mean())
    tr1 = F.true_range(h, l, c)
    tr1 = tr1[~np.isnan(tr1)]
    return float(tr1.mean() * np.sqrt(5.0)) if len(tr1) and tr1.mean() > 0 else float("nan")


def _round_levels(price: float, lo_bound: float, p: FloorParams) -> list[float]:
    grid = p.round_grid_lt20 if price < 20 else (p.round_grid_lt50 if price < 50 else p.round_grid_ge50)
    first = np.floor(price / grid) * grid
    out, lvl = [], first
    while lvl >= lo_bound - grid:
        out.append(round(float(lvl), 4))
        lvl -= grid
    return out


def _volume_profile(h, l, c, v, price: float, atr5: float, p: FloorParams
                    ) -> tuple[list[float], list[float]]:
    """(HVN shelf prices, LVN prices) from a volume-at-typical-price histogram of the given bars."""
    if len(c) < 10 or not np.isfinite(atr5) or atr5 <= 0:
        return [], []
    typ = (np.asarray(h) + np.asarray(l) + np.asarray(c)) / 3.0
    vol = np.asarray(v, float)
    bin_w = max(p.shelf_bin_atr5m * atr5, p.shelf_bin_frac * price)
    lo_b, hi_b = float(typ.min()), float(typ.max())
    if hi_b - lo_b < bin_w:
        return [], []
    nbins = int(np.ceil((hi_b - lo_b) / bin_w))
    mass, edges = np.histogram(typ, bins=nbins, range=(lo_b, lo_b + nbins * bin_w), weights=vol)
    centers = (edges[:-1] + edges[1:]) / 2.0
    med = np.median(mass[mass > 0]) if (mass > 0).any() else 0.0
    if med <= 0:
        return [], []
    hvn, lvn = [], []
    for i in range(len(mass)):
        left = mass[i - 1] if i > 0 else -np.inf
        right = mass[i + 1] if i < len(mass) - 1 else -np.inf
        if mass[i] >= p.shelf_hvn_mult * med and mass[i] >= left and mass[i] >= right:
            hvn.append(round(float(centers[i]), 4))
        elif mass[i] <= p.shelf_lvn_mult * med:
            lvn.append(round(float(centers[i]), 4))
    return hvn, lvn


def _zone_touches(l: np.ndarray, c: np.ndarray, top: float, bottom: float) -> int:
    """Completed tests of [bottom, top] so far today: entries of the bar LOW into the zone from
    above, counted once per excursion (consecutive in-zone bars = one test)."""
    in_zone = (l <= top) & (c >= bottom)          # low reached the zone; close not collapsed through
    touches, prev = 0, False
    for flag in in_zone:
        if flag and not prev:
            touches += 1
        prev = bool(flag)
    return touches


def build_floor_map(
    open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray,
    minute_of_day: np.ndarray,            # int minutes since midnight ET, aligned to the bars
    *,
    asof_idx: int,
    prior_day: dict | None = None,        # {"high": .., "low": .., "close": ..} from the PRIOR session
    premarket: dict | None = None,        # {"high": .., "low": ..} - live only; absent in replay
    prior_day_bars: dict | None = None,   # optional {"high","low","close","volume"} 1-min arrays of the prior session
    catalyst_anchor_idx: int = 0,         # bar index the catalyst leg is anchored at (0 = session open)
    daily_atr: float | None = None,       # prior-session daily ATR14 in price units (search radius)
    params: FloorParams = FloorParams(),
) -> FloorMap:
    """Rank demand zones below the current price from data through `asof_idx` ONLY. Never raises;
    returns an empty map on degenerate input."""
    p = params
    end = max(0, min(int(asof_idx), len(close) - 1)) + 1
    o = np.asarray(open_, float)[:end]; h = np.asarray(high, float)[:end]
    l = np.asarray(low, float)[:end]; c = np.asarray(close, float)[:end]
    v = np.asarray(volume, float)[:end]; mod = np.asarray(minute_of_day, int)[:end]

    empty = FloorMap((), float("nan"), float("nan"), float("nan"), False, float("nan"),
                     float("nan"), float("nan"), float("nan"))
    if len(c) < 3 or not np.isfinite(c[-1]) or c[-1] <= 0:
        return empty
    price = float(c[-1])
    atr5 = _atr5m_asof(o, h, l, c)
    if not np.isfinite(atr5) or atr5 <= 0:
        return empty

    # --- dynamic anchors -------------------------------------------------------------------------
    svwap_arr = F.vwap_session(h, l, c, v, np.zeros(len(c)))       # one session => constant id
    svwap = float(svwap_arr[-1])
    back = min(p.vwap_slope_bars, len(c) - 1)
    vwap_rising = bool(svwap > svwap_arr[-1 - back]) if back > 0 else False

    a0 = max(0, min(int(catalyst_anchor_idx), len(c) - 1))
    typ = (h + l + c) / 3.0
    pv = float(np.sum(typ[a0:] * v[a0:])); vv = float(np.sum(v[a0:]))
    avwap = pv / vv if vv > 0 else price

    hod_idx = int(np.argmax(h[a0:])) + a0
    hod = float(h[hod_idx])
    impulse_low = float(np.min(l[a0:hod_idx + 1]))
    leg = hod - impulse_low
    retrace_frac = float((hod - price) / leg) if leg > 0 else float("nan")

    # --- harvest levels ---------------------------------------------------------------------------
    lo_bound = price - (daily_atr if daily_atr and np.isfinite(daily_atr) and daily_atr > 0
                        else 6.0 * atr5) * p.search_below_daily_atr
    hi_bound = price + p.search_above_atr5m * atr5

    levels: list[Level] = []

    def _add(family: str, lvl: float | None, weight: float) -> None:
        if lvl is None or not np.isfinite(lvl):
            return
        if lo_bound <= lvl <= hi_bound:
            levels.append(Level(family, float(lvl), weight))

    _add("session_vwap", svwap, 2.0 if vwap_rising else 1.0)
    _add("avwap_catalyst", avwap, 2.0)
    if prior_day:
        _add("prior_day_low", prior_day.get("low"), 2.0)
        _add("prior_day_close", prior_day.get("close"), 1.5)
        _add("prior_day_high", prior_day.get("high"), 1.5)     # support once price is above it
    if premarket:
        _add("premarket_low", premarket.get("low"), 2.0)
        _add("premarket_high", premarket.get("high"), 1.0)

    or_mask = mod < _OPEN_MIN + OR_MINUTES
    if or_mask.any() and int(mod[-1]) >= _OPEN_MIN + OR_MINUTES:   # only once the 30-min OR has FORMED
        _add("or_low_30m", float(l[or_mask].min()), 1.0)

    piv = swing_lows(l, p.swing_k)
    aged = [i for i in piv if (len(c) - 1 - i) >= p.swing_min_age_bars]
    below = sorted((float(l[i]) for i in aged if l[i] <= hi_bound), reverse=True)
    for lvl in below[: p.swing_max_count]:
        _add("swing_low", lvl, 1.0)

    hvn_t, lvn_t = _volume_profile(h, l, c, v, price, atr5, p)
    hvn_p, lvn_p = ([], [])
    if prior_day_bars:
        hvn_p, lvn_p = _volume_profile(
            np.asarray(prior_day_bars["high"], float), np.asarray(prior_day_bars["low"], float),
            np.asarray(prior_day_bars["close"], float), np.asarray(prior_day_bars["volume"], float),
            price, atr5, p)
    for lvl in hvn_t + hvn_p:
        _add("volume_shelf", lvl, 1.0)
    lvns = tuple(sorted(set(lvn_t + lvn_p)))

    round_w = 1.0 if price < 20 else 0.5
    for lvl in _round_levels(price, lo_bound, p):
        _add("round", lvl, round_w)

    if not levels:
        return FloorMap((), float("nan"), atr5, svwap, vwap_rising, avwap, hod, impulse_low,
                        retrace_frac, lvns)

    # --- cluster into zones -----------------------------------------------------------------------
    half_w = max(p.zone_half_width_atr5m * atr5, p.zone_half_width_frac * price)
    levels.sort(key=lambda lv: lv.price, reverse=True)
    clusters: list[list[Level]] = []
    for lv in levels:
        if clusters and (clusters[-1][-1].price - lv.price) <= 2.0 * half_w:
            clusters[-1].append(lv)
        else:
            clusters.append([lv])

    zones: list[DemandZone] = []
    for cl in clusters:
        fams: dict[str, float] = {}
        for lv in cl:                                   # distinct families only; keep the max weight
            fams[lv.family] = max(fams.get(lv.family, 0.0), lv.weight)
        if len(fams) < p.zone_min_families:
            continue
        top = max(lv.price for lv in cl) + half_w
        bottom = min(lv.price for lv in cl) - half_w
        if bottom > price:                              # zone entirely above price = not a demand zone
            continue
        touches = _zone_touches(l, c, top, bottom)
        center = (top + bottom) / 2.0
        in_lvn = any(abs(center - x) <= half_w for x in lvns)
        below_both = bool(top < svwap and top < avwap)
        score = sum(fams.values())
        score += 1.0 if touches == 0 else 0.0
        score -= 2.0 if touches >= 3 else 0.0
        score -= 2.0 if below_both else 0.0
        if score < p.zone_min_score:
            continue
        zones.append(DemandZone(round(top, 6), round(bottom, 6), round(score, 3),
                                tuple(sorted(fams)), tuple(cl), touches, touches == 0,
                                in_lvn, below_both))

    zones.sort(key=lambda z: (z.score, z.top), reverse=True)
    if not zones:
        return FloorMap((), float("nan"), atr5, svwap, vwap_rising, avwap, hod, impulse_low,
                        retrace_frac, lvns)
    max_chase = zones[0].top + p.max_chase_atr5m * atr5
    return FloorMap(tuple(zones), round(max_chase, 6), atr5, svwap, vwap_rising, avwap,
                    hod, impulse_low, retrace_frac, lvns)
