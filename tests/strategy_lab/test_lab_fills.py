"""Combo fill math - the load-bearing identities (lab-strategy-runtime-v1).

Hand-computed expectations follow the main suite's convention: arithmetic in comments.
Identity under test everywhere:  net P&L  worst <= base <= optimistic  (per ledger),
which must hold for EVERY structure because it holds leg-wise on both sides.
"""

from __future__ import annotations

import random

from atlas.options.shadow import entry_fills, exit_fills
from atlas.strategy_lab.carisk import BASIS_CAR, BASIS_DEBIT, BASIS_MAX_LOSS, grading_block
from atlas.strategy_lab.model import (LEDGER_NAMES, build_combo_exit_record, combo_from_entry,
                                      combo_net_close, combo_net_open, leg_close_fills,
                                      leg_open_fills, payoff_analysis)

from .conftest import leg, make_entry, specs_and_mids


# --------------------------------------------------------------------- single-leg degeneracy
def test_single_long_leg_equals_shadow_entry_fills():
    """A 1-leg long combo must reproduce atlas.options.shadow exactly (degeneracy proof)."""
    l = leg("SPY260831C00640000", "call", 640, +1, bid=2.00, ask=2.20)
    assert l["fills"] == entry_fills(2.00, 2.20)
    net = combo_net_open([(s, l["fills"]) for (s, _), l in zip(specs_and_mids([l]), [l])])
    # entry_fills(2.0, 2.2): worst=2.2, mid=2.1, base=2.1+0.35*0.1=2.135
    assert net == {"worst": 2.2, "base": 2.135, "optimistic": 2.1}


def test_single_short_leg_uses_sell_side():
    l = leg("SPY260831P00600000", "put", 600, -1, bid=3.00, ask=3.20)
    assert l["fills"] == exit_fills(3.00, 3.20)
    net = combo_net_open([(s, l["fills"]) for (s, _), l in zip(specs_and_mids([l]), [l])])
    # short: credit received -> negative net. worst=-bid=-3.0, mid=3.1, base=-(3.1-0.35*0.1)=-3.065
    assert net == {"worst": -3.0, "base": -3.065, "optimistic": -3.1}


# --------------------------------------------------------------------- verticals
def test_debit_vertical_net_and_pnl_identity(combo_factory):
    legs = [leg("SPY260831C00630000", "call", 630, +1, bid=10.0, ask=10.4, delta=0.55),
            leg("SPY260831C00640000", "call", 640, -1, bid=5.0, ask=5.4, delta=-0.35)]
    rec, pos = combo_factory(legs, declared_basis="debit")
    # net worst = +10.4 (buy at ask) - 5.0 (sell at bid) = 5.4 debit
    # net opt   = +10.2 - 5.2 = 5.0
    assert rec["net_fills"]["worst"] == 5.4
    assert rec["net_fills"]["optimistic"] == 5.0
    assert rec["grading"]["basis"] == BASIS_DEBIT
    # denom = net debit worst * 100 = 540
    assert rec["grading"]["denom_usd"] == 540.0
    # max loss of a debit vertical = debit paid; max gain = width - debit = 1000-540
    assert rec["grading"]["max_loss_usd"] == 540.0
    assert rec["grading"]["max_gain_usd"] == 460.0

    x = build_combo_exit_record(
        ts=rec["ts_epoch"] + 3600, day=rec["day"], pos=pos, rule="test_close",
        legs_close=[{"occ": legs[0]["occ"], "bid": 12.0, "ask": 12.4},
                    {"occ": legs[1]["occ"], "bid": 6.0, "ask": 6.4}],
        S=634.0, state={}, hold_trading_days=1.0)
    nets = [x["ledgers"][n]["net_pnl_usd"] for n in LEDGER_NAMES]
    assert nets[0] <= nets[1] <= nets[2]
    # worst close: sell long at 12.0, buy short back at 6.4 -> net_close 5.6; pnl (5.6-5.4)*100=20
    assert x["ledgers"]["worst"]["net_pnl_usd"] == 20.0
    assert x["ledgers"]["worst"]["return_pct"] == round(20.0 / 540.0, 6)


def test_credit_vertical_basis_and_identity(combo_factory):
    legs = [leg("SPY260831P00610000", "put", 610, -1, bid=4.0, ask=4.4, delta=-0.30),
            leg("SPY260831P00600000", "put", 600, +1, bid=2.6, ask=3.0, delta=0.20)]
    rec, pos = combo_factory(legs, declared_basis="max_loss")
    # worst: sell 610P at bid 4.0, buy 600P at ask 3.0 -> net -1.0 (credit 1.00)
    assert rec["net_fills"]["worst"] == -1.0
    assert rec["grading"]["basis"] == BASIS_MAX_LOSS
    # max loss = width 10*100 - credit 100 = 900
    assert rec["grading"]["denom_usd"] == 900.0
    assert rec["grading"]["max_gain_usd"] == 100.0
    x = build_combo_exit_record(
        ts=rec["ts_epoch"] + 3600, day=rec["day"], pos=pos, rule="profit_50pct",
        legs_close=[{"occ": legs[0]["occ"], "bid": 1.8, "ask": 2.2},
                    {"occ": legs[1]["occ"], "bid": 1.3, "ask": 1.7}],
        S=628.0, state={}, hold_trading_days=5.0)
    nets = [x["ledgers"][n]["net_pnl_usd"] for n in LEDGER_NAMES]
    assert nets[0] <= nets[1] <= nets[2]
    # worst close: buy 610P back at ask 2.2, sell 600P at bid 1.3 -> net_close -0.9
    # pnl = (-0.9 - (-1.0)) * 100 = +10
    assert x["ledgers"]["worst"]["net_pnl_usd"] == 10.0


# --------------------------------------------------------------------- 4-leg + ratio
def test_iron_condor_grading_and_identity(combo_factory):
    legs = [leg("P1", "put", 600, -1, bid=4.0, ask=4.2), leg("P2", "put", 590, +1, bid=2.9, ask=3.1),
            leg("C1", "call", 660, -1, bid=3.5, ask=3.7), leg("C2", "call", 670, +1, bid=2.4, ask=2.6)]
    rec, pos = combo_factory(legs, declared_basis="max_loss")
    # worst credit: -4.0 +3.1 -3.5 +2.6 = -1.8
    assert rec["net_fills"]["worst"] == -1.8
    assert rec["grading"]["basis"] == BASIS_MAX_LOSS
    # both wings 10 wide: max loss = 10*100 - 180 = 820
    assert rec["grading"]["denom_usd"] == 820.0
    assert rec["grading"]["max_gain_usd"] == 180.0


def test_ratio_1x2_qty_math():
    legs = [leg("C1", "call", 640, -1, qty=1, bid=5.0, ask=5.2),
            leg("C2", "call", 660, +1, qty=2, bid=1.9, ask=2.1)]
    pairs = [(s, l["fills"]) for (s, _), l in zip(specs_and_mids(legs), legs)]
    net = combo_net_open(pairs)
    # worst: sell 1 at bid 5.0 -> -5.0; buy 2 at ask 2.1 -> +4.2; net -0.8 credit
    assert net["worst"] == -0.8
    pa = payoff_analysis([s for s, _ in specs_and_mids(legs)], net["worst"] * 100.0)
    # call backspread: slope beyond 660 = -1 + 2 = +1 -> unbounded gain, bounded loss.
    # loss max at 660: -(1*(-20) *100... pnl(660) = -1*20*100 - (-80) = -2000 + 80 = -1920
    assert pa["unbounded_up"] is False
    assert pa["max_gain_usd"] is None
    assert pa["max_loss_usd"] == 1920.0


def test_naked_short_call_is_car_basis(combo_factory):
    legs = [leg("C1", "call", 660, -1, bid=3.5, ask=3.7, delta=-0.16)]
    rec, pos = combo_factory(legs, declared_basis="car", S=630.0)
    g = rec["grading"]
    assert g["basis"] == BASIS_CAR and g["unbounded_up"] is True
    # reg_t: otm = 660-630 = 30; max(0.20*630 - 30, 0.10*630)=max(96,63)=96 -> 9600 + mid-premium 360
    assert g["denom_usd"] == 9960.0
    assert g["car_rule"] == "reg_t_v1"


def test_short_strangle_car_strangle_rule(combo_factory):
    legs = [leg("C1", "call", 660, -1, bid=3.5, ask=3.7),
            leg("P1", "put", 600, -1, bid=4.0, ask=4.2)]
    rec, _ = combo_factory(legs, declared_basis="car", S=630.0)
    g = rec["grading"]
    assert g["basis"] == BASIS_CAR
    # call req: max(126-30,63)=96*100+350=9950 ; put req: max(126-30,60)=96*100+410=10010
    # put side greater -> denom = put req + call-side premium (mid 3.6*100=360) = 10370
    assert g["car_inputs"]["put_req"] == 10010.0
    assert g["denom_usd"] == 10370.0


def test_calendar_covered_multi_expiry_is_debit_basis(combo_factory):
    """Same-strike long calendar: short front covered by long back -> DEBIT basis, denom =
    net debit (NOT the CaR proxy). Uncovered short back-month -> CaR."""
    from datetime import date as _d
    legs = [leg("FRONT", "call", 630, -1, bid=3.0, ask=3.2, expiry=_d(2026, 8, 7)),
            leg("BACK", "call", 630, +1, bid=6.0, ask=6.2, expiry=_d(2026, 9, 18))]
    rec, _ = combo_factory(legs, declared_basis="debit")
    g = rec["grading"]
    # net debit worst = 6.2 - 3.0 = 3.2 -> denom 320
    assert g["basis"] == BASIS_DEBIT and g["denom_usd"] == 320.0
    # reversed (short the LATER expiry, long the earlier) is NOT covered -> CaR
    legs_r = [leg("FRONT2", "call", 630, +1, bid=3.0, ask=3.2, expiry=_d(2026, 8, 7)),
              leg("BACK2", "call", 630, -1, bid=6.0, ask=6.2, expiry=_d(2026, 9, 18))]
    rec_r, _ = combo_factory(legs_r, declared_basis="car")
    assert rec_r["grading"]["basis"] == BASIS_CAR


def test_basis_mismatch_flagged(combo_factory):
    legs = [leg("C1", "call", 660, -1, bid=3.5, ask=3.7)]
    rec, _ = combo_factory(legs, declared_basis="debit")   # wrong on purpose
    assert rec["grading"]["basis_mismatch"] is True
    assert "basis_mismatch" in rec["risk_flags"]


# --------------------------------------------------------------------- property sweep
def test_pnl_identity_random_books(combo_factory):
    """200 random structures x random close books: worst <= base <= optimistic always."""
    rng = random.Random(20260719)
    for _ in range(200):
        n = rng.randint(1, 4)
        legs = []
        for i in range(n):
            bid = round(rng.uniform(0.1, 20.0), 2)
            ask = round(bid + rng.uniform(0.0, 1.5), 2)
            legs.append(leg(f"L{i}", rng.choice(["call", "put"]),
                            rng.choice([580, 600, 620, 640, 660]),
                            rng.choice([+1, -1]), qty=rng.randint(1, 2), bid=bid, ask=ask))
        rec, pos = combo_factory(legs, declared_basis="")
        close = []
        for l in legs:
            b = round(rng.uniform(0.05, 25.0), 2)
            close.append({"occ": l["occ"], "bid": b, "ask": round(b + rng.uniform(0.0, 1.5), 2)})
        x = build_combo_exit_record(ts=rec["ts_epoch"] + 60, day=rec["day"], pos=pos,
                                    rule="prop", legs_close=close, S=630.0, state={},
                                    hold_trading_days=0.5)
        nets = [x["ledgers"][nm]["net_pnl_usd"] for nm in LEDGER_NAMES]
        assert nets[0] <= nets[1] + 1e-9 <= nets[2] + 2e-9, (legs, close, nets)
        assert rec["grading"]["denom_usd"] >= 1.0


def test_close_fill_sides():
    # closing a long leg sells (worst=bid); closing a short leg buys (worst=ask)
    assert leg_close_fills(+1, 2.0, 2.2)["worst"] == 2.0
    assert leg_close_fills(-1, 2.0, 2.2)["worst"] == 2.2
    assert leg_open_fills(+1, 2.0, 2.2)["worst"] == 2.2
    assert leg_open_fills(-1, 2.0, 2.2)["worst"] == 2.0


def test_combo_net_close_ordering():
    legs = [leg("A", "call", 630, +1, bid=10.0, ask=10.4),
            leg("B", "call", 640, -1, bid=5.0, ask=5.4)]
    pairs = [(s, leg_close_fills(s.side, l["nbbo"]["bid"], l["nbbo"]["ask"]))
             for (s, _), l in zip(specs_and_mids(legs), legs)]
    net = combo_net_close(pairs)
    assert net["worst"] <= net["base"] <= net["optimistic"]


def test_rebuild_round_trip(combo_factory):
    legs = [leg("P1", "put", 610, -1, bid=4.0, ask=4.4), leg("P2", "put", 600, +1, bid=2.6, ask=3.0)]
    rec, pos = combo_factory(legs)
    pos2 = combo_from_entry(rec)
    assert pos2.position_id == pos.position_id
    assert pos2.net_open == rec["net_fills"]
    assert pos2.grading["denom_usd"] == rec["grading"]["denom_usd"]
    assert [ls.spec.occ for ls in pos2.legs] == ["P1", "P2"]
