"""Instrument-agnostic PRICE-ACTION CORE - the buy-low / sell-high rebuild (2026-07-07, M4).

A pure `OHLCV arrays -> BuyLowSignal` function. Every feature is BARS-parameterized (never wall-clock /
session) and SCALE-FREE (bounded oscillator, %, or ATR-multiple), so the SAME code scores a $3 stock and
$60k BTC identically - the "trade crypto blindly" litmus. Context (catalysts, WSB, fundamentals) lives
DOWNSTREAM as a confirm/veto informer; it never originates a buy here.

Research verdict (2026-07-07 sweep, adversarially verified): pure intraday OHLCV edge is ~null after costs;
the ONE survivable buy-low edge is DIP-IN-UPTREND MEAN-REVERSION - buy oversold weakness INSIDE an uptrend
at PROVEN support, in a range regime. EARLY-WAVE (first pullback near a rising mean in a TREND regime) is the
regime-gated secondary. The keystone ANTI-PEAK rule (extension >= veto ATR above the mean) rejects the chase
that lost 7/7 for BOTH archetypes - this is the same rule armed at the context gate in M3 (extended_above_mean).

This module does NOT decide sizing/stops-of-record or touch the broker; it emits a signal the cascade + risk
engine consume (wired into detect()/discovery in M5, exits in M6). Survival rails are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from atlas.signals import features as F


@dataclass(frozen=True)
class PriceActionParams:
    trend_sma: int = 200            # long-term uptrend filter (Connors: buy dips only above the 200-SMA)
    ema_mean: int = 21              # the "mean" for extension + early-wave pullback (EMA21 ~ EMA20)
    atr_period: int = 14
    dip_rsi_max: float = 10.0       # RSI-2 < this = oversold (wide-basin: anything in [5,15] works)
    bb_period: int = 20
    bb_std: float = 2.0
    dip_pctb_max: float = 0.10      # %b < this = at/below the lower Bollinger band (deep dip)
    swing_k: int = 3                # fractal swing-low half-width (k bars strictly-higher each side)
    support_band_atr: float = 0.25  # a level within max(0.25*ATR, 0.0015*price) of price is "at" it
    support_band_frac: float = 0.0015
    min_support_families: int = 2   # "strongly supported" = >= this many independent families confluent
    extension_veto_atr: float = 1.5      # (price - ema_mean)/ATR >= this => extended chase => veto (M3 keystone)
    early_wave_max_ext: float = 0.5      # early-wave must sit within this many ATR of the mean (pulled back)
    er_period: int = 10
    er_trend_min: float = 0.35           # efficiency ratio >= this AND adx>=trend_min => TREND regime
    adx_period: int = 14
    adx_trend_min: float = 25.0
    adx_range_max: float = 20.0          # adx < this (or er low) => RANGE regime (dip edge lives here)
    reclaim_body_min: float = 0.5        # bar body (close-open)/(high-low) >= this = a real reclaim bar
    stop_atr: float = 0.5                # structural stop = support - stop_atr*ATR (R is defined off this)


@dataclass(frozen=True)
class BuyLowSignal:
    archetype: str                  # "supported_dip" | "early_wave" | "" (no buy-low trigger)
    passed: bool                    # a tradeable buy-low trigger is live
    score: float                    # buy-low quality in [0,1] (0 when no trigger)
    reason: str                     # why it did / didn't fire (for the context-drop / survivor logs)
    regime: str                     # "trend" | "range" | "unknown"
    support: float | None           # the support level the entry sits on (None if not supported)
    stop: float | None              # structural stop below support (defines R for the exit engine, M6)
    target: float | None            # SELL-HIGH level (M6): mean-reversion snap-back = max(mean, entry+1*ATR)
                                    # for supported_dip; None for early_wave (it RIDES the trailing stop)
    extension: float | None         # ATR-multiples of price above the mean (>= veto => a chase)
    rsi2: float | None
    pct_b: float | None
    support_families: int           # count of confluent support families near price


def _clamp01(x: float) -> float:
    if x != x:                      # nan
        return 0.0
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def swing_lows(low: np.ndarray, k: int) -> list[int]:
    """Indices i (k <= i < n-k) where low[i] is a STRICT fractal pivot low: lower than all k bars on each
    side. A pivot that later gets touched again is where demand has defended price - real support.

    Vectorized (2026-07-07, M7): the backtest calls this on the FULL trailing slice at every bar (detect()
    re-runs the core per bar), so the old per-bar Python loop was O(n^2) Python and made the historical walk
    intractable. This numpy form is byte-identical (proven by test_swing_lows_are_strict_fractal_pivots) and
    ~100x faster; it also shaves the live per-cycle cost."""
    low = np.asarray(low, float)
    n = len(low)
    if n < 2 * k + 1:
        return []
    piv = np.zeros(n, dtype=bool)
    core = low[k:n - k]
    ok = np.ones(len(core), dtype=bool)
    for j in range(1, k + 1):
        ok &= core < low[k - j:n - k - j]        # strictly below the j-th LEFT neighbor
        ok &= core < low[k + j:n - k + j]        # strictly below the j-th RIGHT neighbor
    piv[k:n - k] = ok
    return [int(i) for i in np.nonzero(piv)[0]]


def support_families(open_, high, low, close, volume, price: float, atr: float,
                     p: PriceActionParams) -> tuple[int, float | None, dict[str, float]]:
    """The confluent support FAMILIES at/below `price` (all trailing-rolling + scale-free). Returns
    (count within the confluence band, the support LEVEL price is sitting on, all family levels).
    Families: fractal swing lows, the N-bar Donchian low, the lower Bollinger band, and the rolling VWAP - 
    four INDEPENDENT ways to read demand, so a confluence of >=2 is a genuinely defended level, not one MA."""
    high = np.asarray(high, float); low = np.asarray(low, float)
    close = np.asarray(close, float); volume = np.asarray(volume, float)
    fam: dict[str, float] = {}

    sl = swing_lows(low, p.swing_k)
    below = [float(low[i]) for i in sl if low[i] <= price * (1.0 + p.support_band_frac)]
    if below:
        fam["swing_low"] = max(below)                            # the nearest defended pivot at/below price
    if len(low) >= p.bb_period:
        fam["donchian_low"] = float(np.min(low[-p.bb_period:]))
    _, _, bb_lo = F.bollinger(close, p.bb_period, p.bb_std)
    if len(bb_lo) and not np.isnan(bb_lo[-1]):
        fam["bb_lower"] = float(bb_lo[-1])
    vw = F.vwap(high, low, close, volume, p.bb_period)
    if len(vw) and not np.isnan(vw[-1]):
        fam["vwap"] = float(vw[-1])

    band = max(p.support_band_atr * atr, p.support_band_frac * price)
    near = {k: v for k, v in fam.items() if abs(price - v) <= band}
    # the support price is sitting ON = the highest near-level that is at/below price
    at_or_below = [v for v in near.values() if v <= price * (1.0 + p.support_band_frac)]
    level = max(at_or_below) if at_or_below else None
    return len(near), level, fam


def score_buy_low(open_, high, low, close, volume, params: PriceActionParams = PriceActionParams()) -> BuyLowSignal:
    """Score the CURRENT (last) bar for buy-low quality. Pure; safe on any length (returns a no-trigger
    signal on short history). Never raises."""
    o = np.asarray(open_, float); h = np.asarray(high, float); l = np.asarray(low, float)
    c = np.asarray(close, float); v = np.asarray(volume, float)
    p = params

    def _none(reason: str, regime: str = "unknown", support=None, extension=None,
              rsi2=None, pb=None, fams: int = 0) -> BuyLowSignal:
        return BuyLowSignal("", False, 0.0, reason, regime, support, None, None, extension, rsi2, pb, fams)

    n = len(c)
    if n < 30 or len(h) != n or len(l) != n or len(o) != n or len(v) != n:
        return _none("short_history")

    price = float(c[-1]); last_open = float(o[-1]); last_high = float(h[-1]); last_low = float(l[-1])
    atr = float(F.atr(h, l, c, p.atr_period)[-1])
    if atr != atr or atr <= 0:                                   # nan or non-positive
        return _none("no_atr")

    sma_t = float(F.sma(c, p.trend_sma)[-1])
    ema_m = float(F.ema(c, p.ema_mean)[-1])
    rsi2 = float(F.rsi2(c)[-1])
    pb = float(F.pct_b(c, p.bb_period, p.bb_std)[-1])
    er = float(F.efficiency_ratio(c, p.er_period)[-1])
    adx = float(F.adx(h, l, c, p.adx_period)[-1])
    vol_z = float(F.volume_zscore(v, p.bb_period)[-1])
    extension = (price - ema_m) / atr if ema_m == ema_m else None

    # Regime (Efficiency-Ratio + ADX vote). TREND => early-wave momentum; RANGE => dip mean-reversion.
    if er == er and adx == adx and er >= p.er_trend_min and adx >= p.adx_trend_min:
        regime = "trend"
    elif (er != er or er < p.er_trend_min) and (adx != adx or adx < p.adx_range_max):
        regime = "range"
    else:
        regime = "unknown"

    # Mandatory uptrend filter (fail-OPEN on short history where SMA200 is nan - the litmus/crypto path).
    uptrend = (sma_t != sma_t) or price > sma_t
    # Keystone anti-peak veto (mirrors the M3 context gate): extended far above the mean = a chase, not a dip.
    extended = extension is not None and extension >= p.extension_veto_atr

    # Confluence is measured where price TESTED support (the bar's LOW), not at the reclaimed close - the
    # close sits ABOVE support after a reclaim, so probing at the close would miss the level it bounced off.
    n_fam, support, _fam = support_families(o, h, l, c, v, last_low, atr, p)
    strongly_supported = n_fam >= p.min_support_families and support is not None

    # Proven-hold RECLAIM bar: price dipped to/through support, then reclaimed it on a real green body with
    # participation - buy the HOLD, not the touch (avoids catching a falling knife).
    rng = last_high - last_low
    body = (price - last_open) / rng if rng > 0 else 0.0
    reclaim = (support is not None and last_low <= support * (1.0 + p.support_band_frac) and price > support
               and price > last_open and body >= p.reclaim_body_min and (vol_z != vol_z or vol_z > 0))

    if not uptrend:
        return _none("not_uptrend", regime, support, extension, rsi2, pb, n_fam)
    if extended:
        return _none("extended_above_mean", regime, support, extension, rsi2, pb, n_fam)

    # --- SUPPORTED_DIP (primary): range/unknown regime, oversold, at proven support, reclaimed.
    if (regime in ("range", "unknown") and rsi2 == rsi2 and rsi2 < p.dip_rsi_max
            and strongly_supported and reclaim):
        s_oversold = _clamp01((p.dip_rsi_max - rsi2) / p.dip_rsi_max)             # deeper oversold = higher
        s_conf = _clamp01(n_fam / 4.0)                                           # more families = higher
        s_pctb = _clamp01((p.dip_pctb_max - pb) / 0.30) if pb == pb else 0.5     # further below the band = higher
        s_unext = _clamp01(1.0 - (extension or 0.0) / p.extension_veto_atr)      # closer to the mean = higher
        score = 0.35 * s_oversold + 0.25 * s_conf + 0.20 * s_pctb + 0.20 * s_unext
        stop = support - p.stop_atr * atr
        # SELL HIGH (M6): the dip reverts TO its mean. Target = the mean (EMA21), floored at entry+1*ATR so a
        # dip that reclaimed right below the mean still books a real move. Not-extended guarantees mean-price
        # <= 1.5*ATR, so this is a NEAR, intraday-reachable target (vs the trend setups' far 25% backstop).
        target = max(ema_m, price + atr)
        return BuyLowSignal("supported_dip", True, round(float(score), 4), "dip_at_support_reclaim",
                            regime, support, round(stop, 6), round(float(target), 6),
                            round(extension, 4) if extension is not None else None,
                            round(rsi2, 4), round(pb, 4) if pb == pb else None, n_fam)

    # --- EARLY_WAVE (secondary): a STRONG-TREND name (high ADX - trend strength survives a shallow pullback
    # even as the efficiency ratio momentarily dips) pulled back NEAR the rising mean (not extended) and
    # reclaimed off support. Gated on ADX, not the instantaneous regime tag, because ER droops during the
    # very pullback we want to buy. Threshold calibration (dynamic-MA vs horizontal support) is refined in
    # M7's backtest on real trending data; conservative here (still requires a support level to bounce off).
    if (adx == adx and adx >= p.adx_trend_min and extension is not None
            and extension <= p.early_wave_max_ext and reclaim):
        s_pull = _clamp01(1.0 - abs(extension) / p.early_wave_max_ext)           # right at the mean = higher
        s_trend = _clamp01((adx - p.adx_trend_min) / p.adx_trend_min) if adx == adx else 0.5
        s_conf = _clamp01(n_fam / 4.0)
        score = 0.40 * s_pull + 0.30 * s_trend + 0.30 * s_conf
        stop = (support if support is not None else ema_m - atr) - p.stop_atr * atr
        # early_wave RIDES the trailing stop (open-ended trend continuation) -> no fixed target (None).
        return BuyLowSignal("early_wave", True, round(float(score), 4), "early_pullback_in_trend",
                            regime, support, round(stop, 6), None, round(extension, 4),
                            round(rsi2, 4) if rsi2 == rsi2 else None, round(pb, 4) if pb == pb else None, n_fam)

    return _none("no_trigger", regime, support, extension, rsi2, pb, n_fam)
