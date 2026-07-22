"""decide_exit PAIRED REPLAY (opts-rework-exit-core-v1 §replay): the pure engine-level replay
in atlas/options/replay.py. Fixtures go through the REAL shadow.py builders and carry the
EXACT ext schema the runner writes (run_options_shadow._reval_positions), so replay and ledger
cannot drift apart silently. Engine behavior at each mark is anchored to states already pinned
in test_options_exit_engine{,_legacy}.py - v2 holds where v1's +100% forced take fired.
No IO beyond tmp-free in-memory records; no network; never touches runtime/."""

from __future__ import annotations

import json
from datetime import datetime

from atlas.clock import NY
from atlas.options import exit_engine as v2
from atlas.options import exit_engine_legacy as v1
from atlas.options import shadow as oshadow
from atlas.options.replay import exit_engine_ab, replay_decide_exit
from scripts.run_overnight_lab import AB_VARIANTS

DAY = "2026-07-14"                                     # a Tuesday
EXP = "2026-07-15"                                     # DTE 1 from DAY (evidence rule governs)
MIDNIGHT = datetime(2026, 7, 14, 0, 0, tzinfo=NY).timestamp()


def ep(minute: int) -> float:
    return MIDNIGHT + minute * 60


def _entry(pid: str, *, bid: float, ask: float, strike: float, target_move: float,
           mu_thesis: float, occ: str) -> dict:
    """Entry record via the REAL builder (field names must match production, not a paraphrase).
    entry_minute 590 = 09:50, the engine-test fixtures' entry_ts_min."""
    sig = {"lane": "index_trend", "underlying": "XYZ", "direction": "call",
           "target_move": target_move, "p_thesis": 0.6, "horizon_T": 1.0 / 252.0,
           "mu_thesis": mu_thesis, "expires_minute": 700, "notes": {}}
    pick = {"occ": occ, "underlying": "XYZ", "opt_type": "call", "strike": strike,
            "expiry": EXP, "bid": bid, "ask": ask, "S": 100.0, "theta_day": -0.05}
    return oshadow.build_entry_record(ts=ep(590), day=DAY, entry_minute=590, position_id=pid,
                                      lanes=["index_trend"], config_hash="abc123", signal=sig,
                                      pick=pick, runner_up_occs=[], nbbo={"bid": bid, "ask": ask},
                                      risk_flags=[])


# the two engine-pinned marks:
#  - HEALTHY: mu_thesis 4, target 101 @ 1.95/2.05 -> j_hold in BOTH engines (pinned)
#  - WINNER: entry mid 0.93, strike 98, mu_thesis 8, target 104, mark 2.30/2.34 (+149%) ->
#    v2 j_hold (the anti-hallucination pin) while v1 fires d_take_profit (p_target ~0.12 < .35)
def entry_healthy(pid: str) -> dict:
    return _entry(pid, bid=1.95, ask=2.05, strike=100.0, target_move=0.01, mu_thesis=4.0,
                  occ="XYZ260715C00100000")


def entry_winner(pid: str) -> dict:
    return _entry(pid, bid=0.91, ask=0.95, strike=98.0, target_move=0.04, mu_thesis=8.0,
                  occ="XYZ260715C00098000")


def ext(minute: int, **over) -> dict:
    """The runner's ext snapshot, field-for-field (run_options_shadow write_quote call)."""
    d = {"solved_iv": 0.30, "iv_trend_per_hour": 0.0, "mu_hat": None, "mu_t_stat": 0.0,
         "thesis_valid": True, "opposing_defense": False, "defense_zone_score": 0.0,
         "minutes_to_next_print": None, "minutes_since_print": None,
         "planned_exit_minute": None, "named_catalyst_tomorrow": False, "is_friday": False,
         "after_hours": False, "theta_share_breaches": 0, "minute": minute}
    d.update(over)
    return d


def qrow(pid: str, occ: str, minute: int, bid: float, ask: float, *, S: float = 100.0,
         with_ext: bool = True, **ext_over) -> dict:
    return oshadow.build_quote_record(ts=ep(minute), occ=occ, bid=bid, ask=ask, S=S,
                                      position_id=pid,
                                      ext=ext(minute, **ext_over) if with_ext else None)


# --------------------------------------------------------------------- (a) v2 known first-SELL
def test_v2_replay_reproduces_overnight_evidence_sell():
    e = entry_healthy("P1")
    rows = [qrow("P1", "XYZ260715C00100000", 660, 1.95, 2.05),     # 11:00 -> j_hold (pinned)
            qrow("P1", "XYZ260715C00100000", 950, 1.95, 2.05)]     # 15:50 -> 15:45 checkpoint
    res = replay_decide_exit(e, rows, engine=v2, params=v2.ExitParams())
    assert res is not None
    assert res["rule"] == "overnight_evidence_rule" and res["exit_minute"] == 950
    assert res["sell_bid"] == 1.95
    # worst-ledger dollars: sell bid 1.95 vs entry WORST fill (ask 2.05) -> -$10
    assert res["net_worst"] == -10.0
    assert res["marks_replayed"] == 2 and res["skipped_no_ext"] == 0
    assert res["engine_errors"] == 0


# --------------------------------------------------------------------- (b) v1 vs v2 divergence
def test_legacy_takes_at_plus100_where_v2_holds():
    """THE reason this replay exists: on an identical stored path the frozen v1 fires its
    unregistered +100% forced take (d_take_profit, 11:00) while v2 rides the same mark to the
    15:45 evidence checkpoint - same dollars here, different rule and 290 minutes apart."""
    e = entry_winner("W1")
    rows = [qrow("W1", "XYZ260715C00098000", 660, 2.30, 2.34),     # +149% from entry mid 0.93
            qrow("W1", "XYZ260715C00098000", 950, 2.30, 2.34)]
    old = replay_decide_exit(e, rows, engine=v1, params=v1.ExitParams())
    new = replay_decide_exit(e, rows, engine=v2, params=v2.ExitParams())
    assert old["rule"] == "d_take_profit" and old["exit_minute"] == 660
    assert new["rule"] == "overnight_evidence_rule" and new["exit_minute"] == 950
    # both sell at bid 2.30 vs entry worst 0.95 -> +$135 (the divergence is WHEN/WHY, not price)
    assert old["net_worst"] == new["net_worst"] == 135.0


# --------------------------------------------------------------------- (c) rows without ext
def test_rows_without_ext_are_unreplayable_and_counted():
    e = entry_healthy("N1")
    occ = "XYZ260715C00100000"
    # ALL rows pre-schema-2: nothing decide_exit-replayable -> None (day-0 quote files)
    bare = [qrow("N1", occ, 660, 1.95, 2.05, with_ext=False),
            qrow("N1", occ, 950, 1.95, 2.05, with_ext=False)]
    assert replay_decide_exit(e, bare, engine=v2, params=v2.ExitParams()) is None
    # MIXED path: the bare row is skipped + counted, the ext rows replay normally
    mixed = [qrow("N1", occ, 620, 1.95, 2.05, with_ext=False)] + [
        qrow("N1", occ, 660, 1.95, 2.05), qrow("N1", occ, 950, 1.95, 2.05)]
    res = replay_decide_exit(e, mixed, engine=v2, params=v2.ExitParams())
    assert res["skipped_no_ext"] == 1 and res["marks_replayed"] == 2
    assert res["rule"] == "overnight_evidence_rule"
    # malformed entry record: never crashes, never fabricates a replay
    assert replay_decide_exit({"position_id": "N1"}, mixed,
                              engine=v2, params=v2.ExitParams()) is None


# --------------------------------------------------------------------- (d) A/B aggregation
def test_exit_engine_ab_aggregates_per_variant():
    ea, eb = entry_winner("A1"), entry_healthy("B1")
    quotes = {"A1": [qrow("A1", "XYZ260715C00098000", 660, 2.30, 2.34),
                     qrow("A1", "XYZ260715C00098000", 950, 2.30, 2.34)],
              "B1": [qrow("B1", "XYZ260715C00100000", 660, 1.95, 2.05)]}  # ends open -> unexited
    variants = [("legacy_v1", v1, v1.ExitParams()), ("v2_default", v2, v2.ExitParams())]
    out = exit_engine_ab([eb, ea], quotes, variants)              # unsorted input on purpose

    assert out["n_entries"] == 2 and out["n_ext_rows_total"] == 3
    assert "note" not in out                                      # ext rows exist -> no day-1 note
    assert out["variants"]["legacy_v1"] == {"n": 2, "net_worst_sum": 135.0,
                                            "rule_mix": {"d_take_profit": 1}, "unexited": 1}
    assert out["variants"]["v2_default"] == {"n": 2, "net_worst_sum": 135.0,
                                             "rule_mix": {"overnight_evidence_rule": 1},
                                             "unexited": 1}
    # per-position table is pid-sorted and carries every variant's verdict
    assert [r["position_id"] for r in out["per_position"]] == ["A1", "B1"]
    a = out["per_position"][0]
    assert a["legacy_v1"] == {"rule": "d_take_profit", "exit_minute": 660, "net_worst": 135.0}
    assert a["v2_default"] == {"rule": "overnight_evidence_rule", "exit_minute": 950,
                               "net_worst": 135.0}
    b = out["per_position"][1]
    assert b["legacy_v1"]["rule"] == b["v2_default"]["rule"] == "unexited"
    assert b["v2_default"]["net_worst"] is None

    # day-1 state: entries exist but no schema-2 rows yet -> note, zero-filled variants
    day1 = exit_engine_ab([entry_healthy("B2")],
                          {"B2": [qrow("B2", "XYZ260715C00100000", 660, 1.95, 2.05,
                                       with_ext=False)]}, variants)
    assert day1["n_unreplayable_no_ext_or_malformed"] == 1 and day1["per_position"] == []
    assert day1["n_ext_rows_total"] == 0 and "note" in day1
    assert all(s["n"] == 0 for s in day1["variants"].values())


# --------------------------------------------------------------------- (e) peak maintenance
def test_peak_bid_peak_mid_maintained_like_the_runner():
    """Hand-computed d2* sequence (opts-rule-d2-costbasis-v1): entry 0.91/0.95 (peaks prime at
    entry bid/mid = 0.91/0.93, entry_ask 0.95). Row1 2.30/2.34 updates peaks BEFORE the
    decision (peak_bid 2.30 > entry_ask arms d2*) and HOLDs; row2 0.90/0.96 gives the
    realizable gain back (bid 0.90 <= 0.95) -> d2_costbasis_backstop. Drop row1 and the same
    row2 never fires d2* (peak_bid stays 0.91, never armed) - the peak carry IS the rule."""
    e = entry_winner("K1")
    occ = "XYZ260715C00098000"
    # v3 (opts-audit-wave2-exitv3-v1): d2 CO-REQUIRES the EV verdict - the giveback row also
    # carries strong adverse live drift (mu_hat -15 @ t=3 -> SE=5, tau=8 -> w=0.72 ->
    # mu_eff ~ -9.7) so ev_hold < ev_sell and the backstop may fire. A giveback with an
    # intact favorable EV now HOLDS (the audit's right-tail-amputation fix), pinned below.
    peaked = [qrow("K1", occ, 660, 2.30, 2.34),
              qrow("K1", occ, 700, 0.90, 0.96, mu_hat=-15.0, mu_t_stat=3.0)]
    res = replay_decide_exit(e, peaked, engine=v2, params=v2.ExitParams())
    assert res["rule"] == "d2_costbasis_backstop" and res["exit_minute"] == 700
    assert res["peak_bid"] == 2.30 and res["peak_mid"] == 2.32       # max(0.93, 2.32, 0.93)
    assert res["net_worst"] == -5.0                                  # (0.90 - 0.95) * 100

    # same giveback WITHOUT adverse EV evidence: d2 armed but blocked by the EV co-requirement
    ev_ok = [qrow("K1", occ, 660, 2.30, 2.34), qrow("K1", occ, 700, 0.90, 0.96)]
    held = replay_decide_exit(e, ev_ok, engine=v2, params=v2.ExitParams())
    assert held["rule"] == "unexited", held

    flat = replay_decide_exit(e, peaked[1:], engine=v2, params=v2.ExitParams())
    assert flat["rule"] == "unexited"                                # d2* never armed
    assert flat["peak_bid"] == 0.91 and flat["peak_mid"] == 0.93


# --------------------------------------------------------------------- (f) determinism
def test_replay_is_deterministic():
    # the full pre-registered lab variant set, twice, byte-identical (JSON-normalized) - the
    # nightly report may never depend on dict/iteration accidents
    entries = [entry_winner("A1"), entry_healthy("B1")]
    quotes = {"A1": [qrow("A1", "XYZ260715C00098000", 660, 2.30, 2.34),
                     qrow("A1", "XYZ260715C00098000", 950, 2.30, 2.34)],
              "B1": [qrow("B1", "XYZ260715C00100000", 660, 1.95, 2.05),
                     qrow("B1", "XYZ260715C00100000", 950, 1.95, 2.05)]}
    one = exit_engine_ab(list(entries), dict(quotes), list(AB_VARIANTS))
    two = exit_engine_ab(list(entries), dict(quotes), list(AB_VARIANTS))
    assert json.dumps(one, sort_keys=True) == json.dumps(two, sort_keys=True)
    assert set(one["variants"]) == {"legacy_v1", "legacy_v1_stop50", "v2_default",
                                    "v2_pregain_15", "v2_pregain_35"}
