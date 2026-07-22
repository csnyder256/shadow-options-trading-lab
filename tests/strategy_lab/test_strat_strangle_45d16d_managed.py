"""strangle_45d16d_managed vs its verified brief (docs/strategies/briefs/
strangle_45d16d_managed.md). Each test cites the brief row it pins. Fake hub, no network.
manage() positions are built via the REAL production builders (conftest combo_factory)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from atlas.strategy_lab.strategies.strangle_45d16d_managed import Strangle45D16DManaged
from atlas.strategy_lab.strategy import StrategyContext

from .conftest import leg

NY = ZoneInfo("America/New_York")
MON = datetime(2026, 7, 20, 10, 0, tzinfo=NY)        # Monday scan, 10:00 ET
S_REF = 600.0


@dataclass
class Row:
    symbol: str
    option_type: str
    strike: float
    bid: float
    ask: float


class FakeHub:
    """Duck-typed MarketHub: table-driven deltas so the 16-delta selection is pinned
    exactly (the doctrine under test is SELECTION, not the IV solver)."""

    def __init__(self, pctile=75.0):
        self.chains = {}
        self.refs = {"SPY": S_REF}
        self.exps = ["2026-08-21", "2026-09-02", "2026-09-18"]   # 32 / 44 / 60 DTE from MON
        self.regime = None if pctile is None else {"vix_pctile_252d": pctile}
        self.deltas = {}                     # (opt_type, strike) -> solved delta
        self.nbbo = {}                       # occ -> (bid, ask); absent -> no quote

    def vol_regime(self, max_age_days=5):
        return self.regime

    def ref_price(self, sym):
        return self.refs.get(sym, 0.0)

    def expirations(self, sym, **kw):
        return self.exps

    def chain(self, sym, exp, **kw):
        return self.chains.get((sym, exp), [])

    def last_nbbo(self, occ):
        q = self.nbbo.get(occ)
        return None if q is None else (q[0], q[1], 1.0)

    def row_greeks(self, *, opt_type, strike, S, mid, dte_days, r=0.04):
        d = self.deltas.get((opt_type, strike))
        if d is None:
            return None                      # unsolvable row -> skipped by selection
        return {"iv": 0.2, "delta": d, "gamma": 0.01, "vega": 0.4, "theta_day": -0.05}


def _ctx(dt, hub, open_positions=()):
    return StrategyContext(now_ts=dt.timestamp(), dt_et=dt, day=dt.date().isoformat(),
                           minute=dt.hour * 60 + dt.minute, session_close_min=975, hub=hub,
                           journal=None, open_positions=list(open_positions))


def _spy_chain(hub, exp="2026-09-02"):
    """SPY chain + delta table. Put nearest |0.16|: 555 (|-0.145|); 565 is EXACTLY 16-delta
    but one-sided -> excluded; 610 is ITM -> excluded. Call nearest: 645 (0.155); 650 has
    no solvable greeks -> skipped; 590 is ITM -> excluded. A signed-delta (non-absolute)
    put selection would pick 540 (|-0.10 - 0.16| = 0.26 is the smallest signed distance)."""
    hub.chains[("SPY", exp)] = [
        Row("P540", "put", 540.0, 0.85, 0.95), Row("P555", "put", 555.0, 1.20, 1.30),
        Row("P565", "put", 565.0, 0.0, 1.25), Row("P570", "put", 570.0, 1.70, 1.80),
        Row("P610", "put", 610.0, 11.0, 11.4),
        Row("C590", "call", 590.0, 14.0, 14.5), Row("C630", "call", 630.0, 1.55, 1.65),
        Row("C645", "call", 645.0, 1.05, 1.15), Row("C650", "call", 650.0, 0.95, 1.05),
        Row("C660", "call", 660.0, 0.70, 0.80)]
    hub.deltas.update({("put", 540.0): -0.10, ("put", 555.0): -0.145, ("put", 565.0): -0.16,
                       ("put", 570.0): -0.19, ("put", 610.0): -0.62,
                       ("call", 590.0): 0.68, ("call", 630.0): 0.21, ("call", 645.0): 0.155,
                       ("call", 660.0): 0.12})     # note: NO ("call", 650.0) entry


def test_scan_selects_nearest_16delta_both_sides():
    """Rows 4/5/6: nearest-|delta|-to-0.16 per side, ABSOLUTE delta for puts, OTM +
    two-sided NBBO only, both legs short 1 lot, same expiration (rows 18, §10 shape)."""
    hub = FakeHub()
    _spy_chain(hub)
    got = Strangle45D16DManaged().scan(_ctx(MON, hub))
    assert len(got) == 1
    p = got[0]
    assert p.kind == "short_strangle" and p.underlying == "SPY"
    put, call = p.legs
    assert (put["opt_type"], put["strike"], put["occ"]) == ("put", 555.0, "P555")
    assert (call["opt_type"], call["strike"], call["occ"]) == ("call", 645.0, "C645")
    assert put["side"] == -1 and call["side"] == -1
    assert put["qty"] == 1 and call["qty"] == 1
    assert put["expiry"] == call["expiry"] == "2026-09-02"      # nearest 45 in band (44 DTE)
    assert put["delta"] == -0.145                               # solved put delta stays signed
    assert p.signal["dte_days"] == 44
    assert p.signal["credit_mid"] == 2.35                       # 1.25 + 1.10
    assert p.signal["credit_bid"] == 2.25                       # 1.20 + 1.05
    assert p.signal["gate"]["basis"] == "vix_pctile_252d"
    assert p.risk_flags == []


def test_expiry_band_pins_dte_range():
    """Rows 2/3 + META dte_range (35, 50): a 51-DTE listing NEARER 45 is excluded by the
    band; the 35-DTE in-band listing wins. (Under the brief's published [35, 55] band the
    51-DTE expiry would have won - this pins the platform's narrowed top.)"""
    hub = FakeHub()
    hub.exps = ["2026-08-24", "2026-09-09"]                     # 35 / 51 DTE from MON
    _spy_chain(hub, exp="2026-08-24")
    got = Strangle45D16DManaged().scan(_ctx(MON, hub))
    assert len(got) == 1
    assert got[0].legs[0]["expiry"] == "2026-08-24"
    assert got[0].signal["dte_days"] == 35


def test_gate_blocks_low_vol_including_exact_50():
    """Rows 7/9: VIX-percentile fallback gate blocks pctile <= 50; comparator is STRICT >
    ('above 50%' - tastylive IVR page), so exactly 50.0 does NOT enter."""
    for pct in (30.0, 49.9, 50.0):
        hub = FakeHub(pctile=pct)
        _spy_chain(hub)
        assert Strangle45D16DManaged().scan(_ctx(MON, hub)) == [], f"pctile={pct}"


def test_gate_passes_high_vol_unflagged():
    """Rows 7/9: pctile just above the mapped threshold enters, no risk flags."""
    hub = FakeHub(pctile=50.1)
    _spy_chain(hub)
    got = Strangle45D16DManaged().scan(_ctx(MON, hub))
    assert len(got) == 1
    assert got[0].risk_flags == []
    assert got[0].signal["gate"]["vix_pctile_252d"] == 50.1


def test_gate_unavailable_enters_flagged():
    """Row 9 ladder last rung: regime file missing OR pctile null -> enter UNGATED with
    risk_flag gate_unavailable, gate basis logged for retroactive re-gating (§9)."""
    for regime in (None, {"vix_pctile_252d": None}):
        hub = FakeHub()
        hub.regime = regime
        _spy_chain(hub)
        got = Strangle45D16DManaged().scan(_ctx(MON, hub))
        assert len(got) == 1, f"regime={regime}"
        assert got[0].risk_flags == ["gate_unavailable"]
        assert got[0].signal["gate"]["basis"] == "unavailable"


def test_one_strangle_per_underlying():
    """Row 18 / §10: one open strangle per underlying blocks re-entry on that symbol only;
    flat symbols still fire (one proposal each)."""
    hub = FakeHub()
    _spy_chain(hub)
    hub.refs["QQQ"] = 500.0
    hub.chains[("QQQ", "2026-09-02")] = [Row("QP460", "put", 460.0, 1.00, 1.20),
                                         Row("QC540", "call", 540.0, 0.90, 1.10)]
    hub.deltas.update({("put", 460.0): -0.16, ("call", 540.0): 0.16})

    class OpenPos:
        underlying = "SPY"
    got = Strangle45D16DManaged().scan(_ctx(MON, hub, open_positions=[OpenPos()]))
    assert [p.underlying for p in got] == ["QQQ"]
    both = Strangle45D16DManaged().scan(_ctx(MON, hub))
    assert sorted(p.underlying for p in both) == ["QQQ", "SPY"]


# --------------------------------------------------------------------------- manage
def _strangle_pos(combo_factory):
    """Real-builder short strangle: entry mids 2.00 (put) + 1.50 (call) -> credit 3.50
    (= -net_open['optimistic']); expiry 2026-08-31 (conftest EXP)."""
    legs = [leg("P_OCC", "put", 560.0, -1, bid=1.75, ask=2.25, delta=-0.16),
            leg("C_OCC", "call", 640.0, -1, bid=1.25, ask=1.75, delta=0.16)]
    rec, pos = combo_factory(legs, strategy_id="strangle_45d16d_managed",
                             declared_basis="car", S=S_REF)
    assert pos.net_open["optimistic"] == -3.5
    return rec, pos


def _mhub(put_q, call_q):
    hub = FakeHub()
    hub.nbbo = {}
    if put_q is not None:
        hub.nbbo["P_OCC"] = put_q
    if call_q is not None:
        hub.nbbo["C_OCC"] = call_q
    return hub


def test_profit_50pct_boundary_exact(combo_factory):
    """Row 10: buy back at 50% of credit - cost EXACTLY half the credit fires; a tick
    above holds. dte = 42 here, so no time-rule contamination."""
    _, pos = _strangle_pos(combo_factory)
    s = Strangle45D16DManaged()
    act = s.manage(pos, _ctx(MON, _mhub((0.75, 1.25), (0.50, 1.00))))   # mids 1.00 + 0.75
    assert act is not None and act.action == "close" and act.rule == "profit_50pct"
    assert act.state["credit"] == 3.5 and act.state["cost"] == 1.75
    assert act.state["cost_x_credit"] == 0.5 and act.state["dte"] == 42
    assert act.state["loss_readings"] == {"house_netloss_ge_2x_credit": False,
                                          "alt_buyback_ge_2x_credit": False}
    hold = s.manage(pos, _ctx(MON, _mhub((0.75, 1.25), (0.55, 1.05))))  # cost 1.80 > 1.75
    assert hold is None


def test_dte_21_boundary(combo_factory):
    """Row 11: close at <= 21 DTE - 22 DTE holds, 21 DTE fires (expiry 2026-08-31)."""
    _, pos = _strangle_pos(combo_factory)
    s = Strangle45D16DManaged()
    hub = _mhub((0.75, 1.25), (0.75, 1.25))                    # cost 2.00: no other rule
    d22 = MON.replace(month=8, day=9)
    assert s.manage(pos, _ctx(d22, hub)) is None
    d21 = MON.replace(month=8, day=10)
    act = s.manage(pos, _ctx(d21, hub))
    assert act is not None and act.rule == "dte_21_management"
    assert act.state["dte"] == 21 and act.state["cost"] == 2.0


def test_dte_21_fires_even_without_quotes(combo_factory):
    """Row 11 is doctrine, not market data ('Never hold past 21 DTE' - brief §4): a missing
    leg quote holds the cost rules but never the calendar rule."""
    _, pos = _strangle_pos(combo_factory)
    s = Strangle45D16DManaged()
    hub = _mhub((0.75, 1.25), None)                            # call leg unquoted
    assert s.manage(pos, _ctx(MON, hub)) is None               # 42 DTE: hold, no exit
    act = s.manage(pos, _ctx(MON.replace(month=8, day=10), hub))
    assert act is not None and act.rule == "dte_21_management"
    assert act.state["cost"] is None


def test_loss_2x_credit_boundary_and_disambiguation(combo_factory):
    """Row 12 house convention: NET LOSS >= 2x credit == buy-back >= 3x credit (10.50 on a
    3.50 credit) fires; the SJ-literal alternative reading (buy-back >= 2x credit, 7.00)
    does NOT fire but is logged in state - the §10 telemetry on the published dispute."""
    _, pos = _strangle_pos(combo_factory)
    s = Strangle45D16DManaged()
    act = s.manage(pos, _ctx(MON, _mhub((5.75, 6.25), (4.25, 4.75))))   # mids 6.00 + 4.50
    assert act is not None and act.action == "close" and act.rule == "loss_2x_credit"
    assert act.state["cost"] == 10.5 and act.state["cost_x_credit"] == 3.0
    assert act.state["net_loss_x_credit"] == 2.0
    assert act.state["loss_readings"] == {"house_netloss_ge_2x_credit": True,
                                          "alt_buyback_ge_2x_credit": True}
    # buy-back at exactly 2x credit: the ALT reading alone must NOT close the position
    alt = s.manage(pos, _ctx(MON, _mhub((3.75, 4.25), (2.75, 3.25))))   # cost 7.00
    assert alt is None
    below = s.manage(pos, _ctx(MON, _mhub((5.75, 6.25), (4.00, 4.50)))) # cost 10.25
    assert below is None


def test_meta_doctrine_pins(combo_factory):
    """META verbatim + the CAR basis is what a naked strangle DERIVES (no mismatch)."""
    m = Strangle45D16DManaged.META
    assert m.strategy_id == "strangle_45d16d_managed" and m.version == 1
    assert m.universe == ("SPY", "QQQ", "IWM")                 # row 1 fidelity lane
    assert m.dte_range == (35, 50)                             # rows 2/3, top pinned 50
    assert m.max_concurrent == 3                               # one per underlying
    assert m.event_policy.value == "trade_through"             # §3: no published event gate
    assert m.grading_basis.value == "car"                      # row 20 undefined risk
    assert m.defining_mechanism == "short_vol_carry"
    assert m.settle_at_expiry is False                         # row 11: never rides expiry
    assert m.scan_interval_s == 300.0 and m.mark_interval_s == 300.0
    assert m.expected_fires_per_20_sessions == 3.0             # §10 ~3/month
    assert len(Strangle45D16DManaged().config_hash()) == 12
    rec, _ = _strangle_pos(combo_factory)
    assert rec["grading"]["basis"] == "car"                    # derived == declared
    assert rec["grading"]["basis_mismatch"] is False
