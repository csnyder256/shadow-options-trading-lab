"""Price-action CORE (atlas/signals/price_action.py) - the buy-low / sell-high rebuild (M4).

Proves: a supported DIP-in-uptrend scores high and PASSES; a fresh-high PEAK is vetoed (extended_above_mean,
score 0 - the 7/7 pattern); the core is SCALE-FREE (a 600x BTC-scaled dip yields the IDENTICAL signal - the
'trade crypto blindly' litmus); the three new features are CAUSAL (value at t on the full array == value on
the trailing window close[:t+1], which is exactly the live-vs-backtest parity guarantee); and it never raises
on short/degenerate input. Early-wave threshold calibration is deferred to M7's backtest on real trends."""

import numpy as np

from atlas.signals import features as F
from atlas.signals.price_action import PriceActionParams, score_buy_low, swing_lows


# --- crafted generators (tuned; see scratch iteration in the M4 journal) -------------------------------
def _dip(scale: float = 1.0):
    """Long-term uptrend (above SMA200), currently CHOPPING (range regime, low ADX) with a support shelf ~95;
    a final oversold slide (RSI-2 << 10) ends in a green reclaim hammer whose low tests support."""
    n = 260
    c = np.empty(n)
    c[:200] = np.linspace(68.0, 96.0, 200)
    t = np.arange(200, 254)
    c[200:254] = 96.6 + 1.7 * np.sin((t - 200) * 0.9)             # consolidation -> low ADX/ER + swing lows ~95
    c[254:260] = np.array([96.8, 96.5, 96.2, 95.9, 95.6, 95.3])   # monotone-down slide -> RSI2 << 10
    c *= scale
    op = c - 0.10 * scale
    hi = np.maximum(c, op) + 0.30 * scale
    lo = np.minimum(c, op) - 0.30 * scale
    op[-1] = 94.70 * scale; lo[-1] = 94.60 * scale; hi[-1] = 95.60 * scale   # green reclaim, low tests support
    vol = np.full(n, 1_000_000.0); vol[-1] = 1_600_000.0
    return op, hi, lo, c, vol


def _peak(scale: float = 1.0):
    """Accelerating run into a FRESH high - price far above its mean (the extended chase that lost 7/7)."""
    n = 260
    c = np.concatenate([np.linspace(50, 90, 250), np.linspace(90, 100, 10)]) * scale
    op = c - 0.1 * scale; hi = c + 0.3 * scale; lo = c - 0.3 * scale
    op[-1] = 99.4 * scale; lo[-1] = 99.2 * scale; hi[-1] = 100.1 * scale
    vol = np.full(n, 1_000_000.0); vol[-1] = 3_000_000.0
    return op, hi, lo, c, vol


def test_supported_dip_passes_and_scores_high():
    sig = score_buy_low(*_dip())
    assert sig.passed is True
    assert sig.archetype == "supported_dip"
    assert sig.reason == "dip_at_support_reclaim"
    assert sig.regime == "range"
    assert sig.score >= 0.40                      # a real buy-low, vs the peak's 0.0
    assert sig.support_families >= 2              # strongly supported (>=2 independent families)
    assert sig.stop is not None and sig.stop < sig.support    # structural stop below support (defines R for M6)
    assert sig.rsi2 < 10.0 and sig.extension < 1.5            # oversold + NOT extended


def test_supported_dip_emits_sell_high_target():
    # M6: the CORE publishes the sell-high level = max(mean EMA21, entry + 1*ATR). It must sit ABOVE entry
    # (a real move to book) and be NEAR (a not-extended dip's mean is <= 1.5*ATR up), so it fires intraday
    # instead of riding to a far backstop. This is the level the risk engine turns into the take-profit.
    o, h, l, c, v = _dip()
    sig = score_buy_low(o, h, l, c, v)
    entry = float(c[-1])
    atr = float(F.atr(np.asarray(h, float), np.asarray(l, float), np.asarray(c, float), 14)[-1])
    ema = float(F.ema(np.asarray(c, float), 21)[-1])
    assert sig.target is not None
    assert sig.target > entry                                  # a genuine sell-HIGH, above the fill
    assert abs(sig.target - max(ema, entry + atr)) < 1e-4      # exactly max(mean, entry+1*ATR)
    assert sig.target - entry <= 1.5 * atr + 1e-6              # NEAR (reachable) - not a far backstop
    assert sig.target > sig.support                            # target above the support the stop sits under


def test_fresh_high_peak_is_vetoed():
    sig = score_buy_low(*_peak())
    assert sig.passed is False
    assert sig.score == 0.0
    assert sig.reason == "extended_above_mean"    # the keystone anti-peak veto (same rule as the M3 context gate)
    assert sig.extension >= 1.5


def test_crypto_litmus_is_scale_free():
    # The SAME dip at $95 and at $57,000 (BTC-scale) must yield the identical signal - the core is OHLCV-only
    # and every feature is scale-free, so it would trade crypto blindly.
    small = score_buy_low(*_dip(1.0))
    btc = score_buy_low(*_dip(600.0))
    assert btc.archetype == small.archetype == "supported_dip"
    assert btc.passed is True
    assert abs(btc.score - small.score) < 1e-9    # identical score across a 600x price scale
    assert abs(btc.rsi2 - small.rsi2) < 1e-6 and abs(btc.extension - small.extension) < 1e-6
    # the sell-high target + stop are PRICE levels -> scale-COVARIANT (scale ~600x), so the exit bracket the
    # risk engine builds from them is identical in R terms on a $95 stock and $57k BTC. (Tol 1e-5, not the
    # 1e-6 used for the dimensionless features: a 6-decimal ROUND is absolute, and ATR/support float error
    # doesn't perfectly cancel across a 600x rescale - 5 sig-figs still proves covariance; a bug is gross.)
    assert abs(btc.target / small.target - 600.0) < 1e-5
    assert abs(btc.stop / small.stop - 600.0) < 1e-5


def test_new_features_are_causal_backtest_parity():
    # A feature is causal iff its value at t depends only on data <= t. That is EXACTLY the guarantee that the
    # backtest's O(n) sliced series equals the live engine's trailing-window recompute at every bar - the
    # 'features_fast == features' parity P1 flagged. Assert it for the three M4 additions on a real series.
    _, _, _, c, _ = _dip()
    for fn in (F.rsi2, lambda x: F.pct_b(x, 20, 2.0), lambda x: F.efficiency_ratio(x, 10)):
        full = fn(c)
        for t in (120, 200, 259):                 # a few bars incl. the last
            trailing = fn(c[:t + 1])[-1]
            a, b = full[t], trailing
            assert (np.isnan(a) and np.isnan(b)) or abs(a - b) < 1e-9, f"non-causal at t={t}"


def test_swing_lows_are_strict_fractal_pivots():
    low = np.array([5, 4, 3, 4, 5, 4, 2, 4, 6], dtype=float)   # strict pivot lows at idx 2 (=3) and 6 (=2)
    assert swing_lows(low, 2) == [2, 6]
    assert swing_lows(np.array([5, 5, 5, 5, 5], dtype=float), 2) == []   # flat: no strict pivot


def test_short_history_and_degenerate_never_raise():
    tiny = (np.ones(10), np.ones(10), np.ones(10), np.ones(10), np.ones(10))
    s = score_buy_low(*tiny)
    assert s.passed is False and s.reason == "short_history"
    flat = [np.full(260, 50.0)] * 4 + [np.full(260, 1_000_000.0)]        # zero ATR
    s2 = score_buy_low(*flat)
    assert s2.passed is False and s2.reason == "no_atr"                  # degenerate -> safe no-trigger


def test_params_are_wide_basin_defaults():
    p = PriceActionParams()
    assert p.dip_rsi_max == 10.0 and p.extension_veto_atr == 1.5 and p.min_support_families == 2
