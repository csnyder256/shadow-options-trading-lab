"""earnings_iv_crush_strangle - short 16-delta strangle into earnings, next-open buyback.

AUTHORITY: docs/strategies/briefs/earnings_iv_crush_strangle.md (verified CORRECTED
2026-07-19, zero invented constants). Provenance: tastytrade Market Measures study cards
2015-10-23 / 2018-10-29 / 2019-01-14 (archived pages read directly); academic support
Dubinsky & Johannes (RFS 2019); counter-result Xing & Zhang recorded in §6/§7. Every
constant below cites its brief §8 row.

Doctrine (brief §3/§4 - §4 OVERRIDES all platform exit doctrine for this cohort):
  * REQUIRES_EVENT (row 5: "Sold the Day Before Earnings"): fires ONLY when a universe
    name reports between today's close and tomorrow's open - AMC dated D → enter D's
    closing window; BMO dated D → enter the closing window of the last trading session
    BEFORE D (weekend/holiday-aware). Timing metadata is load-bearing (§7 announcement-
    timing errors + SOURCE_VIABILITY consequence 5): hour must be bmo|amc AND
    timing_reliable AND the date must parse - an unreliable-timing symbol is NEVER traded.
  * Structure (rows 1-2): one short OTM call + one short OTM put, same expiration, 1 lot
    each (row 15, account-blind), strike per side = ABSOLUTE solved delta nearest 0.16
    ("Sold 16 delta Strangles") via hub.row_greeks; two-sided-NBBO rows only (row 16).
  * Tenor (rows 3-4): the nearest listed expiration whose session close falls strictly
    AFTER the announcement, within META.dte_range - AMC dated D → expiry >= D+1 (a
    D-expiry dies at the close BEFORE the evening report); BMO dated D → expiry >= D
    (D's own close is after the morning report - the true front weekly).
  * Entry timing (row 6, ADAPTED): 15:45-16:00 ET window of the entry session - the last
    feasible quotes before the close, maximizing captured event premium.
  * Exit (rows 7-8): unconditional buy-back at the NEXT session's open - manage() fires
    `post_earnings_open_exit` on the first mark at/after 09:30 ET on any day after
    entry_day, WITHOUT consulting quotes (a stale/missing NBBO never delays the mandatory
    buy-back; the runner fills from its book). NO profit target (row 9 - never import the
    45-DTE "manage at 50%" rule), NO stop (row 10 - the hold is one overnight gap, nothing
    can execute inside it), NEVER roll (row 11 - the close branch is fixed).
  * VIX at entry is RECORDED, never gated (row 12); no IV entry gate exists (row 13).
  * CaR basis (row 17): two naked shorts → payoff_analysis derives unbounded_up → CAR
    (Reg-T naked-strangle proxy: greater single-side requirement + other side's premium).
    settle_at_expiry=False: the trade never holds to expiry; the global expiry-day
    backstop stays armed behind the mandatory open buy-back.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from atlas.options.session_calendar import is_trading_day

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")

_RELIABLE_HOURS = ("bmo", "amc")      # SOURCE_VIABILITY consequence 5: dmh/empty NEVER trade


@dataclass(frozen=True)
class EarningsIvCrushParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    target_abs_delta: row 2 SOURCE-VERBATIM "Sold 16 delta Strangles" (nearest-strike per
    side). entry_minute_from/to: row 6 ADAPTED 15:45-16:00 ET window (no clock time
    published; latest-before-close matches "prior to the announcement"; end exclusive).
    exit_minute_from: row 8 ADAPTED - T+1 09:30 ET opening prints; the 09:35 window end is
    the fill convention, not a manage gate - the buy-back demand is unconditional (row 7)
    and stands until filled. dte_min/max_days: rows 3-4 - front weekly nearest after the
    announcement; min 1 (entry always precedes the announcement session boundary), max 12
    mirrors META.dte_range (studied range ran front week → 3 weeks; front week default)."""
    target_abs_delta: float = 0.16
    entry_minute_from: int = 945          # 15:45 ET
    entry_minute_to: int = 960            # exclusive; = 16:00 ET
    exit_minute_from: int = 570           # 09:30 ET, next session
    dte_min_days: int = 1
    dte_max_days: int = 12


class EarningsIvCrushStrangle(Strategy):
    META = StrategyMeta(
        strategy_id="earnings_iv_crush_strangle", version=1,
        name="Earnings IV-crush: short 16Δ strangle, sold the close before, covered next open",
        universe=UNIVERSE, dte_range=(1, 12),
        max_concurrent=3,
        event_policy=EventPolicy.REQUIRES_EVENT,       # row 5: event-driven, never systematic
        grading_basis=GradingBasis.CAR,                # row 17: undefined risk → Reg-T proxy
        defining_mechanism="event_premium",
        settle_at_expiry=False,                        # §4: never holds to expiry
        scan_interval_s=60.0, mark_interval_s=60.0,    # §10: one entry + one exit mark matter
        expected_fires_per_20_sessions=4.0)            # §10: ~2/mo avg, clustered in seasons
    params = EarningsIvCrushParams()

    # -- timing (rows 5-6) -------------------------------------------------
    @staticmethod
    def _parse_date(v) -> date | None:
        try:
            return date.fromisoformat(str(v))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _entry_session_for(report: date, hour: str) -> date | None:
        """The session whose CLOSE immediately precedes the announcement (row 5):
        amc → the report day itself; bmo → the last trading day strictly before the
        report (weekend/holiday-aware via is_trading_day; bounded walk-back)."""
        if hour == "amc":
            return report
        d = report - timedelta(days=1)
        for _ in range(7):
            if is_trading_day(d):
                return d
            d -= timedelta(days=1)
        return None

    # -- tenor (rows 3-4) --------------------------------------------------
    def _pick_expiry(self, ctx, sym: str, today: date, report: date,
                     hour: str) -> str | None:
        """Nearest listed expiration whose session close is strictly after the
        announcement: bmo → >= report date; amc → >= report+1. DTE within
        [dte_min_days, dte_max_days]; None = nothing qualifies (skip, journal)."""
        min_exp = report if hour == "bmo" else report + timedelta(days=1)
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

    # -- strike selection (row 2) ------------------------------------------
    def _select_leg(self, ctx, rows: list, *, opt_type: str, S: float,
                    dte: int) -> tuple | None:
        """OTM row with a two-sided NBBO whose ABSOLUTE solved delta is nearest
        target_abs_delta (row 2; 16Δ legs are OTM by definition). Returns
        (row, greeks) or None; rows the solver cannot price are skipped."""
        target = self.params.target_abs_delta
        best, best_err = None, None
        for r in rows:
            if r.option_type != opt_type:
                continue
            if (r.bid or 0) <= 0 or (r.ask or 0) <= 0:     # row 16: two-sided NBBO only
                continue
            if (opt_type == "call" and r.strike <= S) or \
                    (opt_type == "put" and r.strike >= S):
                continue
            mid = (r.bid + r.ask) / 2.0
            g = ctx.hub.row_greeks(opt_type=opt_type, strike=r.strike, S=S, mid=mid,
                                   dte_days=dte)
            if not g:
                continue
            err = abs(abs(g["delta"]) - target)
            if best_err is None or err < best_err:
                best, best_err = (r, g), err
        return best

    @staticmethod
    def _leg_dict(sym: str, exp: str, opt_type: str, row, g: dict) -> dict:
        return {"occ": row.symbol, "underlying": sym, "opt_type": opt_type,
                "strike": row.strike, "expiry": exp, "side": -1, "qty": 1,
                "nbbo": {"bid": row.bid, "ask": row.ask},
                "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                "theta_day": g.get("theta_day", 0.0)}

    @staticmethod
    def _vix_close(ctx):
        """Row 12: record VIX at entry - observe-only, NO gate, absent → None."""
        fn = getattr(ctx.hub, "vol_regime", None)
        vr = (fn() if callable(fn) else None) or {}
        try:
            v = float(vr.get("vix_close"))
            return round(v, 2) if v > 0 else None
        except (TypeError, ValueError):
            return None

    # -- scan (rows 1-6, 14-16) --------------------------------------------
    def scan(self, ctx) -> list:
        today = ctx.dt_et.date()
        p = self.params
        if not (p.entry_minute_from <= ctx.minute < p.entry_minute_to):
            return []
        held = {pos.underlying for pos in ctx.open_positions}   # one strangle per name
        out = []
        for sym in self.META.universe:
            earn = ctx.earnings.get(sym) or {}
            if not earn:
                continue                                        # no report on file - quiet
            if sym in held:
                continue
            hour = str(earn.get("hour") or "").lower()
            report = self._parse_date(earn.get("date"))
            if hour not in _RELIABLE_HOURS or not earn.get("timing_reliable") \
                    or report is None:
                if ctx.journal:                                 # consequence-5 screen: NEVER trade
                    ctx.journal({"event": "eivc_timing_screen_skip", "symbol": sym,
                                 "hour": hour,
                                 "timing_reliable": bool(earn.get("timing_reliable")),
                                 "date": str(earn.get("date") or "")})
                continue
            if today != self._entry_session_for(report, hour):
                continue                                        # not the pre-report close
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            exp = self._pick_expiry(ctx, sym, today, report, hour)
            if exp is None:
                if ctx.journal:
                    ctx.journal({"event": "eivc_no_expiry", "symbol": sym,
                                 "day": str(today), "report": report.isoformat(),
                                 "hour": hour})
                continue
            dte = (date.fromisoformat(exp) - today).days
            rows = ctx.hub.chain(sym, exp)
            call = self._select_leg(ctx, rows, opt_type="call", S=S_ref, dte=dte)
            put = self._select_leg(ctx, rows, opt_type="put", S=S_ref, dte=dte)
            if call is None or put is None:
                if ctx.journal:
                    ctx.journal({"event": "eivc_no_strike", "symbol": sym, "expiry": exp,
                                 "S_ref": round(S_ref, 4),
                                 "missing": [name for name, leg in
                                             (("call", call), ("put", put)) if leg is None]})
                continue
            (c_row, c_g), (p_row, p_g) = call, put
            credit_bid = round(c_row.bid + p_row.bid, 4)
            out.append(ProposedCombo(
                kind="short_strangle", underlying=sym,
                legs=[self._leg_dict(sym, exp, "call", c_row, c_g),
                      self._leg_dict(sym, exp, "put", p_row, p_g)],
                signal={"report_date": report.isoformat(), "report_hour": hour,
                        "S_ref": round(S_ref, 4), "expiry": exp, "dte_days": dte,
                        "call_strike": c_row.strike, "put_strike": p_row.strike,
                        "call_delta": round(c_g["delta"], 4),
                        "put_abs_delta": round(abs(p_g["delta"]), 4),
                        "credit_bid": credit_bid,
                        "credit_pct_of_S": round(100.0 * credit_bid / S_ref, 3),
                        "vix_at_entry": self._vix_close(ctx),   # row 12: log-only
                        "earnings": dict(earn)}))
        return out

    # -- manage (§4, rows 7-11): unconditional next-open buy-back ----------
    def manage(self, pos, ctx):
        """Rows 7-8: cover at the next session's open - first mark at/after 09:30 ET on
        any day AFTER entry_day (ISO day strings compare chronologically). Quote-blind by
        design: a stale or missing NBBO never delays the mandatory buy-back (the runner
        fills from its book). No profit target (row 9), no stop (row 10), no roll
        (row 11) - otherwise hold through the one overnight gap."""
        if ctx.day > pos.entry_day and ctx.minute >= self.params.exit_minute_from:
            return ExitAction(action="close", rule="post_earnings_open_exit",
                              state={"entry_day": pos.entry_day, "exit_day": ctx.day,
                                     "exit_minute": ctx.minute})
        return None
