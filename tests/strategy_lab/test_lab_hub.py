"""MarketHub: budget governor priorities, chain TTL/degradation, staleness book, greeks
round-trip (lab-strategy-runtime-v1). Fake client + fake clock - no network."""

from __future__ import annotations

import json
from datetime import date

from atlas.options.vendor.blackscholes import bs_price
from atlas.strategy_lab.hub import (CAP_PER_MIN, P0_EXIT_QUOTES, P2_MANAGE_CHAIN,
                                    P3_SCAN_CHAIN, BudgetGovernor, MarketHub)


class FakeClock:
    def __init__(self):
        self.t = 1000.0
    def __call__(self):
        return self.t
    def advance(self, s):
        self.t += s


class FakeQuote:
    def __init__(self, bid, ask):
        self.bid, self.ask = bid, ask


class FakeClient:
    def __init__(self):
        self.calls = {"quotes": 0, "chains": 0, "exps": 0, "hist": 0}
    def get_quotes(self, syms):
        self.calls["quotes"] += 1
        return {s: FakeQuote(1.0, 1.2) for s in syms}
    def get_option_expirations(self, u):
        self.calls["exps"] += 1
        return ["2026-08-21", "2026-08-31", "2026-09-18"]
    def get_option_chain(self, u, exp, greeks=False):
        self.calls["chains"] += 1
        return [{"u": u, "exp": exp}]
    def get_daily_history(self, u, days=260):
        self.calls["hist"] += 1
        return [1] * days


def _hub(tmp_path, cap=CAP_PER_MIN):
    clock = FakeClock()
    client = FakeClient()
    events = []
    hub = MarketHub(client, tmp_path, cap_per_min=cap, journal=events.append, clock=clock)
    return hub, client, clock, events


def test_chain_cache_ttl(tmp_path):
    hub, client, clock, _ = _hub(tmp_path)
    hub.chain("SPY", "2026-08-31")
    hub.chain("SPY", "2026-08-31")
    assert client.calls["chains"] == 1            # cached
    clock.advance(301)
    hub.chain("SPY", "2026-08-31")
    assert client.calls["chains"] == 2            # TTL expired


def test_governor_priorities_and_degrade(tmp_path):
    hub, client, clock, events = _hub(tmp_path, cap=10)
    # burn to the 80% degrade line with distinct chain keys
    for i in range(8):
        hub.chain("SPY", f"2026-08-{i:02d}")
    # next SCAN chain is suppressed (degraded), MANAGE still allowed, P0 always allowed
    assert hub.chain("SPY", "2026-09-18", priority=P3_SCAN_CHAIN) == []
    assert any(e["event"] == "lab_data_degraded" for e in events)
    n_before = client.calls["chains"]
    assert hub.chain("QQQ", "2026-09-18", priority=P2_MANAGE_CHAIN) != []
    assert client.calls["chains"] == n_before + 1
    hub.poll_quotes(["SPY"], ["OCC1"])            # P0 never sheds
    assert client.calls["quotes"] == 1
    # budget window rolls off
    clock.advance(61)
    assert hub.chain("IWM", "2026-09-18", priority=P3_SCAN_CHAIN) != []


def test_entry_path_never_serves_stale(tmp_path):
    hub, client, clock, _ = _hub(tmp_path, cap=4)
    hub.chain("SPY", "2026-08-31")                # cached fresh
    clock.advance(301)                            # cache stale
    for _ in range(4):
        hub.governor.allow(P2_MANAGE_CHAIN)       # exhaust budget
    assert hub.chain("SPY", "2026-08-31", priority=P3_SCAN_CHAIN) == []          # no stale entry
    assert hub.chain("SPY", "2026-08-31", priority=P2_MANAGE_CHAIN) != []        # manage may reuse
    # note: manage got the STALE cached copy without a client call (budget empty)


def test_quote_staleness_book(tmp_path):
    hub, client, clock, _ = _hub(tmp_path)
    hub.poll_quotes(["SPY"], ["OCC1"])
    clock.advance(45)
    assert hub.nbbo_age_s("OCC1") == 45.0
    bid, ask, age = hub.last_nbbo("OCC1")
    assert (bid, ask, age) == (1.0, 1.2, 45.0)
    assert hub.last_nbbo("UNKNOWN") is None


def test_expiration_near_dte(tmp_path):
    hub, _, _, _ = _hub(tmp_path)
    assert hub.expiration_near_dte("SPY", 45, today=date(2026, 7, 19)) == "2026-08-31"
    assert hub.expiration_near_dte("SPY", 30, today=date(2026, 7, 19)) == "2026-08-21"


def test_row_greeks_round_trip(tmp_path):
    # price an ATM call at known IV, solve it back through the hub helper
    S, K, dte, sigma = 630.0, 630.0, 45.0, 0.20
    px = bs_price(S, K, 0.04, 0.0, sigma, dte / 365.0, "call")
    g = MarketHub.row_greeks(opt_type="call", strike=K, S=S, mid=px, dte_days=dte)
    assert abs(g["iv"] - sigma) < 1e-3
    assert 0.5 < g["delta"] < 0.6                 # ATM call with r>0 -> slightly above 0.5
    assert g["theta_day"] < 0
    assert MarketHub.row_greeks(opt_type="call", strike=K, S=S, mid=0.0, dte_days=dte) is None


def test_file_fed_context(tmp_path):
    hub, _, _, _ = _hub(tmp_path)
    assert hub.vol_regime() is None and hub.earnings_week() == {}
    (tmp_path / "vol_regime.json").write_text(json.dumps({"vix_close": 18.77}), encoding="utf-8")
    (tmp_path / "earnings_week.json").write_text(
        json.dumps({"by_symbol": {"TSLA": {"date": "2026-07-22", "hour": "amc",
                                           "timing_reliable": True}}}), encoding="utf-8")
    assert hub.vol_regime()["vix_close"] == 18.77
    assert hub.earnings_week()["TSLA"]["timing_reliable"] is True
