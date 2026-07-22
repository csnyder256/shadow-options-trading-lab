"""Offline tests for atlas/collect/multi_news_source.py (mission 20260712, M3).

No network: the single HTTP seam `_fetch_json` is monkeypatched. Proves per-source fail-open,
macro (symbols==[]) tagging, provider-prefixed ids (no cross-source fingerprint collision),
cross-source dedup semantics, cadence gating + failure isolation, and - the regression gate - 
that build_multi_fetch(['benzinga']) is byte-identical to today's fetch_news.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import atlas.collect.multi_news_source as mns
from atlas.collect.benzinga_news import ET, NewsItem, _to_record, fetch_news

UTC = timezone.utc


def _dt(y=2026, mo=7, d=12, h=12, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=ET)


# --------------------------------------------------------------------------- Finnhub general

def test_finnhub_general_parses_and_tags_macro(monkeypatch):
    row = {"id": 999, "datetime": int(_dt().astimezone(UTC).timestamp()),
           "headline": "Fed holds rates steady", "summary": "body", "source": "Reuters",
           "url": "https://x/y"}
    monkeypatch.setattr(mns, "_fetch_json", lambda url, timeout=12.0: (200, [row], None))
    items, status, err = mns.fetch_finnhub_general("KEY")
    assert err is None and status == 200 and len(items) == 1
    it = items[0]
    assert it.symbols == []                       # MACRO: ticker-less
    assert it.id == "finnhub:999" and it.source == "finnhub"
    assert it.headline == "Fed holds rates steady"


def test_finnhub_general_no_key_is_fail_open():
    items, status, err = mns.fetch_finnhub_general("")
    assert items == [] and err == "no_key"


def test_finnhub_general_http_error_is_fail_open(monkeypatch):
    monkeypatch.setattr(mns, "_fetch_json", lambda url, timeout=12.0: (429, None, "http 429"))
    items, status, err = mns.fetch_finnhub_general("KEY")
    assert items == [] and status == 429 and err == "http 429"


def test_finnhub_general_survives_non_dict_elements(monkeypatch):
    """Refute E8 regression: a list containing null/int/str must FAIL-OPEN (drop that element),
    never raise, and must NOT discard the good items in the same poll."""
    ts = int(_dt().astimezone(UTC).timestamp())
    rows = [{"id": 1, "datetime": ts, "headline": "good one"},
            None, 42, "junk",
            {"id": 2, "datetime": ts, "headline": "good two"}]
    monkeypatch.setattr(mns, "_fetch_json", lambda url, timeout=12.0: (200, rows, None))
    items, status, err = mns.fetch_finnhub_general("KEY")     # must not raise
    assert err is None and [i.id for i in items] == ["finnhub:1", "finnhub:2"]
    # the pure parser is total on garbage too
    assert mns._finnhub_item(None, []) is None
    assert mns._finnhub_item(42, []) is None


def test_finnhub_company_survives_non_dict_elements(monkeypatch):
    ts = int(_dt().astimezone(UTC).timestamp())
    monkeypatch.setattr(mns, "_fetch_json",
                        lambda url, timeout=12.0: (200, [None, {"id": 3, "datetime": ts, "headline": "h"}], None))
    items, status, err = mns.fetch_finnhub_company("KEY", ["AAPL"], _dt(h=9), _dt(h=12))
    assert [i.id for i in items] == ["finnhub:3"] and items[0].symbols == ["AAPL"]


def test_finnhub_general_drops_rows_without_id_or_ts(monkeypatch):
    rows = [{"headline": "no id"},
            {"id": 1, "datetime": 0, "headline": "bad ts"},
            {"id": 2, "datetime": int(_dt().astimezone(UTC).timestamp()), "headline": "ok"}]
    monkeypatch.setattr(mns, "_fetch_json", lambda url, timeout=12.0: (200, rows, None))
    items, _, _ = mns.fetch_finnhub_general("KEY")
    assert [i.id for i in items] == ["finnhub:2"]


# --------------------------------------------------------------------------- Finnhub company

def test_finnhub_company_tags_queried_symbol(monkeypatch):
    row = {"id": 55, "datetime": int(_dt().astimezone(UTC).timestamp()),
           "headline": "AAPL ships thing", "summary": "", "source": "PR", "url": "https://a"}
    monkeypatch.setattr(mns, "_fetch_json", lambda url, timeout=12.0: (200, [row], None))
    items, status, err = mns.fetch_finnhub_company("KEY", ["AAPL"], _dt(h=9), _dt(h=12))
    assert len(items) == 1 and items[0].symbols == ["AAPL"] and items[0].id == "finnhub:55"


def test_finnhub_company_empty_symbols_is_noop():
    items, status, err = mns.fetch_finnhub_company("KEY", [], _dt(), _dt())
    assert items == [] and status is None and err is None


# --------------------------------------------------------------------------- GDELT

def test_gdelt_parses_macro(monkeypatch):
    art = {"url": "https://news/hormuz", "title": "Iran threatens to close Strait of Hormuz",
           "seendate": "20260712T031500Z", "domain": "reuters.com"}
    monkeypatch.setattr(mns, "_fetch_json", lambda url, timeout=15.0: (200, {"articles": [art]}, None))
    items, status, err = mns.fetch_gdelt(mns.DEFAULT_GDELT_QUERY, _dt(h=0), _dt(h=12))
    assert err is None and len(items) == 1
    it = items[0]
    assert it.symbols == [] and it.source == "gdelt" and it.id.startswith("gdelt:")
    assert it.summary == "" and "Hormuz" in it.headline


def test_gdelt_non_dict_response_is_fail_open(monkeypatch):
    monkeypatch.setattr(mns, "_fetch_json", lambda url, timeout=15.0: (200, "<html>err</html>", None))
    items, status, err = mns.fetch_gdelt("q", _dt(), _dt())
    assert items == [] and err == "non_dict_response"


def test_gdelt_drops_articles_without_url_or_ts(monkeypatch):
    arts = [{"title": "no url", "seendate": "20260712T031500Z"},
            {"url": "https://a", "title": "bad ts", "seendate": "garbage"},
            {"url": "https://b", "title": "ok", "seendate": "20260712T031500Z"}]
    monkeypatch.setattr(mns, "_fetch_json", lambda url, timeout=15.0: (200, {"articles": arts}, None))
    items, _, _ = mns.fetch_gdelt("q", _dt(), _dt())
    assert [i.url for i in items] == ["https://b"]


# --------------------------------------------------------------------------- normalization + dedup

def test_normalize_headline_collapses_variants():
    a = mns._normalize_headline("Fed Holds Rates Steady, Markets React!")
    b = mns._normalize_headline("fed   holds  rates - steady markets react")
    assert a == b
    assert mns._normalize_headline("Apple beats earnings") != a


def test_cross_source_dedup_drops_other_source_keeps_same_source():
    d = mns.CrossSourceDedup()
    ts = _dt().isoformat()
    bz = NewsItem("b1", ts, "Iran closes Strait of Hormuz today", "", [], "benzinga", "u1")
    fh = NewsItem("finnhub:2", ts, "Iran closes Strait of Hormuz today", "", [], "finnhub", "u2")
    bz2 = NewsItem("b2", ts, "Iran closes Strait of Hormuz today", "", [], "benzinga", "u3")
    other = NewsItem("b3", ts, "Apple raises full year guidance now", "", ["AAPL"], "benzinga", "u4")
    assert d.admit(bz) is True          # first occurrence: admitted, owner=benzinga
    assert d.admit(fh) is False         # same story from a DIFFERENT source -> dropped
    assert d.admit(bz2) is True         # distinct same-source item sharing the lede -> NOT clobbered
    assert d.admit(other) is True       # genuinely different story -> admitted


# --------------------------------------------------------------------------- schema + fingerprint

def test_macro_record_keeps_canonical_8_key_schema():
    art = {"url": "https://n/1", "title": "OPEC cuts output", "seendate": "20260712T031500Z"}
    it = mns._gdelt_item(art)
    rec = _to_record(it)
    assert set(rec) == {"id", "ts", "headline", "summary", "symbols", "source", "url", "fingerprint"}
    assert rec["symbols"] == []          # macro rows carry empty symbols -> consumer routes to macro sink


def test_no_cross_source_fingerprint_collision():
    ts = _dt().isoformat()
    benz = NewsItem("12345", ts, "h", "", [], "benzinga", "u")          # raw id, unchanged
    finn = NewsItem("finnhub:12345", ts, "h", "", [], "finnhub", "u")   # provider-prefixed
    assert benz.fingerprint != finn.fingerprint


# --------------------------------------------------------------------------- build_multi_fetch + wrapper

def test_build_multi_fetch_benzinga_only_is_identity():
    assert mns.build_multi_fetch(["benzinga"]) is fetch_news
    assert mns.build_multi_fetch(["benzinga", "finnhub"]) is not fetch_news


class _Clock:
    def __init__(self, start): self.t = start
    def __call__(self): return self.t
    def advance(self, secs): self.t = self.t + timedelta(seconds=secs)


def test_multifetcher_merges_dedups_and_gates_cadence(monkeypatch):
    clock = _Clock(_dt(h=12, mi=0))
    gdelt_art = {"url": "https://g/1", "title": "Sanctions escalate globally",
                 "seendate": "20260712T160000Z"}
    fh_row = {"id": 7, "datetime": int(_dt(h=12).astimezone(UTC).timestamp()),
              "headline": "Central bank surprise", "summary": "", "source": "AP", "url": "https://f/1"}

    def fake_fetch_json(url, timeout=12.0):
        if "gdeltproject" in url:
            return 200, {"articles": [gdelt_art]}, None
        if "company-news" in url:
            return 200, [], None
        if "finnhub.io/api/v1/news" in url:
            return 200, [fh_row], None
        return None, None, "unexpected"

    monkeypatch.setattr(mns, "_fetch_json", fake_fetch_json)
    bz_item = NewsItem("b1", _dt(h=12).isoformat(), "Some ticker news", "", ["SPY"], "benzinga", "u")
    f = mns.MultiNewsFetcher(sources=["benzinga", "finnhub", "gdelt"], api_key="K",
                             benzinga_fetch=lambda *a, **k: [bz_item], now_fn=clock)

    first = f(None, _dt(h=11), _dt(h=12), limit=200)
    srcs = {i.source for i in first}
    assert srcs == {"benzinga", "finnhub", "gdelt"}          # all three merged on first tick
    assert f._health["finnhub"]["consecutive_failures"] == 0
    assert f._health["gdelt"]["consecutive_failures"] == 0
    # benzinga health is tracked too (so a silent Benzinga - the original incident - is visible),
    # with http_status None (the alpaca SDK doesn't expose it)
    assert f._health["benzinga"]["items_last_poll"] == 1
    assert f._health["benzinga"]["http_status"] is None

    clock.advance(5)                                          # <60s: finnhub/gdelt NOT due
    second = f(None, _dt(h=12), _dt(h=12, mi=1), limit=200)
    assert {i.source for i in second} == {"benzinga"}         # only benzinga polls every tick


def test_multifetcher_isolates_a_failing_source(monkeypatch):
    clock = _Clock(_dt(h=12))
    fh_row = {"id": 8, "datetime": int(_dt(h=12).astimezone(UTC).timestamp()),
              "headline": "Inflation prints hot", "summary": "", "source": "AP", "url": "https://f/2"}

    def fake_fetch_json(url, timeout=12.0):
        if "gdeltproject" in url:
            return None, None, "timeout"                      # GDELT down
        if "company-news" in url:
            return 200, [], None
        return 200, [fh_row], None                            # finnhub general fine

    monkeypatch.setattr(mns, "_fetch_json", fake_fetch_json)
    f = mns.MultiNewsFetcher(sources=["finnhub", "gdelt"], api_key="K", now_fn=clock)
    out = f(None, _dt(h=11), _dt(h=12), limit=200)
    assert {i.source for i in out} == {"finnhub"}             # gdelt failure isolated
    assert f._health["gdelt"]["consecutive_failures"] == 1
    assert f._health["gdelt"]["last_error"] == "timeout"
    assert f._health["finnhub"]["consecutive_failures"] == 0


def test_multifetcher_writes_sidecar_heartbeat(tmp_path, monkeypatch):
    monkeypatch.setattr(mns, "_fetch_json", lambda url, timeout=12.0: (200, [], None))
    hb = tmp_path / "news_sources_heartbeat.json"
    f = mns.MultiNewsFetcher(sources=["finnhub"], api_key="K", heartbeat_path=hb,
                             now_fn=lambda: _dt(h=12))
    f(None, _dt(h=11), _dt(h=12), limit=200)
    import json
    data = json.loads(hb.read_text(encoding="utf-8"))
    assert data["schema"] == 2 and "finnhub" in data["sources"]
    assert data["sources"]["finnhub"]["http_status"] == 200
