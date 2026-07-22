"""gap_fade_bull_put vs its verified brief (docs/strategies/briefs/gap_fade_bull_put.md).
Each test cites the brief row it pins. Fake hub, no network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from atlas.strategy_lab.strategies.gap_fade_bull_put import GapFadeBullPut
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")
MON = datetime(2026, 7, 20, 10, 0, tzinfo=NY)       # a real Monday, 10:00 ET (minute 600)
DAY = "2026-07-20"


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
    close: float


class FakeHub:
    """Controllable market surface: refs, daily history, expirations, chains, and a
    deterministic row_greeks stub (delta by strike) so the delta-cap selection is exact."""

    def __init__(self):
        self.refs = {}
        self.history = {}
        self.exps = ["2026-07-20", "2026-07-22", "2026-08-21"]
        self.chains = {}
        self.deltas = {501.0: -0.62, 498.0: -0.45, 497.0: -0.33,
                       496.0: -0.24, 495.0: -0.17}

    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)

    def daily_history(self, sym, days=45, **kw):
        return self.history.get(sym, [])

    def expirations(self, sym, **kw):
        return list(self.exps)

    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])

    def row_greeks(self, **kw):
        d = self.deltas.get(kw["strike"])
        if d is None:
            return None
        return {"iv": 0.25, "delta": d, "gamma": 0.01, "vega": 0.3, "theta_day": -0.05}


def _hist(prior_close=500.0, with_today_partial=True):
    """30 older bars + Friday prior close + (optionally) today's PARTIAL daily bar, which
    the gap arithmetic must ignore (rows 1-2: prior RTH close, ts date < today)."""
    bars = [Bar(f"2026-06-{d:02d}", 503.0) for d in range(1, 31)]
    bars.append(Bar("2026-07-17", prior_close))
    if with_today_partial:
        bars.append(Bar("2026-07-20", 498.6))
    return bars


def _spy_chain():
    return [Row("P501", "put", 501.0, 1.90, 2.10),          # above ref - excluded
            Row("P498", "put", 498.0, 0.95, 1.05),          # delta -0.45 - cap-rejected
            Row("P497", "put", 497.0, 0.70, 0.78),          # short (delta -0.33)
            Row("P496", "put", 496.0, 0.44, 0.50),          # long (1 live strike below)
            Row("P495", "put", 495.0, 0.30, 0.36),
            Row("C497", "call", 497.0, 0.70, 0.80),         # call - excluded
            Row("P494_dead", "put", 494.0, 0.0, 0.0)]       # one-sided - excluded


def _hub(ref=498.50):
    hub = FakeHub()
    hub.refs["SPY"] = ref
    hub.history["SPY"] = _hist()
    hub.chains[("SPY", "2026-07-20")] = _spy_chain()
    return hub


def _ctx(dt, hub, open_positions=(), earnings=None, in_blackout=""):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=960, hub=hub,
                           in_blackout=in_blackout, earnings=earnings or {}, journal=None,
                           open_positions=list(open_positions))


def _pos(notes="default", nearest_expiry=date(2026, 7, 22)):
    if notes == "default":
        notes = {"prior_close": 500.0, "stop_level": 497.0, "gap_pct": -0.3}
    legs = [SimpleNamespace(spec=SimpleNamespace(strike=497.0, side=-1)),
            SimpleNamespace(spec=SimpleNamespace(strike=496.0, side=+1))]
    return SimpleNamespace(underlying="SPY", notes=notes, legs=legs,
                           nearest_expiry=nearest_expiry, entry_day=DAY)


def test_gap_math_prior_close_and_entry():
    """Rows 1-2 + task spec: gap% = ref/prior_close - 1 with prior close = last bar dated
    BEFORE today (today's partial daily bar ignored). Hand values: 498.50/500.00 - 1 = -0.3%."""
    s = GapFadeBullPut()
    proposals = s.scan(_ctx(MON, _hub(ref=498.50)))
    assert len(proposals) == 1
    p = proposals[0]
    assert p.underlying == "SPY" and p.kind == "bull_put_spread"
    assert p.signal["gap_pct"] == -0.3                 # hand math, NOT vs today's 498.6 bar
    assert p.signal["prior_close"] == 500.0            # Friday close, not 503, not 498.6
    assert p.signal["notes"] == {"prior_close": 500.0, "stop_level": 497.0,
                                 "gap_pct": -0.3}      # manage()'s persisted thesis levels


def test_gap_band_boundaries():
    """Rows 3-4: trade ONLY the 0.20% <= gap-down <= 0.40% band, both ends inclusive.
    Too-small, too-large, flat, and gap-UP mornings are all rejected."""
    s = GapFadeBullPut()
    for ref, n in [(499.05, 0),      # -0.19% - below the band (sub-0.2% has no premium)
                   (499.00, 1),      # -0.20% - inclusive lower edge
                   (498.00, 1),      # -0.40% - inclusive upper edge
                   (497.95, 0),      # -0.41% - published fade-failure zone
                   (500.00, 0),      # flat - no gap
                   (501.00, 0)]:     # gap UP - wrong direction (row 2)
        assert len(s.scan(_ctx(MON, _hub(ref=ref)))) == n, f"ref={ref}"


def test_entry_window_gating():
    """Rows 5-7: entries only in 09:45 ET (opening range complete) through the 11:30 ET
    cutoff (exclusive)."""
    s = GapFadeBullPut()
    hub = _hub()
    assert s.scan(_ctx(MON.replace(hour=9, minute=44), hub)) == []     # range not complete
    assert len(s.scan(_ctx(MON.replace(hour=9, minute=45), hub))) == 1
    assert len(s.scan(_ctx(MON.replace(hour=11, minute=29), hub))) == 1
    assert s.scan(_ctx(MON.replace(hour=11, minute=30), hub)) == []    # past the cutoff


def test_blackout_suppresses_scan():
    """META BLACKOUT (platform tightening of brief row 23): never fade a gap into a macro
    release window - scan() itself re-checks ctx.in_blackout."""
    s = GapFadeBullPut()
    assert s.scan(_ctx(MON, _hub(), in_blackout="macro_blackout:CPI")) == []


def test_one_per_underlying_per_day():
    """Rows 17/25: an open spread occupies the underlying, and a position entered today
    (pos.entry_day) blocks re-entry - no stacking, no rolls."""
    s = GapFadeBullPut()
    entered_today = SimpleNamespace(underlying="SPY", entry_day=DAY,
                                    nearest_expiry=date(2026, 7, 22))
    assert s.scan(_ctx(MON, _hub(), open_positions=[entered_today])) == []
    held_from_friday = SimpleNamespace(underlying="SPY", entry_day="2026-07-17",
                                       nearest_expiry=date(2026, 7, 22))
    assert s.scan(_ctx(MON, _hub(), open_positions=[held_from_friday])) == []


def test_spread_construction_delta_cap_and_width():
    """Rows 8-11: short put = highest live strike with |delta| <= 0.35 (498 at -0.45 is
    cap-rejected, 497 at -0.33 selected); long put = 1 listed live strike below; both legs
    same 0-5 DTE expiry (0DTE chosen over the +2d listing, row 13)."""
    s = GapFadeBullPut()
    p = s.scan(_ctx(MON, _hub()))[0]
    short, long_ = p.legs
    assert short["side"] == -1 and short["opt_type"] == "put" and short["strike"] == 497.0
    assert long_["side"] == +1 and long_["opt_type"] == "put" and long_["strike"] == 496.0
    assert short["expiry"] == "2026-07-20" and long_["expiry"] == "2026-07-20"
    assert short["delta"] == -0.33 and short["occ"] == "P497" and long_["occ"] == "P496"
    assert p.signal["width"] == 1.0
    assert p.signal["credit_worst"] == 0.20            # short bid 0.70 - long ask 0.50
    assert p.signal["dte_days"] == 0
    # no live strike below the short -> no trade (defined-risk only, row 11)
    hub = _hub()
    hub.chains[("SPY", "2026-07-20")] = [r for r in _spy_chain() if r.strike >= 497.0]
    assert s.scan(_ctx(MON, hub)) == []


def test_credit_floor_boundary():
    """Row 12: worst-ledger credit (short bid - long ask) >= 15% of width, else no trade.
    Exactly 15% is accepted; below is premium-dead and refused."""
    s = GapFadeBullPut()
    hub = _hub()
    chain = _spy_chain()
    chain[2] = Row("P497", "put", 497.0, 0.65, 0.75)   # credit 0.65 - 0.50 = 0.15 == floor
    hub.chains[("SPY", "2026-07-20")] = chain
    p = s.scan(_ctx(MON, hub))[0]
    assert p.signal["credit_worst"] == 0.15 and p.signal["credit_frac_of_width"] == 0.15
    chain[2] = Row("P497", "put", 497.0, 0.60, 0.70)   # credit 0.10 < 0.15 -> reject
    assert s.scan(_ctx(MON, hub)) == []


def test_expiry_selection_dte_band():
    """Row 13: nearest listed expiration 0-5 calendar DTE; nothing in band -> no trade."""
    s = GapFadeBullPut()
    hub = _hub()
    hub.exps = ["2026-07-26", "2026-08-21"]            # 6 and 32 DTE - both out of band
    assert s.scan(_ctx(MON, hub)) == []
    hub.exps = ["2026-07-25", "2026-08-21"]            # 5 DTE - inclusive upper edge
    hub.chains[("SPY", "2026-07-25")] = _spy_chain()
    p = s.scan(_ctx(MON, hub))[0]
    assert p.legs[0]["expiry"] == "2026-07-25" and p.signal["dte_days"] == 5


def test_earnings_gate_single_names():
    """Row 22: single names SKIP when earnings fall in [entry day, expiry] (the canonical
    breakaway-gap defense); earnings after expiry do not block; ETFs are never gated."""
    s = GapFadeBullPut()
    hub = _hub()
    hub.exps = ["2026-07-24"]                          # one 4-DTE listing for everyone
    hub.chains[("SPY", "2026-07-24")] = _spy_chain()
    hub.refs["TSLA"] = 249.25                          # 249.25/250 - 1 = -0.3% - in band
    hub.history["TSLA"] = [Bar("2026-07-17", 250.0)]
    hub.chains[("TSLA", "2026-07-24")] = [Row("T248", "put", 248.0, 0.95, 1.05),
                                          Row("T247", "put", 247.0, 0.62, 0.70)]
    hub.deltas.update({248.0: -0.32, 247.0: -0.22})
    earnings = {"TSLA": {"date": "2026-07-22", "hour": "amc"}}
    got = {p.underlying for p in s.scan(_ctx(MON, hub, earnings=earnings))}
    assert got == {"SPY"}                              # TSLA gated: earnings <= expiry
    earnings = {"TSLA": {"date": "2026-07-27", "hour": "amc"}}
    got = {p.underlying for p in s.scan(_ctx(MON, hub, earnings=earnings))}
    assert got == {"SPY", "TSLA"}                      # after expiry: no exposure to the print


def test_manage_profit_and_stop_boundaries():
    """Rows 14-15: close when the underlying trades AT/ABOVE the prior close (gap filled,
    inclusive); close when strictly BELOW the short-strike shelf (fade dead); hold between."""
    s = GapFadeBullPut()
    hub = FakeHub()

    def act(S):
        hub.refs["SPY"] = S
        return s.manage(_pos(), _ctx(MON, hub))

    a = act(500.00)                                    # target touched exactly
    assert a is not None and a.action == "close" and a.rule == "gap_filled"
    assert act(499.99) is None                         # a cent short of the fill - hold
    assert act(497.00) is None                         # AT the shelf - hold (strictly below)
    b = act(496.99)
    assert b is not None and b.rule == "fade_thesis_dead"
    hub.refs.pop("SPY")                                # missing quote -> hold, never guess
    assert s.manage(_pos(), _ctx(MON, hub)) is None


def test_manage_expiry_day_force_close():
    """Row 16: on expiry day at/after 15:30 ET, force-close when the short strike is ITM or
    within 0.25% of spot; comfortably OTM holds (platform backstop takes the worthless
    buyback). Before 15:30, and on non-expiry days, the doctrine does not fire."""
    s = GapFadeBullPut()
    hub = FakeHub()
    late = MON.replace(hour=15, minute=30)             # minute 930

    def act(S, dt=late, expiry=date(2026, 7, 20), notes="default"):
        hub.refs["SPY"] = S
        return s.manage(_pos(notes=notes, nearest_expiry=expiry), _ctx(dt, hub))

    a = act(497.50)                                    # 497 >= 497.5*0.9975 - near-miss ITM
    assert a is not None and a.rule == "expiry_itm_force_close"
    assert act(499.50) is None                         # comfortably OTM - ride the backstop
    assert act(497.50, dt=MON.replace(hour=15, minute=29)) is None      # before 15:30
    assert act(497.50, expiry=date(2026, 7, 22)) is None                # not expiry day
    assert act(496.50).rule == "fade_thesis_dead"      # shelf stop outranks the expiry rule
    assert act(496.50, notes={}).rule == "expiry_itm_force_close"       # notes-less fallback


def test_meta_doctrine_pins():
    m = GapFadeBullPut.META
    assert m.strategy_id == "gap_fade_bull_put" and m.version == 1
    assert m.event_policy.value == "blackout"          # never fade into a macro window
    assert m.grading_basis.value == "max_loss"         # width - credit (brief §10)
    assert m.settle_at_expiry is False                 # platform backstop covers expiry
    assert m.dte_range == (0, 6) and m.max_concurrent == 3
    assert m.defining_mechanism == "directional_mean_reversion"
    assert m.expected_fires_per_20_sessions == 10.0
    assert m.universe == ("SPY", "QQQ", "IWM", "AAPL", "NVDA", "MSFT", "TSLA", "AMD", "META")
    assert len(GapFadeBullPut().config_hash()) == 12
