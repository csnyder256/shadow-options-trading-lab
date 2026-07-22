"""rsi2_overbought_bear_call vs its verified brief (docs/strategies/briefs/
rsi2_overbought_bear_call.md). Each test cites the brief row it pins. Fake hub, no network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from atlas.strategy_lab.hub import MarketHub
from atlas.strategy_lab.model import combo_from_entry
from atlas.strategy_lab.strategies.rsi2_overbought_bear_call import (Rsi2OverboughtBearCall,
                                                                     wilder_rsi)
from atlas.strategy_lab.strategy import StrategyContext

from .conftest import leg, make_entry

NY = ZoneInfo("America/New_York")
EVAL = datetime(2026, 7, 24, 15, 50, tzinfo=NY)     # Friday 15:50 ET - inside 15:45-15:55
S_SPY = 630.40


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float
    volume: float = 100.0
    open_interest: float = 500.0


@dataclass
class Bar:
    ts: str
    close: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0


def bars(closes, end=date(2026, 7, 23)):
    """Daily bars ending the session BEFORE the eval day (strategy appends the live price)."""
    n = len(closes)
    return [Bar(ts=(end - timedelta(days=n - 1 - i)).isoformat(), close=float(c))
            for i, c in enumerate(closes)]


def overbought_closes(S_now, n=215):
    """~213-day gentle downtrend to 2.4% below S_now, then a sharp 2-day rally into the live
    price: RSI(2) ~99 (row 3) with S_now still well below the 200d SMA (row 4). Also leaves
    S_now ABOVE the 5d SMA and BELOW the 200d SMA - the doctrinal HOLD zone for manage()."""
    m = n - 2
    down = [S_now * (1.11 - (1.11 - 0.9760) * i / (m - 1)) for i in range(m)]
    return down + [S_now * 0.9766, S_now * 0.9868]


def overbought_above_sma_closes(S_now, n=215):
    """Same 2-day rally shape but off a long UPTREND: RSI(2) > 95 yet the close sits above
    its 200d SMA - the row-4 trend filter must veto the short."""
    m = n - 2
    up = [S_now * (0.85 + (0.9760 - 0.85) * i / (m - 1)) for i in range(m)]
    return up + [S_now * 0.9766, S_now * 0.9868]


def downtrend_closes(S_now, n=215):
    """Steady decline through the live price: below the 200d SMA but RSI(2) ~0 - the row-3
    overbought trigger must veto the short."""
    return [S_now * (1.15 - (1.15 - 1.005) * i / (n - 1)) for i in range(n)]


def upflip_closes():
    """Long ascent to just under the live price: close above the 200d SMA (regime flip) while
    NOT under the 5d SMA - isolates the row-8 exit from the row-7 exit."""
    return [550.0 + (629.0 - 550.0) * i / 214 for i in range(215)]


class FakeHub:
    def __init__(self):
        self.chains = {}
        self.refs = {"SPY": S_SPY}
        # DTEs from 2026-07-24: 0, 7, 12, 14, 28 -> the 10-17 band selects 2026-08-05
        self.exps = ["2026-07-24", "2026-07-31", "2026-08-05", "2026-08-07", "2026-08-21"]
        self.daily = {}
        self.nbbo = {}
    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)
    def expirations(self, sym, **kw):
        return self.exps
    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])
    def daily_history(self, sym, days=260, **kw):
        return self.daily.get(sym, [])
    def last_nbbo(self, occ):
        return self.nbbo.get(occ)
    row_greeks = staticmethod(MarketHub.row_greeks)


def _ctx(dt, hub, open_positions=(), earnings=None):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=975, hub=hub,
                           earnings=earnings or {}, journal=None,
                           open_positions=list(open_positions))


def _spy_chain():
    return [Row("C629", "call", 629.0, 3.10, 3.24),
            Row("C630", "call", 630.0, 2.55, 2.67),    # below 630.40 - never the short
            Row("C631", "call", 631.0, 2.05, 2.15),    # first strike at/above spot (row 13)
            Row("C632", "call", 632.0, 1.62, 1.72),
            Row("C633", "call", 633.0, 1.26, 1.34),
            Row("C634", "call", 634.0, 0.96, 1.04),    # only 3 wide - under 0.5% of spot
            Row("C635", "call", 635.0, 0.72, 0.78),    # first strike >= 631 + 3.152 (row 14)
            Row("P631", "put", 631.0, 2.20, 2.30)]     # put - excluded from call selection


def _entry_hub():
    hub = FakeHub()
    hub.daily["SPY"] = bars(overbought_closes(S_SPY))
    hub.chains[("SPY", "2026-08-05")] = _spy_chain()
    return hub


def _pos(expiry=date(2026, 8, 5)):
    rec = make_entry([leg("C631", "call", 631.0, -1, bid=2.05, ask=2.15, expiry=expiry),
                      leg("C635", "call", 635.0, +1, bid=0.72, ask=0.78, expiry=expiry)],
                     declared_basis="max_loss")
    pos = combo_from_entry(rec)
    assert pos is not None
    return pos


BOTH_LEGS = {"C631": (2.60, 2.70, 5.0), "C635": (0.55, 0.65, 5.0)}   # combo mid = -2.05


# --------------------------------------------------------------------------- signal engine
def test_wilder_rsi_hand_values():
    """Row 2: standard Wilder RSI, period 2 - hand-computed pins (seed = simple average of
    the first 2 deltas, then Wilder smoothing)."""
    assert wilder_rsi([100.0, 101.0, 102.0], 2) == 100.0             # all-gain tape
    assert wilder_rsi([100.0, 99.0, 98.0], 2) == 0.0                 # all-loss tape
    # deltas -1, +2, +1: seed g=1.0 l=0.5; smooth +1 -> g=1.0 l=0.25; RS=4 -> RSI=80
    assert wilder_rsi([100.0, 99.0, 101.0, 102.0], 2) == pytest.approx(80.0)
    assert wilder_rsi([100.0, 100.0, 100.0], 2) == 50.0              # flat tape = neutral
    assert wilder_rsi([100.0, 101.0], 2) is None                     # needs period+1 closes


# --------------------------------------------------------------------------- entry (scan)
def test_entry_overbought_below_200sma_builds_bear_call():
    """Rows 2/3/4 (trigger side: RSI(2)>95 BELOW the 200d SMA -> short) + rows 12/13/14/15
    (2-leg bear call: short 631C at/above spot, long 635C = first width >= 0.5% of spot,
    nearest 10-17 DTE expiry)."""
    s = Rsi2OverboughtBearCall()
    proposals = s.scan(_ctx(EVAL, _entry_hub()))
    assert len(proposals) == 1
    p = proposals[0]
    assert p.kind == "bear_call_spread" and p.underlying == "SPY"
    assert len(p.legs) == 2
    short, long_ = p.legs
    assert short["side"] == -1 and short["opt_type"] == "call" and short["strike"] == 631.0
    assert long_["side"] == +1 and long_["opt_type"] == "call" and long_["strike"] == 635.0
    assert short["strike"] < long_["strike"]                         # short below long, always
    assert short["expiry"] == "2026-08-05" and long_["expiry"] == "2026-08-05"   # 12 DTE
    assert p.signal["rsi2"] > 95.0                                   # row 3 trigger recorded
    assert p.signal["S_ref"] < p.signal["sma_trend"]                 # row 4 trend filter
    assert p.signal["width"] == pytest.approx(4.0)                   # 3.152-wide target -> 635
    assert p.signal["credit_mid"] == pytest.approx(1.35)             # 2.10 - 0.75
    assert p.contracts == 1                                          # row 20: 1 lot
    assert short["delta"] > 0                                        # solved call greeks wired


def test_trend_filter_and_rsi_trigger_both_required():
    """Row 4: RSI(2)>95 ABOVE the 200d SMA -> NO short (shorts require below-200d-SMA).
    Row 3: below the SMA without RSI(2)>95 -> NO short."""
    s = Rsi2OverboughtBearCall()
    hub = _entry_hub()
    hub.daily["SPY"] = bars(overbought_above_sma_closes(S_SPY))      # hot RSI, wrong regime
    assert s.scan(_ctx(EVAL, hub)) == []
    hub.daily["SPY"] = bars(downtrend_closes(S_SPY))                 # right regime, cold RSI
    assert s.scan(_ctx(EVAL, hub)) == []


def test_eval_window_and_one_position_per_symbol():
    """Row 6: entries only in the 15:45-15:55 ET evaluation. Row 5: 'no current positions'
 - an open spread on the symbol blocks re-entry."""
    s = Rsi2OverboughtBearCall()
    hub = _entry_hub()
    assert s.scan(_ctx(EVAL.replace(hour=15, minute=44), hub)) == []
    assert s.scan(_ctx(EVAL.replace(hour=15, minute=55), hub)) == []
    assert len(s.scan(_ctx(EVAL.replace(hour=15, minute=45), hub))) == 1   # window start

    class OpenPos:
        underlying = "SPY"
    assert s.scan(_ctx(EVAL, hub, open_positions=[OpenPos()])) == []


def test_liquidity_and_credit_gates():
    """Row 18: two-sided NBBO + spread <= 10% of mid + OI >= 100 on BOTH legs.
    Row 17: reject when net mid credit < 30% of width."""
    s = Rsi2OverboughtBearCall()
    hub = _entry_hub()                                               # sanity: entry fires
    assert len(s.scan(_ctx(EVAL, hub))) == 1
    thin = _spy_chain()
    thin[6] = Row("C635", "call", 635.0, 0.72, 0.78, open_interest=10.0)     # long OI < 100
    hub.chains[("SPY", "2026-08-05")] = thin
    assert s.scan(_ctx(EVAL, hub)) == []
    dead = _spy_chain()
    dead[2] = Row("C631", "call", 631.0, 0.0, 2.15)                  # one-sided short leg
    hub.chains[("SPY", "2026-08-05")] = dead
    assert s.scan(_ctx(EVAL, hub)) == []
    cheap = _spy_chain()
    cheap[2] = Row("C631", "call", 631.0, 1.00, 1.06)                # credit 0.28 < 0.30*4.0
    hub.chains[("SPY", "2026-08-05")] = cheap
    assert s.scan(_ctx(EVAL, hub)) == []


def test_earnings_gate_single_names():
    """Row 19: skip a single-name entry when earnings land on/before the chosen expiry;
    clear once earnings fall after expiry. Index ETFs are untouched."""
    s = Rsi2OverboughtBearCall()
    hub = _entry_hub()
    hub.refs["TSLA"] = 250.30
    hub.daily["TSLA"] = bars(overbought_closes(250.30))
    hub.chains[("TSLA", "2026-08-05")] = [
        Row("T250", "call", 250.0, 1.80, 1.90),
        Row("T251", "call", 251.0, 1.20, 1.30),      # short: first strike >= 250.30
        Row("T252", "call", 252.0, 0.78, 0.86),      # 1 wide < 1.2515 target
        Row("T253", "call", 253.0, 0.42, 0.46)]      # long: first >= 251 + 1.2515
    inside = {"TSLA": {"date": "2026-08-03", "hour": "amc"}}         # on/before 08-05 expiry
    got = {p.underlying for p in s.scan(_ctx(EVAL, hub, earnings=inside))}
    assert got == {"SPY"}                                            # TSLA skipped, SPY fires
    after = {"TSLA": {"date": "2026-08-10", "hour": "amc"}}          # after expiry
    got = {p.underlying: p for p in s.scan(_ctx(EVAL, hub, earnings=after))}
    assert set(got) == {"SPY", "TSLA"}
    assert got["TSLA"].legs[0]["strike"] == 251.0                    # rows 13/14 on TSLA too
    assert got["TSLA"].legs[1]["strike"] == 253.0


# --------------------------------------------------------------------------- exits (manage)
def test_exit_under_5day_sma_fires():
    """Row 7 (book Ch. 12 verbatim): close under the 5-day SMA -> buy the spread back."""
    s = Rsi2OverboughtBearCall()
    hub = FakeHub()
    hub.daily["SPY"] = bars([700.0] * 215)           # live 630.40 << 5d SMA (and << 200d)
    hub.nbbo = dict(BOTH_LEGS)
    act = s.manage(_pos(), _ctx(EVAL, hub))
    assert act is not None and act.action == "close"
    assert act.rule == "exit_under_5sma"
    assert act.state["combo_mid"] == pytest.approx(-2.05)            # cost from leg NBBO mids
    assert act.state["S"] < act.state["sma_exit"]


def test_exit_regime_flip_above_200sma():
    """Row 8 (MQL5 rendition): close above the 200d SMA -> exit, even with the 5d-SMA
    condition NOT met."""
    s = Rsi2OverboughtBearCall()
    hub = FakeHub()
    hub.daily["SPY"] = bars(upflip_closes())         # live 630.40 > 200d SMA, above 5d SMA
    hub.nbbo = dict(BOTH_LEGS)
    act = s.manage(_pos(), _ctx(EVAL, hub))
    assert act is not None and act.rule == "exit_regime_flip_200sma"
    assert act.state["S"] > act.state["sma_trend"]
    assert act.state["S"] >= act.state["sma_exit"]                   # row 7 did NOT apply


def test_no_profit_target_no_stop_holds_any_mark():
    """Rows 10/11 (+§10c): NO stop and NO profit target - deep-profit and near-max-loss
    marks both HOLD while no signal exit is true."""
    s = Rsi2OverboughtBearCall()
    hub = FakeHub()
    hub.daily["SPY"] = bars(overbought_closes(S_SPY))    # above 5d SMA, below 200d SMA
    pos = _pos()
    hub.nbbo = {"C631": (0.05, 0.09, 5.0), "C635": (0.01, 0.03, 5.0)}    # ~95% of credit won
    assert s.manage(pos, _ctx(EVAL, hub)) is None
    hub.nbbo = {"C631": (3.90, 4.00, 5.0), "C635": (0.02, 0.06, 5.0)}    # near max loss
    assert s.manage(pos, _ctx(EVAL, hub)) is None


def test_force_close_1dte_and_close_based_window():
    """Row 16 (PLATFORM-POLICY): 1 DTE at the closing evaluation -> force close, needing no
    signal data. §10: outside the 15:45-15:55 window manage() never exits."""
    s = Rsi2OverboughtBearCall()
    hub = FakeHub()                                  # NO daily history at all
    hub.nbbo = dict(BOTH_LEGS)
    pos = _pos(expiry=date(2026, 7, 25))             # tomorrow -> 1 DTE
    act = s.manage(pos, _ctx(EVAL, hub))
    assert act is not None and act.rule == "force_close_1dte"
    assert act.state["dte"] == 1
    assert s.manage(pos, _ctx(EVAL.replace(hour=12, minute=0), hub)) is None    # window gate
    far = _pos()                                     # 12 DTE, still no history
    assert s.manage(far, _ctx(EVAL, hub)) is None    # no data + no calendar due -> hold


def test_hold_on_missing_leg_quote():
    """Missing leg NBBO -> hold (never exit blind), even when the row-7 signal is true."""
    s = Rsi2OverboughtBearCall()
    hub = FakeHub()
    hub.daily["SPY"] = bars([700.0] * 215)           # under-5d-SMA exit would fire
    hub.nbbo = {"C631": (2.60, 2.70, 5.0)}           # long leg quote missing
    assert s.manage(_pos(), _ctx(EVAL, hub)) is None


# --------------------------------------------------------------------------- meta
def test_meta_doctrine_pins():
    m = Rsi2OverboughtBearCall.META
    assert m.strategy_id == "rsi2_overbought_bear_call" and m.version == 1
    assert m.universe == ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")
    assert m.dte_range == (5, 16)
    assert m.max_concurrent == 9                                     # one per symbol (row 5)
    assert m.event_policy.value == "trade_through"                   # §3.6: no event gate
    assert m.grading_basis.value == "max_loss"                       # §10: width - credit
    assert m.defining_mechanism == "directional_mean_reversion"
    assert m.settle_at_expiry is False                               # row 16 force-close
    assert m.scan_interval_s == 300.0 and m.mark_interval_s == 300.0
    assert m.expected_fires_per_20_sessions == 3.0                   # ~2.5/month (§10)
    assert len(Rsi2OverboughtBearCall().config_hash()) == 12
