"""donchian_breakout_debit_vert - Turtle System 1 (20-day) breakout expressed as a debit
vertical, with the 55-day Failsafe and the last-breakout-winner filter.

AUTHORITY: docs/strategies/briefs/donchian_breakout_debit_vert.md (verified CORRECTED
2026-07-19, zero invented constants). Provenance: "The Original Turtle Trading Rules"
(Faith/Curtis, Chs. 3-7); options expression ADAPTED (no options in source). Every constant
cites its brief §3/§4/§8 row.

Doctrine (§3/§4 - §4 OVERRIDES all platform exit doctrine for this cohort):
  * ENTRY E1 (Ch.4 p.19): price exceeds by a tick the high/low of the preceding 20 days.
    Up-breakout → LONG a bull call vertical; down-breakout → LONG a bear put vertical
    (structure ADAPTED). Intraday, same-day (E4): we test ref_price vs the prior-20-day
    channel, not the close.
  * E2 last-breakout-winner filter (Ch.4 p.19): skip an E1 signal if the LAST 20-day breakout
    in this symbol would have won (reached a profitable 10-day exit before moving 2N adverse).
  * E3 Failsafe (Ch.4 p.19): when E1 is skipped by E2, enter instead on the 55-day breakout.
  * N = 20-day Wilder ATR (Ch.3): the only published price-distance unit; frozen at entry.
  * Strike selection (ADAPTED, no options in source): long leg at the listed strike nearest
    spot (ATM); short leg nearest entry ± 2N in the trend direction (min one strike apart) - 
    2N is the source's own thesis-invalidation distance. DTE nearest monthly 45-75 (anchored
    to the secondary source's 43-day avg winner duration).
  * EXIT (§4, overrides platform ladders): X1 10-day opposite-channel exit (primary); X2
    underlying stop at entry ∓ 2N (non-negotiable); X3 NO profit target (source explicitly
    rejects taking profits early); X4 close at 21 DTE ('a few weeks before expiration').
  * NO regime/IV/event gate (source has none - only E2). DEBIT basis (long vertical).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")


@dataclass(frozen=True)
class DonchianParams:
    """Tunables (pre-registered neighborhood; the rest is doctrine).
    entry_channel_days: E1/E-TRIG SOURCE-VERBATIM 20-day breakout. failsafe_channel_days: E3
    SOURCE-VERBATIM 55-day Failsafe. exit_channel_days: X1 SOURCE-VERBATIM 10-day opposite
    channel. atr_days: N SOURCE-VERBATIM 20-day Wilder ATR. stop_atr_mult / short_offset_atr_mult:
    X2 + strike SOURCE-VERBATIM 2N. roll_dte: X4 ADAPTED 21 DTE ('a few weeks'). dte_min/max_days:
    ADAPTED 45-75 (anchored to 43-day avg winner). history_days: enough for 55d channel + E2
    look-back. entry_minute_from/to: PLATFORM-POLICY scan window (intraday, E4)."""
    entry_channel_days: int = 20
    failsafe_channel_days: int = 55
    exit_channel_days: int = 10
    atr_days: int = 20
    stop_atr_mult: float = 2.0
    short_offset_atr_mult: float = 2.0
    roll_dte: int = 21
    dte_min_days: int = 45
    dte_max_days: int = 75
    history_days: int = 120
    entry_minute_from: int = 575          # ~09:35 ET (let the open settle)
    entry_minute_to: int = 955            # 15:55 ET


def _atr_wilder(bars: list, n: int) -> float | None:
    """N = 20-day Wilder ATR (Ch.3): seed with a 20-day SMA of True Range, then
    N = (19*PDN + TR)/20. bars are chronological TBar with .high/.low/.close."""
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pdc = bars[i].high, bars[i].low, bars[i - 1].close
        trs.append(max(h - l, abs(h - pdc), abs(pdc - l)))
    if len(trs) < n:
        return None
    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = ((n - 1) * atr + tr) / n
    return atr


def _channel(bars: list, n: int, upto: int) -> tuple:
    """(highest high, lowest low) of the `n` bars ending at index upto-1 (exclusive of upto)."""
    window = bars[max(0, upto - n):upto]
    if not window:
        return (None, None)
    return (max(b.high for b in window), min(b.low for b in window))


def _last_breakout_was_winner(bars: list, entry_n: int, exit_n: int, atr: float) -> bool | None:
    """E2: find the most recent prior 20-day breakout in `bars` and simulate whether it hit a
    profitable 10-day opposite-channel exit BEFORE moving 2N adverse. None = no prior breakout
    resolvable (→ E2 cannot skip; treat as not-a-winner so E1 fires)."""
    if atr is None or atr <= 0:
        return None
    for i in range(len(bars) - 2, entry_n, -1):     # most recent first
        hh, ll = _channel(bars, entry_n, i)
        if hh is None:
            continue
        b = bars[i]
        direction = 0
        if b.high > hh:
            direction = +1
        elif b.low < ll:
            direction = -1
        else:
            continue
        entry_px = hh if direction > 0 else ll
        stop = entry_px - 2 * atr if direction > 0 else entry_px + 2 * atr
        # walk forward from the breakout day
        for j in range(i + 1, len(bars)):
            exh, exl = _channel(bars, exit_n, j)
            if exh is None:
                continue
            fb = bars[j]
            if direction > 0:
                if fb.low <= stop:
                    return False                    # 2N adverse first → loser
                if fb.low <= exl and fb.close > entry_px:
                    return True                     # profitable 10-day exit first → winner
            else:
                if fb.high >= stop:
                    return False
                if fb.high >= exh and fb.close < entry_px:
                    return True
        return False                                # unresolved by series end → not a winner
    return None


class DonchianBreakoutDebitVert(Strategy):
    META = StrategyMeta(
        strategy_id="donchian_breakout_debit_vert", version=1,
        name="Turtle System 1 breakout as a debit vertical (55-day failsafe)",
        universe=UNIVERSE, dte_range=(45, 75),
        max_concurrent=9,
        event_policy=EventPolicy.TRADE_THROUGH,
        grading_basis=GradingBasis.DEBIT,
        defining_mechanism="directional_momentum",
        settle_at_expiry=False,
        scan_interval_s=300.0, mark_interval_s=600.0,
        expected_fires_per_20_sessions=3.0)
    params = DonchianParams()

    def _breakout(self, bars: list, S: float, channel_days: int) -> int:
        """+1 up / -1 down / 0 none: ref_price exceeds the prior-channel high/low by a tick."""
        hh, ll = _channel(bars, channel_days, len(bars))
        if hh is None:
            return 0
        if S > hh:
            return +1
        if S < ll:
            return -1
        return 0

    def _pick_expiry(self, ctx, sym: str, today: date) -> str | None:
        best, best_err = None, None
        for e in ctx.hub.expirations(sym):
            try:
                d = date.fromisoformat(e)
            except ValueError:
                continue
            dte = (d - today).days
            if self.params.dte_min_days <= dte <= self.params.dte_max_days:
                err = abs(dte - 60)
                if best_err is None or err < best_err:
                    best, best_err = e, err
        return best

    def _vertical_legs(self, ctx, sym, exp, rows, S, dte, direction, atr) -> list | None:
        """Long ATM + short at entry ± 2N (min one strike apart). direction +1 → bull call,
        -1 → bear put."""
        opt = "call" if direction > 0 else "put"
        legs_rows = [r for r in rows if r.option_type == opt
                     and (r.bid or 0) > 0 and (r.ask or 0) > 0]
        if not legs_rows:
            return None
        long_row = min(legs_rows, key=lambda r: abs(r.strike - S))
        target = S + 2 * atr if direction > 0 else S - 2 * atr
        # short strike beyond the long in the trend direction, nearest the 2N target
        if direction > 0:
            cands = [r for r in legs_rows if r.strike > long_row.strike]
        else:
            cands = [r for r in legs_rows if r.strike < long_row.strike]
        if not cands:
            return None
        short_row = min(cands, key=lambda r: abs(r.strike - target))
        out = []
        for row, side in ((long_row, +1), (short_row, -1)):
            mid = (row.bid + row.ask) / 2.0
            g = ctx.hub.row_greeks(opt_type=opt, strike=row.strike, S=S, mid=mid,
                                   dte_days=dte) or {}
            out.append({"occ": row.symbol, "underlying": sym, "opt_type": opt,
                        "strike": row.strike, "expiry": exp, "side": side, "qty": 1,
                        "nbbo": {"bid": row.bid, "ask": row.ask},
                        "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                        "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                        "theta_day": g.get("theta_day", 0.0)})
        return out

    # -- scan (E1/E2/E3, E4 intraday) -------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        if not (p.entry_minute_from <= ctx.minute < p.entry_minute_to):
            return []
        today = ctx.dt_et.date()
        held = {pos.underlying for pos in ctx.open_positions}
        out = []
        for sym in self.META.universe:
            if sym in held:
                continue
            bars = ctx.hub.daily_history(sym, days=max(p.history_days, p.failsafe_channel_days + 40))
            if len(bars) < p.failsafe_channel_days + p.atr_days + 5:
                continue
            S = ctx.hub.ref_price(sym)
            atr = _atr_wilder(bars, p.atr_days)
            if S <= 0 or not atr:
                continue
            direction = self._breakout(bars, S, p.entry_channel_days)
            channel = "system1_20d"
            if direction != 0:
                winner = _last_breakout_was_winner(bars, p.entry_channel_days,
                                                   p.exit_channel_days, atr)
                if winner:                          # E2: skip E1 → try the 55-day failsafe (E3)
                    direction = self._breakout(bars, S, p.failsafe_channel_days)
                    channel = "failsafe_55d"
            if direction == 0:
                continue
            exp = self._pick_expiry(ctx, sym, today)
            if exp is None:
                if ctx.journal:
                    ctx.journal({"event": "donchian_no_expiry", "symbol": sym})
                continue
            dte = (date.fromisoformat(exp) - today).days
            legs = self._vertical_legs(ctx, sym, exp, ctx.hub.chain(sym, exp), S, dte,
                                       direction, atr)
            if legs is None:
                if ctx.journal:
                    ctx.journal({"event": "donchian_no_strikes", "symbol": sym, "expiry": exp})
                continue
            out.append(ProposedCombo(
                kind="bull_call_vertical" if direction > 0 else "bear_put_vertical",
                underlying=sym, legs=legs,
                signal={"direction": "long" if direction > 0 else "short", "channel": channel,
                        "S": round(S, 4), "N_atr": round(atr, 4), "expiry": exp, "dte_days": dte,
                        "notes": {"N_atr": round(atr, 6), "entry_ref": round(S, 4),
                                  "direction": 1 if direction > 0 else -1}}))
        return out

    # -- manage (§4): X1 channel exit, X2 2N stop, X4 21-DTE close ---------
    def manage(self, pos, ctx):
        p = self.params
        notes = pos.notes or {}
        try:
            direction = int(notes.get("direction", 0))
            N = float(notes.get("N_atr", 0.0))
            entry_ref = float(notes.get("entry_ref", 0.0))
        except (TypeError, ValueError):
            direction, N, entry_ref = 0, 0.0, 0.0
        today = ctx.dt_et.date()
        # X4: 21-DTE roll/close (close only in v1; re-entry is a fresh scan)
        if (pos.nearest_expiry - today).days <= p.roll_dte:
            return ExitAction(action="close", rule="turtle_x4_roll_dte",
                              state={"dte": (pos.nearest_expiry - today).days})
        S = ctx.hub.ref_price(pos.underlying) if ctx.hub else 0.0
        if S <= 0 or direction == 0:
            return None
        # X2: non-negotiable 2N underlying stop (N frozen at entry)
        if N > 0 and entry_ref > 0:
            if direction > 0 and S <= entry_ref - p.stop_atr_mult * N:
                return ExitAction(action="close", rule="turtle_x2_stop_2n",
                                  state={"S": round(S, 4), "stop": round(entry_ref - p.stop_atr_mult * N, 4)})
            if direction < 0 and S >= entry_ref + p.stop_atr_mult * N:
                return ExitAction(action="close", rule="turtle_x2_stop_2n",
                                  state={"S": round(S, 4), "stop": round(entry_ref + p.stop_atr_mult * N, 4)})
        # X1: 10-day opposite-channel exit (from daily history)
        bars = ctx.hub.daily_history(pos.underlying, days=p.exit_channel_days + 5) if ctx.hub else []
        if len(bars) >= p.exit_channel_days:
            exh, exl = _channel(bars, p.exit_channel_days, len(bars))
            if direction > 0 and exl is not None and S <= exl:
                return ExitAction(action="close", rule="turtle_x1_channel_exit",
                                  state={"S": round(S, 4), "ch10_low": round(exl, 4)})
            if direction < 0 and exh is not None and S >= exh:
                return ExitAction(action="close", rule="turtle_x1_channel_exit",
                                  state={"S": round(S, 4), "ch10_high": round(exh, 4)})
        return None
