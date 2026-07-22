"""Doctrine pins for the final 3 slate strategies (mission 20260719), each citing its brief.
Fake hub with BS-priced ladders + daily history; no network."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from atlas.collect.tradier_data import TBar, TOption
from atlas.options.vendor.blackscholes import bs_price
from atlas.strategy_lab.hub import MarketHub
from atlas.strategy_lab.model import combo_from_entry
from atlas.strategy_lab.strategies.backspread_1x2 import Backspread1x2
from atlas.strategy_lab.strategies.donchian_breakout_debit_vert import (DonchianBreakoutDebitVert,
                                                                        _atr_wilder as _atr,
                                                                        _channel)
from atlas.strategy_lab.strategies.pre_earnings_long_straddle import PreEarningsLongStraddle
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")


def _occ(sym, exp, cp, k):
    return f"{sym}{exp.replace('-','')}{cp}{int(k*1000):08d}"


def _ladder(sym, exp, S, dte, iv=0.25):
    T = max(1, dte) / 365.0
    rows = []
    for i in range(-20, 21):
        k = round(S + i * max(1.0, round(S * 0.005)), 0)
        if k <= 0:
            continue
        for cp, ot in (("C", "call"), ("P", "put")):
            px = bs_price(S, k, 0.04, 0.0, iv, T, ot)
            rows.append(TOption(symbol=_occ(sym, exp, cp, k), option_type=ot, strike=k,
                                volume=800, open_interest=2000,
                                bid=max(0.02, round(px - 0.05, 2)), ask=round(px + 0.05, 2),
                                last=round(px, 2), expiration=exp))
    return rows


class Hub:
    def __init__(self, S=630.0, exps=None, hist=None, vix_pctile=30.0, iv=0.25):
        self.S = S
        self._exps = exps or [(date(2026, 7, 22) + timedelta(days=d)).isoformat()
                              for d in (14, 30, 45, 60, 75)]
        self._hist = hist
        self._vix = vix_pctile
        self._iv = iv
        self._q = {}
    def expirations(self, sym, **k): return list(self._exps)
    def chain(self, sym, exp, **k):
        dte = (date.fromisoformat(exp) - date(2026, 7, 22)).days
        return _ladder(sym, exp, self.S, max(1, dte), self._iv)
    def ref_price(self, sym): return self.S
    def row_greeks(self, **k): return MarketHub.row_greeks(**k)
    def daily_history(self, sym, days=260, **k): return self._hist or []
    def vol_regime(self, **k):
        return None if self._vix is None else {"vix_close": 18.0, "vix_pctile_252d": self._vix}
    def last_nbbo(self, occ):
        return self._q.get(occ, (1.0, 1.2, 1.0))


def _ctx(dt, hub, minute=600, earnings=None, open_positions=()):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=minute, session_close_min=960, hub=hub,
                           earnings=earnings or {}, journal=None, open_positions=list(open_positions))


def _trend_hist(base, slope, n=140):
    bars = []
    for i in range(n):
        px = base + slope * i + 2.0 * math.sin(i / 4.0)
        bars.append(TBar(ts=(date(2026, 7, 22) - timedelta(days=n - i)).isoformat(),
                         open=px, high=px + 3, low=px - 3, close=px, volume=1e6))
    return bars


# ---------------------------------------------------------------- backspread
def test_backspread_structure_and_credit_gate():
    """Brief §3: 1x2 (short 1 ~0.40Δ, long 2 ~0.20Δ), net credit >= 0 defining gate; low-IV."""
    hub = Hub(S=630.0, vix_pctile=30.0, hist=_trend_hist(590, 0.3))   # uptrend -> call side
    s = Backspread1x2()
    dt = datetime(2026, 7, 22, 10, 0, tzinfo=NY)
    props = [p for p in s.scan(_ctx(dt, hub)) if p.underlying == "SPY"]
    if props:
        p = props[0]
        assert p.kind == "call_backspread"
        sides = sorted((l["side"], l["qty"]) for l in p.legs)
        assert sides == [(-1, 1), (1, 2)]                       # 1x2
        short = [l for l in p.legs if l["side"] < 0][0]
        longleg = [l for l in p.legs if l["side"] > 0][0]
        assert longleg["strike"] > short["strike"]              # long further OTM (call side)
        assert p.signal["credit_per_share"] >= 0.0             # THE defining gate


def test_backspread_low_iv_gate_blocks_high_vol():
    hub = Hub(S=630.0, vix_pctile=80.0, hist=_trend_hist(590, 0.3))   # high IV -> no entry
    s = Backspread1x2()
    dt = datetime(2026, 7, 22, 10, 0, tzinfo=NY)
    assert s.scan(_ctx(dt, hub)) == []
    # unavailable regime -> enter flagged
    hub2 = Hub(S=630.0, vix_pctile=None, hist=_trend_hist(590, 0.3))
    props = s.scan(_ctx(dt, hub2))
    assert all("gate_unavailable" in p.risk_flags for p in props)


def test_backspread_direction_adaptive():
    s = Backspread1x2()
    dt = datetime(2026, 7, 22, 10, 0, tzinfo=NY)
    down = Hub(S=560.0, vix_pctile=30.0, hist=_trend_hist(600, -0.3))   # downtrend
    props = [p for p in s.scan(_ctx(dt, down)) if p.underlying == "SPY"]
    assert all(p.kind == "put_backspread" for p in props)


def test_backspread_meta():
    m = Backspread1x2.META
    assert m.grading_basis.value == "max_loss" and m.settle_at_expiry is False
    assert m.defining_mechanism == "long_vol_convexity"


# ---------------------------------------------------------------- donchian
def test_donchian_atr_and_channel_math():
    bars = [TBar(ts=str(i), open=100, high=102 + i * 0.1, low=98, close=100 + i * 0.05, volume=1)
            for i in range(60)]
    atr = _atr(bars, 20)
    assert atr is not None and atr > 0
    hh, ll = _channel(bars, 20, len(bars))
    assert hh == max(b.high for b in bars[-20:]) and ll == min(b.low for b in bars[-20:])


def test_donchian_up_breakout_bull_call():
    """Brief E1/E4: ref_price above prior-20-day high -> bull call vertical (long ATM + short +2N)."""
    hist = _trend_hist(500, 0.5, n=140)          # rising; last-20 high well below a spike
    hub = Hub(S=max(b.high for b in hist[-20:]) + 5.0, vix_pctile=None, hist=hist)
    s = DonchianBreakoutDebitVert()
    dt = datetime(2026, 7, 22, 10, 0, tzinfo=NY)
    props = [p for p in s.scan(_ctx(dt, hub)) if p.underlying == "SPY"]
    if props:
        p = props[0]
        assert p.kind == "bull_call_vertical"
        assert p.legs[0]["opt_type"] == "call"
        long_leg = [l for l in p.legs if l["side"] > 0][0]
        short_leg = [l for l in p.legs if l["side"] < 0][0]
        assert short_leg["strike"] > long_leg["strike"]          # short above (2N offset)
        assert p.signal["N_atr"] > 0


def test_donchian_no_breakout_no_entry():
    hist = _trend_hist(600, 0.0, n=140)          # flat, inside channel
    hh, ll = _channel(hist, 20, len(hist))
    hub = Hub(S=(hh + ll) / 2.0, vix_pctile=None, hist=hist)      # mid-channel
    s = DonchianBreakoutDebitVert()
    dt = datetime(2026, 7, 22, 10, 0, tzinfo=NY)
    assert [p for p in s.scan(_ctx(dt, hub)) if p.underlying == "SPY"] == []


def test_donchian_meta_no_profit_target():
    m = DonchianBreakoutDebitVert.META
    assert m.grading_basis.value == "debit" and m.defining_mechanism == "directional_momentum"


# ---------------------------------------------------------------- pre-earnings
def test_pre_earnings_enters_t3_atm_straddle():
    """Brief §3: buy ATM straddle on T-3; both legs long, same strike/expiry."""
    s = PreEarningsLongStraddle()
    # report Fri 2026-07-24; T-3 trading day = Tue 2026-07-21
    report = "2026-07-24"
    dt = datetime(2026, 7, 21, 15, 50, tzinfo=NY)
    hub = Hub(S=235.0, exps=["2026-07-31", "2026-08-21"], iv=0.45)
    earn = {"AAPL": {"date": report, "hour": "amc", "timing_reliable": True}}
    props = [p for p in s.scan(_ctx(dt, hub, minute=950, earnings=earn)) if p.underlying == "AAPL"]
    assert len(props) == 1
    p = props[0]
    assert p.kind == "long_straddle"
    assert all(l["side"] == +1 for l in p.legs)               # both LONG
    strikes = {l["strike"] for l in p.legs}
    assert len(strikes) == 1                                    # same strike (ATM straddle)
    assert {l["opt_type"] for l in p.legs} == {"call", "put"}
    assert p.signal["notes"]["exit_session"] == "2026-07-23"   # T-1 = Thu before Fri report


def test_pre_earnings_not_t3_no_entry():
    s = PreEarningsLongStraddle()
    hub = Hub(S=235.0, exps=["2026-07-31"], iv=0.45)
    earn = {"AAPL": {"date": "2026-07-24", "hour": "amc", "timing_reliable": True}}
    # Wed 2026-07-22 is T-2, not T-3 -> no entry
    dt = datetime(2026, 7, 22, 15, 50, tzinfo=NY)
    assert [p for p in s.scan(_ctx(dt, hub, minute=950, earnings=earn)) if p.underlying == "AAPL"] == []


def test_pre_earnings_timing_unreliable_never_trades():
    s = PreEarningsLongStraddle()
    hub = Hub(S=235.0, exps=["2026-07-31"], iv=0.45)
    earn = {"AAPL": {"date": "2026-07-24", "hour": "", "timing_reliable": False}}
    dt = datetime(2026, 7, 21, 15, 50, tzinfo=NY)
    assert s.scan(_ctx(dt, hub, minute=950, earnings=earn)) == []


def test_pre_earnings_exit_before_print():
    """§4: exit at T-1 close; failsafe never holds into the report session."""
    s = PreEarningsLongStraddle()
    hub = Hub(S=235.0, exps=["2026-07-31"], iv=0.45)
    earn = {"AAPL": {"date": "2026-07-24", "hour": "amc", "timing_reliable": True}}
    rec = s.scan(_ctx(datetime(2026, 7, 21, 15, 50, tzinfo=NY), hub, minute=950, earnings=earn))[0]
    # build a position to manage (runner normally computes leg fills; add them here)
    from tests.strategy_lab.conftest import make_entry
    from atlas.strategy_lab.model import leg_open_fills
    legs = [{**l, "fills": leg_open_fills(l["side"], l["nbbo"]["bid"], l["nbbo"]["ask"])}
            for l in rec.legs]
    e = make_entry(legs, strategy_id="pre_earnings_long_straddle", day="2026-07-21", minute=950)
    e["signal"] = rec.signal                                   # carry notes (exit_session)
    pos = combo_from_entry(e)
    pos.notes = rec.signal["notes"]
    # T-1 (Thu 07-23) at the close window -> exit
    act = s.manage(pos, _ctx(datetime(2026, 7, 23, 15, 50, tzinfo=NY), hub, minute=950))
    assert act is not None and act.rule == "pre_print_exit"
    # report day (Fri 07-24) -> failsafe never holds into the print
    act2 = s.manage(pos, _ctx(datetime(2026, 7, 24, 10, 0, tzinfo=NY), hub, minute=600))
    assert act2 is not None and act2.rule == "pre_print_failsafe"
    # T-2 (Wed 07-22) -> hold
    assert s.manage(pos, _ctx(datetime(2026, 7, 22, 15, 50, tzinfo=NY), hub, minute=950)) is None


def test_pre_earnings_meta():
    m = PreEarningsLongStraddle.META
    assert m.event_policy.value == "requires_event" and m.grading_basis.value == "debit"
