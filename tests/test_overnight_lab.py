"""Overnight lab (O5) - offline tests. Every ledger fixture goes through the REAL shadow.py
builders (the test_grade_options_shadow idiom) so the lab and the ledger schema cannot drift
apart silently. The exit-grid and MFE-capture stage tests are HAND-COMPUTED; the LLM stage is
exercised only through its skip/fake paths (no network anywhere in this file)."""

from __future__ import annotations

from datetime import datetime

from atlas.options.shadow import (
    ShadowLedger,
    build_entry_record,
    build_exit_record,
    build_mark_record,
    build_quote_record,
    position_from_entry,
)
from scripts.run_overnight_lab import (
    _own_rth_allows,
    anomaly_questions,
    exit_efficiency,
    exit_grid_replay,
    llm_stages,
    load_quotes_by_pid,
    rth_blocked,
    run_lab,
)

DAY = "2026-07-09"
OCC = "SPY260717C00600000"


# --------------------------------------------------------------------------- fixture builders
def _mk_entry(led: ShadowLedger, pid: str, *, entry_nbbo: dict, day: str = DAY,
              occ: str = OCC) -> dict:
    sig = {"lane": "index_trend", "underlying": "SPY", "direction": "call",
           "target_move": 0.005, "p_thesis": 0.5, "horizon_T": 0.001, "mu_thesis": 1.0,
           "expires_minute": 700, "notes": {}}
    pick = {"occ": occ, "underlying": "SPY", "opt_type": "call", "strike": 600.0,
            "expiry": "2026-07-17", "S": 600.0, "theta_day": -0.05}
    rec = build_entry_record(ts=1e9, day=day, entry_minute=600, position_id=pid,
                             lanes=["index_trend"], config_hash="abc", signal=sig, pick=pick,
                             runner_up_occs=[], nbbo=entry_nbbo, risk_flags=[])
    led.write_entry(rec)
    return rec


def _mk_exit(led: ShadowLedger, entry_rec: dict, *, exit_nbbo: dict, rule: str,
             day: str = DAY) -> dict:
    pos = position_from_entry(entry_rec)
    assert pos is not None
    xrec = build_exit_record(ts=1e9 + 3600, day=day, pos=pos, rule=rule,
                             bid=exit_nbbo["bid"], ask=exit_nbbo["ask"], solved_iv=0.2,
                             S=601.0, decision_state={}, variant_would_hold=False,
                             hold_trading_days=0.5)
    led.write_exit(xrec)
    return xrec


def _mk_quotes(led: ShadowLedger, pid: str, nbbo_rows: list, *, day: str = DAY,
               occ: str = OCC) -> None:
    for i, (bid, ask) in enumerate(nbbo_rows):
        led.write_quote(day, build_quote_record(ts=1e9 + 60.0 * (i + 1), occ=occ,
                                                bid=bid, ask=ask, S=600.0, position_id=pid))


def _mk_mark(led: ShadowLedger, pid: str, *, bid: float, ask: float, ts: float) -> None:
    led.write_mark(build_mark_record(ts=ts, position_id=pid, occ=OCC, bid=bid, ask=ask,
                                     solved_iv=0.2, S=600.0, decision_state={},
                                     action="hold", rule="none"))


# --------------------------------------------------------------------------- RTH refusal guard
def test_rth_blocked_window():
    # 2026-07-07 is a Tuesday, 2026-07-11 a Saturday
    assert rth_blocked(datetime(2026, 7, 7, 9, 15)) is True     # window opens 09:15
    assert rth_blocked(datetime(2026, 7, 7, 12, 0)) is True
    assert rth_blocked(datetime(2026, 7, 7, 16, 14)) is True    # last blocked minute
    assert rth_blocked(datetime(2026, 7, 7, 9, 14)) is False    # one minute early
    assert rth_blocked(datetime(2026, 7, 7, 16, 15)) is False   # window closes 16:15
    assert rth_blocked(datetime(2026, 7, 7, 23, 30)) is False   # the lab's normal hour
    assert rth_blocked(datetime(2026, 7, 11, 12, 0)) is False   # Saturday never blocks


# --------------------------------------------------------------------------- stage 1: exit grid
def test_exit_grid_replay_hand_computed(tmp_path):
    """Entry 1.00/1.20 (mid 1.10, worst fill 1.20), five quote rows:
        row1 1.05/1.15 mid 1.10  ret  0.0
        row2 0.78/0.82 mid 0.80  ret -0.2727  -> stop -0.25 sells at bid 0.78
        row3 1.70/1.80 mid 1.75  ret +0.5909  -> take 0.5 sells at bid 1.70 (or arms trail)
        row4 2.40/2.60 mid 2.50  ret +1.2727  -> take 1.0 sells at bid 2.40; trail peak 2.50
        row5 1.80/1.90 mid 1.85  <= 2.50*0.75 -> armed trails sell at bid 1.80
    Actual exit 1.50/1.60 -> worst net (1.50-1.20)*100 = +30; uncrossed variants match it."""
    led = ShadowLedger(tmp_path)
    rec = _mk_entry(led, "P1", entry_nbbo={"bid": 1.00, "ask": 1.20})
    _mk_quotes(led, "P1", [(1.05, 1.15), (0.78, 0.82), (1.70, 1.80),
                           (2.40, 2.60), (1.80, 1.90)])
    _mk_exit(led, rec, exit_nbbo={"bid": 1.50, "ask": 1.60}, rule="c_premium_stop")

    grid = exit_grid_replay(led.load_entries(None), led.load_exits(None),
                            load_quotes_by_pid(led))
    assert grid["n_exited"] == 1 and grid["n_replayed"] == 1
    assert grid["n_skipped_no_path_or_malformed"] == 0
    assert grid["actual"] == {"n": 1, "net_worst_sum": 30.0, "net_worst_mean": 30.0}

    v = grid["variants"]
    assert len(v) == 18                                    # 3 stops x 3 takes x 2 trails
    # stop -0.25 fires on ROW 2 (chronologically before any take) at bid 0.78:
    # net = (0.78 - 1.20) * 100 = -42.00, for every take/trail combination
    for take in ("0.5", "1.0", "2.0"):
        for trail in ("off", "trail25"):
            assert v[f"stop-0.25_take{take}_{trail}"] == \
                {"n": 1, "net_worst_sum": -42.0, "net_worst_mean": -42.0}
    # looser stops survive row2 (-0.2727 > -0.50); take 0.5 exits ROW 3 at bid 1.70 -> +50
    assert v["stop-0.5_take0.5_off"]["net_worst_sum"] == 50.0
    assert v["stop-0.75_take0.5_off"]["net_worst_sum"] == 50.0
    # take 1.0 exits row4 at bid 2.40 -> +120
    assert v["stop-0.5_take1.0_off"]["net_worst_sum"] == 120.0
    # trail25: take arms the trail instead of selling; row5 mid 1.85 <= 0.75*peak(2.50)
    # -> sells at row5 bid 1.80 -> +60 (same whether armed at row3 or row4)
    assert v["stop-0.5_take0.5_trail25"]["net_worst_sum"] == 60.0
    assert v["stop-0.5_take1.0_trail25"]["net_worst_sum"] == 60.0
    # take 2.0 never crosses (max ret +1.2727) -> exits at the ACTUAL exit bid 1.50 -> +30
    assert v["stop-0.5_take2.0_off"]["net_worst_sum"] == 30.0
    assert v["stop-0.5_take2.0_trail25"]["net_worst_sum"] == 30.0
    # best variant is a take-1.0 no-trail policy at +120 (tie between the two loose stops)
    assert grid["best_variant"] in ("stop-0.5_take1.0_off", "stop-0.75_take1.0_off")
    assert v[grid["best_variant"]]["net_worst_sum"] == 120.0


def test_exit_grid_accepts_single_row_paths(tmp_path):
    """audit 2026-07-16 REPLAY-LAB-3 (opts-audit-wave0-evidence-v1): the old >=2 gate excluded
    every first-mark exit - the exact hair-trigger population the lab exists to study - so the
    grid had replayed 0% of all real trades. One stored row is a valid (entry-anchored) path."""
    led = ShadowLedger(tmp_path)
    rec = _mk_entry(led, "P1", entry_nbbo={"bid": 1.00, "ask": 1.20})
    _mk_quotes(led, "P1", [(1.05, 1.15)])                       # only ONE stored row
    _mk_exit(led, rec, exit_nbbo={"bid": 1.50, "ask": 1.60}, rule="c_premium_stop")

    grid = exit_grid_replay(led.load_entries(None), led.load_exits(None),
                            load_quotes_by_pid(led))
    assert grid["n_exited"] == 1
    assert grid["n_replayed"] == 1                              # single-row path is IN
    assert grid["n_skipped_no_path_or_malformed"] == 0
    assert grid["actual"]["n"] == 1


def test_exit_grid_noop_on_empty():
    grid = exit_grid_replay([], [], {})
    assert grid["n_exited"] == 0 and grid["n_replayed"] == 0
    assert grid["actual"] == {"n": 0, "net_worst_sum": 0.0, "net_worst_mean": None}
    assert len(grid["variants"]) == 18
    assert all(s == {"n": 0, "net_worst_sum": 0.0, "net_worst_mean": None}
               for s in grid["variants"].values())
    assert grid["best_variant"] is None


# --------------------------------------------------------------------------- stage 2: efficiency
def test_exit_efficiency_hand_computed(tmp_path):
    """Trade A: entry worst fill 1.20 (nbbo 1.00/1.20); mark mids 1.10, 2.20, 1.60 -> peak
    2.20; exit worst fill 1.70 (nbbo 1.70/1.80) -> capture (1.70-1.20)/(2.20-1.20) = 0.5.
    Trade B: entry worst fill 2.20; peak mark mid 2.00 <= entry -> capture is null."""
    led = ShadowLedger(tmp_path)
    rec_a = _mk_entry(led, "A", entry_nbbo={"bid": 1.00, "ask": 1.20})
    _mk_mark(led, "A", bid=1.05, ask=1.15, ts=1e9 + 60)         # mid 1.10
    _mk_mark(led, "A", bid=2.10, ask=2.30, ts=1e9 + 120)        # mid 2.20 (the MFE peak)
    _mk_mark(led, "A", bid=1.55, ask=1.65, ts=1e9 + 180)        # mid 1.60
    _mk_exit(led, rec_a, exit_nbbo={"bid": 1.70, "ask": 1.80}, rule="d_take_profit")

    rec_b = _mk_entry(led, "B", entry_nbbo={"bid": 2.00, "ask": 2.20})
    _mk_mark(led, "B", bid=1.90, ask=2.10, ts=1e9 + 60)         # mid 2.00 <= entry fill 2.20
    _mk_exit(led, rec_b, exit_nbbo={"bid": 1.00, "ask": 1.10}, rule="c_premium_stop")

    eff = exit_efficiency(led.load_marks(None), led.load_exits(None))
    assert eff["n_exits"] == 2
    assert eff["rules"]["d_take_profit"] == \
        {"n": 1, "n_with_peak": 1, "mean_mfe_capture": 0.5}
    assert eff["rules"]["c_premium_stop"] == \
        {"n": 1, "n_with_peak": 0, "mean_mfe_capture": None}


def test_exit_efficiency_noop_on_empty():
    assert exit_efficiency([], []) == {"n_exits": 0, "rules": {}}


# --------------------------------------------------------------------------- stage 3: questions
def test_anomaly_questions_fire():
    rows = [
        {"event": "session_calendar", "day": DAY, "trading_day": True},
        {"event": "lane_error", "lane": "last30", "ts_epoch": 1.0, "error": "boom"},
        {"event": "lane_error", "lane": "last30", "ts_epoch": 2.0, "error": "boom"},
        {"event": "chain_fetch_error", "day": DAY, "error": "500"},
        {"event": "no_pick", "day": DAY, "rejections": {"spread_too_wide": 6, "dte": 1}},
        {"event": "no_pick", "day": DAY, "rejections": {"spread_too_wide": 2}},
    ]
    scorecard = {"day_requested": DAY, "entries_on_day": 0, "malformed_exits": ["P9"]}
    qs = anomaly_questions(rows, scorecard)
    assert len(qs) == 5
    joined = "\n".join(qs)
    assert "Zero shadow entries on trading day 2026-07-09" in joined
    assert "2 lane_error event(s)" in joined
    assert "1 chain_fetch_error event(s)" in joined
    assert "8/9 concentrated in 'spread_too_wide'" in joined
    assert "malformed_exits is nonempty (['P9'])" in joined


def test_anomaly_questions_quiet_when_clean():
    # non-trading day + zero entries is NOT an anomaly; balanced no_pick codes stay quiet
    rows = [
        {"event": "session_calendar", "day": DAY, "trading_day": False},
        {"event": "no_pick", "day": DAY, "rejections": {"spread_too_wide": 1, "dte": 1}},
    ]
    scorecard = {"day_requested": DAY, "entries_on_day": 0, "malformed_exits": []}
    assert anomaly_questions(rows, scorecard) == []
    assert anomaly_questions([], {"day_requested": DAY, "entries_on_day": 0,
                                  "malformed_exits": []}) == []


# --------------------------------------------------------------------------- stage 4: LLM stub
class _FakeClient:
    """Offline stand-in for HttpLLMClient - records whether the network paths were touched."""

    def __init__(self, *, healthy: bool = True, payload=None, raise_exc: Exception | None = None):
        self.healthy = healthy
        self.payload = payload
        self.raise_exc = raise_exc
        self.health_calls = 0
        self.complete_calls = 0

    def health(self) -> bool:
        self.health_calls += 1
        return self.healthy

    def complete_json(self, *, model, system, user, schema):
        self.complete_calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.payload


def test_llm_stage_gate_blocked_skips_silently():
    client = _FakeClient(payload={"ok": True})
    out = llm_stages(gate_fn=lambda: (False, "localgate: blocked (trading window)"),
                     client=client)
    assert out == {"skipped": "localgate: blocked (trading window)"}
    assert client.health_calls == 0 and client.complete_calls == 0   # server never touched


def test_llm_stage_server_down_skips_silently():
    client = _FakeClient(healthy=False, payload={"ok": True})
    out = llm_stages(gate_fn=lambda: (True, "localgate: allowed"), client=client)
    assert "skipped" in out and "health" in out["skipped"]
    assert client.complete_calls == 0                                # no completion attempted


def test_own_rth_allows_exempts_overnight_lab_slot():
    # 2026-07-15 gate reshape: the lab governs itself by RTH, NOT the shared localgate.
    # localgate now blocks 15:40-17:10 ET to keep EXTERNAL local-model users out while the
    # lab runs -- but the lab's own 16:25 slot must still be ALLOWED, and market hours
    # (09:15-16:15 ET) must still block. (2026-07-16 is a Thursday; 07-18 a Saturday.)
    assert _own_rth_allows(datetime(2026, 7, 16, 16, 25))[0] is True    # OvernightLab slot runs
    assert _own_rth_allows(datetime(2026, 7, 16, 10, 0))[0] is False    # RTH still blocked
    assert _own_rth_allows(datetime(2026, 7, 16, 16, 15))[0] is True    # 16:15 RTH-end (exclusive)
    assert _own_rth_allows(datetime(2026, 7, 16, 16, 14))[0] is False   # 16:14 still RTH
    assert _own_rth_allows(datetime(2026, 7, 18, 12, 0))[0] is True     # Saturday: no RTH block


def test_llm_stage_smoke_ok_and_failure_paths():
    ok = llm_stages(gate_fn=lambda: (True, "ok"), client=_FakeClient(payload={"ok": True}))
    assert ok == {"smoke": "ok"}
    bad = llm_stages(gate_fn=lambda: (True, "ok"), client=_FakeClient(payload={"ok": False}))
    assert bad["smoke"].startswith("failed:")
    boom = llm_stages(gate_fn=lambda: (True, "ok"),
                      client=_FakeClient(raise_exc=RuntimeError("smoke kaboom")))
    assert boom["smoke"].startswith("failed:") and "smoke kaboom" in boom["smoke"]
    # a gate that RAISES is a blocked gate (fail-closed), never an exception out of the stage
    ungated = llm_stages(gate_fn=lambda: (_ for _ in ()).throw(RuntimeError("gate down")),
                         client=_FakeClient(payload={"ok": True}))
    assert "skipped" in ungated and "fail-closed" in ungated["skipped"]


# --------------------------------------------------------------------------- orchestration
def test_run_lab_noop_on_empty_ledger(tmp_path):
    led = ShadowLedger(tmp_path)                                 # nothing on disk at all
    report, code = run_lab(led, DAY, llm_fn=lambda: {"skipped": "test-injected"})
    assert code == 0
    assert report["day"] == DAY and "generated" in report
    assert set(report["stages"]) == {"exit_grid", "exit_engine_ab", "exit_efficiency",
                                     "questions", "llm"}
    grid = report["stages"]["exit_grid"]
    assert grid["n_replayed"] == 0 and grid["actual"]["n"] == 0
    assert all(v["n"] == 0 for v in grid["variants"].values())
    # stage 1b (decide_exit A/B): empty ledger = day-1 state - a note, never an error, and all
    # five pre-registered variants present with n=0 (opts-rework-exit-core-v1 §replay)
    ab = report["stages"]["exit_engine_ab"]
    assert set(ab["variants"]) == {"legacy_v1", "legacy_v1_stop50", "v2_default",
                                   "v2_pregain_15", "v2_pregain_35"}
    assert all(v["n"] == 0 for v in ab["variants"].values())
    assert ab["n_ext_rows_total"] == 0 and "note" in ab
    assert report["stages"]["exit_efficiency"] == {"n_exits": 0, "rules": {}}
    assert report["stages"]["questions"] == []
    assert report["stages"]["llm"] == {"skipped": "test-injected"}


def test_run_lab_stage_exception_caught_and_reported(tmp_path):
    def _boom():
        raise RuntimeError("stage kaboom")

    report, code = run_lab(ShadowLedger(tmp_path), DAY, llm_fn=_boom)
    assert code == 6                                             # reported, not raised
    assert "stage kaboom" in report["stages"]["llm"]["error"]
    assert report["stages"]["exit_grid"]["n_replayed"] == 0      # other stages still ran
    assert any("llm RAISED" in n for n in report["notes"])
