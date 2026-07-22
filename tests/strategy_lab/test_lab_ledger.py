"""LabLedger - per-strategy dirs, fail-closed rebuild, foreign-row guard, torn-tail append
(lab-strategy-runtime-v1). All disk work under tmp_path; no runtime/ writes."""

from __future__ import annotations

import pytest

from atlas.strategy_lab.ledger import LabLedger, LedgerUnreadable
from atlas.strategy_lab.model import build_combo_exit_record

from .conftest import leg, make_entry


def _entry(sid, pid_seq=0, day="2026-07-20"):
    legs = [leg("P1", "put", 610, -1, bid=4.0, ask=4.4), leg("P2", "put", 600, +1, bid=2.6, ask=3.0)]
    return make_entry(legs, strategy_id=sid, declared_basis="max_loss", day=day,
                      position_id=f"{sid}:SPY:{day}:600:{pid_seq}")


def test_layout_and_round_trip(tmp_path):
    lab = LabLedger(tmp_path)
    s = lab.strategy("strat_a")
    rec = _entry("strat_a")
    s.write_entry(rec)
    assert (tmp_path / "strategy_lab" / "strat_a" / "entries.jsonl").exists()
    open_pos = s.open_positions()
    assert len(open_pos) == 1 and open_pos[0].position_id == rec["position_id"]


def test_exit_removes_from_open(tmp_path):
    lab = LabLedger(tmp_path)
    s = lab.strategy("strat_a")
    rec = _entry("strat_a")
    s.write_entry(rec)
    from atlas.strategy_lab.model import combo_from_entry
    pos = combo_from_entry(rec)
    x = build_combo_exit_record(ts=rec["ts_epoch"] + 60, day=rec["day"], pos=pos, rule="t",
                                legs_close=[{"occ": "P1", "bid": 4.0, "ask": 4.2},
                                            {"occ": "P2", "bid": 2.7, "ask": 2.9}],
                                S=630.0, state={}, hold_trading_days=0.1)
    s.write_exit(x)
    assert s.open_positions() == []


def test_foreign_strategy_row_rejected(tmp_path):
    lab = LabLedger(tmp_path)
    s = lab.strategy("strat_a")
    rec = _entry("strat_b")            # wrong strategy's record
    with pytest.raises(ValueError, match="foreign_strategy_row"):
        s.write_entry(rec)


def test_malformed_entry_skipped_never_crashes(tmp_path):
    lab = LabLedger(tmp_path)
    s = lab.strategy("strat_a")
    s.write_entry(_entry("strat_a"))
    # append garbage + a malformed-but-json entry directly
    p = s.entries_path
    with open(p, "a", encoding="utf-8") as fh:
        fh.write('{"event": "lab_entry", "position_id": "broken"}\n')
        fh.write("not json at all\n")
    assert len(s.open_positions()) == 1   # good row survives, junk quarantined


def test_unreadable_exits_fail_closed(tmp_path):
    lab = LabLedger(tmp_path)
    s = lab.strategy("strat_a")
    s.write_entry(_entry("strat_a"))
    # simulate an unreadable exits file (exists but read fails): a DIRECTORY at the path
    s.exits_path.mkdir(parents=True)
    with pytest.raises(LedgerUnreadable):
        s.open_positions()


def test_torn_tail_guard_inherited(tmp_path):
    lab = LabLedger(tmp_path)
    s = lab.strategy("strat_a")
    s.write_entry(_entry("strat_a", 0))
    # tear the tail (crash between write and fsync)
    with open(s.entries_path, "a", encoding="utf-8") as fh:
        fh.write('{"torn": tru')
    s.write_entry(_entry("strat_a", 1))
    assert len(s.open_positions()) == 2   # torn fragment quarantined, both real rows read


def test_open_positions_all_and_known_dirs(tmp_path):
    lab = LabLedger(tmp_path)
    lab.strategy("strat_a").write_entry(_entry("strat_a"))
    lab.strategy("strat_b").write_entry(_entry("strat_b"))
    lab.write_quote("2026-07-20", {"event": "lab_quote", "occ": "P1", "bid": 4, "ask": 4.2})
    assert lab.known_strategy_dirs() == ["strat_a", "strat_b"]    # quotes dir excluded
    allpos = lab.open_positions_all()
    assert {k: len(v) for k, v in allpos.items()} == {"strat_a": 1, "strat_b": 1}
