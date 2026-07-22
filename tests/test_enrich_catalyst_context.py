"""WS4 catmem proof (opts-catmem-covariates-v1): enrich_catalyst_context maps recall() output to the
3 covariate keys (guarding fwd_2d-nested + p_pos_2d-underscore traps), and the runner loads
runtime/catalyst_context.json into self._catalyst_ctx for the entry covariate."""

from __future__ import annotations

import json

import scripts.enrich_catalyst_context as ec


def test_extract_hit_and_empty_shapes():
    hit = {"n": 42, "fwd_2d": {"median": 0.013, "p25": -0.01, "p75": 0.04}, "p_pos_2d": 0.58}
    assert ec.extract(hit) == {"kind_hist_n": 42, "kind_hist_ret2d_med": 0.013,
                               "kind_hist_p_pos2d": 0.58}
    empty = {"n": 0, "fwd_2d": None, "p_pos_2d": None}
    assert ec.extract(empty) == {"kind_hist_n": 0, "kind_hist_ret2d_med": None,
                                 "kind_hist_p_pos2d": None}


def test_build_context_maps_by_symbol(monkeypatch):
    calls = []

    def fake_recall(kind, direction=None, **kw):
        calls.append((kind, direction))
        return {"n": 10, "fwd_2d": {"median": 0.02}, "p_pos_2d": 0.6}

    monkeypatch.setattr(ec, "recall", fake_recall)
    rows = [{"symbol": "aapl", "catalyst_kind": "earnings", "gap_pct": 5.0},
            {"symbol": "tsla", "catalyst_kind": "fda"},          # no gap -> direction None
            {"symbol": "nokind"},                                # no kind -> skipped
            "notadict"]
    ctx = ec.build_context(rows)
    assert set(ctx) == {"AAPL", "TSLA"}
    assert ctx["AAPL"] == {"kind_hist_n": 10, "kind_hist_ret2d_med": 0.02, "kind_hist_p_pos2d": 0.6}
    assert ("earnings", "pos") in calls and ("fda", None) in calls    # gap -> direction; no gap -> None


def test_runner_loads_catalyst_context(tmp_path, monkeypatch):
    import scripts.run_options_shadow as ros
    from tests.test_options_shadow import make_core
    monkeypatch.setattr(ros, "RUNTIME", tmp_path)
    (tmp_path / "catalyst_context.json").write_text(
        json.dumps({"AAPL": {"kind_hist_n": 42, "kind_hist_ret2d_med": 0.013,
                             "kind_hist_p_pos2d": 0.58}}), encoding="utf-8")
    core, _ = make_core(tmp_path, clock={"t": 1_800_000_000.0})
    assert core._catalyst_ctx.get("AAPL", {}).get("kind_hist_n") == 42     # loaded at construction
    assert core._catalyst_ctx.get("MISSING", {}) == {}                    # absent -> {} (fail-open)


def test_runner_survives_non_dict_catalyst_context(tmp_path, monkeypatch):
    # refute E7: valid JSON but wrong type (json.loads("null") SUCCEEDS) must coerce to {} so the
    # construction-time cached read can't crash every entry all session.
    import scripts.run_options_shadow as ros
    from tests.test_options_shadow import make_core
    monkeypatch.setattr(ros, "RUNTIME", tmp_path)
    for bad in ("null", "[1,2,3]", '"x"', "123"):
        (tmp_path / "catalyst_context.json").write_text(bad, encoding="utf-8")
        core, _ = make_core(tmp_path, clock={"t": 1_800_000_000.0})
        assert core._catalyst_ctx == {}
