"""zero_dte_morning_ic vs its verified brief (docs/strategies/briefs/zero_dte_morning_ic.md).
Each test cites the brief row it pins. Fake hub (delta table -> exact strike-selection pins),
no network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from atlas.options.events import EconEvent
from atlas.strategy_lab.model import LegSpec
from atlas.strategy_lab.strategies.zero_dte_morning_ic import ZeroDteMorningIc
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")
MON = datetime(2026, 7, 20, 9, 45, tzinfo=NY)       # a real Monday, 09:45 ET (minute 585)
TUE = datetime(2026, 7, 21, 9, 45, tzinfo=NY)
D_MON, D_TUE = "2026-07-20", "2026-07-21"


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float
    open_interest: float = 500.0


class FakeHub:
    """Delta table keyed (opt_type, strike) makes 14-delta selection exactly pinnable
    (SPY ~610 and QQQ ~500 strikes are disjoint, so no symbol key is needed)."""
    def __init__(self):
        self.refs = {"SPY": 610.0}
        self.exps = {"SPY": [D_MON, "2026-07-24"]}
        self.chains = {}
        self.deltas = {}
        self.book = {}                               # occ -> (bid, ask) for last_nbbo

    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)

    def expirations(self, sym, **kw):
        return self.exps.get(sym, [])

    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])

    def row_greeks(self, *, opt_type, strike, S, mid, dte_days, r=0.04):
        d = self.deltas.get((opt_type, strike))
        if d is None:
            return None
        return {"iv": 0.25, "delta": d, "gamma": 0.001, "vega": 0.05, "theta_day": -0.5}

    def last_nbbo(self, occ):
        if occ not in self.book:
            return None
        b, a = self.book[occ]
        return (b, a, 1.0)


def _ctx(dt, hub, open_positions=(), events=(), day=None):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=day or dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=960, hub=hub,
                           events=list(events), journal=None,
                           open_positions=list(open_positions))


def _spy_chain():
    """S_ref 610: shorts should land P605 (-0.14) / C615 (+0.14); wing target 0.75% of 610
    = 4.575 -> nearest listed width is 5 on the $1 grid -> wings P600 / C620."""
    return [Row("P600", "put", 600.0, 0.45, 0.50), Row("P601", "put", 601.0, 0.50, 0.55),
            Row("P603", "put", 603.0, 0.70, 0.78), Row("P604", "put", 604.0, 0.85, 0.93),
            Row("P605", "put", 605.0, 1.00, 1.10), Row("P606", "put", 606.0, 1.20, 1.30),
            Row("P607", "put", 607.0, 1.45, 1.55),
            Row("P608_dead", "put", 608.0, 0.0, 1.9),      # one-sided - excluded (no bid)
            Row("C614", "call", 614.0, 1.15, 1.25), Row("C615", "call", 615.0, 0.95, 1.05),
            Row("C616", "call", 616.0, 0.78, 0.86), Row("C617", "call", 617.0, 0.60, 0.66),
            Row("C619", "call", 619.0, 0.44, 0.48), Row("C620", "call", 620.0, 0.40, 0.44)]


def _spy_deltas():
    return {("put", 600.0): -0.05, ("put", 601.0): -0.06, ("put", 603.0): -0.10,
            ("put", 604.0): -0.12, ("put", 605.0): -0.14, ("put", 606.0): -0.17,
            ("put", 607.0): -0.20, ("put", 608.0): -0.24,
            ("call", 614.0): 0.17, ("call", 615.0): 0.14, ("call", 616.0): 0.11,
            ("call", 617.0): 0.09, ("call", 619.0): 0.06, ("call", 620.0): 0.05}


def _hub():
    hub = FakeHub()
    hub.chains[("SPY", D_MON)] = _spy_chain()
    hub.deltas = _spy_deltas()
    return hub


def test_entry_window_gating():
    """Row 3: ~09:45 ET morning entry only - closed before 09:45 and from 09:55 on."""
    s = ZeroDteMorningIc()
    assert s.scan(_ctx(MON.replace(minute=44), _hub())) == []       # 09:44 - early
    assert s.scan(_ctx(MON.replace(minute=55), _hub())) == []       # 09:55 - window closed
    assert len(ZeroDteMorningIc().scan(_ctx(MON, _hub()))) == 1     # 09:45 fires
    late = MON.replace(minute=54)                                   # 09:54 - last minute in
    assert len(ZeroDteMorningIc().scan(_ctx(late, _hub()))) == 1


def test_zero_dte_expiry_only():
    """Row 2: TODAY-expiring expiration only - no 0DTE listing means no trade, never a
    next-day substitute."""
    hub = _hub()
    hub.exps["SPY"] = ["2026-07-24"]                                # today missing
    assert ZeroDteMorningIc().scan(_ctx(MON, hub)) == []
    p = ZeroDteMorningIc().scan(_ctx(MON, _hub()))[0]
    assert all(leg["expiry"] == D_MON for leg in p.legs)            # all 4 legs expire today


def test_four_leg_construction_14delta_and_wings():
    """Rows 5/7/8: short strikes at |delta| closest to 0.14, wings at the listed strike
    nearest 0.75% of spot, all legs two-sided, delta-symmetric 4-leg shape."""
    p = ZeroDteMorningIc().scan(_ctx(MON, _hub()))[0]
    assert p.kind == "iron_condor_0dte" and p.underlying == "SPY" and p.contracts == 1
    assert [(l["opt_type"], l["side"], l["strike"]) for l in p.legs] == [
        ("put", -1, 605.0), ("put", +1, 600.0),                     # 14d short, 5-wide wing
        ("call", -1, 615.0), ("call", +1, 620.0)]
    assert all(l["qty"] == 1 for l in p.legs)
    assert all(l["nbbo"]["bid"] > 0 and l["nbbo"]["ask"] > 0 for l in p.legs)
    assert p.signal["short_put_delta"] == -0.14                     # row 5 pin
    assert p.signal["short_call_delta"] == 0.14
    assert p.signal["wing_width_put"] == 5.0                        # row 8: |4.575 -> 5| < |-> 4|
    assert p.signal["wing_width_call"] == 5.0
    # credit at mids (row 20): put 1.05-0.475=0.575, call 1.00-0.42=0.58
    assert p.signal["credit_mid"] == pytest.approx(1.155)
    assert p.signal["events_today"] == []


def test_liquidity_and_credit_gates_skip():
    """Rows 9/19 PLATFORM-POLICY gates: OI < 100, spread > 15% of mid, or side credit
    < $0.05 each kill the entry (skip, never a repaired entry)."""
    hub = _hub()                                                    # OI gate: long call OI 50
    hub.chains[("SPY", D_MON)][-1] = Row("C620", "call", 620.0, 0.40, 0.44, open_interest=50.0)
    assert ZeroDteMorningIc().scan(_ctx(MON, hub)) == []

    hub = _hub()                                                    # spread gate: 0.30 > 15% of 1.15
    hub.chains[("SPY", D_MON)][4] = Row("P605", "put", 605.0, 1.00, 1.30)
    assert ZeroDteMorningIc().scan(_ctx(MON, hub)) == []

    hub = _hub()                                                    # credit gate: put side 0.02
    hub.chains[("SPY", D_MON)][4] = Row("P605", "put", 605.0, 0.47, 0.51)   # mid 0.49
    hub.chains[("SPY", D_MON)][0] = Row("P600", "put", 600.0, 0.46, 0.48)   # mid 0.47
    assert ZeroDteMorningIc().scan(_ctx(MON, hub)) == []


def test_one_entry_per_underlying_per_day():
    """Row 17: ONE condor per symbol per day - a same-day rescan (incl. after a stop-out,
    when open_positions is empty again) never re-enters; a new day resets; an open combo
    entered today blocks a fresh instance (restart safety)."""
    s = ZeroDteMorningIc()
    assert len(s.scan(_ctx(MON, _hub()))) == 1
    assert s.scan(_ctx(MON.replace(minute=46), _hub())) == []       # same day: blocked
    # stop-out simulation: position closed -> open_positions still empty -> STILL blocked
    assert s.scan(_ctx(MON.replace(minute=47), _hub(), open_positions=[])) == []
    hub2 = _hub()                                                   # next day: reset, fires
    hub2.exps["SPY"] = [D_TUE]
    hub2.chains[("SPY", D_TUE)] = _spy_chain()
    assert len(s.scan(_ctx(TUE, hub2))) == 1

    class OpenPos:                                                  # restart: rebuilt open combo
        underlying = "SPY"
        entry_day = D_MON
    fresh = ZeroDteMorningIc()
    assert fresh.scan(_ctx(MON, _hub(), open_positions=[OpenPos()])) == []


def test_event_day_trades_through_and_annotates():
    """Row 16: 'trade anyway (formal skip rule UNKNOWN)' - NO print-day stand-down. A same-day
    FOMC (14:00, lands after entry - §7 failure mode) is annotated + risk-flagged for the
    grader's event-day slice (§9), never skipped."""
    events = [EconEvent("fomc", datetime(2026, 7, 20, 14, 0, tzinfo=NY), "decision"),
              EconEvent("fomc", datetime(2026, 7, 20, 14, 30, tzinfo=NY), "presser"),
              EconEvent("cpi", datetime(2026, 7, 21, 8, 30, tzinfo=NY))]    # tomorrow: ignored
    props = ZeroDteMorningIc().scan(_ctx(MON, _hub(), events=events))
    assert len(props) == 1                                          # traded THROUGH the event
    assert props[0].signal["events_today"] == ["fomc"]              # deduped, same-day only
    assert props[0].risk_flags == ["holds_through_fomc"]


class FakePos:
    """manage() surface: net_open + legs[i].spec (real LegSpec for validation fidelity)."""
    def __init__(self, net_open):
        self.net_open = net_open
        exp = date(2026, 7, 20)

        class _L:
            def __init__(self, spec):
                self.spec = spec
        self.legs = [_L(LegSpec("SP", "SPY", "put", 605.0, exp, -1)),
                     _L(LegSpec("LP", "SPY", "put", 600.0, exp, +1)),
                     _L(LegSpec("SC", "SPY", "call", 615.0, exp, -1)),
                     _L(LegSpec("LC", "SPY", "call", 620.0, exp, +1))]


def test_stop_boundary_exact():
    """Row 12 (§10 whole-condor form): close when debit-to-close EITHER short spread >= 1.0 x
    total credit - boundary is >= (equality closes); just below holds; missing NBBO holds."""
    s = ZeroDteMorningIc()
    net_open = {"worst": -1.2, "base": -1.35, "optimistic": -1.5}   # credit 1.50 (mid ledger)
    hub = FakeHub()
    # put side exactly AT credit: 1.75 - 0.25 = 1.50 >= 1.50 -> close (binary-exact values)
    hub.book = {"SP": (1.75, 1.75), "LP": (0.25, 0.25), "SC": (0.5, 0.5), "LC": (0.125, 0.125)}
    act = s.manage(FakePos(net_open), _ctx(MON, hub))
    assert act is not None and act.action == "close"
    assert act.rule == "stop_side_debit_ge_credit"
    assert act.state["breached"] == ["put"]
    assert act.state["credit"] == 1.5
    # one cent below: 1.49 < 1.50 -> hold (no profit target either - row 10)
    hub.book["SP"] = (1.74, 1.74)
    assert s.manage(FakePos(net_open), _ctx(MON, hub)) is None
    # call side breaches alone: 2.0 - 0.5 = 1.5 >= 1.5 -> close
    hub.book = {"SP": (0.5, 0.5), "LP": (0.25, 0.25), "SC": (2.0, 2.0), "LC": (0.5, 0.5)}
    act = s.manage(FakePos(net_open), _ctx(MON, hub))
    assert act is not None and act.state["breached"] == ["call"]
    # missing leg NBBO -> hold, even though the put side would otherwise breach
    hub.book = {"SP": (3.0, 3.0), "LP": (0.25, 0.25), "SC": (0.5, 0.5)}     # LC absent
    assert s.manage(FakePos(net_open), _ctx(MON, hub)) is None
    # degenerate non-credit entry -> no stop reference -> hold
    hub.book = {"SP": (3.0, 3.0), "LP": (0.25, 0.25), "SC": (0.5, 0.5), "LC": (0.125, 0.125)}
    assert s.manage(FakePos({"worst": 0.1, "base": 0.05, "optimistic": 0.02}),
                    _ctx(MON, hub)) is None


def test_meta_doctrine_pins():
    m = ZeroDteMorningIc.META
    assert m.strategy_id == "zero_dte_morning_ic" and m.version == 1
    assert m.settle_at_expiry is True                               # rides to close (vs row 14)
    assert m.expected_fires_per_20_sessions == 20.0
    assert m.event_policy.value == "trade_through"                  # row 16
    assert m.grading_basis.value == "max_loss"                      # row 18 width - credit
    assert m.universe == ("SPY", "QQQ")                             # tasking pin (brief adds IWM)
    assert m.dte_range == (0, 1) and m.max_concurrent == 2          # rows 2/17
    assert m.scan_interval_s == 60.0 and m.mark_interval_s == 60.0  # §9/§10 1-min stop monitor
    h = ZeroDteMorningIc().config_hash()
    assert len(h) == 12
