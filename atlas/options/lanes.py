"""SIGNAL LANES (O3) - pure per-lane detectors for the OPTIONS SHADOW TRADER.

Each lane is a class with `update(ctx) -> LaneSignal | None` (fed COMPLETED 1-min bars via
MinuteCtx) and `invalidated(pos_ctx) -> bool` (the lane's own thesis-invalidation rule, polled by
the exit engine's thesis_valid input). Everything here is PURE: no clock reads, no IO, no network
 - historical inputs (noise profiles) are computed by `build_noise_profile` from a caller-supplied
1-min DataFrame and injected. Lane instances are constructed fresh each session by the runner
(scripts/run_options_shadow.py), so per-day dedup state is per-instance.

Lanes (plan "Signal lanes", 2026-07-09; Lane 4 = measurement stub only):
  * Lane 1  "index_trend" - noise-area break + VWAP side, 5-min-boundary confirmed,
                               14d realized-range percentile >= 50 MANDATORY.
  * Lane 1b "last30" - 15:30 continuation when |open->15:30| > 0.5 x 14d avg daily range;
                               contract preference one_dte_only; clock-bound (never invalidated - 
                               the exit engine's 0DTE/EOD rules govern).
  * Lane 2  "inplay_orb" - premarket gap/catalyst candidates, first-5-min RVOL >= 5,
                               5-min opening-range break; target = 2 x OR height.
  * Lane 3  "macro_reaction" - CPI/NFP 09:30->09:45 reaction (emit 09:45), FOMC 14:00->14:15
                               (emit 14:15); NEVER pre-print: emission waits for a clean
                               (blackout-free) bar, direction stays the measured-window sign.

Interpretations pinned here (documented, not silent):
  * "confirmed on a :00/:30 5-min boundary close": bars are left-labeled, so a 1-min bar with
    minute m closes at m+1; the 5-min grid from 09:30 closes at minutes where (m + 1) % 5 == 0.
    A break that has faded by the boundary close never fires (the boundary close itself must
    still be outside the noise area on the right VWAP side - it IS a 1-min close break).
  * "gap-adjusted" noise: the minute-level move is measured from TODAY'S OPEN (not the prior
    close), so the overnight gap never inflates the intraday noise width.
  * 14-day realized-range percentile: percentile rank of the most recent COMPLETE session's
    high-low range within the trailing window's ranges (0-100); < 50 = dead-vol regime, lane 1
    stands down for the day (the unconditional version is dead post-2015).
  * Lane 2 RVOL baseline (opts-fix-lane2-rvol-scale-v1, 2026-07-10): first-5-min CONSOLIDATED
    volume (live bars = Tradier day-cum-volume deltas) vs (Tradier 90d average_volume x
    FIRST5_UCURVE_FRAC) - UNIFORMLY. The 1-min cache is Alpaca IEX single-venue (~2-3% of
    tape), so its avg_first5_volume must never gate against consolidated live volume (it
    inflated RVOL ~30-50x for cache-backed names, making rvol_min=5 pass on noise); the cache
    keeps serving the PRICE-based noise/range stats it is correct for. The intraday volume
    U-curve front-loads ~4% of a day's volume into the first 5 minutes (open auction + first
    prints), so FIRST5_UCURVE_FRAC = 0.04 - a fixed, documented approximation (registered
    plan-era constant, opts-calib-plan-era-constants-v1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ------------------------------------------------------------------ session constants
OPEN_MIN = 9 * 60 + 30            # 09:30 ET = minute 570
CLOSE_MIN = 16 * 60               # 16:00 ET = minute 960
RTH_MINUTES = 390
TRADING_YEAR_DAYS = 252.0
FIRST5_UCURVE_FRAC = 0.04         # documented fallback: share of day volume in the first 5 min
# audit 2026-07-16 Wave 2.13 (EXIT-ENGINE-1/RUNNER-2/TIMESCALE-STACK-1): thesis invalidation
# re-enters the noise area only INSIDE a fraction of the band (hysteresis), and the band is
# FROZEN at its entry-time width (PositionCtx.frozen_band) so the growing intraday average
# cannot chase a stalling position. CALIBRATION - registered opts-audit-wave2-exitv3-v1.
THESIS_HYSTERESIS_FRAC = 0.8
# audit 2026-07-16 Wave 1.11 (latch-at-entry): a lane fire that dies at the selector re-arms
# after this many minutes while the predicate still holds; a CONFIRMED entry latches for the
# day. CALIBRATION - registered opts-audit-wave1-funnel-v1.
RELEASE_COOLDOWN_MIN = 30

MIN_HORIZON_T = 1.0 / (TRADING_YEAR_DAYS * RTH_MINUTES)


# ------------------------------------------------------------------ shared inputs
@dataclass(frozen=True)
class MinuteCtx:
    """One COMPLETED left-labeled 1-min bar + causal session context (runner-built from
    LiveBarBuilder). `minute` is the bar's START minute-of-day ET; it closes at minute+1."""
    symbol: str
    minute: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    session_open: float           # today's 09:30 open trade price
    svwap: float                  # session VWAP as of this bar
    blackout: str | None = None   # events.in_blackout(now) at the bar close (runner-supplied)


@dataclass(frozen=True)
class PositionCtx:
    """The lane-facing view of an open position's latest underlying mark (for invalidation).
    Audit 2026-07-16 Wave 2.13: `close`/`minute` are the last COMMITTED bar's values (never a
    raw poll tick), and `frozen_band` carries the entry-time noise width so invalidation is
    judged against the band that admitted the entry (0.0 = legacy growing-band behavior)."""
    symbol: str
    direction: str                # "call" | "put"
    minute: int
    close: float                  # latest COMMITTED underlying close
    svwap: float
    session_open: float
    frozen_band: float = 0.0      # entry-time noise width (index_trend); 0 = use current band


@dataclass(frozen=True)
class LaneSignal:
    lane: str
    underlying: str
    direction: str                # "call" | "put"
    target_move: float            # fractional underlying move (always positive magnitude)
    p_thesis: float
    horizon_T: float              # planned hold, TRADING years
    mu_thesis: float              # annualized drift implied by target over horizon (signed)
    expires_minute: int           # runner discards the signal after this ET minute
    notes: dict = field(default_factory=dict)


def _is_5min_boundary_close(minute: int) -> bool:
    """Left-labeled bar `minute` closes at minute+1; the 09:30-anchored 5-min grid closes when
    (minute + 1) % 5 == 0 (09:30 = 570 is itself a multiple of 5)."""
    return (minute + 1) % 5 == 0


def _rest_of_day_T(minute: int, close_min: int = CLOSE_MIN) -> float:
    """Trading-years from this bar's CLOSE (minute+1) to today's session close (16:00 normal;
    13:00 half days - the runner passes the session calendar's per-day value)."""
    remaining = max(0, close_min - (minute + 1))
    return max(remaining / RTH_MINUTES / TRADING_YEAR_DAYS, MIN_HORIZON_T)


def _mu_from_target(target_move: float, horizon_T: float, direction: str) -> float:
    """Annualized drift that carries the underlying to the (signed) target over the horizon - 
    the same convention as selector's ev_hold_thesis."""
    signed = abs(target_move) if direction == "call" else -abs(target_move)
    return math.log(1.0 + signed) / max(horizon_T, MIN_HORIZON_T)


# ------------------------------------------------------------------ noise profile (lane 1 / 1b / 2)
@dataclass(frozen=True)
class NoiseProfile:
    """14-day minute-level noise statistics for one underlying, computed OFFLINE from cached
    1-min bars (build_noise_profile) and injected - the lane never does IO."""
    symbol: str
    minutes: tuple                # sorted minute-of-day keys the arrays below are indexed by
    noise_by_minute: tuple        # avg |close(m)/day_open - 1| per minute key (gap-adjusted)
    remaining_range_by_minute: tuple  # avg (max high[t>=m] - min low[t>=m]) / day_open
    avg_daily_range: float        # mean (high-low)/open over the window
    range_percentile_14d: float   # latest complete session's range pct-rank in the window (0-100)
    avg_first5_volume: float      # mean sum(volume) of the first 5 bars per session
    n_days: int

    def _lookup(self, arr: tuple, minute: int) -> float:
        """Nearest key <= minute (IEX-sparse histories skip minutes); clamps at the ends."""
        if not self.minutes:
            return 0.0
        lo, hi = 0, len(self.minutes) - 1
        if minute <= self.minutes[0]:
            return float(arr[0])
        if minute >= self.minutes[hi]:
            return float(arr[hi])
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if self.minutes[mid] <= minute:
                lo = mid
            else:
                hi = mid
        return float(arr[lo])

    def noise_at(self, minute: int) -> float:
        return self._lookup(self.noise_by_minute, minute)

    def remaining_range_at(self, minute: int) -> float:
        return self._lookup(self.remaining_range_by_minute, minute)


def build_noise_profile(symbol: str, df_1min, lookback_days: int = 14) -> NoiseProfile | None:
    """Compute the profile from a 1-min OHLCV DataFrame (tz-aware index, RTH-only - the
    runtime/intraday_cache parquet format). Pure function of its inputs. None when fewer than
    5 complete sessions exist (the lane then stands down rather than trusting thin stats)."""
    if df_1min is None or len(df_1min) == 0:
        return None
    sessions = []
    for day, g in df_1min.groupby(df_1min.index.normalize()):
        if len(g) >= 30:                      # a usable session, even IEX-sparse
            sessions.append(g)
    sessions = sessions[-int(lookback_days):]
    if len(sessions) < 5:
        return None
    per_minute_moves: dict[int, list] = {}
    per_minute_remaining: dict[int, list] = {}
    ranges: list[float] = []
    first5: list[float] = []
    for g in sessions:
        day_open = float(g["open"].iloc[0])
        if day_open <= 0:
            continue
        highs = g["high"].to_numpy(float)
        lows = g["low"].to_numpy(float)
        closes = g["close"].to_numpy(float)
        vols = g["volume"].to_numpy(float)
        mins = [int(ts.hour) * 60 + int(ts.minute) for ts in g.index]
        n = len(mins)
        # suffix extrema for the remaining-range stat
        suf_hi = [0.0] * n
        suf_lo = [0.0] * n
        hi_run, lo_run = -math.inf, math.inf
        for i in range(n - 1, -1, -1):
            hi_run = max(hi_run, highs[i])
            lo_run = min(lo_run, lows[i])
            suf_hi[i], suf_lo[i] = hi_run, lo_run
        for i, m in enumerate(mins):
            per_minute_moves.setdefault(m, []).append(abs(closes[i] / day_open - 1.0))
            per_minute_remaining.setdefault(m, []).append((suf_hi[i] - suf_lo[i]) / day_open)
        ranges.append((max(highs) - min(lows)) / day_open)
        first5.append(float(vols[: min(5, n)].sum()))
    if not ranges:
        return None
    keys = sorted(per_minute_moves)
    noise = tuple(sum(per_minute_moves[m]) / len(per_minute_moves[m]) for m in keys)
    remaining = tuple(sum(per_minute_remaining[m]) / len(per_minute_remaining[m]) for m in keys)
    latest = ranges[-1]
    pct = 100.0 * sum(1 for r in ranges if r <= latest) / len(ranges)
    return NoiseProfile(symbol=symbol.upper(), minutes=tuple(keys), noise_by_minute=noise,
                        remaining_range_by_minute=remaining,
                        avg_daily_range=sum(ranges) / len(ranges),
                        range_percentile_14d=pct,
                        avg_first5_volume=sum(first5) / len(first5) if first5 else 0.0,
                        n_days=len(ranges))


# ------------------------------------------------------------------ Lane 1: index trend-day
class IndexTrendLane:
    """Lane 1 "index_trend" (SPY/QQQ/IWM). Trigger: 1-min close beyond open +/- noise(minute)
    AND same side of session VWAP, confirmed on a 5-min boundary close; skip the whole day when
    range_percentile_14d < 50. One signal per side per day per underlying. Invalidation: VWAP
    recross or re-entry into the noise area."""

    LANE = "index_trend"

    def __init__(self, profiles: dict, *, p_thesis: float = 0.5,
                 range_percentile_min: float = 50.0, signal_ttl_min: int = 10,
                 close_min: int = CLOSE_MIN):
        self.profiles = {k.upper(): v for k, v in (profiles or {}).items() if v is not None}
        self.p_thesis = float(p_thesis)
        self.range_percentile_min = float(range_percentile_min)
        self.signal_ttl_min = int(signal_ttl_min)
        self.close_min = int(close_min)
        # latch-at-ENTRY (audit 2026-07-16 Wave 1.11): a CONFIRMED entry latches the side for
        # the day; an emission that dies downstream re-arms after RELEASE_COOLDOWN_MIN while
        # the predicate still holds (the old emission-burn latch wasted the day's only fire
        # on selector rejections).
        self._latched: set = set()            # (symbol, direction) - confirmed entries
        self._cooldown: dict = {}             # (symbol, direction) -> re-arm minute

    def update(self, ctx: MinuteCtx) -> LaneSignal | None:
        prof = self.profiles.get(ctx.symbol.upper())
        if prof is None or ctx.session_open <= 0 or ctx.close <= 0:
            return None
        if prof.range_percentile_14d < self.range_percentile_min:
            return None                        # MANDATORY vol condition - lane stands down
        if not _is_5min_boundary_close(ctx.minute):
            return None                        # confirmation happens only on the 5-min grid
        noise = prof.noise_at(ctx.minute)
        if noise <= 0:
            return None
        move = ctx.close / ctx.session_open - 1.0
        if move > noise and ctx.close > ctx.svwap > 0:
            direction = "call"
        elif move < -noise and 0 < ctx.close < ctx.svwap:
            direction = "put"
        else:
            return None
        key = (ctx.symbol.upper(), direction)
        if key in self._latched:
            return None
        cd = self._cooldown.get(key)
        if cd is not None and ctx.minute < cd:
            return None
        # pending guard: the runner either confirm_entry()s (day latch) or release()s
        # (cooldown re-arm) synchronously; a crashed handler re-arms here by timeout
        self._cooldown[key] = ctx.minute + RELEASE_COOLDOWN_MIN + 1
        horizon = _rest_of_day_T(ctx.minute, self.close_min)
        target = max(0.35 * prof.remaining_range_at(ctx.minute), 2.0 * noise)
        return LaneSignal(lane=self.LANE, underlying=ctx.symbol.upper(), direction=direction,
                          target_move=target, p_thesis=self.p_thesis, horizon_T=horizon,
                          mu_thesis=_mu_from_target(target, horizon, direction),
                          expires_minute=ctx.minute + 1 + self.signal_ttl_min,
                          notes={"noise_width": round(noise, 6),
                                 "move_from_open": round(move, 6),
                                 "range_percentile_14d": round(prof.range_percentile_14d, 1),
                                 "svwap": round(ctx.svwap, 4)})

    def invalidated(self, pos: PositionCtx) -> bool:
        """VWAP recross or re-entry into the noise area (either kills the trend-day thesis).
        Audit 2026-07-16 Wave 2.13: the band is FROZEN at its entry-time width when the caller
        supplies pos.frozen_band (the growing intraday average was chasing stalled positions),
        and re-entry means INSIDE THESIS_HYSTERESIS_FRAC x band - a marginal band-edge entry is
        no longer epsilon from its own kill barrier. (Persistence - 2 consecutive committed-
        close evaluations - is enforced runner-side.)"""
        prof = self.profiles.get(pos.symbol.upper())
        if pos.close <= 0 or pos.session_open <= 0:
            return False                       # unreadable mark never flips the thesis
        if pos.svwap > 0:
            if pos.direction == "call" and pos.close < pos.svwap:
                return True
            if pos.direction == "put" and pos.close > pos.svwap:
                return True
        band = pos.frozen_band if pos.frozen_band > 0 else (
            prof.noise_at(pos.minute) if prof is not None else 0.0)
        if band > 0 and abs(pos.close / pos.session_open - 1.0) < THESIS_HYSTERESIS_FRAC * band:
            return True                        # back INSIDE the hysteresis band
        return False

    # ---- latch-at-entry callbacks (runner-driven; audit Wave 1.11) ----------------------------
    def confirm_entry(self, symbol: str, direction: str) -> None:
        self._latched.add((symbol.upper(), direction))

    def release(self, symbol: str, direction: str, minute: int,
                cooldown_min: int = RELEASE_COOLDOWN_MIN) -> None:
        self._cooldown[(symbol.upper(), direction)] = int(minute) + int(cooldown_min)


# ------------------------------------------------------------------ Lane 1b: last-30-min
class Last30Lane:
    """Lane 1b "last30" (index underlyings, 1-DTE preference). At 15:30 exactly - i.e. on the
    first completed bar whose close time is >= 15:30 (left-label minute >= 929), within a small
    late-arrival window - |open->15:30 return| > 0.5 x 14d avg daily range fires the continuation
    side. Clock-bound: invalidated() is always False; the exit engine's 0DTE/EOD rules govern."""

    LANE = "last30"
    TRIGGER_MINUTE = 15 * 60 + 29             # bar 929 closes at 15:30:00
    LATE_WINDOW_MIN = 5                       # accept a sparse-feed bar up to 15:35
    HORIZON_MIN = 25                          # 15:30 -> 15:55

    def __init__(self, profiles: dict, *, p_thesis: float = 0.5, ret_mult: float = 0.5,
                 close_min: int = CLOSE_MIN):
        self.profiles = {k.upper(): v for k, v in (profiles or {}).items() if v is not None}
        self.p_thesis = float(p_thesis)
        self.ret_mult = float(ret_mult)
        self.close_min = int(close_min)
        self.trigger_minute = int(close_min) - 31     # bar closing at close-30 (929 -> 15:30)
        self._done: set = set()               # symbol - one decision per day

    def update(self, ctx: MinuteCtx) -> LaneSignal | None:
        sym = ctx.symbol.upper()
        prof = self.profiles.get(sym)
        if prof is None or ctx.session_open <= 0 or ctx.close <= 0:
            return None
        if not (self.trigger_minute <= ctx.minute < self.trigger_minute + self.LATE_WINDOW_MIN):
            return None
        if sym in self._done:
            return None
        self._done.add(sym)                   # decided (fire or pass) - once per day
        ret = ctx.close / ctx.session_open - 1.0
        if prof.avg_daily_range <= 0 or abs(ret) <= self.ret_mult * prof.avg_daily_range:
            return None
        direction = "call" if ret > 0 else "put"
        horizon = self.HORIZON_MIN / RTH_MINUTES / TRADING_YEAR_DAYS
        # v1 continuation target: 15% of the day move so far (floor 10 bps); refit at N=25.
        target = max(0.15 * abs(ret), 0.001)
        return LaneSignal(lane=self.LANE, underlying=sym, direction=direction,
                          target_move=target, p_thesis=self.p_thesis, horizon_T=horizon,
                          mu_thesis=_mu_from_target(target, horizon, direction),
                          expires_minute=ctx.minute + 6,
                          notes={"one_dte_only": True, "open_to_1530_ret": round(ret, 6),
                                 "avg_daily_range_14d": round(prof.avg_daily_range, 6),
                                 "planned_exit_minute": self.trigger_minute + 1 + self.HORIZON_MIN})

    def invalidated(self, pos: PositionCtx) -> bool:
        return False                          # clock-bound: exit engine's 0DTE/EOD rules govern


# ------------------------------------------------------------------ Lane 2: stocks-in-play ORB
@dataclass(frozen=True)
class InPlayCandidate:
    symbol: str
    gap_pct: float = 0.0
    catalyst: bool = False
    catalyst_kind: str | None = None          # crew catalyst KIND string (stage-2 covariate);
    #                                           the bool `catalyst` above still drives lane gating
    avg_first5_volume: float = 0.0            # from the 1-min cache (IEX scale) - informational
    #                                           ONLY; never gates RVOL (opts-fix-lane2-rvol-scale-v1)
    average_volume: float = 0.0               # Tradier 90d average day volume - THE RVOL baseline


class _ORState:
    __slots__ = ("or_high", "or_low", "first5_vol", "bars_seen", "ready", "rvol", "rvol_ok",
                 "price_ok")

    def __init__(self) -> None:
        self.or_high = -math.inf
        self.or_low = math.inf
        self.first5_vol = 0.0
        self.bars_seen = 0
        self.ready = False
        self.rvol = 0.0
        self.rvol_ok = False
        self.price_ok = False


class InPlayORBLane:
    """Lane 2 "inplay_orb". Universe = the runner-supplied premarket candidate list (gap/catalyst
    names). Gates: first-5-min RVOL >= 5 vs Tradier average_volume x FIRST5_UCURVE_FRAC (the
    CONSOLIDATED-scale baseline - opts-fix-lane2-rvol-scale-v1; the IEX cache never gates)
    AND price >= $5 at the OR close. Trigger: 1-min close beyond the 5-min opening range.
    Target = 2 x OR height. Horizon = to close. Invalidation: close back inside the OR, or VWAP
    recross. One signal per side per day per symbol."""

    LANE = "inplay_orb"

    def __init__(self, candidates: list, *, rvol_min: float = 5.0, price_min: float = 5.0,
                 p_thesis: float = 0.5, signal_ttl_min: int = 10, close_min: int = CLOSE_MIN):
        self.cands = {c.symbol.upper(): c for c in (candidates or [])}
        self.rvol_min = float(rvol_min)
        self.price_min = float(price_min)
        self.p_thesis = float(p_thesis)
        self.signal_ttl_min = int(signal_ttl_min)
        self.close_min = int(close_min)
        self._or: dict[str, _ORState] = {}
        # latch-at-ENTRY (audit 2026-07-16 Wave 1.11) - same semantics as IndexTrendLane
        self._latched: set = set()
        self._cooldown: dict = {}

    def _baseline_first5(self, cand: InPlayCandidate) -> float:
        # opts-fix-lane2-rvol-scale-v1 (2026-07-10): live first-5 volume is CONSOLIDATED tape
        # while cand.avg_first5_volume is Alpaca IEX single-venue (~2-3% of tape) - gating
        # consolidated-vs-IEX inflated RVOL ~30-50x for cache-backed names. Gate uniformly on
        # the consolidated-scale baseline; no average_volume = no same-scale baseline -> 0.0
        # -> rvol 0 -> the name stands down (the runner quote-fetches average_volume for
        # hunt-list names missing it and journals lane2_rvol_baseline_missing when absent).
        if cand.average_volume > 0:
            return cand.average_volume * FIRST5_UCURVE_FRAC
        return 0.0

    def update(self, ctx: MinuteCtx) -> LaneSignal | None:
        sym = ctx.symbol.upper()
        cand = self.cands.get(sym)
        if cand is None or ctx.close <= 0:
            return None
        st = self._or.setdefault(sym, _ORState())
        if ctx.minute < OPEN_MIN:
            return None
        if ctx.minute < OPEN_MIN + 5:                      # building the opening range
            st.or_high = max(st.or_high, ctx.high)
            st.or_low = min(st.or_low, ctx.low)
            st.first5_vol += max(0.0, ctx.volume)
            st.bars_seen += 1
            return None
        if not st.ready:
            st.ready = True
            base = self._baseline_first5(cand)
            st.rvol = st.first5_vol / base if base > 0 else 0.0
            st.rvol_ok = st.rvol >= self.rvol_min
            st.price_ok = ctx.close >= self.price_min or (
                st.bars_seen > 0 and st.or_high >= self.price_min)
        if not (st.rvol_ok and st.price_ok and st.bars_seen > 0):
            return None
        or_h, or_l = st.or_high, st.or_low
        if not (math.isfinite(or_h) and math.isfinite(or_l)) or or_h <= or_l:
            return None
        if ctx.close > or_h:
            direction = "call"
        elif ctx.close < or_l:
            direction = "put"
        else:
            return None
        key = (sym, direction)
        if key in self._latched:
            return None
        cd = self._cooldown.get(key)
        if cd is not None and ctx.minute < cd:
            return None
        self._cooldown[key] = ctx.minute + RELEASE_COOLDOWN_MIN + 1   # pending guard (Wave 1.11)
        horizon = _rest_of_day_T(ctx.minute, self.close_min)
        target = 2.0 * (or_h - or_l) / ctx.close           # OR height x 2, fractional
        if target <= 0:
            return None
        return LaneSignal(lane=self.LANE, underlying=sym, direction=direction,
                          target_move=target, p_thesis=self.p_thesis, horizon_T=horizon,
                          mu_thesis=_mu_from_target(target, horizon, direction),
                          expires_minute=ctx.minute + 1 + self.signal_ttl_min,
                          notes={"or_high": round(or_h, 4), "or_low": round(or_l, 4),
                                 "first5_rvol": round(st.rvol, 2),
                                 "gap_pct": cand.gap_pct, "catalyst": bool(cand.catalyst),
                                 "catalyst_kind": cand.catalyst_kind})

    def or_range(self, symbol: str) -> tuple | None:
        st = self._or.get(symbol.upper())
        if st is None or not st.ready or not math.isfinite(st.or_high):
            return None
        return (st.or_low, st.or_high)

    def invalidated(self, pos: PositionCtx) -> bool:
        """Re-entry into the OR, or VWAP recross against the position. (The OR is frozen by
        construction; runner-side 2-eval persistence - audit Wave 2.13 - covers tick noise.)"""
        rng = self.or_range(pos.symbol)
        if pos.close <= 0:
            return False
        if rng is not None and rng[0] <= pos.close <= rng[1]:
            return True
        if pos.svwap > 0:
            if pos.direction == "call" and pos.close < pos.svwap:
                return True
            if pos.direction == "put" and pos.close > pos.svwap:
                return True
        return False

    # ---- latch-at-entry callbacks (runner-driven; audit Wave 1.11) ----------------------------
    def confirm_entry(self, symbol: str, direction: str) -> None:
        self._latched.add((symbol.upper(), direction))

    def release(self, symbol: str, direction: str, minute: int,
                cooldown_min: int = RELEASE_COOLDOWN_MIN) -> None:
        self._cooldown[(symbol.upper(), direction)] = int(minute) + int(cooldown_min)


# ------------------------------------------------------------------ Lane 3: macro reaction
class MacroReactionLane:
    """Lane 3 "macro_reaction" (SPY; exploratory). Armed ONLY when the runner passes today's
    event kinds (events.is_event_day). CPI/NFP: direction = sign of the 09:30->09:45 move,
    scheduled emission 09:45; FOMC: sign of the 14:00->14:15 move, scheduled emission 14:15.
    NEVER pre-print: a signal is emitted only on a bar whose ctx.blackout is None - when the
    scheduled minute is still inside a blackout window (the FOMC presser windows make 14:15
    structurally dirty), the measured direction is HELD and emitted on the first clean bar.
    Horizon = to 15:55. Invalidation: none at the lane level (the exit engine's post-print
    forced decision, rule f, governs)."""

    LANE = "macro_reaction"
    CPI_MEASURE_END = 9 * 60 + 44             # bar 584 closes at 09:45:00
    FOMC_MEASURE_START = 13 * 60 + 59         # bar 839 closes at 14:00:00 -> the 14:00 reference
    FOMC_MEASURE_END = 14 * 60 + 14           # bar 854 closes at 14:15:00
    EXIT_MINUTE = 15 * 60 + 55

    def __init__(self, event_kinds_today: list, *, symbol: str = "SPY",
                 p_thesis: float = 0.5, signal_ttl_min: int = 10, close_min: int = CLOSE_MIN):
        self.kinds = [str(k).lower() for k in (event_kinds_today or [])]
        self.symbol = symbol.upper()
        self.p_thesis = float(p_thesis)
        self.signal_ttl_min = int(signal_ttl_min)
        self.close_min = int(close_min)
        self.exit_minute = int(close_min) - 5  # designed exit (955 -> 15:55 on normal days)
        self._fomc_ref: float | None = None    # SPY at the 14:00 close
        self._pending: dict | None = None      # measured, waiting for a blackout-free bar
        self._emitted: set = set()             # event kind -> once per day

    def _measure(self, ctx: MinuteCtx) -> None:
        if ("cpi" in self.kinds or "nfp" in self.kinds) and "print_930" not in self._emitted:
            if ctx.minute >= self.CPI_MEASURE_END and ctx.session_open > 0:
                self._emitted.add("print_930")
                move = ctx.close / ctx.session_open - 1.0
                kind = "cpi" if "cpi" in self.kinds else "nfp"
                if move != 0.0:
                    self._pending = {"kind": kind, "move": move,
                                     "print_minute": OPEN_MIN}      # 08:30 print, market ref 09:30
        if "fomc" in self.kinds:
            if self._fomc_ref is None and ctx.minute >= self.FOMC_MEASURE_START:
                self._fomc_ref = ctx.close
                return
            if (self._fomc_ref is not None and "fomc" not in self._emitted
                    and ctx.minute >= self.FOMC_MEASURE_END):
                self._emitted.add("fomc")
                move = ctx.close / self._fomc_ref - 1.0 if self._fomc_ref > 0 else 0.0
                if move != 0.0:
                    self._pending = {"kind": "fomc", "move": move,
                                     "print_minute": 14 * 60}

    def update(self, ctx: MinuteCtx) -> LaneSignal | None:
        if not self.kinds or ctx.symbol.upper() != self.symbol:
            return None
        self._measure(ctx)
        if self._pending is None:
            return None
        if ctx.blackout is not None:
            return None                        # never pre-print / never inside a hard window
        pend, self._pending = self._pending, None
        direction = "call" if pend["move"] > 0 else "put"
        emit_close = ctx.minute + 1
        horizon = max((self.exit_minute - emit_close), 1) / RTH_MINUTES / TRADING_YEAR_DAYS
        target = max(abs(pend["move"]), 0.002)  # v1: the measured reaction repeats; floor 20 bps
        return LaneSignal(lane=self.LANE, underlying=self.symbol, direction=direction,
                          target_move=target, p_thesis=self.p_thesis, horizon_T=horizon,
                          mu_thesis=_mu_from_target(target, horizon, direction),
                          expires_minute=ctx.minute + 1 + self.signal_ttl_min,
                          notes={"event": pend["kind"], "measured_move": round(pend["move"], 6),
                                 "print_minute": pend["print_minute"],
                                 "emit_minute": emit_close,
                                 "planned_exit_minute": self.exit_minute})

    def invalidated(self, pos: PositionCtx) -> bool:
        return False                          # rule (f) post-print forced decision governs


# ------------------------------------------------------------------ Lane 4: measurement stub
class PreEarningsStubLane:
    """Lane 4 stub (plan: deferred-measure-first). Emits NOTHING - it exists so the runner's
    lane roster names it and the spread-gate measurement week has a hook to fill in later."""

    LANE = "pre_earnings_straddle_stub"

    def update(self, ctx: MinuteCtx) -> None:                        # noqa: ARG002
        return None

    def invalidated(self, pos: PositionCtx) -> bool:                 # noqa: ARG002
        return False
