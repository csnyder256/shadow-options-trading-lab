"""rsi2_overbought_bear_call - Connors RSI(2) overbought fade, expressed as a bear call spread.

AUTHORITY: docs/strategies/briefs/rsi2_overbought_bear_call.md (verified CONFIRMED pass 2,
2026-07-19, zero invented constants). Provenance: Connors & Alvarez, *Short Term Trading
Strategies That Work* (2008), Ch. 9 (the 2-period RSI) + Ch. 12 (published short-cover exit);
short-side entry rendition [verified-secondary] via ChartSchool / MQL5. Every constant below
cites its brief row.

Doctrine (brief §3/§4 - overrides ALL platform exit doctrine for this cohort):
  * Entry (rows 2-4): daily-close Wilder RSI(2) rises above 95 while the close sits BELOW the
    200-day SMA (the short side of the published pair). One position per symbol (row 5,
    "no current positions"). Evaluated 15:45-15:55 ET with the live price standing in for
    today's close (row 6, ADAPTED - the published execution is on the daily close itself).
  * ADAPTATION, LOUD (brief §2): the published trade is short the UNDERLYING. This platform is
    options-only, so the signal is expressed as a 2-leg bear call spread - short call at the
    first listed strike at/above spot (row 13), long call at the first strike >= 0.5% of spot
    further out, width floor $1 (row 14), nearest expiry with 10-17 calendar DTE (row 15).
    Structure constants are OURS, not Connors'; the long wing caps a tail the source wears open.
  * Exits (rows 7/8, close-based like everything published): close below the 5-day SMA
    (primary, Ch. 12 verbatim) OR close above the 200-day SMA (regime flip, MQL5 rendition).
    NO stop-loss (row 10) and NO profit target (row 11) - adverse marks are doctrinal HOLDS;
    only rows 7, 8 and 16 may close a position (brief §10c).
  * Force-close at 1 DTE at the closing evaluation if no signal exit fired (row 16,
    PLATFORM-POLICY - spreads expire, stock shorts don't). The runner's expiry-day backstop
    remains the global rail behind it. No rolls, ever (§4.6).
  * Entry gates, ours: net mid credit >= 30% of width (row 17), two-sided NBBO with
    (ask-bid)/mid <= 10% and OI >= 100 on BOTH legs (row 18), and skip single-name entries
    whose earnings land on/before the chosen expiry (row 19). 1 spread, account-blind (row 20).
  * Known fiction (brief §10d): the shadow cannot see early assignment of an ITM short call
    across an ex-div date; no ex-div feed exists in the lab, so it is not modeled - grading
    caveat only, flagged here rather than silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")


def wilder_rsi(closes: list, period: int = 2) -> float | None:
    """Wilder RSI on a close series (row 2). Seed = simple average of the first `period`
    gains/losses, then Wilder smoothing avg = (avg*(period-1) + x)/period across the rest.
    None with fewer than period+1 closes. One-sided tapes read 100.0 (all-gain) / 0.0
    (all-loss); a perfectly flat series reads a neutral 50.0 - a dead tape is neither
    overbought nor oversold, so it can never fake the row-3 trigger."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i + 1] - closes[i] for i in range(len(closes) - 1)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss <= 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


@dataclass(frozen=True)
class Rsi2BearCallParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    eval window: brief row 6 '15:45-15:55 ET with near-close values' (ADAPTED - published
    execution is on the daily close). rsi/sma/threshold: rows 2/3/4/7 (SOURCE-VERBATIM /
    SOURCE-RANGE with 95 documented better). history floor: brief §9 (>=210 trading days).
    dte band / width: rows 15/14 (ADAPTED - no options exist in the source). credit,
    liquidity, force-close: rows 17/18/16 (PLATFORM-POLICY)."""
    eval_minute_from: int = 945           # 15:45 ET (row 6)
    eval_minute_to: int = 955             # exclusive; = 15:55 ET (row 6)
    rsi_period: int = 2                   # row 2
    entry_rsi_threshold: float = 95.0     # row 3
    sma_trend_days: int = 200             # row 4 entry filter; row 8 regime-flip exit
    sma_exit_days: int = 5                # row 7 primary exit
    min_history_days: int = 210           # §9 data floor (200d SMA + warmup)
    dte_min_days: int = 10                # row 15
    dte_max_days: int = 17                # row 15
    width_frac_of_spot: float = 0.005     # row 14
    width_floor_usd: float = 1.0          # row 14 floor
    min_credit_frac_of_width: float = 0.30    # row 17
    max_spread_frac_of_mid: float = 0.10      # row 18
    min_open_interest: float = 100.0          # row 18
    force_close_dte: int = 1              # row 16


class Rsi2OverboughtBearCall(Strategy):
    META = StrategyMeta(
        strategy_id="rsi2_overbought_bear_call", version=1,
        name="Connors RSI(2) overbought fade as a defined-risk bear call spread",
        universe=UNIVERSE, dte_range=(5, 16),
        max_concurrent=9,                              # one spread per symbol (row 5)
        event_policy=EventPolicy.TRADE_THROUGH,        # §3.6: no published event/IV gate
        grading_basis=GradingBasis.MAX_LOSS,           # §10: CaR = width - credit
        defining_mechanism="directional_mean_reversion",
        settle_at_expiry=False,                        # row 16 force-close; never rides expiry
        scan_interval_s=300.0, mark_interval_s=300.0,  # close-based doctrine; 5-min cadence
        expected_fires_per_20_sessions=3.0)            # ~2.5/month across regimes (§10)
    params = Rsi2BearCallParams()

    # -- signal engine (rows 1-4, 7, 8) ------------------------------------
    def _signal_state(self, ctx, sym: str) -> dict | None:
        """Daily-close series with the live price standing in for today's close (row 6),
        -> RSI(2) + trend/exit SMAs. None when the reference price or the §9 history floor
        is missing - callers treat None as 'no signal today', never as a default signal."""
        p = self.params
        S = ctx.hub.ref_price(sym)
        if S <= 0:
            return None
        today_iso = ctx.dt_et.date().isoformat()
        bars = ctx.hub.daily_history(sym, days=p.min_history_days + 50)
        closes = [float(b.close) for b in bars if str(b.ts)[:10] < today_iso]
        if len(closes) < p.min_history_days:
            return None
        closes.append(S)                               # today's provisional close (row 6)
        return {"S": S,
                "rsi2": wilder_rsi(closes, p.rsi_period),
                "sma_trend": sum(closes[-p.sma_trend_days:]) / p.sma_trend_days,
                "sma_exit": sum(closes[-p.sma_exit_days:]) / p.sma_exit_days}

    def _pick_expiry(self, ctx, sym: str, today: date) -> tuple:
        """Nearest listed expiration with 10 <= DTE <= 17 calendar days (row 15)."""
        best, best_dte = None, None
        for e in ctx.hub.expirations(sym):
            try:
                y, m, d = map(int, str(e).split("-"))
                dte = (date(y, m, d) - today).days
            except ValueError:
                continue
            if self.params.dte_min_days <= dte <= self.params.dte_max_days:
                if best_dte is None or dte < best_dte:
                    best, best_dte = e, dte
        return best, best_dte

    def _leg_ok(self, row) -> bool:
        """Row 18 liquidity gate: two-sided NBBO, spread <= 10% of mid, OI >= 100."""
        bid, ask = float(row.bid or 0.0), float(row.ask or 0.0)
        if bid <= 0 or ask <= 0:
            return False
        mid = (bid + ask) / 2.0
        if mid <= 0 or (ask - bid) / mid > self.params.max_spread_frac_of_mid:
            return False
        return float(row.open_interest or 0.0) >= self.params.min_open_interest

    def _leg_dict(self, ctx, sym: str, exp: str, row, side: int, S: float, dte: int) -> dict:
        mid = (row.bid + row.ask) / 2.0
        g = ctx.hub.row_greeks(opt_type="call", strike=row.strike, S=S, mid=mid,
                               dte_days=dte) or {}
        return {"occ": row.symbol, "underlying": sym, "opt_type": "call",
                "strike": row.strike, "expiry": exp, "side": side, "qty": 1,
                "nbbo": {"bid": row.bid, "ask": row.ask},
                "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                "theta_day": g.get("theta_day", 0.0)}

    # -- scan (rows 2-6, 12-15, 17-19) -------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        if not (p.eval_minute_from <= ctx.minute < p.eval_minute_to):
            return []                                  # row 6: closing evaluation only
        today = ctx.dt_et.date()
        holding = {pos.underlying for pos in ctx.open_positions}    # row 5: no pyramiding
        out = []
        for sym in self.META.universe:
            if sym in holding:
                continue
            sig = self._signal_state(ctx, sym)
            if sig is None:
                continue                               # no price / thin history -> no signal
            if sig["rsi2"] is None or not (sig["rsi2"] > p.entry_rsi_threshold
                                           and sig["S"] < sig["sma_trend"]):
                continue                               # rows 3+4: trigger AND trend filter
            combo = self._build_spread(ctx, sym, today, sig)
            if combo is not None:
                out.append(combo)
        return out

    def _build_spread(self, ctx, sym: str, today: date, sig: dict):
        """Rows 12-15 structure + rows 17-19 gates. None (with a journal line) when the
        doctrinal contract cannot be built - the strike is never silently moved."""
        p = self.params
        S = sig["S"]
        exp, dte = self._pick_expiry(ctx, sym, today)
        if exp is None:
            self._journal(ctx, {"event": "rsi2bc_no_expiry", "symbol": sym,
                                "day": today.isoformat()})
            return None
        earn = ctx.earnings.get(sym) or {}
        edate = str(earn.get("date") or "")
        if edate and today.isoformat() <= edate <= exp:
            self._journal(ctx, {"event": "rsi2bc_earnings_skip", "symbol": sym,
                                "earnings": edate, "expiry": exp})    # row 19
            return None
        calls = [r for r in ctx.hub.chain(sym, exp) if r.option_type == "call"]
        shorts = [r for r in calls if r.strike >= S]
        if not shorts:
            self._journal(ctx, {"event": "rsi2bc_no_short_strike", "symbol": sym,
                                "expiry": exp, "S_ref": round(S, 4)})
            return None
        short = min(shorts, key=lambda r: r.strike)    # row 13: first strike at/above spot
        width_target = max(p.width_floor_usd, p.width_frac_of_spot * S)   # row 14
        longs = [r for r in calls if r.strike >= short.strike + width_target]
        if not longs:
            self._journal(ctx, {"event": "rsi2bc_no_long_wing", "symbol": sym,
                                "expiry": exp, "short_strike": short.strike})
            return None
        long_ = min(longs, key=lambda r: r.strike)     # row 14: smallest width >= target
        if not (self._leg_ok(short) and self._leg_ok(long_)):
            self._journal(ctx, {"event": "rsi2bc_liquidity_reject", "symbol": sym,
                                "expiry": exp, "short_strike": short.strike,
                                "long_strike": long_.strike})         # row 18
            return None
        width = long_.strike - short.strike
        credit_mid = ((short.bid + short.ask) - (long_.bid + long_.ask)) / 2.0
        if credit_mid < p.min_credit_frac_of_width * width:
            self._journal(ctx, {"event": "rsi2bc_credit_reject", "symbol": sym,
                                "expiry": exp, "credit_mid": round(credit_mid, 4),
                                "width": round(width, 4)})            # row 17
            return None
        return ProposedCombo(
            kind="bear_call_spread", underlying=sym,
            legs=[self._leg_dict(ctx, sym, exp, short, -1, S, dte),
                  self._leg_dict(ctx, sym, exp, long_, +1, S, dte)],
            signal={"S_ref": round(S, 4), "rsi2": round(sig["rsi2"], 2),
                    "sma_trend": round(sig["sma_trend"], 4),
                    "sma_exit": round(sig["sma_exit"], 4),
                    "short_strike": short.strike, "long_strike": long_.strike,
                    "width": round(width, 4), "credit_mid": round(credit_mid, 4),
                    "credit_natural": round(short.bid - long_.ask, 4),
                    "expiry": exp, "dte_days": dte, "earnings": earn or None},
            risk_flags=[])

    # -- manage (rows 7, 8, 10, 11, 16) ------------------------------------
    def manage(self, pos, ctx) -> ExitAction | None:
        p = self.params
        if not (p.eval_minute_from <= ctx.minute < p.eval_minute_to):
            return None                                # §10: exits fire off the close eval only
        combo_mid = self._combo_mid(ctx, pos)
        if combo_mid is None:
            return None                                # no leg quotes -> never exit blind
        today = ctx.dt_et.date()
        dte = (pos.nearest_expiry - today).days
        state = {"combo_mid": round(combo_mid, 4), "dte": dte}
        sig = self._signal_state(ctx, pos.underlying)
        if sig is not None:
            state.update({"S": round(sig["S"], 4),
                          "rsi2": None if sig["rsi2"] is None else round(sig["rsi2"], 2),
                          "sma_exit": round(sig["sma_exit"], 4),
                          "sma_trend": round(sig["sma_trend"], 4)})
            if sig["S"] < sig["sma_exit"]:             # row 7: close under the 5-day SMA
                return ExitAction(action="close", rule="exit_under_5sma", state=state)
            if sig["S"] > sig["sma_trend"]:            # row 8: close above the 200-day SMA
                return ExitAction(action="close", rule="exit_regime_flip_200sma", state=state)
        if dte <= p.force_close_dte:                   # row 16: calendar-only, needs no signal
            return ExitAction(action="close", rule="force_close_1dte", state=state)
        return None                                    # rows 10/11: no stop, no target - hold

    def _combo_mid(self, ctx, pos) -> float | None:
        """Signed combo cost at leg NBBO mids (model sign convention: negative = credit).
        None when ANY leg quote is missing - the caller holds."""
        total = 0.0
        for ls in pos.legs:
            nb = ctx.hub.last_nbbo(ls.spec.occ)
            if nb is None:
                return None
            total += ls.spec.side * ls.spec.qty * ((nb[0] + nb[1]) / 2.0)
        return total

    @staticmethod
    def _journal(ctx, rec: dict) -> None:
        if ctx.journal:
            ctx.journal(rec)
