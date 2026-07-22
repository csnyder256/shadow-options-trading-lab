"""pre_fomc_drift_call vs its verified brief (docs/strategies/briefs/pre_fomc_drift_call.md).
Each test cites the brief row/§ it pins. Fake hub + fake (duck-typed) EconEvents, no network.
Clock fixture: FOMC decision Wed 2026-07-29 14:00 ET (real Fed calendar row), so T-1 is
Tue 2026-07-28 and the derived window is [Tue 13:45 ET, Wed 13:45 ET] (rows 2/3/4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from atlas.strategy_lab.hub import MarketHub
from atlas.strategy_lab.strategies.pre_fomc_drift_call import PreFomcDriftCall
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")
DECISION = datetime(2026, 7, 29, 14, 0, tzinfo=NY)       # Wed 14:00 ET statement release
T1_1346 = datetime(2026, 7, 28, 13, 46, tzinfo=NY)       # inside [13:45, 13:55) on T-1


@dataclass
class FakeEvent:                                          # duck-typed atlas.options.events.EconEvent
    kind: str
    ts_et: datetime
    label: str = ""


def _events():
    return [FakeEvent("fomc", DECISION, "decision"),
            FakeEvent("fomc", DECISION + timedelta(minutes=30), "presser"),
            FakeEvent("cpi", datetime(2026, 8, 12, 8, 30, tzinfo=NY))]


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float


def _spy_calls():
    return [Row("C629", "call", 629.0, 3.60, 3.80), Row("C630", "call", 630.0, 3.00, 3.20),
            Row("C631", "call", 631.0, 2.45, 2.65),
            Row("P630", "put", 630.0, 2.90, 3.10),        # put - excluded
            Row("C632_dead", "call", 632.0, 0.0, 0.0)]    # one-sided book - excluded


class FakeHub:
    def __init__(self):
        self.refs = {"SPY": 630.40}
        self.exps = ["2026-07-28", "2026-07-29", "2026-07-30", "2026-08-07"]
        self.chains = {("SPY", e): _spy_calls() for e in self.exps}
    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)
    def expirations(self, sym, **kw):
        return self.exps
    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])
    row_greeks = staticmethod(MarketHub.row_greeks)


def _ctx(dt, hub, events=(), open_positions=(), journal=None):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=975, hub=hub,
                           events=list(events), journal=journal,
                           open_positions=list(open_positions))


class FakePos:
    """Duck-typed ComboPosition slice manage() reads: notes + entry_ts."""
    def __init__(self, notes=None, entry_dt=T1_1346):
        self.notes = notes if notes is not None else {"decision_ts_et": DECISION.isoformat()}
        self.entry_ts = entry_dt.timestamp()


# --------------------------------------------------------------------------- entry doctrine
def test_enters_in_t1_window_long_atm_call_expiry_after_decision():
    """Rows 2/3 (window), 7/10 (long 1 call), 11 (ATM), 12 (expiry strictly after decision)."""
    s = PreFomcDriftCall()
    got = s.scan(_ctx(T1_1346, FakeHub(), events=_events()))
    assert len(got) == 1
    p = got[0]
    assert p.kind == "long_call_pre_fomc" and p.underlying == "SPY" and p.contracts == 1
    leg = p.legs[0]
    assert leg["side"] == +1 and leg["opt_type"] == "call" and leg["qty"] == 1   # rows 7/10/19
    assert leg["strike"] == 630.0                    # nearest to 630.40 (row 11) - not 629/631
    assert leg["expiry"] == "2026-07-30"             # strictly AFTER 07-29, never the decision day
    assert leg["delta"] > 0                          # solved call delta present
    assert p.signal["decision_ts_et"] == DECISION.isoformat()
    assert p.signal["notes"]["decision_ts_et"] == DECISION.isoformat()   # exit anchor persisted


def test_no_fomc_event_no_scan():
    """META REQUIRES_EVENT + row 1: no scheduled DECISION in ctx.events -> never enters.
    A presser row or another macro print is not the signal."""
    s = PreFomcDriftCall()
    hub = FakeHub()
    assert s.scan(_ctx(T1_1346, hub, events=[])) == []
    assert s.scan(_ctx(T1_1346, hub, events=[FakeEvent("cpi", DECISION)])) == []
    presser_only = [FakeEvent("fomc", DECISION + timedelta(minutes=30), "presser")]
    assert s.scan(_ctx(T1_1346, hub, events=presser_only)) == []


def test_entry_window_minutes_gate():
    """Rows 2/3: entry ONLY in [release-24h15m, start+tolerance) on T-1 - never a minute
    before the published start, never elsewhere on T-1, never on the decision day."""
    s = PreFomcDriftCall()
    hub = FakeHub()
    ev = _events()
    def at(day, hh, mm):
        return _ctx(datetime(2026, 7, day, hh, mm, tzinfo=NY), hub, events=ev)
    assert s.scan(at(28, 13, 44)) == []              # 1 min before the published window start
    assert len(s.scan(at(28, 13, 45))) == 1          # the derived start itself (13:45 ET T-1)
    assert len(s.scan(at(28, 13, 54))) == 1          # inside the entry tolerance
    assert s.scan(at(28, 13, 55)) == []              # tolerance closed
    assert s.scan(at(28, 11, 0)) == []               # mid-day T-1: outside the window
    assert s.scan(at(29, 13, 46)) == []              # decision day is the exit clock, not entry


def test_atm_tie_breaks_low_and_skips_dead_quotes():
    """Row 11: nearest strike to spot; equidistant tie -> lower strike (ITM side, closer to
    the delta-one source); a one-sided book can never be the pick."""
    s = PreFomcDriftCall()
    hub = FakeHub()
    hub.refs["SPY"] = 630.50                         # exactly between 630 and 631
    got = s.scan(_ctx(T1_1346, hub, events=_events()))
    assert got[0].legs[0]["strike"] == 630.0
    hub2 = FakeHub()
    hub2.refs["SPY"] = 630.40
    hub2.chains = {("SPY", e): [Row("C630", "call", 630.0, 0.0, 3.20),   # one-sided - skipped
                                Row("C631", "call", 631.0, 2.45, 2.65),
                                Row("C629", "call", 629.0, 3.60, 3.80)] for e in hub2.exps}
    got2 = s.scan(_ctx(T1_1346, hub2, events=_events()))
    assert got2[0].legs[0]["strike"] == 631.0        # 631 (0.60 away) beats 629 (1.40 away)


def test_no_listed_expiry_after_decision_stands_down_and_journals():
    """Row 12: expiry must be strictly after the decision day; none listed -> no entry
    (non-result journaled, never silent)."""
    s = PreFomcDriftCall()
    hub = FakeHub()
    hub.exps = ["2026-07-28", "2026-07-29"]          # nothing beyond the decision day
    hub.chains = {("SPY", e): _spy_calls() for e in hub.exps}
    seen = []
    assert s.scan(_ctx(T1_1346, hub, events=_events(), journal=seen.append)) == []
    assert [r["event"] for r in seen] == ["prefomc_no_expiry"]


def test_open_position_blocks_reentry():
    """max_concurrent=1 doctrine mirrored in scan: an open window position blocks entry."""
    s = PreFomcDriftCall()
    assert s.scan(_ctx(T1_1346, FakeHub(), events=_events(),
                       open_positions=[object()])) == []


# --------------------------------------------------------------------------- exit doctrine
def test_time_exit_fires_at_gate_not_before():
    """Row 4: sell at release - 15 min (13:45 ET decision day). Rows 13/14/15: NOTHING else
    exits - no profit target, no stop, no roll - so every earlier mark holds."""
    s = PreFomcDriftCall()
    pos = FakePos()
    for dt in (datetime(2026, 7, 28, 14, 30, tzinfo=NY),    # T-1, 44 min after entry
               datetime(2026, 7, 29, 9, 40, tzinfo=NY),     # decision-day open
               datetime(2026, 7, 29, 13, 44, tzinfo=NY)):   # one minute before the gate
        assert s.manage(pos, _ctx(dt, None)) is None
    a = s.manage(pos, _ctx(datetime(2026, 7, 29, 13, 45, tzinfo=NY), None))
    assert a is not None and a.action == "close" and a.rule == "time_exit_pre_release"
    assert a.state["late_past_release"] is False
    assert a.state["gate_et"] == (DECISION - timedelta(minutes=15)).isoformat()


def test_late_mark_still_exits_immediately():
    """§10: a post-release mark is a process failure to grade, but the position is NEVER
    held - manage() exits on the first opportunity even after 14:00 (quotes not consulted)."""
    s = PreFomcDriftCall()
    a = s.manage(FakePos(), _ctx(datetime(2026, 7, 29, 14, 5, tzinfo=NY), None))
    assert a is not None and a.action == "close" and a.rule == "time_exit_pre_release"
    assert a.state["late_past_release"] is True


def test_exit_anchor_falls_back_to_events_then_failsafe():
    """§7 release-time-drift failure mode: lost entry notes -> live ctx.events decision;
    both anchors gone -> full-published-window failsafe (entry_lead - exit_lead = 24h).
    The one thing this strategy never does is hold through the announcement."""
    s = PreFomcDriftCall()
    ev = _events()
    pos = FakePos(notes={})
    assert s.manage(pos, _ctx(datetime(2026, 7, 29, 13, 40, tzinfo=NY), None, events=ev)) is None
    a = s.manage(pos, _ctx(datetime(2026, 7, 29, 13, 45, tzinfo=NY), None, events=ev))
    assert a is not None and a.rule == "time_exit_pre_release"
    assert a.state["anchor"] == "ctx_events"
    blind = FakePos(notes={})                        # no notes AND no calendar
    assert s.manage(blind, _ctx(datetime(2026, 7, 29, 13, 30, tzinfo=NY), None)) is None
    b = s.manage(blind, _ctx(datetime(2026, 7, 29, 13, 47, tzinfo=NY), None))
    assert b is not None and b.action == "close" and b.rule == "time_exit_failsafe"


# --------------------------------------------------------------------------- META doctrine
def test_meta_doctrine_pins():
    m = PreFomcDriftCall.META
    assert m.strategy_id == "pre_fomc_drift_call" and m.version == 1
    assert m.universe == ("SPY",)                    # row 9: SPY primary, singles excluded
    assert m.event_policy.value == "requires_event"  # row 1: the scheduled decision IS the signal
    assert m.grading_basis.value == "debit"          # §10: long premium, max loss = debit
    assert m.settle_at_expiry is False               # §4: exit is a sale, never settlement
    assert m.max_concurrent == 1
    assert m.dte_range == (1, 10)
    assert m.defining_mechanism == "drift_capture"
    assert m.scan_interval_s == 60.0 and m.mark_interval_s == 120.0
    assert m.expected_fires_per_20_sessions == 1.0   # 8 scheduled meetings/yr (§10 cadence)
    assert len(PreFomcDriftCall().config_hash()) == 12
