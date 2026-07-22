"""overnight_1dte_strangle vs its verified brief (docs/strategies/briefs/overnight_1dte_strangle.md).
Each test cites the brief row it pins. Fake hub, no network. NOTE: the brief records NO
event-day stand-down - row 18 is trade-through-and-TAG (row 9: unconditional entry) - so the
event pin here asserts tag-not-skip."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from atlas.options.events import EconEvent
from atlas.strategy_lab.hub import MarketHub
from atlas.strategy_lab.strategies.overnight_1dte_strangle import Overnight1dteStrangle
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")
THU = datetime(2026, 7, 23, 15, 50, tzinfo=NY)      # Thursday 15:50 ET - inside [15:45, 16:00)
FRI = datetime(2026, 7, 24, 15, 50, tzinfo=NY)      # Friday entry → Monday expiry


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float


class FakeHub:
    """Prescribed-delta hub: row_greeks returns the delta pinned per (opt_type, strike) so
    selection-rule tests are exact and solver-free. chain_calls records requested expiries."""
    def __init__(self, deltas=None):
        self.chains = {}
        self.refs = {"SPY": 630.40}
        self.exps = ["2026-07-23", "2026-07-24", "2026-07-27", "2026-07-31"]
        self.deltas = deltas or {}
        self.chain_calls = []
    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)
    def expirations(self, sym, **kw):
        return self.exps
    def chain(self, sym, exp, **kw):
        self.chain_calls.append((sym, exp))
        return self.chains.get((sym, exp), [])
    def row_greeks(self, *, opt_type, strike, S, mid, dte_days, **kw):
        d = self.deltas.get((opt_type, strike))
        if d is None:
            return None
        return {"iv": 0.2, "delta": d, "gamma": 0.05, "vega": 0.1, "theta_day": -1.0}


class RealGreeksHub(FakeHub):
    """Same fixture surface but the REAL solver (mid → IV → delta), as the runner wires it."""
    row_greeks = staticmethod(MarketHub.row_greeks)


def _ctx(dt, hub, open_positions=(), events=(), session_close_min=960):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute,
                           session_close_min=session_close_min, hub=hub,
                           events=list(events), journal=None,
                           open_positions=list(open_positions))


def _std_hub():
    """SPY chain for 2026-07-24 whose prescribed deltas make call 634 (+0.27) and put 627
    (-0.24) the |Δ|-nearest-0.25 picks, with exact-0.25 ITM TRAP rows that only an OTM
    filter rejects (row 3)."""
    hub = FakeHub(deltas={
        ("call", 633.0): 0.31, ("call", 634.0): 0.27, ("call", 635.0): 0.22,
        ("call", 636.0): 0.16, ("call", 629.0): 0.25,          # ITM call trap (629 < S_ref)
        ("put", 626.0): -0.19, ("put", 627.0): -0.24, ("put", 628.0): -0.29,
        ("put", 629.0): -0.36, ("put", 632.0): -0.25})         # ITM put trap (632 > S_ref)
    hub.chains[("SPY", "2026-07-24")] = [
        Row("C629", "call", 629.0, 1.90, 1.98), Row("C633", "call", 633.0, 1.54, 1.58),
        Row("C634", "call", 634.0, 1.22, 1.26), Row("C635", "call", 635.0, 0.95, 0.99),
        Row("C636", "call", 636.0, 0.73, 0.77),
        Row("P626", "put", 626.0, 0.95, 0.99), Row("P627", "put", 627.0, 1.23, 1.27),
        Row("P628", "put", 628.0, 1.56, 1.60), Row("P629", "put", 629.0, 1.94, 1.98),
        Row("P632", "put", 632.0, 2.40, 2.48)]
    # today's 0DTE chain EXISTS and is populated - must never be chosen or even requested.
    hub.chains[("SPY", "2026-07-23")] = list(hub.chains[("SPY", "2026-07-24")])
    return hub


def test_entry_only_inside_closing_window():
    """Rows 7/9 + §9: entry only in the last 15 min before the session close, relative to
    ctx.session_close_min (half days inherit the window)."""
    hub = _std_hub()
    s = Overnight1dteStrangle()
    assert len(s.scan(_ctx(THU, hub))) == 1                              # 15:50 in-window
    assert s.scan(_ctx(THU.replace(hour=15, minute=44), hub)) == []      # 15:44 too early
    assert s.scan(_ctx(THU.replace(hour=15, minute=45), hub)) != []      # 15:45 boundary in
    assert s.scan(_ctx(THU.replace(hour=16, minute=0), hub)) == []       # 16:00 closed
    assert s.scan(_ctx(THU.replace(hour=10, minute=0), hub)) == []       # mid-day never
    # half day: close 13:00 → window [12:45, 13:00), and 15:50 is after the close
    assert s.scan(_ctx(THU.replace(hour=12, minute=50), hub,
                       session_close_min=780)) != []
    assert s.scan(_ctx(THU, hub, session_close_min=780)) == []


def test_sells_25delta_nearest_otm_strangle():
    """Rows 3/4: sell 1 OTM call + 1 OTM put at the strikes nearest |Δ|=0.25; the exact-0.25
    ITM trap rows must lose to the OTM filter."""
    hub = _std_hub()
    s = Overnight1dteStrangle()
    proposals = s.scan(_ctx(THU, hub))
    assert len(proposals) == 1
    p = proposals[0]
    assert p.kind == "short_strangle_overnight" and p.underlying == "SPY"
    assert len(p.legs) == 2 and all(l["side"] == -1 and l["qty"] == 1 for l in p.legs)
    call = next(l for l in p.legs if l["opt_type"] == "call")
    put = next(l for l in p.legs if l["opt_type"] == "put")
    assert call["strike"] == 634.0            # +0.27 nearest 0.25 (not ITM trap 629 @ +0.25)
    assert put["strike"] == 627.0             # -0.24 nearest 0.25 (not ITM trap 632 @ -0.25)
    assert p.signal["call_delta"] == 0.27 and p.signal["put_delta"] == -0.24
    assert p.signal["credit_bid"] == round(1.22 + 1.23, 4)      # both legs' bids
    assert p.signal["expiry"] == "2026-07-24"


def test_next_session_expiry_never_same_day():
    """Row 6: expiry = NEXT trading session - nearest listed expiration STRICTLY after today
    within dte_range; 0DTE excluded even though today's chain is listed and populated."""
    hub = _std_hub()
    s = Overnight1dteStrangle()
    p = s.scan(_ctx(THU, hub))[0]
    assert all(l["expiry"] == "2026-07-24" for l in p.legs)      # not today's 2026-07-23
    assert p.signal["dte_days"] == 1
    assert ("SPY", "2026-07-23") not in hub.chain_calls          # 0DTE chain never requested
    # Friday entry → Monday expiry (3 calendar days = 1 trading session, row 6)
    hub2 = _std_hub()
    hub2.chains[("SPY", "2026-07-27")] = hub2.chains.pop(("SPY", "2026-07-24"))
    p2 = s.scan(_ctx(FRI, hub2))[0]
    assert all(l["expiry"] == "2026-07-27" for l in p2.legs)
    assert p2.signal["dte_days"] == 3
    # no listing inside (0, 3] days → skip the night (holiday long weekend shape)
    hub3 = _std_hub()
    hub3.exps = ["2026-07-23", "2026-07-28"]                     # today + 5 days out
    assert s.scan(_ctx(THU, hub3)) == []


def test_delta_band_gate_skips_symbol():
    """Row 5: the SELECTED (nearest-0.25) strike must sit in 0.15 ≤ |Δ| ≤ 0.30 or the whole
    symbol is skipped that night - even when a farther in-band strike exists (select-then-
    gate, §10d coarse-ladder skips), and even when only one leg fails (both-or-nothing)."""
    s = Overnight1dteStrangle()
    # nearest put is -0.32 (dist 0.07, out of band); -0.17 (dist 0.08) in band but NOT nearest
    hub = FakeHub(deltas={("call", 634.0): 0.27,
                          ("put", 627.0): -0.32, ("put", 626.0): -0.17})
    hub.chains[("SPY", "2026-07-24")] = [
        Row("C634", "call", 634.0, 1.22, 1.26),
        Row("P627", "put", 627.0, 1.23, 1.27), Row("P626", "put", 626.0, 0.95, 0.99)]
    assert s.scan(_ctx(THU, hub)) == []
    # sanity: same chain with the put in band fires (call side alone was never the blocker)
    hub_ok = FakeHub(deltas={("call", 634.0): 0.27, ("put", 627.0): -0.28,
                             ("put", 626.0): -0.17})
    hub_ok.chains[("SPY", "2026-07-24")] = hub.chains[("SPY", "2026-07-24")]
    assert len(s.scan(_ctx(THU, hub_ok))) == 1


def test_one_per_underlying_and_two_sided_nbbo():
    """Row 20 (one strangle per symbol per night: open position blocks re-entry) + entry
    quality: one-sided rows are not a market - selection falls to the two-sided strike."""
    hub = _std_hub()
    s = Overnight1dteStrangle()

    class OpenPos:
        underlying = "SPY"
    assert s.scan(_ctx(THU, hub, open_positions=[OpenPos()])) == []
    # best-delta call (0.26) is one-sided → the 0.22 two-sided call is selected instead
    hub2 = FakeHub(deltas={("call", 634.0): 0.26, ("call", 635.0): 0.22,
                           ("put", 627.0): -0.24})
    hub2.chains[("SPY", "2026-07-24")] = [
        Row("C634", "call", 634.0, 0.0, 1.26),                   # no bid - not a market
        Row("C635", "call", 635.0, 0.95, 0.99),
        Row("P627", "put", 627.0, 1.23, 1.27)]
    p = s.scan(_ctx(THU, hub2))[0]
    call = next(l for l in p.legs if l["opt_type"] == "call")
    assert call["strike"] == 635.0


def test_macro_eve_trades_through_and_tags():
    """Rows 9/18: the brief records NO event stand-down - CPI/NFP-eve nights are ENTERED and
    TAGGED (8:30 a.m. release inside the close→open hold); FOMC 2 p.m. is outside the window
    and never tags."""
    s = Overnight1dteStrangle()
    cpi_eve = EconEvent("cpi", datetime(2026, 7, 24, 8, 30, tzinfo=NY))
    p = s.scan(_ctx(THU, _std_hub(), events=[cpi_eve]))[0]        # entered, NOT stood down
    assert p.risk_flags == ["macro_release_in_window"]
    assert p.signal["macro_events_in_window"] == ["cpi"]
    fomc = EconEvent("fomc", datetime(2026, 7, 24, 14, 0, tzinfo=NY), label="decision")
    p2 = s.scan(_ctx(THU, _std_hub(), events=[fomc]))[0]          # 14:00 > 09:30 exit open
    assert p2.risk_flags == [] and p2.signal["macro_events_in_window"] is None
    far = EconEvent("cpi", datetime(2026, 7, 29, 8, 30, tzinfo=NY))
    p3 = s.scan(_ctx(THU, _std_hub(), events=[far]))[0]           # beyond the held night
    assert p3.risk_flags == []


def test_next_open_buyback_morning_after_only():
    """§4 + rows 11/13/14/15: unconditional buy-back at the NEXT open - fires at/after 09:30
    ET the morning AFTER entry, never on the entry day, never pre-open, and with NO quote
    dependency (hub=None: missing quotes must not delay the mandatory buy-back)."""
    s = Overnight1dteStrangle()

    class Pos:
        underlying = "SPY"
        entry_day = "2026-07-23"
    pos = Pos()
    same_day = _ctx(THU.replace(hour=15, minute=55), hub=None)
    assert s.manage(pos, same_day) is None                        # entry evening: hold
    late_night = _ctx(THU.replace(hour=19, minute=59), hub=None)
    assert s.manage(pos, late_night) is None                      # rows 13/14: no other exits
    pre_open = _ctx(FRI.replace(hour=9, minute=15), hub=None)
    assert s.manage(pos, pre_open) is None                        # next day but pre-open
    at_open = s.manage(pos, _ctx(FRI.replace(hour=9, minute=30), hub=None))
    assert at_open is not None and at_open.action == "close"
    assert at_open.rule == "next_open_buyback"                    # row 11: 09:30 boundary
    after_open = s.manage(pos, _ctx(FRI.replace(hour=9, minute=31), hub=None))
    assert after_open is not None and after_open.rule == "next_open_buyback"
    assert after_open.state["entry_day"] == "2026-07-23"


def test_meta_doctrine_pins():
    m = Overnight1dteStrangle.META
    assert m.strategy_id == "overnight_1dte_strangle" and m.version == 1
    assert m.universe == ("SPY", "QQQ", "IWM")                    # row 2 core trio
    assert m.dte_range == (0, 3) and m.max_concurrent == 3
    assert m.event_policy.value == "trade_through"                # rows 9/18
    assert m.grading_basis.value == "car"                         # row 21 Reg-T proxy
    assert m.settle_at_expiry is False                            # §4 mandatory open buy-back
    assert m.defining_mechanism == "overnight_premium"
    assert m.expected_fires_per_20_sessions == 60.0               # §10: 3 symbols x 20 nights
    assert m.scan_interval_s == 60.0 and m.mark_interval_s == 60.0
    assert len(Overnight1dteStrangle().config_hash()) == 12


def test_real_solver_selects_25delta_strikes():
    """Rows 4/8 integration: with mid-quote chains priced at IV≈20% (1 DTE, S=630.40) the
    REAL solver path (mid → IV → Δ) picks call 635 (Δ≈+0.248) and put 626 (Δ≈−0.247)."""
    hub = RealGreeksHub()
    hub.chains[("SPY", "2026-07-24")] = [
        Row("C633", "call", 633.0, 1.54, 1.58), Row("C634", "call", 634.0, 1.22, 1.26),
        Row("C635", "call", 635.0, 0.95, 0.99), Row("C636", "call", 636.0, 0.73, 0.77),
        Row("P625", "put", 625.0, 0.73, 0.77), Row("P626", "put", 626.0, 0.95, 0.99),
        Row("P627", "put", 627.0, 1.23, 1.27), Row("P628", "put", 628.0, 1.56, 1.60)]
    s = Overnight1dteStrangle()
    p = s.scan(_ctx(THU, hub))[0]
    call = next(l for l in p.legs if l["opt_type"] == "call")
    put = next(l for l in p.legs if l["opt_type"] == "put")
    assert call["strike"] == 635.0 and put["strike"] == 626.0
    assert 0.15 <= call["delta"] <= 0.30                          # row 5 band, + sign
    assert -0.30 <= put["delta"] <= -0.15
    assert 0.19 < call["iv"] < 0.21                               # solver recovered the IV
