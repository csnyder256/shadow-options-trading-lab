"""zero_dte_morning_ic - 0DTE morning iron condor, hold to close with per-side stop.

AUTHORITY: docs/strategies/briefs/zero_dte_morning_ic.md (verified CORRECTED 2026-07-19,
composite benchmark: Option Alpha 0DTE report primary; CBOE/Schwartz, Options Trading IQ,
Theta Profits secondaries). Every constant below cites its brief row.

Doctrine (brief §3/§4 - overrides ALL platform exit doctrine for this cohort):
  * UNCONDITIONAL daily entry (row 4) at ~09:45 ET (row 3, ADAPTED composite inside the
    published 09:35-10:15 window; completion window to 09:55 is PLATFORM-POLICY tolerance),
    subject ONLY to the §8 PLATFORM-POLICY liquidity/credit gates (rows 9/19).
  * Structure (rows 2/5/7/8): TODAY-expiring (0DTE, definitional) 4-leg iron condor - 
    short put + short call at the listed strike with |delta| closest to 0.14 each side
    (row 5 SOURCE-VERBATIM "sell the 14 delta put and call"), long wings at the listed
    strike nearest 0.75% of spot beyond each short (row 8 ADAPTED dollar-grid rescale).
    All four legs must carry two-sided NBBO.
  * ONE condor per symbol per day (row 17), no re-entry after a stop (row 17 is a per-day
    count, not per-open-position) - tracked via ctx.open_positions entered today PLUS a
    per-day instance attribute (a stopped condor no longer appears in open_positions).
    Known edge: an intraday process restart after a same-day stop forgets the set; the
    10-minute entry window bounds the exposure. Documented, accepted.
  * Event days (row 16): trade anyway - "trade anyway (formal skip rule UNKNOWN)"
    [PLATFORM-POLICY]. NO print-day stand-down exists in the brief; scan() therefore never
    gates on ctx.events. It ANNOTATES instead (§7/§9): upcoming same-day events (e.g. the
    14:00 FOMC that lands after entry) go into signal.events_today and risk-flag
    holds_through_<kind>, so the grader can slice - tagged, never skipped.
  * Exit (rows 10/12): NO profit target - hold to the close (row 10 SOURCE-VERBATIM
    set-and-forget). The ONLY managed exit is the stop (row 12 SOURCE-VERBATIM, Theta
    Profits): close when the debit-to-close EITHER short spread >= 1.0 x total condor
    credit. §10 1-lot adaptation: the whole condor closes when a side's stop triggers
    (the published form closes just the breached side). Credit reference = entry mid
    credit, i.e. -net_open["optimistic"] (optimistic ledger IS the mid fill - row 20's
    mid-quote mark convention). Stop evaluated on last_nbbo mids; any missing leg NBBO
    -> hold (a stop on fictional marks is worse than a late stop).
  * Settlement: settle_at_expiry=True - the runner settles at intrinsic vs the close.
    DOCUMENTED DEVIATION from row 14 (15:55 ET forced flatten): the flatten exists to
    dodge American-style assignment/pin in a real book; the shadow's intrinsic-vs-close
    settlement is the cash-settled analogue of the published SPX hold-to-close form, so
    the lab rides 15:55->16:00 instead of flattening. Grader note, not a bug.
  * Universe (row 1): tasking pins ("SPY", "QQQ") - brief row 1 also lists IWM; the IWM
    lane is a tasking-level narrowing, not a brief change. Mega-caps stay EXCLUDED (§2).
  * CaR basis (row 18): wing width - credit = expiry max loss, which is exactly what
    payoff_analysis derives for a defined-risk credit condor -> grading_basis MAX_LOSS.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ")


@dataclass(frozen=True)
class ZeroDteIcParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    entry_minute_from: brief row 3 '09:45 ET' (ADAPTED composite) -> minute 585.
    entry_minute_to: 09:55 exclusive - PLATFORM-POLICY completion window, still inside the
    published 09:35-10:15 bracket. short_delta: row 5 SOURCE-VERBATIM 14 delta.
    wing_pct_of_spot: row 8 ADAPTED 0.75% of spot. min_credit_per_side: row 9
    PLATFORM-POLICY $0.05 floor (published gate UNKNOWN). min_oi_per_leg /
    max_spread_frac_of_mid: row 19 PLATFORM-POLICY liquidity gates. stop_credit_multiple:
    row 12 SOURCE-VERBATIM 1.0 x total credit per side."""
    entry_minute_from: int = 585          # 09:45 ET
    entry_minute_to: int = 595            # exclusive; = 09:55 ET
    short_delta: float = 0.14
    wing_pct_of_spot: float = 0.0075
    min_credit_per_side: float = 0.05
    min_oi_per_leg: int = 100
    max_spread_frac_of_mid: float = 0.15
    stop_credit_multiple: float = 1.0


class ZeroDteMorningIc(Strategy):
    META = StrategyMeta(
        strategy_id="zero_dte_morning_ic", version=1,
        name="0DTE morning iron condor, hold to close with per-side stop",
        universe=UNIVERSE, dte_range=(0, 1),
        max_concurrent=2,                             # 1 condor x 2 underlyings (row 17)
        event_policy=EventPolicy.TRADE_THROUGH,       # row 16: trade anyway, annotate only
        grading_basis=GradingBasis.MAX_LOSS,          # row 18: width - credit (payoff-derived)
        defining_mechanism="short_vol_carry",
        settle_at_expiry=True,                        # rides to close; runner settles intrinsic
        scan_interval_s=60.0, mark_interval_s=60.0,   # §9/§10: 1-min stop monitor is mandatory
        expected_fires_per_20_sessions=20.0)
    params = ZeroDteIcParams()

    def __init__(self):
        self._entered_day = ""                        # row 17 one-per-day tracker (see docstring)
        self._entered: set[str] = set()

    # -- selection helpers (rows 5/7/8) ------------------------------------
    def _pick_short(self, ctx, rows: list, S: float):
        """Row 7: the listed strike whose |delta| is closest to short_delta (row 5). Rows the
        solver cannot price are excluded from short candidacy. Returns (row, greeks) | None."""
        best = None
        for r in rows:
            mid = (r.bid + r.ask) / 2.0
            g = ctx.hub.row_greeks(opt_type=r.option_type, strike=r.strike, S=S, mid=mid,
                                   dte_days=0)
            if not g:
                continue
            dist = abs(abs(g["delta"]) - self.params.short_delta)
            if best is None or dist < best[0]:
                best = (dist, r, g)
        return None if best is None else (best[1], best[2])

    @staticmethod
    def _pick_wing(candidates: list, anchor_strike: float, target_width: float):
        """Row 8: listed strike nearest target_width beyond the short (candidates already
        two-sided and strictly beyond the anchor). Exact-tie goes to the WIDER wing
        (deterministic; no source publishes a tie-break)."""
        if not candidates:
            return None
        return min(candidates,
                   key=lambda r: (abs(abs(r.strike - anchor_strike) - target_width),
                                  -abs(r.strike - anchor_strike)))

    def _gate_reasons(self, legs_rows: list, put_credit: float, call_credit: float) -> list:
        """Rows 9/19 PLATFORM-POLICY gates on the four CHOSEN legs; any reason -> skip entry."""
        reasons = []
        for r in legs_rows:
            oi = getattr(r, "open_interest", None)
            if oi is not None and float(oi) < self.params.min_oi_per_leg:      # row 19
                reasons.append(f"oi<{self.params.min_oi_per_leg}:{r.symbol}")
            mid = (r.bid + r.ask) / 2.0
            if mid <= 0 or (r.ask - r.bid) > self.params.max_spread_frac_of_mid * mid:
                reasons.append(f"spread>{self.params.max_spread_frac_of_mid:.0%}:{r.symbol}")
        if put_credit < self.params.min_credit_per_side:                       # row 9
            reasons.append(f"put_credit<{self.params.min_credit_per_side}")
        if call_credit < self.params.min_credit_per_side:
            reasons.append(f"call_credit<{self.params.min_credit_per_side}")
        return reasons

    @staticmethod
    def _leg(row, side: int, sym: str, exp: str, g: dict) -> dict:
        return {"occ": row.symbol, "underlying": sym, "opt_type": row.option_type,
                "strike": row.strike, "expiry": exp, "side": side, "qty": 1,
                "nbbo": {"bid": row.bid, "ask": row.ask},
                "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                "theta_day": g.get("theta_day", 0.0)}

    # -- scan (rows 2-9, 16, 17, 19) ---------------------------------------
    def scan(self, ctx) -> list:
        if ctx.day != self._entered_day:              # day roll: reset the one-per-day set
            self._entered_day = ctx.day
            self._entered = set()
        if not (self.params.entry_minute_from <= ctx.minute < self.params.entry_minute_to):
            return []                                 # row 3: ~09:45 ET morning entry only
        today = ctx.dt_et.date()
        # Row 16: NO stand-down - annotate upcoming same-day events for the grader (§7/§9).
        events_today = sorted({e.kind for e in (ctx.events or [])
                               if e.ts_et.date() == today})
        for p in ctx.open_positions:                  # restart safety: today's combos block
            if getattr(p, "entry_day", "") == ctx.day:
                self._entered.add(p.underlying)
        out = []
        for sym in self.META.universe:
            if sym in self._entered:                  # row 17: one condor per symbol per day
                continue
            S = ctx.hub.ref_price(sym)
            if S <= 0:
                continue
            exp = ctx.day                             # row 2: TODAY-expiring only (0DTE)
            if exp not in ctx.hub.expirations(sym):
                if ctx.journal:
                    ctx.journal({"event": "zdteic_no_0dte_expiry", "symbol": sym,
                                 "day": ctx.day})
                continue
            rows = ctx.hub.chain(sym, exp)
            live = [r for r in rows if (r.bid or 0) > 0 and (r.ask or 0) > 0]  # two-sided only
            puts = [r for r in live if r.option_type == "put" and r.strike < S]
            calls = [r for r in live if r.option_type == "call" and r.strike > S]
            sp = self._pick_short(ctx, puts, S)
            sc = self._pick_short(ctx, calls, S)
            if sp is None or sc is None:
                if ctx.journal:
                    ctx.journal({"event": "zdteic_no_short_strike", "symbol": sym,
                                 "day": ctx.day, "S": round(S, 4)})
                continue
            (sp_row, sp_g), (sc_row, sc_g) = sp, sc
            wing = self.params.wing_pct_of_spot * S   # row 8
            lp_row = self._pick_wing([r for r in puts if r.strike < sp_row.strike],
                                     sp_row.strike, wing)
            lc_row = self._pick_wing([r for r in calls if r.strike > sc_row.strike],
                                     sc_row.strike, wing)
            if lp_row is None or lc_row is None:
                if ctx.journal:
                    ctx.journal({"event": "zdteic_no_wing", "symbol": sym, "day": ctx.day,
                                 "short_put": sp_row.strike, "short_call": sc_row.strike})
                continue
            mid = lambda r: (r.bid + r.ask) / 2.0     # noqa: E731 - row 20 mid convention
            put_credit = mid(sp_row) - mid(lp_row)
            call_credit = mid(sc_row) - mid(lc_row)
            reasons = self._gate_reasons([sp_row, lp_row, sc_row, lc_row],
                                         put_credit, call_credit)
            if reasons:                               # rows 9/19: gate-skip (retry in window OK)
                if ctx.journal:
                    ctx.journal({"event": "zdteic_gate_skip", "symbol": sym, "day": ctx.day,
                                 "reasons": reasons})
                continue
            lp_g = ctx.hub.row_greeks(opt_type="put", strike=lp_row.strike, S=S,
                                      mid=mid(lp_row), dte_days=0) or {}
            lc_g = ctx.hub.row_greeks(opt_type="call", strike=lc_row.strike, S=S,
                                      mid=mid(lc_row), dte_days=0) or {}
            width_put = sp_row.strike - lp_row.strike
            width_call = lc_row.strike - sc_row.strike
            self._entered.add(sym)                    # marked at PROPOSAL (conservative)
            out.append(ProposedCombo(
                kind="iron_condor_0dte", underlying=sym,
                legs=[self._leg(sp_row, -1, sym, exp, sp_g),
                      self._leg(lp_row, +1, sym, exp, lp_g),
                      self._leg(sc_row, -1, sym, exp, sc_g),
                      self._leg(lc_row, +1, sym, exp, lc_g)],
                signal={"S_ref": round(S, 4), "expiry": exp,
                        "strikes": {"short_put": sp_row.strike, "long_put": lp_row.strike,
                                    "short_call": sc_row.strike, "long_call": lc_row.strike},
                        "short_put_delta": sp_g.get("delta", 0.0),
                        "short_call_delta": sc_g.get("delta", 0.0),
                        "wing_width_put": round(width_put, 4),
                        "wing_width_call": round(width_call, 4),
                        "credit_mid": round(put_credit + call_credit, 4),
                        "credit_pct_of_width": round(
                            100.0 * (put_credit + call_credit) / max(width_put, width_call), 2)
                            if max(width_put, width_call) > 0 else None,
                        "events_today": events_today},
                risk_flags=[f"holds_through_{k}" for k in events_today]))
        return out

    # -- manage (rows 10/12): hold to close; per-side stop only ------------
    def manage(self, pos, ctx):
        """Row 12 stop, §10 1-lot form: close the WHOLE condor when the debit-to-close either
        short spread >= stop_credit_multiple x total entry credit. Otherwise hold - row 10 has
        no profit target; settlement (settle_at_expiry) handles the close. Any missing leg
        NBBO -> hold (never stop on fictional marks)."""
        credit = -float((pos.net_open or {}).get("optimistic") or 0.0)
        if credit <= 0:                               # degenerate (not a credit) - no reference
            return None
        mids = {}
        for ls in pos.legs:
            nb = ctx.hub.last_nbbo(ls.spec.occ)
            if nb is None:
                return None
            bid, ask = float(nb[0] or 0.0), float(nb[1] or 0.0)
            mids[ls.spec.occ] = (bid + ask) / 2.0

        def side_cost(opt_type: str):
            shorts = [ls for ls in pos.legs
                      if ls.spec.opt_type == opt_type and ls.spec.side < 0]
            longs = [ls for ls in pos.legs
                     if ls.spec.opt_type == opt_type and ls.spec.side > 0]
            if not shorts or not longs:
                return None
            return (sum(mids[ls.spec.occ] * ls.spec.qty for ls in shorts)
                    - sum(mids[ls.spec.occ] * ls.spec.qty for ls in longs))

        put_cost = side_cost("put")
        call_cost = side_cost("call")
        if put_cost is None or call_cost is None:     # malformed combo - hold, never guess
            return None
        threshold = self.params.stop_credit_multiple * credit
        breached = [name for name, cost in (("put", put_cost), ("call", call_cost))
                    if cost >= threshold]
        if breached:
            return ExitAction(
                action="close", rule="stop_side_debit_ge_credit",
                state={"credit": round(credit, 4), "put_side_cost": round(put_cost, 4),
                       "call_side_cost": round(call_cost, 4),
                       "threshold": round(threshold, 4), "breached": breached})
        return None
