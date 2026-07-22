"""Black-Scholes-Merton pricing, Greeks, and an implied-volatility solver.

Merton form with a continuous dividend yield ``q`` so dividend-paying names are
handled correctly. Everything here is a pure, deterministic function of the
inputs ``(S, K, r, q, sigma, T)`` - the same inputs always produce the same
output, which is the whole point of the engine.

Conventions (matching how option chains quote Greeks):
- ``theta`` is returned **per calendar day** (annual theta / 365).
- ``vega`` and ``rho`` are returned **per 1 percentage point** (per 1%), i.e.
  the raw per-unit value divided by 100.

References: Hull, *Options, Futures, and Other Derivatives*; Macroption
Black-Scholes formula pages; CBOE "Learning the Greeks".
"""

from __future__ import annotations

import math
from typing import Optional

from atlas.options.vendor.models import Greeks, OptionType  # VENDORED: was `from app.models import ...`

_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _d1_d2(S: float, K: float, r: float, q: float, sigma: float, T: float):
    if S <= 0 or K <= 0 or sigma <= 0 or T <= 0:
        raise ValueError("S, K, sigma, T must be positive")
    vol_sqrt_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


def bs_price(
    S: float, K: float, r: float, q: float, sigma: float, T: float,
    option_type: OptionType,
) -> float:
    """Black-Scholes-Merton theoretical price of a European option."""
    if T <= 0:
        # At/after expiry, value is intrinsic.
        if option_type == OptionType.CALL:
            return max(0.0, S - K)
        return max(0.0, K - S)
    if sigma <= 0:
        # Degenerate: discounted intrinsic on the forward.
        fwd = S * math.exp(-q * T)
        disc_k = K * math.exp(-r * T)
        if option_type == OptionType.CALL:
            return max(0.0, fwd - disc_k)
        return max(0.0, disc_k - fwd)

    d1, d2 = _d1_d2(S, K, r, q, sigma, T)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    if option_type == OptionType.CALL:
        return S * disc_q * _norm_cdf(d1) - K * disc_r * _norm_cdf(d2)
    return K * disc_r * _norm_cdf(-d2) - S * disc_q * _norm_cdf(-d1)


def _vega_raw(S: float, q: float, T: float, d1: float) -> float:
    """Vega per 1.0 (100 percentage points) change in sigma - used by the solver."""
    return S * math.exp(-q * T) * _norm_pdf(d1) * math.sqrt(T)


def greeks(
    S: float, K: float, r: float, q: float, sigma: float, T: float,
    option_type: OptionType,
) -> Greeks:
    """All first-order Greeks in chain-quote conventions (see module docstring)."""
    d1, d2 = _d1_d2(S, K, r, q, sigma, T)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    pdf_d1 = _norm_pdf(d1)

    if option_type == OptionType.CALL:
        delta = disc_q * _norm_cdf(d1)
    else:
        delta = -disc_q * _norm_cdf(-d1)

    gamma = disc_q * pdf_d1 / (S * sigma * math.sqrt(T))

    vega_raw = _vega_raw(S, q, T, d1)

    common_theta = -(S * disc_q * pdf_d1 * sigma) / (2.0 * math.sqrt(T))
    if option_type == OptionType.CALL:
        theta_annual = (
            common_theta
            - r * K * disc_r * _norm_cdf(d2)
            + q * S * disc_q * _norm_cdf(d1)
        )
        rho_raw = K * T * disc_r * _norm_cdf(d2)
    else:
        theta_annual = (
            common_theta
            + r * K * disc_r * _norm_cdf(-d2)
            - q * S * disc_q * _norm_cdf(-d1)
        )
        rho_raw = -K * T * disc_r * _norm_cdf(-d2)

    return Greeks(
        delta=delta,
        gamma=gamma,
        theta=theta_annual / 365.0,   # per calendar day
        vega=vega_raw / 100.0,        # per 1% IV
        rho=rho_raw / 100.0,          # per 1% rate
        d1=d1,
        d2=d2,
    )


def _intrinsic_lower_bound(
    S: float, K: float, r: float, q: float, T: float, option_type: OptionType
) -> float:
    fwd = S * math.exp(-q * T)
    disc_k = K * math.exp(-r * T)
    if option_type == OptionType.CALL:
        return max(0.0, fwd - disc_k)
    return max(0.0, disc_k - fwd)


def implied_vol(
    price: float, S: float, K: float, r: float, q: float, T: float,
    option_type: OptionType,
    tol: float = 1e-7, max_iter: int = 100,
) -> Optional[float]:
    """Recover implied volatility by inverting BSM from a market price.

    Newton-Raphson on Vega with a bisection fallback. Returns ``None`` when the
    price is below intrinsic / outside the arbitrage bounds or no root is found
    (e.g. illiquid, crossed, or no two-sided market).
    """
    if price is None or price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return None

    lower = _intrinsic_lower_bound(S, K, r, q, T, option_type)
    if price < lower - 1e-8:
        return None  # price below no-arbitrage floor; cannot be a valid premium
    # Upper bound: a call can't exceed the (discounted) spot; a put can't exceed K.
    upper_bound = S * math.exp(-q * T) if option_type == OptionType.CALL else K * math.exp(-r * T)
    if price >= upper_bound:
        return None

    sqrt_t = math.sqrt(T)
    # Brenner-Subrahmanyam ATM seed, clamped to a sane range.
    sigma = max(0.05, min(3.0, (price / S) * math.sqrt(2.0 * math.pi) / sqrt_t)) or 0.2

    for _ in range(max_iter):
        try:
            model = bs_price(S, K, r, q, sigma, T, option_type)
            d1, _ = _d1_d2(S, K, r, q, sigma, T)
        except ValueError:
            break
        diff = model - price
        if abs(diff) < tol:
            return sigma
        v = _vega_raw(S, q, T, d1)
        if v < 1e-10:
            break  # vega too small for a stable Newton step -> bisection
        sigma -= diff / v
        if sigma <= 1e-6 or sigma > 5.0:
            break  # left the sensible region -> bisection

    # Bisection fallback on [1e-4, 5.0].
    lo, hi = 1e-4, 5.0
    try:
        f_lo = bs_price(S, K, r, q, lo, T, option_type) - price
        f_hi = bs_price(S, K, r, q, hi, T, option_type) - price
    except ValueError:
        return None
    if f_lo * f_hi > 0:
        return None  # no sign change -> no root in bracket
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f_mid = bs_price(S, K, r, q, mid, T, option_type) - price
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return 0.5 * (lo + hi)


def prob_itm(
    S: float, K: float, r: float, q: float, sigma: float, T: float,
    option_type: OptionType,
) -> float:
    """Risk-neutral probability of finishing in the money: N(d2) call / N(-d2) put.

    Used (with K set to the break-even price) to compute probability of profit.
    """
    if sigma <= 0 or T <= 0:
        # Degenerate: deterministic forward.
        fwd = S * math.exp((r - q) * T)
        if option_type == OptionType.CALL:
            return 1.0 if fwd > K else 0.0
        return 1.0 if fwd < K else 0.0
    _, d2 = _d1_d2(S, K, r, q, sigma, T)
    if option_type == OptionType.CALL:
        return _norm_cdf(d2)
    return _norm_cdf(-d2)
