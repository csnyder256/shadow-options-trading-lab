"""overnight_1dte_strangle - Muravyev-Ni overnight option premium: sell a ~25Δ 1DTE strangle
near the close, buy it back at the next open.

AUTHORITY: docs/strategies/briefs/overnight_1dte_strangle.md (verified CORRECTED, second
adversarial pass CONFIRMED, 2026-07-19). Provenance: Muravyev & Ni, JFE 2020 (Internet
Appendix read in full). The 25Δ / 1DTE / unhedged-strangle shape is the brief's tagged
ADAPTATION of the published decomposition - the brief's honesty box governs grading claims.
Every constant below cites its brief row.

Doctrine (brief §3/§4 - §4 overrides ALL platform exit doctrine for this cohort):
  * UNCONDITIONAL every-night short - no IV gate, no regime gate, no event filter (rows
    9/10, SOURCE-VERBATIM absence). Fridays INCLUDED (weekend nights are MORE negative in
    the source, row 9). CPI/NFP-eve nights are TRADED THROUGH and TAGGED for split grading
    (row 18, PLATFORM-POLICY) - the brief records NO event stand-down; 8:30 a.m. releases
    land inside the close→open hold, FOMC (2 p.m.) is outside it.
  * Entry: last minutes before the session close (row 7 + §9: snapshot ~3:45-4:00 p.m. ET
    → [session_close_min-15, session_close_min)), sell 1 OTM call + 1 OTM put (row 3),
    each at the listed strike nearest |Δ|=0.25 (row 4), accept 0.15 ≤ |Δ| ≤ 0.30 on the
    selected strike else skip the symbol that night (row 5). Expiry = NEXT trading session
    (row 6): the nearest listed expiration STRICTLY after today within META.dte_range
    (0DTE excluded; Fri→Mon = 3 calendar days). Both legs need two-sided NBBO; one
    strangle per underlying per night (row 20); an already-open position blocks re-entry.
  * Exit: unconditional buy-back of BOTH legs at the next market open (row 11: 9:30 a.m.
    ET, first clean snapshot 9:30-9:35) - manage() fires `next_open_buyback` on the first
    mark at/after 09:30 ET on any day after entry_day, WITHOUT consulting quotes (missing
    quotes never delay the mandatory buy-back; the runner fills from its book). No profit
    target (row 13), no stop loss (row 14), no rolls (row 15). settle_at_expiry=False:
    the exit morning IS expiry day, and the global expiry-day backstop is the safety net
    behind the mandatory open buy-back (§4).
  * CaR basis (row 21): two naked shorts → payoff_analysis derives unbounded_up → CAR
    (reg_t_v1 strangle proxy: greater single-side requirement + other side's premium).
    grading_basis=CAR matches the derived basis; returns are NOT floored at -1.

Universe note: ETF trio only (row 2 core; META verbatim). Row 17's earnings skip applies
to single names only ("ETFs never skipped") - moot here; it MUST be implemented before any
single-name expansion. Row 19's ex-div-night skip is NOT implemented: no ex-div feed exists
on the ctx/hub surface (known gap - call-leg early-assignment channel, §7; row 16 forced
exits are the runner's book-keeping). A holiday long weekend (Fri→Tue = 4 calendar days)
falls outside dte_range=(0,3) and is skipped that night (journaled no_expiry).

Cadence (§10): exactly two meaningful marks per trade - the entry close snapshot and the
exit open snapshot. expected_fires_per_20_sessions=60 is the 3-symbols x 20-nights ceiling
(brief §10 estimates ~55/month realistic with IWM's M/W/F listings).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM")

_ET = ZoneInfo("America/New_York")
_OPEN_T = time(9, 30)          # row 11: "An overnight period is from 4:15 pm to 9:30 am."


@dataclass(frozen=True)
class OvernightStrangleParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    entry_lead_min: row 7 + §9 - entry snapshot ~3:45-4:00 p.m. ET → last 15 min before the
    session close (SOURCE-RANGE; relative to session_close_min so half days inherit it).
    delta_target: row 4 (ADAPTED - 25Δ is the boundary of the published most-negative
    0.1<|Δ|<0.25 bucket). delta_band_lo/hi: row 5 tolerance band 0.15-0.30, selected-strike
    out-of-band → skip symbol that night (PLATFORM-POLICY). exit_minute_from: row 11 - 
    next open 9:30 a.m. ET (570), first clean quote snapshot 9:30-9:35 (SOURCE-VERBATIM)."""
    entry_lead_min: int = 15
    delta_target: float = 0.25
    delta_band_lo: float = 0.15
    delta_band_hi: float = 0.30
    exit_minute_from: int = 570           # 09:30 ET


class Overnight1dteStrangle(Strategy):
    META = StrategyMeta(
        strategy_id="overnight_1dte_strangle", version=1,
        name="Muravyev-Ni overnight premium: short ~25Δ 1DTE strangle, close→open",
        universe=UNIVERSE, dte_range=(0, 3),
        max_concurrent=3,                             # one strangle per ETF per night (row 20)
        event_policy=EventPolicy.TRADE_THROUGH,       # rows 9/18: unconditional, tag-not-skip
        grading_basis=GradingBasis.CAR,               # row 21: Reg-T short-strangle proxy
        defining_mechanism="overnight_premium",
        settle_at_expiry=False,                       # §4: mandatory open buy-back on expiry morning
        scan_interval_s=60.0, mark_interval_s=60.0,   # §10: entry + open snapshots are the trade
        expected_fires_per_20_sessions=60.0)          # 3 symbols x 20 nights ceiling (§10)
    params = OvernightStrangleParams()

    # -- expiry (row 6) ----------------------------------------------------
    def _next_session_expiry(self, ctx, sym: str, today: date) -> tuple:
        """Row 6: expiry = NEXT trading session - nearest listed expiration STRICTLY after
        today (0DTE excluded), within META.dte_range calendar days (3 covers Fri→Mon; a
        holiday Fri→Tue gap of 4 falls outside the band → that night is a skip)."""
        hi = self.META.dte_range[1]
        best, best_dte = None, None
        for e in ctx.hub.expirations(sym):
            try:
                dte = (date.fromisoformat(str(e)) - today).days
            except ValueError:
                continue
            if 1 <= dte <= hi and (best_dte is None or dte < best_dte):
                best, best_dte = str(e), dte
        return best, best_dte

    # -- strike selection (rows 3/4/5) -------------------------------------
    def _pick_leg(self, ctx, rows, opt_type: str, S_ref: float, dte_days: int):
        """Row 4: the listed strike nearest |Δ|=0.25 among OTM (row 3) two-sided rows;
        row 5: the SELECTED strike must satisfy 0.15 ≤ |Δ| ≤ 0.30 else None (symbol skip - 
        coarse-ladder skips are expected and logged, §10d). Returns (row, greeks) | None."""
        best = None                                   # (dist, row, greeks, |delta|)
        for r in rows:
            if r.option_type != opt_type:
                continue
            if opt_type == "call" and r.strike <= S_ref:      # row 3: OTM call only
                continue
            if opt_type == "put" and r.strike >= S_ref:       # row 3: OTM put only
                continue
            if not ((r.bid or 0) > 0 and (r.ask or 0) > 0):   # two-sided NBBO required
                continue
            mid = (r.bid + r.ask) / 2.0
            g = ctx.hub.row_greeks(opt_type=opt_type, strike=r.strike, S=S_ref, mid=mid,
                                   dte_days=dte_days)
            if not g:
                continue
            ad = abs(g.get("delta") or 0.0)
            dist = abs(ad - self.params.delta_target)
            if best is None or dist < best[0]:
                best = (dist, r, g, ad)
        if best is None:
            return None
        _, r, g, ad = best
        if not (self.params.delta_band_lo <= ad <= self.params.delta_band_hi):
            return None                               # row 5: out-of-band → skip symbol
        return r, g

    # -- macro-eve tagging (row 18) ----------------------------------------
    @staticmethod
    def _macro_kinds_in_window(ctx, exp_date: date) -> list:
        """Row 18: CPI/NFP-eve nights are TRADED THROUGH and TAGGED - the 8:30 a.m. release
        lands inside the close→open hold; FOMC (2 p.m.) is outside it. Window = (now,
        exit-session open 09:30 ET]. Pure time-window check over ctx.events (EconEvent)."""
        start = ctx.dt_et if ctx.dt_et.tzinfo is not None else ctx.dt_et.replace(tzinfo=_ET)
        end = datetime.combine(exp_date, _OPEN_T, tzinfo=_ET)
        kinds = []
        for ev in ctx.events or []:
            ts = getattr(ev, "ts_et", None)
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_ET)
            k = str(getattr(ev, "kind", "") or "")
            if start < ts <= end and k and k not in kinds:
                kinds.append(k)
        return kinds

    # -- scan (rows 3-9, 18, 20) -------------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        if not (ctx.session_close_min - p.entry_lead_min <= ctx.minute
                < ctx.session_close_min):             # row 7/§9: closing window only
            return []
        today = ctx.dt_et.date()
        holding = {pos.underlying for pos in ctx.open_positions}   # row 20: one per underlying
        out = []
        for sym in self.META.universe:
            if sym in holding:
                continue
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            exp, dte_days = self._next_session_expiry(ctx, sym, today)
            if exp is None:
                if ctx.journal:
                    ctx.journal({"event": "overnight_1dte_no_expiry", "symbol": sym,
                                 "day": str(today)})
                continue
            rows = ctx.hub.chain(sym, exp)
            call = self._pick_leg(ctx, rows, "call", S_ref, dte_days)
            put = self._pick_leg(ctx, rows, "put", S_ref, dte_days)
            if call is None or put is None:
                if ctx.journal:
                    ctx.journal({"event": "overnight_1dte_leg_skip", "symbol": sym,
                                 "expiry": exp, "S_ref": round(S_ref, 4),
                                 "missing": [s for s, leg in (("call", call), ("put", put))
                                             if leg is None]})
                continue
            (c_row, c_g), (p_row, p_g) = call, put
            macro = self._macro_kinds_in_window(ctx, date.fromisoformat(exp))
            legs = []
            for row, g, ot in ((c_row, c_g, "call"), (p_row, p_g, "put")):
                legs.append({"occ": row.symbol, "underlying": sym, "opt_type": ot,
                             "strike": row.strike, "expiry": exp, "side": -1, "qty": 1,
                             "nbbo": {"bid": row.bid, "ask": row.ask},
                             "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                             "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                             "theta_day": g.get("theta_day", 0.0)})
            credit_bid = c_row.bid + p_row.bid
            credit_mid = (c_row.bid + c_row.ask) / 2.0 + (p_row.bid + p_row.ask) / 2.0
            out.append(ProposedCombo(
                kind="short_strangle_overnight", underlying=sym, legs=legs,
                signal={"S_ref": round(S_ref, 4), "expiry": exp, "dte_days": dte_days,
                        "call_strike": c_row.strike, "call_delta": c_g.get("delta", 0.0),
                        "put_strike": p_row.strike, "put_delta": p_g.get("delta", 0.0),
                        "credit_bid": round(credit_bid, 4),
                        "credit_mid": round(credit_mid, 4),
                        "credit_pct_of_S": round(100.0 * credit_bid / S_ref, 3),
                        "macro_events_in_window": macro or None},
                risk_flags=(["macro_release_in_window"] if macro else [])))
        return out

    # -- manage (§4, rows 11-15): unconditional next-open buy-back ---------
    def manage(self, pos, ctx):
        """Row 11: buy back BOTH legs at the next market open - first mark at/after 09:30 ET
        on any day AFTER entry_day (ISO day strings compare chronologically). Quote-blind by
        design: a missing NBBO never delays the mandatory buy-back (§4 - the runner fills
        from its book). No profit target (13), no stop (14), no roll (15) - otherwise hold."""
        if ctx.day > pos.entry_day and ctx.minute >= self.params.exit_minute_from:
            return ExitAction(action="close", rule="next_open_buyback",
                              state={"entry_day": pos.entry_day, "exit_day": ctx.day,
                                     "exit_minute": ctx.minute})
        return None
