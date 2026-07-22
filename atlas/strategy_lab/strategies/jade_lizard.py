"""jade_lizard - tasty jade lizard: short put + short call spread, 45DTE, credit > width.

AUTHORITY: docs/strategies/briefs/jade_lizard.md (verified CORRECTED 2026-07-19, zero
invented constants). Provenance: tastylive jade-lizard learn page (primary - structure and
the credit>width no-upside-risk identity), tastylive strangle page (45DTE / 50%-target
doctrine transfer, flagged in rows 3/14), TradeStation 2026-05-13 + SlashTraders
(delta/width SOURCE-RANGEs), FinancialTechWiz 2024-01-29 (50%-target confirmation).
Every constant below cites its brief §8 row.

Doctrine (brief §3/§4 - overrides ALL platform exit doctrine for this cohort):
  * Structure (row 1): SELL 1 OTM put + SELL 1 OTM call + BUY 1 higher-strike call, same
    expiration, 1x1x1 - "combines a short put with a short call spread".
  * THE DEFINING CONSTRAINT (row 8, source "preferred" elevated to HARD gate): total net
    credit MUST exceed the call-spread width - "that removes upside risk in the strategy".
    A candidate failing at current quotes is journaled (jade_no_credit_constraint) and
    SKIPPED; a lizard with upside risk is never entered. Credit is evaluated at leg mids - 
    the optimistic-ledger fill convention, the same basis manage() reads back as
    -net_open["optimistic"]. The worst-ledger natural credit is stamped in the signal and
    flagged (worst_credit_below_width) when it alone would not clear the width.
  * Entry (rows 3-7, 9-11): expiration nearest 45 DTE (row 3, strangle-doctrine transfer)
    within [35, 50] (row 4; upper edge narrowed 55->50 to match META.dte_range chain
    requests); short put |delta| in [0.20, 0.30] targeting 0.30 (row 5); short call
    |delta| in [0.15, 0.20] targeting 0.20 (row 6); long call at the NARROWEST listed
    width >= 0.5% of spot that keeps credit > width (row 7 - the flat $1-$5 band is
    degenerate on a $600+ underlying, §7). All legs two-sided NBBO (row 20 clause); one
    lizard per underlying (row 18 unit convention, META.max_concurrent = universe size).
    IV gate (rows 9/10): published "high IVR" (numeric threshold UNKNOWN) implemented via
    the registered fallback ladder (scripts/refresh_vix_history.py): rung 1 per-symbol IVR
    archive is cold -> rung 2 vol_regime.json VIX 252d percentile >= 50 (PLATFORM-POLICY
    midpoint of "high") -> rung 3 file missing/stale = UNGATED + jade_gate_unavailable
    journal. No trend trigger (row 11: qualitative only), no entry clock (row 12).
  * Exit (rows 14-17): buy back ALL legs when the combo closes for <= 50% of the opening
    net credit (row 14); otherwise close at 21 DTE (row 15 - the mechanic is documented
    doctrine, the study verdict is UNKNOWN). NO stop-loss (row 16: the absence is the
    finding) and NO rolls (row 17: rolls chain positions and break unit grading).
  * Universe: SPY/QQQ/IWM - the mission-pinned ETF tier of the brief row-2 mapping. Row
    13's single-name earnings exclusion is therefore moot; it MUST be implemented before
    any single name joins this universe.
  * Grading (row 19 + META): MAX_LOSS basis - with credit > width the expiry payoff is
    bounded below at the put strike and has NO upside branch; model.payoff_analysis
    derives max_loss = put_strike*100 - credit_usd with unbounded_up False.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM")


@dataclass(frozen=True)
class JadeLizardParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    dte_target: row 3 (45 DTE, strangle-doctrine transfer). dte_min/dte_max: row 4 35-55
    selection band, upper edge narrowed to 50 to match META.dte_range (PLATFORM-POLICY).
    put_delta_*: row 5 range 0.20-0.30, default/target 0.30. call_delta_*: row 6 range
    0.15-0.20, default/target 0.20. min_width_pct_of_spot: row 7 (narrowest width >= 0.5%
    of spot). iv_gate_pctile: row 10 VIX 252d (1y) percentile >= 50 IVR proxy
    (PLATFORM-POLICY; row 9 published value UNKNOWN). regime_max_age_days: staleness bound
    on vol_regime.json asof (PLATFORM-POLICY, mirrors hub.vol_regime default).
    profit_take_frac: row 14 (50% of opening credit). manage_dte: row 15 (21 DTE)."""
    dte_target: int = 45
    dte_min: int = 35
    dte_max: int = 50
    put_delta_target: float = 0.30
    put_delta_min: float = 0.20
    put_delta_max: float = 0.30
    call_delta_target: float = 0.20
    call_delta_min: float = 0.15
    call_delta_max: float = 0.20
    min_width_pct_of_spot: float = 0.5
    iv_gate_pctile: float = 50.0
    regime_max_age_days: int = 5
    profit_take_frac: float = 0.50
    manage_dte: int = 21


class JadeLizard(Strategy):
    META = StrategyMeta(
        strategy_id="jade_lizard", version=1,
        name="Jade lizard - short put + short call spread, credit > width (no upside risk)",
        universe=UNIVERSE, dte_range=(35, 50),
        max_concurrent=3,                             # one lizard per underlying (row 18)
        event_policy=EventPolicy.TRADE_THROUGH,       # no published macro-event gate (§9)
        grading_basis=GradingBasis.MAX_LOSS,          # row 19: bounded at the put strike
        defining_mechanism="short_vol_carry",
        settle_at_expiry=False,                       # row 15: never inside 21 DTE
        scan_interval_s=300.0, mark_interval_s=300.0,
        expected_fires_per_20_sessions=3.0)           # §10: ~2-6/month, vol-clustered
    params = JadeLizardParams()

    # -- IV gate (rows 9/10): the registered vol_regime fallback ladder ----
    def _iv_gate(self, ctx) -> tuple:
        """(blocked, gate_ctx). Rung 2: VIX 252d percentile from vol_regime.json; rung 3:
        file missing/incomplete/stale -> UNGATED + jade_gate_unavailable journal."""
        p = self.params
        regime = ctx.hub.vol_regime() or {}
        pct = regime.get("vix_pctile_252d")
        reason = "missing" if pct is None else ""
        asof = regime.get("asof")
        if pct is not None and asof:
            try:
                age = (ctx.dt_et.date() - date.fromisoformat(str(asof))).days
                if age > p.regime_max_age_days:
                    reason = "stale"
            except ValueError:
                reason = "unparseable_asof"
        if reason:
            if ctx.journal:
                ctx.journal({"event": "jade_gate_unavailable", "reason": reason,
                             "asof": asof, "day": ctx.day})
            return False, {"vix_pctile_252d": None, "gate": "unavailable_ungated"}
        if float(pct) < p.iv_gate_pctile:
            if ctx.journal:
                ctx.journal({"event": "jade_iv_gate", "vix_pctile_252d": float(pct),
                             "need": p.iv_gate_pctile, "day": ctx.day})
            return True, {"vix_pctile_252d": float(pct), "gate": "blocked"}
        return False, {"vix_pctile_252d": float(pct), "gate": "pass"}

    # -- leg selection helpers ---------------------------------------------
    def _pick_expiry(self, ctx, sym: str, today: date) -> tuple:
        """Listed expiration nearest dte_target within [dte_min, dte_max] (rows 3/4).
        (None, None) = no listing in the window."""
        p = self.params
        best, best_dte, best_gap = None, None, None
        for e in ctx.hub.expirations(sym):
            try:
                y, m, d = map(int, e.split("-"))
                dte = (date(y, m, d) - today).days
            except ValueError:
                continue
            if not (p.dte_min <= dte <= p.dte_max):
                continue
            gap = abs(dte - p.dte_target)
            if best_gap is None or gap < best_gap:
                best, best_dte, best_gap = e, dte, gap
        return best, best_dte

    @staticmethod
    def _pick_short_leg(ctx, rows, *, opt_type: str, S: float, dte: int,
                        d_lo: float, d_hi: float, d_target: float):
        """OTM leg whose self-computed |delta| lies in [d_lo, d_hi], closest to d_target
        (rows 5/6). `rows` are already two-sided. None = band unpopulated."""
        best = None
        for r in rows:
            if r.option_type != opt_type:
                continue
            if (r.strike >= S) if opt_type == "put" else (r.strike <= S):
                continue                               # OTM only (row 1 structure)
            mid = (r.bid + r.ask) / 2.0
            g = ctx.hub.row_greeks(opt_type=opt_type, strike=r.strike, S=S, mid=mid,
                                   dte_days=dte)
            if not g:
                continue
            d = abs(g["delta"])
            if not (d_lo <= d <= d_hi):
                continue
            key = abs(d - d_target)
            if best is None or key < best[0]:
                best = (key, r, mid, g)
        return None if best is None else best[1:]

    # -- scan (rows 1, 3-11, 18, 20) ---------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        today = ctx.dt_et.date()
        blocked, gate_ctx = self._iv_gate(ctx)
        if blocked:
            return []
        held = {pos.underlying for pos in ctx.open_positions}   # one per underlying
        out = []
        for sym in self.META.universe:
            if sym in held:
                continue
            S = ctx.hub.ref_price(sym)
            if S <= 0:
                continue
            exp, dte = self._pick_expiry(ctx, sym, today)
            if exp is None:
                if ctx.journal:
                    ctx.journal({"event": "jade_no_expiry", "symbol": sym, "day": ctx.day})
                continue
            rows = [r for r in ctx.hub.chain(sym, exp)
                    if (r.bid or 0) > 0 and (r.ask or 0) > 0]    # two-sided NBBO, all legs
            put = self._pick_short_leg(ctx, rows, opt_type="put", S=S, dte=dte,
                                       d_lo=p.put_delta_min, d_hi=p.put_delta_max,
                                       d_target=p.put_delta_target)
            if put is None:
                if ctx.journal:
                    ctx.journal({"event": "jade_no_put_leg", "symbol": sym, "expiry": exp})
                continue
            call = self._pick_short_leg(ctx, rows, opt_type="call", S=S, dte=dte,
                                        d_lo=p.call_delta_min, d_hi=p.call_delta_max,
                                        d_target=p.call_delta_target)
            if call is None:
                if ctx.journal:
                    ctx.journal({"event": "jade_no_call_leg", "symbol": sym, "expiry": exp})
                continue
            put_row, put_mid, put_g = put
            call_row, call_mid, call_g = call
            short_credit = put_mid + call_mid

            # Long call: narrowest listed width >= 0.5% of spot that keeps credit > width
            # (row 7). Ascending walk - credit-width shrinks as width grows, so the first
            # pass is also the best one.
            min_w = p.min_width_pct_of_spot / 100.0 * S
            cands = sorted((r for r in rows if r.option_type == "call"
                            and r.strike - call_row.strike >= min_w),
                           key=lambda r: r.strike)
            if not cands:
                if ctx.journal:
                    ctx.journal({"event": "jade_no_long_call", "symbol": sym,
                                 "expiry": exp, "short_call": call_row.strike})
                continue
            chosen, best_gap = None, None
            for r in cands:
                width = r.strike - call_row.strike
                mid = (r.bid + r.ask) / 2.0
                credit = short_credit - mid
                gap = credit - width
                best_gap = gap if best_gap is None else max(best_gap, gap)
                if credit > width:                    # row 8: THE defining hard gate
                    chosen = (r, mid, width, credit)
                    break
            if chosen is None:
                if ctx.journal:
                    ctx.journal({"event": "jade_no_credit_constraint", "symbol": sym,
                                 "expiry": exp, "short_put": put_row.strike,
                                 "short_call": call_row.strike,
                                 "best_credit_minus_width": round(best_gap, 4)})
                continue                              # never enter a lizard with upside risk
            long_row, long_mid, width, credit = chosen
            long_g = ctx.hub.row_greeks(opt_type="call", strike=long_row.strike, S=S,
                                        mid=long_mid, dte_days=dte) or {}
            credit_worst = put_row.bid + call_row.bid - long_row.ask   # natural fills
            risk_flags = []
            if credit_worst <= width:
                risk_flags.append("worst_credit_below_width")

            def leg(row, opt_type, side, g):
                return {"occ": row.symbol, "underlying": sym, "opt_type": opt_type,
                        "strike": row.strike, "expiry": exp, "side": side, "qty": 1,
                        "nbbo": {"bid": row.bid, "ask": row.ask},
                        "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                        "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                        "theta_day": g.get("theta_day", 0.0)}

            out.append(ProposedCombo(
                kind="jade_lizard", underlying=sym,
                legs=[leg(put_row, "put", -1, put_g),
                      leg(call_row, "call", -1, call_g),
                      leg(long_row, "call", +1, long_g)],
                signal={"S_ref": round(S, 4), "expiry": exp, "dte_days": dte,
                        "put_strike": put_row.strike, "call_short_strike": call_row.strike,
                        "call_long_strike": long_row.strike, "width": round(width, 4),
                        "width_pct_of_spot": round(100.0 * width / S, 3),
                        "credit_mid": round(credit, 4),
                        "credit_worst": round(credit_worst, 4),
                        "credit_minus_width": round(credit - width, 4),
                        "put_delta": put_g.get("delta"), "call_delta": call_g.get("delta"),
                        "max_loss_preview_usd": round(put_row.strike * 100.0
                                                      - credit * 100.0, 2),
                        "iv_gate": gate_ctx},
                risk_flags=risk_flags))
        return out

    # -- manage (rows 14-17): 50%-of-credit buyback, else 21 DTE; no stop, no rolls ----
    @staticmethod
    def _buyback_cost_mid(pos, ctx):
        """Cost (per share, positive = pay) to close all legs at last_nbbo mids.
        None when any leg lacks a usable two-sided book -> caller holds."""
        net = 0.0
        for ls in pos.legs:
            rec = ctx.hub.last_nbbo(ls.spec.occ)
            if rec is None:
                return None
            bid, ask = float(rec[0] or 0.0), float(rec[1] or 0.0)
            if bid <= 0 and ask <= 0:
                return None
            net += ls.spec.side * ls.spec.qty * ((bid + ask) / 2.0)
        return -net

    def manage(self, pos, ctx):
        p = self.params
        dte = (pos.nearest_expiry - ctx.dt_et.date()).days
        entry_credit = -float(pos.net_open.get("optimistic") or 0.0)
        cost = self._buyback_cost_mid(pos, ctx)
        if (entry_credit > 0 and cost is not None
                and cost <= p.profit_take_frac * entry_credit):     # row 14: <= 50%
            return ExitAction("close", "profit_50pct",
                              state={"entry_credit": round(entry_credit, 4),
                                     "buyback_cost": round(cost, 4),
                                     "frac_of_credit": round(cost / entry_credit, 4),
                                     "dte": dte})
        if dte <= p.manage_dte:                                     # row 15: 21 DTE
            return ExitAction("close", "time_21dte",
                              state={"entry_credit": round(entry_credit, 4),
                                     "buyback_cost": (None if cost is None
                                                      else round(cost, 4)),
                                     "dte": dte})
        return None                                                 # rows 16/17: no stop, no roll
