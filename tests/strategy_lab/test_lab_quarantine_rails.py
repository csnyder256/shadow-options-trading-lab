"""A quarantined strategy's OPEN combos still get the global rails
(opts-fix-lab-quarantine-rails-v1).

The runner's own fault-containment contract (scripts/run_strategy_lab.py module docstring):
"QUARANTINE_ERRORS_PER_DAY exceptions from one strategy disarms it for the day (its positions
still get the global rails: expiry backstop + marks)."

The code did not honor the parenthetical. The tick loop `continue`d on a quarantined sid
BEFORE building the ctx, so both rails - which are runner code, not strategy code - were
dropped along with the strategy's own scan/manage:

  * no marks for the rest of the session, so the combo's mark series has a hole;
  * the global expiry-day backstop never fired, so a combo whose nearest leg expired that day
    (settle_at_expiry=False) rode past the rail entirely and was settled at intrinsic on the
    NEXT day-roll instead - a different exit rule and a different P&L than the rail would have
    booked off the live NBBO.

Both rails must keep running with the strategy's own code suspended. These tests fail on the
pre-fix code (no marks after quarantine, no expiry_backstop exit, an expiry_settlement exit
appearing at the next day-roll) and pass after it. Fake hub + scripted strategy + frozen
weekday clock - no network, everything under tmp_path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import scripts.run_strategy_lab as rsl
from atlas.options.session_calendar import options_close_minute, session_close_minute
from atlas.strategy_lab.strategy import (EventPolicy, GradingBasis, ProposedCombo, Strategy,
                                         StrategyMeta)

NY = ZoneInfo("America/New_York")
DAY = "2026-07-22"                       # a normal Wednesday (equity close 960, ETF 975)
MORNING = datetime(2026, 7, 22, 10, 0, tzinfo=NY)
LATE = datetime(2026, 7, 22, 16, 10, tzinfo=NY)   # 970: inside SPY's [965, 975) backstop band
NEXT_DAY = datetime(2026, 7, 23, 10, 0, tzinfo=NY)


class Bar:
    def __init__(self, ts, close):
        self.ts, self.close = ts, close


class FakeQuote:
    def __init__(self, bid, ask, last=0.0):
        self.bid, self.ask, self.last = bid, ask, last


class FakeGovernor:
    def used(self):
        return 0


class FakeHub:
    """Static two-leg book on SPY plus the expiry-day daily bar the settlement path reads."""

    def __init__(self):
        self.governor = FakeGovernor()
        self.book = {"SPY": (629.9, 630.1, 630.0),
                     "OCC_LONG": (10.0, 10.4, 0.0), "OCC_SHORT": (5.0, 5.4, 0.0)}
        self.bars = [Bar(DAY, 632.0)]

    def poll_quotes(self, underlyings, leg_occs):
        return {s: FakeQuote(*self.book[s]) for s in set(underlyings) | set(leg_occs)
                if s in self.book}

    def last_nbbo(self, sym):
        if sym not in self.book:
            return None
        b, a, _ = self.book[sym]
        return (b, a, 1.0)

    def earnings_week(self):
        return {}

    def daily_history(self, u, days=10):
        return list(self.bars)

    def expirations(self, u):
        return [DAY]


@dataclass(frozen=True)
class _P:
    hold: float = 1.0


class QuarantineProbe(Strategy):
    """Enters ONE debit vertical expiring TODAY, then raises on every later scan().

    manage() never self-exits, so the global expiry-day backstop is the ONLY thing that can
    close the combo - exactly the shape the quarantine gap abandoned.
    """

    META = StrategyMeta(strategy_id="quarantine_probe", version=1, name="quarantine probe",
                        universe=("SPY",), dte_range=(0, 10), max_concurrent=2,
                        event_policy=EventPolicy.TRADE_THROUGH,
                        grading_basis=GradingBasis.DEBIT,
                        defining_mechanism="directional_momentum",
                        settle_at_expiry=False,          # the backstop applies
                        scan_interval_s=0.0, mark_interval_s=0.0)
    params = _P()

    def __init__(self):
        self.entered = False
        self.manage_calls = 0

    def scan(self, ctx):
        if self.entered:
            raise RuntimeError("probe scan bug")
        self.entered = True
        legs = [{"occ": "OCC_LONG", "underlying": "SPY", "opt_type": "call", "strike": 630,
                 "expiry": ctx.day, "side": +1, "qty": 1,
                 "nbbo": {"bid": 10.0, "ask": 10.4}, "iv": 0.2, "delta": 0.55,
                 "gamma": 0.01, "vega": 0.4, "theta_day": -0.05},
                {"occ": "OCC_SHORT", "underlying": "SPY", "opt_type": "call", "strike": 640,
                 "expiry": ctx.day, "side": -1, "qty": 1,
                 "nbbo": {"bid": 5.0, "ask": 5.4}, "iv": 0.19, "delta": -0.35,
                 "gamma": 0.01, "vega": 0.35, "theta_day": -0.04}]
        return [ProposedCombo(kind="bull_call_vertical", underlying="SPY", legs=legs,
                              signal={"trigger": "probe"})]

    def manage(self, pos, ctx):
        self.manage_calls += 1
        return None


def _read(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _core(tmp_path, monkeypatch):
    strat = QuarantineProbe()
    sid = strat.META.strategy_id
    monkeypatch.setattr(rsl, "build_all", lambda: {sid: strat})
    monkeypatch.setattr(rsl, "load_state", lambda: {sid: {"state": "armed", "cohort_pin": "",
                                                          "note": ""}})
    monkeypatch.setattr(rsl, "upcoming_events", lambda now: [])
    monkeypatch.setattr(rsl, "in_blackout", lambda now, events=None: None)
    clock = {"now": MORNING}
    core = rsl.StrategyLabCore(runtime_dir=tmp_path, log=lambda m: None, hub=FakeHub(),
                               now_fn=lambda: clock["now"])
    core._scan_ts[sid] = 0.0
    core._mark_ts[sid] = 0.0
    return core, strat, sid, clock


def _quarantine(core, sid, clock):
    """Drive the lab until the probe strategy is quarantined, and prove it happened."""
    for _ in range(6):                          # tick 1 enters; ticks 2-6 raise 5x
        core.tick()
    assert core.quarantined.get(sid, 0) >= rsl.QUARANTINE_ERRORS_PER_DAY
    core._scan_ts[sid] = 0.0
    core._mark_ts[sid] = 0.0
    return clock


def test_backstop_band_is_real_on_this_clock():
    """The two bounds the test leans on really are distinct: the rail fires at 965 (ETF close
    minus the 10-minute lead), so 970 is inside it and the morning is not."""
    d = datetime.fromisoformat(DAY).date()
    assert session_close_minute(d) == 960
    assert options_close_minute(d, "SPY") == 975
    assert 600 < 975 - 10 <= 970 < 975


def test_quarantined_strategy_still_gets_marks_and_the_expiry_backstop(tmp_path, monkeypatch):
    """The documented contract: the rails keep running while the strategy's code is suspended.

    Pre-fix the late tick wrote NOTHING (no mark, no exit) and the combo was settled at
    intrinsic on the next day-roll (rule expiry_settlement, worst -$340) instead of being closed
    by the rail off the live NBBO (rule expiry_backstop, worst -$80).
    """
    core, strat, sid, clock = _core(tmp_path, monkeypatch)
    s = core.ledger.strategy(sid)
    _quarantine(core, sid, clock)
    marks_before = len(_read(s.marks_path))
    manage_calls_before = strat.manage_calls
    assert marks_before == 5 and manage_calls_before == 5     # ticks 2-6 marked + managed
    assert _read(s.exits_path) == []

    clock["now"] = LATE                                        # 16:10 -> the rail is due
    core._mark_ts[sid] = 0.0
    core._scan_ts[sid] = 0.0
    core.tick()

    marks = _read(s.marks_path)
    assert len(marks) == marks_before + 1, "a quarantined combo must still be marked"
    assert marks[-1]["rule"] == "quarantined_rail_only", \
        "a quarantined mark must not claim the strategy chose to hold"
    assert strat.manage_calls == manage_calls_before, \
        "the quarantined strategy's own manage() stays suspended"

    exits = _read(s.exits_path)
    assert len(exits) == 1, "the global expiry-day backstop must still fire"
    x = exits[0]
    assert x["rule"] == "expiry_backstop"
    # live NBBO close: long sells at bid 10.0, short buys back at ask 5.4 -> net 4.6 vs 5.4 entry
    assert x["ledgers"]["worst"]["net_pnl_usd"] == -80.0
    assert core.positions[sid] == []

    # the combo is gone, so the next day-roll has nothing left to settle at intrinsic
    clock["now"] = NEXT_DAY
    core._mark_ts[sid] = 0.0
    core.tick()
    assert [r["rule"] for r in _read(s.exits_path)] == ["expiry_backstop"], \
        "the rail's close must not be followed by a second, contradictory settlement"


def test_quarantine_still_disarms_scan_and_new_entries(tmp_path, monkeypatch):
    """The other half of the contract is unchanged: a quarantined strategy takes no new
    actions. Its scan() is not called again (so the error count stops at the threshold) and no
    further entry is written - the rails apply to positions it already holds, nothing more."""
    core, strat, sid, clock = _core(tmp_path, monkeypatch)
    s = core.ledger.strategy(sid)
    _quarantine(core, sid, clock)
    errors_before = len([r for r in _read(s.journal_path) if r.get("event") == "strategy_error"])
    assert errors_before == rsl.QUARANTINE_ERRORS_PER_DAY

    clock["now"] = LATE
    core._mark_ts[sid] = 0.0
    core._scan_ts[sid] = 0.0
    core.tick()
    core.tick()                                                # and once more, same minute

    errors = [r for r in _read(s.journal_path) if r.get("event") == "strategy_error"]
    assert len(errors) == rsl.QUARANTINE_ERRORS_PER_DAY, \
        "a quarantined strategy's code must not be called again today"
    assert len(_read(s.entries_path)) == 1, "quarantine means no new entries"
    hb = json.loads((tmp_path / "strategy_lab_heartbeat.json").read_text(encoding="utf-8"))
    assert hb["quarantined"] == [sid]


def test_healthy_strategy_marks_are_unlabelled_and_managed(tmp_path, monkeypatch):
    """Regression pin on the normal path: a strategy that has not quarantined keeps an
    unlabelled hold mark and still gets its own manage() call every mark cycle. Three ticks
    are two scan errors short of the quarantine threshold, so nothing is suspended yet."""
    core, strat, sid, clock = _core(tmp_path, monkeypatch)
    core.tick()                                                # enter
    core._mark_ts[sid] = 0.0
    core.tick()                                                # mark + manage (error 1)
    core.tick()                                                # mark + manage (error 2)

    marks = _read(core.ledger.strategy(sid).marks_path)
    assert len(marks) == 2
    assert all(m["rule"] == "" for m in marks)
    assert all(m["action"] == "hold" for m in marks)
    assert strat.manage_calls == 2, "the healthy path still calls the strategy's manage()"
    assert core.quarantined.get(sid, 0) == 2 < rsl.QUARANTINE_ERRORS_PER_DAY
