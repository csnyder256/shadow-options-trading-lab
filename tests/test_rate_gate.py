"""Tests for the RH MCP rate gate: priority classification + the token bucket (orders never blocked,
scan polling throttled). Deterministic via an injectable clock + advancing sleep."""

from __future__ import annotations

from atlas.execution.rate_gate import RateGate, classify_priority


class _Clk:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _adv(clk):
    def sleep(dt):
        clk.t += dt
    return sleep


def test_classify_priority():
    assert classify_priority("place_equity_order") == "high"
    assert classify_priority("cancel_equity_order") == "high"
    assert classify_priority("get_equity_quotes") == "high"
    assert classify_priority("run_scan") == "low"
    assert classify_priority("get_portfolio") == "normal"
    assert classify_priority("get_equity_positions") == "normal"


def test_high_priority_never_blocks_even_when_empty():
    clk = _Clk()
    g = RateGate(capacity=2, refill_per_sec=1.0, clock=clk)
    assert g.acquire(priority="normal", timeout=0.0)  # drain
    assert g.acquire(priority="normal", timeout=0.0)
    # bucket now empty; a high-priority order still goes immediately and burns no wall time
    assert g.acquire(priority="high") is True
    assert clk.t == 0.0


def test_low_priority_throttled_when_budget_dry():
    clk = _Clk()
    g = RateGate(capacity=2, refill_per_sec=0.1, clock=clk)  # very slow refill
    assert g.acquire(priority="normal", timeout=0.0)
    assert g.acquire(priority="normal", timeout=0.0)
    # no token will free up within the 2s low-priority window -> dropped
    assert g.acquire(priority="low", timeout=2.0, sleep=_adv(clk)) is False
    assert clk.t >= 2.0


def test_normal_priority_blocks_then_succeeds_after_refill():
    clk = _Clk()
    g = RateGate(capacity=1, refill_per_sec=1.0, clock=clk)
    assert g.acquire(priority="normal", timeout=0.0)  # drain the one token
    ok = g.acquire(priority="normal", timeout=5.0, sleep=_adv(clk))  # waits ~1s for a refill
    assert ok is True
    assert 0.9 <= clk.t <= 1.6


def test_tokens_refill_and_cap_at_capacity():
    clk = _Clk()
    g = RateGate(capacity=5, refill_per_sec=2.0, clock=clk)
    g.acquire(priority="normal", timeout=0.0)  # 5 -> 4
    clk.t = 100.0
    assert g.tokens() == 5.0  # refilled but capped at capacity
