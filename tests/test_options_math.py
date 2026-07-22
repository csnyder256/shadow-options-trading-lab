"""Options decision math (O1): p_touch vs seeded Monte Carlo (both barrier sides, with drift),
EV_hold martingale + monotonicity properties, regain-move round-trip, theta-share bounds,
trading-time conventions, 0DTE decay shape.
"""

from __future__ import annotations

import math
from datetime import date, datetime

import numpy as np

from atlas.options.math import (breakeven_move, ev_hold, ev_hold_thesis, expected_move, p_touch,
                                regain_move, theta_share, trading_T, zero_dte_decay_rate,
                                zero_dte_theta_multiplier)
from atlas.options.vendor.blackscholes import bs_price
from atlas.options.vendor.models import OptionType


def _mc_touch(S, H, sigma, T, mu, n_paths=60_000, n_steps=2000, seed=7) -> float:
    """Discrete MC with the Broadie-Glasserman-Kou continuity correction (shift the barrier by
    exp(±0.5826·σ·√dt)) so the discrete-monitoring bias doesn't swamp the comparison."""
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    z = rng.standard_normal((n_paths, n_steps))
    log_paths = np.cumsum((mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z, axis=1)
    paths = S * np.exp(log_paths)
    beta = 0.5826 * sigma * math.sqrt(dt)
    if H > S:
        return float((paths.max(axis=1) >= H * math.exp(-beta)).mean())
    return float((paths.min(axis=1) <= H * math.exp(beta)).mean())


def test_p_touch_matches_monte_carlo_up_and_down_with_drift():
    cases = [
        (100.0, 103.0, 0.25, 10 / 252, 0.0),
        (100.0, 103.0, 0.25, 10 / 252, 0.5),      # strong up-drift
        (100.0, 97.0, 0.25, 10 / 252, 0.0),
        (100.0, 97.0, 0.25, 10 / 252, 0.5),       # up-drift vs down barrier (the Ito-sign trap)
        (100.0, 96.0, 0.40, 3 / 252, -0.3),
    ]
    for S, H, sig, T, mu in cases:
        exact = p_touch(S, H, sig, T, mu)
        mc = _mc_touch(S, H, sig, T, mu)
        assert abs(exact - mc) < 0.012, (S, H, sig, T, mu, exact, mc)


def test_p_touch_dominates_terminal_probability_and_edges():
    S, H, sig, T = 100.0, 104.0, 0.3, 5 / 252
    # touching is at least as likely as finishing beyond the barrier
    n = 400_000
    rng = np.random.default_rng(1)
    st = sig * math.sqrt(T)
    terminal = S * np.exp((-0.5 * sig**2) * T + st * rng.standard_normal(n))
    p_term = float((terminal >= H).mean())
    assert p_touch(S, H, sig, T) >= p_term
    assert p_touch(100, 100.0000001, 0.2, 1 / 252) > 0.45   # barrier at spot ~ certain-ish touch
    assert p_touch(100, 200, 0.2, 1 / 252) < 1e-6
    assert p_touch(0, 100, 0.2, 1.0) == 0.0
    assert p_touch(100, 104, 0.0, 1.0, mu=0.5) == 1.0       # deterministic drift reaches it
    assert p_touch(100, 104, 0.0, 0.001, mu=0.0) == 0.0


def test_ev_hold_martingale_at_fair_mid_and_monotonicities():
    S, K, r, q, iv, T = 100.0, 100.0, 0.0, 0.0, 0.30, 10 / 252
    fair = bs_price(S, K, r, q, iv, T, OptionType.CALL)
    # mu=0, r=0: E[BS(S_dt, T-dt)] == BS(S, T) (martingale) => EV(hold) ~ 0 at fair mid
    res = ev_hold(S, K, OptionType.CALL, r, q, iv, T, 2 / 252, fair, mu=0.0, n_grid=21)
    assert abs(res["ev"]) < 0.02 * fair
    # positive drift helps a call; negative IV change hurts
    up = ev_hold(S, K, OptionType.CALL, r, q, iv, T, 2 / 252, fair, mu=1.0, n_grid=21)
    crush = ev_hold(S, K, OptionType.CALL, r, q, iv, T, 2 / 252, fair, iv_change=-0.05, n_grid=21)
    assert up["ev"] > res["ev"] > crush["ev"]
    # thesis mixture sits between its two components
    mix = ev_hold_thesis(S, K, OptionType.CALL, r, q, iv, T, 2 / 252, fair,
                         target_move=0.02, horizon_T=5 / 252, p_thesis=0.5, n_grid=21)
    assert res["ev"] - 1e-9 <= mix["ev"] <= up["ev"] + abs(up["ev"])
    # expiry horizon at mu=0, r=0: E[intrinsic] == today's BS price EXACTLY (martingale
    # identity - the exact truncated-lognormal form, opts-fix-math-audit-20260710; the old
    # GH-on-a-kink quadrature UNDERESTIMATED it, and the previous strict `<` pin passed only
    # by that numerical error)
    exp_res = ev_hold(S, K, OptionType.CALL, r, q, iv, T, T, fair, mu=0.0, n_grid=21)
    assert abs(exp_res["e_value"] - fair) < 1e-9
    # with discounting (r>0) the PV of the expectation sits strictly below the same-measure fair
    exp_disc = ev_hold(S, K, OptionType.CALL, 0.04, q, iv, T, T,
                       bs_price(S, K, 0.04, q, iv, T, OptionType.CALL), mu=0.0, n_grid=21)
    assert exp_disc["e_value"] < bs_price(S, K, 0.04, q, iv, T, OptionType.CALL) * 1.001
    # p_profit is now EXACT and continuous (was quantized to ~10 GH node sums): the fair-mid
    # ATM case sits mid-range, and nearby strikes move it smoothly
    assert 0.30 < res["p_profit"] < 0.70
    p1 = ev_hold(S, 101.0, OptionType.CALL, r, q, iv, T, 2 / 252,
                 bs_price(S, 101.0, r, q, iv, T, OptionType.CALL), mu=0.0)["p_profit"]
    p2 = ev_hold(S, 103.0, OptionType.CALL, r, q, iv, T, 2 / 252,
                 bs_price(S, 103.0, r, q, iv, T, OptionType.CALL), mu=0.0)["p_profit"]
    assert p1 != p2 and 0.0 < p1 < 1.0 and 0.0 < p2 < 1.0


def test_p_regain_composition_and_zero_dte_clock():
    from atlas.options.math import MIN_T, p_regain, zero_dte_effective_T

    # value-gone (regain_move None: 150 is beyond even a +60% move's value) -> p exactly 0
    gone = p_regain(150.0, 100.0, 100.0, OptionType.CALL, 0.0, 0.0, 0.30, 5 / 252,
                    minute=660, dte=1, sell_clock_min=900)
    assert gone["move"] is None and gone["p"] == 0.0
    # a call already worth more than c_ref at T_minus regains trivially
    rich = bs_price(100.0, 100.0, 0.0, 0.0, 0.30, 4 / 252, OptionType.CALL) * 0.5
    easy = p_regain(rich, 100.0, 100.0, OptionType.CALL, 0.0, 0.0, 0.30, 5 / 252,
                    minute=660, dte=1, sell_clock_min=900)
    assert easy["move"] == 0.0 and easy["p"] == 1.0
    # favorable drift raises the touch probability (monotone in mu, call side)
    mid = bs_price(100.0, 100.0, 0.0, 0.0, 0.30, 5 / 252, OptionType.CALL)
    lo = p_regain(mid, 100.0, 100.0, OptionType.CALL, 0.0, 0.0, 0.30, 5 / 252,
                  minute=660, dte=1, sell_clock_min=900, mu=-3.0)["p"]
    hi = p_regain(mid, 100.0, 100.0, OptionType.CALL, 0.0, 0.0, 0.30, 5 / 252,
                  minute=660, dte=1, sell_clock_min=900, mu=+3.0)["p"]
    assert hi > lo
    # 0DTE: at/past the engine's own sell clock there is no actionable horizon
    late = p_regain(1.0, 100.0, 100.0, OptionType.CALL, 0.0, 0.0, 0.30, 30 / 390 / 252,
                    minute=905, dte=0, sell_clock_min=900)
    assert late["p"] == 0.0 and late["dt_h"] == 0.0
    # the empirical 0DTE clock: shrinks model time, monotone in window width, floored
    T = 120 / 390 / 252
    t1 = zero_dte_effective_T(T, 840, 870)
    t2 = zero_dte_effective_T(T, 840, 930)
    assert MIN_T <= t2 < t1 < T
    assert zero_dte_effective_T(T, 900, 900) == T                   # empty window = no decay


def test_regain_move_roundtrip_call_and_put():
    S, K, r, q, iv = 100.0, 100.0, 0.0, 0.0, 0.35
    c_today = bs_price(S, K, r, q, iv, 5 / 252, OptionType.CALL)
    m = regain_move(c_today, S, K, OptionType.CALL, r, q, iv, 4 / 252)
    assert m is not None and m > 0                        # must move UP to offset a day of decay
    assert abs(bs_price(S * (1 + m), K, r, q, iv, 4 / 252, OptionType.CALL) - c_today) < 1e-4
    p_today = bs_price(S, K, r, q, iv, 5 / 252, OptionType.PUT)
    mp = regain_move(p_today, S, K, OptionType.PUT, r, q, iv, 4 / 252)
    assert mp is not None and mp < 0                      # puts regain by moving DOWN
    assert abs(bs_price(S * (1 + mp), K, r, q, iv, 4 / 252, OptionType.PUT) - p_today) < 1e-4
    # unreachable reference -> None (the value is simply gone)
    assert regain_move(c_today * 50, S, K, OptionType.CALL, r, q, iv, 1 / 252) is None
    # already worth it -> 0.0
    assert regain_move(c_today * 0.5, S, K, OptionType.CALL, r, q, iv, 4 / 252) == 0.0


def test_theta_share_and_breakeven():
    assert 0.0 <= theta_share(-5.0, 0.6, 100.0, 0.3, 1.0) <= 1.0
    # zero delta => pure decay
    assert theta_share(-5.0, 0.0, 100.0, 0.3, 1.0) == 1.0
    # zero theta => pure direction
    assert theta_share(0.0, 0.6, 100.0, 0.3, 1.0) == 0.0
    assert breakeven_move(-0.5, 0.05) == math.sqrt(2 * 0.5 / 0.05)
    assert breakeven_move(-0.5, 0.0) == float("inf")


def test_trading_time_conventions():
    # 0DTE at 10:00 ET: 360 RTH minutes left = 360/390 of a day
    t = trading_T(datetime(2026, 7, 10, 10, 0), date(2026, 7, 10))
    assert abs(t - (360 / 390) / 252) < 1e-12
    # Friday 15:00 -> Monday expiry: 60/390 today + 1 trading day (weekend pre-paid)
    t2 = trading_T(datetime(2026, 7, 10, 15, 0), date(2026, 7, 13))
    assert abs(t2 - ((60 / 390) + 1) / 252) < 1e-12
    # after the close on expiry day: floored at one trading minute
    t3 = trading_T(datetime(2026, 7, 10, 16, 30), date(2026, 7, 10))
    assert t3 > 0


def test_zero_dte_decay_shape():
    assert zero_dte_decay_rate(9 * 60 + 35) < 0.04       # gentle at the open
    assert zero_dte_decay_rate(15 * 60) > 0.10           # steep in the afternoon
    rates = [zero_dte_decay_rate(m) for m in range(9 * 60 + 30, 16 * 60, 5)]
    assert rates == sorted(rates)                        # monotone increasing
    assert zero_dte_theta_multiplier(15 * 60) > 1.5 > zero_dte_theta_multiplier(10 * 60)
