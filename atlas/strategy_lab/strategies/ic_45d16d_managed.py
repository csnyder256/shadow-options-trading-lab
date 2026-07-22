"""ic_45d16d_managed - tasty 45-DTE ~16-delta iron condor, managed at 50% credit / 21 DTE.

AUTHORITY: docs/strategies/briefs/ic_45d16d_managed.md (adversarially verified CORRECTED
2026-07-19 + independently re-verified CONFIRMED; zero invented constants). Every constant
below cites its brief row (the §8 parameter table).

Doctrine (§3 entry / §4 exit - §4 OVERRIDES the platform exit ladder for this cohort):
  * Standing short-premium program, no signal trigger (row 2): per underlying, if flat in
    that name, open one condor at the next passing scan inside the 10:00-15:30 ET window
    (row 19); re-enter after each exit. max_concurrent=3 = one condor per index name.
  * Expiration nearest 45 calendar DTE inside the 35-55 band (rows 3/4); exact-distance
    ties prefer the monthly, then the earlier listing (row 22). All 4 legs share it.
  * Shorts: the put and the call whose SOLVED |delta| is nearest 0.16, accepted only in
    0.12-0.20 (rows 5-7; hub.row_greeks from live mids - the platform greeks law).
  * Wings (row 10 EXACTLY as recorded - no fixed width, no 5-delta rule): the symmetric
    listed width whose MID net credit is closest to 1/3 of width (row 8), tie -> narrower,
    width <= $25 (row 11); skip the name when the best width collects < 1/4 of width
    (row 9 - the implicit IV floor) and journal it; the shortfall vs the 1/3 target is
    logged in the signal (§3.4). All four legs must be two-sided NBBO (§9).
  * IV gate: NONE numeric (row 18 - the source is qualitative "High" only). Registered
    gate ladder: iv_rank archive is cold platform-wide -> VIX 252d percentile via
    hub.vol_regime() logged as an entry covariate; when THAT is unavailable too, enter
    anyway with risk_flag `gate_unavailable`. The gate never blocks - covariate, not
    threshold. FOMC/CPI: log-only, trade through (row 21).
  * Universe: META arms the index core SPY/QQQ/IWM only; the brief row 1 single-name tier
    (and its row-20 earnings gate) is NOT armed in this module - the index tier needs no
    earnings gate (§9).
  * Exits (manage(), memoryless - profit checked first, so a <=21-DTE mark that also
    satisfies the target closes as the standing GTC fill, row 13):
      profit_50pct       buy the condor back when the MID cost to close <= 50% of the
                         entry credit (rows 12/13). Entry credit = -net_open["optimistic"]
                         (the mid ledger - matches the mid-fill doctrine the rule was
                         published against); cost to close = -(sum side*qty*mid) over legs
                         from hub.last_nbbo.
      dte_21_management  close at the first mark at <= 21 calendar DTE, win or lose
                         (row 14). Never hold past 21 DTE; expiry is unreachable by rule,
                         so a runner expiry-backstop close on this lane = implementation
                         bug (§7), not doctrine.
      NO stop-loss (row 15 - the absence is SOURCE-VERBATIM), no rolls (row 16), and any
      leg without a quote at a mark = hold (fail to holding, never to a blind exit).
  * Sizing: 1 condor = 4 legs x 1 contract, account-blind (row 23). CaR basis is the
    defined-risk width - credit -> grading_basis MAX_LOSS (row 24), which is exactly what
    payoff_analysis derives for a symmetric 4-leg condor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM")


@dataclass(frozen=True)
class IcParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    entry_dte_target: row 3 SOURCE-VERBATIM 'around 45 days to expiration'.
    entry_dte_min/entry_dte_max: row 4 ADAPTED 35-55 band ('around 45' operationalized).
    short_delta: rows 5/6 SOURCE-RANGE (published 16-20 delta; 16 per id / 1SD convention).
    delta_band_lo/delta_band_hi: row 7 ADAPTED strike-grid acceptance 0.12-0.20.
    credit_target_frac: row 8 SOURCE-VERBATIM '1/3rd the width of the strikes in premium'.
    credit_floor_frac: row 9 ADAPTED - skip entry when best width collects < 1/4 width.
    wing_width_cap: row 11 PLATFORM-POLICY <= $25 per side (CaR bound).
    profit_take_frac: row 12 SOURCE-VERBATIM - buy back at 50% of the entry credit.
    time_exit_dte: row 14 SOURCE-VERBATIM (secondary attribution) - close at <= 21 DTE.
    entry_minute_from/entry_minute_to: row 19 PLATFORM-POLICY 10:00-15:30 ET scan window
    (from inclusive, to exclusive)."""
    entry_dte_target: int = 45
    entry_dte_min: int = 35
    entry_dte_max: int = 55
    short_delta: float = 0.16
    delta_band_lo: float = 0.12
    delta_band_hi: float = 0.20
    credit_target_frac: float = 1.0 / 3.0
    credit_floor_frac: float = 0.25
    wing_width_cap: float = 25.0
    profit_take_frac: float = 0.50
    time_exit_dte: int = 21
    entry_minute_from: int = 600          # 10:00 ET
    entry_minute_to: int = 930            # exclusive; = 15:30 ET


def _mid(row) -> float:
    return (float(row.bid) + float(row.ask)) / 2.0


def _leg(row, sym: str, opt_type: str, side: int, exp: str, g: dict) -> dict:
    return {"occ": row.symbol, "underlying": sym, "opt_type": opt_type,
            "strike": float(row.strike), "expiry": exp, "side": side, "qty": 1,
            "nbbo": {"bid": float(row.bid), "ask": float(row.ask)},
            "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
            "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
            "theta_day": g.get("theta_day", 0.0)}


class Ic45d16dManaged(Strategy):
    META = StrategyMeta(
        strategy_id="ic_45d16d_managed", version=1,
        name="tasty 45DTE 16-delta iron condor, managed 50% credit / 21 DTE",
        universe=UNIVERSE, dte_range=(35, 50),
        max_concurrent=3,                             # one condor per index name (row 2)
        event_policy=EventPolicy.TRADE_THROUGH,       # row 21: macro is log-only
        grading_basis=GradingBasis.MAX_LOSS,          # row 24: width - credit
        defining_mechanism="short_vol_carry",
        settle_at_expiry=False,                       # §4: MANAGED - always out by 21 DTE
        scan_interval_s=300.0, mark_interval_s=300.0,
        expected_fires_per_20_sessions=3.0)           # §10 cadence on the 3-name core
    params = IcParams()

    # -- entry selection helpers (rows 3-11) --------------------------------
    def _entry_expiry(self, ctx, sym: str, today: date) -> str | None:
        """Listed expiration with DTE nearest entry_dte_target inside [min, max]
        (rows 3/4); exact-distance ties prefer the monthly, then the earlier (row 22)."""
        p = self.params
        best_key, best = None, None
        for e in ctx.hub.expirations(sym):
            try:
                d = date.fromisoformat(str(e))
            except ValueError:
                continue
            dte = (d - today).days
            if not (p.entry_dte_min <= dte <= p.entry_dte_max):
                continue
            key = (abs(dte - p.entry_dte_target), 0 if self._monthly(d) else 1, dte)
            if best_key is None or key < best_key:
                best_key, best = key, str(e)
        return best

    @staticmethod
    def _monthly(d: date) -> bool:
        return d.weekday() == 4 and 15 <= d.day <= 21          # 3rd-Friday convention

    @staticmethod
    def _two_sided(rows) -> dict:
        """{'put'|'call': {strike: row}} restricted to two-sided NBBO (§9: no_quote on
        any leg = skip that leg entirely - as short AND as wing)."""
        book = {"put": {}, "call": {}}
        for r in rows:
            if getattr(r, "option_type", "") not in ("put", "call"):
                continue
            if (r.bid or 0) > 0 and (r.ask or 0) > 0:
                book[r.option_type][float(r.strike)] = r
        return book

    def _short_leg(self, ctx, by_strike: dict, opt_type: str, S: float, dte: int):
        """OTM strike whose solved |delta| is nearest short_delta, accepted only inside
        [delta_band_lo, delta_band_hi] (rows 5-7). Returns (row, greeks) or None."""
        p = self.params
        best_score, best = None, None
        for k in sorted(by_strike):
            if (opt_type == "put" and k >= S) or (opt_type == "call" and k <= S):
                continue
            r = by_strike[k]
            g = ctx.hub.row_greeks(opt_type=opt_type, strike=k, S=S, mid=_mid(r),
                                   dte_days=dte)
            if not g:
                continue
            ad = abs(float(g.get("delta") or 0.0))
            if not (p.delta_band_lo <= ad <= p.delta_band_hi):
                continue
            score = abs(ad - p.short_delta)
            if best_score is None or score < best_score:
                best_score, best = score, (r, g)
        return best

    def _wings(self, book: dict, kp: float, kc: float):
        """Symmetric listed width whose MID net credit is closest to
        credit_target_frac * width, tie -> narrower; width <= wing_width_cap
        (rows 8/10/11). Score rounded to 6dp so exact doctrine ties are float-stable.
        Returns (width, long_put_row, long_call_row, credit_mid) or None."""
        p = self.params
        puts, calls = book["put"], book["call"]
        if kp not in puts or kc not in calls:
            return None
        shorts_mid = _mid(puts[kp]) + _mid(calls[kc])
        cands = []
        for k in puts:
            w = round(kp - k, 4)
            if w <= 0 or w > p.wing_width_cap:
                continue
            cr = calls.get(round(kc + w, 4))
            if cr is None:
                continue
            credit = shorts_mid - (_mid(puts[k]) + _mid(cr))
            score = round(abs(credit - w * p.credit_target_frac), 6)
            cands.append((score, w, puts[k], cr, credit))
        if not cands:
            return None
        cands.sort(key=lambda t: (t[0], t[1]))                 # tie -> narrower (row 10)
        _, w, lp, cr, credit = cands[0]
        return w, lp, cr, credit

    @staticmethod
    def _vix_percentile(ctx):
        """Row 18 covariate via the registered gate ladder: iv_rank archive is cold ->
        VIX 252d percentile from hub.vol_regime(); None (file absent OR pctile cold) ->
        the caller flags gate_unavailable and enters anyway (the gate is log-only)."""
        fn = getattr(ctx.hub, "vol_regime", None)
        vr = fn() if callable(fn) else None
        if not isinstance(vr, dict):
            return None
        return vr.get("vix_pctile_252d")

    @staticmethod
    def _journal(ctx, rec: dict) -> None:
        if ctx.journal:
            ctx.journal(rec)

    # -- scan (rows 2-11, 18-19, 22-23) -------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        if not (p.entry_minute_from <= ctx.minute < p.entry_minute_to):
            return []
        today = ctx.dt_et.date()
        holding = {pos.underlying for pos in ctx.open_positions}     # row 2: one per name
        vix_pct = self._vix_percentile(ctx)
        out = []
        for sym in self.META.universe:
            if sym in holding:
                continue
            S = ctx.hub.ref_price(sym)
            if S <= 0:
                continue
            exp = self._entry_expiry(ctx, sym, today)
            if exp is None:
                self._journal(ctx, {"event": "ic_no_expiry", "symbol": sym,
                                    "day": str(today)})
                continue
            dte = (date.fromisoformat(exp) - today).days
            book = self._two_sided(ctx.hub.chain(sym, exp))
            short_put = self._short_leg(ctx, book["put"], "put", S, dte)
            short_call = self._short_leg(ctx, book["call"], "call", S, dte)
            if short_put is None or short_call is None:
                self._journal(ctx, {"event": "ic_no_short_strike", "symbol": sym,
                                    "expiry": exp, "S_ref": round(S, 4)})
                continue
            (sp_row, sp_g), (sc_row, sc_g) = short_put, short_call
            wings = self._wings(book, float(sp_row.strike), float(sc_row.strike))
            if wings is None:
                self._journal(ctx, {"event": "ic_no_wings", "symbol": sym, "expiry": exp})
                continue
            width, lp_row, lc_row, credit_mid = wings
            if credit_mid < p.credit_floor_frac * width:             # row 9 floor
                self._journal(ctx, {"event": "ic_credit_floor_skip", "symbol": sym,
                                    "expiry": exp, "width": width,
                                    "credit_mid": round(credit_mid, 4),
                                    "floor": round(p.credit_floor_frac * width, 4)})
                continue
            lp_g = ctx.hub.row_greeks(opt_type="put", strike=float(lp_row.strike), S=S,
                                      mid=_mid(lp_row), dte_days=dte) or {}
            lc_g = ctx.hub.row_greeks(opt_type="call", strike=float(lc_row.strike), S=S,
                                      mid=_mid(lc_row), dte_days=dte) or {}
            legs = [_leg(sp_row, sym, "put", -1, exp, sp_g),
                    _leg(lp_row, sym, "put", +1, exp, lp_g),
                    _leg(sc_row, sym, "call", -1, exp, sc_g),
                    _leg(lc_row, sym, "call", +1, exp, lc_g)]
            out.append(ProposedCombo(
                kind="iron_condor", underlying=sym, legs=legs,
                signal={"S_ref": round(S, 4), "expiry": exp, "dte_days": dte,
                        "short_put": float(sp_row.strike),
                        "short_put_delta": sp_g.get("delta"),
                        "short_call": float(sc_row.strike),
                        "short_call_delta": sc_g.get("delta"),
                        "wing_width": width,
                        "long_put": float(lp_row.strike),
                        "long_call": float(lc_row.strike),
                        "credit_mid": round(credit_mid, 4),
                        "credit_target_third": round(width * p.credit_target_frac, 4),
                        "credit_frac_of_width": round(credit_mid / width, 4),
                        "credit_shortfall_vs_third": round(
                            max(0.0, width * p.credit_target_frac - credit_mid), 4),
                        "vix_pctile_252d": vix_pct,              # row 18 covariate
                        "macro_blackout": ctx.in_blackout or None},   # row 21 log-only
                risk_flags=([] if vix_pct is not None else ["gate_unavailable"])))
        return out

    # -- manage (rows 12-17): 50% credit buyback + 21-DTE, nothing else -----
    def manage(self, pos, ctx) -> ExitAction | None:
        p = self.params
        net_close = 0.0
        for ls in pos.legs:
            nb = ctx.hub.last_nbbo(ls.spec.occ)
            if nb is None:
                return None                    # unquoted leg -> hold, never a blind exit
            net_close += ls.spec.side * ls.spec.qty * ((float(nb[0]) + float(nb[1])) / 2.0)
        cost_to_close = -net_close             # positive debit to buy the condor back
        entry_credit = -float(pos.net_open.get("optimistic") or 0.0)  # mid ledger (row 12)
        dte = (pos.nearest_expiry - ctx.dt_et.date()).days
        state = {"entry_credit": round(entry_credit, 4),
                 "cost_to_close": round(cost_to_close, 4),
                 "cost_frac_of_credit": (round(cost_to_close / entry_credit, 4)
                                         if entry_credit > 0 else None),
                 "dte": dte}
        if entry_credit > 0 and cost_to_close <= p.profit_take_frac * entry_credit:
            return ExitAction(action="close", rule="profit_50pct", state=state)  # rows 12/13
        if dte <= p.time_exit_dte:                                               # row 14
            return ExitAction(action="close", rule="dte_21_management", state=state)
        return None                            # row 15: NO stop-loss; row 16: no rolls
