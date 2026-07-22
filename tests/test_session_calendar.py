"""Session calendar (late-close mode foundation): pure queries with injected days, the
Tradier calendar parser, fetch/cache/fallback tolerance, and the half-day/event-table
disjointness tripwire."""

from __future__ import annotations

import json
from datetime import date

from atlas.collect.tradier_data import parse_calendar
from atlas.options import events as oevents
from atlas.options import session_calendar as scal


def test_normal_day_defaults_without_any_data():
    d = date(2026, 7, 14)                                   # ordinary Tuesday, days={}
    assert scal.session_close_minute(d, days={}) == 960
    assert scal.options_close_minute(d, "SPY", days={}) == 975     # index ETF: +15 every day
    assert scal.options_close_minute(d, "XYZ", days={}) == 960
    assert scal.is_trading_day(d, days={}) is True
    assert scal.is_trading_day(date(2026, 7, 11), days={}) is False  # Saturday


def test_half_days_and_holidays_from_fallback_tables():
    assert scal.session_close_minute(date(2026, 11, 27), days={}) == 780
    assert scal.session_close_minute(date(2026, 12, 24), days={}) == 780
    assert scal.options_close_minute(date(2026, 11, 27), "QQQ", days={}) == 795
    assert scal.is_trading_day(date(2026, 11, 26), days={}) is False   # Thanksgiving
    assert scal.is_trading_day(date(2026, 7, 3), days={}) is False     # July 4th observed
    # injected days override the fallback (a fetched calendar wins)
    days = {"2026-11-27": {"status": "open", "close_min": 780},
            "2026-11-26": {"status": "closed"}}
    assert scal.session_close_minute(date(2026, 11, 27), days=days) == 780
    assert scal.is_trading_day(date(2026, 11, 26), days=days) is False


def test_half_days_disjoint_from_macro_event_tables():
    # tripwire: BLS/Fed never schedule releases on HALF sessions - if either table is ever
    # edited into a collision, the lane-3 blackout math needs a fresh look. Full holidays MAY
    # carry a print (2026-04-03 = Good Friday AND the April NFP - BLS publishes with the
    # market closed; the shadow isn't running, so it's benign and lane 3 simply never fires).
    event_dates = set(oevents.CPI_2026_FALLBACK) | set(oevents.NFP_2026_FALLBACK) | {
        d.isoformat() for d in oevents.FOMC_DECISION_DAYS_2026}
    assert not (set(scal.HALF_DAYS_2026_FALLBACK) & event_dates)
    assert set(scal.HOLIDAYS_2026_FALLBACK) & event_dates == {"2026-04-03"}  # known + benign


def test_parse_calendar_shapes():
    payload = {"calendar": {"days": {"day": [
        {"date": "2026-07-14", "status": "open", "open": {"start": "09:30", "end": "16:00"}},
        {"date": "2026-07-11", "status": "closed"},
        {"date": "2026-11-27", "status": "open", "open": {"start": "09:30", "end": "13:00"}},
        {"date": "", "status": "open"},                       # malformed -> skipped
    ]}}}
    days = parse_calendar(payload)
    assert days["2026-07-14"] == {"status": "open", "close_min": 960}
    assert days["2026-07-11"] == {"status": "closed"}
    assert days["2026-11-27"] == {"status": "open", "close_min": 780}
    assert len(days) == 3
    # single-element collapse (Tradier scalar-izes one-day responses)
    one = parse_calendar({"calendar": {"days": {"day":
        {"date": "2026-12-24", "status": "open", "open": {"start": "09:30", "end": "13:00"}}}}})
    assert one == {"2026-12-24": {"status": "open", "close_min": 780}}
    assert parse_calendar({}) == {}


class _FakeCalClient:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = 0

    def get_calendar(self, month: int, year: int) -> dict:
        self.calls += 1
        if self.fail:
            raise RuntimeError("calendar endpoint down")
        return {f"{year}-{month:02d}-01": {"status": "open", "close_min": 960}}


def test_refresh_calendar_cache_fetch_and_fallback(tmp_path):
    cache = tmp_path / "market_calendar.json"
    ok = _FakeCalClient()
    data = scal.refresh_calendar(client=ok, cache_path=cache, year=2026)
    assert data["source"] == "tradier" and ok.calls == 12 and len(data["days"]) == 12
    # fresh cache short-circuits (no second fetch)
    again = scal.refresh_calendar(client=ok, cache_path=cache, year=2026)
    assert ok.calls == 12 and again["source"] == "tradier"
    # fetch failure fails open to the fallback tables (and still writes the cache)
    bad_cache = tmp_path / "mc2.json"
    data2 = scal.refresh_calendar(client=_FakeCalClient(fail=True), cache_path=bad_cache,
                                  year=2026)
    assert data2["source"] == "fallback_nyse_2026"
    assert data2["days"]["2026-11-27"] == {"status": "open", "close_min": 780}
    assert bad_cache.exists()
    # corrupt cache JSON -> refetch, no crash
    bad_cache.write_text("{not json", encoding="utf-8")
    data3 = scal.refresh_calendar(client=ok, cache_path=bad_cache, year=2026)
    assert data3["source"] == "tradier"
    # no client + no cache -> pure fallback
    data4 = scal.refresh_calendar(client=None, cache_path=tmp_path / "mc3.json", year=2026)
    assert data4["source"] == "fallback_nyse_2026"
    assert json.loads((tmp_path / "mc3.json").read_text("utf-8"))["days"]