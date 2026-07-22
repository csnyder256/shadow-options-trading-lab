"""strangle_45d16d_managed - tasty canonical 45DTE 16-delta short strangle, managed.

AUTHORITY: docs/strategies/briefs/strangle_45d16d_managed.md (verified CORRECTED + second
fresh-context pass CONFIRMED, 2026-07-19). Provenance: tastylive strangle / IVR / managing-
winners mechanics pages, Fabian 2016-09-23 (manage-at-50 study), Zeng 2024-06-24 (21 DTE
study), SJ Options independent SPX backtest (the canonical-formula sentence). Every constant
below cites its brief §8 row.

Doctrine (brief §3/§4 - overrides ALL platform exit doctrine for this cohort):
  * ENTRY gate: IVR >= 50 (row 7) via the registered fallback ladder (row 9). Rung 1
    (per-underlying 52-week IVR) is COLD; rung 2 = VIX 252d daily-close percentile from
    hub.vol_regime(), threshold mapped 1:1 (IVR>50 ~= VIX pctile>50, ADAPTED); rung 3 =
    regime unavailable (file missing OR pctile null) -> enter UNGATED with risk_flag
    "gate_unavailable", and the gate basis is logged in signal on every entry so trades can
    be re-gated retroactively (brief §9). Comparator is STRICT > per the primary wording
    "above 50%" (row 7); row 9's ADAPTED paraphrase writes ">= 50" - pctile == 50.0 does
    NOT enter (logged choice, pinned in tests).
  * ENTRY structure: expiration nearest 45 DTE (row 2) within [35, 50] (row 3 band; the
    published top 55 is narrowed to 50 by the platform META pin - PLATFORM-POLICY); short
    1x put and short 1x call at the strike whose ABSOLUTE solved delta is nearest 0.16 per
    side (rows 4/5, nearest-strike rule row 6), OTM two-sided-NBBO rows only; 1 lot per leg
    (row 18); ONE strangle per underlying at a time. Universe = the index-ETF fidelity lane
    only (row 1: SPY/QQQ/IWM are faithful to the published SPY/SPX evidence; the mega-cap
    extension lane is deferred - it requires separate-lane grading the brief flags loudly).
    Row 19's spread%/OI liquidity gate is NOT implemented in v1 (two-sided NBBO only).
  * EXIT first-touched (row 13), evaluated (a) -> (b) -> (c) within one mark cycle:
      (a) profit_50pct       buy back when current cost <= 50% of entry credit (row 10)
      (b) dte_21_management  close at <= 21 DTE (row 11). Quote-INDEPENDENT: fires even
                             when a leg quote is missing - brief §4: "Never hold past
                             21 DTE" is doctrine, not market data.
      (c) loss_2x_credit     close when NET LOSS >= 2x entry credit, i.e. buy-back cost
                             >= 3x credit - the HOUSE convention per the brief's row 12
                             disambiguation note. The alternative literal reading
                             (buy-back >= 2x credit) does NOT fire, but BOTH readings are
                             logged in state on every decision (the §10 telemetry that
                             resolves the published P/L-stop dispute).
    Entry credit = -pos.net_open["optimistic"] (mid-based). Current cost = sum of leg mids
    from hub.last_nbbo; any leg quote missing or dead (0x0) -> the cost-based rules HOLD
    (no exit decision on a dead quote); the calendar rule still runs.
  * No rolling (row 14: close-only v1 - the published trigger is qualitative), no earnings
    gate (row 17 - moot for the ETF lane), settle_at_expiry=False (the 21 DTE exit makes
    expiry unreachable; the runner's expiry-day backstop stays armed regardless). CaR
    basis: undefined-risk naked strangle -> reg_t_v1 proxy denominator (row 20 / §10).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM")


@dataclass(frozen=True)
class StrangleParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    dte_target: row 2 "around 45 days to expiration" (SOURCE-RANGE, default 45).
    dte_min/dte_max: row 3 band [35, 55], top narrowed to 50 by the META pin (PLATFORM-
    POLICY). target_abs_delta: rows 4/5 "Sell the 16 delta of the call and put" (SOURCE-
    VERBATIM), nearest-strike selection row 6 (PLATFORM-POLICY). ivr_gate_pctile: row 7
    IVR>50 (SOURCE-VERBATIM) carried by the row 9 VIX-252d-percentile fallback, 1:1
    threshold mapping (ADAPTED), strict >. profit_take_frac: row 10 "50% of the credit
    received" (SOURCE-VERBATIM). time_exit_dte: row 11 close at 21 DTE (SOURCE-VERBATIM).
    loss_multiple_credit: row 12 net loss >= 2x credit == buy-back >= 3x credit (SOURCE-
    RANGE, ambiguous - house convention; alt reading logged, never fired)."""
    dte_target: int = 45
    dte_min: int = 35
    dte_max: int = 50
    target_abs_delta: float = 0.16
    ivr_gate_pctile: float = 50.0
    profit_take_frac: float = 0.50
    time_exit_dte: int = 21
    loss_multiple_credit: float = 2.0


class Strangle45D16DManaged(Strategy):
    META = StrategyMeta(
        strategy_id="strangle_45d16d_managed", version=1,
        name="tasty 45DTE 16-delta short strangle, managed 50% / 21 DTE / 2x credit",
        universe=UNIVERSE, dte_range=(35, 50),
        max_concurrent=3,                              # one strangle per underlying (row 18)
        event_policy=EventPolicy.TRADE_THROUGH,        # no published event gate (§3)
        grading_basis=GradingBasis.CAR,                # undefined risk -> reg_t_v1 (row 20)
        defining_mechanism="short_vol_carry",
        settle_at_expiry=False,                        # never holds past 21 DTE (row 11)
        scan_interval_s=300.0, mark_interval_s=300.0,  # §9: modest cadence suffices
        expected_fires_per_20_sessions=3.0)            # §10: ~3/month, heavily clustered
    params = StrangleParams()

    # -- entry gate (rows 7/9: IVR>=50 via the VIX-percentile fallback ladder) ----------
    def _gate(self, ctx) -> tuple[bool, dict]:
        """(enter_allowed, gate_info). Rung 2: VIX 252d percentile, STRICT > threshold.
        Rung 3: regime file missing or pctile null -> allowed + flagged upstream (§9)."""
        vr = ctx.hub.vol_regime() or {}
        pct = vr.get("vix_pctile_252d")
        if pct is None:
            return True, {"basis": "unavailable", "vix_pctile_252d": None, "ivr": None,
                          "threshold": self.params.ivr_gate_pctile}
        pct = float(pct)
        info = {"basis": "vix_pctile_252d", "vix_pctile_252d": pct, "ivr": None,
                "threshold": self.params.ivr_gate_pctile}
        return pct > self.params.ivr_gate_pctile, info

    # -- expiry selection (rows 2/3) -----------------------------------------------------
    def _expiry_near_target(self, ctx, sym: str, today: date) -> tuple | None:
        """(expiration, dte) nearest dte_target within [dte_min, dte_max]; None when no
        listing qualifies. Tie-break: first-listed wins (row 16's monthly preference needs
        cycle metadata the hub does not carry - PLATFORM-POLICY deterministic stand-in)."""
        best, best_dte, best_diff = None, None, None
        for e in ctx.hub.expirations(sym):
            try:
                y, m, d = map(int, e.split("-"))
                dte = (date(y, m, d) - today).days
            except ValueError:
                continue
            if not (self.params.dte_min <= dte <= self.params.dte_max):
                continue
            diff = abs(dte - self.params.dte_target)
            if best_diff is None or diff < best_diff:
                best, best_dte, best_diff = e, dte, diff
        return None if best is None else (best, best_dte)

    # -- strike selection (rows 4/5/6) ---------------------------------------------------
    def _pick_short_leg(self, ctx, rows: list, *, opt_type: str, S: float,
                        dte: int) -> tuple | None:
        """OTM row with a two-sided NBBO whose ABSOLUTE solved delta is nearest 0.16.
        Returns (row, mid, greeks) or None. Put deltas are negative - selection uses
        abs(delta) (rows 4/5). Rows the solver cannot price are skipped."""
        target = self.params.target_abs_delta
        best = None
        for r in rows:
            if r.option_type != opt_type:
                continue
            if (r.bid or 0) <= 0 or (r.ask or 0) <= 0:
                continue                                   # two-sided NBBO only
            if (opt_type == "put" and r.strike >= S) or \
                    (opt_type == "call" and r.strike <= S):
                continue                                   # 16-delta legs are OTM by definition
            mid = (r.bid + r.ask) / 2.0
            g = ctx.hub.row_greeks(opt_type=opt_type, strike=r.strike, S=S, mid=mid,
                                   dte_days=dte)
            if not g:
                continue
            diff = abs(abs(g["delta"]) - target)
            if best is None or diff < best[0]:
                best = (diff, r, mid, g)
        return None if best is None else (best[1], best[2], best[3])

    @staticmethod
    def _leg_dict(sym: str, exp: str, opt_type: str, row, g: dict) -> dict:
        return {"occ": row.symbol, "underlying": sym, "opt_type": opt_type,
                "strike": row.strike, "expiry": exp, "side": -1, "qty": 1,
                "nbbo": {"bid": row.bid, "ask": row.ask},
                "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                "theta_day": g.get("theta_day", 0.0)}

    # -- scan (rows 1-9, 18) -------------------------------------------------------------
    def scan(self, ctx) -> list:
        today = ctx.dt_et.date()
        allowed, gate = self._gate(ctx)
        if not allowed:
            if ctx.journal:
                ctx.journal({"event": "strangle_gate_blocked", "day": str(today), **gate})
            return []
        risk_flags = ["gate_unavailable"] if gate["basis"] == "unavailable" else []
        holding = {p.underlying for p in ctx.open_positions}   # one strangle per underlying
        out = []
        for sym in self.META.universe:
            if sym in holding:
                continue
            S = ctx.hub.ref_price(sym)
            if S <= 0:
                continue
            near = self._expiry_near_target(ctx, sym, today)
            if near is None:
                if ctx.journal:
                    ctx.journal({"event": "strangle_no_expiry", "symbol": sym,
                                 "day": str(today)})
                continue
            exp, dte = near
            rows = ctx.hub.chain(sym, exp)
            put = self._pick_short_leg(ctx, rows, opt_type="put", S=S, dte=dte)
            call = self._pick_short_leg(ctx, rows, opt_type="call", S=S, dte=dte)
            if put is None or call is None:
                if ctx.journal:
                    ctx.journal({"event": "strangle_no_leg", "symbol": sym, "expiry": exp,
                                 "missing": [name for name, leg in
                                             (("put", put), ("call", call)) if leg is None]})
                continue
            (p_row, p_mid, p_g), (c_row, c_mid, c_g) = put, call
            out.append(ProposedCombo(
                kind="short_strangle", underlying=sym,
                legs=[self._leg_dict(sym, exp, "put", p_row, p_g),
                      self._leg_dict(sym, exp, "call", c_row, c_g)],
                signal={"S_ref": round(S, 4), "expiry": exp, "dte_days": dte,
                        "put_strike": p_row.strike, "call_strike": c_row.strike,
                        "put_abs_delta": round(abs(p_g["delta"]), 4),
                        "call_delta": round(c_g["delta"], 4),
                        "credit_mid": round(p_mid + c_mid, 4),
                        "credit_bid": round(p_row.bid + c_row.bid, 4),
                        "gate": dict(gate)},
                risk_flags=list(risk_flags)))
        return out

    # -- manage (rows 10-13): 50% profit / 21 DTE / 2x-credit loss, first-touched --------
    @staticmethod
    def _current_cost(pos, ctx) -> tuple:
        """(buy-back cost, {occ: mid}) from the hub quote book; cost is None when any leg
        has no quote or a dead 0x0 book (no cost-based exit decision on a dead quote)."""
        total, mids = 0.0, {}
        for ls in pos.legs:
            q = ctx.hub.last_nbbo(ls.spec.occ)
            bid = max(0.0, float(q[0])) if q else 0.0
            ask = max(0.0, float(q[1])) if q else 0.0
            if q is None or (bid <= 0.0 and ask <= 0.0):
                mids[ls.spec.occ] = None
                return None, mids
            mid = (bid + ask) / 2.0
            mids[ls.spec.occ] = round(mid, 4)
            total += mid * ls.spec.qty
        return total, mids

    def manage(self, pos, ctx) -> ExitAction | None:
        p = self.params
        dte = (pos.nearest_expiry - ctx.dt_et.date()).days
        credit = -float(pos.net_open.get("optimistic") or 0.0)   # mid-based entry credit
        cost, leg_mids = self._current_cost(pos, ctx)

        state = {"credit": round(credit, 4), "cost": None if cost is None else round(cost, 4),
                 "dte": dte, "leg_mids": leg_mids}
        priced = credit > 0 and cost is not None
        if priced:
            state.update({
                "cost_x_credit": round(cost / credit, 4),
                "net_loss_x_credit": round((cost - credit) / credit, 4),
                # row 12 ambiguity flag: BOTH readings logged on every decision (§10)
                "loss_readings": {
                    "house_netloss_ge_2x_credit":
                        bool(cost >= (1.0 + p.loss_multiple_credit) * credit),
                    "alt_buyback_ge_2x_credit":
                        bool(cost >= p.loss_multiple_credit * credit)}})
            if cost <= p.profit_take_frac * credit:                       # (a) row 10
                return ExitAction(action="close", rule="profit_50pct", state=state)
        if dte <= p.time_exit_dte:                                        # (b) row 11
            return ExitAction(action="close", rule="dte_21_management", state=state)
        if priced and cost >= (1.0 + p.loss_multiple_credit) * credit:    # (c) row 12
            return ExitAction(action="close", rule="loss_2x_credit", state=state)
        return None
