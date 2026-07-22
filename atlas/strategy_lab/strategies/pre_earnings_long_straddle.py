"""pre_earnings_long_straddle - buy an ATM straddle T-3, sell it T-1 before the print.

AUTHORITY: docs/strategies/briefs/pre_earnings_long_straddle.md (verified CONFIRMED
2026-07-19, zero invented constants). Provenance: Gao, Xing & Zhang, "Anticipating
Uncertainty: Straddles Around Earnings Announcements" (JFQA 2018). Every constant cites its
brief §8 row / Section II filter.

Doctrine (§3/§4 - §4 OVERRIDES all platform exit doctrine for this cohort):
  * REQUIRES_EVENT: fires only when a universe name's next scheduled earnings date is the
    strategy's entry offset (T-3 trading days) ahead. Timing metadata (SOURCE_VIABILITY
    consequence 5): the source ignores announcement HOUR (Section II) but our platform still
    requires timing_reliable so the T-1 exit is guaranteed before the print for both BMO and
    AMC reporters - an unreliable-timing symbol is NEVER traded.
  * Structure: LONG 1 ATM call + LONG 1 ATM put, same strike + same expiration (filter 8),
    1 lot each (per-unit framing, §5). ATM = moneyness 0.9-1.1 (filter 7) AND |delta|
    0.375-0.625 (filter 6); the qualifying strike nearest moneyness 1.00 wins (ADAPTED - a
    1-lot shadow cannot average across pairs; ties → higher combined volume). Both legs need
    price >= $0.125 (filter 1), positive OI (filter 3), two-sided NBBO (filter 4).
  * Tenor: 10-60 days to maturity at formation (filter 5); nearest listed expiry in band that
    postdates the announcement (always true for a 10-60d option on T-3).
  * Entry: end-of-day of the T-3 session at the closing bid-ask midpoint (Section III.C).
  * Exit (§4): UNCONDITIONAL time exit at the T-1 session close - the [-3,-1] window, the only
    window guaranteed to exit before the print for BMO and AMC reporters. NO profit target,
    NO stop, NO roll, NO rebalance, NEVER hold to expiry (max published hold 4 trading days;
    ours is 2). Failsafe: if the announcement moved earlier so the print precedes our T-1
    exit, close at the first mark and flag calendar_error.
  * DEBIT basis: a long straddle's max loss is the debit paid (payoff_analysis derives it).
    settle_at_expiry=False - the trade always exits before the print, never at expiry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from atlas.options.session_calendar import is_trading_day

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")
_RELIABLE_HOURS = ("bmo", "amc")


@dataclass(frozen=True)
class PreEarningsStraddleParams:
    """Tunables (pre-registered tweak neighborhood; the rest is doctrine).
    entry_offset_sessions: §3 'buy the straddle on day -3' (SOURCE-VERBATIM, T-3 trading days).
    entry/exit_minute_from/to: §3/§4 end-of-day closing-midpoint convention (ADAPTED clock - 
    no wall time published; 15:45-16:00 ET matches 'closing bid-ask average').
    abs_delta_lo/hi: filter 6 SOURCE-VERBATIM 'absolute delta between 0.375 and 0.625'.
    moneyness_lo/hi: filter 7 SOURCE-VERBATIM 'moneyness between 0.9 and 1.1'.
    min_option_price: filter 1 SOURCE-VERBATIM 'option prices are at least $0.125'.
    dte_min/max_days: filter 5 SOURCE-VERBATIM '10 to 60 days to maturity'."""
    entry_offset_sessions: int = 3
    entry_minute_from: int = 945          # 15:45 ET
    entry_minute_to: int = 960            # exclusive; 16:00 ET
    exit_minute_from: int = 945           # T-1 close window
    abs_delta_lo: float = 0.375
    abs_delta_hi: float = 0.625
    moneyness_lo: float = 0.9
    moneyness_hi: float = 1.1
    min_option_price: float = 0.125
    dte_min_days: int = 10
    dte_max_days: int = 60


class PreEarningsLongStraddle(Strategy):
    META = StrategyMeta(
        strategy_id="pre_earnings_long_straddle", version=1,
        name="Pre-earnings ATM straddle bought T-3, sold T-1 before the print",
        universe=UNIVERSE, dte_range=(10, 60),
        max_concurrent=3,
        event_policy=EventPolicy.REQUIRES_EVENT,
        grading_basis=GradingBasis.DEBIT,
        defining_mechanism="event_premium",
        settle_at_expiry=False,
        scan_interval_s=300.0, mark_interval_s=300.0,
        expected_fires_per_20_sessions=4.0)
    params = PreEarningsStraddleParams()

    # -- trading-day offsets ----------------------------------------------
    @staticmethod
    def _parse_date(v) -> date | None:
        try:
            return date.fromisoformat(str(v))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _sessions_before(report: date, n: int) -> date | None:
        """The n-th trading day strictly before `report` (weekend/holiday-aware)."""
        d = report
        left = n
        for _ in range(3 * n + 10):
            d -= timedelta(days=1)
            if is_trading_day(d):
                left -= 1
                if left == 0:
                    return d
        return None

    def _pick_expiry(self, ctx, sym: str, today: date, report: date) -> str | None:
        min_exp = report + timedelta(days=1)      # must postdate the announcement
        best, best_dte = None, None
        for e in ctx.hub.expirations(sym):
            d = self._parse_date(e)
            if d is None or d < min_exp:
                continue
            dte = (d - today).days
            if not (self.params.dte_min_days <= dte <= self.params.dte_max_days):
                continue
            if best_dte is None or dte < best_dte:
                best, best_dte = e, dte
        return best

    def _atm_strike(self, ctx, rows: list, S: float, dte: int) -> float | None:
        """The strike present as BOTH a qualifying call and put, moneyness 0.9-1.1 and
        |delta| 0.375-0.625, nearest moneyness 1.00 (ties → higher combined volume)."""
        p = self.params
        by_strike: dict[float, dict] = {}
        for r in rows:
            if r.strike <= 0 or (r.bid or 0) <= 0 or (r.ask or 0) <= 0:
                continue
            mid = (r.bid + r.ask) / 2.0
            if mid < p.min_option_price or (r.open_interest or 0) <= 0:
                continue
            money = r.strike / S if S > 0 else 0.0
            if not (p.moneyness_lo <= money <= p.moneyness_hi):
                continue
            g = ctx.hub.row_greeks(opt_type=r.option_type, strike=r.strike, S=S, mid=mid,
                                   dte_days=dte)
            if not g or not (p.abs_delta_lo <= abs(g["delta"]) <= p.abs_delta_hi):
                continue
            by_strike.setdefault(r.strike, {})[r.option_type] = (r, g)
        paired = [(k, v) for k, v in by_strike.items() if "call" in v and "put" in v]
        if not paired:
            return None
        def key(item):
            k, v = item
            vol = (v["call"][0].volume or 0) + (v["put"][0].volume or 0)
            return (abs(k / S - 1.0), -vol)
        return min(paired, key=key)[0]

    @staticmethod
    def _leg_dict(sym, exp, opt_type, row, g) -> dict:
        return {"occ": row.symbol, "underlying": sym, "opt_type": opt_type,
                "strike": row.strike, "expiry": exp, "side": +1, "qty": 1,
                "nbbo": {"bid": row.bid, "ask": row.ask},
                "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                "theta_day": g.get("theta_day", 0.0)}

    # -- scan --------------------------------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        today = ctx.dt_et.date()
        if not (p.entry_minute_from <= ctx.minute < p.entry_minute_to):
            return []
        held = {pos.underlying for pos in ctx.open_positions}
        out = []
        for sym in self.META.universe:
            earn = ctx.earnings.get(sym) or {}
            if not earn or sym in held:
                continue
            hour = str(earn.get("hour") or "").lower()
            report = self._parse_date(earn.get("date"))
            if hour not in _RELIABLE_HOURS or not earn.get("timing_reliable") or report is None:
                if ctx.journal:
                    ctx.journal({"event": "pes_timing_screen_skip", "symbol": sym, "hour": hour,
                                 "date": str(earn.get("date") or "")})
                continue
            if today != self._sessions_before(report, p.entry_offset_sessions):
                continue                               # not the T-3 session
            S = ctx.hub.ref_price(sym)
            if S <= 0:
                continue
            exp = self._pick_expiry(ctx, sym, today, report)
            if exp is None:
                if ctx.journal:
                    ctx.journal({"event": "pes_no_expiry", "symbol": sym, "report": report.isoformat()})
                continue
            dte = (date.fromisoformat(exp) - today).days
            rows = ctx.hub.chain(sym, exp)
            k = self._atm_strike(ctx, rows, S, dte)
            if k is None:
                if ctx.journal:
                    ctx.journal({"event": "pes_no_atm", "symbol": sym, "expiry": exp,
                                 "S": round(S, 4)})
                continue
            by = {}
            for r in rows:
                if r.strike == k and r.option_type in ("call", "put"):
                    mid = (r.bid + r.ask) / 2.0
                    g = ctx.hub.row_greeks(opt_type=r.option_type, strike=k, S=S, mid=mid,
                                           dte_days=dte) or {}
                    by[r.option_type] = (r, g)
            if "call" not in by or "put" not in by:
                continue
            exit_session = self._sessions_before(report, 1)
            out.append(ProposedCombo(
                kind="long_straddle", underlying=sym,
                legs=[self._leg_dict(sym, exp, "call", *by["call"]),
                      self._leg_dict(sym, exp, "put", *by["put"])],
                signal={"report_date": report.isoformat(), "report_hour": hour,
                        "S": round(S, 4), "strike": k, "expiry": exp, "dte_days": dte,
                        "debit_ask": round(by["call"][0].ask + by["put"][0].ask, 4),
                        "notes": {"report_date": report.isoformat(),
                                  "exit_session": exit_session.isoformat() if exit_session else ""}}))
        return out

    # -- manage (§4): unconditional T-1 time exit + calendar failsafe ------
    def manage(self, pos, ctx):
        notes = pos.notes or {}
        exit_session = str(notes.get("exit_session") or "")
        report_date = str(notes.get("report_date") or "")
        # failsafe: never hold into or past the announcement session
        if report_date and ctx.day >= report_date:
            return ExitAction(action="close", rule="pre_print_failsafe",
                              state={"report_date": report_date, "flag": "calendar_error"})
        if exit_session and ctx.day >= exit_session and ctx.minute >= self.params.exit_minute_from:
            return ExitAction(action="close", rule="pre_print_exit",
                              state={"exit_session": exit_session, "report_date": report_date})
        return None
