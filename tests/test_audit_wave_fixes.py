"""Behavior pins for the 2026-07-17 audit-wave implementation (opts-audit-wave{0,1,2,3}-*-v1,
docs/AUDIT_2026-07-16_options_platform.md). One compact pin per NEW mechanism not already
covered by the repinned legacy suites."""

from __future__ import annotations

import json
from datetime import date

from atlas.options import lanes as olanes
from atlas.options import shadow as oshadow
from atlas.options.session_calendar import (HALF_DAYS_2026_FALLBACK, HOLIDAYS_2026_FALLBACK,
                                            is_trading_day, nyse_half_days, nyse_holidays)
from scripts.grade_options_shadow import eprocess_wealth


# --------------------------------------------------------------------- calendar (Wave 3.20)
def test_calendar_algorithmic_reproduces_2026_and_covers_2027():
    # the generator must reproduce the published 2026 tables EXACTLY (the pinned reference)...
    assert nyse_holidays(2026) == set(HOLIDAYS_2026_FALLBACK)
    assert nyse_half_days(2026) == HALF_DAYS_2026_FALLBACK
    # ...and the 2027 rollover no longer silently classifies New Year's Day as a session
    assert is_trading_day(date(2027, 1, 1), days={}) is False       # Friday, NYSE closed
    assert is_trading_day(date(2027, 1, 4), days={}) is True
    assert "2027-03-26" in nyse_holidays(2027)                      # Good Friday via computus
    assert "2027-07-05" in nyse_holidays(2027)                      # July 4 observed (Sunday)


# --------------------------------------------------------------------- lane latch (Wave 1.11)
def test_lane_latch_release_and_confirm():
    prof = olanes.NoiseProfile(symbol="SPY", minutes=(570, 600), noise_by_minute=(0.001, 0.001),
                               remaining_range_by_minute=(0.008, 0.006), avg_daily_range=0.008,
                               range_percentile_14d=80.0, avg_first5_volume=1e6, n_days=14)
    lane = olanes.IndexTrendLane({"SPY": prof})

    def bar(minute):
        return olanes.MinuteCtx(symbol="SPY", minute=minute, open=100.4, high=100.6, low=100.3,
                                close=100.5, volume=1000.0, session_open=100.0, svwap=100.2)

    sig = lane.update(bar(599))                                     # 5-min boundary, beyond band
    assert sig is not None
    assert lane.update(bar(604)) is None                            # pending guard holds
    lane.release("SPY", "call", 604)                                # selector rejected the fire
    assert lane.update(bar(609)) is None                            # cooldown (30 min) holds
    resig = lane.update(bar(634))                                   # predicate persists -> re-arm
    assert resig is not None and resig.lane == "index_trend"
    lane.confirm_entry("SPY", "call")                               # a real entry latches the day
    assert lane.update(bar(659)) is None


# --------------------------------------------------------------------- frozen band (Wave 2.13)
def test_invalidation_uses_frozen_band_with_hysteresis():
    prof = olanes.NoiseProfile(symbol="SPY", minutes=(570, 700), noise_by_minute=(0.002, 0.009),
                               remaining_range_by_minute=(0.008, 0.005), avg_daily_range=0.008,
                               range_percentile_14d=80.0, avg_first5_volume=1e6, n_days=14)
    lane = olanes.IndexTrendLane({"SPY": prof})
    # +0.55% move, entry-frozen band 0.5%: OUTSIDE 0.8*frozen (0.4%) -> thesis stands, even
    # though the GROWN band at minute 700 (0.9%) would have swallowed it under the old rule
    ok = olanes.PositionCtx(symbol="SPY", direction="call", minute=700, close=100.55,
                            svwap=100.2, session_open=100.0, frozen_band=0.005)
    assert lane.invalidated(ok) is False
    # +0.35% move: inside 0.8*frozen -> invalid (the hysteresis threshold, not the raw band)
    back = olanes.PositionCtx(symbol="SPY", direction="call", minute=700, close=100.35,
                              svwap=100.2, session_open=100.0, frozen_band=0.005)
    assert lane.invalidated(back) is True


# --------------------------------------------------------------------- e-process (Wave 0.2)
def test_eprocess_wealth_math_and_bounds():
    assert eprocess_wealth([]) == 1.0
    # hand-computed single bet, R=+1.0: mean over lambdas of (1+lambda) = 1 + mean(lambdas)
    assert abs(eprocess_wealth([1.0]) - (1.0 + (0.05 + 0.10 + 0.20) / 3.0)) < 1e-12
    # a total loss (R=-1) can never zero the wealth (1 - lambda > 0 for the whole grid)
    w = eprocess_wealth([-1.0] * 10)
    assert 0.0 < w < 1.0
    # the single-bet cap: a +1000% fluke counts as +200%
    assert eprocess_wealth([10.0]) == eprocess_wealth([2.0])
    # a genuine positive stream grows wealth monotonically past the pilot threshold
    stream = [0.5] * 40
    assert eprocess_wealth(stream) > 5.0


# --------------------------------------------------------------------- torn tail (SL-2)
def test_append_jsonl_repairs_torn_tail(tmp_path):
    p = tmp_path / "led.jsonl"
    p.write_text('{"a": 1}\n{"torn": ', encoding="utf-8")           # crash mid-line, no newline
    oshadow.append_jsonl(p, {"b": 2})
    rows = oshadow.read_jsonl(p)
    assert {"a": 1} in rows and {"b": 2} in rows                    # torn fragment quarantined
    assert len(rows) == 2


def test_read_jsonl_strict_raises_on_unreadable(tmp_path):
    d = tmp_path / "is_a_dir.jsonl"
    d.mkdir()                                                       # exists but unreadable
    assert oshadow.read_jsonl(d) == []                              # tolerant path unchanged
    try:
        oshadow.read_jsonl(d, strict=True)
        raise AssertionError("strict read must raise LedgerUnreadable")
    except oshadow.LedgerUnreadable:
        pass


# --------------------------------------------------------------------- occ expiry helper
def test_occ_expiry_parse():
    from scripts.run_options_shadow import _occ_expiry
    assert _occ_expiry("IWM260715P00293000") == date(2026, 7, 15)
    assert _occ_expiry("NVDA260720P00210000") == date(2026, 7, 20)
    assert _occ_expiry("FAKE") is None
