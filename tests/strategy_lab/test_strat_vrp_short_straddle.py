"""vrp_short_straddle vs its verified brief (docs/strategies/briefs/vrp_short_straddle.md).
Each test cites the brief row it pins. Fake hub, no network. Realized vol is HAND-COMPUTED
in-test (alternating-close series with closed-form stdev) - never trusted from the module."""

from __future__ import annotations

import dataclasses
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from atlas.strategy_lab.hub import MarketHub
from atlas.strategy_lab.strategies.vrp_short_straddle import VrpParams, VrpShortStraddle
from atlas.strategy_lab.strategy import StrategyContext

from .conftest import leg

NY = ZoneInfo("America/New_York")
WED = datetime(2026, 7, 22, 10, 30, tzinfo=NY)      # scan day; 2026-08-21 is exactly 30 DTE


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float


@dataclass
class Bar:
    close: float


class FakeHub:
    def __init__(self):
        self.chains = {}
        self.refs = {"SPY": 630.40}
        self.exps = {"SPY": ["2026-08-14", "2026-08-21", "2026-09-18"]}  # dte 23 / 30 / 58
        self.hist = {}                       # sym -> [Bar]
        self.vr = None                       # vol_regime payload | None
        self.nbbo = {}                       # occ -> (bid, ask, age_s)
    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)
    def expirations(self, sym, **kw):
        return self.exps.get(sym, [])
    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])
    def daily_history(self, sym, **kw):
        return self.hist.get(sym, [])
    def vol_regime(self, **kw):
        return self.vr
    def last_nbbo(self, occ):
        return self.nbbo.get(occ)
    row_greeks = staticmethod(MarketHub.row_greeks)


def _ctx(dt, hub, open_positions=(), journal=None):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=975, hub=hub,
                           earnings={}, journal=journal,
                           open_positions=list(open_positions))


def _spy_chain():
    """ATM pairs at 625/630/635 around ref 630.40; straddle mids price ~15 vol at 30 DTE."""
    return [Row("C625", "call", 625.0, 13.5, 13.7), Row("P625", "put", 625.0, 8.3, 8.5),
            Row("C630", "call", 630.0, 10.9, 11.1), Row("P630", "put", 630.0, 10.6, 10.8),
            Row("C635", "call", 635.0, 8.4, 8.6), Row("P635", "put", 635.0, 13.0, 13.2)]


def _alt_closes(lo: float, hi: float, n: int = 253):
    """Alternating close series -> hand-computable HV (row 9 formula, replicated in-test)."""
    return [Bar(lo if i % 2 == 0 else hi) for i in range(n)]


def _hand_hv(bars):
    closes = [b.close for b in bars][-253:]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    return statistics.stdev(rets) * math.sqrt(252.0)


LOW_HV_BARS = _alt_closes(100.0, 100.5)     # HV ~ 0.079 - well under a ~0.15 IV
HIGH_HV_BARS = _alt_closes(100.0, 110.0)    # HV ~ 1.52 - dwarfs any sane IV


def test_vrp_gate_blocks_negative_vrp():
    """Row 8: IV - HV <= 0 -> NO entry, journaled with the hand-computed HV."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-08-21")] = _spy_chain()
    hub.hist["SPY"] = HIGH_HV_BARS
    logs = []
    s = VrpShortStraddle()
    assert s.scan(_ctx(WED, hub, journal=logs.append)) == []
    blocked = [e for e in logs if e["event"] == "vrp_gate_blocked"]
    assert len(blocked) == 1 and blocked[0]["symbol"] == "SPY"
    assert blocked[0]["hv"] == round(_hand_hv(HIGH_HV_BARS), 4)     # ~1.52, hand-checked
    assert blocked[0]["vrp"] < 0


def test_vrp_gate_passes_positive_vrp_hand_computed():
    """Rows 8/9/10: hand-computed HV below solved ATM IV -> entry, signal numbers exact."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-08-21")] = _spy_chain()
    hub.hist["SPY"] = LOW_HV_BARS
    s = VrpShortStraddle()
    proposals = s.scan(_ctx(WED, hub))
    assert len(proposals) == 1
    sig = proposals[0].signal
    hv_exp = _hand_hv(LOW_HV_BARS)
    g_c = MarketHub.row_greeks(opt_type="call", strike=630.0, S=630.40,
                               mid=(10.9 + 11.1) / 2.0, dte_days=30)
    g_p = MarketHub.row_greeks(opt_type="put", strike=630.0, S=630.40,
                               mid=(10.6 + 10.8) / 2.0, dte_days=30)
    iv_exp = (g_c["iv"] + g_p["iv"]) / 2.0                    # row 10: mean of call+put IV
    assert sig["hv"] == round(hv_exp, 4)
    assert sig["iv"] == round(iv_exp, 4)
    assert sig["vrp"] == round(iv_exp - hv_exp, 4) and sig["vrp"] > 0
    assert sig["iv_source"] == "atm_mean"
    assert sig["dte_days"] == 30


def test_atm_same_strike_both_legs_construction():
    """Rows 4/6 + row 20: short 1 call + short 1 put, SAME strike nearest spot, both legs
    two-sided; a closer strike missing one leg is skipped."""
    hub = FakeHub()
    hub.refs["SPY"] = 630.60                                   # 631 would be nearest...
    chain = _spy_chain() + [Row("P631", "put", 631.0, 10.2, 10.4)]   # ...but has NO call
    hub.chains[("SPY", "2026-08-21")] = chain
    hub.hist["SPY"] = LOW_HV_BARS
    s = VrpShortStraddle()
    proposals = s.scan(_ctx(WED, hub))
    assert len(proposals) == 1
    p = proposals[0]
    assert p.kind == "short_straddle"
    assert len(p.legs) == 2
    assert {l["opt_type"] for l in p.legs} == {"call", "put"}
    assert all(l["side"] == -1 and l["qty"] == 1 for l in p.legs)
    assert {l["strike"] for l in p.legs} == {630.0}            # paired strike, not 631
    assert {l["expiry"] for l in p.legs} == {"2026-08-21"}
    assert p.signal["credit_bid"] == round(10.9 + 10.6, 4)     # both-legs bid credit
    call = next(l for l in p.legs if l["opt_type"] == "call")
    put = next(l for l in p.legs if l["opt_type"] == "put")
    assert call["delta"] > 0 > put["delta"]                    # solved greeks present


def test_dte_band_nearest_30_and_no_expiry():
    """Rows 2/3: pick the expiry nearest 30 DTE inside 25-35; nothing in band -> skip."""
    hub = FakeHub()
    hub.exps["SPY"] = ["2026-08-19", "2026-08-24"]             # dte 28 vs 33 -> 28 wins
    hub.chains[("SPY", "2026-08-19")] = _spy_chain()
    hub.hist["SPY"] = LOW_HV_BARS
    s = VrpShortStraddle()
    proposals = s.scan(_ctx(WED, hub))
    assert [p.legs[0]["expiry"] for p in proposals] == ["2026-08-19"]

    hub2 = FakeHub()
    hub2.exps["SPY"] = ["2026-08-14", "2026-08-28"]            # dte 23 / 37: both outside
    hub2.hist["SPY"] = LOW_HV_BARS
    logs = []
    assert s.scan(_ctx(WED, hub2, journal=logs.append)) == []
    assert [e["event"] for e in logs] == ["vrp_no_expiry"]


def test_moneyness_band_blocks_far_strikes():
    """Row 5: only strikes with K/S in [0.975, 1.025] are eligible ATM candidates."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-08-21")] = [                      # 600/630.4=0.952, 660=1.047
        Row("C600", "call", 600.0, 33.0, 33.4), Row("P600", "put", 600.0, 3.0, 3.2),
        Row("C660", "call", 660.0, 2.1, 2.3), Row("P660", "put", 660.0, 31.0, 31.4)]
    hub.hist["SPY"] = LOW_HV_BARS
    logs = []
    s = VrpShortStraddle()
    assert s.scan(_ctx(WED, hub, journal=logs.append)) == []
    assert [e["event"] for e in logs] == ["vrp_no_atm_strike"]


def test_insufficient_history_skips():
    """Row 9: the 12-month window needs 253 closes - fewer -> no HV -> no entry (journaled)."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-08-21")] = _spy_chain()
    hub.hist["SPY"] = _alt_closes(100.0, 100.5, n=200)         # short of 253
    logs = []
    s = VrpShortStraddle()
    assert s.scan(_ctx(WED, hub, journal=logs.append)) == []
    assert [e["event"] for e in logs] == ["vrp_no_history"]
    assert logs[0]["need_closes"] == 253


def test_vix_fallback_and_no_iv_skip():
    """Row 11 + task fallback: no solvable leg IV -> VIX close/100 as implied; vol_regime
    None AND no computable IV -> skip with journal."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-08-21")] = _spy_chain()
    hub.hist["SPY"] = LOW_HV_BARS
    hub.row_greeks = lambda **kw: None                         # force: no computable IV
    hub.vr = {"vix_close": 30.0, "day": "2026-07-21"}
    s = VrpShortStraddle()
    proposals = s.scan(_ctx(WED, hub))
    assert len(proposals) == 1
    assert proposals[0].signal["iv"] == 0.3                    # 30.0/100 - unit-normalized
    assert proposals[0].signal["iv_source"] == "vix_close"
    assert proposals[0].signal["vix_close"] == 30.0

    hub.vr = None                                              # now nothing to gate on
    logs = []
    assert s.scan(_ctx(WED, hub, journal=logs.append)) == []
    assert [e["event"] for e in logs] == ["vrp_no_iv"]


def test_one_open_straddle_per_underlying():
    """Row 18 (enforced parenthetical): an open SPY straddle blocks a new SPY entry."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-08-21")] = _spy_chain()
    hub.hist["SPY"] = LOW_HV_BARS

    class OpenPos:
        underlying = "SPY"
    s = VrpShortStraddle()
    assert s.scan(_ctx(WED, hub, open_positions=[OpenPos()])) == []
    assert len(s.scan(_ctx(WED, hub))) == 1                    # control: fires when clear


# ---------------------------------------------------------------- manage (rows 14/15/16)
STRADDLE_LEGS = [leg("SPYC630", "call", 630.0, -1, bid=5.0, ask=5.2, delta=0.52),
                 leg("SPYP630", "put", 630.0, -1, bid=4.8, ask=5.0, delta=-0.48)]


def _open_straddle(combo_factory):
    rec, pos = combo_factory(STRADDLE_LEGS, declared_basis="car", S=630.40,
                             strategy_id="vrp_short_straddle", kind="short_straddle")
    assert -pos.net_open["optimistic"] == 10.0                 # credit = sum of entry mids
    return pos


def test_profit_target_boundary_exact(combo_factory):
    """Row 14: $10 credit closes when the straddle REACHES $7.50 (25% of credit kept) - 
    inclusive boundary; one cent above holds."""
    pos = _open_straddle(combo_factory)
    hub = FakeHub()
    s = VrpShortStraddle()
    hub.nbbo = {"SPYC630": (3.70, 3.80, 4.0), "SPYP630": (3.70, 3.80, 4.0)}   # cost 7.50
    act = s.manage(pos, _ctx(WED, hub))
    assert act is not None and act.action == "close" and act.rule == "profit_25pct"
    assert act.state["credit_ps"] == 10.0 and act.state["cost_ps"] == 7.5

    hub.nbbo["SPYP630"] = (3.70, 3.82, 4.0)                    # cost 7.51 -> not reached
    assert s.manage(pos, _ctx(WED, hub)) is None


def test_stop_loss_boundary_exact(combo_factory):
    """Row 15: -100% stop - $10 credit closes when the straddle REACHES $20 (doubled);
    one cent below holds."""
    pos = _open_straddle(combo_factory)
    hub = FakeHub()
    s = VrpShortStraddle()
    hub.nbbo = {"SPYC630": (9.90, 10.10, 4.0), "SPYP630": (9.90, 10.10, 4.0)}  # cost 20.0
    act = s.manage(pos, _ctx(WED, hub))
    assert act is not None and act.action == "close" and act.rule == "stop_100pct"
    assert act.state["cost_ps"] == 20.0

    hub.nbbo["SPYP630"] = (9.90, 10.08, 4.0)                   # cost 19.99 -> hold (row 16)
    assert s.manage(pos, _ctx(WED, hub)) is None


def test_hold_on_missing_or_dead_quotes(combo_factory):
    """Task pin: any leg with no last_nbbo (or a dead 0x0 quote) -> hold, even at levels
    that would otherwise fire either rule."""
    pos = _open_straddle(combo_factory)
    hub = FakeHub()
    s = VrpShortStraddle()
    hub.nbbo = {"SPYC630": (0.10, 0.20, 4.0)}                  # put quote MISSING
    assert s.manage(pos, _ctx(WED, hub)) is None
    hub.nbbo["SPYP630"] = (0.0, 0.0, 4.0)                      # dead quote -> still hold
    assert s.manage(pos, _ctx(WED, hub)) is None


def test_meta_and_params_doctrine_pins():
    m = VrpShortStraddle.META
    assert m.strategy_id == "vrp_short_straddle" and m.version == 1
    assert m.universe == ("SPY", "QQQ", "IWM")                 # ETF tier this wave
    assert m.dte_range == (25, 35)                             # row 3
    assert m.max_concurrent == 3                               # one per symbol (row 18)
    assert m.grading_basis.value == "car"                      # row 22: naked short -> CaR
    assert m.event_policy.value == "trade_through"             # §3.5: no published event gate
    assert m.settle_at_expiry is False                         # platform backstop deviation
    assert m.scan_interval_s == 300 and m.mark_interval_s == 300
    assert m.expected_fires_per_20_sessions == 6

    p = VrpShortStraddle.params
    assert (p.profit_target_frac, p.stop_loss_mult) == (0.25, 2.0)     # rows 14/15
    assert (p.dte_target, p.dte_min, p.dte_max) == (30, 25, 35)        # rows 2/3
    assert (p.moneyness_lo, p.moneyness_hi) == (0.975, 1.025)          # row 5
    assert p.hv_lookback_td == 252                                     # row 9
    assert dataclasses.is_dataclass(p)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.profit_target_frac = 0.5                             # doctrine is frozen
    assert len(VrpShortStraddle().config_hash()) == 12
