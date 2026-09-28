"""End-to-end runner flow through the REAL StrategyLabCore: scan -> enter -> mark -> manage ->
exit -> rebuild, plus quarantine containment (lab-strategy-runtime-v1). Fake hub + scripted
strategy + frozen weekday clock - no network, everything under tmp_path."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import scripts.run_strategy_lab as rsl
from atlas.strategy_lab.strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo,
                                         Strategy, StrategyMeta)

NY = ZoneInfo("America/New_York")
MONDAY_10AM = datetime(2026, 7, 20, 10, 0, tzinfo=NY)


class FakeQuote:
    def __init__(self, bid, ask, last=0.0):
        self.bid, self.ask, self.last = bid, ask, last


class FakeGovernor:
    def used(self):
        return 0


class FakeHub:
    """Duck-typed MarketHub replacement: static book, everything fresh."""
    def __init__(self):
        self.governor = FakeGovernor()
        self.book = {"SPY": (629.9, 630.1, 630.0),
                     "OCC_LONG": (10.0, 10.4, 0.0), "OCC_SHORT": (5.0, 5.4, 0.0)}
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
        return []


@dataclass(frozen=True)
class _P:
    profit_take: float = 0.5


class ScriptStrategy(Strategy):
    """Enters one debit vertical on the first scan; closes it on the second manage call."""
    META = StrategyMeta(strategy_id="script_strat", version=1, name="scripted",
                        universe=("SPY",), dte_range=(30, 60), max_concurrent=1,
                        event_policy=EventPolicy.TRADE_THROUGH,
                        grading_basis=GradingBasis.DEBIT,
                        defining_mechanism="directional_momentum",
                        scan_interval_s=0.0, mark_interval_s=0.0)
    params = _P()

    def __init__(self):
        self.manage_calls = 0

    def scan(self, ctx):
        legs = [{"occ": "OCC_LONG", "underlying": "SPY", "opt_type": "call", "strike": 630,
                 "expiry": "2026-08-31", "side": +1, "qty": 1,
                 "nbbo": {"bid": 10.0, "ask": 10.4}, "iv": 0.2, "delta": 0.55,
                 "gamma": 0.01, "vega": 0.4, "theta_day": -0.05},
                {"occ": "OCC_SHORT", "underlying": "SPY", "opt_type": "call", "strike": 640,
                 "expiry": "2026-08-31", "side": -1, "qty": 1,
                 "nbbo": {"bid": 5.0, "ask": 5.4}, "iv": 0.19, "delta": -0.35,
                 "gamma": 0.01, "vega": 0.35, "theta_day": -0.04}]
        return [ProposedCombo(kind="bull_call_vertical", underlying="SPY", legs=legs,
                              signal={"trigger": "scripted"})]

    def manage(self, pos, ctx):
        self.manage_calls += 1
        if self.manage_calls >= 2:
            return ExitAction(action="close", rule="scripted_close", state={"calls": self.manage_calls})
        return None


class BrokenStrategy(ScriptStrategy):
    META = StrategyMeta(strategy_id="broken_strat", version=1, name="raises",
                        universe=("SPY",), dte_range=(30, 60), max_concurrent=1,
                        event_policy=EventPolicy.TRADE_THROUGH,
                        grading_basis=GradingBasis.DEBIT,
                        defining_mechanism="directional_momentum",
                        scan_interval_s=0.0, mark_interval_s=0.0)
    def scan(self, ctx):
        raise RuntimeError("scripted bug")


def _core(tmp_path, monkeypatch, strat_cls=ScriptStrategy):
    strat = strat_cls()
    sid = strat.META.strategy_id
    monkeypatch.setattr(rsl, "build_all", lambda: {sid: strat})
    monkeypatch.setattr(rsl, "load_state", lambda: {sid: {"state": "armed", "cohort_pin": "",
                                                          "note": ""}})
    monkeypatch.setattr(rsl, "upcoming_events", lambda now: [])
    monkeypatch.setattr(rsl, "in_blackout", lambda now, events=None: None)
    core = rsl.StrategyLabCore(runtime_dir=tmp_path, log=lambda m: None, hub=FakeHub(),
                               now_fn=lambda: MONDAY_10AM)
    return core, strat, sid


def _read(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_full_lifecycle_enter_mark_close_rebuild(tmp_path, monkeypatch):
    core, strat, sid = _core(tmp_path, monkeypatch)
    core.tick()                                    # roll + scan -> ENTER
    s = core.ledger.strategy(sid)
    entries = _read(s.entries_path)
    assert len(entries) == 1
    rec = entries[0]
    assert rec["strategy_id"] == sid and rec["kind"] == "bull_call_vertical"
    assert rec["net_fills"]["worst"] == 5.4        # 10.4 - 5.0 (proven fill math)
    assert rec["grading"]["basis"] == "debit" and rec["grading"]["denom_usd"] == 540.0
    assert rec["strategy_config_hash"] == strat.config_hash()
    assert len(core.positions[sid]) == 1

    core.tick()                                    # manage call 1 -> hold (mark written)
    assert strat.manage_calls == 1
    marks = _read(s.marks_path)
    assert marks and marks[-1]["action"] == "hold"

    core.tick()                                    # manage call 2 -> close; freed slot re-enters
    exits = _read(s.exits_path)
    assert len(exits) == 1
    x = exits[0]
    assert x["rule"] == "scripted_close"
    # flat book: close worst = sell 10.0, buy back 5.4 -> net 4.6; pnl = (4.6-5.4)*100 = -80
    assert x["ledgers"]["worst"]["net_pnl_usd"] == -80.0
    assert x["ledgers"]["worst"]["return_pct"] == round(-80.0 / 540.0, 6)
    assert x["legs_close"][0]["iv"] > 0            # solved close IV present for attribution
    # scan ran after the close in the same tick (interval 0, slot freed) -> seq-1 entry open
    entries2 = _read(s.entries_path)
    assert len(entries2) == 2
    assert [p.position_id for p in core.positions[sid]] == [entries2[1]["position_id"]]

    # rebuild from ledgers: 2 entries, 1 exit -> exactly the second position open
    core2, _, _ = _core(tmp_path, monkeypatch)
    core2.tick()
    assert len(core2.positions[sid]) == 1
    assert core2.positions[sid][0].position_id == _read(s.entries_path)[1]["position_id"]

    # quote-capture rows written for open legs
    qdir = tmp_path / "strategy_lab" / "quotes"
    assert any(qdir.glob("*.jsonl"))


def test_quarantine_contains_broken_strategy(tmp_path, monkeypatch):
    core, strat, sid = _core(tmp_path, monkeypatch, strat_cls=BrokenStrategy)
    for _ in range(6):
        core.tick()
    s = core.ledger.strategy(sid)
    errors = [r for r in _read(s.journal_path) if r.get("event") == "strategy_error"]
    assert len(errors) == rsl.QUARANTINE_ERRORS_PER_DAY          # then skipped, no more errors
    lab_j = _read(tmp_path / "strategy_lab" / "lab_journal.jsonl")
    assert any(r.get("event") == "strategy_quarantined" for r in lab_j)
    hb = json.loads((tmp_path / "strategy_lab_heartbeat.json").read_text(encoding="utf-8"))
    assert hb["quarantined"] == [sid]


def test_blackout_policy_suppresses_scan(tmp_path, monkeypatch):
    class BlackoutStrat(ScriptStrategy):
        META = StrategyMeta(strategy_id="script_strat", version=1, name="scripted",
                            universe=("SPY",), dte_range=(30, 60), max_concurrent=1,
                            event_policy=EventPolicy.BLACKOUT,
                            grading_basis=GradingBasis.DEBIT,
                            defining_mechanism="directional_momentum",
                            scan_interval_s=0.0, mark_interval_s=0.0)
    core, strat, sid = _core(tmp_path, monkeypatch, strat_cls=BlackoutStrat)
    monkeypatch.setattr(rsl, "in_blackout", lambda now, events=None: "cpi")
    core.tick()
    s = core.ledger.strategy(sid)
    assert _read(s.entries_path) == []
    assert any(r.get("event") == "scan_blackout_skip" for r in _read(s.journal_path))


def test_halted_underlying_vetoes_entry(tmp_path, monkeypatch):
    core, strat, sid = _core(tmp_path, monkeypatch)
    import time as _time
    (tmp_path / "symbol_state.json").write_text(json.dumps(
        {"fetched_epoch": _time.time(),
         "halts": {"SPY": {"ts_epoch": _time.time(), "reason": "LUDP"}}}), encoding="utf-8")
    core.tick()
    s = core.ledger.strategy(sid)
    journal = _read(s.journal_path)
    vetoed = [r for r in journal if r.get("event") == "entry_vetoed"]
    if vetoed:                                     # schema matched -> hard assertion
        assert _read(s.entries_path) == []
    else:
        # fail-open contract: unknown snapshot shape must NEVER block entries
        assert len(_read(s.entries_path)) == 1


# --------------------------------------------------------------------- multi-expiry settlement
class CalendarQuote:
    def __init__(self, bid, ask, last=0.0):
        self.bid, self.ask, self.last = bid, ask, last


class _Bar:
    def __init__(self, ts, close):
        self.ts, self.close = ts, close


class CalendarHub(FakeHub):
    """Daily history keyed by date with a REAL lookback window, plus a live book for both legs.

    `daily_history(days=N)` returns only the bars inside an N-calendar-day window ending at the
    page's `asof` day, mirroring Tradier's calendar-day semantics - so a test can prove that an
    old front expiry is reachable, and that one the provider can no longer serve (outside the
    window) is honestly missed rather than silently priced off the wrong day.
    """

    def __init__(self, asof="2026-08-24"):
        super().__init__()
        self.book = {"SPY": (629.9, 630.1, 630.0),
                     "OCC_FRONT": (4.60, 5.00, 0.0),      # short leg, expiring 2026-07-24
                     "OCC_BACK": (8.00, 8.40, 0.0)}       # long leg, expiring 2026-08-21
        self.bars = {"2026-07-24": 632.0, "2026-08-21": 632.0}
        self.asof = asof

    def daily_history(self, u, days=10):
        end = datetime.fromisoformat(self.asof).date()
        start = end.fromordinal(end.toordinal() - int(days))
        return [_Bar(ts=d, close=c) for d, c in sorted(self.bars.items())
                if start <= datetime.fromisoformat(d).date() <= end]


class CalendarStrategy(Strategy):
    """Enters one short-front / long-back debit calendar - the only multi-expiry shape armed."""
    META = StrategyMeta(strategy_id="script_calendar", version=1, name="scripted calendar",
                        universe=("SPY",), dte_range=(5, 45), max_concurrent=1,
                        event_policy=EventPolicy.TRADE_THROUGH,
                        grading_basis=GradingBasis.DEBIT,
                        defining_mechanism="term_structure",
                        settle_at_expiry=False,
                        scan_interval_s=0.0, mark_interval_s=0.0)
    params = _P()

    def scan(self, ctx):
        legs = [{"occ": "OCC_FRONT", "underlying": "SPY", "opt_type": "call", "strike": 630,
                 "expiry": "2026-07-24", "side": -1, "qty": 1,
                 "nbbo": {"bid": 4.60, "ask": 5.00}, "iv": 0.22, "delta": -0.5,
                 "gamma": 0.02, "vega": 0.30, "theta_day": -0.12},
                {"occ": "OCC_BACK", "underlying": "SPY", "opt_type": "call", "strike": 630,
                 "expiry": "2026-08-21", "side": +1, "qty": 1,
                 "nbbo": {"bid": 8.00, "ask": 8.40}, "iv": 0.20, "delta": 0.55,
                 "gamma": 0.01, "vega": 0.45, "theta_day": -0.05}]
        return [ProposedCombo(kind="atm_call_calendar", underlying="SPY", legs=legs,
                              signal={"trigger": "scripted"})]

    def manage(self, pos, ctx):
        return None                       # never self-exits: the day-roll path must handle it


def _calendar_core(tmp_path, monkeypatch, day, hub=None):
    strat = CalendarStrategy()
    sid = strat.META.strategy_id
    monkeypatch.setattr(rsl, "build_all", lambda: {sid: strat})
    monkeypatch.setattr(rsl, "load_state", lambda: {sid: {"state": "armed", "cohort_pin": "",
                                                          "note": ""}})
    monkeypatch.setattr(rsl, "upcoming_events", lambda now: [])
    monkeypatch.setattr(rsl, "in_blackout", lambda now, events=None: None)
    return rsl.StrategyLabCore(runtime_dir=tmp_path, log=lambda m: None,
                               hub=hub or CalendarHub(), now_fn=lambda: day), sid


def test_settlement_prices_only_the_expired_leg_at_intrinsic(tmp_path, monkeypatch):
    """A multi-expiry combo (the ATM calendar) whose FRONT leg expired while the lab was down.

    The day-roll intrinsic path must settle that front leg against the expiry close and price
    the still-live back leg at its last observed NBBO. Settling BOTH legs at intrinsic invents
    a close for a contract with 27 days of life left, which writes a fabricated P&L into the
    ledger the whole evidence base is graded from.
    """
    core, sid = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM)
    core.tick()                                       # day 1 -> ENTER the calendar
    s = core.ledger.strategy(sid)
    entry = _read(s.entries_path)[0]
    assert entry["grading"]["basis"] == "debit" and entry["grading"]["denom_usd"] == 380.0
    # worst debit: short front sells at bid 4.60, long back buys at ask 8.40 -> 3.80

    # the lab sits down through the front expiry; the next session is the following Monday
    next_mon = datetime(2026, 7, 27, 10, 0, tzinfo=NY)
    core.now_fn = lambda: next_mon
    core.hub.asof = "2026-07-27"                      # provider's "today" advances with the clock
    core.tick()
    exits = _read(s.exits_path)
    assert len(exits) == 1
    x = exits[0]
    assert x["rule"] == "expiry_settlement"
    close = {l["occ"]: l for l in x["legs_close"]}
    # front leg: settled at intrinsic (632 - 630 = 2.00), identical on all three ledgers
    assert close["OCC_FRONT"]["fills"] == {"worst": 2.0, "base": 2.0, "optimistic": 2.0}
    # back leg: still live -> priced off its NBBO, NOT at intrinsic
    assert close["OCC_BACK"]["fills"] != {"worst": 2.0, "base": 2.0, "optimistic": 2.0}
    assert close["OCC_BACK"]["fills"]["worst"] == 8.00      # long leg closes by selling at bid
    # net_close worst = -2.00 (front) + 8.00 (back) = 6.00 ; entry debit 3.80 -> pnl +220
    assert x["ledgers"]["worst"]["net_pnl_usd"] == 220.0
    # the mixed settlement is self-describing: which legs settled, which were marked
    assert x["state"]["settled_legs"] == ["OCC_FRONT"]
    assert x["state"]["live_legs_at_last_nbbo"] == ["OCC_BACK"]


def test_fully_expired_combo_prices_each_leg_at_its_own_expiry_close(tmp_path, monkeypatch):
    """Once EVERY leg has expired, each still settles at intrinsic - but at ITS OWN expiry-day
    close. The front (2026-07-24) and back (2026-08-21) legs die on different days with
    different closes, so pricing both off one close is the same fabrication as pricing a live
    leg at intrinsic. This is the case the original all-expired test could NOT see: it gave both
    expiries the SAME close, so a single-close implementation passed it by accident."""
    hub = CalendarHub(asof="2026-08-24")
    hub.bars = {"2026-07-24": 632.0, "2026-08-21": 640.0}      # different closes per expiry
    core, sid = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM, hub=hub)
    core.tick()
    s = core.ledger.strategy(sid)
    core.now_fn = lambda: datetime(2026, 8, 24, 10, 0, tzinfo=NY)     # both legs now expired
    core.tick()
    x = _read(s.exits_path)[0]
    close = {l["occ"]: l for l in x["legs_close"]}
    # front: intrinsic 632 - 630 = 2.00 ; back: intrinsic 640 - 630 = 10.00 - each off its own day
    assert close["OCC_FRONT"]["fills"] == {"worst": 2.0, "base": 2.0, "optimistic": 2.0}
    assert close["OCC_BACK"]["fills"] == {"worst": 10.0, "base": 10.0, "optimistic": 10.0}
    # net_close worst = -2.00 (short front) + 10.00 (long back) = 8.00 ; entry debit 3.80 -> +420
    assert x["ledgers"]["worst"]["net_pnl_usd"] == 420.0
    assert x["state"]["settled_legs"] == ["OCC_BACK", "OCC_FRONT"]
    assert x["state"]["live_legs_at_last_nbbo"] == []
    # the per-expiry prices are recorded explicitly, not inferred from a single S
    assert x["state"]["settle_prices"] == {"OCC_BACK": 640.0, "OCC_FRONT": 632.0}
    assert x["state"]["settle_S"] == 640.0                       # headline S = latest expiry
    assert x["S"] == 640.0


def test_same_expiry_combo_settles_every_leg_at_one_close(tmp_path, monkeypatch):
    """Unchanged path: a single-expiry combo (the CNDR condor / weekly putwrite / 0DTE IC shape)
    still prices every leg off one expiry-day close, and the record's state is untouched by the
    per-expiry plumbing - `settled_legs` lists every leg, `live_legs_at_last_nbbo` is empty."""
    hub = CalendarHub(asof="2026-07-24")
    hub.bars = {"2026-07-24": 632.0}
    core, sid = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM, hub=hub)
    core.tick()
    s = core.ledger.strategy(sid)
    # collapse both legs onto the SAME expiry: rewrite the entry's back leg to the front date
    entries = _read(s.entries_path)
    entries[0]["legs"][1]["expiry"] = "2026-07-24"
    (s.entries_path).write_text("\n".join(json.dumps(r) for r in entries) + "\n", encoding="utf-8")
    core2, sid2 = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM, hub=hub)
    core2.now_fn = lambda: datetime(2026, 7, 27, 10, 0, tzinfo=NY)
    core2.tick()
    x = _read(core2.ledger.strategy(sid2).exits_path)[0]
    close = {l["occ"]: l for l in x["legs_close"]}
    for occ in ("OCC_FRONT", "OCC_BACK"):
        assert close[occ]["fills"] == {"worst": 2.0, "base": 2.0, "optimistic": 2.0}
    # net_close = -2.00 + 2.00 = 0 -> pnl = (0 - 3.80) * 100
    assert x["ledgers"]["worst"]["net_pnl_usd"] == -380.0
    assert x["state"]["settled_legs"] == ["OCC_BACK", "OCC_FRONT"]
    assert x["state"]["live_legs_at_last_nbbo"] == []


def test_missing_earlier_expiry_close_defers(tmp_path, monkeypatch):
    """The honest failure: an earlier expiry's close is not retrievable (outside the provider's
    history) while a later one is. The settlement must DEFER, not price the front leg off the
    later close. This is the exact fabrication the fix exists to stop, and the deferral is a
    real terminal risk - a month-old front expiry may never come back."""
    hub = CalendarHub(asof="2026-08-24")
    hub.bars = {"2026-08-21": 640.0}                  # only the LATER expiry is available
    core, sid = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM, hub=hub)
    core.tick()
    s = core.ledger.strategy(sid)
    core.now_fn = lambda: datetime(2026, 8, 24, 10, 0, tzinfo=NY)
    core.tick()
    assert _read(s.exits_path) == []                  # nothing fabricated
    deferred = [r for r in _read(s.journal_path) if r.get("event") == "settlement_deferred"]
    assert deferred, "missing expiry close must journal a deferral"
    assert deferred[-1]["missing_expiry_close"] == ["OCC_FRONT"]
    assert deferred[-1]["expired"] == ["OCC_BACK", "OCC_FRONT"]
    assert len(core.positions[sid]) == 1              # position stays open for the next day-roll


def test_partial_settlement_defers_when_a_live_leg_has_no_quote(tmp_path, monkeypatch):
    """No fabricated price: with a live leg unpriced the settlement is deferred and journaled,
    and the position stays on the books for the next day-roll - the front leg's own expiry close
    being available does not license guessing the live leg's mark."""
    core, sid = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM)
    core.tick()
    s = core.ledger.strategy(sid)
    core.hub.book.pop("OCC_BACK")                     # quote feed never saw the back leg
    core.now_fn = lambda: datetime(2026, 7, 27, 10, 0, tzinfo=NY)
    core.hub.asof = "2026-07-27"
    core.tick()
    assert _read(s.exits_path) == []                  # nothing invented
    deferred = [r for r in _read(s.journal_path) if r.get("event") == "settlement_deferred"]
    assert deferred and deferred[-1]["expired"] == ["OCC_FRONT"]
    assert "NBBO" in deferred[-1]["detail"]
    assert any(p.position_id for p in core.positions.get(sid, []))


def test_old_front_expiry_is_reachable_within_the_lookback(tmp_path, monkeypatch):
    """Lookback honesty (the other half of the bug): the old code asked for `days=10`
    (calendar days) and could not see a front expiry a month old, so the settlement would defer
    forever even though the bar exists. The window is now sized from the expiry's age, so a
    47-day-old front expiry is actually fetched and settled."""
    hub = CalendarHub(asof="2026-08-24")
    hub.bars = {"2026-07-08": 700.0, "2026-08-21": 640.0}     # front is 47 days old
    core, sid = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM, hub=hub)
    core.tick()
    s = core.ledger.strategy(sid)
    # retarget the front leg to the 47-day-old expiry so it is far outside a days=10 window
    entries = _read(s.entries_path)
    entries[0]["legs"][0]["expiry"] = "2026-07-08"
    s.entries_path.write_text("\n".join(json.dumps(r) for r in entries) + "\n", encoding="utf-8")
    core2, sid2 = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM, hub=hub)
    core2.now_fn = lambda: datetime(2026, 8, 24, 10, 0, tzinfo=NY)
    core2.tick()
    exits = _read(core2.ledger.strategy(sid2).exits_path)
    assert exits, "old front expiry must be reachable, not deferred"
    close = {l["occ"]: l for l in exits[0]["legs_close"]}
    # front 700 - 630 = 70 intrinsic off its OWN 2026-07-08 close
    assert close["OCC_FRONT"]["fills"]["worst"] == 70.0
    assert exits[0]["state"]["settle_prices"]["OCC_FRONT"] == 700.0




@pytest.mark.parametrize("invalid", [0, -1, float("nan"), float("inf"), "bad"])
def test_invalid_expiry_close_defers_instead_of_fabricating_pnl(tmp_path, monkeypatch, invalid):
    core, sid = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM)
    core.tick()
    core.hub.asof = "2026-07-27"
    core.hub.bars["2026-07-24"] = invalid
    core.now_fn = lambda: datetime(2026, 7, 27, 10, 0, tzinfo=NY)
    core.tick()
    assert _read(core.ledger.strategy(sid).exits_path) == []
    assert core.positions[sid]


@pytest.mark.parametrize("nbbo", [(9, 8, 0), (8, float("nan"), 0), (8, 9, -1), (8, 9)])
def test_invalid_live_quote_defers_settlement(tmp_path, monkeypatch, nbbo):
    core, sid = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM)
    core.tick()
    core.hub.asof = "2026-07-27"
    original = core.hub.last_nbbo
    core.hub.last_nbbo = lambda occ: nbbo if occ == "OCC_BACK" else original(occ)
    core.now_fn = lambda: datetime(2026, 7, 27, 10, 0, tzinfo=NY)
    core._settle_expired("2026-07-27")
    assert _read(core.ledger.strategy(sid).exits_path) == []
    assert core.positions[sid]


def test_stale_exit_quote_is_allowed_but_its_age_is_recorded(tmp_path, monkeypatch):
    core, sid = _calendar_core(tmp_path, monkeypatch, MONDAY_10AM)
    core.tick()
    core.hub.asof = "2026-07-27"
    original = core.hub.last_nbbo
    core.hub.last_nbbo = lambda occ: (8, 8.4, 3600) if occ == "OCC_BACK" else original(occ)
    core.now_fn = lambda: datetime(2026, 7, 27, 10, 0, tzinfo=NY)
    core.tick()
    exit = _read(core.ledger.strategy(sid).exits_path)[0]
    assert exit["state"]["live_leg_quote_ages_s"] == {"OCC_BACK": 3600}
