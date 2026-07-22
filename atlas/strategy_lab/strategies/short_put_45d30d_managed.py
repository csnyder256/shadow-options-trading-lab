"""short_put_45d30d_managed - tastylive-style 45-DTE ~30-delta short put, managed 50% / 21 DTE.

AUTHORITY: docs/strategies/briefs/short_put_45d30d_managed.md (verified CORRECTED 2026-07-19,
two adversarial passes, zero invented constants). Provenance: tastylive Market Measures
2015-09-01 ("Short Puts | Managing Winners & Losers") + 2016-07-14 (delta grid), Skinny on
Options 2020-07-27 (45-DTE-in / 21-DTE-out); replications spintwig 2019 (the exact 30-delta
managed variant) and projectoption 2017. Every constant below cites its brief §8 row.

Doctrine (brief §3/§4 - §4 OVERRIDES all platform exit machinery for this cohort, §10):
  * Entry: FIRST TRADING DAY of each month, per underlying (row 9, SOURCE-VERBATIM),
    unconditionally - no market-condition signal (row 11), no IV gate (row 12: OFF,
    log-only VIX percentile), no credit floor (row 13). Sell 1 naked put (rows 6/18) at
    the STANDARD MONTHLY expiration (row 5) closest to 45 DTE inside the 30-60 band
    (rows 3/4; deterministic tie-break: shorter DTE), strike whose self-computed delta is
    closest to 30 within +/-3.5 delta (rows 7/8 - no strike inside the tolerance = no
    entry that month). Two-sided NBBO required (row 20 platform liquidity gate).
  * Earnings gate (row 19, PLATFORM-POLICY - ours, single-name tier): skip the month's
    entry when a confirmed earnings date falls inside [entry day, planned 21-DTE exit
    day], both ends inclusive (conservative containment of the §7 gap-through-strike
    failure mode the SPY studies never faced). Earnings after the planned exit do not
    gate - exposure ends at 21 DTE, not at expiry. ETFs carry no earnings entries.
    Single names are additionally tagged `single_name_tier` so the grader lanes the
    extension tier separately from the ETF tier (§2 LOUD adaptation note).
  * Exit (manage): buy back at 50% of max profit - current NBBO mid <= (1 - 0.50) x
    entry credit (row 14) - OR close at 21 DTE, (expiry - today).days <= 21 (row 15),
    whichever occurs first. NO stop-loss (row 16): a multi-credit loss ridden to the
    21-DTE exit is CORRECT doctrine, never cut early. NO rolls (row 17): close; the next
    monthly cadence re-establishes. Missing/offer-less NBBO on a mark = HOLD (never guess
    a repurchase price); the runner's expiry-day backstop (settle_at_expiry=False) is the
    terminal safety net if quotes never return.
  * Trigger basis (PLATFORM-POLICY, mission-fixed): entry credit = -net_open["optimistic"]
    (mid fill at open) vs current NBBO mid - mid-to-mid, matching the published rule
    stated on premium collected ("Take profit when you collect 50% of the premium"),
    not on any fill-pessimism ledger. One-sided quote with a live offer counts (a dead
    put at bid 0 CAN be repurchased at the offer); no offer = no evaluation.
  * Grading: MAX_LOSS - payoff_analysis derives the naked short put's true bounded max
    loss (strike notional - credit at S=0). Platform law fixed by the mission architect;
    the brief's §10 Reg-T CaR proxy is declined as the denominator (the cash-secured
    basis IS the conservative alternative the brief itself records).

Sizing: always 1 contract per entry (row 18), account-blind, platform convention (§5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from atlas.options.session_calendar import is_trading_day

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")
ETF_TIER = ("SPY", "QQQ", "IWM")       # faithful tier; the rest is the §2 extension tier


@dataclass(frozen=True)
class ShortPut45Params:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    dte_target: row 3 SOURCE-VERBATIM "closest to 45 days to expiration (DTE)".
    dte_band_min/dte_band_max: row 4 SOURCE-RANGE "trades between 30-60 days to
    expiration" (projectoption), choose the expiry closest to 45.
    delta_target: row 7 SOURCE-RANGE - house default "Sell options with a 30 delta."
    (financialtechwiz) inside the primary 15-50 grid; spintwig's exact replication
    variant; NOT itself a primary-study constant.
    delta_tolerance: row 8 SOURCE-VERBATIM "30 delta +/- 3.5 delta, closest to 30"
    (spintwig methodology) - 3.5 delta = 0.035.
    profit_target_frac: row 14 SOURCE-VERBATIM "exiting at 50% of max profit".
    time_exit_dte: row 15 SOURCE-VERBATIM "we exit trades at 21 DTE"."""
    dte_target: int = 45
    dte_band_min: int = 30
    dte_band_max: int = 60
    delta_target: float = 0.30
    delta_tolerance: float = 0.035
    profit_target_frac: float = 0.50
    time_exit_dte: int = 21


class ShortPut45D30DManaged(Strategy):
    META = StrategyMeta(
        strategy_id="short_put_45d30d_managed", version=1,
        name="Tastylive-style 45-DTE 30-delta short put, managed 50% / 21 DTE",
        universe=UNIVERSE, dte_range=(35, 50),
        max_concurrent=9,                              # one open put per underlying (row 9)
        event_policy=EventPolicy.TRADE_THROUGH,        # row 11: unconditional entry
        grading_basis=GradingBasis.MAX_LOSS,           # naked put bounded loss (platform law)
        defining_mechanism="short_vol_carry",
        settle_at_expiry=False,                        # MANAGED: rows 14/15 exits, never expiry
        scan_interval_s=300.0, mark_interval_s=300.0,  # intraday mid polling for the 50% touch (§9)
        expected_fires_per_20_sessions=9.0)            # ~9 per monthly cycle (§10)
    params = ShortPut45Params()

    # -- calendar math (rows 5/9) ------------------------------------------
    @staticmethod
    def first_trading_day_of_month(d: date) -> date:
        """Row 9: 'On the first trading day of every month'. Pure calendar + is_trading_day."""
        cur = d.replace(day=1)
        for _ in range(10):
            if is_trading_day(cur):
                return cur
            cur += timedelta(days=1)
        return cur

    @staticmethod
    def standard_monthly_expiry(year: int, month: int) -> date:
        """Row 5: standard monthly expiration = third Friday of the month, stepped back to
        the preceding trading day when that Friday is an exchange holiday."""
        d = date(year, month, 15)
        d += timedelta(days=(4 - d.weekday()) % 7)     # third Friday lands on the 15th-21st
        for _ in range(5):
            if is_trading_day(d):
                return d
            d -= timedelta(days=1)
        return d

    def _monthly_expiry_near_target(self, ctx, sym: str) -> str | None:
        """Rows 3/4/5: listed STANDARD MONTHLY expiry inside [band_min, band_max] DTE with
        DTE closest to dte_target; ties broken toward the shorter DTE (deterministic,
        no published tie-break). None = no qualifying listing."""
        today = ctx.dt_et.date()
        best, best_key = None, None
        for e in ctx.hub.expirations(sym):
            try:
                ed = date.fromisoformat(str(e))
            except ValueError:
                continue
            dte = (ed - today).days
            if not (self.params.dte_band_min <= dte <= self.params.dte_band_max):
                continue
            if ed != self.standard_monthly_expiry(ed.year, ed.month):
                continue                               # weeklies/quarterlies excluded (row 5)
            key = (abs(dte - self.params.dte_target), dte)
            if best_key is None or key < best_key:
                best, best_key = str(e), key
        return best

    # -- scan (rows 3, 6-13, 19-20) ----------------------------------------
    def scan(self, ctx) -> list:
        today = ctx.dt_et.date()
        if today != self.first_trading_day_of_month(today):
            return []                                  # row 9: monthly cadence only
        holding = {p.underlying for p in ctx.open_positions}   # one per underlying at a time
        vr = ctx.hub.vol_regime() or {}                # row 12: observe-only, never a gate
        out = []
        for sym in self.META.universe:
            if sym in holding:
                continue
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            exp = self._monthly_expiry_near_target(ctx, sym)
            if exp is None:
                if ctx.journal:
                    ctx.journal({"event": "sp45_no_expiry", "symbol": sym, "day": str(today)})
                continue
            exp_d = date.fromisoformat(exp)
            dte = (exp_d - today).days
            planned_exit = (exp_d - timedelta(days=self.params.time_exit_dte)).isoformat()
            earn = ctx.earnings.get(sym) or {}
            earn_date = str(earn.get("date") or "")
            if earn_date and today.isoformat() <= earn_date <= planned_exit:
                if ctx.journal:                        # row 19: skip the month, don't enter
                    ctx.journal({"event": "sp45_earnings_gate_skip", "symbol": sym,
                                 "earnings_date": earn_date, "planned_exit": planned_exit,
                                 "expiry": exp})
                continue
            rows = ctx.hub.chain(sym, exp)             # [] when degraded -> no entry today
            puts = [r for r in rows if r.option_type == "put" and r.strike < S_ref
                    and (r.bid or 0) > 0 and (r.ask or 0) > 0]      # row 20: two-sided NBBO
            if not puts:
                if ctx.journal:
                    ctx.journal({"event": "sp45_no_strike", "symbol": sym, "expiry": exp,
                                 "S_ref": round(S_ref, 4)})
                continue
            best = None                                # (dist, strike, row, mid, greeks)
            for r in puts:
                mid = (r.bid + r.ask) / 2.0
                g = ctx.hub.row_greeks(opt_type="put", strike=r.strike, S=S_ref, mid=mid,
                                       dte_days=dte)
                if not g:
                    continue
                dist = abs(abs(g["delta"]) - self.params.delta_target)
                if dist > self.params.delta_tolerance:
                    continue                           # row 8: outside +/-3.5 delta
                key = (dist, r.strike)                 # deterministic tie-break: lower strike
                if best is None or key < best[:2]:
                    best = (dist, r.strike, r, mid, g)
            if best is None:
                if ctx.journal:                        # row 8: no fit in tolerance = no entry
                    ctx.journal({"event": "sp45_no_delta_fit", "symbol": sym, "expiry": exp,
                                 "S_ref": round(S_ref, 4), "n_puts": len(puts)})
                continue
            _, _, row, mid, g = best
            risk_flags = [] if sym in ETF_TIER else ["single_name_tier"]   # §2 lane split
            out.append(ProposedCombo(
                kind="short_put_45d", underlying=sym,
                legs=[{"occ": row.symbol, "underlying": sym, "opt_type": "put",
                       "strike": row.strike, "expiry": exp, "side": -1, "qty": 1,
                       "nbbo": {"bid": row.bid, "ask": row.ask},
                       "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                       "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                       "theta_day": g.get("theta_day", 0.0)}],
                signal={"S_ref": round(S_ref, 4), "strike": row.strike, "expiry": exp,
                        "dte_days": dte, "delta": g.get("delta", 0.0),
                        "credit_bid": row.bid, "credit_mid": round(mid, 4),
                        "credit_pct_of_S": round(100.0 * row.bid / S_ref, 3),
                        "planned_exit_21dte": planned_exit,
                        "vix_close": vr.get("vix_close"),              # row 12: log-only
                        "vix_pctile_252d": vr.get("vix_pctile_252d"),
                        "earnings": earn or None},
                risk_flags=risk_flags))
        return out

    # -- manage (rows 14-17): 50% profit or 21 DTE, whichever first --------
    def manage(self, pos, ctx):
        leg = pos.legs[0].spec                         # single short put (row 6)
        today = ctx.dt_et.date()
        dte = (leg.expiry - today).days
        nbbo = ctx.hub.last_nbbo(leg.occ)
        if nbbo is None:
            return None                                # no quote -> HOLD, never guess
        bid, ask, age_s = nbbo
        if ask <= 0:
            return None                                # no live offer -> repurchase unpriceable
        cost = (max(0.0, bid) + ask) / 2.0             # current buyback mid (mission-fixed basis)
        credit = -float(pos.net_open.get("optimistic") or 0.0)      # mid credit at open
        threshold = (1.0 - self.params.profit_target_frac) * credit
        state = {"dte": dte, "credit_open_mid": round(credit, 4),
                 "cost_now_mid": round(cost, 4), "threshold_mid": round(threshold, 4),
                 "quote_age_s": age_s}
        if credit > 0 and cost <= threshold:           # row 14: 50% of max profit captured
            state["capture_frac"] = round((credit - cost) / credit, 4)
            return ExitAction(action="close", rule="profit_50pct", state=state)
        if dte <= self.params.time_exit_dte:           # row 15: 21-DTE management exit
            state["time_exit_dte"] = self.params.time_exit_dte
            return ExitAction(action="close", rule="dte_21_management", state=state)
        return None                                    # row 16: NO stop-loss between the rails
