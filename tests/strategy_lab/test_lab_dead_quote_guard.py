"""A dead (0x0) leg quote is not a price (opts-fix-lab-dead-quote-v1).

The lab's managed-close rules are MID comparisons, so a leg quote that carries no price at all
(bid 0 / ask 0 - exactly what the vendor returns for a contract with no market, and what
hub.poll_quotes stores verbatim) used to read as a zero buyback cost. That satisfied
`cost_to_close <= 0.50 * entry_credit`, so `ic_45d16d_managed` fired its 50%-of-credit profit
target and booked the FULL entry credit as realized profit; the same zero bid satisfied
`bid <= intrinsic` in `atm_calendar_low_iv`'s short-parity assignment guard and fired a
fabricated urgent close. All-zero fills are internally consistent, so neither the ledger
identity gate nor the denominator gate could see it.

Three layers are pinned here:
  * the runner's mark/close book (`_leg_book`) now applies the SAME NBBO validity test the
    settlement path has always applied to a live leg, so a dead quote yields no book and the
    tick journals a partial mark and skips BOTH exit funnels - for every strategy, present and
    future;
  * `ic_45d16d_managed.manage` refuses a dead quote (the guard every sibling quote-reading
    manage() already carries);
  * `atm_calendar_low_iv`'s parity guard needs a LIVE bid.

No network, no runtime/ writes: fake hubs, everything under tmp_path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import scripts.run_strategy_lab as rsl
from atlas.strategy_lab.model import combo_from_entry, leg_open_fills
from atlas.strategy_lab.strategies import atm_calendar_low_iv as cal_mod
from atlas.strategy_lab.strategies.atm_calendar_low_iv import AtmCalendarLowIv
from atlas.strategy_lab.strategies.ic_45d16d_managed import Ic45d16dManaged
from atlas.strategy_lab.strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo,
                                         Strategy, StrategyContext, StrategyMeta)
from tests.strategy_lab.conftest import make_entry

NY = ZoneInfo("America/New_York")
MONDAY_10AM = datetime(2026, 7, 20, 10, 0, tzinfo=NY)

DEAD = (0.0, 0.0, 1.0)


def _read(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# --------------------------------------------------------------------------- runner-level
class FakeQuote:
    def __init__(self, bid, ask, last=0.0):
        self.bid, self.ask, self.last = bid, ask, last


class FakeGovernor:
    def used(self):
        return 0


class BookHub:
    """Duck-typed MarketHub whose whole leg book is settable per test."""

    def __init__(self, book):
        self.governor = FakeGovernor()
        self.book = dict(book)                       # {sym/occ: (bid, ask, age_s)}

    def poll_quotes(self, underlyings, leg_occs):
        return {s: FakeQuote(*self.book[s][:3]) for s in set(underlyings) | set(leg_occs)
                if s in self.book}

    def last_nbbo(self, sym):
        if sym not in self.book:
            return None
        b, a, age = self.book[sym][:3]
        return (b, a, age)

    def earnings_week(self):
        return {}

    def daily_history(self, u, days=10):
        return []


@dataclass(frozen=True)
class _P:
    dummy: float = 0.0


class CloseOnManage(Strategy):
    """Enters one 2-leg debit combo, then wants to close on the very next mark."""

    META = StrategyMeta(strategy_id="script_dead_quote", version=1, name="closes on manage",
                        universe=("SPY",), dte_range=(30, 60), max_concurrent=1,
                        event_policy=EventPolicy.TRADE_THROUGH,
                        grading_basis=GradingBasis.DEBIT,
                        defining_mechanism="directional_momentum",
                        scan_interval_s=0.0, mark_interval_s=0.0)
    params = _P()

    def scan(self, ctx):
        legs = [{"occ": "OCC_LONG", "underlying": "SPY", "opt_type": "call", "strike": 630,
                 "expiry": "2026-08-31", "side": +1, "qty": 1,
                 "nbbo": {"bid": 10.0, "ask": 10.4}, "iv": 0.2, "delta": 0.55,
                 "gamma": 0.01, "vega": 0.4, "theta_day": -0.05},
                {"occ": "OCC_SHORT", "underlying": "SPY", "opt_type": "call", "strike": 640,
                 "expiry": "2026-08-31", "side": -1, "qty": 1,
                 "nbbo": {"bid": 5.0, "ask": 5.4}, "iv": 0.19, "delta": -0.35,
                 "gamma": 0.01, "vega": 0.35, "theta_day": -0.04}]
        return [ProposedCombo(kind="bull_call_vertical", underlying="SPY", legs=legs,
                              signal={"trigger": "scripted"})]

    def manage(self, pos, ctx):
        return ExitAction(action="close", rule="scripted_close", state={})


LIVE_BOOK = {"SPY": (629.9, 630.1, 630.0), "OCC_LONG": (10.0, 10.4, 0.0),
             "OCC_SHORT": (5.0, 5.4, 0.0)}


def _core(tmp_path, monkeypatch, hub):
    strat = CloseOnManage()
    sid = strat.META.strategy_id
    monkeypatch.setattr(rsl, "build_all", lambda: {sid: strat})
    monkeypatch.setattr(rsl, "load_state", lambda: {sid: {"state": "armed", "cohort_pin": "",
                                                          "note": ""}})
    monkeypatch.setattr(rsl, "upcoming_events", lambda now: [])
    monkeypatch.setattr(rsl, "in_blackout", lambda now, events=None: None)
    core = rsl.StrategyLabCore(runtime_dir=tmp_path, log=lambda m: None, hub=hub,
                               now_fn=lambda: MONDAY_10AM)
    core.tick()                                      # tick 1 -> ENTER
    return core, sid


def test_dead_leg_quote_blocks_the_mark_and_both_exit_funnels(tmp_path, monkeypatch):
    """A dead (0x0) leg quote carries no price, so the mark/close tick must write NO mark and
    NO exit - the strategy's close demand is skipped exactly like the runner already skips a
    MISSING quote. Pre-fix this tick wrote rule=scripted_close priced off 0x0 fills."""
    core, sid = _core(tmp_path, monkeypatch, BookHub({**LIVE_BOOK, "OCC_LONG": DEAD}))
    s = core.ledger.strategy(sid)
    assert _read(s.entries_path)                         # the entry itself still happens
    core.tick()                                          # tick 2 -> mark + manage
    assert _read(s.marks_path) == []                     # no mark off a dead quote
    assert _read(s.exits_path) == []                     # and no exit
    assert any(r.get("event") == "combo_mark_partial" for r in _read(s.journal_path))
    assert len(core.positions[sid]) == 1                 # still on the books


def test_dead_short_leg_quote_also_blocks_the_mark(tmp_path, monkeypatch):
    """Mirror: the dead leg may be the SHORT side - still no book, still no exit."""
    core, sid = _core(tmp_path, monkeypatch, BookHub({**LIVE_BOOK, "OCC_SHORT": DEAD}))
    s = core.ledger.strategy(sid)
    core.tick()
    assert _read(s.marks_path) == [] and _read(s.exits_path) == []
    assert any(r.get("event") == "combo_mark_partial" for r in _read(s.journal_path))


def test_live_book_still_marks_and_closes(tmp_path, monkeypatch):
    """Positive control: a live two-sided book is untouched by the guard - the mark is written
    and the strategy's close still fires."""
    core, sid = _core(tmp_path, monkeypatch, BookHub(LIVE_BOOK))
    s = core.ledger.strategy(sid)
    core.tick()
    assert len(_read(s.marks_path)) == 1
    exits = _read(s.exits_path)
    assert len(exits) == 1 and exits[0]["rule"] == "scripted_close"
    assert exits[0]["legs_close"][0]["fills"]["worst"] > 0.0    # real prices, not zeros


@pytest.mark.parametrize("bad", [(0.0, 0.0, 0.0), (9.0, 8.0, 0.0),
                                 (8.0, float("nan"), 0.0), (8.0, 9.0, -1.0)])
def test_other_invalid_live_quotes_are_refused_too(tmp_path, monkeypatch, bad):
    """The shared predicate is the settlement path's: dead, crossed, non-finite and
    age-negative quotes all carry no price."""
    core, sid = _core(tmp_path, monkeypatch, BookHub({**LIVE_BOOK, "OCC_LONG": bad}))
    s = core.ledger.strategy(sid)
    core.tick()
    assert _read(s.marks_path) == [] and _read(s.exits_path) == []
    assert any(r.get("event") == "combo_mark_partial" for r in _read(s.journal_path))


def test_stale_but_live_quote_is_still_accepted(tmp_path, monkeypatch):
    """Guard is not over-broad: a STALE quote is live information (its age is stamped into the
    mark), only a quote that carries no price at all is refused."""
    core, sid = _core(tmp_path, monkeypatch,
                      BookHub({**LIVE_BOOK, "OCC_LONG": (10.0, 10.4, 3600.0)}))
    s = core.ledger.strategy(sid)
    core.tick()
    marks = _read(s.marks_path)
    assert len(marks) == 1
    assert {l["occ"]: l["age_s"] for l in marks[0]["legs"]}["OCC_LONG"] == 3600.0


@pytest.mark.parametrize("nbbo,ok", [((0.0, 0.0, 0.0), False), ((9.0, 8.0, 0.0), False),
                                     ((8.0, 9.0, -1.0), False), ((8.0, 9.0), False),
                                     (None, False), (5, False), (["a", "b", "c"], False),
                                     ((0.0, 1.0, 0.0), True),
                                     ((8.0, 8.4, 3600.0), True)])
def test_valid_nbbo_predicate(nbbo, ok):
    """The one predicate, pinned directly (it gates the settlement path and the mark/close
    book alike). Non-tuple junk is refused, never raised - the tick loop is unwrapped."""
    assert rsl._valid_nbbo(nbbo) is ok


# --------------------------------------------------------------------------- ic_45d16d_managed
IC_LEGS = [
    {"occ": "SPY260821P00600000", "underlying": "SPY", "opt_type": "put", "strike": 600.0,
     "expiry": "2026-08-21", "side": -1, "qty": 1, "nbbo": {"bid": 3.00, "ask": 3.20}},
    {"occ": "SPY260821P00575000", "underlying": "SPY", "opt_type": "put", "strike": 575.0,
     "expiry": "2026-08-21", "side": +1, "qty": 1, "nbbo": {"bid": 1.00, "ask": 1.20}},
    {"occ": "SPY260821C00660000", "underlying": "SPY", "opt_type": "call", "strike": 660.0,
     "expiry": "2026-08-21", "side": -1, "qty": 1, "nbbo": {"bid": 3.00, "ask": 3.20}},
    {"occ": "SPY260821C00685000", "underlying": "SPY", "opt_type": "call", "strike": 685.0,
     "expiry": "2026-08-21", "side": +1, "qty": 1, "nbbo": {"bid": 1.00, "ask": 1.20}},
]
IC_OCCS = [l["occ"] for l in IC_LEGS]


class QuoteMap:
    """Per-OCC quote book (leg mids drive the condor's buy-back cost)."""

    def __init__(self, quotes):
        self.quotes = quotes

    def last_nbbo(self, occ):
        return self.quotes.get(occ, DEAD)


def _ic_pos():
    legs = [{**l, "fills": leg_open_fills(l["side"], l["nbbo"]["bid"], l["nbbo"]["ask"])}
            for l in IC_LEGS]
    rec = make_entry(legs, strategy_id="ic_45d16d_managed", declared_basis="max_loss",
                     S=630.0, day="2026-07-20")
    pos = combo_from_entry(rec)
    assert pos is not None
    return rec, pos


def _ctx(hub, dt=datetime(2026, 7, 22, 11, 0, tzinfo=NY)):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=960, hub=hub,
                           earnings={}, journal=None, open_positions=[])


def test_ic_dead_quote_never_books_the_credit_as_profit():
    """THE bug. A dead 0x0 book computes cost_to_close == 0.00, which is <= 50% of the entry
    credit, so the profit target fired and the ledger booked the whole credit as a win at
    30 DTE. Now it holds. Discriminating: pre-fix this returned rule='profit_50pct'."""
    rec, pos = _ic_pos()
    assert -rec["net_fills"]["optimistic"] > 0            # it IS a credit condor
    act = Ic45d16dManaged().manage(pos, _ctx(QuoteMap({})))          # every leg dead
    assert act is None, (act and (act.rule, act.state))


def test_ic_live_book_at_target_still_closes_profit():
    """Positive control: a LIVE book whose mid cost is <= 50% of the credit still fires."""
    rec, pos = _ic_pos()
    credit = -rec["net_fills"]["optimistic"]
    cheap = {"SPY260821P00600000": (0.9, 1.1),       # short legs bought back cheap
             "SPY260821C00660000": (0.9, 1.1),
             "SPY260821P00575000": (0.4, 0.6),
             "SPY260821C00685000": (0.4, 0.6)}
    act = Ic45d16dManaged().manage(pos, _ctx(QuoteMap(cheap)))
    assert act is not None and act.rule == "profit_50pct"
    assert act.state["cost_to_close"] <= 0.5 * credit


def test_ic_live_book_off_target_falls_through_to_the_calendar_rule():
    """A live but RICH book (> 50% of credit) at <= 21 DTE closes on the calendar rule, not on
    a fake profit; the same rich live book well before 21 DTE holds."""
    rich = {"SPY260821P00600000": (2.9, 3.1),        # shorts expensive, longs cheap
            "SPY260821C00660000": (2.9, 3.1),
            "SPY260821P00575000": (0.4, 0.6),
            "SPY260821C00685000": (0.4, 0.6)}
    _, pos = _ic_pos()
    dt16 = datetime(2026, 8, 5, 11, 0, tzinfo=NY)                     # 16 DTE
    act = Ic45d16dManaged().manage(pos, _ctx(QuoteMap(rich), dt=dt16))
    assert act is not None and act.rule == "dte_21_management"
    assert Ic45d16dManaged().manage(pos, _ctx(QuoteMap(rich))) is None


# --------------------------------------------------------------------------- atm_calendar_low_iv
CAL_LEGS = [
    {"occ": "SPY260729C00630000", "underlying": "SPY", "opt_type": "call", "strike": 630.0,
     "expiry": "2026-07-29", "side": -1, "qty": 1, "nbbo": {"bid": 2.40, "ask": 2.60}},
    {"occ": "SPY260821C00630000", "underlying": "SPY", "opt_type": "call", "strike": 630.0,
     "expiry": "2026-08-21", "side": +1, "qty": 1, "nbbo": {"bid": 5.60, "ask": 5.80}},
]


class ItmQuoteMap(QuoteMap):
    def ref_price(self, sym):
        return 645.0                                     # short call ITM by 15


def _cal_pos():
    legs = [{**l, "fills": leg_open_fills(l["side"], l["nbbo"]["bid"], l["nbbo"]["ask"])}
            for l in CAL_LEGS]
    rec = make_entry(legs, strategy_id="atm_calendar_low_iv", declared_basis="debit",
                     S=630.0, day="2026-07-20")
    pos = combo_from_entry(rec)
    assert pos is not None
    return pos


def test_atm_calendar_zero_bid_is_not_parity(monkeypatch):
    """A dead (0x0) quote on an ITM short call satisfies `bid <= intrinsic` trivially, so the
    urgent assignment guard fired a fabricated close. A dead quote is the absence of a market,
    not evidence of parity: the guard must not fire. Discriminating: pre-fix this returned
    rule='short_parity_assignment_guard' with short_bid=0.0."""
    monkeypatch.setattr(cal_mod, "is_trading_day", lambda d, **kw: d.weekday() < 5)
    pos = _cal_pos()
    hub = ItmQuoteMap({"SPY260729C00630000": DEAD, "SPY260821C00630000": (5.6, 5.8)})
    dt = datetime(2026, 7, 21, 11, 0, tzinfo=NY)         # 6 trading days to front: T-5 silent
    act = AtmCalendarLowIv().manage(pos, _ctx(hub, dt=dt))
    assert act is None


def test_atm_calendar_live_parity_bid_still_guards(monkeypatch):
    """Positive control: a LIVE bid at/below intrinsic while ITM still fires the guard."""
    monkeypatch.setattr(cal_mod, "is_trading_day", lambda d, **kw: d.weekday() < 5)
    pos = _cal_pos()
    hub = ItmQuoteMap({"SPY260729C00630000": (14.8, 15.2), "SPY260821C00630000": (5.6, 5.8)})
    dt = datetime(2026, 7, 21, 11, 0, tzinfo=NY)
    act = AtmCalendarLowIv().manage(pos, _ctx(hub, dt=dt))
    assert act is not None and act.rule == "short_parity_assignment_guard"
    assert act.state["short_bid"] == 14.8
