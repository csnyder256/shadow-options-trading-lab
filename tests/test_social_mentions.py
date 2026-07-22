"""Mention tap pure logic (opts-svc-mention-tap-v1): extraction discipline + honest z-math."""

from __future__ import annotations

from atlas.collect.social_mentions import (MIN_BASELINE_DAYS, acceleration_z, bucket_key,
                                           bucket_of_day, extract_symbols, merge_bucket)

UNIVERSE = frozenset({"NVDA", "AMD", "TSLA", "F", "GME", "IV", "ALL", "SPY"})


def test_cashtags_bypass_blacklist_bare_tokens_do_not():
    text = "YOLO on $F and $IV - ALL in, also NVDA calls and CALLS on AMD"
    got = extract_symbols(text, UNIVERSE)
    assert "F" in got and "IV" in got            # cashtag = explicit intent, even 1-letter/blacklisted
    assert "NVDA" in got and "AMD" in got        # bare tokens in universe, not blacklisted
    assert "ALL" not in got                      # blacklisted bare token stays out
    assert "CALLS" not in got                    # slang never extracted


def test_extract_dedups_ignores_unknown_and_caps():
    text = "$NVDA NVDA $nvda $FAKE " + " ".join(f"$X{i}" for i in range(30))
    got = extract_symbols(text, UNIVERSE)
    assert got == ["NVDA"]                       # dedup + unknown-symbol drop
    spam = " ".join(f"${s}" for s in UNIVERSE) + " " + " ".join(f"${s}" for s in UNIVERSE)
    assert len(extract_symbols(spam * 3, frozenset(f"S{i}" for i in range(40)))) == 0


def test_acceleration_z_refuses_thin_baseline():
    assert acceleration_z(10, [1] * (MIN_BASELINE_DAYS - 1)) is None
    acc = acceleration_z(10, [1, 1, 2, 1, 1])
    assert acc is not None and acc["n_days"] == 5 and acc["flag"] is True and acc["z"] >= 3.0
    quiet = acceleration_z(1, [1, 1, 2, 1, 1])
    assert quiet is not None and quiet["flag"] is False


def test_acceleration_z_zero_variance_honest():
    same = acceleration_z(3, [3, 3, 3, 3, 3])
    assert same is not None and same["flag"] is False        # count == mean, sd 0 -> z 0
    burst = acceleration_z(9, [3, 3, 3, 3, 3])
    assert burst is not None and burst["flag"] is True       # above a flat baseline -> inf-capped


def test_bucketing_and_merge():
    ts = 1_800_000_000.0
    assert bucket_key(ts) % 300 == 0 and bucket_key(ts) <= ts < bucket_key(ts) + 300
    assert 0 <= bucket_of_day(ts, tz_offset_s=-4 * 3600) < 288
    rows = merge_bucket({"NVDA": {"reddit": 3, "stocktwits_trend": 1}, "AMD": {"reddit": 1},
                         "GHOST": {"reddit": 0}})
    assert [r["symbol"] for r in rows] == ["NVDA", "AMD"]    # zero-count dropped, sorted desc
    assert rows[0]["count"] == 4 and rows[0]["sources"]["reddit"] == 3
