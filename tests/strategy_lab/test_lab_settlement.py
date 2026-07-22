"""Expiry settlement + early assignment (lab-strategy-runtime-v1). All three ledgers must be
EQUAL at settlement (intrinsic has no spread)."""

from __future__ import annotations

from datetime import date

from atlas.strategy_lab.model import LEDGER_NAMES, build_combo_exit_record
from atlas.strategy_lab.settlement import (early_assignment_risk, expired_legs, pin_risk_flags,
                                           settlement_fills)

from .conftest import EXP, leg


def test_settlement_itm_otm_three_ledger_equality(combo_factory):
    legs = [leg("P1", "put", 610, -1, bid=4.0, ask=4.4), leg("P2", "put", 600, +1, bid=2.6, ask=3.0)]
    rec, pos = combo_factory(legs, declared_basis="max_loss")
    # settle at S=605: short 610P ITM by 5 -> costs 5.00; long 600P OTM -> 0
    fills = settlement_fills(pos, 605.0)
    assert fills == {"P1": 5.0, "P2": 0.0}
    x = build_combo_exit_record(ts=rec["ts_epoch"] + 86_400, day="2026-08-31", pos=pos,
                                rule="expiry_settlement",
                                legs_close=[{"occ": "P1", "bid": 0, "ask": 0},
                                            {"occ": "P2", "bid": 0, "ask": 0}],
                                S=605.0, state={}, hold_trading_days=30.0,
                                fills_override=fills)
    nets = [x["ledgers"][n]["net_pnl_usd"] for n in LEDGER_NAMES]
    # entry worst credit -1.0 -> settle net_close = -5.0 + 0 = -5.0; pnl worst = (-5.0-(-1.0))*100 = -400
    assert x["ledgers"]["worst"]["net_pnl_usd"] == -400.0
    # ledgers differ ONLY by entry fills at settlement; identity still ordered
    assert nets[0] <= nets[1] <= nets[2]
    assert x["ledgers"]["worst"]["exit_net"] == x["ledgers"]["optimistic"]["exit_net"] == -5.0


def test_settlement_ratio_qty_math(combo_factory):
    legs = [leg("C1", "call", 640, -1, qty=1, bid=5.0, ask=5.2),
            leg("C2", "call", 660, +1, qty=2, bid=1.9, ask=2.1)]
    rec, pos = combo_factory(legs)
    fills = settlement_fills(pos, 670.0)
    # 640C intrinsic 30, 660C intrinsic 10
    assert fills == {"C1": 30.0, "C2": 10.0}
    x = build_combo_exit_record(ts=rec["ts_epoch"] + 60, day="2026-08-31", pos=pos,
                                rule="expiry_settlement",
                                legs_close=[{"occ": "C1", "bid": 0, "ask": 0},
                                            {"occ": "C2", "bid": 0, "ask": 0}],
                                S=670.0, state={}, hold_trading_days=30.0, fills_override=fills)
    # net_close = -1*30 + 2*10 = -10 ; entry worst -0.8 -> pnl = (-10 -(-0.8))*100 = -920
    assert x["ledgers"]["worst"]["net_pnl_usd"] == -920.0


def test_pin_and_expired_helpers(combo_factory):
    legs = [leg("C1", "call", 640, -1, bid=5.0, ask=5.2)]
    _, pos = combo_factory(legs)
    assert pin_risk_flags(pos, 640.5, EXP) == ["pin_risk:C1"]      # |640.5-640| < 0.2% of 640.5
    assert pin_risk_flags(pos, 660.0, EXP) == []
    assert pin_risk_flags(pos, 640.5, date(2026, 8, 30)) == []     # not expiring yet
    assert [ls.spec.occ for ls in expired_legs(pos, EXP)] == ["C1"]
    assert expired_legs(pos, date(2026, 8, 30)) == []


def test_early_assignment_short_deep_itm_only(combo_factory):
    legs = [leg("C1", "call", 600, -1, bid=30.0, ask=30.10, delta=-0.97),
            leg("C2", "call", 660, +1, bid=1.0, ask=1.2, delta=0.20)]
    _, pos = combo_factory(legs)
    # S=630: C1 intrinsic 30, mid 30.05 -> extrinsic 0.05 >= 0.03 -> NOT yet at risk
    assert early_assignment_risk(pos, {"C1": (30.0, 30.10), "C2": (1.0, 1.2)}, 630.0) == []
    # extrinsic collapses to 0.02 -> fires; the LONG deep-ITM leg never fires
    assert early_assignment_risk(pos, {"C1": (30.0, 30.04), "C2": (1.0, 1.2)}, 630.0) == ["C1"]
    # low |delta| shorts don't fire even at low extrinsic
    assert early_assignment_risk(pos, {"C1": (30.0, 30.04)}, 630.0, deltas={"C1": -0.5}) == []
