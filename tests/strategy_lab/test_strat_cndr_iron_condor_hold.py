"""cndr_iron_condor_hold vs its verified brief (docs/strategies/briefs/cndr_iron_condor_hold.md).
Each test cites the brief row it pins. Fake hub with INJECTED per-strike deltas (the module
selects strikes purely through hub.row_greeks, so injecting deltas hand-solves the chain);
no network. Dates: third Friday July 2026 = 2026-07-17; next monthly = 2026-08-21 (35 DTE)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

import atlas.strategy_lab.strategies.cndr_iron_condor_hold as cndr_mod
from atlas.strategy_lab.strategies.cndr_iron_condor_hold import CndrIronCondorHold
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")
ROLL = datetime(2026, 7, 17, 10, 50, tzinfo=NY)     # third Friday July 2026, 10:50 ET
S_REF = 630.40


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float


class FakeHub:
    """Chain/expirations fake + injected signed deltas keyed (opt_type, strike).
    row_greeks mirrors MarketHub.row_greeks' keyword-only signature; None = unsolvable."""

    def __init__(self):
        self.chains = {}
        self.refs = {"SPY": S_REF}
        self.exps = ["2026-07-17", "2026-07-24", "2026-08-07", "2026-08-21", "2026-09-18"]
        self.deltas = {}

    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)

    def expirations(self, sym, **kw):
        return self.exps

    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])

    def row_greeks(self, *, opt_type, strike, S, mid, dte_days, r=0.04):
        d = self.deltas.get((opt_type, strike))
        if d is None:
            return None
        return {"iv": 0.18, "delta": d, "gamma": 0.01, "vega": 0.4, "theta_day": -0.05}


def _ctx(dt, hub, open_positions=(), earnings=None, journal=None):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=960, hub=hub,
                           earnings=earnings or {}, journal=journal,
                           open_positions=list(open_positions))


def _happy_hub():
    """Hand-solved SPY chain for 2026-08-21. Targets: short put 605 (-0.19), long put 580
    (-0.048), short call 655 (+0.21), long call 680 (+0.052). Traps: ITM rows with EXACT
    target deltas (put 635, call 625) and a one-sided call (656, exact 0.20) - each would
    WIN if its gate (OTM / two-sided NBBO) were broken."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-08-21")] = [
        Row("SPY_P570", "put", 570.0, 0.55, 0.65), Row("SPY_P580", "put", 580.0, 1.05, 1.15),
        Row("SPY_P590", "put", 590.0, 2.00, 2.16), Row("SPY_P600", "put", 600.0, 3.30, 3.50),
        Row("SPY_P605", "put", 605.0, 4.20, 4.40), Row("SPY_P610", "put", 610.0, 5.30, 5.50),
        Row("SPY_P635", "put", 635.0, 12.00, 12.40),          # ITM trap (strike > S_ref)
        Row("SPY_C625", "call", 625.0, 9.00, 9.40),           # ITM trap (strike < S_ref)
        Row("SPY_C645", "call", 645.0, 5.10, 5.30), Row("SPY_C655", "call", 655.0, 3.20, 3.36),
        Row("SPY_C656", "call", 656.0, 0.0, 3.00),            # one-sided trap (no bid)
        Row("SPY_C660", "call", 660.0, 2.10, 2.26), Row("SPY_C670", "call", 670.0, 1.00, 1.10),
        Row("SPY_C680", "call", 680.0, 0.50, 0.60), Row("SPY_C690", "call", 690.0, 0.22, 0.30)]
    hub.deltas = {
        ("put", 570.0): -0.028, ("put", 580.0): -0.048, ("put", 590.0): -0.08,
        ("put", 600.0): -0.15, ("put", 605.0): -0.19, ("put", 610.0): -0.26,
        ("put", 635.0): -0.20,                                # exact target - must be excluded
        ("call", 625.0): 0.20, ("call", 656.0): 0.20,         # exact targets - must be excluded
        ("call", 645.0): 0.30, ("call", 655.0): 0.21, ("call", 660.0): 0.16,
        ("call", 670.0): 0.09, ("call", 680.0): 0.052, ("call", 690.0): 0.03}
    return hub


def test_roll_gating_third_friday_and_entry_window():
    """Rows 12/15: fires ONLY on the third Friday, inside the [10:45, 11:00) ET window."""
    hub = _happy_hub()
    s = CndrIronCondorHold()
    assert len(s.scan(_ctx(ROLL, hub))) == 1
    assert s.scan(_ctx(datetime(2026, 7, 10, 10, 50, tzinfo=NY), hub)) == []   # 2nd Friday
    assert s.scan(_ctx(datetime(2026, 7, 24, 10, 50, tzinfo=NY), hub)) == []   # 4th Friday
    assert s.scan(_ctx(datetime(2026, 7, 16, 10, 50, tzinfo=NY), hub)) == []   # Thursday
    assert s.scan(_ctx(ROLL.replace(hour=10, minute=30), hub)) == []           # before 10:45
    assert s.scan(_ctx(ROLL.replace(hour=11, minute=0), hub)) == []            # 11:00 exclusive
    assert s.scan(_ctx(ROLL.replace(hour=14, minute=0), hub)) == []


def test_holiday_third_friday_rolls_to_preceding_business_day(monkeypatch):
    """Row 12: 'Should the third Friday fall on an exchange holiday, the roll date is the
    preceding Business Day.'"""
    monkeypatch.setattr(cndr_mod, "is_trading_day", lambda d, **kw: d != date(2026, 7, 17))
    hub = _happy_hub()
    s = CndrIronCondorHold()
    assert s.roll_date_of_month(date(2026, 7, 16)) == date(2026, 7, 16)
    thu = datetime(2026, 7, 16, 10, 50, tzinfo=NY)
    assert [p.underlying for p in s.scan(_ctx(thu, hub))] == ["SPY"]   # Thursday IS the roll
    assert s.scan(_ctx(ROLL, hub)) == []                              # holiday Friday is not


def test_four_leg_delta_targeting_monthly_tenor_and_gates():
    """Rows 2-7: 4 legs at closest-to-target deltas; rows 13/14: the third-Friday monthly
    (2026-08-21) beats the in-DTE-range 2026-08-07 weekly; §1.1 OTM + row 26 two-sided
    gates exclude the exact-delta traps; row 23: one unit per leg; §1.1: net credit."""
    hub = _happy_hub()
    s = CndrIronCondorHold()
    props = s.scan(_ctx(ROLL, hub))
    assert len(props) == 1
    p = props[0]
    assert p.kind == "iron_condor" and p.underlying == "SPY" and p.contracts == 1
    assert len(p.legs) == 4
    by = {(l["opt_type"], l["side"]): l for l in p.legs}
    assert len(by) == 4                                   # one leg per (type, side)
    sp, lp = by[("put", -1)], by[("put", 1)]
    sc, lc = by[("call", -1)], by[("call", 1)]
    assert sp["strike"] == 605.0        # |-0.19| nearest 0.20 (ITM 635 exact-0.20 excluded)
    assert lp["strike"] == 580.0        # |-0.048| nearest 0.05 below the short put
    assert sc["strike"] == 655.0        # 0.21 nearest 0.20 (ITM 625 + one-sided 656 excluded)
    assert lc["strike"] == 680.0        # 0.052 nearest 0.05 above the short call
    for l in p.legs:
        assert l["expiry"] == "2026-08-21"                # monthly tenor, never the weekly
        assert l["qty"] == 1
        assert l["nbbo"]["bid"] > 0 and l["nbbo"]["ask"] > 0
    assert sp["delta"] < 0 and lp["delta"] < 0 and sc["delta"] > 0 and lc["delta"] > 0
    assert p.signal["dte_days"] == 35
    assert p.signal["credit_mid"] == pytest.approx(5.93)  # 4.30 + 3.28 - 1.10 - 0.55
    assert p.signal["credit_mid"] > 0                     # net-credit structure
    assert p.signal["max_width"] == 25.0                  # row 27 CaR input: max(25, 25)


def test_wings_strictly_outside_shorts():
    """§2.1 payoff structure: wings sit OUTSIDE the shorts. A globally-closest-to-5-delta
    strike INSIDE the short strike must be passed over for the best strike beyond it."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-08-21")] = [
        Row("SPY_P580", "put", 580.0, 0.90, 1.00), Row("SPY_P590", "put", 590.0, 1.60, 1.72),
        Row("SPY_P600", "put", 600.0, 2.80, 3.00), Row("SPY_P605", "put", 605.0, 4.20, 4.40),
        Row("SPY_P610", "put", 610.0, 5.30, 5.50),
        Row("SPY_C645", "call", 645.0, 5.10, 5.30), Row("SPY_C650", "call", 650.0, 4.00, 4.20),
        Row("SPY_C655", "call", 655.0, 3.20, 3.36), Row("SPY_C660", "call", 660.0, 2.10, 2.26),
        Row("SPY_C670", "call", 670.0, 1.00, 1.10)]
    hub.deltas = {
        ("put", 610.0): -0.05,          # exact wing target but ABOVE the short put - inside
        ("put", 605.0): -0.19, ("put", 600.0): -0.09, ("put", 590.0): -0.048,
        ("put", 580.0): -0.03,
        ("call", 650.0): 0.05,          # exact wing target but BELOW the short call - inside
        ("call", 645.0): 0.30, ("call", 655.0): 0.21, ("call", 660.0): 0.16,
        ("call", 670.0): 0.052}
    s = CndrIronCondorHold()
    props = s.scan(_ctx(ROLL, hub))
    assert len(props) == 1
    by = {(l["opt_type"], l["side"]): l for l in props[0].legs}
    assert by[("call", -1)]["strike"] == 655.0
    assert by[("call", 1)]["strike"] == 670.0             # NOT 650 (inside); best beyond 655
    assert by[("put", -1)]["strike"] == 605.0
    assert by[("put", 1)]["strike"] == 590.0              # NOT 610 (inside); best below 605
    assert by[("call", 1)]["strike"] > by[("call", -1)]["strike"]
    assert by[("put", 1)]["strike"] < by[("put", -1)]["strike"]


def test_no_wing_beyond_short_vetoes_whole_condor():
    """Row 26: a leg failing selection vetoes the whole condor - no naked-ish 3-leg entry."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-08-21")] = [
        Row("SPY_P580", "put", 580.0, 0.90, 1.00), Row("SPY_P605", "put", 605.0, 4.20, 4.40),
        Row("SPY_C645", "call", 645.0, 5.10, 5.30), Row("SPY_C655", "call", 655.0, 3.20, 3.36)]
    hub.deltas = {("put", 605.0): -0.19, ("put", 580.0): -0.048,
                  ("call", 645.0): 0.30, ("call", 655.0): 0.21}   # nothing beyond 655
    s = CndrIronCondorHold()
    events = []
    assert s.scan(_ctx(ROLL, hub, journal=events.append)) == []
    assert any(e["event"] == "cndr_no_strikes" and e["missing"] == ["long_call"]
               for e in events)


def test_strike_tiebreak_prefers_more_otm():
    """Row 8: tie-break UNKNOWN in the source - pinned local convention: on equal
    |delta - target| take the more OTM strike (calls higher, puts lower). Exact float
    ties via identical injected deltas at two strikes."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-08-21")] = [
        Row("SPY_P580", "put", 580.0, 0.90, 1.00), Row("SPY_P600", "put", 600.0, 2.80, 3.00),
        Row("SPY_P610", "put", 610.0, 5.30, 5.50),
        Row("SPY_C650", "call", 650.0, 4.00, 4.20), Row("SPY_C660", "call", 660.0, 2.10, 2.26),
        Row("SPY_C680", "call", 680.0, 0.50, 0.60)]
    hub.deltas = {("put", 610.0): -0.18, ("put", 600.0): -0.18, ("put", 580.0): -0.05,
                  ("call", 650.0): 0.18, ("call", 660.0): 0.18, ("call", 680.0): 0.05}
    s = CndrIronCondorHold()
    props = s.scan(_ctx(ROLL, hub))
    assert len(props) == 1
    by = {(l["opt_type"], l["side"]): l for l in props[0].legs}
    assert by[("call", -1)]["strike"] == 660.0            # tie 650/660 -> higher (more OTM)
    assert by[("put", -1)]["strike"] == 600.0             # tie 600/610 -> lower (more OTM)
    assert by[("call", 1)]["strike"] == 680.0
    assert by[("put", 1)]["strike"] == 580.0


def test_weeklies_never_substitute_for_the_monthly():
    """Rows 13/14: only third-Friday-cycle listings qualify; an in-DTE-range weekly
    (2026-08-14, 28 DTE but 7 days off the cycle) is NOT the monthly -> no entry."""
    hub = _happy_hub()
    hub.exps = ["2026-07-24", "2026-07-31", "2026-08-07", "2026-08-14"]
    s = CndrIronCondorHold()
    events = []
    assert s.scan(_ctx(ROLL, hub, journal=events.append)) == []
    assert any(e["event"] == "cndr_no_expiry" and e["symbol"] == "SPY" for e in events)


def test_one_condor_per_underlying_with_roll_day_overlap():
    """§10 roll-gap fidelity: an open condor expiring LATER blocks re-entry; the old condor
    expiring TODAY (roll day) never blocks the new month's entry."""
    hub = _happy_hub()
    s = CndrIronCondorHold()

    class OpenPos:
        underlying = "SPY"
        nearest_expiry = date(2026, 8, 21)
    assert s.scan(_ctx(ROLL, hub, open_positions=[OpenPos()])) == []

    class ExpiringPos:
        underlying = "SPY"
        nearest_expiry = date(2026, 7, 17)
    assert len(s.scan(_ctx(ROLL, hub, open_positions=[ExpiringPos()]))) == 1


def test_earnings_hold_flagged_never_skipped():
    """Row 22: no event gate - a hold spanning earnings is tagged for split grading,
    entry remains unconditional."""
    hub = _happy_hub()
    s = CndrIronCondorHold()
    inside = {"SPY": {"date": "2026-08-10", "hour": "amc"}}
    got = s.scan(_ctx(ROLL, hub, earnings=inside))
    assert len(got) == 1                                  # never skipped
    assert got[0].risk_flags == ["holds_through_earnings"]
    after = {"SPY": {"date": "2026-09-01", "hour": "amc"}}
    assert s.scan(_ctx(ROLL, hub, earnings=after))[0].risk_flags == []


def test_manage_always_holds():
    """Rows 18-20: HOLD TO EXPIRATION - no profit target, no stop, no adjustment.
    manage() never exits; the runner's intrinsic settlement is the only close."""
    s = CndrIronCondorHold()
    assert s.manage(object(), None) is None


def test_meta_doctrine_pins():
    m = CndrIronCondorHold.META
    assert m.settle_at_expiry is True                     # row 18: ride to intrinsic settle
    assert m.grading_basis.value == "max_loss"            # row 27: max(width) - credit
    assert m.event_policy.value == "trade_through"        # row 21: unconditional
    assert m.universe == ("SPY",)                         # brief §2 faithful SPX mapping
    assert m.dte_range == (21, 40)                        # row 13 tenor + listing tolerance
    assert m.max_concurrent == 2                          # settling old + fresh new on roll day
    h = CndrIronCondorHold().config_hash()
    assert len(h) == 12
