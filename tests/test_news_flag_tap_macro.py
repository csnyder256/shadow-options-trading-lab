"""M5 proof (mission 20260712): the news-flag tap routes ticker-less MACRO rows to their own
observe-first sink (runtime/news_macro.jsonl) and NEVER hands them to the per-symbol classifier;
the symbol-row path is unchanged.
"""

from __future__ import annotations

import json
import sys

import scripts.news_flag_tap as nft


class _StubLocal:
    def health(self):
        return False


class _StubEngines:
    """No network / no LLM - the classifier tier returns nothing so we isolate ROUTING."""
    groq = None
    groq_fail_streak = 0
    local_fail_streak = 0
    local = _StubLocal()

    def classify(self, packet, allowed):
        return [], "none"

    def keepalive(self):
        pass


def test_macro_rows_route_to_sink_not_classifier(tmp_path, monkeypatch):
    stream = tmp_path / "news_stream.jsonl"
    flags = tmp_path / "news_flags.jsonl"
    macro = tmp_path / "news_macro.jsonl"
    hb = tmp_path / "news_flags_heartbeat.json"
    for name, val in (("STREAM", stream), ("FLAGS", flags), ("MACRO", macro), ("HEARTBEAT", hb)):
        monkeypatch.setattr(nft, name, val)
    monkeypatch.setattr(nft, "Engines", lambda: _StubEngines())

    sym = {"id": "1", "ts": "2026-07-12T10:00:00-04:00", "headline": "Acme halted pending news",
           "summary": "", "symbols": ["ACME"], "source": "benzinga", "url": "u1", "fingerprint": "fp1"}
    mac = {"id": "gdelt:abc", "ts": "2026-07-12T10:01:00-04:00",
           "headline": "Iran threatens to close Strait of Hormuz", "summary": "", "symbols": [],
           "source": "gdelt", "url": "u2", "fingerprint": "fp2"}

    calls = {"n": 0}

    def fake_read(offset):
        if calls["n"] == 0:
            calls["n"] = 1
            return [sym, mac], 100
        return [], 100

    monkeypatch.setattr(nft, "read_new_records", fake_read)
    monkeypatch.setattr(sys, "argv", ["news_flag_tap", "--once"])

    assert nft.main() == 0

    # 1) the macro row landed in its OWN sink, verbatim, tagged news_macro
    macro_rows = [json.loads(x) for x in macro.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(macro_rows) == 1
    m = macro_rows[0]
    assert m["event"] == "news_macro" and m["fingerprint"] == "fp2" and m["source"] == "gdelt"
    assert "Hormuz" in m["headline"]

    # 2) the macro row NEVER reached the classifier output (no flag carries its fingerprint)
    flag_rows = ([json.loads(x) for x in flags.read_text(encoding="utf-8").splitlines() if x.strip()]
                 if flags.exists() else [])
    assert all(r.get("fingerprint") != "fp2" for r in flag_rows)

    # 3) heartbeat exposes the new macro_written counter
    beat = json.loads(hb.read_text(encoding="utf-8"))
    assert beat["macro_written"] == 1


def test_append_macro_is_a_noop_on_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(nft, "MACRO", tmp_path / "news_macro.jsonl")
    assert nft.append_macro([]) == 0
    assert not (tmp_path / "news_macro.jsonl").exists()


def test_symbol_only_batch_still_classifies_and_no_macro_file(tmp_path, monkeypatch):
    """A burst with only symbol rows must behave exactly as before: no macro sink is written."""
    stream = tmp_path / "news_stream.jsonl"
    flags = tmp_path / "news_flags.jsonl"
    macro = tmp_path / "news_macro.jsonl"
    hb = tmp_path / "hb.json"
    for name, val in (("STREAM", stream), ("FLAGS", flags), ("MACRO", macro), ("HEARTBEAT", hb)):
        monkeypatch.setattr(nft, name, val)
    monkeypatch.setattr(nft, "Engines", lambda: _StubEngines())

    sym = {"id": "9", "ts": "2026-07-12T10:00:00-04:00", "headline": "Widget Co maintains buy",
           "summary": "", "symbols": ["WDGT"], "source": "benzinga", "url": "u", "fingerprint": "fp9"}
    calls = {"n": 0}

    def fake_read(offset):
        if calls["n"] == 0:
            calls["n"] = 1
            return [sym], 50
        return [], 50

    monkeypatch.setattr(nft, "read_new_records", fake_read)
    monkeypatch.setattr(sys, "argv", ["news_flag_tap", "--once"])
    assert nft.main() == 0
    assert not macro.exists()                              # no macro rows -> sink never created
    beat = json.loads(hb.read_text(encoding="utf-8"))
    assert beat["macro_written"] == 0
