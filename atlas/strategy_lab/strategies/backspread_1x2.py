"""backspread_1x2 - call/put 1x2 backspread for even money or a credit, direction-adaptive.

AUTHORITY: docs/strategies/briefs/backspread_1x2.md (verified CONFIRMED 2026-07-19, zero
invented constants). Provenance: McMillan "Options as a Strategic Investment" (Ch.13, Ch.34,
Ch.39); Natenberg "Option Volatility and Pricing" (Ch.8). Every constant cites its brief row.

Doctrine (§3/§4 - §4 OVERRIDES all platform exit doctrine for this cohort):
  * Structure (call side): SELL 1 call at K1, BUY 2 calls at K2 > K1, same expiry. Put side
    (mirror): SELL 1 put at K2, BUY 2 puts at K1 < K2. Delta ratio ≈ 2:1 (sell ~0.40Δ, buy
    ~0.20Δ; McMillan p.842 worked example). The long leg carries qty=2.
  * THE DEFINING GATE (§3): net premium >= 0 - established for a credit or even money; reject
    debits ("if the spread cannot be initiated at a credit, it is usually not attractive",
    McMillan p.233). Walk the long strike OUTWARD (cheaper) until the combo clears net credit
    >= 0, else skip.
  * Direction (ADAPTED - the source's directional trigger is qualitative, "great upside/
    downside potential"): momentum sign of ref_price vs its trend SMA - above → call
    backspread (up thesis), below → put backspread (down thesis). Tagged ADAPTED (row 10-ish).
  * Low-IV gate (§3, McMillan p.841 "used if implied volatility were in a low percentile"):
    enter only when VIX 252d percentile is LOW (vol_regime fallback ladder; unavailable →
    enter flagged gate_unavailable). No numeric percentile is published (ADAPTED default).
  * DTE (ADAPTED, none published): nearest monthly 45-75 DTE.
  * EXIT (§4, overrides platform ladders): X1 default = hold toward expiration (no stop, no
    time exit - the debit... no, the MAX LOSS bounds risk). X2 profit-take = close when the
    position's mark shows a gain >= the frozen max-loss magnitude (the source's own worst-case
    quantity used as a symmetric target - ADAPTED, non-invented). X5 early-assignment guard =
    short leg ITM with extrinsic <= $0.05 inside 5 DTE → close (ADAPTED numbers; trigger
    published). NO profit target beyond X2 (source rejects early profit-taking generally, but
    NAMES the favorable-move close - X2 is that named action).
  * MAX_LOSS basis: bounded max loss at the long strike, unbounded gain (payoff_analysis
    derives it). settle_at_expiry=False - the global expiry backstop stands behind X1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")


@dataclass(frozen=True)
class BackspreadParams:
    """Tunables (pre-registered neighborhood; the rest is doctrine).
    sell_delta_target/buy_delta_target: §3 SOURCE (McMillan p.842) ~0.40Δ short / ~0.20Δ long,
    2:1 delta ratio. min_net_credit: §3 THE DEFINING GATE - net premium >= 0 (SOURCE-VERBATIM
    doctrine; 0.0 = even-money boundary, McMillan p.240). vix_pctile_max: §3 low-IV gate
    (ADAPTED - no numeric percentile published; 50 = 'toward the 50th percentile helps',
    McMillan p.841). trend_sma_days: ADAPTED direction proxy (source trigger is qualitative).
    dte_min/max_days: ADAPTED 45-75 (none published). ea_extrinsic_max/ea_dte: X5 ADAPTED
    ($0.05 / 5 DTE; the early-assignment trigger is published, the numbers are ours)."""
    sell_delta_target: float = 0.40
    buy_delta_target: float = 0.20
    min_net_credit: float = 0.0
    vix_pctile_max: float = 50.0
    trend_sma_days: int = 20
    dte_min_days: int = 45
    dte_max_days: int = 75
    history_days: int = 40
    ea_extrinsic_max: float = 0.05
    ea_dte: int = 5
    entry_minute_from: int = 575
    entry_minute_to: int = 955


class Backspread1x2(Strategy):
    META = StrategyMeta(
        strategy_id="backspread_1x2", version=1,
        name="1x2 call/put backspread for even money, direction-adaptive",
        universe=UNIVERSE, dte_range=(45, 75),
        max_concurrent=6,
        event_policy=EventPolicy.TRADE_THROUGH,
        grading_basis=GradingBasis.MAX_LOSS,
        defining_mechanism="long_vol_convexity",
        settle_at_expiry=False,
        scan_interval_s=300.0, mark_interval_s=300.0,
        expected_fires_per_20_sessions=2.0)
    params = BackspreadParams()

    @staticmethod
    def _sma(bars: list, n: int) -> float | None:
        if len(bars) < n:
            return None
        return sum(b.close for b in bars[-n:]) / n

    def _pick_expiry(self, ctx, sym, today) -> str | None:
        best, best_err = None, None
        for e in ctx.hub.expirations(sym):
            try:
                dte = (date.fromisoformat(e) - today).days
            except ValueError:
                continue
            if self.params.dte_min_days <= dte <= self.params.dte_max_days:
                err = abs(dte - 60)
                if best_err is None or err < best_err:
                    best, best_err = e, err
        return best

    def _build(self, ctx, sym, exp, rows, S, dte, direction) -> tuple | None:
        """Return (legs, credit_per_share) or None. call side (dir +1): short ~0.40Δ K1,
        long 2x ~0.20Δ K2>K1; put side mirror. Net credit >= min_net_credit (walk long OUT)."""
        p = self.params
        opt = "call" if direction > 0 else "put"
        cand = []
        for r in rows:
            if r.option_type != opt or (r.bid or 0) <= 0 or (r.ask or 0) <= 0:
                continue
            mid = (r.bid + r.ask) / 2.0
            g = ctx.hub.row_greeks(opt_type=opt, strike=r.strike, S=S, mid=mid, dte_days=dte)
            if not g:
                continue
            cand.append((r, g, abs(g["delta"]), mid))
        if not cand:
            return None
        short = min(cand, key=lambda x: abs(x[2] - p.sell_delta_target))
        s_row, s_g, _, s_mid = short
        # long candidates further OTM than the short (higher K for calls, lower K for puts)
        if direction > 0:
            longs = [c for c in cand if c[0].strike > s_row.strike]
        else:
            longs = [c for c in cand if c[0].strike < s_row.strike]
        if not longs:
            return None
        # order OTM-ward (cheaper first for calls = higher strike; for puts = lower strike)
        longs.sort(key=lambda c: c[0].strike, reverse=(direction > 0))
        # nearest 0.20Δ first, but require net credit >= gate; walk further OTM if needed
        longs.sort(key=lambda c: abs(c[2] - p.buy_delta_target))
        for l_row, l_g, _, l_mid in longs:
            credit = s_mid - 2.0 * l_mid                # net premium per share (mid)
            if credit >= p.min_net_credit:
                def leg(row, g, side, qty):
                    return {"occ": row.symbol, "underlying": sym, "opt_type": opt,
                            "strike": row.strike, "expiry": exp, "side": side, "qty": qty,
                            "nbbo": {"bid": row.bid, "ask": row.ask},
                            "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                            "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                            "theta_day": g.get("theta_day", 0.0)}
                return ([leg(s_row, s_g, -1, 1), leg(l_row, l_g, +1, 2)], round(credit, 4))
        return None

    def _vix_pctile(self, ctx):
        fn = getattr(ctx.hub, "vol_regime", None)
        vr = (fn() if callable(fn) else None) or {}
        try:
            return float(vr.get("vix_pctile_252d"))
        except (TypeError, ValueError):
            return None

    # -- scan --------------------------------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        if not (p.entry_minute_from <= ctx.minute < p.entry_minute_to):
            return []
        today = ctx.dt_et.date()
        held = {pos.underlying for pos in ctx.open_positions}
        pctile = self._vix_pctile(ctx)
        gate_flag = []
        if pctile is None:
            gate_flag = ["gate_unavailable"]        # ladder last rung: enter flagged
        elif pctile >= p.vix_pctile_max:
            return []                               # not a low-IV regime → no backspread
        out = []
        for sym in self.META.universe:
            if sym in held:
                continue
            bars = ctx.hub.daily_history(sym, days=max(p.history_days, p.trend_sma_days + 5))
            sma = self._sma(bars, p.trend_sma_days)
            S = ctx.hub.ref_price(sym)
            if S <= 0 or sma is None:
                continue
            direction = +1 if S >= sma else -1       # ADAPTED momentum-sign direction
            exp = self._pick_expiry(ctx, sym, today)
            if exp is None:
                continue
            dte = (date.fromisoformat(exp) - today).days
            built = self._build(ctx, sym, exp, ctx.hub.chain(sym, exp), S, dte, direction)
            if built is None:
                if ctx.journal:
                    ctx.journal({"event": "backspread_no_credit_fit", "symbol": sym,
                                 "expiry": exp, "direction": direction})
                continue
            legs, credit = built
            out.append(ProposedCombo(
                kind="call_backspread" if direction > 0 else "put_backspread",
                underlying=sym, legs=legs,
                signal={"direction": "call" if direction > 0 else "put", "S": round(S, 4),
                        "sma": round(sma, 4), "vix_pctile": pctile, "credit_per_share": credit,
                        "expiry": exp, "dte_days": dte},
                risk_flags=list(gate_flag)))
        return out

    # -- manage (§4): X2 profit-take at max-loss magnitude, X5 early-assign -
    def manage(self, pos, ctx):
        p = self.params
        today = ctx.dt_et.date()
        # current mid net (liquidation) from live NBBO
        net_close = 0.0
        have_all = True
        for ls in pos.legs:
            nb = ctx.hub.last_nbbo(ls.spec.occ) if ctx.hub else None
            if nb is None or nb[0] <= 0 or nb[1] <= 0:
                have_all = False
                break
            mid = (nb[0] + nb[1]) / 2.0
            net_close += ls.spec.side * ls.spec.qty * mid
        if have_all:
            pnl_usd = (net_close - pos.net_open["optimistic"]) * 100.0 * pos.contracts
            max_loss = float(pos.grading.get("max_loss_usd") or 0.0)
            if max_loss > 0 and pnl_usd >= max_loss:      # X2: gain >= worst-case loss magnitude
                return ExitAction(action="close", rule="backspread_x2_profit",
                                  state={"pnl_usd": round(pnl_usd, 2), "max_loss_usd": max_loss})
        # X5: short leg ITM with tiny extrinsic inside 5 DTE → early-assignment close
        for ls in pos.legs:
            if ls.spec.side >= 0:
                continue
            if (ls.spec.expiry - today).days > p.ea_dte:
                continue
            nb = ctx.hub.last_nbbo(ls.spec.occ) if ctx.hub else None
            S = ctx.hub.ref_price(pos.underlying) if ctx.hub else 0.0
            if nb is None or S <= 0:
                continue
            intrinsic = (max(0.0, S - ls.spec.strike) if ls.spec.opt_type == "call"
                         else max(0.0, ls.spec.strike - S))
            mid = (nb[0] + nb[1]) / 2.0
            if intrinsic > 0 and (mid - intrinsic) <= p.ea_extrinsic_max:
                return ExitAction(action="close", rule="backspread_x5_early_assign",
                                  state={"occ": ls.spec.occ, "extrinsic": round(mid - intrinsic, 4)})
        return None
