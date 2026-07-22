"""Nightly intraday-cache refresh (opts-fix-noise-cache-refresh-v1) - pure-core tests.

merge_1min: idempotent dedupe + dtype/tz pinning (the cache is Alpaca IEX,
datetime64[us, America/New_York], float64 columns - parquet round-trips must stay
byte-stable). missing_sessions: only CLOSED trading sessions strictly after the
last cached bar, half days honored via the injected session-calendar mapping.
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from atlas.collect.intraday_data import merge_1min
from scripts.refresh_intraday_cache import missing_sessions

TZ = "America/New_York"


def _frame(ts: list[str], base: float = 100.0) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(t, tz=TZ) for t in ts]).as_unit("us")
    n = len(idx)
    return pd.DataFrame(
        {"open": [base] * n, "high": [base + 1] * n, "low": [base - 1] * n,
         "close": [base + 0.5] * n, "volume": [1000.0] * n}, index=idx)


def test_merge_dedupes_and_sorts():
    old = _frame(["2026-07-08 09:30", "2026-07-08 09:31", "2026-07-08 15:59"])
    new = _frame(["2026-07-08 15:59", "2026-07-09 09:30", "2026-07-09 09:31"], base=200.0)
    merged = merge_1min(old, new)
    assert len(merged) == 5
    assert merged.index.is_monotonic_increasing
    # overlap resolves to the NEW row (keep="last")
    assert merged.loc[pd.Timestamp("2026-07-08 15:59", tz=TZ), "close"] == 200.5


def test_merge_is_idempotent():
    old = _frame(["2026-07-08 09:30"])
    new = _frame(["2026-07-09 09:30", "2026-07-09 09:31"])
    once = merge_1min(old, new)
    twice = merge_1min(once, new)
    pd.testing.assert_frame_equal(once, twice)


def test_merge_pins_dtypes_and_unit():
    old = _frame(["2026-07-08 09:30"])
    new = _frame(["2026-07-09 09:30"])
    # perturb: nanosecond index + int volume must be normalized back to cache shape
    new.index = new.index.as_unit("ns")
    new["volume"] = new["volume"].astype("int64")
    merged = merge_1min(old, new)
    assert str(merged.index.dtype) == f"datetime64[us, {TZ}]"
    assert all(str(dt) == "float64" for dt in merged.dtypes)
    assert list(merged.columns) == ["open", "high", "low", "close", "volume"]


def test_merge_empty_new_is_noop():
    old = _frame(["2026-07-08 09:30"])
    assert merge_1min(old, pd.DataFrame()) is old


def test_missing_sessions_friday_evening_catches_up_two_days():
    # cache last bar Wed 07-08; Friday 20:00 ET -> Thu + Fri (the real first-run case)
    got = missing_sessions(date(2026, 7, 8), datetime(2026, 7, 10, 20, 0), days={})
    assert got == [date(2026, 7, 9), date(2026, 7, 10)]


def test_missing_sessions_weekend_is_noop_after_catchup():
    got = missing_sessions(date(2026, 7, 10), datetime(2026, 7, 11, 12, 0), days={})
    assert got == []


def test_missing_sessions_mid_session_excludes_today():
    # Friday 12:00 ET: today's session (close 960) still open -> only Thursday
    got = missing_sessions(date(2026, 7, 8), datetime(2026, 7, 10, 12, 0), days={})
    assert got == [date(2026, 7, 9)]


def test_missing_sessions_skips_closed_days_from_injected_calendar():
    days = {"2026-07-09": {"status": "closed"}}
    got = missing_sessions(date(2026, 7, 8), datetime(2026, 7, 10, 20, 0), days=days)
    assert got == [date(2026, 7, 10)]


def test_missing_sessions_half_day_close_honored():
    # 2026-11-27 half day closes 13:00 ET (fallback table); 11-26 is Thanksgiving.
    # 14:00 ET run (840 >= 780): the half day is closed -> included.
    got = missing_sessions(date(2026, 11, 25), datetime(2026, 11, 27, 14, 0), days={})
    assert got == [date(2026, 11, 27)]
    # 12:00 ET run (720 < 780): still trading -> excluded.
    got = missing_sessions(date(2026, 11, 25), datetime(2026, 11, 27, 12, 0), days={})
    assert got == []
