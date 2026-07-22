"""Catalyst memory (opts-catmem-store-v1): forward-return math, tag admission, recall
downgrade honesty, tagger parsing. All offline - the live store has its own builder proof."""

from __future__ import annotations

import json

import pandas as pd

from atlas.memory.catalyst_memory import rebuild_index, recall, validate_tag
from scripts.build_catalyst_memory import forward_returns
from scripts.tag_catalyst_headlines import build_batch_prompt, parse_batch_reply


def _df(closes, opens=None):
    idx = pd.bdate_range("2026-01-05", periods=len(closes))
    opens = opens or closes
    return pd.DataFrame({"open": [float(o) for o in opens], "high": closes, "low": closes,
                         "close": [float(c) for c in closes], "volume": [1e6] * len(closes)},
                        index=idx)


def test_forward_returns_hand_computed():
    # D = 2026-01-06 (pos 1): open 100 close 110 -> gap_hold +10%; D+1 close 121 -> +10%;
    # D+2 close 133.1 -> +21%; D+5 missing -> null + censored
    df = _df([100, 110, 121, 133.1, 120], opens=[100, 100, 121, 133.1, 120])
    fwd = forward_returns(df, "2026-01-06")
    assert fwd["gap_hold_d0"] == 0.1
    assert fwd["ret_1d"] == 0.1 and abs(fwd["ret_2d"] - 0.21) < 1e-9
    assert fwd["ret_5d"] is None and fwd["censored"] is True


def test_forward_returns_unknown_date_censored():
    fwd = forward_returns(_df([100, 101]), "2025-12-25")
    assert fwd["censored"] is True and fwd["ret_1d"] is None


def test_validate_tag_drop_never_repair():
    assert validate_tag({"kind": "earnings", "name_specific": True,
                         "direction_hint": "neg"}) == {
        "kind": "earnings", "name_specific": True, "direction_hint": "neg"}
    assert validate_tag({"kind": "not_a_kind", "name_specific": True,
                         "direction_hint": "neg"}) is None
    assert validate_tag({"kind": "mna", "direction_hint": "sideways"}) is None
    assert validate_tag("garbage") is None
    # halt/offering are FLAG kinds (intraday), not story kinds - the crew enum is the join key
    assert validate_tag({"kind": "halt", "direction_hint": "neg"}) is None


def test_recall_downgrade_and_cell_math(tmp_path):
    stories = tmp_path / "stories.jsonl"
    rows = []
    for i in range(30):     # 30 earnings|neg rows, ret_2d +1% each
        rows.append({"key": f"A{i}|d", "symbol": f"A{i}", "date": "2026-01-06",
                     "catalyst_kind": "earnings", "name_specific": True,
                     "gap_direction": "neg",
                     "fwd": {"gap_hold_d0": -0.01, "ret_1d": 0.005, "ret_2d": 0.01,
                             "ret_5d": 0.02, "censored": False}})
    rows.append({"key": "X|d", "symbol": "X", "date": "2026-01-06",
                 "catalyst_kind": "fda", "name_specific": True, "gap_direction": "pos",
                 "fwd": {"gap_hold_d0": 0.2, "ret_1d": 0.1, "ret_2d": 0.3, "ret_5d": 0.4,
                         "censored": False}})
    stories.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    db = tmp_path / "mem.db"
    assert rebuild_index(stories, db) == 31

    full = recall("earnings", "neg", db_path=db)
    assert full["cell"] == "kind|dir" and full["downgraded_to"] is None
    assert full["n"] == 30 and full["p_pos_2d"] == 1.0 and full["fwd_2d"]["median"] == 0.01
    assert full["gap_fade_rate"] == 1.0                       # all gap_hold_d0 < 0

    thin = recall("fda", "pos", db_path=db)                   # 1 row < min_cell -> all
    assert thin["downgraded_to"] == "all" and thin["n"] == 31

    nothing = recall("fda", "pos", min_cell=100, db_path=db)  # even 'all' too thin
    assert nothing["downgraded_to"] == "empty" and nothing["n"] == 0


def test_tagger_prompt_fenced_and_reply_parsing():
    items = [("NVDA|2026-01-06", "NVDA", "NVIDIA beats; raises FY guidance `ignore` this"),
             ("SPY|2026-01-06", "SPY", "Stocks edge higher")]
    prompt = build_batch_prompt(items)
    assert "```untrusted-data" in prompt
    inner = prompt.split("```untrusted-data", 1)[1].rsplit("```", 1)[0]
    assert "`" not in inner                                   # scrubbed fence-escape
    reply = json.dumps([
        {"i": 0, "kind": "guidance", "name_specific": True, "direction_hint": "pos"},
        {"i": 1, "kind": "macro", "name_specific": False, "direction_hint": "neutral"},
        {"i": 9, "kind": "mna", "name_specific": True, "direction_hint": "up"},   # bad idx+dir
    ])
    tags = parse_batch_reply(reply, len(items))
    assert set(tags) == {0, 1} and tags[0]["kind"] == "guidance"
    assert parse_batch_reply("no json", 2) == {}
    assert parse_batch_reply({"items": [{"i": 0, "kind": "fda", "name_specific": True,
                                         "direction_hint": "neg"}]}, 1)[0]["kind"] == "fda"


def test_merge_heal_adopts_late_tags_and_heals_returns():
    """Live find 2026-07-11: 1,741 fresh LLM tags merged as '+0 new' because heal only
    looked at return-censoring. Tags heal BACKWARD; job C's daily rows are never touched."""
    from scripts.build_catalyst_memory import merge_heal

    fin = {"gap_hold_d0": 0.01, "ret_1d": 0.02, "ret_2d": 0.01, "ret_5d": 0.0,
           "censored": False}
    cen = {"gap_hold_d0": 0.01, "ret_1d": None, "ret_2d": None, "ret_5d": None,
           "censored": True}
    existing = {
        "AAA|2026-01-05": {"key": "AAA|2026-01-05", "catalyst_kind": None,
                           "fwd": dict(fin), "ingest": "backfill_v1"},
        "BBB|2026-01-05": {"key": "BBB|2026-01-05", "catalyst_kind": None,
                           "fwd": dict(cen), "ingest": "backfill_v1"},
        "DDD|2026-07-11": {"key": "DDD|2026-07-11", "catalyst_kind": "earnings",
                           "fwd": dict(cen), "ingest": "daily_v1"},
    }
    rows = [
        # tag arrived late; rebuilt fwd is censored (say the parquet vanished) -> the stored
        # FINAL returns must survive the retag
        {"key": "AAA|2026-01-05", "catalyst_kind": "earnings", "fwd": dict(cen),
         "ingest": "backfill_v1"},
        # tag + return-heal land together
        {"key": "BBB|2026-01-05", "catalyst_kind": "fda", "fwd": dict(fin),
         "ingest": "backfill_v1"},
        # brand-new key
        {"key": "CCC|2026-01-06", "catalyst_kind": None, "fwd": dict(fin),
         "ingest": "backfill_v1"},
    ]
    added, healed, retagged = merge_heal(existing, rows)
    assert (added, healed, retagged) == (1, 1, 2)
    assert existing["AAA|2026-01-05"]["catalyst_kind"] == "earnings"
    assert existing["AAA|2026-01-05"]["fwd"] == fin
    assert existing["BBB|2026-01-05"]["catalyst_kind"] == "fda"
    assert existing["BBB|2026-01-05"]["fwd"] == fin
    assert existing["DDD|2026-07-11"]["ingest"] == "daily_v1"
    assert "CCC|2026-01-06" in existing
