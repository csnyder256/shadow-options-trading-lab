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


def test_open_positions_reprimes_observation_state_from_marks(tmp_path):
    """A rebuild must restore the RUNNING excursion and the mark-carried state, not restart them.

    The day-roll rebuilds every open combo from its entry row; `combo_from_entry` starts
    fav_max/fav_min at 0 and carried empty. The mark history is the only record of what the
    position actually observed while it was open, so a position that printed +11% on day 1 and
    closed days later used to report only the closing session's move in `underlying_mfe`/`_mae`
    - and the state every mark carries (the `Strategy.rebuild` contract) was dropped at each
    session boundary. The main shadow's rebuild re-primes exactly these from the same marks.
    """
    from atlas.strategy_lab.model import build_combo_mark_record

    lab = LabLedger(tmp_path)
    s = lab.strategy("strat_a")
    rec = _entry("strat_a")                     # entry reference S = 630 (make_entry default)
    s.write_entry(rec)
    pid = rec["position_id"]
    nb = [{"occ": "P1", "bid": 4.0, "ask": 4.2, "age_s": 1.0},
          {"occ": "P2", "bid": 2.6, "ask": 2.8, "age_s": 1.0}]
    for ts, S, phase in ((rec["ts_epoch"] + 60, 700.0, "ran_up"),
                         (rec["ts_epoch"] + 120, 650.0, "retraced")):
        s.write_mark(build_combo_mark_record(ts=ts, position_id=pid, strategy_id="strat_a",
                                             legs_nbbo=nb, S=S, state={"phase": phase},
                                             action="hold", rule=""))
    pos = s.open_positions()[0]
    # the day-1 extreme (700) survives, not just the last mark (650 -> ~0.0317)
    assert pos.fav_max == pytest.approx(700.0 / 630.0 - 1.0, abs=1e-9)
    assert pos.fav_min == 0.0                   # never traded below the entry reference
    assert pos.last_mark_ts == rec["ts_epoch"] + 120
    assert pos.carried == {"phase": "retraced"}  # carried state rides the marks across a rebuild


def test_open_positions_without_marks_still_rebuild(tmp_path):
    """No mark history (a position entered but not yet marked) must rebuild unchanged."""
    lab = LabLedger(tmp_path)
    s = lab.strategy("strat_a")
    s.write_entry(_entry("strat_a"))
    pos = s.open_positions()[0]
    assert pos.fav_max == 0.0 and pos.fav_min == 0.0 and pos.last_mark_ts == 0.0
    assert pos.carried == {}
