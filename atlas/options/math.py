"""OPTIONS DECISION MATH (O1) - the quantities the owner's exit framework runs on, built on the
vendored, Hull-verified BSM primitives (atlas/options/vendor/blackscholes.py).

Everything here is pure and deterministic. Conventions:
- T is in YEARS of TRADING time (252 days x 390 RTH minutes) - weekend theta is pre-paid in the
  quoted price, so decisions use trading time (see trading_T()).
- mu is the assumed DRIFT of the underlying price process (0 = conservative/no-view). The exit
  engine always computes the dual: mu=0 AND mu_thesis - the gap measures thesis-dependence.
- All probabilities are real-world under the caller's (mu, sigma); nothing here is risk-neutral
  except where BSM pricing itself is used to revalue the contract.
- KNOWN MODEL RISK (registered opts-variant-realized-vol-physical-v1, 2026-07-10): callers pass
  the option's own solved IV as the PHYSICAL diffusion sigma (ev_hold's S_T distribution,
  p_touch, p_regain, theta_share's directional term). Implied vol carries the volatility risk
  premium - index IV typically exceeds realized vol by a few points - so probabilities and EVs
  are mildly PRO-HOLD across the board: a directionally consistent, documented bias. A
  realized-vol physical measure is a paired-replay column; it goes live only on N-evidence
  (an arbitrary haircut would be the banned unregistered-constant class).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np

from atlas.options.vendor.blackscholes import bs_price
from atlas.options.vendor.models import OptionType

MIN_T = 1.0 / (252.0 * 390.0)             # one trading minute, in years
_MIN_T = MIN_T                            # backward-compat alias
RTH_MINUTES = 390


def _phi(x: float) -> float:
    # erfc form (opts-fix-math-audit-20260710): 0.5*(1+erf(x/√2)) underflows to exactly 0 for
    # x <~ -8.3 (catastrophic cancellation), silently zeroing the reflection term in
    # _bm_hits_level; erfc keeps full relative precision in the left tail.
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


# --------------------------------------------------------------------------- trading time
def trading_T(now_et: datetime, expiry: date, *, close_minute: int = 16 * 60) -> float:
    """Remaining life in TRADING years: fraction of today's RTH left + whole trading days
    (weekdays; holidays ignored - a <1-day overstatement at most) until expiry's close."""
    minutes_today = max(0, close_minute - (now_et.hour * 60 + now_et.minute))
    frac_today = min(minutes_today, RTH_MINUTES) / RTH_MINUTES
    d = now_et.date()
    if expiry < d:                 # already expired: dead, not "rest of today" (audit fix)
        return _MIN_T
    if expiry == d:
        return max(frac_today / 252.0, _MIN_T)
    days = 0
    cur = d + timedelta(days=1)
    while cur <= expiry:
        if cur.weekday() < 5:
            days += 1
        cur += timedelta(days=1)
    return max((frac_today + days) / 252.0, _MIN_T)


# --------------------------------------------------------------------------- P(touch)
def _bm_hits_level(b: float, nu: float, sigma: float, T: float) -> float:
    """P(drifted Brownian motion nu*t + sigma*W_t reaches level b > 0 within T) - reflection
    principle: Phi((nu*T - b)/(s*sqrt(T))) + exp(2*nu*b/s^2) * Phi((-b - nu*T)/(s*sqrt(T)))."""
    st = sigma * math.sqrt(T)
    term1 = _phi((nu * T - b) / st)
    expo = 2.0 * nu * b / (sigma * sigma)
    term2 = math.exp(min(expo, 700.0)) * _phi((-b - nu * T) / st) if expo > -700.0 else 0.0
    return min(1.0, max(0.0, term1 + term2))


def p_touch(S: float, H: float, sigma: float, T: float, mu: float = 0.0) -> float:
    """Exact GBM first-passage probability that the underlying TOUCHES barrier H within T years.
    H above S = upside target; H below S = downside target. mu is the PRICE drift (ln S drifts at
    mu - sigma^2/2); sigma annualized. Degenerate inputs fail toward 0 (conservative), except an
    already-touched barrier which is 1."""
    if S <= 0 or H <= 0 or T <= 0:
        return 0.0
    if math.isclose(S, H, rel_tol=1e-12):
        return 1.0
    if sigma <= 0:                              # deterministic drift
        end = S * math.exp(mu * T)
        return 1.0 if (end >= H if H > S else end <= H) else 0.0
    if H > S:                                   # upside: ln(S_t/S) must reach b = ln(H/S) > 0
        return _bm_hits_level(math.log(H / S), mu - 0.5 * sigma * sigma, sigma, T)
    # downside: ln(S/S_t) = -(mu - s^2/2)t - s*W_t must reach b = ln(S/H) > 0; its drift is
    # nu' = s^2/2 - mu (the Ito sign - a plain -mu mirror would be wrong by sigma^2)
    return _bm_hits_level(math.log(S / H), 0.5 * sigma * sigma - mu, sigma, T)


def expected_move(S: float, iv: float, T: float) -> float:
    """1-sigma expected move in price units (the ATM-straddle market convention is ~0.8x this)."""
    if S <= 0 or iv <= 0 or T <= 0:
        return 0.0
    return S * iv * math.sqrt(T)


# --------------------------------------------------------------------------- EV(hold)
def _gh_grid(n: int) -> tuple[np.ndarray, np.ndarray]:
    x, w = np.polynomial.hermite.hermgauss(n)   # physicists' Hermite
    z = x * math.sqrt(2.0)                      # standard-normal nodes
    wn = w / math.sqrt(math.pi)                 # weights sum to 1
    return z, wn


def _expected_intrinsic(S: float, K: float, opt_type: OptionType,
                        mu: float, sigma: float, dt: float) -> float:
    """EXACT E[max(±(S_T − K), 0)] for lognormal S_T under PHYSICAL drift mu (truncated-lognormal
    closed form - the BS shape with e^{mu·dt} in place of the risk-neutral forward). Replaces the
    Gauss-Hermite evaluation of the kinked payoff, which under-integrated at n=11
    (opts-fix-math-audit-20260710)."""
    if dt <= 0 or sigma <= 0:
        s_end = S * math.exp(mu * max(dt, 0.0))
        return max(0.0, s_end - K) if opt_type == OptionType.CALL else max(0.0, K - s_end)
    st = sigma * math.sqrt(dt)
    fwd = S * math.exp(mu * dt)
    d1 = (math.log(S / K) + (mu + 0.5 * sigma * sigma) * dt) / st
    d2 = d1 - st
    if opt_type == OptionType.CALL:
        return fwd * _phi(d1) - K * _phi(d2)
    return K * _phi(-d2) - fwd * _phi(-d1)


def _critical_spot(threshold: float, K: float, opt_type: OptionType, r: float, q: float,
                   iv_exit: float, T_exit: float) -> float | None:
    """S* such that the contract's value at the horizon equals `threshold` (value is monotone
    in S: increasing for calls, decreasing for puts). Bisection over a wide bracket; None when
    the threshold is outside the reachable value range (p_profit is then 0 or 1)."""
    if T_exit <= _MIN_T:                       # intrinsic: invertible in closed form
        if opt_type == OptionType.CALL:
            return K + threshold
        s = K - threshold
        return s if s > 0 else None            # a put's value is capped at K

    def px(s: float) -> float:
        return bs_price(s, K, r, q, iv_exit, T_exit, opt_type)

    lo, hi = K * 1e-3, K * 1e3
    p_lo, p_hi = px(lo), px(hi)
    lo_v, hi_v = (p_lo, p_hi) if opt_type == OptionType.CALL else (p_hi, p_lo)
    if threshold <= lo_v or threshold >= hi_v:
        return None
    for _ in range(80):
        m = math.sqrt(lo * hi)                 # geometric bisection (lognormal-natural)
        if (px(m) < threshold) == (opt_type == OptionType.CALL):
            lo = m
        else:
            hi = m
    return math.sqrt(lo * hi)


def ev_hold(S: float, K: float, opt_type: OptionType, r: float, q: float,
            iv_now: float, T_now: float, dt: float, mark_mid: float,
            *, mu: float = 0.0, iv_change: float = 0.0, n_grid: int = 11) -> dict:
    """Expected value of HOLDING for dt more years (trading time) vs the current mid: revalue the
    contract with full BSM over a Gauss-Hermite grid of underlying scenarios (never linear-greek).
    Returns {ev, e_value, p_profit} where ev = PV(E[value(t+dt)]) - mark_mid (discounted at r - 
    audit fix: the undiscounted comparison was a pro-hold bias). IV path: iv_now + iv_change at
    the horizon. At/after expiry the EXACT truncated-lognormal E[intrinsic] replaces the grid,
    and p_profit is EXACT via the monotone critical spot S* (the old indicator-through-quadrature
    was quantized to ~10 attainable values and flipped the selector's 0.40 floor - 
    opts-fix-math-audit-20260710)."""
    if S <= 0 or K <= 0 or T_now <= 0 or mark_mid < 0:
        return {"ev": 0.0, "e_value": mark_mid, "p_profit": 0.0}
    dt = min(max(dt, 0.0), T_now)
    T_exit = T_now - dt
    sigma = max(iv_now, 1e-4)
    iv_exit = max(iv_now + iv_change, 1e-4)
    disc = math.exp(-max(r, 0.0) * dt)

    if T_exit <= _MIN_T:
        e_value = disc * _expected_intrinsic(S, K, opt_type, mu, sigma, dt)
    else:
        z, w = _gh_grid(max(5, int(n_grid)))
        drift = (mu - 0.5 * sigma * sigma) * dt
        vol = sigma * math.sqrt(dt) if dt > 0 else 0.0
        values = np.empty(len(z))
        for i, zi in enumerate(z):
            s_i = S * math.exp(drift + vol * zi)
            values[i] = bs_price(s_i, K, r, q, iv_exit, T_exit, opt_type)
        e_value = disc * float(np.dot(w, values))

    # EXACT p_profit: value at the horizon is monotone in S_T, so P(value > mid) is a single
    # lognormal tail probability at the critical spot S*
    if dt <= 0 or sigma <= 0:
        s_end = S                               # no diffusion: degenerate indicator
        v_end = e_value
        p_profit = 1.0 if v_end > mark_mid else 0.0
    else:
        s_star = _critical_spot(mark_mid, K, opt_type, r, q, iv_exit, T_exit)
        if s_star is None or s_star <= 0:
            # threshold unreachable: value everywhere above or everywhere below the mid
            probe = bs_price(S, K, r, q, iv_exit, T_exit, opt_type) if T_exit > _MIN_T else \
                _expected_intrinsic(S, K, opt_type, mu, sigma, dt)
            p_profit = 1.0 if probe > mark_mid else 0.0
        else:
            st = sigma * math.sqrt(dt)
            z_star = (math.log(s_star / S) - (mu - 0.5 * sigma * sigma) * dt) / st
            p_profit = (1.0 - _phi(z_star)) if opt_type == OptionType.CALL else _phi(z_star)
    return {"ev": e_value - mark_mid, "e_value": e_value, "p_profit": float(p_profit)}


def ev_hold_thesis(S, K, opt_type, r, q, iv_now, T_now, dt, mark_mid,
                   *, target_move: float, horizon_T: float, p_thesis: float = 0.5,
                   iv_change: float = 0.0, n_grid: int = 11) -> dict:
    """Thesis-mixture EV: p x (drift that reaches target_move over horizon_T) + (1-p) x (mu=0).
    target_move is fractional (+0.005 = +0.5%)."""
    mu_t = math.log(1.0 + target_move) / max(horizon_T, _MIN_T)
    a = ev_hold(S, K, opt_type, r, q, iv_now, T_now, dt, mark_mid,
                mu=mu_t, iv_change=iv_change, n_grid=n_grid)
    b = ev_hold(S, K, opt_type, r, q, iv_now, T_now, dt, mark_mid,
                mu=0.0, iv_change=iv_change, n_grid=n_grid)
    p = min(1.0, max(0.0, p_thesis))
    out = {k: p * a[k] + (1.0 - p) * b[k] for k in a}
    # measure-disagreement instrumentation (audit 2026-07-16 Wave 0.3): expose the two mixture
    # components so callers can LOG how much of the blended EV is assumption (thesis arm) vs
    # no-view (mu=0 arm) - the live trade where the market-implied thesis weight was -0.004
    # was invisible without these.
    out["ev_thesis"] = a["ev"]
    out["ev_mu0"] = b["ev"]
    return out


# --------------------------------------------------------------------------- regain move
def regain_move(c_ref: float, S: float, K: float, opt_type: OptionType, r: float, q: float,
                iv: float, T_minus: float) -> float | None:
    """the owner's metric: the fractional underlying move S*/S - 1 needed for the contract to be worth
    c_ref again at time T_minus (e.g. tomorrow). Bisection on the monotone BSM price. None when
    unreachable within +/-60% (that is itself the signal: the value is gone)."""
    if c_ref <= 0 or S <= 0 or T_minus <= 0 or iv <= 0:
        return None
    lo, hi = (1.0, 1.6) if opt_type == OptionType.CALL else (0.4, 1.0)

    def px(mult: float) -> float:
        return bs_price(S * mult, K, r, q, iv, T_minus, opt_type)

    # a call regains value as S rises; a put as S falls - orient the bracket accordingly
    if opt_type == OptionType.CALL:
        if px(1.0) >= c_ref:
            return 0.0
        if px(hi) < c_ref:
            return None
        a, b = 1.0, hi
        for _ in range(60):
            m = (a + b) / 2.0
            if px(m) < c_ref:
                a = m
            else:
                b = m
        return b - 1.0
    else:
        if px(1.0) >= c_ref:
            return 0.0
        if px(lo) < c_ref:
            return None
        a, b = lo, 1.0
        for _ in range(60):
            m = (a + b) / 2.0
            if px(m) < c_ref:
                b = m
            else:
                a = m
        return a - 1.0


# --------------------------------------------------------------------------- P(regain)
def zero_dte_effective_T(T_now: float, minute_now: int, minute_end: int) -> float:
    """The EMPIRICAL 0DTE clock (opts-rework-exit-core-v1, derived - no new constants): map the
    shipped decay ramp onto BSM time. The ramp says remaining time value decays at rate(m)/hour,
    so over [now, end): TV(end) = TV(now) * exp(-I), I = sum rate(m)/60. ATM BSM time value is
    proportional to sqrt(T), hence the model time that reproduces the empirical decay is
        T_eff(end) = T_now * exp(-2 * I).
    T_eff may exceed the model's own T(end) in the MORNING (the documented 0DTE reality: time
    value holds up early and collapses after 14:00 - BSM's sqrt-T clock front-loads decay more
    evenly) and undershoots it in the afternoon. Floored at MIN_T."""
    if T_now <= 0:
        return _MIN_T
    a, b = int(minute_now), int(minute_end)
    if b <= a:
        return max(T_now, _MIN_T)
    integral = sum(zero_dte_decay_rate(m) for m in range(a, b)) / 60.0
    return max(T_now * math.exp(-2.0 * integral), _MIN_T)


def p_regain(c_ref: float, S: float, K: float, opt_type: OptionType, r: float, q: float,
             iv: float, T_now: float, *, minute: int, dte: int, sell_clock_min: int,
             mu: float = 0.0) -> dict:
    """P(the underlying touches, within the ACTIONABLE horizon, the level at which the contract
 - after paying the horizon's theta - is worth c_ref again). owner rule 2 verbatim, made
    continuous (rules 11/25): the barrier is solved at the horizon END (regain_move at T_minus,
    so the level already prices the interval's decay - touching EARLIER means the contract was
    worth MORE than c_ref there, making this the conservative-toward-holding bound), then
    p_touch answers whether we reach that level in time under the CURRENT drift estimate.
    Rule 18: c_ref is TODAY'S value (the current mid), never the high-water mark.

    Horizon: 0DTE -> until the engine's own rule-(a) forced-sale clock (the caller resolves the
    deep-ITM extension); DTE>=1 -> min(T_now, one trading day) (rule 10: every additional day is
    a new decision). 0DTE uses the empirical clock (zero_dte_effective_T) for the horizon-end
    life. Returns {p, move, dt_h, t_minus}; move None (unreachable +/-60%) -> p = 0.0."""
    if c_ref <= 0 or S <= 0 or T_now <= 0 or iv <= 0:
        return {"p": 0.0, "move": None, "dt_h": 0.0, "t_minus": _MIN_T}
    if dte == 0:
        mins_left = max(0, int(sell_clock_min) - int(minute))
        dt_h = min(mins_left / (390.0 * 252.0), T_now)
        # MATH-CORE-1 (docs/AUDIT_2026-07-16_options_platform.md §3.3, 2/2 refuters upheld):
        # zero_dte_effective_T maps the CURRENT model time onto the horizon end by integrating
        # the empirical decay ramp over [now, end). Feeding it the horizon-END time
        # (T_now - dt_h) charged model decay AND empirical decay for the same interval - 
        # every historical p_regain was biased toward selling winners (13:00 example: coded
        # 41.9 min of life vs the intended 125.8; p_regain 0.53 vs 0.82).
        t_minus = zero_dte_effective_T(T_now, int(minute), int(sell_clock_min))
    else:
        dt_h = min(T_now, 1.0 / 252.0)
        t_minus = max(T_now - dt_h, _MIN_T)
    if dt_h <= 0:
        return {"p": 0.0, "move": None, "dt_h": 0.0, "t_minus": t_minus}
    m = regain_move(c_ref, S, K, opt_type, r, q, iv, t_minus)
    if m is None:
        return {"p": 0.0, "move": None, "dt_h": dt_h, "t_minus": t_minus}
    if m == 0.0:
        return {"p": 1.0, "move": 0.0, "dt_h": dt_h, "t_minus": t_minus}
    p = p_touch(S, S * (1.0 + m), iv, dt_h, mu=mu)
    return {"p": p, "move": m, "dt_h": dt_h, "t_minus": t_minus}


# --------------------------------------------------------------------------- theta dominance
def theta_share(theta_day: float, delta: float, S: float, iv: float, dt_days: float) -> float:
    """Fraction of the next dt_days' expected P&L magnitude that is pure decay:
    |theta*dt| / (|theta*dt| + |delta| * 0.8 * S * (iv/16) * sqrt(dt_days)). >0.5 = decay dominates
    directional exposure (owner's rule g trigger, with the P_target condition)."""
    decay = abs(theta_day) * max(dt_days, 0.0)
    directional = abs(delta) * 0.8 * S * (iv / 16.0) * math.sqrt(max(dt_days, 0.0))
    tot = decay + directional
    return float(decay / tot) if tot > 0 else 0.0


def breakeven_move(theta_day: float, gamma: float) -> float:
    """Daily gamma-theta breakeven |dS|: sqrt(2|theta_day| / gamma). Price units."""
    if gamma <= 0:
        return float("inf")
    return math.sqrt(2.0 * abs(theta_day) / gamma)


# --------------------------------------------------------------------------- 0DTE decay shape
def zero_dte_decay_rate(minute_of_day: int) -> float:
    """Empirical 0DTE time-value decay rate (fraction of REMAINING time value per hour) - 
    inverse-sigmoid shape from published observation (~2%/hr at the open rising past 15%/hr after
    14:00). Hardcoded v1; refit from our own stored quote paths once N suffices (plan §O5)."""
    m = float(minute_of_day)
    return 0.02 + 0.14 / (1.0 + math.exp(-(m - 14 * 60) / 45.0))


def zero_dte_theta_multiplier(minute_of_day: int) -> float:
    """Scale factor for annualized theta on a 0DTE afternoon: rate(now) / mean rate over the
    session (>=1 after ~13:30). The exit engine multiplies theta_day by this for 0DTE positions."""
    rates = [zero_dte_decay_rate(m) for m in range(9 * 60 + 30, 16 * 60, 15)]
    avg = sum(rates) / len(rates)
    return zero_dte_decay_rate(minute_of_day) / avg
