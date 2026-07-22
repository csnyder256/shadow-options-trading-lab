"""atm_calendar_low_iv vs its verified brief (docs/strategies/briefs/atm_calendar_low_iv.md).
Each test cites the brief row (§8 table) it pins. Fake hub, no network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

import atlas.strategy_lab.strategies.atm_calendar_low_iv as cal_mod
from atlas.strategy_lab.carisk import grading_block
from atlas.strategy_lab.hub import MarketHub
from atlas.strategy_lab.model import ComboPosition, LegSpec, LegState
from atlas.strategy_lab.strategies.atm_calendar_low_iv import AtmCalendarLowIv
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")
MON = datetime(2026, 7, 20, 10, 30, tzinfo=NY)          # a real Monday, mid-session
LOW_REGIME = {"asof": "2026-07-17", "vix_close": 13.9, "vix_pctile_252d": 22.0}


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float


class FakeHub:
    def __init__(self):
        self.chains = {}
        self.refs = {"SPY": 630.40}
        self.exps = ["2026-07-24",            # 4 DTE - below front window
                     "2026-07-28",            # 8 DTE - front pick
                     "2026-07-30",            # 10 DTE - in window, later
                     "2026-08-21",            # 32 DTE - back pick
                     "2026-08-28",            # 39 DTE - in window, later
                     "2026-09-18"]            # 60 DTE - beyond back window
        self.regime = dict(LOW_REGIME)
        self.nbbo = {}
    def vol_regime(self, max_age_days=5):
        return self.regime
    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)
    def expirations(self, sym, **kw):
        return self.exps
    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])
    def last_nbbo(self, occ):
        return self.nbbo.get(occ)
    row_greeks = staticmethod(MarketHub.row_greeks)


def _ctx(dt, hub, open_positions=(), journal=None):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=975, hub=hub,
                           journal=journal, open_positions=list(open_positions))


def _load_spy(hub):
    hub.chains[("SPY", "2026-07-28")] = [
        Row("SPY260728C628", "call", 628.0, 6.60, 6.80),
        Row("SPY260728C630", "call", 630.0, 5.50, 5.70),
        Row("SPY260728C632", "call", 632.0, 4.50, 4.70),
        Row("SPY260728P630", "put", 630.0, 5.00, 5.20),      # put - excluded (row 3: calls)
        Row("SPY260728C631", "call", 631.0, 0.0, 5.10)]      # one-sided - excluded (row 19)
    hub.chains[("SPY", "2026-08-21")] = [
        Row("SPY260821C628", "call", 628.0, 12.70, 13.00),
        Row("SPY260821C630", "call", 630.0, 11.60, 11.90),
        Row("SPY260821C632", "call", 632.0, 10.60, 10.90)]


def _spy_proposals(hub):
    return [p for p in AtmCalendarLowIv().scan(_ctx(MON, hub)) if p.underlying == "SPY"]


# --------------------------------------------------------------------------- entry gate
def test_low_iv_gate_passes_low_and_blocks_high():
    """Rows 7/8: LOW-vol entry gate - VIX 252d percentile strictly < 30 admits, >= 30 blocks
    (the INVERSE of the premium-sellers' gate)."""
    hub = FakeHub()
    _load_spy(hub)
    assert len(_spy_proposals(hub)) == 1               # pctile 22 -> enter
    hub.regime = dict(LOW_REGIME, vix_pctile_252d=75.0)
    assert _spy_proposals(hub) == []                   # high vol -> blocked
    hub.regime = dict(LOW_REGIME, vix_pctile_252d=30.0)
    assert _spy_proposals(hub) == []                   # boundary: 30.0 blocks (strict <)
    hub.regime = dict(LOW_REGIME, vix_pctile_252d=29.9)
    assert len(_spy_proposals(hub)) == 1               # 29.9 passes


def test_gate_unavailable_skips_and_journals():
    """Row 8 fallback ladder: no vol_regime data -> NO entry (low IV is the affirmative
    entry condition, never presumed) + cal_gate_unavailable journal."""
    hub = FakeHub()
    _load_spy(hub)
    events = []
    hub.regime = None
    s = AtmCalendarLowIv()
    assert s.scan(_ctx(MON, hub, journal=events.append)) == []
    assert [e["event"] for e in events] == ["cal_gate_unavailable"]
    hub.regime = {"asof": "2026-07-17", "vix_pctile_252d": None}
    assert s.scan(_ctx(MON, hub)) == []


# --------------------------------------------------------------------------- construction
def test_calendar_construction_same_strike_long_back():
    """Rows 1-4: short FRONT call + long BACK call, SAME strike nearest spot, 1:1, long
    expiry strictly AFTER short (covered shape); windowed expiry picks; net long vega."""
    hub = FakeHub()
    _load_spy(hub)
    (p,) = _spy_proposals(hub)
    assert p.kind == "atm_call_calendar" and p.risk_flags == []
    assert len(p.legs) == 2
    front, back = p.legs
    assert front["side"] == -1 and back["side"] == +1
    assert front["opt_type"] == "call" and back["opt_type"] == "call"      # row 3
    assert front["strike"] == back["strike"] == 630.0    # row 4: nearest 630.40 (same strike)
    assert front["qty"] == back["qty"] == 1              # row 2: 1:1
    assert front["expiry"] == "2026-07-28"               # earliest in [7,10] DTE window
    assert back["expiry"] == "2026-08-21"                # earliest in [30,40] DTE window
    assert date.fromisoformat(back["expiry"]) > date.fromisoformat(front["expiry"])
    for leg in p.legs:                                   # row 19: two-sided NBBO both legs
        assert leg["nbbo"]["bid"] > 0 and leg["nbbo"]["ask"] > 0
    assert p.signal["debit_mid"] == pytest.approx(11.75 - 5.60)   # net debit paid
    assert p.signal["net_vega"] > 0                      # §3.6: long time spread = +vega
    assert p.signal["gate_rung"] == "vix_pctile_252d"


def test_two_sided_nbbo_required_on_both_legs():
    """Row 19: a strike missing a two-sided market in EITHER expiry is ineligible - the
    strategy falls to the nearest strike quoted two-sided in BOTH."""
    hub = FakeHub()
    _load_spy(hub)
    hub.chains[("SPY", "2026-08-21")] = [
        Row("SPY260821C628", "call", 628.0, 12.70, 13.00),
        Row("SPY260821C630", "call", 630.0, 0.0, 11.90),     # ATM back leg one-sided
        Row("SPY260821C632", "call", 632.0, 10.60, 10.90)]
    (p,) = _spy_proposals(hub)
    assert p.legs[0]["strike"] == p.legs[1]["strike"] == 632.0    # next-nearest common strike


def test_one_open_calendar_per_underlying():
    """Row 20: an open calendar blocks re-entry on that symbol only."""
    hub = FakeHub()
    _load_spy(hub)
    hub.refs["QQQ"] = 560.20
    hub.chains[("QQQ", "2026-07-28")] = [Row("QQQ260728C560", "call", 560.0, 4.90, 5.10)]
    hub.chains[("QQQ", "2026-08-21")] = [Row("QQQ260821C560", "call", 560.0, 10.30, 10.60)]

    class OpenPos:
        underlying = "SPY"
    got = {p.underlying for p in AtmCalendarLowIv().scan(_ctx(MON, hub, open_positions=[OpenPos()]))}
    assert got == {"QQQ"}                               # SPY blocked, QQQ still proposed


# --------------------------------------------------------------------------- manage/exit
class ManageHub:
    def __init__(self, S=0.0, short_nbbo=None):
        self.S = S
        self.short_nbbo = short_nbbo
    def ref_price(self, sym):
        return self.S
    def last_nbbo(self, occ):
        return self.short_nbbo


def _pos(front_exp: date, back_exp: date, K: float = 630.0) -> ComboPosition:
    front = LegState(spec=LegSpec(occ="F", underlying="SPY", opt_type="call", strike=K,
                                  expiry=front_exp, side=-1),
                     entry_bid=5.50, entry_ask=5.70,
                     open_fills={"worst": 5.50, "base": 5.60, "optimistic": 5.70})
    back = LegState(spec=LegSpec(occ="B", underlying="SPY", opt_type="call", strike=K,
                                 expiry=back_exp, side=+1),
                    entry_bid=11.60, entry_ask=11.90,
                    open_fills={"worst": 11.90, "base": 11.75, "optimistic": 11.60})
    return ComboPosition(position_id="x", strategy_id="atm_calendar_low_iv",
                         strategy_config_hash="h", kind="atm_call_calendar", underlying="SPY",
                         legs=[front, back],
                         net_open={"worst": 6.40, "base": 6.15, "optimistic": 5.90},
                         grading={"basis": "debit", "denom_usd": 640.0},
                         entry_ts=0.0, entry_minute=630, entry_day="2026-07-20",
                         entry_S=630.40)


def test_front_expiry_week_exit_boundary(monkeypatch):
    """Row 11: close BOTH legs T-5 TRADING days before front expiry - 6 trading days out
    holds, 5 fires; fires strictly BEFORE the runner's expiry-day backstop."""
    monkeypatch.setattr(cal_mod, "is_trading_day", lambda d, **kw: d.weekday() < 5)
    s = AtmCalendarLowIv()
    pos = _pos(date(2026, 8, 21), date(2026, 9, 18))    # front expires Friday 8/21
    hub = ManageHub()                                   # no quotes -> parity guard cannot fire
    hold = s.manage(pos, _ctx(datetime(2026, 8, 13, 10, 30, tzinfo=NY), hub))
    assert hold is None                                 # Thu 8/13: 6 trading days left
    act = s.manage(pos, _ctx(datetime(2026, 8, 14, 10, 30, tzinfo=NY), hub))
    assert act is not None and act.action == "close"    # Fri 8/14: exactly T-5
    assert act.rule == "front_expiry_week_exit"
    assert act.state["trading_days_to_front"] == 5
    assert date(2026, 8, 14) < date(2026, 8, 21)        # strategy exit precedes backstop day


def test_parity_assignment_guard(monkeypatch):
    """Row 12 (SOURCE-VERBATIM): close immediately when the ITM short call trades at parity
    (bid <= intrinsic); no fire when bid > intrinsic or the short is OTM."""
    monkeypatch.setattr(cal_mod, "is_trading_day", lambda d, **kw: d.weekday() < 5)
    s = AtmCalendarLowIv()
    pos = _pos(date(2026, 8, 21), date(2026, 9, 18))
    early = _ctx(datetime(2026, 7, 21, 10, 30, tzinfo=NY),
                 ManageHub(S=660.0, short_nbbo=(29.90, 30.40, 5.0)))
    act = s.manage(pos, early)                          # intrinsic 30.0 >= bid 29.90 -> parity
    assert act is not None and act.rule == "short_parity_assignment_guard"
    assert act.action == "close"
    above = _ctx(datetime(2026, 7, 21, 10, 30, tzinfo=NY),
                 ManageHub(S=660.0, short_nbbo=(30.55, 31.00, 5.0)))
    assert s.manage(pos, above) is None                 # bid > intrinsic: carry (time premium)
    otm = _ctx(datetime(2026, 7, 21, 10, 30, tzinfo=NY),
               ManageHub(S=600.0, short_nbbo=(0.05, 0.15, 5.0)))
    assert s.manage(pos, otm) is None                   # OTM: no assignment risk, hold


def test_no_stop_loss_no_profit_target(monkeypatch):
    """Rows 13/14: adverse breakout -> HOLD (risk fixed at the debit); pinned-at-strike
    profit zone -> HOLD (no armed profit trigger; front-week exit IS the profit event)."""
    monkeypatch.setattr(cal_mod, "is_trading_day", lambda d, **kw: d.weekday() < 5)
    s = AtmCalendarLowIv()
    pos = _pos(date(2026, 8, 21), date(2026, 9, 18))
    crash = _ctx(datetime(2026, 7, 21, 10, 30, tzinfo=NY),
                 ManageHub(S=560.0, short_nbbo=(0.01, 0.05, 5.0)))
    assert s.manage(pos, crash) is None                 # row 13: no stop through the breakout
    pinned = _ctx(datetime(2026, 7, 21, 10, 30, tzinfo=NY),
                  ManageHub(S=630.20, short_nbbo=(4.00, 4.20, 5.0)))
    assert s.manage(pos, pinned) is None                # row 14: no profit target armed


# --------------------------------------------------------------------------- grading
def test_grading_basis_debit_for_covered_calendar():
    """Row 16 + brief §10: same-strike covered calendar grades on the DEBIT basis - carisk
    derives it via the covered-multi-expiry rule; the reversed (short-back) shape does NOT."""
    hub = FakeHub()
    _load_spy(hub)
    (p,) = _spy_proposals(hub)
    legs_with_mid = [(LegSpec(occ=l["occ"], underlying=l["underlying"], opt_type=l["opt_type"],
                              strike=l["strike"], expiry=date.fromisoformat(l["expiry"]),
                              side=l["side"], qty=l["qty"]),
                      (l["nbbo"]["bid"] + l["nbbo"]["ask"]) / 2.0) for l in p.legs]
    worst = sum((l["nbbo"]["ask"] if l["side"] > 0 else l["nbbo"]["bid"]) * l["side"]
                for l in p.legs)                        # buy back at ask, sell front at bid
    g = grading_block(legs_with_mid=legs_with_mid, net_open_worst=worst, S=630.40,
                      declared_basis=AtmCalendarLowIv.META.grading_basis.value)
    assert g["basis"] == "debit" and g["basis_mismatch"] is False
    assert g["denom_usd"] == pytest.approx(round(worst * 100.0, 2))   # 11.90 - 5.50 = 6.40
    assert "multi-expiry" in g["payoff_note"]           # expiry payoff undefined -> covered rule
    flipped = [(LegSpec(occ=s_.occ, underlying=s_.underlying, opt_type=s_.opt_type,
                        strike=s_.strike, expiry=s_.expiry, side=-s_.side, qty=s_.qty), m)
               for s_, m in legs_with_mid]              # short back / long front: NOT covered
    g2 = grading_block(legs_with_mid=flipped, net_open_worst=-worst, S=630.40,
                       declared_basis="debit")
    assert g2["basis"] == "car" and g2["basis_mismatch"] is True


# --------------------------------------------------------------------------- meta
def test_meta_doctrine_pins():
    m = AtmCalendarLowIv.META
    assert m.strategy_id == "atm_calendar_low_iv" and m.version == 1
    assert m.universe == ("SPY", "QQQ", "IWM")
    assert m.dte_range == (5, 45)
    assert m.max_concurrent == 3                        # row 20: 1 per symbol x 3 ETFs
    assert m.event_policy.value == "trade_through"
    assert m.grading_basis.value == "debit"             # row 16: max loss = net debit
    assert m.defining_mechanism == "term_structure"
    assert m.settle_at_expiry is False                  # row 11: never rides into front expiry
    assert m.scan_interval_s == 300.0 and m.mark_interval_s == 300.0
    assert m.expected_fires_per_20_sessions == 2.0
    s = AtmCalendarLowIv()
    assert len(s.config_hash()) == 12
    assert s.params.vix_pctile_max == 30.0              # row 8 ADAPTED (threshold ours)
    assert s.params.front_exit_trading_days == 5        # row 11 ADAPTED T-5 trading days
