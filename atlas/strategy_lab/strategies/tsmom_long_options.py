"""tsmom_long_options - Moskowitz-Ooi-Pedersen time-series momentum via 60-90 DTE long options.

AUTHORITY: docs/strategies/briefs/tsmom_long_options.md (verified CORRECTED, independently
re-verified CONFIRMED, both 2026-07-19). Provenance: Moskowitz/Ooi/Pedersen, "Time Series
Momentum," JFE 104 (2012) - a FUTURES paper with ZERO option parameters: every option-leg
constant below is the brief's ADAPTED or PLATFORM-POLICY value (OURS, no published authority).
Every constant cites its brief §8 row.

Doctrine (brief §3/§4 - overrides ALL platform exit doctrine for this cohort):
  * Signal (rows 1-3, SOURCE-VERBATIM): the SIGN of the trailing 12-month return - no
    strength threshold, no IV/regime/event gate (rows 3/17). The 12 months are mechanized as
    252 trading-day closes from hub daily history (ADAPTED count of the published k=12),
    observed at the last close STRICTLY BEFORE the rebalance session (row 8 + §10 hygiene:
    signal from the prior close, execution next session - today's tape never enters the sign).
  * Direction (row 10, ADAPTED): sign > 0 -> long call; sign < 0 -> long put; exactly 0 is
    neither ("long if positive, short if negative") -> flat for the month.
  * Contract (rows 11-13, ADAPTED): listed expiry nearest 75 DTE inside [60, 90] calendar
    days; nearest-to-ATM strike among two-sided quotes (row 13's recorded delta target
    0.50 ± 0.05 is what nearest-ATM proxies; the solved delta is journaled on the leg for the
    §7-#5 IV-crush diagnostics - a delta gate would be invented doctrine, so there is none).
  * Cadence (rows 5/6/8/9): monthly, h=1. Enter ONLY on the first trading session of the
    month, 15:30-15:55 ET (row 9, PLATFORM-POLICY). Every other session scans to [].
  * Exit (§4, rows 14-16): the ONLY exit is the monthly re-formation - at the next monthly
    rebalance the position is closed WHETHER OR NOT the sign flipped (rule
    "monthly_rebalance_flip" when it flipped, "monthly_rebalance_roll" when it did not) and
    the same session's scan re-enters fresh 60-90 DTE per the new sign. NO profit target
    (row 15), NO stop (row 16), NO intra-month exit of any kind, NO DTE-floor rule (none
    published - the monthly roll exits at ~30-60 DTE by construction; the expiry-day backstop
    is the runner's global rail, not strategy doctrine, hence settle_at_expiry=False).
    Mechanization of "close at the rebalance": an on-time close fires inside the row-9
    execution window on the rebalance day; a MISSED rebalance (runner outage) closes at the
    first later manage() tick, stamped late=True - re-entry still waits for the next monthly
    rebalance (the source reads signals monthly; there is no mid-month entry).
    Missing/short history at the rebalance -> HOLD, journaled (fail-safe: never close without
    a fresh sign to re-form from).

KNOWN DEVIATIONS, LOUD (platform data surface, not new doctrine - see brief rows 4 / §10):
  * Row 4's excess-return reference (12-mo total return MINUS the compounded 13-week T-bill)
    is OMITTED: the hub exposes no T-bill series, so the sign is computed on RAW total
    return. In a year where 0 < 12-mo return < T-bill return the published rule says short
    and this module says long. Revisit when a risk-free series lands in the hub.
  * §10 requires dividend-adjusted total returns; the hub's daily closes are used as-is. If
    the feed is not dividend-adjusted, high-dividend underlyings (IWM) can mis-sign in flat
    years - the brief's "silent bug" warning applies to the data plane feeding this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from atlas.options.session_calendar import is_trading_day

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")


@dataclass(frozen=True)
class TsmomParams:
    """Tunables + frozen doctrine records (everything else is code-level doctrine).
    lookback_days: row 1 k=12 months, mechanized as 252 trading days (ADAPTED count of the
    SOURCE-VERBATIM 12). entry window: row 9 PLATFORM-POLICY 15:30-15:55 ET on the first
    session of the month (source has no intraday convention). dte band: rows 11/12 (ADAPTED
    60-90 calendar); dte_target 75 = band midpoint (PLATFORM-POLICY 'nearest 75').
    history_days: brief §9 - >= 13 months of daily closes; 300 trading days covers the
    252+1 the sign needs with slack for listing gaps."""
    lookback_days: int = 252
    entry_minute_from: int = 930          # 15:30 ET
    entry_minute_to: int = 955            # exclusive; = 15:55 ET
    dte_entry_min: int = 60
    dte_entry_max: int = 90
    dte_target: int = 75
    history_days: int = 300


class TsmomLongOptions(Strategy):
    META = StrategyMeta(
        strategy_id="tsmom_long_options", version=1,
        name="MOP time-series momentum via 60-90 DTE long options, monthly re-formation",
        universe=UNIVERSE, dte_range=(55, 95),
        max_concurrent=9,                  # one position per symbol; close precedes reopen
        event_policy=EventPolicy.TRADE_THROUGH,       # rows 3/17: no gate of any kind
        grading_basis=GradingBasis.DEBIT,             # §10: capital-at-risk = debit paid
        defining_mechanism="directional_momentum",
        settle_at_expiry=False,                       # §4: hold-to-expiry never occurs
        scan_interval_s=600.0, mark_interval_s=600.0,  # monthly cadence; daily marks suffice (§10)
        expected_fires_per_20_sessions=9.0)           # §10: ~9 round trips per month
    params = TsmomParams()

    # -- rebalance-day math (rows 6/8/9) ------------------------------------
    @staticmethod
    def rebalance_day_of_month(today: date) -> date:
        """This month's rebalance date: the FIRST trading session of the month (row 9
        PLATFORM-POLICY mechanization of the source's monthly re-formation). Pure calendar
        math + is_trading_day."""
        d = today.replace(day=1)
        while not is_trading_day(d) and d.day < 7:
            d += timedelta(days=1)
        return d

    # -- signal (rows 1-4, 8; §10 hygiene) ----------------------------------
    def signal_direction(self, ctx, sym: str, today: date) -> dict | None:
        """Sign of the trailing lookback_days total return, observed at the last close
        STRICTLY BEFORE `today` (row 8: prior close; no lookahead). None = insufficient
        history (callers hold/skip - fail-safe). direction: +1 long call / -1 long put /
        0 flat (row 2: 'long if positive, short if negative' - zero is neither)."""
        bars = ctx.hub.daily_history(sym, days=self.params.history_days)
        cutoff = today.isoformat()
        closes = [(b.ts, b.close) for b in bars if b.ts < cutoff and (b.close or 0) > 0]
        closes.sort(key=lambda t: t[0])
        n = self.params.lookback_days
        if len(closes) < n + 1:
            return None
        obs_date, c_now = closes[-1]
        base_date, c_then = closes[-(n + 1)]
        r12 = c_now / c_then - 1.0
        direction = 1 if r12 > 0 else (-1 if r12 < 0 else 0)
        return {"direction": direction, "r12": round(r12, 6),
                "obs_date": obs_date, "base_date": base_date}

    # -- contract selection (rows 11-13) ------------------------------------
    def _pick_expiry(self, ctx, sym: str, today: date) -> tuple | None:
        """Listed expiration nearest dte_target inside [dte_entry_min, dte_entry_max]
        (rows 11/12; ties break to the shorter listing). None = nothing listed in band."""
        best = None
        for e in ctx.hub.expirations(sym):
            try:
                y, m, d = map(int, e.split("-"))
                dte = (date(y, m, d) - today).days
            except ValueError:
                continue
            if self.params.dte_entry_min <= dte <= self.params.dte_entry_max:
                key = (abs(dte - self.params.dte_target), dte)
                if best is None or key < best[0]:
                    best = (key, e, dte)
        return None if best is None else (best[1], best[2])

    # -- scan (rows 1-3, 6, 8-13, 20-21) ------------------------------------
    def scan(self, ctx) -> list:
        today = ctx.dt_et.date()
        if today != self.rebalance_day_of_month(today):
            return []                                  # row 6: the signal is read monthly only
        if not (self.params.entry_minute_from <= ctx.minute < self.params.entry_minute_to):
            return []                                  # row 9 execution window
        holding = {p.underlying for p in ctx.open_positions}   # one per symbol (row 20);
        out = []                                               # manage() frees it before reopen
        for sym in self.META.universe:
            if sym in holding:
                continue
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            sig = self.signal_direction(ctx, sym, today)
            if sig is None:
                if ctx.journal:
                    ctx.journal({"event": "tsmom_no_history", "symbol": sym,
                                 "day": str(today)})
                continue
            if sig["direction"] == 0:
                if ctx.journal:
                    ctx.journal({"event": "tsmom_zero_sign", "symbol": sym,
                                 "day": str(today)})
                continue
            opt_type = "call" if sig["direction"] > 0 else "put"    # row 10
            picked = self._pick_expiry(ctx, sym, today)
            if picked is None:
                if ctx.journal:
                    ctx.journal({"event": "tsmom_no_expiry", "symbol": sym,
                                 "day": str(today)})
                continue
            exp, dte = picked
            rows = [r for r in ctx.hub.chain(sym, exp)
                    if r.option_type == opt_type and (r.bid or 0) > 0 and (r.ask or 0) > 0]
            if not rows:
                if ctx.journal:
                    ctx.journal({"event": "tsmom_no_strike", "symbol": sym, "expiry": exp,
                                 "S_ref": round(S_ref, 4)})
                continue
            row = min(rows, key=lambda r: (abs(r.strike - S_ref), r.strike))   # row 13: ATM
            mid = (row.bid + row.ask) / 2.0
            g = ctx.hub.row_greeks(opt_type=opt_type, strike=row.strike, S=S_ref, mid=mid,
                                   dte_days=dte) or {}
            earn = ctx.earnings.get(sym) or {}
            risk_flags = []
            if earn and str(earn.get("date") or "") <= exp:
                risk_flags.append("holds_through_earnings")   # §7#6/§9: tag, never gate
            out.append(ProposedCombo(
                kind=f"tsmom_long_{opt_type}", underlying=sym,
                legs=[{"occ": row.symbol, "underlying": sym, "opt_type": opt_type,
                       "strike": row.strike, "expiry": exp, "side": +1, "qty": 1,
                       "nbbo": {"bid": row.bid, "ask": row.ask},
                       "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                       "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                       "theta_day": g.get("theta_day", 0.0)}],
                signal={"S_ref": round(S_ref, 4), "strike": row.strike, "expiry": exp,
                        "dte_days": dte, "debit_ask": row.ask,
                        "debit_pct_of_S": round(100.0 * row.ask / S_ref, 3),
                        "direction": sig["direction"], "r12": sig["r12"],
                        "obs_date": sig["obs_date"], "base_date": sig["base_date"],
                        "earnings": earn or None},
                risk_flags=risk_flags))
        return out

    # -- manage (§4, rows 14-16): the monthly re-formation is the ONLY exit --
    def manage(self, pos, ctx):
        """Close the whole position at the monthly rebalance whether or not the sign flipped
        (row 14); scan() re-enters per the fresh sign the same session. No profit target
        (row 15), no stop (row 16), no intra-month exit. On-time closes fire inside the
        row-9 window; an overdue position (missed rebalance) closes at the first later tick,
        stamped late. Missing history -> hold (never close without a sign to re-form from)."""
        today = ctx.dt_et.date()
        reb = self.rebalance_day_of_month(today)
        if today < reb:
            return None                                # month started on a non-session day
        if today == reb and not (self.params.entry_minute_from <= ctx.minute
                                 < self.params.entry_minute_to):
            return None                                # on-time close only inside the window
        opened = self._entry_date(pos)
        if opened is not None and opened >= reb:
            return None                                # opened at THIS rebalance: hold the month
        sig = self.signal_direction(ctx, pos.underlying, today)
        if sig is None:
            if ctx.journal:
                ctx.journal({"event": "tsmom_hold_no_history", "symbol": pos.underlying,
                             "day": str(today)})
            return None
        old_dir = self._position_direction(pos)
        flip = old_dir is not None and sig["direction"] != old_dir
        return ExitAction(
            action="close",
            rule="monthly_rebalance_flip" if flip else "monthly_rebalance_roll",
            state={"rebalance_day": str(reb), "late": today > reb,
                   "old_direction": old_dir, "new_direction": sig["direction"],
                   "r12": sig["r12"], "obs_date": sig["obs_date"]})

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _entry_date(pos) -> date | None:
        """Position open date from its entry_day stamp; None (treated as due for the roll,
        self-healing) when unparsable."""
        try:
            return date.fromisoformat(str(getattr(pos, "entry_day", "") or ""))
        except ValueError:
            return None

    @staticmethod
    def _position_direction(pos) -> int | None:
        """+1 held call / -1 held put (single-leg long combos by construction)."""
        for ls in getattr(pos, "legs", None) or []:
            ot = getattr(getattr(ls, "spec", ls), "opt_type", "")
            if ot == "call":
                return 1
            if ot == "put":
                return -1
        return None
