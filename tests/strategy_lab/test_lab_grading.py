"""Grading math (lab-strategy-runtime-v1): PARITY with the main grader on bounded bases,
conservative-clamp properties, floor breaches, attribution reconstruction on synthetic paths."""

from __future__ import annotations

import random

from scripts.grade_options_shadow import eprocess_wealth
from atlas.strategy_lab.carisk import BASIS_CAR, BASIS_DEBIT
from atlas.strategy_lab.grading import (LAMBDAS_BOUNDED, LAMBDAS_CAR, R_CAP, attribute,
                                        loss_shares, r_return, wealth_against, wealth_for)
from atlas.strategy_lab.model import build_combo_exit_record, combo_from_entry

from .conftest import leg, make_entry


# --------------------------------------------------------------------- parity + properties
def test_parity_with_main_grader_bounded_basis():
    """Bit-for-bit: on a bounded basis the lab FOR-process IS the main eprocess_wealth."""
    rng = random.Random(7)
    for _ in range(50):
        rs = [rng.uniform(-1.0, 3.0) for _ in range(rng.randint(0, 40))]
        assert wealth_for(rs, BASIS_DEBIT)["wealth"] == eprocess_wealth(rs)


def test_car_no_loss_floor_annihilates():
    """A monster CaR loss annihilates FOR-wealth (no floor) - the honest outcome."""
    w = wealth_for([-60.0], BASIS_CAR)["wealth"]     # r < -1/lam for every lam in the CAR grid
    assert w < 1e-3
    # bounded basis floors the same loss at -1 (parity clamp)
    wb = wealth_for([-60.0], BASIS_DEBIT)["wealth"]
    assert wb == eprocess_wealth([-60.0]) > 0.7


def test_car_floor_breach_indices():
    out = wealth_for([0.5, -11.0, 0.2, -9.0], BASIS_CAR)
    # lam_max = 0.10 -> breach when r < -10
    assert out["floor_breaches"] == [1]


def test_capping_wins_never_raises_wealth_for():
    """Conservativeness: replacing any win with a bigger win must not lower wealth; capping
    means wealth with r=R_CAP equals wealth with any r > R_CAP."""
    base = [0.3, -0.2, 1.0]
    w_at_cap = wealth_for(base + [R_CAP], BASIS_CAR)["wealth"]
    w_beyond = wealth_for(base + [50.0], BASIS_CAR)["wealth"]
    assert abs(w_at_cap - w_beyond) < 1e-12


def test_flooring_losses_never_raises_wealth_against():
    """Mirror conservativeness: the against-process treats any loss beyond -1 as -1."""
    base = [0.3, -0.2]
    w_at_floor = wealth_against(base + [-1.0], BASIS_CAR)
    w_beyond = wealth_against(base + [-30.0], BASIS_CAR)
    assert abs(w_at_floor - w_beyond) < 1e-12
    # and a monster WIN annihilates the against-case
    assert wealth_against([60.0], BASIS_CAR) < 1e-3


def test_lambda_grids():
    assert wealth_for([], BASIS_DEBIT)["wealth"] == 1.0
    assert LAMBDAS_BOUNDED == (0.05, 0.10, 0.20)
    assert LAMBDAS_CAR == (0.02, 0.05, 0.10)


def test_wealth_directions():
    """Winning stream: FOR grows, AGAINST shrinks. Losing stream: mirror."""
    wins = [0.4] * 30
    losses = [-0.4] * 30
    assert wealth_for(wins, BASIS_DEBIT)["wealth"] > 5.0
    assert wealth_against(wins, BASIS_DEBIT) < 1.0
    assert wealth_for(losses, BASIS_DEBIT)["wealth"] < 1.0
    assert wealth_against(losses, BASIS_DEBIT) > 5.0


# --------------------------------------------------------------------- r_return
def _exit_for(rec, pos, close, S=630.0, iv=None):
    legs_close = []
    for l, c in zip(rec["legs"], close):
        row = {"occ": l["occ"], "bid": c[0], "ask": c[1]}
        if iv is not None:
            row["iv"] = iv.get(l["occ"], 0.0)
        legs_close.append(row)
    return build_combo_exit_record(ts=rec["ts_epoch"] + 3600 * 6.5, day=rec["day"], pos=pos,
                                   rule="t", legs_close=legs_close, S=S, state={},
                                   hold_trading_days=1.0)


def test_r_return_uses_frozen_denominator(combo_factory):
    legs = [leg("C1", "call", 630, +1, bid=10.0, ask=10.4),
            leg("C2", "call", 640, -1, bid=5.0, ask=5.4)]
    rec, pos = combo_factory(legs)
    x = _exit_for(rec, pos, [(12.0, 12.4), (6.0, 6.4)])
    # worst pnl +20 (proven in fills test); denom 540
    assert abs(r_return(x) - 20.0 / 540.0) < 1e-12
    x["grading"]["denom_usd"] = 0
    assert r_return(x) is None


# --------------------------------------------------------------------- attribution
def test_attribution_reconstructs_synthetic_components(combo_factory):
    """Single long call, known delta/vega/theta; move S and IV by known amounts; the computed
    components must reconstruct the inputs (hand arithmetic in comments)."""
    legs = [leg("C1", "call", 630, +1, bid=10.0, ask=10.0, delta=0.50, vega=0.80,
                theta_day=-0.10, iv=0.20)]
    rec, pos = combo_factory(legs)
    # gross uses mid-to-mid: entry mid 10.0. Close mid 12.0 -> gross = +200.
    x = _exit_for(rec, pos, [(12.0, 12.0)], S=633.0, iv={"C1": 0.22})
    a = attribute(x, rec)
    # direction = 0.5*100 shares * (633-630) = +150
    assert a["direction_usd"] == 150.0
    # vol = vega 0.8 * dIV 0.02 * 100 = +1.6
    assert abs(a["vol_usd"] - 1.6) < 1e-9
    # theta = -0.10 * 1 day * 100 = -10
    assert a["theta_usd"] == -10.0
    # residual = 200 - 150 - 1.6 + 10 = 58.4 ; coverage = 1 - 58.4/200 = 0.708
    assert abs(a["residual_usd"] - 58.4) < 1e-9
    assert abs(a["coverage"] - 0.708) < 1e-3
    assert a["tail_flag"] is False


def test_attribution_tail_flag(combo_factory):
    legs = [leg("C1", "call", 660, -1, bid=3.5, ask=3.7)]     # CaR basis, denom 9960
    rec, pos = combo_factory(legs, declared_basis="car")
    # catastrophic buy-back at 150: pnl worst = (-150 - (-3.5)) * 100 = -14650 -> r ~ -1.47
    x = _exit_for(rec, pos, [(149.9, 150.1)], S=810.0)
    a = attribute(x, rec)
    assert a["tail_flag"] is True


def test_loss_shares_and_driver():
    attribs = [
        {"direction_usd": -300.0, "vol_usd": -50.0, "theta_usd": 20.0, "residual_usd": -10.0,
         "spread_tax_usd": 40.0, "coverage": 0.9, "tail_flag": False},
        {"direction_usd": -200.0, "vol_usd": -30.0, "theta_usd": 10.0, "residual_usd": 5.0,
         "spread_tax_usd": 30.0, "coverage": 0.8, "tail_flag": True},
        {"direction_usd": 400.0, "vol_usd": 10.0, "theta_usd": -5.0, "residual_usd": 0.0,
         "spread_tax_usd": 20.0, "coverage": 0.95, "tail_flag": False},
    ]
    nets = [-340.0, -215.0, 405.0]
    agg = loss_shares(attribs, nets)
    assert agg["loss_driver"] == "direction"       # 500 of the loss mass
    assert agg["win_driver"] == "direction"
    assert agg["n_loss"] == 2 and agg["n_win"] == 1 and agg["tail_count"] == 1
    assert abs(sum(agg["loss_shares"].values()) - 1.0) < 0.01
