"""Vendored options-math validation (2026-07-09, O1).

PORTED from the owner's options project (C:/path/to/options-project,
tests/test_blackscholes.py) with ONLY the import lines changed (app.engine/app.models ->
atlas.options.vendor.*). The test bodies are byte-identical to the originals - if one fails,
the vendoring broke the math. The source project has no dedicated pure-volatility test file
(only scoring-level coverage), so the volatility section below is ATLAS-ADDED sanity coverage
of the vendored functions the IV archive consumes (iv_rank / iv_percentile / realized vol /
atm_iv_from_pairs), clearly marked as additions rather than ports.
"""

import math
from datetime import date, timedelta

import pytest

from atlas.options.vendor import blackscholes as bs
from atlas.options.vendor import volatility as vol
from atlas.options.vendor.models import OHLC, OptionType

# --------------------------------------------------------------------------- #
# PORTED VERBATIM from tests/test_blackscholes.py (imports aside).
# --------------------------------------------------------------------------- #


def test_call_put_textbook():
    # Hull, Options Futures and Other Derivatives: S=42,K=40,r=10%,sigma=20%,T=0.5
    S, K, r, q, sigma, T = 42, 40, 0.10, 0.0, 0.20, 0.5
    call = bs.bs_price(S, K, r, q, sigma, T, OptionType.CALL)
    put = bs.bs_price(S, K, r, q, sigma, T, OptionType.PUT)
    assert call == pytest.approx(4.76, abs=0.01)
    assert put == pytest.approx(0.81, abs=0.01)


def test_put_call_parity():
    S, K, r, q, sigma, T = 100, 105, 0.03, 0.01, 0.25, 0.75
    call = bs.bs_price(S, K, r, q, sigma, T, OptionType.CALL)
    put = bs.bs_price(S, K, r, q, sigma, T, OptionType.PUT)
    lhs = call - put
    rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
    assert lhs == pytest.approx(rhs, abs=1e-9)


@pytest.mark.parametrize("sigma", [0.08, 0.15, 0.30, 0.65, 1.2])
@pytest.mark.parametrize("otype", [OptionType.CALL, OptionType.PUT])
def test_iv_roundtrip(sigma, otype):
    S, K, r, q, T = 100, 110, 0.04, 0.0, 0.4
    price = bs.bs_price(S, K, r, q, sigma, T, otype)
    iv = bs.implied_vol(price, S, K, r, q, T, otype)
    assert iv is not None
    assert iv == pytest.approx(sigma, abs=1e-4)


def test_iv_below_intrinsic_returns_none():
    # A call can't be worth less than its intrinsic value.
    S, K, r, q, T = 100, 80, 0.04, 0.0, 0.5
    assert bs.implied_vol(1.0, S, K, r, q, T, OptionType.CALL) is None


def test_greek_signs():
    S, K, r, q, sigma, T = 100, 100, 0.04, 0.0, 0.25, 0.5
    call = bs.greeks(S, K, r, q, sigma, T, OptionType.CALL)
    put = bs.greeks(S, K, r, q, sigma, T, OptionType.PUT)
    assert 0 < call.delta < 1
    assert -1 < put.delta < 0
    assert call.gamma > 0 and put.gamma > 0
    assert call.gamma == pytest.approx(put.gamma, abs=1e-12)  # gamma is side-agnostic
    assert call.vega > 0 and put.vega > 0
    assert call.theta < 0  # long ATM call bleeds time value
    assert call.rho > 0 and put.rho < 0


def test_prob_itm_monotonic_in_strike():
    # Higher strike -> lower probability a call finishes ITM.
    S, r, q, sigma, T = 100, 0.04, 0.0, 0.3, 0.5
    p_low = bs.prob_itm(S, 90, r, q, sigma, T, OptionType.CALL)
    p_high = bs.prob_itm(S, 120, r, q, sigma, T, OptionType.CALL)
    assert 0 <= p_high < p_low <= 1


# --------------------------------------------------------------------------- #
# ATLAS-ADDED volatility sanity tests (the source project shipped none that are
# pure-volatility). These pin exactly the behaviors the IV archive relies on.
# --------------------------------------------------------------------------- #


def _bars(closes):
    """Flat-gap OHLC bars from a close series (open = prior close)."""
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append(OHLC(day=date(2026, 1, 1) + timedelta(days=i), open=o,
                        high=max(o, c) * 1.005, low=min(o, c) * 0.995, close=c, volume=1e6))
        prev = c
    return out


def test_realized_vol_close_to_close_known_value():
    # Alternating +1%/-1% log-ish moves -> hand-computable stdev of log returns.
    closes = [100.0]
    for i in range(20):
        closes.append(closes[-1] * (1.01 if i % 2 == 0 else 0.99))
    hv = vol.realized_vol_close_to_close(closes, window=0)
    rets = vol.log_returns(closes)
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    assert hv == pytest.approx(sd * math.sqrt(vol.TRADING_DAYS), rel=1e-12)
    assert vol.realized_vol_close_to_close([100.0]) is None  # not enough data


def test_yang_zhang_positive_and_fallback_agrees_on_scale():
    closes = [100.0]
    for i in range(40):
        closes.append(closes[-1] * (1.0 + 0.012 * (((i % 5) - 2) / 2.0)))
    bars = _bars(closes)
    yz = vol.realized_vol_yang_zhang(bars, window=30)
    cc = vol.realized_vol_close_to_close(closes, window=30)
    assert yz is not None and yz > 0
    assert cc is not None and 0.2 < yz / cc < 5.0        # same order of magnitude
    assert vol.realized_vol_yang_zhang(bars[:2], window=30) is None  # needs ~3 days
    assert vol.hv_from_bars(bars, 30) == pytest.approx(yz)


def test_atm_iv_from_pairs_picks_nearest_valid_strike():
    pairs = [(95.0, 0.50), (100.0, None), (101.0, 0.30), (110.0, 0.20)]
    assert vol.atm_iv_from_pairs(100.4, pairs) == pytest.approx(0.30)  # None IV skipped
    assert vol.atm_iv_from_pairs(100.0, [(100.0, 0.0)]) is None        # non-positive IV skipped


def test_iv_rank_and_percentile_contract():
    history = [0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.24, 0.26, 0.30]
    assert vol.iv_rank(0.30, history) == pytest.approx(100.0)
    assert vol.iv_rank(0.10, history) == pytest.approx(0.0)
    assert vol.iv_rank(0.20, history) == pytest.approx(50.0)
    assert vol.iv_percentile(0.21, history) == pytest.approx(60.0)  # 6 of 10 below
    # Degenerate / warming-up guards.
    assert vol.iv_rank(0.20, history[:5]) is None                   # <10 samples
    assert vol.iv_rank(0.20, [0.2] * 12) is None                    # zero range
    assert vol.iv_percentile(None, history) is None
    assert vol.iv_vs_hv_ratio(0.3, 0.2) == pytest.approx(1.5)
    assert vol.iv_vs_hv_ratio(0.3, 0.0) is None
