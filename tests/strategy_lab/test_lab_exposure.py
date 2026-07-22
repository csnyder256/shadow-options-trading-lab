"""Exposure aggregation + correlation flags (lab-strategy-runtime-v1)."""

from __future__ import annotations

from atlas.strategy_lab.exposure import (aggregate, combo_greeks, correlation_block,
                                         _effective_n)
from atlas.strategy_lab.model import combo_from_entry

from .conftest import leg, make_entry


def _pos(sid, delta, underlying="SPY", seq=0):
    legs = [leg("C1", "call", 640, +1, bid=2.0, ask=2.2, delta=delta, vega=0.5,
                theta_day=-0.05, underlying=underlying)]
    rec = make_entry(legs, strategy_id=sid, position_id=f"{sid}:{underlying}:2026-07-20:600:{seq}")
    return combo_from_entry(rec)


def test_combo_greeks_hand_math():
    pos = _pos("a", 0.5)
    g = combo_greeks(pos, 630.0)
    # 0.5 delta * 100 sh * S 630 = 31,500 dollar-delta ; vega 50 ; theta -5
    assert g == {"delta_dollars": 31500.0, "vega": 50.0, "theta_day": -5.0}


def test_same_sign_concentration_flag():
    book = {f"s{i}": [_pos(f"s{i}", 0.5)] for i in range(8)}    # 8 strategies long SPY
    out = aggregate(book, spots={"SPY": 630.0})
    assert any("8 strategies long SPY" in f for f in out["flags"])
    assert out["per_underlying"]["SPY"]["n_long"] == 8
    # net == gross when all same sign -> the one-directional-bet flag fires too
    assert any("|net|/gross" in f for f in out["flags"])


def test_balanced_book_no_flags():
    # 3 underlyings so no single one reaches the 50% gross share bar; long/short pairs net to 0
    book = {"a": [_pos("a", 0.5)], "b": [_pos("b", -0.5, seq=1)],
            "c": [_pos("c", 0.5, underlying="QQQ")], "d": [_pos("d", -0.5, underlying="QQQ", seq=1)],
            "e": [_pos("e", 0.5, underlying="IWM")], "f": [_pos("f", -0.5, underlying="IWM", seq=1)]}
    out = aggregate(book, spots={"SPY": 630.0, "QQQ": 630.0, "IWM": 630.0})
    assert out["flags"] == []
    assert abs(out["net_delta_dollars"]) < 1e-6


def test_correlation_flags_and_effective_n():
    days = [f"2026-07-{d:02d}" for d in range(1, 21)]
    a = {d: 1.0 if i % 2 else -1.0 for i, d in enumerate(days)}
    b = dict(a)                                     # perfectly correlated with a
    c = {d: -v for d, v in a.items()}               # perfectly anti-correlated
    out = correlation_block({"a": a, "b": b, "c": c})
    assert out["n_series"] == 3
    rhos = {(p["a"], p["b"]): p["rho"] for p in out["flagged_pairs"]}
    assert rhos[("a", "b")] == 1.0 and rhos[("a", "c")] == -1.0
    # 3 series, all |rho|=1 -> effectively ONE independent bet
    assert out["effective_n"] is not None and out["effective_n"] < 1.5


def test_effective_n_identity_matrix():
    # no correlations -> effective_n == n
    assert _effective_n(["a", "b", "c"], {}) == 3.0


def test_correlation_min_overlap_guard():
    short = {f"2026-07-{d:02d}": 1.0 for d in range(1, 5)}
    out = correlation_block({"a": short, "b": short})
    assert out["n_series"] == 0 and out["flagged_pairs"] == []
