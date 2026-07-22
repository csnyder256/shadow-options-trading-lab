"""Integration smoke: every ARMED strategy scans + manages through the REAL runner wiring
without throwing (mission 20260719; guards the 07:35 live launch). A fully-populated fake hub
drives one RTH tick across the whole armed roster; ANY strategy that throws would journal a
strategy_error / quarantine - the test asserts none do, and that build_all() loads the roster."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import scripts.run_strategy_lab as rsl
from atlas.collect.tradier_data import TOption, TQuote
from atlas.options.vendor.blackscholes import bs_price
from atlas.strategy_lab.registry import armed_roster

NY = ZoneInfo("America/New_York")
# a Wednesday mid-session so no strategy's calendar gate is structurally impossible
WED_1030 = datetime(2026, 7, 22, 10, 30, tzinfo=NY)
SPOT = {"SPY": 630.0, "QQQ": 560.0, "IWM": 225.0, "AAPL": 235.0, "NVDA": 175.0,
        "MSFT": 505.0, "TSLA": 250.0, "AMD": 165.0, "META": 720.0}


def _occ(sym, exp, cp, strike):
    return f"{sym}{exp.replace('-','')}{cp}{int(strike*1000):08d}"


class FakeHub:
    """Populated enough that every strategy family can build a combo: full strike ladders with
    real BS mids across a wide DTE set, daily history with trend + vol, vol regime, earnings."""

    def __init__(self):
        self.governor = type("G", (), {"used": lambda self: 5})()
        self._quotes = {}
        self._today = WED_1030.date()
        self._exps = [(self._today + timedelta(days=d)).isoformat()
                      for d in (1, 2, 3, 7, 14, 30, 37, 45, 60, 75)]

    def expirations(self, sym, **k):
        return list(self._exps)

    def _rows(self, sym, exp):
        S = SPOT.get(sym, 100.0)
        dte = max(1, (date.fromisoformat(exp) - self._today).days)
        T = dte / 365.0
        rows = []
        step = max(1.0, round(S * 0.005))
        for i in range(-25, 26):
            k = round(S + i * step, 0)
            if k <= 0:
                continue
            for cp, ot in (("C", "call"), ("P", "put")):
                px = bs_price(S, k, 0.04, 0.0, 0.20, T, ot)
                bid = max(0.01, round(px - 0.05, 2))
                ask = round(px + 0.05, 2)
                rows.append(TOption(symbol=_occ(sym, exp, cp, k), option_type=ot, strike=k,
                                    volume=500, open_interest=1000, bid=bid, ask=ask,
                                    last=round(px, 2), expiration=exp))
        return rows

    def chain(self, sym, exp, **k):
        return self._rows(sym, exp)

    def ref_price(self, sym):
        return SPOT.get(sym, 100.0)

    def poll_quotes(self, unders, occs):
        out = {}
        for s in set(unders):
            S = SPOT.get(s, 100.0)
            out[s] = TQuote(symbol=s, last=S, bid=S - 0.02, ask=S + 0.02, prevclose=S * 0.99,
                            volume=1e7, average_volume=1e7, low=S * 0.99)
            self._quotes[s] = (S - 0.02, S + 0.02, WED_1030.timestamp(), S)
        for o in occs:
            self._quotes.setdefault(o, (1.0, 1.2, WED_1030.timestamp(), 0.0))
        return out

    def last_nbbo(self, sym):
        r = self._quotes.get(sym)
        return None if r is None else (r[0], r[1], 1.0)

    def row_greeks(self, **k):
        from atlas.strategy_lab.hub import MarketHub
        return MarketHub.row_greeks(**k)

    def daily_history(self, sym, days=260, **k):
        # a gently trending, positive-vol series long enough for 252d momentum + BB + RSI
        from atlas.collect.tradier_data import TBar
        S0 = SPOT.get(sym, 100.0) * 0.7
        out = []
        for i in range(max(days, 300)):
            px = S0 * (1.0 + 0.0008 * i) * (1.0 + 0.01 * math.sin(i / 5.0))
            d = (self._today - timedelta(days=(max(days, 300) - i))).isoformat()
            out.append(TBar(ts=d, open=px * 0.999, high=px * 1.01, low=px * 0.99,
                            close=px, volume=1e6))
        return out

    def vol_regime(self, **k):
        return {"vix_close": 18.77, "vix_pctile_252d": 71.0, "vix3m_close": 20.54,
                "vix_vix3m_ratio": 0.9138, "asof": self._today.isoformat()}

    def earnings_week(self):
        # one reliable amc name tomorrow so the earnings strategies have something to act on
        tmr = (self._today + timedelta(days=1)).isoformat()
        return {"AAPL": {"date": tmr, "hour": "amc", "timing_reliable": True, "eps_estimate": 1.2}}


def _read(path):
    return [] if not path.exists() else [json.loads(l) for l in
                                         path.read_text(encoding="utf-8").splitlines() if l.strip()]


import pytest

# the distinct active windows the 20 strategies fire in - every one must scan crash-free
_WINDOWS = [
    datetime(2026, 7, 22, 10, 30, tzinfo=NY),   # mid-session (verticals, momentum, RSI, backspread)
    datetime(2026, 7, 22, 9, 45, tzinfo=NY),    # 0DTE morning IC entry
    datetime(2026, 7, 24, 15, 50, tzinfo=NY),   # Friday close: wput roll + overnight strangle
    datetime(2026, 7, 21, 15, 50, tzinfo=NY),   # T-3 pre-earnings entry / earnings-eve close
    datetime(2026, 7, 22, 15, 58, tzinfo=NY),   # near-close: expiry-backstop / managed exits
]


@pytest.mark.parametrize("now_dt", _WINDOWS)
def test_all_armed_strategies_scan_and_manage_without_throwing(tmp_path, monkeypatch, now_dt):
    # real registry (armed roster from config/strategy_lab.yaml), fake hub, injected RTH clock
    monkeypatch.setattr(rsl, "upcoming_events", lambda now: [])
    monkeypatch.setattr(rsl, "in_blackout", lambda now, events=None: None)
    monkeypatch.setattr(rsl, "is_trading_day", lambda d, **k: True)
    monkeypatch.setattr(rsl, "session_close_minute", lambda d, **k: 960)
    monkeypatch.setattr(rsl, "options_close_minute", lambda d, u, **k: 960)

    hub = FakeHub()
    hub._today = now_dt.date()
    hub._exps = [(now_dt.date() + timedelta(days=d)).isoformat()
                 for d in (0, 1, 2, 3, 7, 14, 30, 37, 45, 60, 75)]
    core = rsl.StrategyLabCore(runtime_dir=tmp_path, log=lambda m: None, hub=hub,
                              now_fn=lambda: now_dt)
    armed = armed_roster(core.strategies, core.state)
    assert len(armed) >= 20, armed
    # force every strategy's scan+manage to run this tick regardless of its cadence
    for sid in armed:
        core._scan_ts[sid] = 0.0
        core._mark_ts[sid] = 0.0
    core.tick()

    # NO strategy may have thrown (quarantine counter stays 0; no strategy_error journal rows)
    assert core.quarantined == {}, core.quarantined
    for sid in armed:
        errs = [r for r in _read(core.ledger.strategy(sid).journal_path)
                if r.get("event") == "strategy_error"]
        assert errs == [], (sid, errs[:2])

    # heartbeat reflects the full armed roster
    hb = json.loads((tmp_path / "strategy_lab_heartbeat.json").read_text(encoding="utf-8"))
    assert len(hb["strategies_armed"]) == len(armed)
    assert hb["quarantined"] == []

    # every entry that WAS written (any window) has a frozen denominator > 0 and matched hash - 
    # proves the enter path wires end-to-end through combo build + grading + ledger
    total_entries = sum(len(_read(core.ledger.strategy(sid).entries_path)) for sid in armed)
    for sid in armed:
        for rec in _read(core.ledger.strategy(sid).entries_path):
            assert rec["grading"]["denom_usd"] > 0, (sid, rec["position_id"])
            assert rec["strategy_config_hash"] == core.strategies[sid].config_hash()
    # the mid-session window must produce at least one real entry (verticals/momentum fire)
    if now_dt == datetime(2026, 7, 22, 10, 30, tzinfo=NY):
        assert total_entries >= 1, "no strategy entered on a fully-populated mid-session tape"
