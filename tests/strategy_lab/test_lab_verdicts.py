"""Verdict machine + prune bar + auto-disable transitions (lab-strategy-runtime-v1)."""

from __future__ import annotations

from atlas.strategy_lab.verdicts import auto_disable_check, prune_assessment, verdict_for

ATTR_GOOD = {"loss_driver": "vol", "win_driver": "vol", "coverage": 0.85,
             "loss_shares": {"vol": 0.7, "direction": 0.2, "theta": 0.05,
                             "spread_tax": 0.05, "residual": 0.0}}
ATTR_BAD_COVERAGE = {**ATTR_GOOD, "coverage": 0.41}
ATTR_SPREAD = {**ATTR_GOOD, "loss_driver": "spread_tax"}


def _v(**kw):
    base = dict(gates_clean=True, n=30, wealth_for=1.0, wealth_against=1.0,
                mean_net_usd=10.0, attribution=ATTR_GOOD, funnel_health="OK")
    base.update(kw)
    return verdict_for(**base)


def test_broken_first():
    assert _v(gates_clean=False, wealth_for=100.0)["verdict"] == "BROKEN"


def test_winning_pilot_and_live():
    assert _v(wealth_for=6.0)["action"] == "PILOT-ELIGIBLE"
    assert _v(wealth_for=25.0)["action"] == "SIZED-LIVE-DISCUSSION"
    # below N floor: no verdict regardless of wealth
    assert _v(wealth_for=25.0, n=20)["verdict"] == "UNPROVEN"


def test_losing_paths():
    v = _v(wealth_against=6.0, mean_net_usd=-15.0)
    assert v["verdict"] == "LOSING" and v["action"] == "PRUNE-TRACK"
    # gross-negative rule alone (against-wealth quiet)
    v = _v(wealth_against=1.2, mean_net_usd=-15.0)
    assert v["verdict"] == "LOSING"
    # tunable driver routes to TWEAK-QUEUE, not prune
    v = _v(wealth_against=6.0, mean_net_usd=-15.0, attribution=ATTR_SPREAD)
    assert v["action"] == "TWEAK-QUEUE"
    # unreliable attribution forbids mechanism claims
    v = _v(wealth_against=6.0, mean_net_usd=-15.0, attribution=ATTR_BAD_COVERAGE)
    assert v["action"] == "INVESTIGATE"
    assert any("UNRELIABLE-ATTRIBUTION" in w for w in v["why"])


def test_unproven_and_funnel():
    v = _v(n=5)
    assert v["verdict"] == "UNPROVEN" and v["action"] == "NONE"
    v = _v(n=12)
    assert any("interim" in w for w in v["why"])
    v = _v(n=0, funnel_health="DEAD")
    assert v["action"] == "INVESTIGATE-FUNNEL"


def test_prune_bar_two_parts():
    common = dict(n=30, mean_net_usd=-20.0, coverage=0.8, defining_mechanism="short_vol_carry")
    # (a) full + (b) full -> PRUNE-CANDIDATE
    p = prune_assessment(wealth_against=25.0, loss_driver="vol", sweep_survivors=0, **common)
    assert p["state"] == "PRUNE-CANDIDATE"
    # sweep found a surviving cell -> not prune-eligible
    p = prune_assessment(wealth_against=25.0, loss_driver="vol", sweep_survivors=2, **common)
    assert p["state"] != "PRUNE-CANDIDATE"
    # driver is not a mechanism component -> not prune-eligible
    p = prune_assessment(wealth_against=25.0, loss_driver="spread_tax", sweep_survivors=0, **common)
    assert p["state"] != "PRUNE-CANDIDATE"
    # statistical bar alone (a-lite) -> EARLY-FLAG at least
    p = prune_assessment(wealth_against=6.0, loss_driver=None, sweep_survivors=None,
                         n=30, mean_net_usd=-20.0, coverage=0.3,
                         defining_mechanism="short_vol_carry")
    assert p["state"] in ("EARLY-FLAG", "PRUNE-EVIDENCE-PARTIAL")
    # fork immortality counts as (a)
    p = prune_assessment(wealth_against=2.0, loss_driver="vol", sweep_survivors=0,
                         cohort_forks_against=3, **common)
    assert p["state"] == "PRUNE-CANDIDATE"
    # low coverage blocks the mechanism claim
    p = prune_assessment(wealth_against=25.0, loss_driver="vol", sweep_survivors=0,
                         n=30, mean_net_usd=-20.0, coverage=0.4,
                         defining_mechanism="short_vol_carry")
    assert p["state"] != "PRUNE-CANDIDATE"


def test_auto_disable():
    ok = dict(floor_breaches=0, gate_broken_today=False, gate_broken_streak=0,
              day_net_usd=-100.0, median_denom_usd=900.0)
    assert auto_disable_check(**ok)["disable"] is False
    assert auto_disable_check(**{**ok, "floor_breaches": 1})["disable"] is True
    # gate broken today but streak below 2 -> not yet
    r = auto_disable_check(**{**ok, "gate_broken_today": True})
    assert r["disable"] is False and r["gate_broken_streak"] == 1
    # second consecutive session -> disable
    r2 = auto_disable_check(**{**ok, "gate_broken_today": True, "gate_broken_streak": 1})
    assert r2["disable"] is True
    # streak resets on a clean day
    assert auto_disable_check(**{**ok, "gate_broken_streak": 5})["gate_broken_streak"] == 0
    # day kill line: -3x median denom
    assert auto_disable_check(**{**ok, "day_net_usd": -2800.0})["disable"] is True
