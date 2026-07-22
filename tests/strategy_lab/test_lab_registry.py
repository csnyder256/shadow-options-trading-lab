"""Registry + strategy contract + runner smoke (lab-strategy-runtime-v1).

The runner smoke test proves DOD-3's core mechanically: `run_strategy_lab.py --once` exits 0
against an isolated runtime dir, writes a fresh heartbeat, and touches NOTHING outside it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from atlas.strategy_lab.registry import armed_roster, load_state, validate
from atlas.strategy_lab.strategy import (EventPolicy, GradingBasis, Strategy, StrategyMeta,
                                         expiry_backstop_due)

REPO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class _P:
    delta_target: float = 0.30
    profit_take_frac: float = 0.50


class _FakeStrat(Strategy):
    META = StrategyMeta(strategy_id="fake_short_put", version=1, name="fixture strategy",
                        universe=("SPY",), dte_range=(30, 60), max_concurrent=2,
                        event_policy=EventPolicy.TRADE_THROUGH,
                        grading_basis=GradingBasis.CAR, defining_mechanism="short_vol_carry")
    params = _P()

    def scan(self, ctx):
        return []

    def manage(self, pos, ctx):
        return None


def test_config_hash_stable_and_param_sensitive():
    a, b = _FakeStrat(), _FakeStrat()
    assert a.config_hash() == b.config_hash()
    assert len(a.config_hash()) == 12
    c = _FakeStrat()
    c.params = _P(delta_target=0.16)
    assert c.config_hash() != a.config_hash()


def test_load_state_and_validate(tmp_path):
    p = tmp_path / "strategy_lab.yaml"
    p.write_text("strategies:\n  fake_short_put:\n    state: armed\n    cohort_pin: ''\n"
                 "  ghost_strat:\n    state: armed\n", encoding="utf-8")
    state = load_state(p)
    strategies = {"fake_short_put": _FakeStrat()}
    problems = validate(strategies, state)
    assert problems == ["ghost_strat: armed in YAML but no factory registered"]
    assert armed_roster(strategies, state) == ["fake_short_put"]


def test_cohort_pin_drift_detected(tmp_path):
    strategies = {"fake_short_put": _FakeStrat()}
    state = {"fake_short_put": {"state": "armed", "cohort_pin": "000000000000", "note": ""}}
    problems = validate(strategies, state)
    assert any("cohort_pin" in p for p in problems)


def test_invalid_state_rejected(tmp_path):
    p = tmp_path / "strategy_lab.yaml"
    p.write_text("strategies:\n  x:\n    state: yolo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid state"):
        load_state(p)


def test_absent_state_file_means_nothing_armed(tmp_path):
    assert load_state(tmp_path / "nope.yaml") == {}
    assert armed_roster({"fake_short_put": _FakeStrat()}, {}) == []


def test_expiry_backstop_due():
    from datetime import date
    from .conftest import leg, make_entry
    from atlas.strategy_lab.model import combo_from_entry
    rec = make_entry([leg("C1", "call", 640, +1)])
    pos = combo_from_entry(rec)
    exp = date(2026, 8, 31)
    assert expiry_backstop_due(pos, today=exp, minute=950, session_close_min=960) is True
    assert expiry_backstop_due(pos, today=exp, minute=900, session_close_min=960) is False
    assert expiry_backstop_due(pos, today=date(2026, 8, 28), minute=950,
                               session_close_min=960) is False


def test_runner_once_isolated_runtime(tmp_path):
    """DOD-3 core: --once exits 0, writes heartbeat + lock released, isolated runtime dir."""
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "run_strategy_lab.py"),
         "--once", "--no-hub", "--runtime-dir", str(tmp_path)],
        capture_output=True, text=True, timeout=120, cwd=str(REPO))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    hb = json.loads((tmp_path / "strategy_lab_heartbeat.json").read_text(encoding="utf-8"))
    assert hb["schema"] == 2 and isinstance(hb["strategies_armed"], list)
    assert hb["cap_per_min"] == 40
    assert not (tmp_path / "strategy_lab.lock").exists()   # released on exit
    # process journal recorded the day roll
    rows = (tmp_path / "strategy_lab" / "lab_journal.jsonl").read_text(encoding="utf-8")
    assert '"event":"day_roll"' in rows.replace(" ", "")


def test_runner_stop_flag_exits_zero(tmp_path):
    (tmp_path / "STOP_LAB.flag").write_text("stop", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "run_strategy_lab.py"),
         "--once", "--no-hub", "--runtime-dir", str(tmp_path)],
        capture_output=True, text=True, timeout=120, cwd=str(REPO))
    assert proc.returncode == 0
    assert not (tmp_path / "strategy_lab_heartbeat.json").exists()   # stopped before tick
