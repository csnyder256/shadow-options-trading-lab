"""Expiry-backstop session bound is the POSITION's own options close (opts-fix-lab-backstop-close-v1).

`StrategyContext.session_close_min` is built once per strategy from
`options_close_minute(today, universe[0])`. For a mixed universe whose first member is SPY
that is 975 - the late-close index-ETF bound (SPY/QQQ/IWM/DIA quote to close+15) - even when
the open combo is a single name whose options stop at the 960 equity close. The global
expiry-day backstop rail then fired up to 15 minutes AFTER that combo's contracts stopped
quoting and wrote a stale pre-close NBBO into the ledger the WORST-fill evidence is graded
from. The rail's bound must come from the combo's OWN underlying; the tick-gate fix
(67bb29c) made the same distinction for `ctx.session_close_min`.

Fake hub + scripted strategy + frozen clock - no network, everything under tmp_path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import scripts.run_strategy_lab as rsl
from atlas.options.session_calendar import options_close_minute
from atlas.strategy_lab.strategy import (EventPolicy, GradingBasis, ProposedCombo, Strategy,
                                         StrategyMeta)

NY = ZoneInfo("America/New_York")
DAY = "2026-07-22"                       # a normal Wednesday (equity close 960, ETF 975)
MORNING = datetime(2026, 7, 22, 10, 0, tzinfo=NY)
AT_955 = datetime(2026, 7, 22, 15, 55, tzinfo=NY)     # 955: inside AAPL's [950, 960) close band,
#                                                       outside SPY's [965, 975) one
AT_965 = datetime(2026, 7, 22, 16, 5, tzinfo=NY)      # 965: AAPL options already stopped


class FakeQuote:
    def __init__(self, bid, ask, last=0.0):
        self.bid, self.ask, self.last = bid, ask, last


class FakeGovernor:
    def used(self):
        return 0


class FakeHub:
    """Static two-underlying book: SPY + AAPL, plus one AAPL leg pair expiring TODAY."""

    def __init__(self):
        self.governor = FakeGovernor()
        self.book = {"SPY": (629.9, 630.1, 630.0),
                     "AAPL": (229.9, 230.1, 230.0),
                     "OCC_A_LONG": (10.0, 10.4, 0.0), "OCC_A_SHORT": (5.0, 5.4, 0.0),
                     "OCC_S_LONG": (10.0, 10.4, 0.0), "OCC_S_SHORT": (5.0, 5.4, 0.0)}

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
        return [DAY]


@dataclass(frozen=True)
class _P:
    hold: float = 1.0


class ExpiryBackstopProbe(Strategy):
    """Enters ONE debit vertical in `underlying` expiring TODAY, then never self-exits - so the
    global expiry-day backstop is the only thing that can close it. `manage` returns None on
    purpose: this probes the rail, not a strategy rule."""

    META = StrategyMeta(strategy_id="expiry_backstop_probe", version=1, name="backstop probe",
                        universe=("SPY", "AAPL"), dte_range=(0, 10), max_concurrent=1,
                        event_policy=EventPolicy.TRADE_THROUGH,
                        grading_basis=GradingBasis.DEBIT,
                        defining_mechanism="directional_momentum",
                        settle_at_expiry=False,          # the backstop applies
                        scan_interval_s=0.0, mark_interval_s=0.0)
    params = _P()
    underlying = "AAPL"

    def __init__(self):
        self._entered = False

    def scan(self, ctx):
        if self._entered:
            return []
        self._entered = True
        sym = self.underlying
        occ = "OCC_A" if sym == "AAPL" else "OCC_S"
        legs = [{"occ": f"{occ}_LONG", "underlying": sym, "opt_type": "call", "strike": 230,
                 "expiry": ctx.day, "side": +1, "qty": 1,
                 "nbbo": {"bid": 10.0, "ask": 10.4}, "iv": 0.2, "delta": 0.55,
                 "gamma": 0.01, "vega": 0.4, "theta_day": -0.05},
                {"occ": f"{occ}_SHORT", "underlying": sym, "opt_type": "call", "strike": 240,
                 "expiry": ctx.day, "side": -1, "qty": 1,
                 "nbbo": {"bid": 5.0, "ask": 5.4}, "iv": 0.19, "delta": -0.35,
                 "gamma": 0.01, "vega": 0.35, "theta_day": -0.04}]
        return [ProposedCombo(kind="bull_call_vertical", underlying=sym, legs=legs,
                              signal={"trigger": "probe"})]

    def manage(self, pos, ctx):
        return None


def _core(tmp_path, monkeypatch, now_fn, strat):
    sid = strat.META.strategy_id
    monkeypatch.setattr(rsl, "build_all", lambda: {sid: strat})
    monkeypatch.setattr(rsl, "load_state", lambda: {sid: {"state": "armed", "cohort_pin": "",
                                                          "note": ""}})
    monkeypatch.setattr(rsl, "upcoming_events", lambda now: [])
    monkeypatch.setattr(rsl, "in_blackout", lambda now, events=None: None)
    core = rsl.StrategyLabCore(runtime_dir=tmp_path, log=lambda m: None, hub=FakeHub(),
                               now_fn=now_fn)
    for k in core.strategies:
        core._scan_ts[k] = 0.0
        core._mark_ts[k] = 0.0
    return core, sid


def _exits(tmp_path, sid) -> list:
    p = tmp_path / "strategy_lab" / sid / "exits.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_close_bounds_are_per_underlying():
    """The two closes the rail must respect really are distinct on a normal session."""
    from datetime import date
    d = date.fromisoformat(DAY)
    assert options_close_minute(d, "AAPL") == 960        # equity close
    assert options_close_minute(d, "SPY") == 975         # index ETF: close + 15
    assert 950 <= 955 < 960                              # AAPL's backstop band at 955
    assert not (965 <= 955)                              # ... and 955 is NOT SPY's band


def test_single_name_position_closes_at_its_own_options_close(tmp_path, monkeypatch):
    """A single-name combo in a SPY-first universe must be backstopped by ITS close (960 -> the
    rail fires at 950), not the strategy's universe[0] ETF close (975 -> 965). At 955 the rail
    must already have closed it, BEFORE the contracts stop quoting. Pre-fix this tick held."""
    clock = {"now": MORNING}
    strat = ExpiryBackstopProbe()
    strat.underlying = "AAPL"
    core, sid = _core(tmp_path, monkeypatch, lambda: clock["now"], strat)

    core.tick()                                       # 10:00 -> enter the AAPL vertical
    assert len(core.positions[sid]) == 1

    clock["now"] = AT_955                             # 15:55, before the 960 AAPL close
    core.tick()
    exits = _exits(tmp_path, sid)
    assert len(exits) == 1, "the backstop must close before the single name's options stop"
    assert exits[0]["rule"] == "expiry_backstop"
    assert exits[0]["underlying"] == "AAPL"
    assert core.positions[sid] == []


def test_etf_position_still_waits_for_the_late_close(tmp_path, monkeypatch):
    """Positive control: the fix must NOT over-close an index-ETF combo. SPY quotes to 975, so
    at 955 (its rail fires at 965) the position is held - the per-position bound moved the
    single-name rail earlier, not every rail earlier."""
    clock = {"now": MORNING}
    strat = ExpiryBackstopProbe()
    strat.underlying = "SPY"
    core, sid = _core(tmp_path, monkeypatch, lambda: clock["now"], strat)

    core.tick()                                       # enter the SPY vertical (expiry today)
    assert len(core.positions[sid]) == 1

    clock["now"] = AT_955
    core.tick()
    assert _exits(tmp_path, sid) == []                # 955 < 965: SPY's own band not reached
    assert len(core.positions[sid]) == 1

    clock["now"] = AT_965                             # 965 >= 975 - 10: SPY's rail now fires
    core.tick()
    exits = _exits(tmp_path, sid)
    assert len(exits) == 1 and exits[0]["rule"] == "expiry_backstop"
