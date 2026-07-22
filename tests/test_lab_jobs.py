"""Overnight-lab stage-4 real jobs (opts-lab-jobs-v1): job A citation validation + job C
story-stub append, all with fakes - the double gate itself is covered by test_overnight_lab."""

from __future__ import annotations

import json

from scripts.run_overnight_lab import EXIT_TAG_ENUM, _job_catmem_append, _job_exit_reviews


class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def complete_json(self, **kw):
        self.calls += 1
        return self.reply

    def health(self):
        return True


class FakeLedger:
    def __init__(self, tmp, exits=(), entries=()):
        self.quotes_dir = tmp / "quotes"
        self.journal_path = tmp / "journal.jsonl"
        self._exits = list(exits)
        self._entries = list(entries)

    def load_exits(self, _day):
        return self._exits

    def load_entries(self, _day):
        return self._entries


EXIT_ROW = {"position_id": "P1", "occ": "SPY260713C00560000", "day": "2026-07-11",
            "rule": "h_ev_hold_below_sell", "bid": 1.20, "ask": 1.30,
            "ledgers": {"worst": {"net_pnl_usd": 12.0, "gross_pnl_usd": 20.0}},
            "decomposition": {"spread_paid_usd": 8.0, "theta_paid_usd": 3.0},
            "underlying_mfe": 0.01, "underlying_mae": -0.004, "hold_trading_days": 0.2}


def _quotes(tmp, pid="P1"):
    qdir = tmp / "quotes"
    qdir.mkdir(parents=True, exist_ok=True)
    rows = [{"position_id": pid, "ts_epoch": 100.0, "bid": 1.0, "ask": 1.1},
            {"position_id": pid, "ts_epoch": 200.0, "bid": 1.9, "ask": 2.0},   # the peak
            {"position_id": pid, "ts_epoch": 300.0, "bid": 1.2, "ask": 1.3}]
    (qdir / "2026-07-11.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_job_a_valid_citation_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.run_overnight_lab.LAB_DIR", tmp_path / "lab")
    _quotes(tmp_path)
    client = FakeClient({"narrative": "Peaked at 200 then faded; ladder took the EV exit.",
                         "tags": ["exited_into_strength", "bogus_tag"], "cites": [200.0]})
    out = _job_exit_reviews(client, FakeLedger(tmp_path, exits=[EXIT_ROW]), "2026-07-11")
    assert out["n"] == 1 and out["dropped"] == 0
    data = json.loads((tmp_path / "lab" / "exit_reviews" / "2026-07-11.json").read_text("utf-8"))
    item = data["items"][0]
    assert item["tags"] == ["exited_into_strength"]          # bogus tag silently dropped
    assert item["cites"] == [200.0]
    assert item["digest"]["peak_bid"] == 1.9
    assert item["digest"]["left_on_table_usd"] == 70.0       # (1.9 - 1.2) * 100 - CODE computed


def test_job_a_fabricated_citation_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.run_overnight_lab.LAB_DIR", tmp_path / "lab")
    _quotes(tmp_path)
    client = FakeClient({"narrative": "x", "tags": [], "cites": [999.0]})   # ts not in path
    out = _job_exit_reviews(client, FakeLedger(tmp_path, exits=[EXIT_ROW]), "2026-07-11")
    assert out["n"] == 0 and out["dropped"] == 1


def test_job_c_appends_story_stub(tmp_path, monkeypatch):
    import scripts.run_overnight_lab as lab
    monkeypatch.setattr(lab, "LAB_DIR", tmp_path / "lab")
    monkeypatch.setattr(lab, "RUNTIME", tmp_path)
    mem = tmp_path / "memory"
    monkeypatch.setattr("atlas.memory.catalyst_memory.MEM_DIR", mem)
    monkeypatch.setattr("atlas.memory.catalyst_memory.STORIES_PATH",
                        mem / "catalyst_stories.jsonl")
    (tmp_path / "news_stream.jsonl").write_text(json.dumps(
        {"ts": "2026-07-11T10:00:00-04:00", "headline": "ACME wins defense contract",
         "symbols": ["ACME"]}), encoding="utf-8")
    (tmp_path / "hunt_list.json").write_text(json.dumps(
        {"candidates": [{"symbol": "ACME"}]}), encoding="utf-8")
    client = FakeClient([{"i": 0, "kind": "contract", "name_specific": True,
                          "direction_hint": "pos"}])
    out = _job_catmem_append(client, FakeLedger(tmp_path), "2026-07-11")
    assert out["n"] == 1
    row = json.loads((mem / "catalyst_stories.jsonl").read_text("utf-8").strip())
    assert row["key"] == "ACME|2026-07-11" and row["catalyst_kind"] == "contract"
    assert row["fwd"]["censored"] is True and row["ingest"] == "daily_v1"
    # idempotence: a second run skips the existing key
    out2 = _job_catmem_append(client, FakeLedger(tmp_path), "2026-07-11")
    assert out2["n"] == 0


def test_exit_tag_enum_closed():
    assert "exited_into_strength" in EXIT_TAG_ENUM and len(EXIT_TAG_ENUM) == 6
