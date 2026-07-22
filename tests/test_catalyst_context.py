"""WS1b proof (opts-catalyst-context-writer-v1): the revived catalyst context feeds + CatalystBook
write runtime/catalyst_state.json in the NATIVE schema the research crew already reads - un-starving
the crew / archiver / catalyst-memory chain. No network (the HTTP seam is monkeypatched)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import atlas.collect.catalysts as C
from atlas.collect.catalyst_book import CatalystBook


# --------------------------------------------------------------------------- EDGAR feed (primary)

def _edgar_hit(items, name):
    return {"_source": {"items": items, "display_names": [name], "file_date": "2026-07-12"}}


def test_edgar_parser_pos_neg_split_and_dropna(monkeypatch):
    hits = {"hits": {"hits": [
        _edgar_hit(["1.01"], "Acme Corp (ACME) (CIK 0001234567)"),         # positive 8-K only
        _edgar_hit(["1.01", "1.03"], "Broke Inc (BRK) (CIK 0007654321)"),  # ONE filing, BOTH classes
        _edgar_hit(["1.01"], "No Ticker Fund LLC (CIK 0000000001)"),       # no listed ticker -> drop
    ]}}
    monkeypatch.setattr(C, "_http_json", lambda url, **kw: hits)
    # scan the negative items too (the writer's config) so bankruptcy/delisting split to edgar_neg
    evs = C.EdgarMaterialEventsFeed(items=("1.01", "1.03")).poll("2026-07-12T13:00:00+00:00", 1000.0)
    pairs = {(e.symbol, e.source) for e in evs}
    assert ("ACME", "edgar") in pairs                    # positive -> context source
    assert ("BRK", "edgar") in pairs                     # same filing also emits its positive context
    assert ("BRK", "edgar_neg") in pairs                 # ...and its negative defensive event
    assert not any("No" in e.symbol for e in evs)        # no-ticker filing dropped
    assert next(e for e in evs if e.symbol == "ACME").kind == "edgar.8k.material_agreement"


def test_edgar_feed_is_fail_open(monkeypatch):
    def boom(url, **kw):
        raise OSError("network down")
    monkeypatch.setattr(C, "_http_json", boom)
    assert C.EdgarMaterialEventsFeed().poll("2026-07-12T13:00:00+00:00", 1000.0) == []   # never raises


# --------------------------------------------------------------------------- the book

class _FakeFeed:
    name = "fake"
    last_error = ""

    def __init__(self, events):
        self._events = events

    def poll(self, now_iso, now_epoch):
        return list(self._events)


def _mk_event(sym="ABCD", ttl=86400.0, ts="2026-07-12T13:00:00"):
    return C.CatalystEvent.build(symbol=sym, kind="edgar.8k.material_agreement", headline="8-K filed",
                                 detail="material agreement", magnitude=15.0, observed_at_iso=ts,
                                 source_ts_iso=ts, source="edgar", ttl_seconds=ttl)


def test_book_poll_dedup_prune_and_native_schema(tmp_path):
    state = tmp_path / "catalyst_state.json"
    book = CatalystBook(feeds=[_FakeFeed([_mk_event()])], state_path=state)
    assert len(book.poll("2026-07-12T13:00:00", 1000.0)) == 1     # accepted
    assert book.poll("2026-07-12T13:00:10", 1010.0) == []         # dedup by event_id
    book.save()
    data = json.loads(state.read_text("utf-8"))
    assert set(data) >= {"events", "seen", "snapshot"}            # native schema (crew + archiver read)
    (_eid, rec), = data["events"].items()
    assert rec["status"] == "pending" and rec["event"]["symbol"] == "ABCD"
    assert rec["event"]["kind"] == "edgar.8k.material_agreement"
    book._prune(1000.0 + 86400.0 + 1.0)                          # past TTL -> pruned
    assert book.events == {}


def test_book_load_roundtrips(tmp_path):
    state = tmp_path / "catalyst_state.json"
    book = CatalystBook(feeds=[_FakeFeed([_mk_event()])], state_path=state)
    book.poll("2026-07-12T13:00:00", 1000.0)
    book.save()
    assert set(CatalystBook(feeds=[], state_path=state).events) == set(book.events)


def test_book_output_is_crew_readable(tmp_path, monkeypatch):
    """THE un-starve proof: crew.gather_catalyst_events reads book-written catalyst_state.json."""
    import scripts.research_crew as rc
    now = datetime.now(timezone.utc)                             # fresh event -> inside the 48h window
    book = CatalystBook(feeds=[_FakeFeed([_mk_event(sym="MSFT", ts=now.isoformat())])],
                        state_path=tmp_path / "catalyst_state.json")
    book.poll(now.isoformat(), now.timestamp())
    book.save()
    monkeypatch.setattr(rc, "RUNTIME_DIR", tmp_path)
    events = rc.gather_catalyst_events()
    assert any(e["symbol"] == "MSFT" and e["kind"] == "edgar.8k.material_agreement" for e in events)


def test_dropped_govcon_and_localhost_feeds_are_gone():
    for gone in ("DefenseGovFeed", "SamGovFeed", "SentinelCatalystFeed"):
        assert not hasattr(C, gone)
    for kept in ("EdgarMaterialEventsFeed", "Form4InsiderBuyFeed", "Schedule13DFeed",
                 "FdaBinaryEventFeed", "DilutionWatchFeed", "GlobeNewswirePrFeed",
                 "ApeWisdomFeed", "BorrowFeeFeed"):
        assert hasattr(C, kept)
