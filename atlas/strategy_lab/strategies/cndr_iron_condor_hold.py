"""cndr_iron_condor_hold - CNDR-style monthly 20-delta/5-delta iron condor, hold to expiry.

AUTHORITY: docs/strategies/briefs/cndr_iron_condor_hold.md (verified CORRECTED 2026-07-19,
two adversarial passes, zero invented constants). Provenance: Cboe S&P 500 Iron Condor
Index (CNDR) Methodology v4.1 (2025-12-12). Every constant below cites its brief row (§8).

Doctrine (brief §3/§4 - overrides ALL platform exit doctrine for this cohort):
  * UNCONDITIONAL monthly roll - no IV gate, no regime gate, no event filter (row 21,
    SOURCE-VERBATIM absence). Holds spanning earnings are tagged, never skipped (row 22).
  * Roll/entry date: the THIRD FRIDAY of each month; exchange-holiday third Friday ->
    preceding business day (row 12). Strikes are fixed before 11:00 a.m. ET and the
    position is deemed entered at 11:00 a.m. ET (row 15) -> entry window [10:45, 11:00)
    ET, ADAPTED minute bounds matching the brief §9 snapshot spec.
  * Structure (row 2, §1.1): SELL the OTM put and OTM call with delta closest to +/-0.20
    (rows 3/4); BUY the OTM put and OTM call with delta closest to +/-0.05 as wings
    (rows 5/6). Closest-to-target per leg (row 7); one unit per leg (row 23). Deltas come
    from hub-solved greeks (row 11, ADAPTED - Cboe's Black-formula IV input is
    unpublished, row 10).
  * Tenor: the NEXT month's standard third-Friday monthly ("1 month", row 13; monthlies
    only, never weeklies, row 14). A listed expiry farther than monthly_tolerance_days
    from the next third Friday is not the monthly (holiday-shifted listings pass).
  * Exit: HOLD TO EXPIRATION (row 18). No profit target (row 19), no stop (row 20), no
    intra-month management of any kind - manage() always returns None; settlement is the
    runner's intrinsic-at-close path (settle_at_expiry=True), the shadow analogue of the
    published SOQ cash settlement (row 17, ADAPTED AM->PM per brief §2).
  * Grading basis MAX_LOSS (row 27): worst payoff = max(call width, put width) x 100 -
    net credit - the per-spread form of §2.1's "Max (KCall_P5 - KCall_P20,
    KPut_N20 - KPut_N5)". payoff_analysis derives exactly this for the 4-leg condor.

LOCAL CONVENTIONS (logged loudly because the source is silent - brief row 8):
  * Strike tie-break: on equal |delta - target| pick the MORE OTM strike (calls: higher
    strike, puts: lower strike). Deterministic, ours, NOT published.
  * Candidate domain: OTM rows only (§1.1 "Out-of-the-Money", verbatim) with two-sided
    NBBO on all four legs; any leg failing vetoes the whole condor for the symbol-month
    (row 26). Wings are searched STRICTLY beyond their short strike - structural: the
    §2.1 worst-payoff formula presumes wings outside shorts, and on any sane chain the
    closest-to-5-delta strike lands there anyway; this only guards degenerate chains.
  * Universe ("SPY",): the faithful S&P 500 mapping of the published SPX claim (row 1 is
    ADAPTED; brief §2). The QQQ/IWM core-tier siblings and the mega-cap extension tier
    are graded separately per §2 and would be a later version/cohort fork.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from atlas.options.session_calendar import is_trading_day

from ..strategy import (EventPolicy, GradingBasis, ProposedCombo, Strategy, StrategyMeta)

UNIVERSE = ("SPY",)


@dataclass(frozen=True)
class CndrParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    short_delta: rows 3/4 '"Option with delta closest to 0.20." / "closest to -0.20."'
    (SOURCE-VERBATIM, absolute-value form). wing_delta: rows 5/6, same wording at 0.05.
    entry window: row 15 'strikes ... selected before 11 a.m. ET' / 'deemed purchased and
    sold (11:00 a.m. ET)' - ADAPTED minute bounds; §9 pins the 10:45-11:00 ET snapshot.
    dte bounds: row 13 '1 month' (~28-35 calendar days), widened as listing/holiday
    tolerance (PLATFORM-POLICY); META.dte_range mirrors them for chain requests.
    monthly_tolerance_days: row 14 third-Friday-cycle pin - max |listed expiry - next
    third Friday|; holiday-shifted monthlies pass, weeklies never (PLATFORM-POLICY)."""
    short_delta: float = 0.20
    wing_delta: float = 0.05
    entry_minute_from: int = 645          # 10:45 ET
    entry_minute_to: int = 660            # exclusive; = 11:00 ET, the deemed-entry stamp
    dte_min_days: int = 21
    dte_max_days: int = 40
    monthly_tolerance_days: int = 3


class CndrIronCondorHold(Strategy):
    META = StrategyMeta(
        strategy_id="cndr_iron_condor_hold", version=1,
        name="CNDR-style monthly 20-delta/5-delta iron condor, hold to expiry",
        universe=UNIVERSE, dte_range=(21, 40),
        max_concurrent=2,                  # 1 underlying x (settling old + fresh new) on roll day
        event_policy=EventPolicy.TRADE_THROUGH,        # row 21: unconditional monthly entry
        grading_basis=GradingBasis.MAX_LOSS,           # row 27: max(width) x 100 - net credit
        defining_mechanism="short_vol_carry",
        settle_at_expiry=True,                         # row 18: hold to expiry, intrinsic settle
        scan_interval_s=300.0, mark_interval_s=600.0,  # row 25 daily-EOD doctrine; marks diagnostic
        expected_fires_per_20_sessions=1.5)            # ~1 condor/month (§10, SPY tier)
    params = CndrParams()

    # -- roll-day math (row 12) --------------------------------------------
    @staticmethod
    def third_friday(year: int, month: int) -> date:
        """Third Friday of a calendar month (always the 15th-21st). Pure."""
        d15 = date(year, month, 15)
        return d15 + timedelta(days=(4 - d15.weekday()) % 7)

    @classmethod
    def roll_date_of_month(cls, today: date) -> date:
        """This month's roll date: the third Friday, or the preceding business day when
        that Friday is an exchange holiday (row 12). Calendar math + is_trading_day."""
        d = cls.third_friday(today.year, today.month)
        limit = d - timedelta(days=4)
        while not is_trading_day(d) and d > limit:
            d -= timedelta(days=1)
        return d

    # -- tenor (rows 13/14) ------------------------------------------------
    def _monthly_expiry(self, ctx, sym: str, today: date) -> str | None:
        """The NEXT month's standard monthly listing: nearest listed expiry to next
        month's third Friday, inside the dte bounds and the third-Friday-cycle tolerance.
        None = no monthly listed (veto). Equidistant listings: earlier date wins."""
        ny, nm = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        target = self.third_friday(ny, nm)
        best = None                        # (offset_days, expiry_date, iso_string)
        for e in ctx.hub.expirations(sym):
            try:
                ed = date.fromisoformat(str(e))
            except ValueError:
                continue
            dte = (ed - today).days
            if not (self.params.dte_min_days <= dte <= self.params.dte_max_days):
                continue
            off = abs((ed - target).days)
            if off > self.params.monthly_tolerance_days:
                continue                   # weekly / off-cycle: never the monthly (row 14)
            if best is None or (off, ed) < best[:2]:
                best = (off, ed, str(e))
        return best[2] if best else None

    # -- strike selection (rows 3-8, §1.1 OTM) -----------------------------
    def _candidates(self, ctx, rows: list, opt_type: str, S_ref: float, dte: int) -> list:
        """OTM, two-sided rows of one type with hub-solved greeks: [(row, greeks, |delta|)].
        Rows the solver cannot price (row_greeks None) drop out."""
        out = []
        for r in rows:
            if r.option_type != opt_type:
                continue
            if opt_type == "call" and not r.strike > S_ref:
                continue                   # §1.1: OTM only (row 2)
            if opt_type == "put" and not r.strike < S_ref:
                continue
            if not ((r.bid or 0) > 0 and (r.ask or 0) > 0):
                continue                   # row 26: two-sided NBBO per leg
            mid = (r.bid + r.ask) / 2.0
            g = ctx.hub.row_greeks(opt_type=opt_type, strike=r.strike, S=S_ref, mid=mid,
                                   dte_days=dte)
            if not g:
                continue
            out.append((r, g, abs(float(g.get("delta") or 0.0))))
        return out

    def _pick(self, cands: list, target: float, opt_type: str, *,
              beyond: float | None = None):
        """The candidate with |delta| closest to target (row 7). `beyond` restricts wing
        legs STRICTLY outside their short strike. Tie-break: more OTM (row 8 - UNKNOWN in
        the source; deterministic local convention, calls higher / puts lower)."""
        if beyond is not None:
            cands = [c for c in cands
                     if (c[0].strike > beyond if opt_type == "call" else c[0].strike < beyond)]
        if not cands:
            return None
        otm = (lambda c: -c[0].strike) if opt_type == "call" else (lambda c: c[0].strike)
        return min(cands, key=lambda c: (abs(c[2] - target), otm(c)))

    @staticmethod
    def _leg(sym: str, exp: str, cand: tuple, side: int) -> dict:
        r, g, _ = cand
        return {"occ": r.symbol, "underlying": sym, "opt_type": r.option_type,
                "strike": r.strike, "expiry": exp, "side": side, "qty": 1,   # row 23: one unit
                "nbbo": {"bid": r.bid, "ask": r.ask},
                "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                "theta_day": g.get("theta_day", 0.0)}

    # -- scan (rows 2-16, 21-23) --------------------------------------------
    def scan(self, ctx) -> list:
        today = ctx.dt_et.date()
        if today != self.roll_date_of_month(today):
            return []                                  # row 12: roll dates only
        if not (self.params.entry_minute_from <= ctx.minute < self.params.entry_minute_to):
            return []                                  # row 15: before-11:00 window
        holding = {p.underlying for p in ctx.open_positions
                   if p.nearest_expiry > today}        # this cycle's condor already on;
        out = []                                       # one expiring TODAY never blocks (§10)
        for sym in self.META.universe:
            if sym in holding:
                continue
            S_ref = ctx.hub.ref_price(sym)
            if S_ref <= 0:
                continue
            exp = self._monthly_expiry(ctx, sym, today)
            if exp is None:
                if ctx.journal:
                    ctx.journal({"event": "cndr_no_expiry", "symbol": sym, "day": str(today)})
                continue
            rows = ctx.hub.chain(sym, exp)
            dte = max(1, (date.fromisoformat(exp) - today).days)
            calls = self._candidates(ctx, rows, "call", S_ref, dte)
            puts = self._candidates(ctx, rows, "put", S_ref, dte)
            sc = self._pick(calls, self.params.short_delta, "call")
            sp = self._pick(puts, self.params.short_delta, "put")
            lc = self._pick(calls, self.params.wing_delta, "call",
                            beyond=sc[0].strike) if sc else None
            lp = self._pick(puts, self.params.wing_delta, "put",
                            beyond=sp[0].strike) if sp else None
            if not (sc and sp and lc and lp):
                if ctx.journal:
                    missing = [n for n, c in (("short_call", sc), ("short_put", sp),
                                              ("long_call", lc), ("long_put", lp)) if c is None]
                    ctx.journal({"event": "cndr_no_strikes", "symbol": sym, "expiry": exp,
                                 "missing": missing, "S_ref": round(S_ref, 4)})
                continue                               # row 26: one bad leg vetoes the condor
            legs = [self._leg(sym, exp, lp, +1), self._leg(sym, exp, sp, -1),
                    self._leg(sym, exp, sc, -1), self._leg(sym, exp, lc, +1)]
            mids = {k: (c[0].bid + c[0].ask) / 2.0
                    for k, c in (("lp", lp), ("sp", sp), ("sc", sc), ("lc", lc))}
            credit_mid = mids["sp"] + mids["sc"] - mids["lp"] - mids["lc"]   # row 16: mid fills
            credit_nat = sp[0].bid + sc[0].bid - lp[0].ask - lc[0].ask
            width_put = sp[0].strike - lp[0].strike
            width_call = lc[0].strike - sc[0].strike
            earn = ctx.earnings.get(sym) or {}
            risk_flags = []
            if earn and str(earn.get("date") or "") <= exp:
                risk_flags.append("holds_through_earnings")    # row 22: flag, never skip
            out.append(ProposedCombo(
                kind="iron_condor", underlying=sym, legs=legs,
                signal={"S_ref": round(S_ref, 4), "expiry": exp, "dte_days": dte,
                        "strikes": {"long_put": lp[0].strike, "short_put": sp[0].strike,
                                    "short_call": sc[0].strike, "long_call": lc[0].strike},
                        "deltas": {"long_put": lp[1].get("delta"), "short_put": sp[1].get("delta"),
                                   "short_call": sc[1].get("delta"), "long_call": lc[1].get("delta")},
                        "credit_mid": round(credit_mid, 4), "credit_natural": round(credit_nat, 4),
                        "width_put": round(width_put, 4), "width_call": round(width_call, 4),
                        "max_width": round(max(width_put, width_call), 4),  # row 27 CaR input
                        "earnings": earn or None},
                risk_flags=risk_flags))
        return out

    # -- manage (rows 18-20): hold to expiration, full stop ------------------
    def manage(self, pos, ctx):
        return None
