"""overnight_1dte_strangle's entry window ends at the EQUITY close
(opts-fix-lab-overnight-entry-window-v1).

Brief row 7 records `entry_time = "last chain snapshot at/before 4:00 p.m. ET"` (the published
baseline is the 4:15 p.m. option-market close; the recorded default is the 4:00 p.m. snapshot)
and §9 asks for "~3:45-4:00 p.m. ET daily for entry". The module docstring and
`test_strat_overnight_1dte_strangle.test_entry_only_inside_closing_window` both pin the window
as the last 15 minutes before that bound - 15:45-16:00 ET, 12:45-13:00 on a half day.

The runner builds `ctx.session_close_min` from `options_close_minute(today, universe[0])` - the
OPTIONS close of the strategy's FIRST universe symbol, which for this ETF trio is the equity
close + 15 (975, not 960; 795, not 780 on the 2026-11-27 half day). `scan()` read the window off
that field, so in production the strategy entered at 16:00-16:15 ET: entirely PAST the brief's
hard 4:00 p.m. bound, in the post-close ETF book, while the 15:45-16:00 window its brief, its
docstring and its own unit test describe was unreachable.

These tests drive `scan()` with the ctx the runner actually builds (`session_close_min` from
`options_close_minute`) and FAIL on the pre-fix code: 15:50 produced no proposal and 16:05
produced one - the window exactly inverted. Fake hub, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from atlas.options.session_calendar import options_close_minute, session_close_minute
from atlas.strategy_lab.strategies.overnight_1dte_strangle import Overnight1dteStrangle
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")

# A normal Thursday (equity close 960, SPY options 975) and the 2026-11-27 half day
# (equity close 780, SPY options 795) - the only two shapes the calendar can hand this lane.
THU = datetime(2026, 7, 23, 15, 50, tzinfo=NY)
HALF_DAY = datetime(2026, 11, 27, 12, 50, tzinfo=NY)


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float


class FakeHub:
    """Minimal hub for one ETF name: a prescribed-delta 1-session-out chain (call 634 @ +0.27,
    put 627 @ -0.24 - the |Δ|-nearest-0.25 pair the brief's row 4 selects)."""

    def __init__(self, expiry: str):
        self.refs = {"SPY": 630.40}
        self.exps = [expiry]
        self.deltas = {("call", 634.0): 0.27, ("put", 627.0): -0.24}
        self.chains = {(("SPY"), expiry): [Row("C634", "call", 634.0, 1.22, 1.26),
                                           Row("P627", "put", 627.0, 1.23, 1.27)]}

    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)

    def expirations(self, sym, **kw):
        return self.exps

    def chain(self, sym, exp, **kw):
        return self.chains.get(("SPY", exp), [])

    def row_greeks(self, *, opt_type, strike, S, mid, dte_days, **kw):
        d = self.deltas.get((opt_type, strike))
        if d is None:
            return None
        return {"iv": 0.2, "delta": d, "gamma": 0.05, "vega": 0.1, "theta_day": -1.0}


def _runner_ctx(dt: datetime, expiry: str) -> StrategyContext:
    """The ctx the runner builds: `session_close_min` = the strategy's own universe[0] OPTIONS
    close, i.e. the +15 ETF bound - not the equity close the window is defined against."""
    strat = Overnight1dteStrangle()
    close_min = options_close_minute(dt.date(), strat.META.universe[0])
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=close_min,
                           hub=FakeHub(expiry), events=[], journal=None, open_positions=[])


def _at(dt: datetime, hh: int, mm: int, expiry: str):
    return Overnight1dteStrangle().scan(_runner_ctx(dt.replace(hour=hh, minute=mm), expiry))


def test_runner_ctx_is_the_options_close_not_the_equity_close():
    """The coupling that caused the defect: for the ETF trio the runner's `session_close_min`
    is equity close + 15 on both session shapes. Pinned so a runner change is visible here."""
    strat = Overnight1dteStrangle()
    assert strat.META.universe[0] == "SPY"
    assert session_close_minute(THU.date()) == 960
    assert options_close_minute(THU.date(), "SPY") == 975
    assert session_close_minute(HALF_DAY.date()) == 780
    assert options_close_minute(HALF_DAY.date(), "SPY") == 795


def test_entry_window_is_the_last_15_minutes_before_the_equity_close():
    """Rows 7/§9: with the runner's own ctx the window is 15:45-16:00 ET, NOT 16:00-16:15."""
    exp = "2026-07-24"                       # next session (row 6)
    assert len(_at(THU, 15, 50, exp)) == 1   # in the documented window (pre-fix: 0)
    assert len(_at(THU, 15, 45, exp)) == 1   # inclusive lower boundary
    assert _at(THU, 15, 44, exp) == []       # one minute early
    assert len(_at(THU, 15, 59, exp)) == 1   # last documented minute
    assert _at(THU, 16, 0, exp) == []        # row 7 hard bound: at/before 4:00 p.m. ET
    assert _at(THU, 16, 5, exp) == []        # post-close ETF book (pre-fix: 1)
    assert _at(THU, 10, 0, exp) == []        # mid-day never


def test_half_day_window_inherits_the_calendar_equity_close():
    """§9 + row 7 on a half day: the 13:00 equity close gives 12:45-13:00, not 13:00-13:15."""
    exp = "2026-11-30"                       # next session after the holiday weekend (row 6)
    assert len(_at(HALF_DAY, 12, 50, exp)) == 1   # in window (pre-fix: 0)
    assert len(_at(HALF_DAY, 12, 45, exp)) == 1   # inclusive lower boundary
    assert _at(HALF_DAY, 12, 44, exp) == []       # one minute early
    assert _at(HALF_DAY, 13, 0, exp) == []        # the half-day hard bound
    assert _at(HALF_DAY, 13, 5, exp) == []        # past the close (pre-fix: 1)


def test_entry_window_helper_reports_the_bounds_it_uses():
    """`_entry_window` is the single source of the bounds scan() applies - and it can never
    end later than the equity close, even if a caller supplies a larger session bound."""
    strat = Overnight1dteStrangle()
    ctx = _runner_ctx(THU, "2026-07-24")
    assert strat._entry_window(ctx) == (945, 960)
    ctx_half = _runner_ctx(HALF_DAY, "2026-11-30")
    assert strat._entry_window(ctx_half) == (765, 780)
    # a hypothetical larger bound (a future runner passing a longer options session) still
    # cannot push the window past the 4:00 p.m. published ceiling
    ctx_big = _runner_ctx(THU, "2026-07-24")
    ctx_big.session_close_min = 1000
    assert strat._entry_window(ctx_big) == (945, 960)
