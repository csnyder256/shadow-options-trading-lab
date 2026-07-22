"""Offline tests for atlas/collect/benzinga_news.py - NO network anywhere.

The pagination tests rig a REAL alpaca-py NewsClient (dummy keys) whose HTTP layer
(RESTClient.get) is replaced with a fake page server, so the SDK's actual pagination loop is
exercised offline. Everything else uses fakes injected through the module's seams
(_client / fetch_news / NewsTap(fetch=...)).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

import pytest

from atlas.collect import benzinga_news as bz


ET = bz.ET


def _art(i, ts_utc, headline="Some Headline", summary="A summary.", syms=("AAPL",)):
    """Raw v1beta1/news article dict as the API returns it."""
    return {
        "id": i, "headline": headline, "author": "au", "created_at": ts_utc,
        "updated_at": ts_utc, "summary": summary, "content": "", "url": "https://bz.example/x",
        "symbols": list(syms), "source": "benzinga",
    }


def _item(i, ts, headline="h", summary="s", syms=("ABC",)):
    return bz.NewsItem(id=str(i), ts=ts, headline=headline, summary=summary,
                       symbols=list(syms), source="benzinga", url="https://bz.example/x")


# --------------------------------------------------------------------------- #
# NewsItem.fingerprint
# --------------------------------------------------------------------------- #

def test_fingerprint_is_stable_and_id_derived():
    a1 = _item(12345, "2026-07-09T09:31:00-04:00")
    a2 = _item(12345, "2026-07-09T10:00:00-04:00", headline="different text entirely")
    b = _item(12346, "2026-07-09T09:31:00-04:00")
    # Same id -> same fingerprint regardless of other fields; different id -> different.
    assert a1.fingerprint == a2.fingerprint
    assert a1.fingerprint != b.fingerprint
    # Stable across runs: sha256 of the id string, not Python's salted hash().
    assert a1.fingerprint == hashlib.sha256(b"12345").hexdigest()[:16]
    assert len(a1.fingerprint) == 16


# --------------------------------------------------------------------------- #
# fetch_news: pagination + dedup + fail-open (SDK client, fake HTTP layer)
# --------------------------------------------------------------------------- #

def _rigged_client(pages):
    """Real NewsClient with dummy creds; its RESTClient.get serves `pages` in order and
    records every call's (path, data)."""
    from alpaca.data.historical.news import NewsClient
    client = NewsClient("dummy-key", "dummy-secret", raw_data=True)
    calls = []

    def fake_get(path=None, data=None, **kwargs):
        calls.append({"path": path, "data": dict(data or {})})
        return pages[min(len(calls) - 1, len(pages) - 1)]

    client.get = fake_get          # instance attribute shadows the bound HTTP method
    return client, calls


def test_fetch_news_paginates_dedups_and_sorts(monkeypatch):
    page1 = {"news": [_art(1, "2026-07-08T20:01:00Z"), _art(2, "2026-07-08T21:00:00Z")],
             "next_page_token": "tok2"}
    page2 = {"news": [_art(2, "2026-07-08T21:00:00Z"),          # duplicate id across pages
                      _art(3, "2026-07-09T10:00:00Z", syms=("msft", "  ", 7)),
                      {"headline": "no id -> dropped"},
                      _art(4, "not-a-timestamp")],              # unparseable ts -> dropped
             "next_page_token": None}
    client, calls = _rigged_client([page1, page2])
    monkeypatch.setattr(bz, "_client", lambda: client)

    items = bz.fetch_news(["aapl", " msft "], datetime(2026, 7, 8, 16, 0, tzinfo=ET),
                          datetime(2026, 7, 9, 8, 0, tzinfo=ET), limit=10)

    # Pagination: two HTTP calls, second carries the page token; limit plumbed through.
    assert len(calls) == 2
    assert calls[0]["data"].get("limit") == 10
    assert calls[0]["data"].get("symbols") == "AAPL,MSFT"
    assert calls[1]["data"].get("page_token") == "tok2"
    # Dedup (id 2 once), drops (no-id, bad-ts), ascending ts order.
    assert [it.id for it in items] == ["1", "2", "3"]
    assert [it.ts for it in items] == sorted(it.ts for it in items)
    # UTC 20:01Z -> 16:01 ET (EDT) conversion.
    assert items[0].ts.startswith("2026-07-08T16:01:00")
    # Symbol normalization: upper-cased, blanks and non-strings dropped.
    assert items[2].symbols == ["MSFT"]


def test_fetch_news_fail_open_on_client_error(monkeypatch):
    def boom():
        raise RuntimeError("no creds / endpoint down")
    monkeypatch.setattr(bz, "_client", boom)
    out = bz.fetch_news(None, datetime(2026, 7, 8, 16, 0, tzinfo=ET),
                        datetime(2026, 7, 9, 8, 0, tzinfo=ET))
    assert out == []


def test_fetch_news_fail_open_on_http_error(monkeypatch):
    from alpaca.data.historical.news import NewsClient
    client = NewsClient("dummy-key", "dummy-secret", raw_data=True)

    def fake_get(path=None, data=None, **kwargs):
        raise ConnectionError("transport down")

    client.get = fake_get
    monkeypatch.setattr(bz, "_client", lambda: client)
    out = bz.fetch_news(["AAPL"], datetime(2026, 7, 8, 16, 0, tzinfo=ET),
                        datetime(2026, 7, 9, 8, 0, tzinfo=ET))
    assert out == []


# --------------------------------------------------------------------------- #
# overnight_news window math (weekend-aware most-recent-weekday-close)
# --------------------------------------------------------------------------- #
# 2026-01-01 is a Thursday => Jan 2 Fri, Jan 3 Sat, Jan 4 Sun, Jan 5 Mon, Jan 6 Tue.

@pytest.mark.parametrize("now,expected_close", [
    # Tuesday 06:00 -> Monday 16:00 (plain yesterday).
    (datetime(2026, 1, 6, 6, 0, tzinfo=ET), datetime(2026, 1, 5, 16, 0, tzinfo=ET)),
    # Monday 06:00 -> FRIDAY 16:00 (walk back across the weekend).
    (datetime(2026, 1, 5, 6, 0, tzinfo=ET), datetime(2026, 1, 2, 16, 0, tzinfo=ET)),
    # Sunday / Saturday -> Friday 16:00.
    (datetime(2026, 1, 4, 12, 0, tzinfo=ET), datetime(2026, 1, 2, 16, 0, tzinfo=ET)),
    (datetime(2026, 1, 3, 12, 0, tzinfo=ET), datetime(2026, 1, 2, 16, 0, tzinfo=ET)),
])
def test_last_weekday_close(now, expected_close):
    got = bz.last_weekday_close(now)
    assert got == expected_close
    assert got.weekday() < 5


def test_overnight_news_window_dedup_and_sort(monkeypatch):
    captured = {}

    def fake_fetch(symbols, start, end, *, limit=200):
        captured.update(symbols=symbols, start=start, end=end, limit=limit)
        return [  # out of order + duplicate id - overnight_news must sort + dedup
            _item(2, "2026-01-05T09:00:00-05:00"),
            _item(1, "2026-01-02T18:00:00-05:00"),
            _item(2, "2026-01-05T09:00:00-05:00"),
        ]

    monkeypatch.setattr(bz, "fetch_news", fake_fetch)
    now = datetime(2026, 1, 5, 6, 0)                     # NAIVE Monday 06:00 -> treated as ET
    out = bz.overnight_news(now)

    assert captured["symbols"] is None
    assert captured["start"] == datetime(2026, 1, 2, 16, 0, tzinfo=ET)   # FRIDAY close
    assert captured["end"] == datetime(2026, 1, 5, 6, 0, tzinfo=ET)
    assert [it.id for it in out] == ["1", "2"]           # deduped, ts-ascending


# --------------------------------------------------------------------------- #
# NewsTap: JSONL append, cursor advance, dedup across polls, length caps, heartbeat
# --------------------------------------------------------------------------- #

def test_news_tap_poll_once_appends_dedups_caps_and_advances_cursor(tmp_path):
    now = datetime(2026, 7, 9, 9, 40, tzinfo=ET)
    oversized = _item(
        "big", "2026-07-09T09:35:00-04:00",
        headline="H" * 10_000, summary="S\nwith\nnewlines" + "s" * 10_000,
        syms=["VERYLONGSYMBOLNAME" + str(k) for k in range(50)])
    batches = [
        [_item(1, "2026-07-09T09:31:00-04:00"), oversized],
        [_item(1, "2026-07-09T09:31:00-04:00"), oversized,          # repeats -> deduped
         _item(3, "2026-07-09T09:39:00-04:00")],
    ]
    windows = []

    def fake_fetch(symbols, start, end, *, limit=200):
        windows.append((start, end))
        return batches[min(len(windows) - 1, len(batches) - 1)]

    out = tmp_path / "news_stream.jsonl"
    hb = tmp_path / "news_tap_heartbeat.json"
    tap = bz.NewsTap(since_hours=1.0, fetch=fake_fetch, now_fn=lambda: now)
    assert tap.cursor == now - timedelta(hours=1)

    # Poll 1: both items appended, cursor -> latest item ts (09:35).
    assert tap.poll_once(out, heartbeat_path=hb) == 2
    assert tap.cursor == datetime(2026, 7, 9, 9, 35, tzinfo=ET)

    lines = out.read_text("utf-8").splitlines()
    assert len(lines) == 2
    recs = [json.loads(ln) for ln in lines]              # every line is valid JSON
    big = next(r for r in recs if r["id"] == "big")
    assert len(big["headline"]) == bz.HEADLINE_MAX       # caps enforced at write time
    assert len(big["summary"]) == bz.SUMMARY_MAX
    assert "\n" not in big["summary"]
    assert len(big["symbols"]) == bz.MAX_SYMBOLS_PER_ITEM
    assert all(len(s) <= bz.SYMBOL_MAX for s in big["symbols"])
    assert big["fingerprint"] == hashlib.sha256(b"big").hexdigest()[:16]
    assert set(recs[0]) == {"id", "ts", "headline", "summary", "symbols", "source",
                            "url", "fingerprint"}

    # Poll 2: only the genuinely new item lands; window starts at cursor - overlap.
    assert tap.poll_once(out, heartbeat_path=hb) == 1
    assert len(out.read_text("utf-8").splitlines()) == 3
    assert tap.cursor == datetime(2026, 7, 9, 9, 39, tzinfo=ET)
    assert windows[1][0] == datetime(2026, 7, 9, 9, 35, tzinfo=ET) - tap.overlap

    hb_data = json.loads(hb.read_text("utf-8"))
    assert hb_data["polls"] == 2 and hb_data["appended_total"] == 3
    assert hb_data["cursor"].startswith("2026-07-09T09:39:00")


def test_news_tap_failed_poll_keeps_cursor(tmp_path):
    now = datetime(2026, 7, 9, 9, 40, tzinfo=ET)
    tap = bz.NewsTap(since_hours=2.0, fetch=lambda *a, **k: [], now_fn=lambda: now)
    before = tap.cursor
    assert tap.poll_once(tmp_path / "out.jsonl") == 0
    assert tap.cursor == before                          # a [] poll never skips the window
    assert not (tmp_path / "out.jsonl").exists()         # nothing appended, no empty file


def test_news_tap_seen_memory_is_bounded(tmp_path):
    now = datetime(2026, 7, 9, 9, 40, tzinfo=ET)
    tap = bz.NewsTap(fetch=lambda *a, **k: [], now_fn=lambda: now)
    for i in range(bz.MAX_SEEN_FINGERPRINTS + 500):
        tap._remember(f"fp{i}")
    assert len(tap._seen) == bz.MAX_SEEN_FINGERPRINTS
    assert len(tap._seen_order) == bz.MAX_SEEN_FINGERPRINTS
    assert "fp0" not in tap._seen                        # oldest evicted FIFO
