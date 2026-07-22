"""rsi2_oversold_short_put - Connors RSI(2) oversold pullback expressed as a short put.

AUTHORITY: docs/strategies/briefs/rsi2_oversold_short_put.md (verified CONFIRMED 2026-07-19,
two independent fresh-context passes). Provenance: Connors & Alvarez, *Short Term Trading
Strategies That Work* (2008) - Ch. 9 entry, Ch. 13 exit doctrine. The published form buys
the UNDERLYING; the entire option leg is ADAPTED (brief §2 loud-adaptation notice) and none
of it is attributable to the source. Every constant below cites its brief §8 row.

Doctrine (brief §3/§4 - overrides ALL platform exit doctrine for this cohort):
  * Signal on daily closes (row 1): Wilder RSI(2) below 5 (rows 2/3/6) while the close is
    above its 200-day SMA (rows 4/5; the Wilder form and the SMA type are the brief's
    recorded ASSUMPTIONS - the primary restates neither). Computed 15:30-15:50 ET by
    splicing the near-final close onto completed daily history (row 7: "Buy on the close",
    ADAPTED mechanics), entered in the same window.
  * Option leg (rows 15/17/18, ALL ADAPTED): sell 1 put at the strike whose |delta| is
    nearest 0.30 inside the 0.25-0.35 band, on the nearest listed expiry with 7-14 calendar
    DTE (>=7 so the published ~3.5-trading-day hold is never truncated by expiry).
  * Earnings gate (row 19, PLATFORM-POLICY): single names skip entry when earnings fall
    before entry+7 calendar days; SPY/QQQ/IWM need no calendar (§9).
  * Exit: RSI(2) daily close > 65 (row 8) -> buy back at the FIRST MARK AFTER that close
    (row 9: next-session open in practice). manage() therefore evaluates COMPLETED closes
    only, and only closes printed on/after the entry day. NO stop loss (row 11 - the Ch. 13
    no-stop doctrine), no profit target, no roll (§4.5). The ADAPTED expiry failsafe
    (row 16) is delegated to the platform expiry-day backstop: settle_at_expiry=False closes
    the combo at close-10min on expiry day, satisfying the <=1-DTE buyback.
  * Grading: naked short put -> payoff_analysis max loss at S=0 = strike*100 - credit, the
    cash-secured ceiling §10 adopts as the bounded basis -> grading_basis MAX_LOSS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")
ETF_TIER = frozenset({"SPY", "QQQ", "IWM"})   # §9: earnings calendar not needed for these


def wilder_rsi(closes: list, period: int) -> float | None:
    """Wilder-smoothed RSI over daily closes (rows 2/3: period 2; the Wilder form is the
    brief's recorded ASSUMPTION - §8 unknowns - since the primary never restates the
    formula). Seed = simple average of the first `period` gains/losses, then Wilder
    smoothing over the rest; needs period+1 closes. Degenerate tails: no losses -> 100,
    no gains -> 0 via the formula, flat both-zero -> neutral 50."""
    n = len(closes)
    if period < 1 or n < period + 1:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(0.0, d)
        losses += max(0.0, -d)
    avg_gain, avg_loss = gains / period, losses / period
    for i in range(period + 1, n):
        d = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(0.0, d)) / period
        avg_loss = (avg_loss * (period - 1) + max(0.0, -d)) / period
    if avg_loss <= 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def sma(closes: list, n: int) -> float | None:
    """Simple moving average of the LAST n closes (rows 4/5: 200-day; SMA type is the
    brief's recorded assumption, adopted per the StockCharts secondary)."""
    if n < 1 or len(closes) < n:
        return None
    return sum(closes[-n:]) / float(n)


@dataclass(frozen=True)
class Rsi2Params:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    rsi_period / entry / exit thresholds and the 200-day filter are SOURCE-VERBATIM
    (rows 2/6/8/4); the RSI formula variant and SMA type are the brief's recorded
    assumptions (rows 3/5). The entry window is row 7's ADAPTED near-close mechanics
    (15:30-15:50 ET). The option-leg values (rows 17/18) and the earnings gate (row 19)
    are ADAPTED/PLATFORM-POLICY - no published option values exist. history_days: §9
    requires >=210 trading days of closes; 260 = hub-default cushion (PLATFORM-POLICY)."""
    rsi_period: int = 2                   # row 2 SOURCE-VERBATIM: "2-period RSI"
    entry_rsi_threshold: float = 5.0      # row 6 SOURCE-VERBATIM (secondary's <10 NOT used)
    exit_rsi_threshold: float = 65.0      # row 8 SOURCE-VERBATIM: "closes above 65"
    trend_sma_days: int = 200             # row 4 SOURCE-VERBATIM; SMA type row 5 (assumed)
    entry_minute_from: int = 930          # row 7: 15:30 ET near-close window start
    entry_minute_to: int = 950            # row 7: 15:50 ET window end (exclusive)
    delta_target: float = 0.30            # row 17 ADAPTED: target |delta|
    delta_band_lo: float = 0.25           # row 17 ADAPTED: band floor
    delta_band_hi: float = 0.35           # row 17 ADAPTED: band cap
    dte_min_days: int = 7                 # row 18 ADAPTED: nearest weekly >=7 cal DTE
    dte_max_days: int = 14                # row 18 ADAPTED: cal-DTE ceiling
    earnings_gate_days: int = 7           # row 19 PLATFORM-POLICY: earnings < entry+7d -> skip
    history_days: int = 260               # §9: >=210 needed; 260 = hub default cushion


class Rsi2OversoldShortPut(Strategy):
    META = StrategyMeta(
        strategy_id="rsi2_oversold_short_put", version=1,
        name="Connors RSI(2) oversold pullback as a short put",
        universe=UNIVERSE, dte_range=(5, 16),      # chain-request band around selection 7-14
        max_concurrent=9,                          # one put per symbol; §7: fires CLUSTER
        event_policy=EventPolicy.TRADE_THROUGH,    # §3.4: no published event/IV/VIX gate
        grading_basis=GradingBasis.MAX_LOSS,       # §10: cash-secured ceiling K*100 - credit
        defining_mechanism="directional_mean_reversion",
        settle_at_expiry=False,                    # row 16 failsafe via the expiry backstop rail
        scan_interval_s=300.0, mark_interval_s=300.0,  # daily-close doctrine; 5-min cadence
        expected_fires_per_20_sessions=8.0)        # §10: ~8 trades/month, arriving in bursts
    params = Rsi2Params()

    # -- daily-close series (rows 1/7/8) -----------------------------------
    def _completed_closes(self, ctx, sym: str) -> list:
        """[(day, close)] for sessions strictly BEFORE ctx.day, chronological. Both signals
        are defined on PRINTED daily closes, so any in-progress bar the vendor returns for
        today is dropped - scan() re-adds today as the live near-final close (row 7);
        manage() never sees today's bar at all (row 9)."""
        out = []
        for b in ctx.hub.daily_history(sym, days=self.params.history_days):
            d = str(b.ts)[:10]
            if d < ctx.day and float(b.close) > 0:
                out.append((d, float(b.close)))
        out.sort(key=lambda t: t[0])
        return out

    # -- option-leg selection (rows 17/18) ---------------------------------
    def _pick_expiry(self, ctx, sym: str, today: date) -> str | None:
        """Nearest listed expiry with dte in [7, 14] (row 18: nearest weekly >=7 - the floor
        keeps the published ~3.5-day hold inside the option's life); None = no listing."""
        best, best_dte = None, None
        for e in ctx.hub.expirations(sym):
            try:
                y, m, d = map(int, e.split("-"))
                dte = (date(y, m, d) - today).days
            except ValueError:
                continue
            if self.params.dte_min_days <= dte <= self.params.dte_max_days:
                if best_dte is None or dte < best_dte:
                    best, best_dte = e, dte
        return best

    def _pick_strike(self, ctx, rows: list, S_ref: float, dte: int) -> tuple:
        """Winner = two-sided-quote put (row 20 quote-presence) whose solved |delta| is
        nearest delta_target INSIDE the 0.25-0.35 band (row 17); (None, None) when the band
        is empty - no entry rather than a nearest-out-of-band compromise."""
        best, best_g, best_err = None, None, None
        for r in sorted((r for r in rows if r.option_type == "put"
                         and (r.bid or 0) > 0 and (r.ask or 0) > 0),
                        key=lambda r: r.strike):
            mid = (r.bid + r.ask) / 2.0
            g = ctx.hub.row_greeks(opt_type="put", strike=r.strike, S=S_ref, mid=mid,
                                   dte_days=dte)
            if not g:
                continue
            ad = abs(g.get("delta", 0.0))
            if not (self.params.delta_band_lo <= ad <= self.params.delta_band_hi):
                continue
            err = abs(ad - self.params.delta_target)
            if best_err is None or err < best_err:
                best, best_g, best_err = r, g, err
        return best, best_g

    # -- scan (§3 rows 1-7, 15-20) -----------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        if not (p.entry_minute_from <= ctx.minute < p.entry_minute_to):
            return []                                  # row 7: 15:30-15:50 ET only
        today = ctx.dt_et.date()
        holding = {pos.underlying for pos in ctx.open_positions}   # one put per symbol (§4.5)
        out = []
        for sym in self.META.universe:
            if sym in holding:
                continue
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            prior = self._completed_closes(ctx, sym)
            closes = [c for _, c in prior] + [S_ref]   # near-final close = signal close (row 7)
            if len(closes) < p.trend_sma_days:
                if ctx.journal:
                    ctx.journal({"event": "rsi2_short_history", "symbol": sym,
                                 "n_closes": len(closes), "day": str(today)})
                continue
            trend_sma = sma(closes, p.trend_sma_days)
            rsi = wilder_rsi(closes, p.rsi_period)
            if trend_sma is None or rsi is None:
                continue
            if not (S_ref > trend_sma):                # rows 4/5: 200-day SMA trend gate
                continue
            if not (rsi < p.entry_rsi_threshold):      # row 6: RSI(2) below 5
                continue
            if sym not in ETF_TIER:                    # row 19: earnings gate, single names only
                edate = str((ctx.earnings.get(sym) or {}).get("date") or "")
                gate_end = (today + timedelta(days=p.earnings_gate_days)).isoformat()
                if edate and today.isoformat() <= edate < gate_end:
                    if ctx.journal:
                        ctx.journal({"event": "rsi2_earnings_gate", "symbol": sym,
                                     "earnings": edate, "day": str(today)})
                    continue
            exp = self._pick_expiry(ctx, sym, today)
            if exp is None:
                if ctx.journal:
                    ctx.journal({"event": "rsi2_no_expiry", "symbol": sym, "day": str(today)})
                continue
            dte = max(1, (date.fromisoformat(exp) - today).days)
            rows = ctx.hub.chain(sym, exp)
            row, g = self._pick_strike(ctx, rows, S_ref, dte)
            if row is None:
                if ctx.journal:
                    ctx.journal({"event": "rsi2_no_strike_in_band", "symbol": sym,
                                 "expiry": exp, "S_ref": round(S_ref, 4),
                                 "n_rows": len(rows)})
                continue
            out.append(ProposedCombo(
                kind="short_put_rsi2", underlying=sym,
                legs=[{"occ": row.symbol, "underlying": sym, "opt_type": "put",
                       "strike": row.strike, "expiry": exp, "side": -1, "qty": 1,
                       "nbbo": {"bid": row.bid, "ask": row.ask},
                       "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                       "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                       "theta_day": g.get("theta_day", 0.0)}],
                signal={"S_ref": round(S_ref, 4), "rsi2": round(rsi, 2),
                        "sma200": round(trend_sma, 4), "strike": row.strike,
                        "expiry": exp, "dte_days": dte,
                        "abs_delta": round(abs(g.get("delta", 0.0)), 4),
                        "credit_bid": row.bid,
                        "credit_pct_of_S": round(100.0 * row.bid / S_ref, 3)}))
        return out

    # -- manage (§4 rows 8-12, 16) -----------------------------------------
    def manage(self, pos, ctx) -> ExitAction | None:
        """The ONLY discretionary exit: RSI(2) closing above 65 (row 8), executed at the
        first mark AFTER that close (row 9) - so only COMPLETED sessions count, and the
        signal close must print on/after the entry day (a pre-entry overbought close is
        not an exit signal for this position). No stop (row 11), no profit target, no roll
        (§4.5); history unavailable -> hold, never exit blind. Expiry failsafe (row 16) =
        the platform backstop via settle_at_expiry=False."""
        prior = self._completed_closes(ctx, pos.underlying)
        if not prior:
            return None
        last_day = prior[-1][0]
        if last_day < pos.entry_day:
            return None                                # no post-entry close printed yet
        rsi = wilder_rsi([c for _, c in prior], self.params.rsi_period)
        if rsi is None:
            return None
        if rsi > self.params.exit_rsi_threshold:       # row 8: "closes above 65"
            return ExitAction(action="close", rule="rsi2_close_above_65",
                              state={"rsi2_close": round(rsi, 2),
                                     "signal_close_day": last_day})
        return None
