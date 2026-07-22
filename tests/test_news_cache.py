"""WS4/WS5 module proof: NewsFlagsCache O(1) queries over runtime/news_flags.jsonl - covariate
windows, direction-align, the accel materiality/freshness floor, both row shapes (tier-0 has no
latency_s), and incremental tailing. No network."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from atlas.options.news_cache import NEWS_ACCEL_MIN_MATERIALITY, NewsFlagsCache

ET = ZoneInfo("America/New_York")
NOW = 1_800_000_000.0


def _ts(mins_ago):
    return datetime.fromtimestamp(NOW - mins_ago * 60, tz=ET).isoformat()


def _row(sym, mins_ago, *, shock=True, kind="fda", direction="up", mat=0.8, llm=False):
    r = {"event": "news_flag", "schema": 1, "symbol": sym, "shock": shock, "kind": kind,
         "direction": direction, "materiality": mat, "engine": "groq" if llm else "regex",
         "news_id": f"finnhub:{sym}{mins_ago}", "fingerprint": f"fp{sym}{mins_ago}",
         "headline_ts": _ts(mins_ago)}
    if llm:
        r["latency_s"] = 1.2                       # LLM rows carry it; tier-0 rows do NOT
    return r


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_covariate_windows_and_direction(tmp_path):
    p = tmp_path / "news_flags.jsonl"
    _write(p, [
        _row("AAPL", 40, shock=False, kind="analyst", direction="down", mat=0.3),   # 60m not 15m
        _row("AAPL", 5, shock=True, kind="fda", direction="up", mat=0.9, llm=True),  # newest, <15m
        _row("AAPL", 120, shock=True, kind="mna", direction="up"),                   # >60m -> excluded
        _row("TSLA", 3, shock=True, kind="halt", direction="unclear", mat=0.8),      # tier-0, no latency_s
    ])
    c = NewsFlagsCache(path=p)
    c.update()
    assert c.news_shock_15m("AAPL", NOW) is True
    assert c.news_count_60m("AAPL", NOW) == 2                 # 5m + 40m; 120m excluded
    assert c.news_kind_recent("AAPL", NOW) == "fda"          # newest BY TIME (order-independent)
    assert c.news_direction_align("AAPL", "call", NOW) == 1  # newest 'up' agrees with a call
    assert c.news_direction_align("AAPL", "put", NOW) == -1  # ...opposes a put
    assert c.headline_age_min("AAPL", NOW) == 5.0
    assert c.news_shock_15m("TSLA", NOW) is True             # tier-0 row handled
    assert c.news_direction_align("TSLA", "call", NOW) == 0  # unclear -> 0
    # unknown symbol -> safe defaults
    assert c.news_shock_15m("NONE", NOW) is False and c.news_count_60m("NONE", NOW) == 0
    assert c.news_kind_recent("NONE", NOW) is None and c.headline_age_min("NONE", NOW) is None


def test_fresh_shock_respects_materiality_and_window(tmp_path):
    p = tmp_path / "news_flags.jsonl"
    _write(p, [
        _row("HI", 3, shock=True, mat=0.9),                  # in-window, above floor -> returned
        _row("LO", 3, shock=True, mat=NEWS_ACCEL_MIN_MATERIALITY - 0.1),  # below floor -> None
        _row("OLD", 30, shock=True, mat=0.9),                # above floor but > accel window -> None
        _row("NOSHOCK", 2, shock=False, mat=0.9),            # high mat but not a shock -> None
    ])
    c = NewsFlagsCache(path=p)
    c.update()
    hit = c.fresh_shock("HI", NOW)
    assert hit is not None and hit["fingerprint"] == "fpHI3"
    assert c.fresh_shock("LO", NOW) is None
    assert c.fresh_shock("OLD", NOW) is None
    assert c.fresh_shock("NOSHOCK", NOW) is None


def test_incremental_tail_and_rotation(tmp_path):
    p = tmp_path / "news_flags.jsonl"
    _write(p, [_row("X", 5)])
    c = NewsFlagsCache(path=p)
    c.update()
    assert c.news_count_60m("X", NOW) == 1
    # append a second row -> only the NEW bytes are read
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_row("X", 2)) + "\n")
    c.update()
    assert c.news_count_60m("X", NOW) == 2
    c.update()                                               # idempotent (no new bytes)
    assert c.news_count_60m("X", NOW) == 2
