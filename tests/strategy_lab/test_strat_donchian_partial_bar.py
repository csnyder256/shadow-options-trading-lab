"""Regression pins for donchian_breakout_debit_vert's COMPLETED-session bar filter.

opts-fix-lab-partial-bar-channel-v1. The vendor's daily-history response includes the CURRENT
session's PARTIAL bar; the strategy used to fold it into every channel, which made the E1/E3
breakout test arithmetically impossible intraday (ref_price can never exceed today's own high)
- the strategy silently never fired - and let the X1 exit channel grade an unfinished session.
These tests use a hub whose daily_history returns today's partial bar the way the vendor does,
so they fail on the pre-fix code and pass after it. No network: BS-priced fake ladder.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from atlas.collect.tradier_data import TBar, TOption
from atlas.options.vendor.blackscholes import bs_price
from atlas.strategy_lab.hub import MarketHub
from atlas.strategy_lab.strategies.donchian_breakout_debit_vert import (
    DonchianBreakoutDebitVert, _atr_wilder, _last_breakout_was_winner)
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")
TODAY = "2026-07-22"
EXP = "2026-09-18"                      # ~58 DTE, inside the 45-75 band


def _occ(sym, exp, cp, k):
    return f"{sym}{exp.replace('-', '')}{cp}{int(k * 1000):08d}"


def _ladder(sym, exp, S, dte, iv=0.25):
    T = max(1, dte) / 365.0
    rows = []
    for i in range(-40, 41):
        k = float(round(S) + i)
        if k <= 0:
            continue
        for cp, ot in (("C", "call"), ("P", "put")):
            px = bs_price(S, k, 0.04, 0.0, iv, T, ot)
            rows.append(TOption(symbol=_occ(sym, exp, cp, k), option_type=ot, strike=k,
                                volume=800, open_interest=2000,
                                bid=max(0.02, round(px - 0.05, 2)), ask=round(px + 0.05, 2),
                                last=round(px, 2), expiration=exp))
    return rows


def _completed_bar(i: int, high: float, low: float, close: float, start=date(2026, 4, 1)) -> TBar:
    return TBar(ts=(start + timedelta(days=i)).isoformat(), open=close, high=high, low=low,
                close=close, volume=1e6)


def _partial_today(high: float, low: float, close: float) -> TBar:
    """Today's IN-PROGRESS bar - exactly what the vendor's daily-history response carries."""
    return TBar(ts=TODAY, open=close, high=high, low=low, close=close, volume=5e5)


class Hub:
    """daily_history returns completed bars + today's partial bar (vendor behavior)."""

    def __init__(self, bars, S):
        self._bars = list(bars)
        self.S = S

    def daily_history(self, sym, days=260, **k):
        return list(self._bars)

    def ref_price(self, sym):
        return self.S

    def expirations(self, sym, **k):
        return [EXP]

    def chain(self, sym, exp, **k):
        return _ladder(sym, exp, self.S, 58)

    def row_greeks(self, **k):
        return MarketHub.row_greeks(**k)

    def vol_regime(self, **k):
        return None

    def last_nbbo(self, occ):
        return (1.0, 1.2, 1.0)


def _ctx(hub, minute=600, open_positions=()):
    dt = datetime(2026, 7, 22, minute // 60, minute % 60, tzinfo=NY)
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=TODAY, minute=minute,
                           session_close_min=960, hub=hub, earnings={},
                           open_positions=list(open_positions))


def _flat_history(high=100.0, low=96.0, close=98.0, n=100) -> list:
    return [_completed_bar(i, high, low, close) for i in range(n)]


# --------------------------------------------------------------- entry channel (E1/E3)
def test_partial_bar_cannot_blind_the_up_breakout():
    """E1: ref_price above the COMPLETED 20-day high fires, even though today's partial high
    (the intraday spike) sits above ref_price. Pre-fix the partial bar owned the channel and
    the breakout was arithmetically impossible."""
    bars = _flat_history() + [_partial_today(high=105.0, low=99.0, close=102.0)]
    strat = DonchianBreakoutDebitVert()
    ctx = _ctx(Hub(bars, S=102.0))                      # 102 > completed high 100, < partial 105
    props = [p for p in strat.scan(ctx) if p.underlying == "SPY"]
    assert props, "breakout must fire off the completed-session channel"
    p = props[0]
    assert p.kind == "bull_call_vertical"
    long_leg = [l for l in p.legs if l["side"] > 0][0]
    short_leg = [l for l in p.legs if l["side"] < 0][0]
    assert short_leg["strike"] > long_leg["strike"]


def test_partial_bar_cannot_blind_the_down_breakout():
    """Mirror case: ref_price below the COMPLETED 20-day low fires a bear put vertical."""
    bars = _flat_history() + [_partial_today(high=101.0, low=91.0, close=94.0)]
    strat = DonchianBreakoutDebitVert()
    ctx = _ctx(Hub(bars, S=94.0))                       # 94 < completed low 96, > partial 91
    props = [p for p in strat.scan(ctx) if p.underlying == "SPY"]
    assert props and props[0].kind == "bear_put_vertical"


def test_price_inside_completed_channel_does_not_fire():
    """Positive control: with today's partial bar present but ref_price INSIDE the completed
    channel, no entry - the fix must not manufacture breakouts."""
    bars = _flat_history() + [_partial_today(high=105.0, low=91.0, close=99.0)]
    strat = DonchianBreakoutDebitVert()
    assert [p for p in strat.scan(_ctx(Hub(bars, S=99.0))) if p.underlying == "SPY"] == []


def test_entry_atr_ignores_todays_partial_range():
    """N is the Wilder ATR of COMPLETED true ranges; a tiny partial-day range must not deflate
    it. The strategy freezes N at entry, so a deflated N also misplaces the 2N stop and the
    short strike. Completed TR is 100-96 = 4 every day; today's partial TR is 0.1."""
    bars = _flat_history() + [_partial_today(high=98.1, low=98.0, close=98.05)]
    strat = DonchianBreakoutDebitVert()
    # S above the completed high so the entry fires and N is observable on the signal
    props = [p for p in strat.scan(_ctx(Hub(bars, S=102.0))) if p.underlying == "SPY"]
    assert props and props[0].signal["N_atr"] == 4.0


# --------------------------------------------------------------- X1 exit channel
def _entry_position(direction=1, entry_ref=98.0, N=4.0):
    from atlas.strategy_lab.model import combo_from_entry
    from tests.strategy_lab.conftest import make_entry

    legs = [{"occ": "SPY20260918C00098000", "underlying": "SPY", "opt_type": "call",
             "strike": 98.0, "expiry": EXP, "side": +1, "qty": 1, "nbbo": {"bid": 3.0, "ask": 3.2},
             "iv": 0.25, "delta": 0.5, "gamma": 0.01, "vega": 0.4, "theta_day": -0.05},
            {"occ": "SPY20260918C00106000", "underlying": "SPY", "opt_type": "call",
             "strike": 106.0, "expiry": EXP, "side": -1, "qty": 1, "nbbo": {"bid": 1.0, "ask": 1.2},
             "iv": 0.25, "delta": 0.3, "gamma": 0.01, "vega": 0.3, "theta_day": -0.04}]
    from atlas.strategy_lab.model import leg_open_fills
    legs = [{**l, "fills": leg_open_fills(l["side"], l["nbbo"]["bid"], l["nbbo"]["ask"])}
            for l in legs]
    e = make_entry(legs, strategy_id="donchian_breakout_debit_vert", day=TODAY, minute=600)
    pos = combo_from_entry(e)
    pos.notes = {"direction": direction, "N_atr": N, "entry_ref": entry_ref}
    return pos


def test_x1_exit_uses_the_completed_10_day_channel():
    """X1 fires when ref_price is at/below the COMPLETED 10-day low. With today's partial bar
    folded in (low 96), the pre-fix code compared against min(99, 96)=96 and MISSED the exit
    at S=98 even though 98 <= the prior-10-day low of 99."""
    bars = [_completed_bar(i, 101.0, 99.0, 100.0) for i in range(40)]
    bars.append(_partial_today(high=100.0, low=96.0, close=98.0))
    strat = DonchianBreakoutDebitVert()
    act = strat.manage(_entry_position(direction=+1, entry_ref=98.0),
                       _ctx(Hub(bars, S=98.0), minute=700))
    assert act is not None and act.rule == "turtle_x1_channel_exit"
    assert act.state["ch10_low"] == 99.0


def test_x1_does_not_fire_above_the_completed_channel():
    """Positive control: ref_price above the completed 10-day low holds, even when today's
    partial bar dipped below it and recovered."""
    bars = [_completed_bar(i, 101.0, 96.0, 100.0) for i in range(40)]
    bars.append(_partial_today(high=101.0, low=95.0, close=100.5))
    strat = DonchianBreakoutDebitVert()
    assert strat.manage(_entry_position(direction=+1, entry_ref=98.0),
                        _ctx(Hub(bars, S=100.5), minute=700)) is None


# --------------------------------------------------------------- E2 walk index
def test_e2_walk_evaluates_the_most_recent_completed_breakout():
    """With today filtered out, the last completed bar IS a valid 'last breakout', so the E2
    scan starts at len(bars)-1: a breakout on that bar is evaluated (unresolved by series end
    -> not a winner -> False), not silently skipped as it was pre-fix (which returned None)."""
    bars = _flat_history(high=100.0, low=96.0, close=98.0, n=30)
    # last completed bar is a clean up-breakout (high 104 > prior-20 high 100)
    bars.append(_completed_bar(30, high=104.0, low=99.0, close=103.0))
    atr = _atr_wilder(bars, 20)
    assert _last_breakout_was_winner(bars, 20, 10, atr) is False
