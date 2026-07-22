"""atm_calendar_low_iv - ATM call calendar (short front / long back, SAME strike), low-IV entry.

AUTHORITY: docs/strategies/briefs/atm_calendar_low_iv.md (verified CORRECTED 2026-07-19).
Provenance: Natenberg 1994 Ch. 8 (volatility logic - long time spreads are positive-vega and
want LOW implied vol, pp. 152/166-167) + McMillan 5th ed. Ch. 9 (structure/management,
pp. 191-199). Every constant below cites its brief row; ADAPTED / PLATFORM constants are
never attributed to the sources (brief §10 honesty ledger).

Doctrine (brief §3/§4 - overrides ALL platform exit doctrine for this cohort):
  * Structure (rows 1-4, SOURCE-VERBATIM): SELL 1 nearer-expiry call + BUY 1 farther-expiry
    call, SAME strike (listed strike nearest spot at entry), same type, 1:1 - the covered
    multi-expiry shape whose max loss is bounded by the debit paid (row 16), which is exactly
    what carisk.grading_block derives (basis DEBIT) for covered calendars.
  * Entry gate (rows 7-8): enter only when IV is LOW - the INVERSE of the premium-sellers'
    gate. The published rule is comparative only (no number exists in source); the
    operational gate is the IV-rank fallback ladder rung 2: VIX 252d percentile < 30
    (ADAPTED - threshold is ours) read from hub.vol_regime(). Gate data unavailable ->
    NO ENTRY + cal_gate_unavailable journal: low IV is this strategy's AFFIRMATIVE entry
    condition and cannot be presumed absent data (the generic lab rung-3 "ungated + flag"
    idiom is a premium-seller veto convention, not applied here).
  * DTE mapping (PLATFORM-MANDATE, deviates from brief rows 5-6): front 7-10d / back 30-40d
    per the lab wave spec (META dte_range=(5,45)). The brief's PUBLISHED values are front
    56-84d (McMillan p. 194 "8 to 12 weeks") with back = first monthly 63-98d after front;
    the compressed mapping here mirrors the Options Playbook one-month variant noted in
    row 6 and is tagged as OURS, never as published.
  * Exit (rows 11-13): close BOTH legs as one spread at T-5 TRADING days before front expiry
    (rule "front_expiry_week_exit", row 11 ADAPTED - fires well before the runner's
    expiry-day backstop rail); close immediately if the short call trades at parity,
    bid <= intrinsic while ITM (rule "short_parity_assignment_guard", row 12
    SOURCE-VERBATIM, McMillan p. 194). NO stop-loss (row 13: hold through adverse
    breakouts, risk capped at the debit) and NO profit target (row 14: the 2x-debit
    aspiration is recorded, NOT armed) - manage() implements exactly the two rules above.
  * Universe: ETF subset SPY/QQQ/IWM of the brief's row-18 tier, so the earnings gate
    (row 9) is moot - ETFs exempt. One open calendar per symbol (row 20); 1 spread,
    account-blind (row 17). Legs list order is [short front, long back].
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from atlas.options.session_calendar import is_trading_day

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM")


@dataclass(frozen=True)
class AtmCalendarParams:
    """Tunables (the pre-registered tweak neighborhood; structure + exit SHAPE are doctrine).
    vix_pctile_max: brief row 8 ADAPTED - pass BELOW 30 (inverse of the sellers' gate); the
      threshold 30 is OURS, the published rule (row 7, Natenberg pp. 166-167) is comparative
      only. Fallback-ladder rung 2 (VIX 252d percentile) until the IV archive warms.
    front/back DTE windows: PLATFORM-MANDATE (lab wave spec front ~7-10d, back ~30-40d) - 
      deviates from brief rows 5-6 published 56-84d front + first-monthly 63-98d-after
      back; Options Playbook one-month variant (row 6 note) is the documented analogue.
      NOT attributed to McMillan/Natenberg (brief §10 honesty ledger).
    front_exit_trading_days: brief row 11 ADAPTED - close both legs as one spread T-5
      trading days before front expiry (McMillan's published rule is "by front expiry";
      the one-week buffer is ours, mandated by the strategy id)."""
    vix_pctile_max: float = 30.0
    front_dte_min: int = 7
    front_dte_max: int = 10
    back_dte_min: int = 30
    back_dte_max: int = 40
    front_exit_trading_days: int = 5


class AtmCalendarLowIv(Strategy):
    META = StrategyMeta(
        strategy_id="atm_calendar_low_iv", version=1,
        name="ATM call calendar, short front / long back same strike, low-IV entry",
        universe=UNIVERSE, dte_range=(5, 45),
        max_concurrent=3,                              # 1 per underlying x 3 ETFs (row 20)
        event_policy=EventPolicy.TRADE_THROUGH,        # no published event gate; ETFs exempt row 9
        grading_basis=GradingBasis.DEBIT,              # row 16: max loss = net debit (covered shape)
        defining_mechanism="term_structure",
        settle_at_expiry=False,                        # row 11: never rides into front expiry
        scan_interval_s=300.0, mark_interval_s=300.0,  # EOD-cadence family (brief §10)
        expected_fires_per_20_sessions=2.0)            # regime-clustered trickle (brief §10)
    params = AtmCalendarParams()

    # -- expiry selection (windowed; earliest listed inside window, exemplar idiom) ------
    def _expiry_in_window(self, ctx, sym: str, today: date, lo: int, hi: int):
        """(expiry_iso, dte) for the earliest listed expiration with dte in [lo, hi];
        (None, None) when nothing is listed in the window."""
        best, best_dte = None, None
        for e in ctx.hub.expirations(sym):
            try:
                y, m, d = map(int, str(e).split("-"))
                dte = (date(y, m, d) - today).days
            except ValueError:
                continue
            if lo <= dte <= hi and (best_dte is None or dte < best_dte):
                best, best_dte = str(e), dte
        return best, best_dte

    @staticmethod
    def _twosided_calls(rows: list) -> dict:
        """{strike: row} for call rows with two-sided NBBO (row 19 liquidity gate)."""
        return {r.strike: r for r in rows
                if r.option_type == "call" and (r.bid or 0) > 0 and (r.ask or 0) > 0}

    # -- scan (rows 1-8, 18-20) ----------------------------------------------------------
    def scan(self, ctx) -> list:
        today = ctx.dt_et.date()
        regime = ctx.hub.vol_regime() or {}
        pctile = regime.get("vix_pctile_252d")
        if pctile is None:                             # gate data absent -> NO ENTRY (see docstring)
            if ctx.journal:
                ctx.journal({"event": "cal_gate_unavailable", "day": str(today)})
            return []
        pctile = float(pctile)
        if not pctile < self.params.vix_pctile_max:    # row 8: LOW-vol gate, strict <
            if ctx.journal:
                ctx.journal({"event": "cal_gate_blocked", "day": str(today),
                             "vix_pctile_252d": pctile,
                             "max": self.params.vix_pctile_max})
            return []
        holding = {p.underlying for p in ctx.open_positions}   # row 20: 1 per symbol
        out = []
        for sym in self.META.universe:
            if sym in holding:
                continue
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            front, front_dte = self._expiry_in_window(
                ctx, sym, today, self.params.front_dte_min, self.params.front_dte_max)
            back, back_dte = self._expiry_in_window(
                ctx, sym, today, self.params.back_dte_min, self.params.back_dte_max)
            if front is None or back is None or back_dte <= front_dte:
                if ctx.journal:                        # covered shape needs back AFTER front
                    ctx.journal({"event": "cal_no_expiry_pair", "symbol": sym,
                                 "front": front, "back": back})
                continue
            front_calls = self._twosided_calls(ctx.hub.chain(sym, front))
            back_calls = self._twosided_calls(ctx.hub.chain(sym, back))
            common = set(front_calls) & set(back_calls)    # SAME strike in BOTH expiries (row 1)
            if not common:
                if ctx.journal:
                    ctx.journal({"event": "cal_no_common_strike", "symbol": sym,
                                 "front": front, "back": back})
                continue
            K = min(common, key=lambda k: (abs(k - S_ref), k))   # nearest ATM (row 4)
            f, b = front_calls[K], back_calls[K]
            f_mid, b_mid = (f.bid + f.ask) / 2.0, (b.bid + b.ask) / 2.0
            debit_mid = b_mid - f_mid
            if debit_mid <= 0:                         # inverted term quotes: not a debit calendar
                if ctx.journal:
                    ctx.journal({"event": "cal_nonpositive_debit", "symbol": sym,
                                 "strike": K, "debit_mid": round(debit_mid, 4)})
                continue
            fg = ctx.hub.row_greeks(opt_type="call", strike=K, S=S_ref, mid=f_mid,
                                    dte_days=max(1, front_dte)) or {}
            bg = ctx.hub.row_greeks(opt_type="call", strike=K, S=S_ref, mid=b_mid,
                                    dte_days=max(1, back_dte)) or {}
            legs = []
            for row, g, side, exp in ((f, fg, -1, front), (b, bg, +1, back)):
                legs.append({"occ": row.symbol, "underlying": sym, "opt_type": "call",
                             "strike": K, "expiry": exp, "side": side, "qty": 1,
                             "nbbo": {"bid": row.bid, "ask": row.ask},
                             "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                             "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                             "theta_day": g.get("theta_day", 0.0)})
            out.append(ProposedCombo(
                kind="atm_call_calendar", underlying=sym, legs=legs,
                signal={"S_ref": round(S_ref, 4), "strike": K,
                        "front_expiry": front, "front_dte": front_dte,
                        "back_expiry": back, "back_dte": back_dte,
                        "front_mid": round(f_mid, 4), "back_mid": round(b_mid, 4),
                        "debit_mid": round(debit_mid, 4),
                        "net_vega": round(bg.get("vega", 0.0) - fg.get("vega", 0.0), 4),
                        "net_theta_day": round(bg.get("theta_day", 0.0)
                                               - fg.get("theta_day", 0.0), 4),
                        "vix_pctile_252d": pctile, "gate_rung": "vix_pctile_252d",
                        "regime_asof": regime.get("asof")},
                risk_flags=[]))
        return out

    # -- manage (rows 11-14): exactly two rules, no stop, no profit target ---------------
    @staticmethod
    def _trading_days_until(today: date, expiry: date) -> int:
        """Trading days in (today, expiry] - 0 when expiry is today or past."""
        n, d = 0, today
        while d < expiry:
            d += timedelta(days=1)
            if is_trading_day(d):
                n += 1
        return n

    def manage(self, pos, ctx) -> ExitAction | None:
        short = next((ls for ls in pos.legs if ls.spec.side < 0), None)
        if short is None:                              # malformed combo: runner rails own it
            return None
        # Row 12 (SOURCE-VERBATIM, urgent - checked first): short call at parity while ITM.
        S = ctx.hub.ref_price(pos.underlying)
        nbbo = ctx.hub.last_nbbo(short.spec.occ)
        if S > 0 and nbbo is not None:
            bid = float(nbbo[0])
            intr = max(0.0, S - short.spec.strike)
            if intr > 0 and bid <= intr:
                return ExitAction(action="close", rule="short_parity_assignment_guard",
                                  state={"S": round(S, 4), "short_bid": round(bid, 4),
                                         "intrinsic": round(intr, 4),
                                         "quote_age_s": float(nbbo[2]) if len(nbbo) > 2 else None})
        # Row 11 (ADAPTED): close both legs T-5 trading days before front expiry - fires
        # strictly before the runner's expiry-day backstop (strategy exit owns the close).
        td_left = self._trading_days_until(ctx.dt_et.date(), short.spec.expiry)
        if td_left <= self.params.front_exit_trading_days:
            return ExitAction(action="close", rule="front_expiry_week_exit",
                              state={"trading_days_to_front": td_left,
                                     "front_expiry": short.spec.expiry.isoformat()})
        return None                                    # rows 13/14: no stop, no profit target
