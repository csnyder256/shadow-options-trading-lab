"""short_put_45d30d_managed vs its verified brief
(docs/strategies/briefs/short_put_45d30d_managed.md). Each test cites the brief row it pins.
Fake hub, no network; manage() positions built via the REAL production builders (conftest
combo_factory). Chain quotes were generated at a flat 17% vol so the solved deltas are exact:
at 46 DTE / S=630.40 the 615 put solves to -0.3003 (winner), 613 -> -0.2818 and
617 -> -0.3193 (inside +/-3.5 delta but farther), 610/620 fall outside the tolerance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import atlas.strategy_lab.strategies.short_put_45d30d_managed as sp_mod
from atlas.strategy_lab.hub import MarketHub
from atlas.strategy_lab.model import leg_open_fills
from atlas.strategy_lab.strategies.short_put_45d30d_managed import ShortPut45D30DManaged
from atlas.strategy_lab.strategy import StrategyContext

NY = ZoneInfo("America/New_York")
AUG3 = datetime(2026, 8, 3, 10, 5, tzinfo=NY)    # first trading day of Aug 2026 (Monday)
AUG4 = datetime(2026, 8, 4, 10, 5, tzinfo=NY)
S_REF = 630.40
OCC = "SPY260918P00615000"


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
        self.refs = {"SPY": S_REF}
        # 08-21 monthly (18 DTE: below band) / 08-28 weekly / 09-17 THURSDAY non-standard at
        # exactly 45 DTE / 09-18 standard monthly at 46 DTE / 10-16 monthly (74 DTE: above band)
        self.exps = ["2026-08-21", "2026-08-28", "2026-09-17", "2026-09-18", "2026-10-16"]
        self.nbbo = {}
        self.regime = None
    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)
    def expirations(self, sym, **kw):
        return self.exps
    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])
    def last_nbbo(self, occ):
        return self.nbbo.get(occ)
    def vol_regime(self, **kw):
        return self.regime
    row_greeks = staticmethod(MarketHub.row_greeks)


def _ctx(dt, hub, open_positions=(), earnings=None, journal=None):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=960, hub=hub,
                           earnings=earnings or {}, journal=journal,
                           open_positions=list(open_positions))


def _chain(prefix="SPY"):
    """46-DTE quotes at flat 17% vol (see module docstring). 617/613 listed BEFORE 615 so a
    first-within-tolerance implementation would pick the wrong strike."""
    return [Row(f"{prefix}P590", "put", 590.0, 2.04, 2.24),     # delta -0.113: outside band
            Row(f"{prefix}P617", "put", 617.0, 8.05, 8.25),     # -0.3193: in band, dist .019
            Row(f"{prefix}P613", "put", 613.0, 6.77, 6.97),     # -0.2818: in band, dist .018
            Row(f"{prefix}P615", "put", 615.0, 7.39, 7.59),     # -0.3003: WINNER, dist .0003
            Row(f"{prefix}P620", "put", 620.0, 9.11, 9.31),     # -0.3485: outside band
            Row(f"{prefix}C615", "call", 615.0, 9.00, 9.20),    # call - excluded
            Row(f"{prefix}P625x", "put", 625.0, 0.0, 11.28),    # one-sided - excluded (row 20)
            Row(f"{prefix}P640", "put", 640.0, 14.00, 14.40)]   # strike >= S_ref - excluded


def _short_put_pos(combo_factory, *, bid=2.90, ask=3.10, expiry="2026-09-18"):
    """Real ComboPosition via production builders: sell-open optimistic fill = mid = 3.00,
    so net_open['optimistic'] = -3.00 and the entry mid credit is exactly 3.00."""
    leg = {"occ": OCC, "underlying": "SPY", "opt_type": "put", "strike": 615.0,
           "expiry": expiry, "side": -1, "qty": 1, "nbbo": {"bid": bid, "ask": ask},
           "fills": leg_open_fills(-1, bid, ask),
           "iv": 0.17, "delta": -0.30, "gamma": 0.009, "vega": 0.78, "theta_day": -0.12}
    _, pos = combo_factory([leg], strategy_id="short_put_45d30d_managed",
                           declared_basis="max_loss", S=S_REF, kind="short_put_45d")
    return pos


# --------------------------------------------------------------------- entry doctrine
def test_first_trading_day_entry_monthly_45dte_30delta():
    """Rows 3/4/5/7/8/12/18: first-trading-day entry sells the ~30-delta put on the standard
    MONTHLY closest to 45 DTE - the 46-DTE monthly beats the exactly-45-DTE Thursday weekly."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-09-18")] = _chain()
    hub.regime = {"vix_close": 17.2, "vix_pctile_252d": 0.41}
    s = ShortPut45D30DManaged()
    props = [p for p in s.scan(_ctx(AUG3, hub)) if p.underlying == "SPY"]
    assert len(props) == 1
    p = props[0]
    assert p.kind == "short_put_45d" and p.contracts == 1          # row 18: 1 contract
    leg = p.legs[0]
    assert leg["side"] == -1 and leg["opt_type"] == "put" and leg["qty"] == 1   # row 6
    assert leg["expiry"] == "2026-09-18"          # row 5: monthly only (not 09-17 weekly)
    assert leg["strike"] == 615.0                 # rows 7/8: closest to 30 delta, not first fit
    assert -0.335 <= leg["delta"] <= -0.265       # row 8: inside +/-3.5 delta
    assert p.signal["dte_days"] == 46
    assert p.signal["planned_exit_21dte"] == "2026-08-28"          # row 15 bookkeeping
    assert p.signal["vix_pctile_252d"] == 0.41    # row 12: logged, never gated
    assert p.risk_flags == []                     # ETF tier - no extension tag


def test_entry_cadence_first_trading_day_only():
    """Row 9: 'On the first trading day of every month' - no other day fires."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-09-18")] = _chain()
    s = ShortPut45D30DManaged()
    assert s.scan(_ctx(AUG4, hub)) == []                           # second trading day
    mid_month = datetime(2026, 8, 17, 10, 5, tzinfo=NY)
    assert s.scan(_ctx(mid_month, hub)) == []


def test_holiday_first_of_month_shifts_cadence(monkeypatch):
    """Row 9: first TRADING day, not first calendar day - an Aug 3 holiday moves entry to Aug 4."""
    monkeypatch.setattr(sp_mod, "is_trading_day",
                        lambda d, **kw: d.weekday() < 5 and d != date(2026, 8, 3))
    hub = FakeHub()
    hub.chains[("SPY", "2026-09-18")] = _chain()
    s = ShortPut45D30DManaged()
    assert s.scan(_ctx(AUG3, hub)) == []                           # holiday itself never fires
    props = [p for p in s.scan(_ctx(AUG4, hub)) if p.underlying == "SPY"]
    assert len(props) == 1
    assert props[0].legs[0]["strike"] == 615.0                     # 45 DTE now; winner unchanged


def test_standard_monthly_expiry_math(monkeypatch):
    """Row 5: standard monthly = third Friday; exchange-holiday Friday steps back one day."""
    s = ShortPut45D30DManaged()
    assert s.standard_monthly_expiry(2026, 8) == date(2026, 8, 21)
    assert s.standard_monthly_expiry(2026, 9) == date(2026, 9, 18)
    assert s.standard_monthly_expiry(2026, 10) == date(2026, 10, 16)
    monkeypatch.setattr(sp_mod, "is_trading_day",
                        lambda d, **kw: d.weekday() < 5 and d != date(2026, 9, 18))
    assert s.standard_monthly_expiry(2026, 9) == date(2026, 9, 17)


def test_one_position_per_symbol():
    """Row 9 cadence implies one open put per underlying - an open SPY combo blocks SPY."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-09-18")] = _chain()
    s = ShortPut45D30DManaged()

    class OpenPos:
        underlying = "SPY"
        nearest_expiry = date(2026, 9, 18)
    assert [p for p in s.scan(_ctx(AUG3, hub, open_positions=[OpenPos()]))
            if p.underlying == "SPY"] == []


def test_no_delta_fit_or_degraded_chain_means_no_entry():
    """Row 8: nothing inside +/-3.5 delta = no entry; degraded hub (empty chain) = no entry."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-09-18")] = [Row("SPYP590", "put", 590.0, 2.04, 2.24),   # -0.113
                                         Row("SPYP575", "put", 575.0, 0.73, 0.93)]   # -0.051
    s = ShortPut45D30DManaged()
    assert s.scan(_ctx(AUG3, hub)) == []
    hub.chains.clear()                                             # hub degraded -> chain []
    assert s.scan(_ctx(AUG3, hub)) == []


def test_dte_band_excludes_out_of_range_monthlies():
    """Rows 3/4: only monthlies OUTSIDE the 30-60 DTE band listed (18 and 74 DTE) -> no
    entry, even though both chains carry fittable ~30-delta strikes."""
    hub = FakeHub()
    hub.exps = ["2026-08-21", "2026-10-16", "not-a-date"]          # parse guard exercised too
    hub.chains[("SPY", "2026-08-21")] = _chain()
    hub.chains[("SPY", "2026-10-16")] = _chain()
    s = ShortPut45D30DManaged()
    assert s.scan(_ctx(AUG3, hub)) == []


def test_earnings_gate_skips_only_inside_hold_window():
    """Row 19 (PLATFORM-POLICY): skip the month when earnings falls in [entry, planned 21-DTE
    exit]; earnings AFTER the planned exit (even before expiry) does NOT gate. §2: single
    names carry the single_name_tier lane tag."""
    hub = FakeHub()
    hub.chains[("SPY", "2026-09-18")] = _chain()
    hub.refs["TSLA"] = S_REF
    hub.chains[("TSLA", "2026-09-18")] = _chain("TSLA")
    s = ShortPut45D30DManaged()
    events = []

    # earnings inside [2026-08-03, 2026-08-28] -> TSLA skipped, journaled; SPY unaffected
    got = {p.underlying for p in s.scan(_ctx(AUG3, hub,
           earnings={"TSLA": {"date": "2026-08-05", "hour": "amc"}}, journal=events.append))}
    assert got == {"SPY"}
    assert any(e["event"] == "sp45_earnings_gate_skip" and e["symbol"] == "TSLA"
               for e in events)
    # boundary: earnings ON the planned exit day still gates (inclusive containment)
    got = {p.underlying for p in s.scan(_ctx(AUG3, hub,
           earnings={"TSLA": {"date": "2026-08-28", "hour": "bmo"}}))}
    assert got == {"SPY"}
    # earnings after the 21-DTE exit but before expiry -> exposure already closed: ENTER
    props = {p.underlying: p for p in s.scan(_ctx(AUG3, hub,
             earnings={"TSLA": {"date": "2026-09-10", "hour": "amc"}}))}
    assert set(props) == {"SPY", "TSLA"}
    assert props["TSLA"].risk_flags == ["single_name_tier"]        # §2 lane split
    # stale past earnings date (already reported) never gates
    got = {p.underlying for p in s.scan(_ctx(AUG3, hub,
           earnings={"TSLA": {"date": "2026-07-30", "hour": "amc"}}))}
    assert got == {"SPY", "TSLA"}


# --------------------------------------------------------------------- exit doctrine
def test_profit_50pct_fires_at_threshold_not_before(combo_factory):
    """Row 14: buy back when current mid <= 0.5 x entry credit (3.00 -> threshold 1.50) - 
    fires AT the threshold, not a cent above it."""
    s = ShortPut45D30DManaged()
    pos = _short_put_pos(combo_factory)
    hub = FakeHub()
    dt = datetime(2026, 8, 10, 11, 0, tzinfo=NY)                   # 39 DTE: time exit far away
    hub.nbbo[OCC] = (1.45, 1.60, 3.0)                              # mid 1.525 > 1.50 -> HOLD
    assert s.manage(pos, _ctx(dt, hub)) is None
    hub.nbbo[OCC] = (1.40, 1.60, 3.0)                              # mid 1.50 == threshold
    act = s.manage(pos, _ctx(dt, hub))
    assert act is not None and act.action == "close" and act.rule == "profit_50pct"
    assert act.state["credit_open_mid"] == 3.0
    assert act.state["threshold_mid"] == 1.5
    assert act.state["cost_now_mid"] == 1.5
    assert act.state["capture_frac"] == 0.5


def test_dte21_time_exit_and_no_stop_loss(combo_factory):
    """Rows 15/16: close at DTE <= 21; between the rails there is NO stop - a 3x-credit loss
    at 22 DTE is a HOLD."""
    s = ShortPut45D30DManaged()
    pos = _short_put_pos(combo_factory)                            # expiry 2026-09-18
    hub = FakeHub()
    hub.nbbo[OCC] = (2.00, 2.20, 3.0)                              # mid 2.10: above threshold
    d22 = datetime(2026, 8, 27, 11, 0, tzinfo=NY)                  # 22 DTE
    assert s.manage(pos, _ctx(d22, hub)) is None
    hub.nbbo[OCC] = (8.90, 9.10, 3.0)                              # mid 9.00 = 3x credit loss
    assert s.manage(pos, _ctx(d22, hub)) is None                   # row 16: never cut early
    d21 = datetime(2026, 8, 28, 11, 0, tzinfo=NY)                  # exactly 21 DTE
    act = s.manage(pos, _ctx(d21, hub))
    assert act is not None and act.action == "close" and act.rule == "dte_21_management"
    assert act.state["dte"] == 21 and act.state["time_exit_dte"] == 21
    d17 = datetime(2026, 9, 1, 11, 0, tzinfo=NY)                   # already inside 21 DTE
    act = s.manage(pos, _ctx(d17, hub))
    assert act is not None and act.rule == "dte_21_management"


def test_hold_when_quotes_missing_never_guess(combo_factory):
    """Missing or offer-less NBBO = HOLD (even inside 21 DTE); a dead put with a live offer
    (bid 0) is still repurchasable -> 50% rule may fire on the offer-derived mid."""
    s = ShortPut45D30DManaged()
    pos = _short_put_pos(combo_factory)
    hub = FakeHub()                                                # no NBBO stored at all
    d10 = datetime(2026, 9, 8, 11, 0, tzinfo=NY)                   # 10 DTE
    assert s.manage(pos, _ctx(d10, hub)) is None
    hub.nbbo[OCC] = (0.0, 0.0, 3.0)                                # no live offer
    assert s.manage(pos, _ctx(d10, hub)) is None
    hub.nbbo[OCC] = (0.0, 0.02, 3.0)                               # dead put, offer alive
    d39 = datetime(2026, 8, 10, 11, 0, tzinfo=NY)
    act = s.manage(pos, _ctx(d39, hub))
    assert act is not None and act.rule == "profit_50pct"          # cost 0.01 <= 1.50


# --------------------------------------------------------------------- META / params pins
def test_meta_and_params_doctrine_pins():
    m = ShortPut45D30DManaged.META
    assert m.strategy_id == "short_put_45d30d_managed" and m.version == 1
    assert m.settle_at_expiry is False                             # MANAGED (rows 14/15)
    assert m.grading_basis.value == "max_loss"                     # naked put bounded loss
    assert m.event_policy.value == "trade_through"                 # row 11: unconditional
    assert m.max_concurrent == 9 and len(m.universe) == 9          # row 2: one per underlying
    assert m.dte_range == (35, 50)
    assert m.expected_fires_per_20_sessions == 9.0                 # §10: ~9/monthly cycle
    prm = ShortPut45D30DManaged.params
    assert prm.dte_target == 45                                    # row 3
    assert (prm.dte_band_min, prm.dte_band_max) == (30, 60)        # row 4
    assert prm.delta_target == 0.30 and prm.delta_tolerance == 0.035   # rows 7/8
    assert prm.profit_target_frac == 0.50                          # row 14
    assert prm.time_exit_dte == 21                                 # row 15
    assert len(ShortPut45D30DManaged().config_hash()) == 12
