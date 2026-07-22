"""Tradier data client tests - pure parsers against recorded-shape fixtures (no network), the
single-element-collapse quirk, config-absent degradation, and the Guardian alt-quote fallback."""

import pytest

from atlas.collect.tradier_data import (
    TQuote,
    TradierData,
    parse_daily_history,
    parse_quotes_batch,
    parse_timesales,
)


def test_parse_quotes_batch_multi_and_fields():
    payload = {"quotes": {"quote": [
        {"symbol": "AAPL", "last": 308.63, "bid": 308.44, "ask": 308.47,
         "prevclose": 307.1, "volume": 75400626, "average_volume": 53591689, "low": 305.86},
        {"symbol": "FRT", "last": 121.69, "bid": 121.03, "ask": 122.64,
         "prevclose": 121.0, "volume": 768432, "average_volume": 965312},
    ]}}
    out = parse_quotes_batch(payload)
    assert set(out) == {"AAPL", "FRT"}
    q = out["AAPL"]
    assert q.bid == 308.44 and q.ask == 308.47 and q.volume == 75400626
    assert q.rvol_day == pytest.approx(75400626 / 53591689)
    # Session low feeds the SSR self-compute; omitted -> 0.0 (=> ssr_active stays False).
    assert q.low == 305.86 and out["FRT"].low == 0.0


def test_parse_quotes_batch_single_element_collapse_and_missing_last():
    # Tradier collapses a 1-element array to an object; a missing/zero last falls back to close.
    payload = {"quotes": {"quote": {"symbol": "spy", "last": 0, "close": 744.78,
                                    "bid": 744.6, "ask": 744.9}}}
    out = parse_quotes_batch(payload)
    assert out["SPY"].last == 744.78
    assert out["SPY"].rvol_day is None            # no average_volume -> unknown, never fabricated


def test_parse_quotes_batch_empty_and_junk_safe():
    assert parse_quotes_batch({}) == {}
    assert parse_quotes_batch({"quotes": {"quote": [{"last": 5.0}]}}) == {}  # no symbol -> dropped


def test_parse_timesales_orders_and_vwap():
    payload = {"series": {"data": [
        {"time": "2026-07-02T09:30:00", "open": 747.4, "high": 747.93, "low": 747.1,
         "close": 747.86, "volume": 485434, "price": 747.515},
    ]}}
    bars = parse_timesales(payload)
    assert len(bars) == 1 and bars[0].vwap == pytest.approx(747.515)
    assert parse_timesales({"series": None}) == []   # closed day / empty session


def test_parse_daily_history_sorted():
    payload = {"history": {"day": [
        {"date": "2026-07-02", "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 10},
        {"date": "2026-07-01", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 5},
    ]}}
    bars = parse_daily_history(payload)
    assert [b.ts for b in bars] == ["2026-07-01", "2026-07-02"]


def test_from_local_config_absent_returns_none(tmp_path):
    assert TradierData.from_local_config(tmp_path / "nope.yaml") is None
    (tmp_path / "empty.yaml").write_text("token: ''\n", encoding="utf-8")
    assert TradierData.from_local_config(tmp_path / "empty.yaml") is None


# test_guardian_alt_quotes_used_and_falls_back MOVED to attic\tests\test_guardian_alt_quotes.py
# (2026-07-10 pivot: it exercises the ARCHIVED equity Guardian, not Tradier parsing)
