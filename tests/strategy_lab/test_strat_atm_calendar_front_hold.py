"""atm_calendar_low_iv must not enter a calendar its OWN T-5 exit closes immediately.

opts-fix-lab-calendar-front-hold-v1. `_expiry_in_window` used to pick the earliest listed
expiry with dte in [7, 10]. A 7-calendar-day front expiry is EXACTLY 5 trading days away for
every weekday (same weekday, five weekdays between), and `manage()` closes at
`_trading_days_until(today, front_expiry) <= front_exit_trading_days` (5) - so the picked
front leg triggered the strategy's own `front_expiry_week_exit` at the first mark after entry:
entered and exited minutes apart, paying the spread twice, booking a guaranteed loss with no
hold and no theta, and writing a fabricated entry/exit pair into the graded evidence.

These tests fail on the pre-fix code (front pick = the 7-DTE listing, entry fired) and pass
after it. Fake hub, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from atlas.strategy_lab.hub import MarketHub
from atlas.strategy_lab.model import ComboPosition, LegSpec, LegState
from atlas.strategy_lab.strategies.atm_calendar_low_iv import AtmCalendarLowIv
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")
MON = datetime(2026, 7, 20, 10, 30, tzinfo=NY)     # a real Monday; +7d = Mon 2026-07-27
LOW_REGIME = {"asof": "2026-07-17", "vix_close": 13.9, "vix_pctile_252d": 22.0}
SEVEN_DTE = "2026-07-27"      # exactly 5 TRADING days out -> inside the T-5 exit window
EIGHT_DTE = "2026-07-28"      # 6 trading days out -> holdable
BACK = "2026-08-21"           # 32 DTE back leg


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float


class FakeHub:
    def __init__(self, exps):
        self.exps = exps
        self.chains = {}
        self.regime = dict(LOW_REGIME)

    def vol_regime(self, max_age_days=5):
        return self.regime

    def ref_price(self, sym):
        return 630.40 if sym == "SPY" else 0.0

    def expirations(self, sym, **kw):
        return list(self.exps)

    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])

    def last_nbbo(self, occ):
        return None

    row_greeks = staticmethod(MarketHub.row_greeks)


def _ctx(hub, journal=None):
    return StrategyContext(now_ts=MON.timestamp(), dt_et=MON, day=MON.date().isoformat(),
                           minute=MON.hour * 60 + MON.minute, session_close_min=975, hub=hub,
                           journal=journal, open_positions=[])


def _ladder(hub, exp, atm_bid=5.50, atm_ask=5.70):
    """Two-sided call ladder; the ATM strike 630 is common to every expiry (the back leg is
    priced richer, as a real longer-dated option is)."""
    tag = exp.replace("-", "")[2:]
    hub.chains[("SPY", exp)] = [
        Row(f"SPY{tag}C628", "call", 628.0, atm_bid + 1.10, atm_ask + 1.10),
        Row(f"SPY{tag}C630", "call", 630.0, atm_bid, atm_ask),
        Row(f"SPY{tag}C632", "call", 632.0, atm_bid - 1.00, atm_ask - 1.00)]


def _load(hub):
    _ladder(hub, EIGHT_DTE)
    _ladder(hub, BACK, 11.60, 11.90)


def _spy(hub):
    return [p for p in AtmCalendarLowIv().scan(_ctx(hub)) if p.underlying == "SPY"]


def _hold_days(s, expiry: str) -> int:
    return s._trading_days_until(MON.date(), date.fromisoformat(expiry))


# --------------------------------------------------------------------- the fix
def test_front_pick_skips_a_listing_inside_the_exit_window():
    """A 7-DTE front listing is exactly 5 trading days out (the T-5 exit fires on entry), so
    the pick must fall through to the next listed expiry that leaves room to hold."""
    s = AtmCalendarLowIv()
    hub = FakeHub([SEVEN_DTE, EIGHT_DTE, BACK])
    _load(hub)
    assert _hold_days(s, SEVEN_DTE) == s.params.front_exit_trading_days    # 5 == 5: collides
    (p,) = _spy(hub)
    front, back = p.legs
    assert front["expiry"] == EIGHT_DTE                # pre-fix: SEVEN_DTE
    assert back["expiry"] == BACK
    assert front["strike"] == back["strike"] == 630.0
    # THE INVARIANT: the entry must leave at least one session beyond the T-5 exit window,
    # so manage() cannot close the calendar on the session that opened it.
    assert _hold_days(s, front["expiry"]) > s.params.front_exit_trading_days
    assert p.signal["front_dte"] == 8


def test_no_entry_when_the_whole_front_window_sits_inside_the_exit_window():
    """When the only listing in [7, 10] DTE is already inside the T-5 window, there is no
    holdable calendar - skip and journal the real reason, never fire a self-closing entry."""
    hub = FakeHub([SEVEN_DTE, BACK])
    _ladder(hub, BACK, 11.60, 11.90)
    events = []
    s = AtmCalendarLowIv()
    assert s.scan(_ctx(hub, journal=events.append)) == []
    assert [e["event"] for e in events] == ["cal_front_inside_exit_window"]
    ev = events[0]
    assert ev["front_in_window"] == SEVEN_DTE and ev["front_dte"] == 7
    assert ev["front_exit_trading_days"] == 5


def test_manage_does_not_close_the_picked_calendar_on_entry():
    """The end-to-end claim, stated directly: for the front leg the scan actually picks,
    manage() at entry time must HOLD (pre-fix the picked front leg fired the exit)."""
    s = AtmCalendarLowIv()
    hub = FakeHub([SEVEN_DTE, EIGHT_DTE, BACK])
    _load(hub)
    (p,) = _spy(hub)

    def leg_state(l, side):
        return LegState(spec=LegSpec(occ=l["occ"], underlying="SPY", opt_type="call",
                                     strike=l["strike"], expiry=date.fromisoformat(l["expiry"]),
                                     side=side),
                        entry_bid=l["nbbo"]["bid"], entry_ask=l["nbbo"]["ask"],
                        open_fills={"worst": l["nbbo"]["bid"], "base": l["nbbo"]["ask"],
                                    "optimistic": l["nbbo"]["ask"]})

    pos = ComboPosition(position_id="x", strategy_id="atm_calendar_low_iv",
                        strategy_config_hash="h", kind="atm_call_calendar", underlying="SPY",
                        legs=[leg_state(p.legs[0], -1), leg_state(p.legs[1], +1)],
                        net_open={"worst": 0.0, "base": 0.0, "optimistic": 0.0},
                        grading={"basis": "debit", "denom_usd": 1.0},
                        entry_ts=MON.timestamp(), entry_minute=MON.hour * 60 + MON.minute,
                        entry_day=MON.date().isoformat(), entry_S=630.40)
    # no quotes -> the parity guard cannot fire, so the ONLY exit rule in reach is the T-5 one
    assert s.manage(pos, _ctx(FakeHub([]))) is None
