"""Indicator tests - reference values + invariants for the pure-numpy feature functions."""

import numpy as np
import pytest

from atlas.signals import features as F


def test_sma_reference():
    out = F.sma([1, 2, 3, 4, 5], 3)
    assert np.isnan(out[0]) and np.isnan(out[1])
    assert out[2] == pytest.approx(2.0)  # mean(1,2,3)
    assert out[4] == pytest.approx(4.0)  # mean(3,4,5)


def test_ema_of_constant_is_constant():
    out = F.ema([5.0] * 20, 5)
    assert out[-1] == pytest.approx(5.0)
    assert np.isnan(out[3]) and out[4] == pytest.approx(5.0)


def test_rsi_all_gains_is_100_and_bounded():
    out = F.rsi(np.arange(1.0, 30.0), 14)
    assert out[-1] == pytest.approx(100.0)
    valid = out[~np.isnan(out)]
    assert np.all((valid >= 0) & (valid <= 100))


def test_atr_constant_true_range():
    n = 20
    high = np.full(n, 11.0)
    low = np.full(n, 9.0)
    close = np.full(n, 10.0)
    out = F.atr(high, low, close, 14)
    assert out[-1] == pytest.approx(2.0)


def test_vwap_constant_typical_price():
    n = 10
    high = np.full(n, 10.5)
    low = np.full(n, 9.5)
    close = np.full(n, 10.0)  # typical = 10.0 for all bars
    vol = np.arange(1.0, n + 1)
    out = F.vwap(high, low, close, vol)
    assert out[-1] == pytest.approx(10.0)


def test_vwap_rolling_reflects_recent_value_not_inception():
    # Regression guard for the 2026-06-29 fix: a *cumulative* (since-inception) VWAP on daily bars
    # reads ~15 here (avg of all 40 bars) while price is 20 -> every uptrend looks "extended above
    # VWAP". The rolling 20-bar VWAP must equal the recent value area (20.0), NOT 15.0.
    n = 40
    close = np.concatenate([np.full(20, 10.0), np.full(20, 20.0)])
    high, low = close + 0.5, close - 0.5            # typical price == close
    vol = np.full(n, 1000.0)
    out = F.vwap(high, low, close, vol, period=20)
    assert out[-1] == pytest.approx(20.0)
    assert out[-1] != pytest.approx(15.0)           # would be the inception-cumulative value


def test_bollinger_constant_has_zero_width():
    mid, upper, lower = F.bollinger([10.0] * 25, 20, 2.0)
    assert mid[-1] == pytest.approx(10.0)
    assert upper[-1] == pytest.approx(10.0)
    assert lower[-1] == pytest.approx(10.0)


def test_volume_zscore_spike():
    vol = np.array([100.0] * 19 + [300.0])
    out = F.volume_zscore(vol, 20)
    assert out[-1] == pytest.approx(4.3589, abs=1e-3)


def test_gap_pct():
    assert F.gap_pct(100.0, 102.0) == pytest.approx(2.0)
    assert F.gap_pct(100.0, 97.0) == pytest.approx(-3.0)


def test_relative_strength():
    close = np.linspace(100.0, 110.0, 11)  # +10% over 10 bars
    bench = np.full(11, 100.0)             # flat
    assert F.relative_strength(close, bench, 10) == pytest.approx(10.0)


def test_adx_strong_uptrend_is_high_and_bounded():
    n = 60
    close = 100.0 + np.arange(n) * 1.0
    high = close + 1.0
    low = close - 1.0
    out = F.adx(high, low, close, 14)
    last = out[-1]
    assert 0.0 <= last <= 100.0
    assert last > 50.0  # a clean monotonic trend has very high directional strength
