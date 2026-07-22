"""vrp_short_straddle - VRP-gated ~30DTE short ATM straddle (unhedged, managed).

AUTHORITY: docs/strategies/briefs/vrp_short_straddle.md (verified CORRECTED 2026-07-19,
zero invented constants). Provenance: Bakshi-Kapadia 2003 (negative market volatility risk
premium), Coval-Shumway 2001 (short ATM index straddles ~ -3%/wk for buyers), Goyal-Saretto
2009 (the IV-vs-HV gate), projectfinance 2022 (management constants). The composition is
ADAPTED (brief §1/§2) - no single source publishes this exact strategy end-to-end.

Doctrine (brief §8 rows cited; §4 OVERRIDES platform exit doctrine for this cohort):
  * VRP gate (row 8, ADAPTED per-symbol from Goyal-Saretto's cross-sectional sign split - 
    their N group, IV above HV, is the published short side): enter only when
    IV_atm30 - HV_12m > 0. The published condition is the SIGN; the absolute threshold is
    recorded UNKNOWN in row 8 and is deliberately NOT invented here.
      - HV (row 9): sample std dev of daily LOG returns over the trailing 252 trading days,
        annualized by sqrt(252), from hub.daily_history closes (prior-close information).
        Fewer than 253 closes -> the published window is not computable -> skip + journal.
      - IV (row 10): mean of the ATM call IV and ATM put IV solved from live mids at the
        chosen strike/expiry (hub.row_greeks; one-leg fallback tagged "atm_single"). If
        NEITHER leg solves, fall back to VIX close / 100 from hub.vol_regime() (row 11's
        documented ETF-tier marker, unit-normalized). vol_regime absent AND no computable
        IV -> skip with journal (fail to no-entry, never to a guessed gate).
  * Structure (rows 4/5/6): SHORT 1 ATM call + SHORT 1 ATM put, same strike, same expiry,
    1:1 ratio, UNHEDGED (row 7 - the deliberate no-stock-leg expression). Strike = nearest
    to spot among strikes carrying BOTH legs two-sided (bid>0 AND ask>0 each leg - row 20
    quote sanity), restricted to the 0.975-1.025 moneyness band (row 5); nearest-|K-S| wins,
    ties to the lower strike.
  * Expiry (rows 2/3): nearest |DTE-30| inside the 25-35 acceptance band.
  * Max ONE open straddle per symbol (row 18's enforced parenthetical).
  * manage() (rows 14/15 - projectfinance combined rule "25% Profit OR 100% Loss"):
    credit received = -pos.net_open["optimistic"]; buyback cost = sum of leg mids from
    hub.last_nbbo. Close when cost <= (1-0.25)*credit (rule "profit_25pct") or when
    cost >= 2.0*credit (rule "stop_100pct"). Boundaries are INCLUSIVE per the source's
    reach semantics ($10 credit -> close at $7.50 / at $20). Any leg quote missing or dead
    -> hold (never exit blind). Neither rule hit -> hold to expiration (row 16). The
    "21 DTE" rule is [unverified] lore and NOT adopted (§4); no rolls (row 17); no
    gate-reversal early close (§4).
  * Grading basis CAR (row 22): a naked short straddle is unbounded_up, so the runner's
    grading_block derives the reg_t_v1 proxy (carisk.py) - declared basis matches derived.

Deviations from the brief, flagged loudly:
  * Universe = ETF tier ONLY (SPY/QQQ/IWM) this wave - the single-name tier (row 1) and its
    earnings blackout (row 19) ship together later; ETFs are row-19-exempt so no earnings
    machinery is wired here.
  * settle_at_expiry=False: the runner's expiry-day backstop closes surviving combos at
    close-10min instead of row 16's terminal-intrinsic settlement (platform rail; with the
    §4 managed overlay the final 10 minutes are immaterial).
  * Row 12's t/t+1 entry lag is not reproducible in a stateless scan: HV is prior-close by
    construction; IV is evaluated live at scan time (§3.4 platform-convention line).
  * Row 18's "eligible again first trading day after exit" needs closed-position visibility
    scan() does not have; the one-open-per-symbol check is the enforced part.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM")
ANNUALIZATION_TD = 252.0     # row 9: "(252 td), annualized" - per-year base, not a tunable


@dataclass(frozen=True)
class VrpParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    Every field cites its brief §8 row in tests/strategy_lab/test_lab_provenance.py."""
    dte_target: int = 30              # row 2: ~one-month straddle
    dte_min: int = 25                 # row 3: 25-35 DTE acceptance band, lower edge
    dte_max: int = 35                 # row 3: upper edge
    moneyness_lo: float = 0.975       # row 5: Goyal-Saretto moneyness band, lower edge
    moneyness_hi: float = 1.025       # row 5: upper edge
    hv_lookback_td: int = 252         # row 9: trailing 12 months of daily returns
    profit_target_frac: float = 0.25  # row 14: adopted 25% of credit received
    stop_loss_mult: float = 2.0       # row 15: -100% stop = mark >= 2x credit


class VrpShortStraddle(Strategy):
    META = StrategyMeta(
        strategy_id="vrp_short_straddle", version=1,
        name="VRP-gated 30DTE short ATM straddle, 25%PT/100%SL",
        universe=UNIVERSE, dte_range=(25, 35),
        max_concurrent=3,                             # one straddle per ETF symbol (row 18)
        event_policy=EventPolicy.TRADE_THROUGH,       # §3.5: no published event gates
        grading_basis=GradingBasis.CAR,               # row 22: naked short -> reg_t proxy
        defining_mechanism="short_vol_carry",
        settle_at_expiry=False,                       # platform backstop, see deviations
        scan_interval_s=300.0, mark_interval_s=300.0,
        expected_fires_per_20_sessions=6.0)
    params = VrpParams()

    # -- rule ids (rows 14/15) - derived from params so a tweak renames the rule ----------
    def profit_rule_id(self) -> str:
        return f"profit_{int(round(self.params.profit_target_frac * 100))}pct"

    def stop_rule_id(self) -> str:
        return f"stop_{int(round((self.params.stop_loss_mult - 1.0) * 100))}pct"

    # -- realized vol (row 9) --------------------------------------------------------------
    @staticmethod
    def _closes(bars) -> list:
        """Positive closes from daily-history bars (TBar-like .close, dict, or raw number)."""
        out = []
        for b in bars or []:
            c = getattr(b, "close", None)
            if c is None and isinstance(b, dict):
                c = b.get("close")
            elif c is None and isinstance(b, (int, float)):
                c = b
            try:
                c = float(c)
            except (TypeError, ValueError):
                continue
            if c > 0:
                out.append(c)
        return out

    def realized_vol(self, bars) -> float | None:
        """Row 9: annualized sample std dev of daily log returns over the trailing
        hv_lookback_td trading days. Needs lookback+1 closes; None = not computable
        (the published 12-month window cannot be shortened silently)."""
        closes = self._closes(bars)
        n = self.params.hv_lookback_td
        if len(closes) < n + 1:
            return None
        closes = closes[-(n + 1):]
        rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        if len(rets) < 2:
            return None
        return statistics.stdev(rets) * math.sqrt(ANNUALIZATION_TD)

    # -- contract selection (rows 2-6, 20) -------------------------------------------------
    def _pick_expiry(self, ctx, sym: str, today: date) -> tuple | None:
        """Nearest |DTE - dte_target| inside [dte_min, dte_max]; ties -> shorter DTE.
        Returns (expiry_iso, dte) or None."""
        best, best_key = None, None
        for e in ctx.hub.expirations(sym):
            try:
                dte = (date.fromisoformat(str(e)) - today).days
            except ValueError:
                continue
            if self.params.dte_min <= dte <= self.params.dte_max:
                key = (abs(dte - self.params.dte_target), dte)
                if best_key is None or key < best_key:
                    best, best_key = (str(e), dte), key
        return best

    def _atm_pair(self, rows, S_ref: float) -> tuple | None:
        """Rows 4/5/6 + row 20: the strike nearest spot among strikes with BOTH legs
        two-sided, inside the 0.975-1.025 moneyness band. Returns (K, call_row, put_row)."""
        calls, puts = {}, {}
        for r in rows:
            if not ((r.bid or 0) > 0 and (r.ask or 0) > 0):
                continue
            if r.option_type == "call":
                calls[r.strike] = r
            elif r.option_type == "put":
                puts[r.strike] = r
        p = self.params
        band = [k for k in calls.keys() & puts.keys()
                if p.moneyness_lo <= k / S_ref <= p.moneyness_hi]
        if not band:
            return None
        K = min(band, key=lambda k: (abs(k - S_ref), k))
        return K, calls[K], puts[K]

    @staticmethod
    def _journal(ctx, rec: dict) -> None:
        if ctx.journal:
            ctx.journal(rec)

    def _leg(self, row, sym: str, opt_type: str, strike: float, exp: str, g: dict) -> dict:
        return {"occ": row.symbol, "underlying": sym, "opt_type": opt_type,
                "strike": strike, "expiry": exp, "side": -1, "qty": 1,
                "nbbo": {"bid": row.bid, "ask": row.ask},
                "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                "theta_day": g.get("theta_day", 0.0)}

    # -- scan (rows 2-12, 18, 20) ----------------------------------------------------------
    def scan(self, ctx) -> list:
        today = ctx.dt_et.date()
        held = {p.underlying for p in ctx.open_positions}      # row 18: one per symbol
        vr = ctx.hub.vol_regime() or {}
        try:
            vix_close = float(vr.get("vix_close") or 0.0)
        except (TypeError, ValueError):
            vix_close = 0.0
        out = []
        for sym in self.META.universe:
            if sym in held:
                continue
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            picked = self._pick_expiry(ctx, sym, today)
            if picked is None:
                self._journal(ctx, {"event": "vrp_no_expiry", "symbol": sym,
                                    "day": str(today)})
                continue
            exp, dte = picked
            pair = self._atm_pair(ctx.hub.chain(sym, exp), S_ref)
            if pair is None:
                self._journal(ctx, {"event": "vrp_no_atm_strike", "symbol": sym,
                                    "expiry": exp, "S_ref": round(S_ref, 4)})
                continue
            K, call_row, put_row = pair
            hv = self.realized_vol(ctx.hub.daily_history(sym))
            if hv is None:
                self._journal(ctx, {"event": "vrp_no_history", "symbol": sym,
                                    "need_closes": self.params.hv_lookback_td + 1})
                continue
            call_mid = (call_row.bid + call_row.ask) / 2.0
            put_mid = (put_row.bid + put_row.ask) / 2.0
            g_call = ctx.hub.row_greeks(opt_type="call", strike=K, S=S_ref, mid=call_mid,
                                        dte_days=dte) or {}
            g_put = ctx.hub.row_greeks(opt_type="put", strike=K, S=S_ref, mid=put_mid,
                                       dte_days=dte) or {}
            ivs = [g["iv"] for g in (g_call, g_put) if (g.get("iv") or 0.0) > 0]
            if ivs:                                   # row 10: mean of ATM call+put IV
                iv = sum(ivs) / len(ivs)
                iv_source = "atm_mean" if len(ivs) == 2 else "atm_single"
            elif vix_close > 0:                       # row 11 fallback, unit-normalized
                iv, iv_source = vix_close / 100.0, "vix_close"
            else:
                self._journal(ctx, {"event": "vrp_no_iv", "symbol": sym, "expiry": exp,
                                    "strike": K, "vol_regime_present": bool(vr)})
                continue
            vrp = iv - hv
            if vrp <= 0:                              # row 8: published SIGN condition
                self._journal(ctx, {"event": "vrp_gate_blocked", "symbol": sym,
                                    "iv": round(iv, 4), "hv": round(hv, 4),
                                    "vrp": round(vrp, 4), "iv_source": iv_source})
                continue
            out.append(ProposedCombo(
                kind="short_straddle", underlying=sym,
                legs=[self._leg(call_row, sym, "call", K, exp, g_call),
                      self._leg(put_row, sym, "put", K, exp, g_put)],
                signal={"S_ref": round(S_ref, 4), "strike": K, "expiry": exp,
                        "dte_days": dte, "moneyness": round(K / S_ref, 4),
                        "iv": round(iv, 4), "iv_source": iv_source,
                        "hv": round(hv, 4), "vrp": round(vrp, 4),
                        "credit_bid": round((call_row.bid or 0.0) + (put_row.bid or 0.0), 4),
                        "vix_close": round(vix_close, 2) if vix_close > 0 else None},
                risk_flags=[]))
        return out

    # -- manage (rows 14/15/16): 25% profit OR 100% loss, else hold to expiry --------------
    def manage(self, pos, ctx) -> ExitAction | None:
        credit = -float(pos.net_open.get("optimistic") or 0.0)   # short straddle: credit > 0
        if credit <= 0:
            return None                               # degenerate book - never exit on it
        cost, age_max = 0.0, 0.0
        for ls in pos.legs:
            q = ctx.hub.last_nbbo(ls.spec.occ)
            if q is None:
                return None                           # missing leg quote -> hold
            bid, ask = max(0.0, float(q[0])), max(0.0, float(q[1]))
            if ask <= 0.0:
                return None                           # dead quote -> hold, never a fake win
            cost += ls.spec.qty * (bid + ask) / 2.0
            age_max = max(age_max, float(q[2] or 0.0))
        p = self.params
        state = {"credit_ps": round(credit, 4), "cost_ps": round(cost, 4),
                 "cost_frac_of_credit": round(cost / credit, 4),
                 "quote_age_s_max": round(age_max, 1)}
        if cost <= credit * (1.0 - p.profit_target_frac):        # row 14: reach $7.50 on $10
            return ExitAction(action="close", rule=self.profit_rule_id(), state=state)
        if cost >= credit * p.stop_loss_mult:                    # row 15: reach $20 on $10
            return ExitAction(action="close", rule=self.stop_rule_id(), state=state)
        return None                                              # row 16: ride to expiry
