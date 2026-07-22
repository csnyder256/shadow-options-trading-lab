"""WS1a proof (mission reincorporate-cut-systems): harvest --daily-append is an idempotent
incremental update of cached symbols that screens ONLY the newly-appended sessions. No network."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

import scripts.harvest_inplay_days as h


def _mk_df(dates, *, close=10.0, vol=2_000_000.0, open_=None):
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    n = len(dates)
    o = open_ if open_ is not None else close
    return pd.DataFrame(
        {"open": [o] * n, "high": [max(o, close) * 1.01] * n, "low": [min(o, close) * 0.99] * n,
         "close": [close] * n, "volume": [vol] * n},
        index=idx)


def test_append_bars_merges_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "DAILY_CACHE", tmp_path)
    base = [date(2026, 6, 1) + timedelta(days=i) for i in range(30)]        # 6/1..6/30
    added0 = h._append_bars_to_cache("AAA", _mk_df(base))
    assert len(added0) == 30
    nxt = date(2026, 7, 1)
    added1 = h._append_bars_to_cache("AAA", _mk_df([base[-1], nxt]))         # overlap 6/30 + new 7/1
    assert added1 == {nxt}
    assert len(pd.read_parquet(h._daily_path("AAA"))) == 31                  # deduped, one new row
    assert h._append_bars_to_cache("AAA", _mk_df([nxt])) == set()           # idempotent no-op


class _Args:
    catchup_days = 7
    min_price = 5.0
    max_price = 500.0
    min_dollar_vol = 10_000_000.0
    gap_min = 4.0
    vol_mult_min = 3.0
    per_day_cap = 8
    min_hits = 1


def test_run_daily_append_screens_only_new_sessions(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    harvest = tmp_path / "harvest"
    cache.mkdir()
    harvest.mkdir()
    monkeypatch.setattr(h, "DAILY_CACHE", cache)
    monkeypatch.setattr(h, "HARVEST_DIR", harvest)

    # 30 flat sessions (no gap, flat vol → never in-play), plus a symbol the fake fetch gaps up.
    base = [date(2026, 6, 1) + timedelta(days=i) for i in range(30)]
    h._append_bars_to_cache("GAPPY", _mk_df(base, close=10.0, vol=2_000_000.0))
    h._append_bars_to_cache("QUIET", _mk_df(base, close=20.0, vol=2_000_000.0))
    new_sess = date(2026, 7, 1)

    def fake_fetch(symbols, start, end):
        out = set()
        out |= h._append_bars_to_cache("GAPPY", _mk_df([new_sess], close=11.0, vol=6_000_000.0, open_=11.0))
        out |= h._append_bars_to_cache("QUIET", _mk_df([new_sess], close=20.0, vol=2_000_000.0, open_=20.0))
        return out

    assert h.run_daily_append(_Args(), fetch_fn=fake_fetch) == 0
    screen = json.loads((harvest / "inplay_name_days.json").read_text())
    assert list(screen.keys()) == [new_sess.isoformat()]                    # ONLY the new session
    syms = {r["symbol"] for r in screen[new_sess.isoformat()]}
    assert "GAPPY" in syms and "QUIET" not in syms                          # +10% gap in, flat out
    assert (harvest / "inplay_symbols.txt").read_text().strip() == "GAPPY"

    # idempotent: a no-op fetch (cache current) adds nothing and preserves the file
    assert h.run_daily_append(_Args(), fetch_fn=lambda s, a, b: set()) == 0
    assert list(json.loads((harvest / "inplay_name_days.json").read_text()).keys()) == [new_sess.isoformat()]


def test_daily_append_empty_cache_returns_1(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "DAILY_CACHE", tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    assert h.run_daily_append(_Args(), fetch_fn=lambda s, a, b: set()) == 1
