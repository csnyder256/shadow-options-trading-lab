"""wput_weekly_putwrite vs its verified brief (docs/strategies/briefs/wput_weekly_putwrite.md).
Each test cites the brief row it pins. Fake hub, no network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

import atlas.strategy_lab.strategies.wput_weekly_putwrite as wput_mod
from atlas.strategy_lab.hub import MarketHub
from atlas.strategy_lab.strategies.wput_weekly_putwrite import WputWeeklyPutWrite
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")
FRI = datetime(2026, 7, 24, 15, 57, tzinfo=NY)      # a real Friday, 15:57 ET
THU = datetime(2026, 7, 23, 15, 57, tzinfo=NY)


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
        self.exps = ["2026-07-24", "2026-07-31", "2026-08-07"]
    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)
    def expirations(self, sym, **kw):
        return self.exps
    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])
    row_greeks = staticmethod(MarketHub.row_greeks)


def _ctx(dt, hub, open_positions=(), earnings=None):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=975, hub=hub,
                           earnings=earnings or {}, journal=None,
                           open_positions=list(open_positions))


def _spy_chain():
    return [Row("P629", "put", 629.0, 3.10, 3.30), Row("P630", "put", 630.0, 3.55, 3.75),
            Row("P631", "put", 631.0, 4.05, 4.25),                     # above ref - excluded
            Row("C630", "call", 630.0, 3.60, 3.80),                    # call - excluded
            Row("P628_dead", "put", 628.0, 0.0, 0.0)]                  # one-sided - excluded


def test_friday_window_writes_first_strike_below_ref():
    """Rows 6/7/9: Friday final-minutes entry at the first strike strictly below reference."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-07-31")] = _spy_chain()
    s = WputWeeklyPutWrite()
    proposals = [p for p in s.scan(_ctx(FRI, hub)) if p.underlying == "SPY"]
    assert len(proposals) == 1
    p = proposals[0]
    assert p.kind == "short_put_weekly"
    leg = p.legs[0]
    assert leg["side"] == -1 and leg["opt_type"] == "put"
    assert leg["strike"] == 630.0                 # first below 630.40 (not 629, not 631)
    assert leg["expiry"] == "2026-07-31"          # 7 DTE, not today's expiry (row 5)
    assert p.signal["credit_bid"] == 3.55         # premium at bid (row 10)
    assert leg["delta"] < 0                       # solved put delta present


def test_not_roll_day_and_window_gate():
    hub = FakeHub()
    hub.chains[("SPY", "2026-07-31")] = _spy_chain()
    s = WputWeeklyPutWrite()
    assert s.scan(_ctx(THU, hub)) == []                            # Thursday: not roll day
    early = FRI.replace(hour=10, minute=0)
    assert s.scan(_ctx(early, hub)) == []                          # outside 15:55-16:00
    late = FRI.replace(hour=16, minute=0)
    assert s.scan(_ctx(late, hub)) == []


def test_holiday_friday_rolls_to_preceding_business_day(monkeypatch):
    """Row 6: exchange-holiday Friday -> preceding business day."""
    monkeypatch.setattr(wput_mod, "is_trading_day",
                        lambda d, **kw: d != date(2026, 7, 24))
    hub = FakeHub()
    hub.chains[("SPY", "2026-07-31")] = _spy_chain()
    s = WputWeeklyPutWrite()
    assert s.roll_day_of_week(date(2026, 7, 23)) == date(2026, 7, 23)
    got = [p.underlying for p in s.scan(_ctx(THU, hub))]
    assert got == ["SPY"]                                          # Thursday IS the roll day now


def test_already_holding_symbol_skipped():
    """One put per symbol per week: an open position expiring later this week blocks re-entry."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-07-31")] = _spy_chain()
    s = WputWeeklyPutWrite()

    class OpenPos:
        underlying = "SPY"
        nearest_expiry = date(2026, 7, 31)
    assert [p for p in s.scan(_ctx(FRI, hub, open_positions=[OpenPos()]))
            if p.underlying == "SPY"] == []
    # an EXPIRING-today position does NOT block the new weekly write (roll semantics)
    class ExpiringPos:
        underlying = "SPY"
        nearest_expiry = date(2026, 7, 24)
    assert len([p for p in s.scan(_ctx(FRI, hub, open_positions=[ExpiringPos()]))
                if p.underlying == "SPY"]) == 1


def test_earnings_week_tagged_never_skipped():
    """Row 21: single names write THROUGH earnings, tagged for split grading."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-07-31")] = _spy_chain()
    hub.refs["TSLA"] = 250.30
    hub.chains[("TSLA", "2026-07-31")] = [Row("T249", "put", 249.0, 5.0, 5.4),
                                          Row("T250", "put", 250.0, 5.6, 6.0)]
    s = WputWeeklyPutWrite()
    earnings = {"TSLA": {"date": "2026-07-28", "hour": "amc", "timing_reliable": True}}
    got = {p.underlying: p for p in s.scan(_ctx(FRI, hub, earnings=earnings))}
    assert "TSLA" in got                                           # never skipped
    assert got["TSLA"].risk_flags == ["holds_through_earnings"]
    assert got["SPY"].risk_flags == []                             # no earnings -> no tag


def test_manage_always_holds():
    """Rows 12-14: hold to expiry - manage() never exits."""
    s = WputWeeklyPutWrite()
    assert s.manage(object(), None) is None


def test_meta_doctrine_pins():
    m = WputWeeklyPutWrite.META
    assert m.settle_at_expiry is True                              # row 12
    assert m.grading_basis.value == "max_loss"                     # row 16 cash-secured
    assert m.event_policy.value == "trade_through"                 # row 11 unconditional
    assert m.max_concurrent == 18                                  # 9 symbols x roll-day overlap
    h = WputWeeklyPutWrite().config_hash()
    assert len(h) == 12
