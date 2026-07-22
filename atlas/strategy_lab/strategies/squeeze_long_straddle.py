"""squeeze_long_straddle - Bollinger BandWidth Squeeze -> long ATM straddle.

AUTHORITY: docs/strategies/briefs/squeeze_long_straddle.md (verified CORRECTED 2026-07-19).
Provenance: John Bollinger, *Bollinger on Bollinger Bands* (2001) supplies ONLY the signal
substrate and the exit doctrine; the straddle expression and every option-shaped constant
are the brief's documented ADAPTATIONS (§2 - no option-trading content exists in the
portions of the source read). Every constant below cites its brief §8 row.

Doctrine (brief §3/§4 - §4 OVERRIDES all platform exit doctrine for this cohort):
  * Bands: 20-day SIMPLE MA +/- 2 POPULATION standard deviations (rows 1-3);
    BandWidth = (upper - lower)/middle (row 5).
  * E1 entry (rows 6-8, 11): signal on DAILY CLOSE when BandWidth equals the minimum of
    its trailing 126 sessions INCLUDING today (inclusive-min tie-break, row 8). Squeeze
    ALONE fires - the published band-break confirmation (row 9) belongs to the EXIT state
    machine, not to entry (§3 E1). Enter the NEXT session: scan() reads completed daily
    bars only (ts < today), so an intraday fire is always yesterday's close-signal.
  * Structure (rows 10/12/13): 1 call + 1 put, both LONG, qty 1, at the single listed
    strike nearest spot with BOTH legs two-sided; one expiry nearest 45 DTE inside the
    30-50 band (band upper trimmed 60->50 to match the pinned META dte_range).
  * Exits: X1 post-breakout trail-out - tag of the band OPPOSITE the breakout direction
    OR parabolic SAR flip (Wilder 0.02/0.2), whichever first (rows 9/15/16); X2 time stop
 - 15 completed sessions from entry (entry day's own close = session 1) with no close
    outside either band (row 14); X5 platform DTE floor <= 7 (row 19). NO profit target
    and NO premium stop (rows 17/18 - published absence, armed as doctrine). Missing or
    thin daily history -> HOLD; X5 fires regardless of data state.
  * Gates: re-arm hysteresis after every manage()-driven exit - BandWidth must leave the
    bottom quartile of its trailing 126-session range before a fresh min may fire again
    (row 20; held in-memory, resets to ARMED on restart - documented soft spot; runner
    rail closes do not feed it). Earnings within 21 calendar days of the signal close
    block SINGLE NAMES only (row 21; ctx.earnings horizon may be shorter than 21d - the
    gate degrades to the feed's horizon). IV/VIX logged observe-only, never gating
    (row 22). Liquidity floor = two-sided NBBO on BOTH legs (row 25 platform floor).

Conventions pinned here (deterministic, recomputed from history each call - restart-safe):
breakout = first close STRICTLY outside a band on/after the entry session; opposite-band
tag = inclusive touch (low <= lower for up-breakouts, high >= upper for down); same-day
tag + SAR flip resolves to the tag label; SAR seeds at the entry->breakout episode extreme
(the "most recent significant low" variant the brief records with Method II).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import pstdev

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")
INDEX_NAMES = frozenset({"SPY", "QQQ", "IWM"})          # row 21: earnings gate is single-name-only
HISTORY_DAYS = 260                                       # brief §9: >=150 sessions; hub default


# ---------------------------------------------------------------- band math (pure, row 1-5)
def bollinger_point(window: list, mult: float = 2.0) -> tuple:
    """(middle, upper, lower) for one 20-close window: SMA +/- mult*POPULATION stdev
    (rows 1-3 - the book's Table P.1 formula uses the plain N-divisor sigma)."""
    mid = sum(window) / len(window)
    sd = pstdev(window)
    return mid, mid + mult * sd, mid - mult * sd


def bandwidth_point(window: list, mult: float = 2.0) -> float:
    """BandWidth = (Upper - Lower)/Middle (row 5, Bollinger 2001 p. 63 per FJQ)."""
    mid, up, lo = bollinger_point(window, mult)
    return (up - lo) / mid if mid > 0 else 0.0


def bandwidth_series(closes: list, period: int = 20, mult: float = 2.0) -> list:
    """BandWidth per day; element k corresponds to closes[k + period - 1]."""
    return [bandwidth_point(closes[i - period + 1:i + 1], mult)
            for i in range(period - 1, len(closes))]


@dataclass(frozen=True)
class SqueezeParams:
    """Tunables, every field citing its brief §8 row (the pre-registered tweak neighborhood).
    bb_period/bb_stdev: rows 1/2 SOURCE-VERBATIM (20, 2.0). squeeze_lookback_days: rows 6/7
 - six-month book default -> 126 trading sessions (ADAPTED day count). dte_*: row 13 band
    30-60 prefer ~45, upper trimmed 60->50 to match the pinned META dte_range (PLATFORM-
    POLICY trim). no_expansion_exit_sessions: row 14 X2 (ADAPTED 15). sar_step/sar_max_af:
    row 16 Wilder defaults (ADAPTED - book names Parabolic, publishes no constants).
    dte_floor_exit: row 19 X5 (PLATFORM-POLICY). rearm_quartile: row 20 bottom quartile of
    the trailing 126-session BandWidth range (PLATFORM-POLICY). earnings_gate_days: row 21
    (PLATFORM-POLICY, single names only)."""
    bb_period: int = 20
    bb_stdev: float = 2.0
    squeeze_lookback_days: int = 126
    dte_min_days: int = 30
    dte_max_days: int = 50
    dte_target_days: int = 45
    no_expansion_exit_sessions: int = 15
    sar_step: float = 0.02
    sar_max_af: float = 0.2
    dte_floor_exit: int = 7
    rearm_quartile: float = 0.25
    earnings_gate_days: int = 21


class SqueezeLongStraddle(Strategy):
    META = StrategyMeta(
        strategy_id="squeeze_long_straddle", version=1,
        name="Bollinger BandWidth Squeeze -> long ATM straddle",
        universe=UNIVERSE, dte_range=(30, 50),
        max_concurrent=9,                             # one straddle per name (row 26)
        event_policy=EventPolicy.TRADE_THROUGH,       # price-only signal; earnings gate is ours
        grading_basis=GradingBasis.DEBIT,             # row 27: max loss = net debit paid
        defining_mechanism="long_vol_convexity",
        settle_at_expiry=False,                       # X5 forbids holding into expiry (row 19)
        scan_interval_s=300.0, mark_interval_s=300.0, # daily-close doctrine; 5-min is diagnostic
        expected_fires_per_20_sessions=3.0)           # ~2-4/month across 9 names (brief §10)
    params = SqueezeParams()

    def __init__(self):
        # row 20 hysteresis book: {symbol: iso day of the manage()-driven exit}. In-memory - 
        # a restart re-arms every name (worst case one F3-style re-entry, documented above).
        self._disarmed_since: dict = {}

    # -- shared history access ---------------------------------------------
    @staticmethod
    def _completed_bars(ctx, sym: str) -> list:
        """Daily bars with ts strictly before today - the signal/state substrate is always
        the last COMPLETED close (row 11: signal on daily close, act the next session)."""
        bars = [b for b in (ctx.hub.daily_history(sym, days=HISTORY_DAYS) or [])
                if str(b.ts)[:10] < ctx.day]
        bars.sort(key=lambda b: str(b.ts))
        return bars

    # -- entry gates (rows 20/21) ------------------------------------------
    def _rearmed(self, sym: str, bars: list, bw: list) -> bool:
        """Row 20: after an exit, BandWidth must close ABOVE the bottom quartile of its
        trailing 126-session range on some later session before the name may fire again
        (the fresh-min half of the rule IS the squeeze trigger itself)."""
        exit_day = self._disarmed_since.get(sym)
        if exit_day is None:
            return True
        p = self.params
        for k in range(len(bw)):
            if str(bars[k + p.bb_period - 1].ts)[:10] <= exit_day:
                continue
            rng = bw[max(0, k - (p.squeeze_lookback_days - 1)):k + 1]
            mn, mx = min(rng), max(rng)
            if bw[k] > mn + p.rearm_quartile * (mx - mn):
                del self._disarmed_since[sym]
                return True
        return False

    def _earnings_blocked(self, sym: str, signal_day: str, earnings: dict,
                          flags: list) -> bool:
        """Row 21: single names only - skip when confirmed earnings fall within 21 calendar
        days of the signal close. Unparseable date -> enter + flag (not 'confirmed')."""
        if sym in INDEX_NAMES:
            return False
        raw = str((earnings.get(sym) or {}).get("date") or "")
        if not raw:
            return False
        try:
            delta = (date.fromisoformat(raw[:10]) - date.fromisoformat(signal_day)).days
        except ValueError:
            flags.append("earnings_date_unparsed")
            return False
        return 0 <= delta <= self.params.earnings_gate_days

    # -- contract selection (rows 12/13/25) --------------------------------
    def _pick_expiry(self, ctx, sym: str, today: date) -> tuple:
        """Listed expiry nearest dte_target inside [dte_min, dte_max] (row 13; tie -> the
        shorter). No monthly filter - nearest-45 per the operative spec."""
        p = self.params
        best, best_key, best_dte = None, None, 0
        for e in ctx.hub.expirations(sym):
            try:
                dte = (date.fromisoformat(str(e)) - today).days
            except ValueError:
                continue
            if p.dte_min_days <= dte <= p.dte_max_days:
                key = (abs(dte - p.dte_target_days), dte)
                if best_key is None or key < best_key:
                    best, best_key, best_dte = e, key, dte
        return best, best_dte

    @staticmethod
    def _pick_straddle(rows: list, S_ref: float):
        """Single strike nearest spot carrying BOTH a two-sided call and put (rows 12/25;
        tie -> the lower strike). None when no strike can host the straddle."""
        by_strike: dict = {}
        for r in rows:
            if (r.bid or 0) > 0 and (r.ask or 0) > 0:
                by_strike.setdefault(float(r.strike), {})[r.option_type] = r
        pairs = [(k, v) for k, v in by_strike.items() if "call" in v and "put" in v]
        if not pairs:
            return None
        _, v = min(pairs, key=lambda kv: (abs(kv[0] - S_ref), kv[0]))
        return v["call"], v["put"]

    # -- scan (rows 6-13, 20-25) -------------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        today = ctx.dt_et.date()
        holding = {pos.underlying for pos in ctx.open_positions}   # one straddle per name
        min_bars = p.bb_period + p.squeeze_lookback_days - 1        # 126 BandWidth points
        out = []
        for sym in self.META.universe:
            if sym in holding:
                continue
            bars = self._completed_bars(ctx, sym)
            if len(bars) < min_bars:
                if ctx.journal and bars:
                    ctx.journal({"event": "sqz_history_short", "symbol": sym,
                                 "n_bars": len(bars), "need": min_bars})
                continue
            closes = [float(b.close) for b in bars]
            bw = bandwidth_series(closes, p.bb_period, p.bb_stdev)
            window = bw[-p.squeeze_lookback_days:]
            if bw[-1] > min(window):        # squeeze = inclusive trailing-126 min (row 8)
                continue
            signal_day = str(bars[-1].ts)[:10]
            if not self._rearmed(sym, bars, bw):
                if ctx.journal:
                    ctx.journal({"event": "sqz_blocked_rearm", "symbol": sym,
                                 "signal_day": signal_day})
                continue
            flags: list = []
            earn = ctx.earnings.get(sym) or {}
            if self._earnings_blocked(sym, signal_day, ctx.earnings, flags):
                if ctx.journal:
                    ctx.journal({"event": "sqz_blocked_earnings", "symbol": sym,
                                 "signal_day": signal_day, "earnings": earn})
                continue
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            exp, dte = self._pick_expiry(ctx, sym, today)
            if exp is None:
                if ctx.journal:
                    ctx.journal({"event": "sqz_no_expiry", "symbol": sym, "day": ctx.day})
                continue
            pick = self._pick_straddle(ctx.hub.chain(sym, exp), S_ref)
            if pick is None:
                if ctx.journal:
                    ctx.journal({"event": "sqz_no_strike", "symbol": sym, "expiry": exp,
                                 "S_ref": round(S_ref, 4)})
                continue
            legs, ivs, mids = [], [], []
            for opt_type, r in zip(("call", "put"), pick):
                mid = (r.bid + r.ask) / 2.0
                g = ctx.hub.row_greeks(opt_type=opt_type, strike=float(r.strike), S=S_ref,
                                       mid=mid, dte_days=max(1, dte)) or {}
                legs.append({"occ": r.symbol, "underlying": sym, "opt_type": opt_type,
                             "strike": float(r.strike), "expiry": exp, "side": +1, "qty": 1,
                             "nbbo": {"bid": r.bid, "ask": r.ask},
                             "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                             "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                             "theta_day": g.get("theta_day", 0.0)})
                ivs.append(g.get("iv", 0.0))
                mids.append(mid)
            vr = None                                   # row 22: observe-only, never gates
            get_vr = getattr(ctx.hub, "vol_regime", None)
            if callable(get_vr):
                try:
                    vr = get_vr()
                except Exception:  # noqa: BLE001 - logging must never block an entry
                    vr = None
            out.append(ProposedCombo(
                kind="long_straddle", underlying=sym, legs=legs,
                signal={"S_ref": round(S_ref, 4), "strike": legs[0]["strike"], "expiry": exp,
                        "dte_days": dte, "signal_day": signal_day,
                        "bandwidth": round(bw[-1], 6),
                        "bw_lookback_min": round(min(window), 6),
                        "debit_mid": round(sum(mids), 4),
                        "entry_atm_iv": round(sum(ivs) / 2.0, 4),
                        "vol_regime": vr, "earnings": earn or None},
                risk_flags=flags))
        return out

    # -- manage (X1/X2/X5; rows 9, 14-19) ----------------------------------
    def manage(self, pos, ctx) -> ExitAction | None:
        p = self.params
        bars = self._completed_bars(ctx, pos.underlying)
        if bars:
            act = self._doctrine_exit(pos, bars)
            if act is not None:
                self._disarmed_since[pos.underlying] = ctx.day     # start row-20 hysteresis
                return act
        dte = (pos.nearest_expiry - ctx.dt_et.date()).days
        if dte <= p.dte_floor_exit:                    # X5 (row 19) - regardless of state/data
            self._disarmed_since[pos.underlying] = ctx.day
            return ExitAction("close", "x5_dte_floor", state={"dte_days": dte})
        return None                                    # missing data -> hold (doctrine)

    def _doctrine_exit(self, pos, bars: list) -> ExitAction | None:
        """X1/X2 state machine recomputed from daily history each call (stateless, restart-
        safe). Windows: breakout scan and the X2 clock both start at the entry session
        (ts >= entry_day); the entry day's own close is session 1 of the X2 count."""
        p = self.params
        period = p.bb_period
        entry_day = str(pos.entry_day)[:10]
        idx0 = next((i for i, b in enumerate(bars) if str(b.ts)[:10] >= entry_day), None)
        if idx0 is None or idx0 < period - 1:
            return None                                # no post-entry close / thin warmup -> hold
        closes = [float(b.close) for b in bars]
        highs = [float(b.high) for b in bars]
        lows = [float(b.low) for b in bars]

        def band(t):
            return bollinger_point(closes[t - period + 1:t + 1], p.bb_stdev)

        bt = direction = None                          # row 9: first close STRICTLY outside
        for t in range(idx0, len(bars)):
            _, up, lo = band(t)
            if closes[t] > up:
                bt, direction = t, +1
                break
            if closes[t] < lo:
                bt, direction = t, -1
                break
        if bt is None:                                 # pre-breakout: only the X2 clock runs
            sessions = len(bars) - idx0
            pos.carried.update({"phase": "pre_breakout", "sessions_since_entry": sessions})
            if sessions >= p.no_expansion_exit_sessions:
                return ExitAction("close", "x2_time_stop",
                                  state={"sessions_since_entry": sessions,
                                         "entry_day": entry_day})
            return None
        # post-breakout: X1 trail-out (rows 15/16) - tag before SAR on the same bar.
        if direction > 0:
            sar, ep = min(lows[idx0:bt + 1]), highs[bt]   # seed under the episode low
        else:
            sar, ep = max(highs[idx0:bt + 1]), lows[bt]
        af = p.sar_step
        breakout_day = str(bars[bt].ts)[:10]
        for t in range(bt + 1, len(bars)):
            _, up, lo = band(t)
            if (direction > 0 and lows[t] <= lo) or (direction < 0 and highs[t] >= up):
                return ExitAction("close", "x1_opposite_band_tag",
                                  state={"breakout_day": breakout_day,
                                         "breakout_dir": "up" if direction > 0 else "down",
                                         "tag_day": str(bars[t].ts)[:10]})
            sar = sar + af * (ep - sar)
            if direction > 0:
                sar = min(sar, lows[t - 1], lows[t - 2])
                if lows[t] <= sar:
                    return ExitAction("close", "x1_sar_flip",
                                      state={"breakout_day": breakout_day, "breakout_dir": "up",
                                             "sar": round(sar, 4),
                                             "flip_day": str(bars[t].ts)[:10]})
                if highs[t] > ep:
                    ep, af = highs[t], min(af + p.sar_step, p.sar_max_af)
            else:
                sar = max(sar, highs[t - 1], highs[t - 2])
                if highs[t] >= sar:
                    return ExitAction("close", "x1_sar_flip",
                                      state={"breakout_day": breakout_day, "breakout_dir": "down",
                                             "sar": round(sar, 4),
                                             "flip_day": str(bars[t].ts)[:10]})
                if lows[t] < ep:
                    ep, af = lows[t], min(af + p.sar_step, p.sar_max_af)
        pos.carried.update({"phase": "post_breakout", "breakout_day": breakout_day,
                            "breakout_dir": "up" if direction > 0 else "down",
                            "sar": round(sar, 4)})
        return None
