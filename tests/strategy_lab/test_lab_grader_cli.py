"""Golden-fixture grader CLI test (lab-strategy-runtime-v1): a 2-strategy fixture ledger tree
with hand-computable wealth; every falsification gate exercised by injecting one violation.
Runs main() in-process against tmp_path (no runtime/ writes)."""

from __future__ import annotations

import json

from scripts.grade_strategy_lab import main as grade_main
from atlas.strategy_lab.ledger import LabLedger
from atlas.strategy_lab.model import build_combo_exit_record, combo_from_entry

from .conftest import leg, make_entry


def _trade(lab, sid, seq, close, day="2026-07-20"):
    """One debit-vertical round trip. close=(long_bid, long_ask, short_bid, short_ask)."""
    legs = [leg("C1", "call", 630, +1, bid=10.0, ask=10.4),
            leg("C2", "call", 640, -1, bid=5.0, ask=5.4)]
    rec = make_entry(legs, strategy_id=sid, day=day,
                     position_id=f"{sid}:SPY:{day}:600:{seq}")
    s = lab.strategy(sid)
    s.write_entry(rec)
    pos = combo_from_entry(rec)
    x = build_combo_exit_record(
        ts=rec["ts_epoch"] + 3600, day=day, pos=pos, rule="test",
        legs_close=[{"occ": "C1", "bid": close[0], "ask": close[1]},
                    {"occ": "C2", "bid": close[2], "ask": close[3]}],
        S=634.0, state={}, hold_trading_days=1.0)
    s.write_exit(x)
    return rec, x


def test_grader_golden_fixture(tmp_path, capsys):
    lab = LabLedger(tmp_path)
    # strat_win: two identical +20-worst trades (r = 20/540 each)
    _trade(lab, "strat_win", 0, (12.0, 12.4, 6.0, 6.4))
    _trade(lab, "strat_win", 1, (12.0, 12.4, 6.0, 6.4))
    # strat_lose: one losing trade - close worst: sell C1 at 7.0, buy C2 back at 2.8
    # -> net_close 4.2 vs entry 5.4 -> worst pnl = -120
    _trade(lab, "strat_lose", 0, (7.0, 7.4, 2.4, 2.8))

    rc = grade_main(["--runtime-dir", str(tmp_path), "--day", "2026-07-20"])
    assert rc == 0
    card = json.loads((tmp_path / "strategy_lab" / "scorecard.json").read_text(encoding="utf-8"))

    win = card["strategies"]["strat_win"]
    assert all(not v for v in win["gates"].values()), win["gates"]
    ev = list(win["evidence"].values())[0]
    r = 20.0 / 540.0
    expected = sum((1 + lam * r) ** 2 for lam in (0.05, 0.10, 0.20)) / 3.0
    assert abs(ev["wealth_for"] - round(expected, 4)) < 1e-4
    assert ev["n"] == 2 and win["verdict"] == "UNPROVEN"   # far below N=25
    assert win["day_net_worst_usd"] == 40.0

    lose = card["strategies"]["strat_lose"]
    ev_l = list(lose["evidence"].values())[0]
    r_l = -120.0 / 540.0
    expected_l = sum((1 - lam * r_l) for lam in (0.05, 0.10, 0.20)) / 3.0
    assert abs(ev_l["wealth_against"] - round(expected_l, 4)) < 1e-4
    assert card["pid_collisions"] == []
    # daily returns appended for the correlation block
    rows = (tmp_path / "strategy_lab" / "daily_returns.jsonl").read_text(encoding="utf-8")
    assert rows.count('"day":"2026-07-20"') == 2


def test_grader_gates_fire(tmp_path):
    lab = LabLedger(tmp_path)
    rec, x = _trade(lab, "strat_bad", 0, (12.0, 12.4, 6.0, 6.4))
    s = lab.strategy("strat_bad")
    # duplicate exit (same position_id)
    s.write_exit(dict(x, ts_epoch=x["ts_epoch"] + 10))
    # identity violation: corrupt worst above optimistic
    bad = json.loads(json.dumps(x))
    bad["position_id"] = f"strat_bad:SPY:2026-07-20:600:9"
    bad["ledgers"]["worst"]["net_pnl_usd"] = 999.0
    ent2 = make_entry([leg("C1", "call", 630, +1, bid=10.0, ask=10.4),
                       leg("C2", "call", 640, -1, bid=5.0, ask=5.4)],
                      strategy_id="strat_bad", position_id=bad["position_id"])
    s.write_entry(ent2)
    s.write_exit(bad)
    # denominator drift: tamper the frozen denom on a third trade
    rec3, x3 = _trade(lab, "strat_bad", 2, (12.0, 12.4, 6.0, 6.4))

    rc = grade_main(["--runtime-dir", str(tmp_path)])
    assert rc == 0
    card = json.loads((tmp_path / "strategy_lab" / "scorecard.json").read_text(encoding="utf-8"))
    g = card["strategies"]["strat_bad"]["gates"]
    assert g["duplicate_exits"] != []
    assert g["ledger_identity_violations"] != []
    assert card["strategies"]["strat_bad"]["verdict"] == "BROKEN"


def test_grader_validate_mode(tmp_path, capsys):
    lab = LabLedger(tmp_path)
    _trade(lab, "strat_ok", 0, (12.0, 12.4, 6.0, 6.4))
    rc = grade_main(["--runtime-dir", str(tmp_path), "--validate"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["validate"][0]["tier1"] == "PASS"

    # tamper a recorded open fill -> Tier-1 FAIL and exit 1
    s = lab.strategy("strat_ok")
    rows = [json.loads(l) for l in s.entries_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["legs"][0]["fills"]["worst"] = 99.0
    s.entries_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    rc = grade_main(["--runtime-dir", str(tmp_path), "--validate"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert out["validate"][0]["tier1"] == "FAIL"


def test_grader_wires_exposure_block(tmp_path):
    """opts-lab-exposure-wire-v1: an OPEN combo populates scorecard.cross.exposure (Phase-8)."""
    lab = LabLedger(tmp_path)
    # one open (entry, no exit) short-delta position so the aggregate Greeks are non-trivial
    legs = [leg("C1", "call", 640, -1, bid=3.5, ask=3.7, delta=-0.16, vega=0.4, theta_day=-0.05)]
    rec = make_entry(legs, strategy_id="strat_open", declared_basis="car",
                     position_id="strat_open:SPY:2026-07-20:600:0")
    lab.strategy("strat_open").write_entry(rec)
    rc = grade_main(["--runtime-dir", str(tmp_path)])
    assert rc == 0
    card = json.loads((tmp_path / "strategy_lab" / "scorecard.json").read_text(encoding="utf-8"))
    assert "cross" in card and "exposure" in card["cross"]
    exp = card["cross"]["exposure"]
    assert "net_delta_dollars" in exp and "net_vega" in exp and "per_underlying" in exp
    assert exp["gross_delta_dollars"] > 0     # the open position registered exposure
    assert "correlation" in card["cross"]


def test_funnel_warmup_guard(tmp_path):
    """lab-funnel-warmup-guard-v1: a zero-fire ARMED low-frequency strategy reads WARMUP
    (action NONE) before enough lab sessions elapse to expect >=1 fire, and reverts to
    DEAD/INVESTIGATE-FUNNEL once the elapsed window can hold an expected fire. Frequency-aware:
    a HIGH-frequency strategy is never suppressed. Proves the day-1/day-2 false-alarm fix and
    that the >=20-session behaviour is byte-identical."""
    from scripts.grade_strategy_lab import grade_strategy
    lab = LabLedger(tmp_path)
    lo = {"cohort": "warm00000000", "expected_fires_per_20": 4.0, "armed": True}  # weekly-ish
    # 2 elapsed sessions -> 4*2/20 = 0.4 expected fires -> WARMUP, no defect action
    b2 = grade_strategy("lowfreq", lab, lo, day="2026-07-21", lab_sessions_elapsed=2)
    assert b2["funnel"]["health"] == "WARMUP"
    assert b2["action"] == "NONE"
    assert b2["funnel"]["expected_over_elapsed"] == 0.4
    # 25 elapsed sessions -> 4*1.0 = 4.0 expected fires -> DEAD preserved (byte-identical)
    b25 = grade_strategy("lowfreq", lab, lo, day="2026-07-21", lab_sessions_elapsed=25)
    assert b25["funnel"]["health"] == "DEAD"
    assert b25["action"] == "INVESTIGATE-FUNNEL"
    # a DAILY strategy (expected 20/20) is NOT suppressed even at 2 sessions (2.0 >= 1)
    hi = {"cohort": "hi0000000000", "expected_fires_per_20": 20.0, "armed": True}
    bhi = grade_strategy("lowfreq", lab, hi, day="2026-07-21", lab_sessions_elapsed=2)
    assert bhi["funnel"]["health"] == "DEAD"
    assert bhi["action"] == "INVESTIGATE-FUNNEL"
    # missing session count -> conservative: no suppression change vs legacy (DEAD)
    bnone = grade_strategy("lowfreq", lab, lo, day="2026-07-21")
    assert bnone["funnel"]["health"] == "DEAD"
    # BOUNDARY: a sub-1-cadence strategy (expected in (0,1), e.g. a quarterly/rare-event)
    # must NOT be silenced forever. WARMUP only inside the trailing-20 window; DEAD once full.
    sub = {"cohort": "sub000000000", "expected_fires_per_20": 0.9, "armed": True}
    assert grade_strategy("lowfreq", lab, sub, day="2026-07-21",
                          lab_sessions_elapsed=2)["funnel"]["health"] == "WARMUP"   # in-window
    for elapsed in (20, 25, 100):  # window full -> guard is a no-op -> DEAD, not WARMUP
        b = grade_strategy("lowfreq", lab, sub, day="2026-07-21", lab_sessions_elapsed=elapsed)
        assert b["funnel"]["health"] == "DEAD", (elapsed, b["funnel"])
        assert b["action"] == "INVESTIGATE-FUNNEL"


def test_grader_pid_collision_lab_wide(tmp_path):
    lab = LabLedger(tmp_path)
    rec, _ = _trade(lab, "strat_a", 0, (12.0, 12.4, 6.0, 6.4))
    # same position_id planted in another strategy's entries (bypass writer guard by editing sid)
    clone = json.loads(json.dumps(rec))
    clone["strategy_id"] = "strat_b"
    lab.strategy("strat_b").write_entry(clone)
    rc = grade_main(["--runtime-dir", str(tmp_path)])
    assert rc == 0
    card = json.loads((tmp_path / "strategy_lab" / "scorecard.json").read_text(encoding="utf-8"))
    assert card["pid_collisions"] != []
