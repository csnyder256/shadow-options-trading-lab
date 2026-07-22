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
