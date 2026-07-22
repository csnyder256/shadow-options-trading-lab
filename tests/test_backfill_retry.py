"""WS1c proof (opts-fix-backfill-retry-v1): a symbol is marked backfilled ONLY after a non-empty
fetch; an empty (fail-open) backfill is retried up to BACKFILL_MAX_ATTEMPTS, then gives up for the
day with a journal note - instead of being permanently starved of session context on the first
transient failure."""

from __future__ import annotations

import types

import scripts.run_options_shadow as ros


class _StubFeed:
    def __init__(self, results):
        self.results = results
        self.calls: dict[str, int] = {}

    def backfill(self, sym):
        self.calls[sym] = self.calls.get(sym, 0) + 1
        return self.results.get(sym, [])


class _StubLedger:
    def __init__(self):
        self.events: list[dict] = []

    def journal(self, d):
        self.events.append(d)


def _core(feed):
    c = ros.OptionsShadowCore.__new__(ros.OptionsShadowCore)   # bypass __init__ - isolate _backfill
    c.feed = feed
    c._backfilled = set()
    c._backfill_attempts = {}
    c.ledger = _StubLedger()
    c.log = lambda *a, **k: None
    c.builder = types.SimpleNamespace(seed_bar=lambda sym, b: None)
    c._on_completed_bar = lambda *a, **k: None
    return c


def test_empty_backfill_retries_then_gives_up():
    feed = _StubFeed({})                                       # every symbol returns [] (fail-open)
    c = _core(feed)
    for _ in range(ros.BACKFILL_MAX_ATTEMPTS - 1):
        c._backfill(["ABC"], now=0.0)
        assert "ABC" not in c._backfilled                     # NOT permanently marked while retrying
    assert feed.calls["ABC"] == ros.BACKFILL_MAX_ATTEMPTS - 1
    c._backfill(["ABC"], now=0.0)                              # final attempt -> give up
    assert "ABC" in c._backfilled
    assert any(e["event"] == "backfill_gave_up" and e["symbol"] == "ABC" for e in c.ledger.events)
    c._backfill(["ABC"], now=0.0)                              # given up -> no further fetch
    assert feed.calls["ABC"] == ros.BACKFILL_MAX_ATTEMPTS


def test_successful_backfill_marks_immediately_no_retry():
    feed = _StubFeed({"XYZ": ["bar1", "bar2"]})
    c = _core(feed)
    seeded = []
    c.builder = types.SimpleNamespace(seed_bar=lambda sym, b: seeded.append((sym, b)))
    c._backfill(["XYZ"], now=0.0)
    assert "XYZ" in c._backfilled
    assert feed.calls["XYZ"] == 1                             # no retry on success
    assert seeded == [("XYZ", "bar1"), ("XYZ", "bar2")]
    assert c.ledger.events == []                              # no give-up journal on success
    c._backfill(["XYZ"], now=0.0)                             # already done -> no second fetch
    assert feed.calls["XYZ"] == 1


def test_transient_failure_then_success_recovers():
    feed = _StubFeed({"REC": []})                            # starts failing
    c = _core(feed)
    c._backfill(["REC"], now=0.0)
    assert "REC" not in c._backfilled                        # retried, not given up
    feed.results["REC"] = ["bar"]                            # feed recovers
    c._backfill(["REC"], now=0.0)
    assert "REC" in c._backfilled and c.ledger.events == []  # recovered cleanly, no give-up
