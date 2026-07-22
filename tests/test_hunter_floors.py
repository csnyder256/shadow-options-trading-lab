"""FLOOR MAP tests (P1a) - incl. the PEEK-DETECTOR: poisoned future bars must not change the map.

The peek test is the anti-fooling keystone from the overhaul plan: every floor must be computable
from data available at stalk time. Any new level family that fails it cannot ship.
"""

from __future__ import annotations

import numpy as np

from atlas.hunter.floors import (DemandZone, FloorMap, FloorParams, _round_levels,
                                 build_floor_map)

OPEN_MIN = 9 * 60 + 30


def _mod(n: int) -> np.ndarray:
    return np.arange(OPEN_MIN, OPEN_MIN + n)


def _flat_then_rise(n_flat: int = 90, n_rise: int = 10) -> dict:
    """Morning value area ~10.60 (VWAP + prior-day levels confluent), then a push to ~10.90 and a
    pullback to 10.75 - a canonical 'stalk the retest of value' tape."""
    n = n_flat + n_rise
    close = np.concatenate([np.full(n_flat, 10.60), np.linspace(10.65, 10.90, n_rise // 2),
                            np.linspace(10.88, 10.75, n_rise - n_rise // 2)])
    open_ = np.concatenate([[10.60], close[:-1]])
    high = close + 0.02
    low = np.concatenate([np.full(n_flat, 10.58), close[n_flat:] - 0.02])
    volume = np.full(n, 1000.0)
    return dict(open_=open_, high=high, low=low, close=close, volume=volume,
                minute_of_day=_mod(n),
                prior_day={"high": 10.85, "low": 10.58, "close": 10.62})


def test_confluent_value_zone_found_and_ranked():
    d = _flat_then_rise()
    fm = build_floor_map(**d, asof_idx=99)
    assert fm.zones, "expected at least one demand zone at the value area"
    z = fm.primary
    assert isinstance(z, DemandZone)
    # the value cluster must contain >=2 distinct families incl. the anchored VWAP + a prior-day level
    assert len(z.families) >= 2
    assert "avwap_catalyst" in z.families
    assert any(f.startswith("prior_day") for f in z.families)
    assert z.bottom < z.top <= 10.75 + fm.atr5m          # a DEMAND zone sits at/below price
    assert z.score >= FloorParams().zone_min_score
    # max_chase is anchored to the primary zone top
    assert np.isclose(fm.max_chase, z.top + FloorParams().max_chase_atr5m * fm.atr5m)


def test_peek_detector_future_bars_do_not_change_the_map():
    d = _flat_then_rise()
    asof = 95
    clean = build_floor_map(**d, asof_idx=asof)
    poisoned = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in d.items()}
    for key, junk in (("open_", 999.0), ("high", 1000.0), ("low", 0.01), ("close", 999.0),
                      ("volume", 9e9)):
        poisoned[key][asof + 1:] = junk
    dirty = build_floor_map(**poisoned, asof_idx=asof)
    assert clean == dirty, "future bars leaked into the floor map"


def test_or_low_family_only_after_the_30min_range_has_formed():
    d = _flat_then_rise()
    early = build_floor_map(**d, asof_idx=25)             # 09:55 - OR not formed yet
    late = build_floor_map(**d, asof_idx=95)              # 11:05 - formed
    early_fams = {f for z in early.zones for f in z.families}
    late_fams = {f for z in late.zones for f in z.families}
    assert "or_low_30m" not in early_fams
    assert "or_low_30m" in late_fams


def test_touch_counting_and_first_test_flag():
    d = _flat_then_rise()
    fm = build_floor_map(**d, asof_idx=99)
    z = fm.primary
    # the value zone traded all morning (one continuous excursion) => 1 touch, not a first test
    assert z.touches_today == 1
    assert z.first_test is False


def test_bear_regime_zone_below_both_vwaps_is_penalized():
    # steady decline: every candidate floor sits BELOW both VWAPs => -2 modifier keeps weak
    # two-family clusters out entirely
    n = 120
    close = np.linspace(12.0, 10.0, n)
    open_ = np.concatenate([[12.0], close[:-1]])
    high = close + 0.02
    low = close - 0.02
    volume = np.full(n, 1000.0)
    fm = build_floor_map(open_=open_, high=high, low=low, close=close, volume=volume,
                         minute_of_day=_mod(n), asof_idx=n - 1,
                         prior_day={"high": 10.10, "low": 9.95, "close": 10.05})
    for z in fm.zones:
        if z.below_both_vwaps:
            # survived despite the -2 => it had to be genuinely heavy confluence
            assert z.score >= FloorParams().zone_min_score
            assert len(z.families) >= 3


def test_retrace_frac_measures_the_catalyst_leg():
    n_up, n_dn = 50, 20
    close = np.concatenate([np.linspace(10.0, 11.0, n_up), np.linspace(11.0, 10.5, n_dn)])
    open_ = np.concatenate([[10.0], close[:-1]])
    high = close + 0.01
    low = close - 0.01
    volume = np.full(n_up + n_dn, 1000.0)
    fm = build_floor_map(open_=open_, high=high, low=low, close=close, volume=volume,
                         minute_of_day=_mod(n_up + n_dn), asof_idx=n_up + n_dn - 1)
    assert 0.45 <= fm.retrace_frac <= 0.55                # pulled back ~half the leg


def test_round_levels_grid_scales_with_price():
    assert 10.5 in _round_levels(10.74, 9.0, FloorParams())
    assert all(abs(x * 2 - round(x * 2)) < 1e-9 for x in _round_levels(15.3, 12.0, FloorParams()))
    lv50 = _round_levels(163.0, 120.0, FloorParams())
    assert 160.0 in lv50 and all(x % 5 == 0 for x in lv50)


def test_degenerate_inputs_never_raise():
    empty = np.array([])
    fm = build_floor_map(open_=empty, high=empty, low=empty, close=empty, volume=empty,
                         minute_of_day=np.array([], dtype=int), asof_idx=0)
    assert isinstance(fm, FloorMap) and fm.zones == ()
    one = np.array([10.0])
    fm1 = build_floor_map(open_=one, high=one, low=one, close=one, volume=one,
                          minute_of_day=_mod(1), asof_idx=0)
    assert fm1.zones == ()
    bad = np.array([np.nan, np.nan, np.nan, np.nan])
    fmb = build_floor_map(open_=bad, high=bad, low=bad, close=bad, volume=bad,
                          minute_of_day=_mod(4), asof_idx=3)
    assert fmb.zones == ()


def test_premarket_levels_only_when_provided():
    d = _flat_then_rise()
    without = build_floor_map(**d, asof_idx=99)
    with_pm = build_floor_map(**d, asof_idx=99, premarket={"high": 10.72, "low": 10.61})
    fams_without = {f for z in without.zones for f in z.families}
    fams_with = {f for z in with_pm.zones for f in z.families}
    assert "premarket_low" not in fams_without
    assert "premarket_low" in fams_with                    # 10.61 joins the value cluster
