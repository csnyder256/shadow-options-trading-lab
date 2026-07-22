"""gap_fade_bull_put - opening gap-down fade expressed as a 0-5 DTE bull put credit spread.

AUTHORITY: docs/strategies/briefs/gap_fade_bull_put.md (verified CONFIRMED 2026-07-19, zero
invented constants). Provenance: Dahlquist & Bauer 2011 Dow Award paper (multi-day horizon
evidence); MyPivots "Fading the Gap" (opening-gap definition, fill base rates); TradeThatSwing
/ Cory Mitchell (gap-size fill buckets, 15-min-range entry, prior-close target). The OPTIONS
EXPRESSION IS ENTIRELY ADAPTED (brief §2 loud notice): no cited source trades options - every
option-leg constant is ADAPTED/PLATFORM-POLICY and must never be attributed to the authors.
The TTS gap band is SPY-only; applying it to the mega-cap tier is likewise ADAPTED (brief §8
UNKNOWN single_name_gap_band). Every constant below cites its brief §8 row.

Doctrine (brief §3/§4 - §4 OVERRIDES the platform exit ladder for this cohort):
  * Trigger (rows 1-4): opening gap DOWN, underlying still 0.20-0.40% below the prior RTH
    close. The lab hub exposes no 1-min bars, so the gap is re-measured live as ref_price vs
    prior daily close at scan time (ADAPTED simplification - the spread is only sold while
    the fill remains unrealized), and the published 15-min opening-range breakout
    confirmation (rows 5-6) is approximated by the entry window OPENING at 09:45 ET, the
    earliest minute the published confirmation could fire. Cutoff 11:30 ET (row 7).
  * Structure (rows 8-13): bull put spread, 1 spread. Short put = highest live-quoted strike
    with |delta| <= 0.35 (row 10 ceiling - the no-bars proxy for the row-9 opening-range-low
    shelf); long put 1 listed live strike below (row 11); worst-ledger (short bid - long ask)
    credit >= 15% of width or no trade (row 12); nearest expiry 0-5 calendar DTE (row 13 - 
    single-name grids make the nearest listed <=5 the weekly automatically).
  * One spread per underlying per day (rows 17/25): an open spread occupies the underlying,
    and any open position with entry_day == today blocks re-entry. Never roll (row 17).
  * Earnings gate (row 22): single names skip when earnings fall in [entry day, expiry].
  * Exits (§4): gap-fill profit target - underlying trades AT/ABOVE the prior RTH close ->
    close (rule gap_filled, row 14); thesis-dead stop - underlying strictly BELOW the
    short-strike shelf -> close (rule fade_thesis_dead, row 15 - the brief itself identifies
    the opening-range low with "our short-strike shelf"); expiry-day 15:30 ET force-close
    when the short strike is ITM or within 0.25% of spot (rule expiry_itm_force_close,
    row 16); otherwise HOLD. Missing quotes -> hold. settle_at_expiry=False: the platform
    expiry backstop is the final rail (an OTM spread's near-zero buyback approximates the
    row-16 expire-worthless branch on a shadow platform).
  * Macro events: EventPolicy.BLACKOUT - PLATFORM-POLICY tightening of brief row 23 (the
    brief logs FOMC/CPI mornings observe-only; the platform does not fade a gap into a macro
    release window). The runner suppresses scan() during blackouts; scan() re-checks
    ctx.in_blackout defensively.
  * Covariates logged, never gated: day-of-week (row 19) and ref vs 30-day MA (row 21). The
    row-20 intraday relative-volume covariate needs volume-so-far the hub does not expose - 
    omitted, recorded here so nobody later "remembers" it as implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

UNIVERSE = ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")


@dataclass(frozen=True)
class GapFadeParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    gap_min_pct: row 3 ADAPTED - 0.20% lower bound at the TTS bucket boundary (sub-0.2% gaps
      fill most often but carry no fadeable premium). gap_max_pct: row 4 SOURCE-RANGE - the
      published >0.4% fade-failure zone starts above. entry_minute_from: rows 5/6 - 09:45 ET,
      the 15-min opening range complete (breakout confirmation approximated by the window
      start; the hub has no 1-min bars - ADAPTED). entry_minute_to: row 7 ADAPTED - 11:30 ET
      cutoff, exclusive bound ('no later than 11:30'). dte_min/max_days: row 13 ADAPTED - 
      0-5 calendar DTE, 0DTE where listed. short_delta_cap: row 10 PLATFORM-POLICY - 0.35
      ceiling, the no-bars proxy for the row-9 opening-range-low shelf. width_strikes:
      row 11 PLATFORM-POLICY - 1 listed live strike below the short (the 1-2 band default).
      credit_floor_frac: row 12 PLATFORM-POLICY - worst-ledger credit >= 15% of width.
      expiry_force_minute / expiry_buffer_pct: row 16 ADAPTED - 15:30 ET expiry-day check,
      'ITM or within 0.25% of spot' force-close band."""
    gap_min_pct: float = 0.20
    gap_max_pct: float = 0.40
    entry_minute_from: int = 585          # 09:45 ET
    entry_minute_to: int = 690            # exclusive; = 11:30 ET
    dte_min_days: int = 0
    dte_max_days: int = 5
    short_delta_cap: float = 0.35
    width_strikes: int = 1
    credit_floor_frac: float = 0.15
    expiry_force_minute: int = 930        # 15:30 ET
    expiry_buffer_pct: float = 0.25


class GapFadeBullPut(Strategy):
    META = StrategyMeta(
        strategy_id="gap_fade_bull_put", version=1,
        name="Opening gap-down fade via bull put credit spread, 0-5 DTE",
        universe=UNIVERSE, dte_range=(0, 6),
        max_concurrent=3,                             # correlated-morning cap (brief §7)
        event_policy=EventPolicy.BLACKOUT,            # never fade a gap into a macro window
        grading_basis=GradingBasis.MAX_LOSS,          # width - credit (brief §10 CaR basis)
        defining_mechanism="directional_mean_reversion",
        settle_at_expiry=False,                       # platform backstop covers expiry day
        scan_interval_s=60.0, mark_interval_s=120.0,
        expected_fires_per_20_sessions=10.0)          # ~10/month estimate (brief §10)
    params = GapFadeParams()

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _journal(ctx, rec: dict) -> None:
        if ctx.journal:
            ctx.journal(rec)

    def _next_expiry(self, ctx, sym: str, today: date) -> str | None:
        """Nearest listed expiration 0-5 calendar DTE out (row 13); None = nothing in band."""
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

    @staticmethod
    def _prior_bars(ctx, sym: str) -> list:
        """Daily bars strictly BEFORE today (rows 1-2: prior RTH close; today's partial
        daily bar, when the vendor includes it, must never be the gap reference)."""
        return [b for b in ctx.hub.daily_history(sym, days=45)
                if str(getattr(b, "ts", ""))[:10] < ctx.day]

    # -- scan (rows 1-13, 17, 22-25) ---------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        if ctx.in_blackout:                           # defensive re-check of the META rail
            return []
        if not (p.entry_minute_from <= ctx.minute < p.entry_minute_to):
            return []
        today = ctx.dt_et.date()
        blocked = {q.underlying for q in ctx.open_positions}          # occupied (row 17)
        blocked |= {q.underlying for q in ctx.open_positions
                    if getattr(q, "entry_day", "") == ctx.day}        # one per day (row 25)
        out = []
        for sym in self.META.universe:
            if sym in blocked:
                continue
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            prior = self._prior_bars(ctx, sym)
            prior_close = float(prior[-1].close) if prior else 0.0
            if prior_close <= 0:
                self._journal(ctx, {"event": "gap_fade_no_prior_close", "symbol": sym,
                                    "day": ctx.day})
                continue
            gap_pct = round((S_ref / prior_close - 1.0) * 100.0, 4)
            if not (p.gap_min_pct <= -gap_pct <= p.gap_max_pct):
                continue                              # not a fadeable gap-down (rows 2-4)
            exp = self._next_expiry(ctx, sym, today)
            if exp is None:
                self._journal(ctx, {"event": "gap_fade_no_expiry", "symbol": sym})
                continue
            earn = ctx.earnings.get(sym) or {}
            e_date = str(earn.get("date") or "")
            if e_date and ctx.day <= e_date <= exp:   # row 22: skip, never hold the print
                self._journal(ctx, {"event": "gap_fade_earnings_gate", "symbol": sym,
                                    "earnings": e_date, "expiry": exp})
                continue
            dte = (date.fromisoformat(exp) - today).days
            puts = sorted((r for r in ctx.hub.chain(sym, exp)
                           if r.option_type == "put" and r.strike < S_ref
                           and (r.bid or 0) > 0 and (r.ask or 0) > 0),
                          key=lambda r: r.strike, reverse=True)
            short_row, short_g, short_i = None, None, -1
            for i, r in enumerate(puts):              # highest strike under the delta ceiling
                g = ctx.hub.row_greeks(opt_type="put", strike=r.strike, S=S_ref,
                                       mid=(r.bid + r.ask) / 2.0, dte_days=dte)
                if g and abs(g.get("delta", 0.0)) <= p.short_delta_cap:
                    short_row, short_g, short_i = r, g, i
                    break
            if short_row is None:
                self._journal(ctx, {"event": "gap_fade_no_short_strike", "symbol": sym,
                                    "expiry": exp, "S_ref": round(S_ref, 4)})
                continue
            below = puts[short_i + 1:]
            if len(below) < p.width_strikes:
                self._journal(ctx, {"event": "gap_fade_no_long_strike", "symbol": sym,
                                    "expiry": exp, "short_strike": short_row.strike})
                continue
            long_row = below[p.width_strikes - 1]     # row 11: 1 listed live strike below
            width = round(short_row.strike - long_row.strike, 4)
            credit_worst = round(short_row.bid - long_row.ask, 4)
            if width <= 0 or credit_worst < p.credit_floor_frac * width:
                self._journal(ctx, {"event": "gap_fade_credit_floor", "symbol": sym,
                                    "credit_worst": credit_worst, "width": width})
                continue
            long_g = ctx.hub.row_greeks(opt_type="put", strike=long_row.strike, S=S_ref,
                                        mid=(long_row.bid + long_row.ask) / 2.0,
                                        dte_days=dte) or {}
            credit_mid = round((short_row.bid + short_row.ask) / 2.0
                               - (long_row.bid + long_row.ask) / 2.0, 4)
            closes = [float(b.close) for b in prior[-30:]]
            ma30 = round(sum(closes) / 30.0, 4) if len(closes) >= 30 else None
            out.append(ProposedCombo(
                kind="bull_put_spread", underlying=sym,
                legs=[{"occ": short_row.symbol, "underlying": sym, "opt_type": "put",
                       "strike": short_row.strike, "expiry": exp, "side": -1, "qty": 1,
                       "nbbo": {"bid": short_row.bid, "ask": short_row.ask},
                       "iv": short_g.get("iv", 0.0), "delta": short_g.get("delta", 0.0),
                       "gamma": short_g.get("gamma", 0.0), "vega": short_g.get("vega", 0.0),
                       "theta_day": short_g.get("theta_day", 0.0)},
                      {"occ": long_row.symbol, "underlying": sym, "opt_type": "put",
                       "strike": long_row.strike, "expiry": exp, "side": +1, "qty": 1,
                       "nbbo": {"bid": long_row.bid, "ask": long_row.ask},
                       "iv": long_g.get("iv", 0.0), "delta": long_g.get("delta", 0.0),
                       "gamma": long_g.get("gamma", 0.0), "vega": long_g.get("vega", 0.0),
                       "theta_day": long_g.get("theta_day", 0.0)}],
                signal={"gap_pct": gap_pct, "prior_close": round(prior_close, 4),
                        "S_ref": round(S_ref, 4), "expiry": exp, "dte_days": dte,
                        "short_strike": short_row.strike, "long_strike": long_row.strike,
                        "width": width, "credit_worst": credit_worst,
                        "credit_mid": credit_mid,
                        "credit_frac_of_width": round(credit_worst / width, 4),
                        "dow": ctx.dt_et.strftime("%A"),                    # row 19, log-only
                        "ma30": ma30,                                       # row 21, log-only
                        "above_ma30": (S_ref > ma30) if ma30 else None,
                        "notes": {"prior_close": round(prior_close, 4),    # -> pos.notes
                                  "stop_level": short_row.strike,          # the shelf (row 15)
                                  "gap_pct": gap_pct}}))
        return out

    # -- manage (§4 rows 14-17; overrides platform doctrine) ---------------
    def manage(self, pos, ctx) -> ExitAction | None:
        p = self.params
        hub = getattr(ctx, "hub", None)
        S = hub.ref_price(pos.underlying) if hub else 0.0
        if S <= 0:
            return None                               # missing quote -> hold
        notes = getattr(pos, "notes", None) or {}
        prior_close = float(notes.get("prior_close") or 0.0)
        stop_level = float(notes.get("stop_level") or 0.0)
        if prior_close > 0 and S >= prior_close:      # row 14: gap filled - target touched
            return ExitAction(action="close", rule="gap_filled",
                              state={"S": round(S, 4), "target": prior_close})
        if stop_level > 0 and S < stop_level:         # row 15: back below the shelf
            return ExitAction(action="close", rule="fade_thesis_dead",
                              state={"S": round(S, 4), "stop": stop_level})
        if pos.nearest_expiry <= ctx.dt_et.date() and ctx.minute >= p.expiry_force_minute:
            short_k = max((ls.spec.strike for ls in pos.legs if ls.spec.side < 0),
                          default=0.0)
            if short_k > 0 and short_k >= S * (1.0 - p.expiry_buffer_pct / 100.0):
                return ExitAction(action="close", rule="expiry_itm_force_close",
                                  state={"S": round(S, 4), "short_strike": short_k,
                                         "minute": ctx.minute})            # row 16
        return None                                   # §4.3 HOLD; platform backstop = final rail
