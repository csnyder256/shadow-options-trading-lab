"""Pin the grader<->ledger field contract (O4). Every record here is produced by the REAL
shadow.py builders (build_entry_record / position_from_entry / build_exit_record), so if the
ledger schema and scripts/grade_options_shadow.py ever drift apart again, this suite fails
instead of the scorecard silently grading every lane as all-zero P&L (the 2026-07-09 bug:
the grader read "pnl"/"exit_rule" fields the builders never wrote)."""

from __future__ import annotations

from atlas.options.shadow import (
    ShadowLedger,
    append_jsonl,
    build_entry_record,
    build_exit_record,
    build_quote_record,
    position_from_entry,
)
from scripts.grade_options_shadow import grade

DAY = "2026-07-10"


def _mk_trade(led: ShadowLedger, pid: str, *, entry_nbbo: dict, exit_nbbo: dict, rule: str,
              lanes: list, risk_flags: list, theta_day: float = -0.05, hold: float = 0.5,
              variant: bool = False, mutate_exit=None) -> None:
    """One full hypothetical trade through the real builders."""
    sig = {"lane": lanes[0], "underlying": "SPY", "direction": "call", "target_move": 0.005,
           "p_thesis": 0.5, "horizon_T": 0.001, "mu_thesis": 1.0, "expires_minute": 700,
           "notes": {}}
    pick = {"occ": "SPY260717C00600000", "underlying": "SPY", "opt_type": "call",
            "strike": 600.0, "expiry": "2026-07-17", "S": 600.0, "theta_day": theta_day}
    rec = build_entry_record(ts=1e9, day=DAY, entry_minute=600, position_id=pid, lanes=lanes,
                             config_hash="abc", signal=sig, pick=pick, runner_up_occs=[],
                             nbbo=entry_nbbo, risk_flags=risk_flags)
    led.write_entry(rec)
    pos = position_from_entry(rec)
    assert pos is not None, "position_from_entry must round-trip a builder entry record"
    xrec = build_exit_record(ts=1e9 + 3600, day=DAY, pos=pos, rule=rule,
                             bid=exit_nbbo["bid"], ask=exit_nbbo["ask"], solved_iv=0.2, S=601.0,
                             decision_state={}, variant_would_hold=variant,
                             hold_trading_days=hold)
    if mutate_exit is not None:
        mutate_exit(xrec)
    led.write_exit(xrec)


def test_grader_reads_real_builder_records(tmp_path):
    led = ShadowLedger(tmp_path)
    # winner: buy 1.00/1.10, sell 1.80/1.90 -> worst net (1.80-1.10)*100 = +70, gross +80
    _mk_trade(led, "P1", entry_nbbo={"bid": 1.00, "ask": 1.10},
              exit_nbbo={"bid": 1.80, "ask": 1.90}, rule="d_take_profit",
              lanes=["index_trend"], risk_flags=["spread_gt_5pct"])
    # loser: buy 2.00/2.20, sell 1.00/1.10 -> worst net (1.00-2.20)*100 = -120, gross -105
    _mk_trade(led, "P2", entry_nbbo={"bid": 2.00, "ask": 2.20},
              exit_nbbo={"bid": 1.00, "ask": 1.10}, rule="c_premium_stop",
              lanes=["index_trend"], risk_flags=[], variant=True)

    card = grade(led, day=DAY)
    assert card["malformed_exits"] == []
    assert card["ledger_identity_violations"] == []
    assert card["entries_total"] == 2 and card["exits_total"] == 2

    lane = card["lanes"]["index_trend"]
    assert lane["n"] == 2 and lane["n_today"] == 2
    # the schema-drift failure mode was all-zero P&L - these MUST be the hand-computed values
    assert lane["net_worst_sum"] == -50.0
    assert lane["net_worst_mean"] == -25.0
    assert lane["net_worst_today"] == -50.0
    assert lane["gross_sum"] == -25.0
    assert lane["winrate_worst"] == 0.5
    assert lane["profit_factor_worst"] == round(70.0 / 120.0, 2)
    assert lane["exit_rule_mix"] == {"c_premium_stop": 1, "d_take_profit": 1}
    # risk flags come from the ENTRY record, joined by position_id
    assert lane["risk_flags"] == {"spread_gt_5pct": {"n": 1, "net": 70.0}}
    # falsification #1 (cost visibility): winner half-spreads 0.05+0.05, loser 0.10+0.05 -> $25
    assert lane["spread_paid_total"] == 25.0
    assert lane["cost_share_of_losses"] == round(25.0 / 120.0, 3)
    assert lane["theta_paid_total"] == -5.0          # -0.05/day * 0.5d * 100 * 2 trades
    assert lane["overnight_variant_divergences"] == 1
    assert lane["verdict"] == "ACCUMULATING"         # n < 25


def test_malformed_exit_rows_are_flagged_and_excluded(tmp_path):
    led = ShadowLedger(tmp_path)
    _mk_trade(led, "GOOD", entry_nbbo={"bid": 1.00, "ask": 1.10},
              exit_nbbo={"bid": 0.50, "ask": 0.60}, rule="c_premium_stop",
              lanes=["inplay_orb"], risk_flags=[])
    # the 2026-07-09 phantom schema, verbatim: "pnl"/"exit_rule" instead of "ledgers"/"rule"
    append_jsonl(led.exits_path, {
        "schema": 1, "event": "shadow_exit", "day": DAY, "position_id": "PHANTOM",
        "lanes": ["inplay_orb"], "exit_rule": "h",
        "pnl": {"worst": {"net": 1.0, "gross": 1.0}}})

    card = grade(led, day=DAY)
    assert card["malformed_exits"] == ["PHANTOM"]
    assert card["exits_total"] == 2                  # counted in the total...
    assert card["lanes"]["inplay_orb"]["n"] == 1     # ...but excluded from the stats


def test_identity_violation_detected(tmp_path):
    led = ShadowLedger(tmp_path)

    def _break_identity(xrec: dict) -> None:
        xrec["ledgers"]["worst"]["net_pnl_usd"] = 999.0   # worst grading above optimistic

    _mk_trade(led, "BAD", entry_nbbo={"bid": 1.00, "ask": 1.10},
              exit_nbbo={"bid": 0.50, "ask": 0.60}, rule="h_ev_hold_below_sell",
              lanes=["last30"], risk_flags=[], mutate_exit=_break_identity)

    card = grade(led, day=DAY)
    assert card["ledger_identity_violations"] == ["BAD"]


def test_expired_unexited_graded_at_terminal_intrinsic(tmp_path):
    # OCC auto-exercises >= $0.01 ITM at expiry: a process-gap position held past expiry must
    # surface with a terminal-intrinsic estimate from the expiry day's quote path - never a
    # stale NBBO, never silently dropped, never pooled into lane stats
    led = ShadowLedger(tmp_path)
    sig = {"lane": "index_trend", "underlying": "SPY", "direction": "call",
           "target_move": 0.005, "p_thesis": 0.5, "horizon_T": 0.001, "mu_thesis": 1.0,
           "expires_minute": 700, "notes": {}}
    pick = {"occ": "SPY260717C00600000", "underlying": "SPY", "opt_type": "call",
            "strike": 600.0, "expiry": "2026-07-17", "S": 598.0, "theta_day": -0.05}
    led.write_entry(build_entry_record(ts=1e9, day="2026-07-16", entry_minute=600,
                                       position_id="GAP", lanes=["index_trend"],
                                       config_hash="abc", signal=sig, pick=pick,
                                       runner_up_occs=[], nbbo={"bid": 1.0, "ask": 1.1},
                                       risk_flags=[]))
    led.write_quote("2026-07-17", build_quote_record(ts=1e9 + 86400, occ="SPY260717C00600000",
                                                     bid=11.9, ask=12.1, S=612.0,
                                                     position_id="GAP"))
    card = grade(led, day="2026-07-20")
    assert len(card["expired_unexited"]) == 1
    row = card["expired_unexited"][0]
    assert row["position_id"] == "GAP"
    assert row["est_terminal_intrinsic_usd"] == 1200.0     # (612 - 600) x 100
    assert card["lanes"] == {}                             # NOT pooled into lane stats


def test_merged_multi_lane_exit_grades_in_every_lane(tmp_path):
    led = ShadowLedger(tmp_path)
    _mk_trade(led, "M1", entry_nbbo={"bid": 1.00, "ask": 1.10},
              exit_nbbo={"bid": 0.50, "ask": 0.60}, rule="overnight_evidence_rule",
              lanes=["index_trend", "last30"], risk_flags=[])

    card = grade(led, day=DAY)
    assert card["lanes"]["index_trend"]["n"] == 1
    assert card["lanes"]["last30"]["n"] == 1
    assert card["lanes"]["index_trend"]["net_worst_sum"] == \
        card["lanes"]["last30"]["net_worst_sum"]
