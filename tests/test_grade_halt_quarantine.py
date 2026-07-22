"""WS3 proof, part B (opts-fix-grade-halt-quarantine-v1): a position whose ENTRY carries the
underlying_halted risk-flag is quarantined out of lane stats (un-fillable phantom), parallel to the
malformed / identity-violation quarantines, and surfaced in the scorecard."""

from __future__ import annotations

from atlas.options.shadow import ShadowLedger
from scripts.grade_options_shadow import grade
from tests.test_grade_options_shadow import DAY, _mk_trade


def test_halted_underlying_entry_is_quarantined(tmp_path):
    led = ShadowLedger(tmp_path)
    # a normal graded winner ...
    _mk_trade(led, "GOOD", entry_nbbo={"bid": 1.00, "ask": 1.10},
              exit_nbbo={"bid": 1.80, "ask": 1.90}, rule="d_take_profit",
              lanes=["index_trend"], risk_flags=[])
    # ... and a phantom recorded on a halted underlying (identical fills) - must NOT pool in
    _mk_trade(led, "HALT", entry_nbbo={"bid": 1.00, "ask": 1.10},
              exit_nbbo={"bid": 1.80, "ask": 1.90}, rule="d_take_profit",
              lanes=["index_trend"], risk_flags=["underlying_halted"])

    card = grade(led, day=DAY)
    assert card["halted_underlying_exits"] == ["HALT"]           # quarantined + surfaced
    assert card["ledger_identity_violations"] == []
    lane = card["lanes"]["index_trend"]
    assert lane["n"] == 1                                        # ONLY the good trade graded
    # if HALT had pooled in, the winner would double: prove it did not
    assert lane["net_worst_sum"] == 70.0                        # one winner (1.80-1.10)*100, not 140
