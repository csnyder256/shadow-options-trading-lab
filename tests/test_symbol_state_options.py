"""WS3 proof, part C (symbol_state revival): the pure state_reasons() the runner will call to feed
the selector's underlying_{state} gate - fail-open freshness contract, and the exact reason strings
the selector consumes (halted -> underlying_halted, sec_suspended -> underlying_sec_suspended)."""

from __future__ import annotations

import atlas.collect.symbol_state as ss


def test_halt_asserted_only_on_fresh_data():
    snap = {"halts": {"ABC": {"ts_epoch": 1000.0}}}
    assert "halted" in ss.state_reasons("ABC", snap, 1000.0 + 60, max_age_s=180)   # fresh
    assert ss.state_reasons("ABC", snap, 1000.0 + 600, max_age_s=180) == []        # stale -> fail-open
    assert ss.state_reasons("ABC", snap, 1000.0 - 600, max_age_s=180) == []        # future-dated -> stale
    assert ss.state_reasons("XYZ", snap, 1000.0, max_age_s=180) == []              # unknown symbol


def test_suspension_expires_by_release_date_not_wall_age():
    snap = {"suspensions": {"SUS": {"released_epoch": 2000.0}}}
    assert "sec_suspended" in ss.state_reasons("SUS", snap, 1500.0)                # before release
    assert ss.state_reasons("SUS", snap, 2500.0) == []                            # after release -> clears


def test_reason_strings_match_selector_gate_codes():
    snap = {"halts": {"H": {"ts_epoch": 100.0}}, "suspensions": {"S": {"released_epoch": 999.0}}}
    # these are the exact strings the runner threads into select_contract(underlying_state=...)
    assert set(ss.state_reasons("H", snap, 120.0)) == {"halted"}
    assert set(ss.state_reasons("S", snap, 500.0)) == {"sec_suspended"}


def test_empty_snapshot_is_fail_open():
    assert ss.state_reasons("ABC", {}, 1000.0) == []
    assert ss.state_reasons("", {"halts": {}}, 1000.0) == []


def test_state_reasons_is_total_on_wrong_type_snapshots():
    # refute E7: valid JSON but WRONG TYPE (non-Mapping snapshot, or non-Mapping sub-values) must
    # fail-open to [] and NEVER raise - the crash the skeptic found.
    for bad in (None, [1, 2, 3], "halted", 123, {"halts": "XYZ"}, {"suspensions": [1]}, {"ssr": 5}):
        assert ss.state_reasons("ABC", bad, 1000.0) == []
