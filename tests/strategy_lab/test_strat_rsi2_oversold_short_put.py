"""rsi2_oversold_short_put vs its verified brief (docs/strategies/briefs/rsi2_oversold_short_put.md).
Each test cites the brief row/section it pins. Fake hub with canned daily history and canned
per-strike greeks (deterministic delta-band pins), no network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from atlas.strategy_lab.strategies.rsi2_oversold_short_put import (Rsi2OversoldShortPut, sma,
                                                                   wilder_rsi)
from atlas.strategy_lab.strategy import ExitAction, StrategyContext

NY = ZoneInfo("America/New_York")
FRI = datetime(2026, 7, 24, 15, 35, tzinfo=NY)     # inside the 15:30-15:50 ET window (row 7)
MON = datetime(2026, 7, 27, 9, 35, tzinfo=NY)      # next-session morning mark (row 9)


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float


@dataclass
class Bar:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class FakeHub:
    def __init__(self):
        self.chains = {}
        self.refs = {}
        self.exps = ["2026-07-24", "2026-07-29", "2026-07-31", "2026-08-07", "2026-08-21"]
        self.hist = {}
        self.greeks_by_strike = {}
    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)
    def expirations(self, sym, **kw):
        return self.exps
    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])
    def daily_history(self, sym, days=260, **kw):
        return self.hist.get(sym, [])
    def row_greeks(self, **kw):
        return self.greeks_by_strike.get(kw["strike"])


def _ctx(dt, hub, open_positions=(), earnings=None):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=975, hub=hub,
                           earnings=earnings or {}, journal=None,
                           open_positions=list(open_positions))


def bars(closes, end=date(2026, 7, 23)):
    """Daily bars ending `end`, one calendar day apart (dates only need to sort < ctx.day)."""
    out, d = [], end
    for c in reversed([float(c) for c in closes]):
        out.append(Bar(d.isoformat(), c, c, c, c, 1_000_000.0))
        d -= timedelta(days=1)
    return list(reversed(out))


def up_history():
    """208-day uptrend then two red closes: with today's near-final 595.0 spliced on,
    Wilder RSI(2) = 2.381 (< 5) while the close sits ~40 pts above the 200-day SMA."""
    return [500.0 + 0.5 * i for i in range(208)] + [601.0, 598.0]


def down_history():
    """Mirror-image downtrend with the same red tail: RSI(2) < 5 but price far BELOW SMA200."""
    return [700.0 - 0.5 * i for i in range(208)] + [594.0, 591.0]


def canned(delta):
    return {"iv": 0.28, "delta": delta, "gamma": 0.01, "vega": 0.5, "theta_day": -0.08}


GREEKS = {610.0: canned(-0.22), 615.0: canned(-0.27), 620.0: canned(-0.31),
          625.0: canned(-0.38)}


def put_chain():
    return [Row("P610", "put", 610.0, 4.0, 4.3), Row("P615", "put", 615.0, 5.2, 5.5),
            Row("P620", "put", 620.0, 6.6, 6.9), Row("P625", "put", 625.0, 8.4, 8.7),
            Row("C620", "call", 620.0, 6.0, 6.3),        # call - excluded
            Row("P605", "put", 605.0, 0.0, 3.0)]         # one-sided quote - excluded


def ready_hub(sym="SPY", ref=595.0):
    hub = FakeHub()
    hub.refs[sym] = ref
    hub.hist[sym] = bars(up_history())
    hub.chains[(sym, "2026-07-31")] = put_chain()
    hub.greeks_by_strike = GREEKS
    return hub


class Pos:
    def __init__(self, underlying="SPY", entry_day="2026-07-21"):
        self.underlying = underlying
        self.entry_day = entry_day


def test_wilder_rsi_hand_computed():
    """Rows 2/3: Wilder RSI, period 2 (seed = simple avg of first 2 deltas, then Wilder
    smoothing). Hand series [100,99,98,100]: seed ag=0 al=1; +2 day -> ag=1 al=0.5;
    RS=2 -> RSI = 100 - 100/3 = 66.67."""
    assert wilder_rsi([100.0, 99.0, 98.0, 100.0], 2) == pytest.approx(66.6667, abs=1e-3)
    assert wilder_rsi([100.0, 99.0, 98.0], 2) == 0.0            # all-loss tail
    assert wilder_rsi([100.0, 101.0, 102.0], 2) == 100.0        # all-gain tail
    assert wilder_rsi([5.0, 5.0, 5.0], 2) == 50.0               # flat -> neutral convention
    assert wilder_rsi([100.0, 99.0], 2) is None                 # needs period+1 closes
    assert sma([1.0, 2.0, 3.0, 4.0], 2) == 3.5
    assert sma([1.0, 2.0], 3) is None


def test_entry_fires_only_below_threshold_and_above_sma():
    """Rows 4/5/6/7: fire iff RSI(2) < 5 AND close > 200-day SMA, on the spliced near-final
    close."""
    hub = ready_hub()
    closes = [b.close for b in hub.hist["SPY"]] + [595.0]
    assert wilder_rsi(closes, 2) == pytest.approx(2.381, abs=0.01)      # setup sanity
    assert 595.0 > sma(closes, 200)
    s = Rsi2OversoldShortPut()
    got = s.scan(_ctx(FRI, hub))
    assert len(got) == 1 and got[0].underlying == "SPY"
    p = got[0]
    assert p.kind == "short_put_rsi2"
    assert p.signal["rsi2"] == pytest.approx(2.38, abs=0.01)
    leg = p.legs[0]
    assert leg["side"] == -1 and leg["opt_type"] == "put" and leg["qty"] == 1

    hub.refs["SPY"] = 620.0                        # green day: RSI(2) snaps back above 5
    assert wilder_rsi([b.close for b in hub.hist["SPY"]] + [620.0], 2) > 5.0
    assert s.scan(_ctx(FRI, hub)) == []            # row 6: no fire without the oversold print

    hub2 = ready_hub(ref=588.0)                    # oversold but in a downtrend
    hub2.hist["SPY"] = bars(down_history())
    closes2 = [b.close for b in hub2.hist["SPY"]] + [588.0]
    assert wilder_rsi(closes2, 2) < 5.0 and 588.0 < sma(closes2, 200)   # setup sanity
    assert s.scan(_ctx(FRI, hub2)) == []           # rows 4/5: trend gate blocks below the SMA


def test_strike_selected_by_delta_band():
    """Row 17: winner = |delta| nearest 0.30 INSIDE 0.25-0.35; calls and one-sided rows are
    excluded; an empty band means no entry, never a nearest-out-of-band compromise."""
    hub = ready_hub()
    s = Rsi2OversoldShortPut()
    p = s.scan(_ctx(FRI, hub))[0]
    leg = p.legs[0]
    assert leg["strike"] == 620.0                  # |-0.31| nearest 0.30; 0.22/0.38 out of band
    assert leg["delta"] == -0.31 and leg["iv"] == 0.28
    assert leg["occ"] == "P620"
    assert p.signal["abs_delta"] == 0.31
    assert p.signal["credit_bid"] == 6.6           # premium marked at bid

    hub.greeks_by_strike = {610.0: canned(-0.15), 615.0: canned(-0.20),
                            620.0: canned(-0.22), 625.0: canned(-0.40)}
    assert s.scan(_ctx(FRI, hub)) == []            # band empty -> no entry


def test_expiry_nearest_weekly_at_least_7dte():
    """Row 18: nearest listed expiry with 7 <= DTE <= 14 - the 5-DTE weekly (2026-07-29)
    must NOT be taken even though nearer; 2026-07-31 (7 DTE) wins over 2026-08-07 (14)."""
    hub = ready_hub()
    s = Rsi2OversoldShortPut()
    p = s.scan(_ctx(FRI, hub))[0]
    assert p.legs[0]["expiry"] == "2026-07-31"
    assert p.signal["dte_days"] == 7

    hub.exps = ["2026-07-29", "2026-08-21"]        # only 5-DTE and 28-DTE listed
    assert s.scan(_ctx(FRI, hub)) == []            # nothing in [7,14] -> no entry


def test_entry_window_gate():
    """Row 7: the signal is computed and entered 15:30-15:50 ET only."""
    hub = ready_hub()
    s = Rsi2OversoldShortPut()
    assert s.scan(_ctx(FRI.replace(hour=10, minute=0), hub)) == []
    assert s.scan(_ctx(FRI.replace(hour=15, minute=50), hub)) == []      # 950 exclusive
    assert len(s.scan(_ctx(FRI.replace(hour=15, minute=30), hub))) == 1  # 930 inclusive


def test_earnings_gate_single_names_only():
    """Row 19 (PLATFORM-POLICY): skip a single name when earnings fall BEFORE entry+7
    calendar days; the ETF tier (SPY/QQQ/IWM) is exempt (§9)."""
    hub = ready_hub(sym="NVDA")
    s = Rsi2OversoldShortPut()
    near = {"NVDA": {"date": "2026-07-27", "hour": "amc"}}               # entry+3 -> skip
    assert s.scan(_ctx(FRI, hub, earnings=near)) == []
    on_boundary = {"NVDA": {"date": "2026-07-31", "hour": "amc"}}        # exactly entry+7
    assert len(s.scan(_ctx(FRI, hub, earnings=on_boundary))) == 1        # 'before' is strict
    spy_hub = ready_hub(sym="SPY")
    got = s.scan(_ctx(FRI, spy_hub, earnings={"SPY": {"date": "2026-07-27"}}))
    assert len(got) == 1                                                 # ETF tier exempt


def test_one_position_per_symbol():
    """§4.5 (no rolls, fresh signal required): an open put on the symbol blocks re-entry."""
    hub = ready_hub()
    s = Rsi2OversoldShortPut()
    assert s.scan(_ctx(FRI, hub, open_positions=[Pos("SPY")])) == []
    assert len(s.scan(_ctx(FRI, hub, open_positions=[Pos("QQQ")]))) == 1  # other symbol only


def test_exit_on_rsi_close_above_65():
    """Rows 8/9: RSI(2) daily close > 65 -> close at the first mark AFTER that close."""
    hub = FakeHub()
    hub.hist["SPY"] = bars([100.0, 99.0, 98.0, 100.0], end=date(2026, 7, 24))   # RSI 66.67
    s = Rsi2OversoldShortPut()
    act = s.manage(Pos("SPY", entry_day="2026-07-21"), _ctx(MON, hub))
    assert isinstance(act, ExitAction) and act.action == "close"
    assert act.rule == "rsi2_close_above_65"
    assert act.state["rsi2_close"] == pytest.approx(66.67, abs=0.01)
    assert act.state["signal_close_day"] == "2026-07-24"

    hub.hist["SPY"] = bars([100.0, 99.0, 98.0, 99.0], end=date(2026, 7, 24))    # RSI 50
    assert s.manage(Pos("SPY", entry_day="2026-07-21"), _ctx(MON, hub)) is None


def test_exit_ignores_partial_and_pre_entry_closes():
    """Row 9's 'first mark thereafter': today's in-progress bar is never the exit signal,
    and an overbought close printed BEFORE entry cannot exit the fresh position."""
    s = Rsi2OversoldShortPut()
    hub = FakeHub()
    hub.hist["SPY"] = bars([100.0, 99.0, 98.0], end=date(2026, 7, 23)) + \
        bars([100.0], end=date(2026, 7, 24))       # today's partial bar would print RSI 66.67
    ctx = _ctx(datetime(2026, 7, 24, 15, 40, tzinfo=NY), hub)
    assert s.manage(Pos("SPY", entry_day="2026-07-21"), ctx) is None     # completed-only

    hub2 = FakeHub()
    hub2.hist["SPY"] = bars([100.0, 99.0, 98.0, 100.0], end=date(2026, 7, 23))  # RSI 66.67
    ctx2 = _ctx(datetime(2026, 7, 24, 15, 40, tzinfo=NY), hub2)
    assert s.manage(Pos("SPY", entry_day="2026-07-24"), ctx2) is None    # pre-entry signal
    assert s.manage(Pos("SPY", entry_day="2026-07-21"), ctx2) is not None  # post-entry: exits


def test_no_stop_holds_through_collapse():
    """Row 11 (Ch. 13 no-stop doctrine): a -30% collapse with RSI pinned low is a HOLD - 
    no price stop, no premium-multiple stop, nothing but the RSI exit and the backstop."""
    hub = FakeHub()
    hub.hist["SPY"] = bars([100.0, 90.0, 80.0, 70.0], end=date(2026, 7, 24))
    s = Rsi2OversoldShortPut()
    assert s.manage(Pos("SPY", entry_day="2026-07-21"), _ctx(MON, hub)) is None


def test_hold_and_no_entry_on_missing_data():
    """History unavailable -> hold / no entry, never act blind (§9 core data need)."""
    s = Rsi2OversoldShortPut()
    empty = FakeHub()
    assert s.manage(Pos("SPY"), _ctx(MON, empty)) is None                # no history -> hold
    empty.refs["SPY"] = 595.0
    assert s.scan(_ctx(FRI, empty)) == []                                # no history -> no entry
    short = ready_hub()
    short.hist["SPY"] = bars([600.0] * 50)
    assert s.scan(_ctx(FRI, short)) == []                                # <200 closes -> no entry
    noref = ready_hub()
    noref.refs["SPY"] = 0.0
    assert s.scan(_ctx(FRI, noref)) == []                                # no reference price


def test_meta_doctrine_pins():
    m = Rsi2OversoldShortPut.META
    assert m.strategy_id == "rsi2_oversold_short_put" and m.version == 1
    assert m.universe == ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")
    assert m.dte_range == (5, 16)
    assert m.max_concurrent == 9                                   # one short put per symbol
    assert m.event_policy.value == "trade_through"                 # §3.4: no published event gate
    assert m.grading_basis.value == "max_loss"                     # §10 cash-secured ceiling
    assert m.defining_mechanism == "directional_mean_reversion"
    assert m.settle_at_expiry is False                             # row 16 failsafe via backstop
    assert m.scan_interval_s == 300.0 and m.mark_interval_s == 300.0
    assert m.expected_fires_per_20_sessions == 8.0                 # §10: ~8 trades/month
    assert len(Rsi2OversoldShortPut().config_hash()) == 12
