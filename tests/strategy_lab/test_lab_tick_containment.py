"""A failing tick never kills the strategy-lab process (opts-fix-lab-tick-containment-v1).

`main()` called `core.tick()` bare, so ANY exception raised inside a tick escaped the loop and
ended the process. The lab's own fault-containment story covers strategy calls only
(`StrategyLabCore._wrap` + quarantine); runner-side work runs outside it - the mark/exit ledger
appends in `_manage_positions`/`_close_position`, the day-roll settlement's `write_exit`, and the
builders' `ValueError`s on a malformed leg or a foreign ledger row. A raise from any of those is
fatal to the whole run.

That matters because of how the lab is supervised: `scripts/launch_strategy_lab.ps1` respawns at
most three times, then pages and GIVES UP FOR THE DAY ("lab died N times - paging and giving up
for the day"). So one transient failure - a locked/unwritable ledger file, one corrupt row -
cost the rest of the session: no marks, no entries, and expiry-day combos riding past the global
backstop. The sibling runner this skeleton was cloned from has contained every tick since the
equity era (`run_options_shadow.main`: "one bad tick never kills the process"); the lab did not.

These tests fail on the pre-fix code (`main()` propagates the exception out of the loop) and pass
after it: the loop keeps ticking, the failure is logged and journaled once per consecutive
stretch, recovery is journaled, and the single-shot `--once` probe reports the failure instead of
exiting 0.
"""

from __future__ import annotations

import json
import time

import pytest

import scripts.run_strategy_lab as rsl

STOP = "STOP_LAB.flag"


def _rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _journal_events(tmp_path, kinds=("tick_error", "tick_recovered")):
    return [r for r in _rows(tmp_path / "strategy_lab" / "lab_journal.jsonl")
            if r.get("event") in kinds]


@pytest.fixture
def fast(monkeypatch):
    """No real sleeping: the loop's interval is 1s minimum."""
    monkeypatch.setattr(time, "sleep", lambda _s: None)


def test_a_failing_tick_does_not_kill_the_runner(tmp_path, monkeypatch, fast):
    """Three failing ticks then a healthy one: the process survives and keeps ticking.

    The failure is a real runner-side one - an OSError from a ledger append (locked/unwritable
    file) - which is exactly what used to escape main() and end the run.
    """
    calls = {"n": 0}

    def scripted_tick(self):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise PermissionError("simulated locked ledger file")
        (tmp_path / STOP).write_text("stop", encoding="utf-8")   # let the loop exit cleanly

    monkeypatch.setattr(rsl.StrategyLabCore, "tick", scripted_tick)

    rc = rsl.main(["--no-hub", "--interval", "0.01", "--runtime-dir", str(tmp_path)])

    assert rc == 0                       # a stop flag ends the run; a bad tick does not
    assert calls["n"] == 4               # the loop kept ticking after every failure
    assert not (tmp_path / "strategy_lab.lock").exists()

    run_log = (tmp_path / "strategy_lab_run.log").read_text(encoding="utf-8")
    assert run_log.count("tick error (") == 3          # every occurrence is logged...
    assert "tick error (1): PermissionError: simulated locked ledger file" in run_log
    assert "tick error (3): PermissionError: simulated locked ledger file" in run_log
    assert "tick recovered after 3 failed tick(s)" in run_log
    assert "stop flag STOP_LAB.flag - exiting cleanly" in run_log


def test_tick_failure_is_journaled_once_per_stretch_and_recovery_is_recorded(tmp_path, monkeypatch, fast):
    """The ledger is the auditable surface the EOD report reads, so a failing tick must leave a
    record there - once per consecutive stretch, not once per tick (the run log already carries
    the per-tick line and its count)."""
    calls = {"n": 0}

    def scripted_tick(self):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise ValueError("simulated malformed mark row")
        (tmp_path / STOP).write_text("stop", encoding="utf-8")

    monkeypatch.setattr(rsl.StrategyLabCore, "tick", scripted_tick)

    assert rsl.main(["--no-hub", "--runtime-dir", str(tmp_path)]) == 0

    events = _journal_events(tmp_path)
    assert [e["event"] for e in events] == ["tick_error", "tick_recovered"]
    assert events[0]["where"] == "tick"
    assert events[0]["detail"] == "ValueError: simulated malformed mark row"
    assert events[1]["failed_ticks"] == 3
    assert isinstance(events[0]["ts_epoch"], float)


def test_journal_failure_never_escalates(tmp_path, monkeypatch, fast):
    """The ledger may be exactly what is failing; the journal row is best-effort and the run
    still survives (the run log has the line either way)."""
    calls = {"n": 0}

    def scripted_tick(self):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise OSError("simulated full disk")
        (tmp_path / STOP).write_text("stop", encoding="utf-8")

    def broken_journal(self, rec):
        raise OSError("simulated full disk")

    monkeypatch.setattr(rsl.StrategyLabCore, "tick", scripted_tick)
    monkeypatch.setattr(rsl.LabLedger, "journal", broken_journal)

    assert rsl.main(["--no-hub", "--runtime-dir", str(tmp_path)]) == 0
    assert calls["n"] == 3
    assert (tmp_path / "strategy_lab_run.log").read_text(encoding="utf-8").count("tick error (") == 2


def test_once_reports_a_failed_tick(tmp_path, monkeypatch):
    """`--once` is the single-shot smoke probe: it must not report success for a tick that
    failed, or a broken deployment looks healthy."""
    def boom(self):
        raise RuntimeError("simulated day-roll failure")

    monkeypatch.setattr(rsl.StrategyLabCore, "tick", boom)

    assert rsl.main(["--once", "--no-hub", "--runtime-dir", str(tmp_path)]) == 1
    assert "tick error (1): RuntimeError: simulated day-roll failure" in \
        (tmp_path / "strategy_lab_run.log").read_text(encoding="utf-8")
    assert not (tmp_path / "strategy_lab.lock").exists()     # lock released on the way out


def test_once_still_succeeds_on_a_healthy_tick(tmp_path):
    """No over-containment: a healthy `--once` run is unchanged (exit 0, heartbeat written,
    no failure rows in the journal)."""
    assert rsl.main(["--once", "--no-hub", "--runtime-dir", str(tmp_path)]) == 0
    assert (tmp_path / "strategy_lab_heartbeat.json").exists()
    assert _journal_events(tmp_path) == []
    assert "tick error" not in (tmp_path / "strategy_lab_run.log").read_text(encoding="utf-8")
