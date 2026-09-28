"""Runner tick-gate vs the per-underlying OPTIONS session window (fix 2026-09-28).

The tick loop used to bound itself with `session_close_minute(today) + 20` - the EQUITY
close, name-blind. But `ctx.session_close_min` is built per strategy from
`options_close_minute(today, universe[0])`, which is close+15 for the late-close index
ETFs (SPY/QQQ/IWM/DIA). Two different sources for one session bound meant the gate and
the context could disagree; the gate now derives its bound from the same per-underlying
source, so it can never under-reach the window it exists to cover.

These tests pin (a) the gate arithmetic directly, (b) that an ETF-only strategy keeps
scanning during its own late window, and (c) that a half day still shortens everything.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from atlas.options.session_calendar import options_close_minute, session_close_minute
from atlas.strategy_lab.strategy import (EventPolicy, GradingBasis, ProposedCombo, Strategy,
                                         StrategyMeta)

import scripts.run_strategy_lab as rsl

NY = ZoneInfo("America/New_York")


class FakeQuote:
    def __init__(self, bid, ask, last=0.0):
        self.bid, self.ask, self.last = bid, ask, last


class FakeGovernor:
    def used(self):
        return 0


class FakeHub:
    """Duck-typed hub: one static SPY strangle book, everything fresh."""

    def __init__(self):
        self.governor = FakeGovernor()
        self.book = {"SPY": (629.9, 630.1, 630.0),
                     "OCC_C": (2.0, 2.2, 0.0), "OCC_P": (1.8, 2.0, 0.0)}
        self.scan_ctx_minutes: list[int] = []

    def poll_quotes(self, underlyings, leg_occs):
        return {s: FakeQuote(*self.book[s]) for s in set(underlyings) | set(leg_occs)
                if s in self.book}

    def last_nbbo(self, sym):
        if sym not in self.book:
            return None
        b, a, _ = self.book[sym]
        return (b, a, 1.0)

    def earnings_week(self):
        return {}

    def daily_history(self, u, days=10):
        return []

    def expirations(self, u):
        return ["2026-10-02"]


@dataclass(frozen=True)
class _P:
    entry_lead_min: int = 15


class EtfCloseScanner(Strategy):
    """SPY-only (an INDEX underlying): records every minute its scan() actually sees, and
    enters one debit vertical the first time it is called inside its late window."""

    META = StrategyMeta(strategy_id="etf_close_scanner", version=1, name="etf close scanner",
                        universe=("SPY",), dte_range=(30, 60), max_concurrent=1,
                        event_policy=EventPolicy.TRADE_THROUGH,
                        grading_basis=GradingBasis.DEBIT,
                        defining_mechanism="directional_momentum",
                        scan_interval_s=0.0, mark_interval_s=0.0)
    params = _P()

    def __init__(self):
        self.seen_minutes: list[int] = []

    def scan(self, ctx):
        self.seen_minutes.append(ctx.minute)
        legs = [{"occ": "OCC_C", "underlying": "SPY", "opt_type": "call", "strike": 630,
                 "expiry": "2026-10-02", "side": +1, "qty": 1,
                 "nbbo": {"bid": 2.0, "ask": 2.2}, "iv": 0.2, "delta": 0.5,
                 "gamma": 0.01, "vega": 0.4, "theta_day": -0.05}]
        return [ProposedCombo(kind="long_call", underlying="SPY", legs=legs,
                              signal={"trigger": "late_window"})]

    def manage(self, pos, ctx):
        return None


def _core(tmp_path, monkeypatch, now_fn, strat):
    sid = strat.META.strategy_id
    monkeypatch.setattr(rsl, "build_all", lambda: {sid: strat})
    monkeypatch.setattr(rsl, "load_state", lambda: {sid: {"state": "armed", "cohort_pin": "",
                                                          "note": ""}})
    monkeypatch.setattr(rsl, "upcoming_events", lambda now: [])
    monkeypatch.setattr(rsl, "in_blackout", lambda now, events=None: None)
    hub = FakeHub()
    core = rsl.StrategyLabCore(runtime_dir=tmp_path, log=lambda m: None, hub=hub,
                               now_fn=now_fn)
    for k in core.strategies:
        core._scan_ts[k] = 0.0
        core._mark_ts[k] = 0.0
    return core, strat, sid


def _heartbeat(tmp_path) -> dict:
    return json.loads((tmp_path / "strategy_lab_heartbeat.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------- gate arithmetic
def test_late_tick_bounds_use_the_per_underlying_options_close():
    """The gate's bound and ctx.session_close_min now share one source: the ETF +15 window
    must be visible in the gate, and the equity/ETF closes must stay distinct."""
    day = datetime(2026, 9, 28).date()          # normal Monday
    equity_close = session_close_minute(day)
    assert equity_close == 960
    assert options_close_minute(day, "SPY") == 975          # index ETF: close + 15
    assert options_close_minute(day, "AAPL") == 960         # equity: close
    # the real 20-minute grace is preserved, now measured from the LATEST options close
    assert options_close_minute(day, "SPY") + rsl.LATE_TICK_GRACE_MIN == 995


def test_half_day_shortens_the_late_tick_bound(tmp_path, monkeypatch):
    """A half day (13:00 equity close, 13:15 ETF options) must carry the +15 through."""
    half = {"2026-11-27": {"status": "open", "close_min": 780}}
    monkeypatch.setattr(rsl, "is_trading_day", lambda d, **k: True)
    monkeypatch.setattr(rsl, "session_close_minute", lambda d, **k: 780)
    monkeypatch.setattr(rsl, "options_close_minute",
                        lambda d, u, **k: 795 if u in ("SPY", "QQQ", "IWM", "DIA") else 780)
    late = datetime(2026, 11, 27, 13, 25, tzinfo=NY)         # 805: past equity+20 (800),
    #                                                            inside ETF 795+20 (815)
    strat = EtfCloseScanner()
    core, strat, sid = _core(tmp_path, monkeypatch, lambda: late, strat)
    core.tick()
    assert strat.seen_minutes == [805], strat.seen_minutes
    assert len(core.ledger.strategy(sid).open_positions()) == 1


def test_etf_strategy_scans_its_own_late_window(tmp_path, monkeypatch):
    """Regression: at minute 992 (16:32 ET, inside ETF options close 975 + grace 20) an
    ETF-only strategy must still be ticked - the old equity-derived gate ended at 980."""
    late = datetime(2026, 9, 28, 16, 32, tzinfo=NY)
    assert late.hour * 60 + late.minute == 992
    strat = EtfCloseScanner()
    core, strat, sid = _core(tmp_path, monkeypatch, lambda: late, strat)
    core.tick()
    assert strat.seen_minutes == [992], strat.seen_minutes


def test_gate_still_stops_after_the_late_bound(tmp_path, monkeypatch):
    """No regression in the other direction: past options_close + grace the loop stands
    down (heartbeat only, no scan) - the gate did not become unbounded."""
    after = datetime(2026, 9, 28, 16, 36, tzinfo=NY)         # 996 > 975 + 20
    strat = EtfCloseScanner()
    core, strat, sid = _core(tmp_path, monkeypatch, lambda: after, strat)
    core.tick()
    assert strat.seen_minutes == [], strat.seen_minutes
    assert _heartbeat(tmp_path)["strategies_armed"] == [sid]


def test_gate_still_respects_the_open(tmp_path, monkeypatch):
    """Pre-open: nothing scans (the 570 floor is unchanged)."""
    pre = datetime(2026, 9, 28, 9, 25, tzinfo=NY)            # 565 < 570
    strat = EtfCloseScanner()
    core, strat, sid = _core(tmp_path, monkeypatch, lambda: pre, strat)
    core.tick()
    assert strat.seen_minutes == [], strat.seen_minutes
