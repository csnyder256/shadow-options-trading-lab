"""wput_weekly_putwrite - WPUT-style weekly ATM put-write, hold to expiry.

AUTHORITY: docs/strategies/briefs/wput_weekly_putwrite.md (verified CORRECTED 2026-07-19,
zero invented constants). Provenance: Cboe PutWrite Indices Methodology v2.0 (2025-10-15),
WPUT rows; performance context Bondarenko 2019. Every constant below cites its brief row.

Doctrine (brief §3/§4 - overrides ALL platform exit doctrine for this cohort):
  * UNCONDITIONAL weekly write - no IV gate, no regime gate, no event filter (row 11,
    SOURCE-VERBATIM absence). Single names write THROUGH earnings and get tagged (row 21).
  * Entry: every Friday (exchange-holiday Friday -> preceding business day, row 6), in the
    final minutes before 16:00 ET (row 9, ADAPTED from the PM branch), sell 1 put at the
    first strike strictly BELOW the reference price (row 7/8), expiring the next roll Friday
    (row 5: 1-week tenor, 6-8 calendar days across holidays).
  * Exit: HOLD TO EXPIRY. No profit target (row 13), no stop (row 14), no intra-week roll.
    manage() therefore always returns None; settlement is the runner's intrinsic-at-close
    path (settle_at_expiry=True), the shadow analogue of the published PM buyback (row 12).
  * CaR basis: cash-secured strike notional K*100 - credit (row 16) - this is exactly what
    payoff_analysis derives for a naked short put (max loss at S=0), so grading_basis is
    MAX_LOSS. Do NOT use the Reg-T proxy: the brief warns it silently levers ~5x (§10).

This is the wave-1 EXEMPLAR module: the idiom every other strategy module copies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from atlas.options.session_calendar import is_trading_day

from ..strategy import (EventPolicy, GradingBasis, ProposedCombo, Strategy, StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")


@dataclass(frozen=True)
class WputParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    entry_window: brief row 9 'final minutes before 4:00 p.m. ET' (ADAPTED - the source gives
    the PM-branch convention, not a minute count). dte bounds: brief row 5 derived 6-8 calendar
    days, widened by 1 each side as listing tolerance (PLATFORM-POLICY)."""
    entry_minute_from: int = 955          # 15:55 ET
    entry_minute_to: int = 960            # exclusive; = 16:00 ET
    dte_min_days: int = 5
    dte_max_days: int = 9


class WputWeeklyPutWrite(Strategy):
    META = StrategyMeta(
        strategy_id="wput_weekly_putwrite", version=1,
        name="WPUT-style weekly ATM put-write, hold to expiry",
        universe=UNIVERSE, dte_range=(4, 9),
        max_concurrent=18,                 # 9 symbols x (expiring old + freshly written) on roll day
        event_policy=EventPolicy.TRADE_THROUGH,       # row 11: unconditional
        grading_basis=GradingBasis.MAX_LOSS,          # row 16: cash-secured strike notional
        defining_mechanism="short_vol_carry",
        settle_at_expiry=True,                        # row 12: hold to expiry, intrinsic settle
        scan_interval_s=60.0, mark_interval_s=300.0,  # daily-EOD doctrine; 5-min marks are diagnostic
        expected_fires_per_20_sessions=36.0)          # ~9/week (brief §10)
    params = WputParams()

    # -- roll-day math (row 6) --------------------------------------------
    @staticmethod
    def roll_day_of_week(today: date) -> date:
        """This week's roll date: Friday, or the preceding business day when Friday is a
        holiday. Pure calendar math + is_trading_day."""
        friday = today + timedelta(days=4 - today.weekday())
        d = friday
        while not is_trading_day(d) and d > friday - timedelta(days=4):
            d -= timedelta(days=1)
        return d

    def _next_expiry(self, ctx, sym: str, today: date) -> str | None:
        """Nearest listed expiration in [dte_min, dte_max] days out (row 5); None = no listing."""
        best, best_dte = None, None
        for e in ctx.hub.expirations(sym):
            try:
                y, m, d = map(int, e.split("-"))
                dte = (date(y, m, d) - today).days
            except ValueError:
                continue
            if self.params.dte_min_days <= dte <= self.params.dte_max_days:
                if best_dte is None or dte < best_dte:
                    best, best_dte = e, dte
        return best

    # -- scan (rows 6-11) --------------------------------------------------
    def scan(self, ctx) -> list:
        today = ctx.dt_et.date()
        if today != self.roll_day_of_week(today):
            return []
        if not (self.params.entry_minute_from <= ctx.minute < self.params.entry_minute_to):
            return []
        holding = {p.underlying for p in ctx.open_positions
                   if p.nearest_expiry > today}          # this week's put already written
        out = []
        for sym in self.META.universe:
            if sym in holding:
                continue
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            exp = self._next_expiry(ctx, sym, today)
            if exp is None:
                if ctx.journal:
                    ctx.journal({"event": "wput_no_expiry", "symbol": sym, "day": str(today)})
                continue
            rows = ctx.hub.chain(sym, exp)
            puts = [r for r in rows if r.option_type == "put" and r.strike < S_ref
                    and (r.bid or 0) > 0 and (r.ask or 0) > 0]
            if not puts:
                if ctx.journal:
                    ctx.journal({"event": "wput_no_strike", "symbol": sym, "expiry": exp,
                                 "S_ref": round(S_ref, 4)})
                continue
            row = max(puts, key=lambda r: r.strike)      # FIRST strike below reference (row 7)
            mid = (row.bid + row.ask) / 2.0
            dte = max(1, (date.fromisoformat(exp) - today).days)
            g = ctx.hub.row_greeks(opt_type="put", strike=row.strike, S=S_ref, mid=mid,
                                   dte_days=dte) or {}
            earn = ctx.earnings.get(sym) or {}
            risk_flags = []
            if earn and str(earn.get("date") or "") <= exp:
                risk_flags.append("holds_through_earnings")   # row 21: write-and-tag, never skip
            out.append(ProposedCombo(
                kind="short_put_weekly", underlying=sym,
                legs=[{"occ": row.symbol, "underlying": sym, "opt_type": "put",
                       "strike": row.strike, "expiry": exp, "side": -1, "qty": 1,
                       "nbbo": {"bid": row.bid, "ask": row.ask},
                       "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                       "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                       "theta_day": g.get("theta_day", 0.0)}],
                signal={"S_ref": round(S_ref, 4), "strike": row.strike, "expiry": exp,
                        "dte_days": dte, "credit_bid": row.bid,
                        "credit_pct_of_S": round(100.0 * row.bid / S_ref, 3),
                        "earnings": earn or None},
                risk_flags=risk_flags))
        return out

    # -- manage (rows 12-14): hold to expiry, full stop --------------------
    def manage(self, pos, ctx):
        return None
