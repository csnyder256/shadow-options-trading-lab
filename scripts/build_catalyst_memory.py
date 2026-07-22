#!/usr/bin/env python3
"""CATALYST MEMORY BUILDER (opts-catmem-store-v1) - deterministic backfill + heal.

Joins three existing assets into runtime/memory/catalyst_stories.jsonl (+ SQLite index):
  runtime/harvest/inplay_name_days.json   the in-play screen (gap/vol/range features), 504 sessions
  runtime/harvest/catalyst_tags.json      3,476 name-days, 1,743 with a real headline
  runtime/harvest_daily_cache/*.parquet   2yr daily OHLCV - forward returns are computed HERE
plus, when present, runtime/memory/catalyst_tags_llm.jsonl (the local-model tagging job's
kind/name_specific/direction_hint per key - validated drop-never-repair on read).

Forward-return rules (code-computed, never LLM):
  gap_hold_d0 = close(D)/open(D) - 1          (did the gap hold or fade intraday)
  ret_kd      = close(D+k)/close(D) - 1       (k = 1, 2, 5 TRADING days on the symbol's own index)
  missing future bars -> field null + censored: true (kept, never dropped - heals on re-run)

Modes: --rebuild writes the store fresh (idempotent backfill); default run HEALS censored rows
and appends keys not yet present. Always rebuilds the SQLite index afterward. Fail-open per
symbol; exit 0 unless the input assets are entirely missing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.memory.catalyst_memory import (MEM_DIR, STORIES_PATH, rebuild_index,  # noqa: E402
                                          validate_tag)

REPO = Path(__file__).resolve().parents[1]
HARVEST = REPO / "runtime" / "harvest"
DAILY_CACHE = REPO / "runtime" / "harvest_daily_cache"
LLM_TAGS = MEM_DIR / "catalyst_tags_llm.jsonl"


def log(msg: str) -> None:
    print(f"[catmem {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_llm_tags() -> dict:
    out: dict = {}
    try:
        for line in LLM_TAGS.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            tag = validate_tag(r)
            if tag and r.get("key"):
                out[str(r["key"])] = {**tag, "agree": bool(r.get("agree")),
                                      "model": r.get("model")}
    except OSError:
        pass
    return out


def forward_returns(df, date_str: str) -> dict:
    """Deterministic forward returns off the symbol's own trading-day index."""
    import pandas as pd
    try:
        ts = pd.Timestamp(date_str)
        pos_arr = df.index.get_indexer([ts])
        pos = int(pos_arr[0])
    except Exception:  # noqa: BLE001
        pos = -1
    if pos < 0:
        return {"gap_hold_d0": None, "ret_1d": None, "ret_2d": None, "ret_5d": None,
                "censored": True}
    row = df.iloc[pos]
    close_d = float(row["close"])
    open_d = float(row["open"])
    out = {"gap_hold_d0": round(close_d / open_d - 1.0, 5) if open_d > 0 else None}
    censored = False
    for k in (1, 2, 5):
        if pos + k < len(df) and close_d > 0:
            out[f"ret_{k}d"] = round(float(df.iloc[pos + k]["close"]) / close_d - 1.0, 5)
        else:
            out[f"ret_{k}d"] = None
            censored = True
    out["censored"] = censored
    return out


def build_rows() -> list[dict]:
    import pandas as pd
    name_days = json.loads((HARVEST / "inplay_name_days.json").read_text(encoding="utf-8"))
    tags = json.loads((HARVEST / "catalyst_tags.json").read_text(encoding="utf-8"))
    llm_tags = load_llm_tags()

    by_symbol: dict = defaultdict(list)
    for date_str, rows in name_days.items():
        for r in rows or []:
            sym = str(r.get("symbol") or "").upper()
            if sym:
                by_symbol[sym].append((date_str, r))

    out: list[dict] = []
    missing_parquet = 0
    for sym, items in sorted(by_symbol.items()):
        p = DAILY_CACHE / f"{sym}.parquet"
        df = None
        if p.exists():
            try:
                df = pd.read_parquet(p)
            except Exception:  # noqa: BLE001
                df = None
        if df is None:
            missing_parquet += 1
        for date_str, feat in items:
            key = f"{sym}|{date_str}"
            tag = tags.get(key) or {}
            llm = llm_tags.get(key)
            fwd = (forward_returns(df, date_str) if df is not None else
                   {"gap_hold_d0": None, "ret_1d": None, "ret_2d": None, "ret_5d": None,
                    "censored": True})
            gap = feat.get("gap_pct")
            headline = tag.get("headline")
            out.append({
                "schema": 1, "key": key, "symbol": sym, "date": date_str,
                "catalyst_kind": llm["kind"] if llm else None,
                # no headline = volume-only in-play day: name_specific false DETERMINISTICALLY
                "name_specific": (llm["name_specific"] if llm else bool(headline)),
                "direction_hint": llm["direction_hint"] if llm else None,
                "gap_direction": ("pos" if (gap or 0) > 0 else "neg" if (gap or 0) < 0
                                  else "neutral"),
                "headline": headline, "first_ts": tag.get("first_ts"),
                "n_news": tag.get("n_news"),
                "gap_pct": feat.get("gap_pct"), "vol_mult": feat.get("vol_mult"),
                "range_pct": feat.get("range_pct"), "dollar_vol20": feat.get("dollar_vol20"),
                "rank": feat.get("rank"), "delisted": bool(feat.get("delisted")),
                "fwd": fwd,
                "tag_source": ({"model": llm.get("model"), "agree": llm.get("agree")}
                               if llm else None),
                "ingest": "backfill_v1",
            })
    if missing_parquet:
        log(f"note: {missing_parquet} symbols had no daily parquet (censored rows kept)")
    return out


def merge_heal(existing: dict, rows: list) -> tuple[int, int, int]:
    """Converge the store toward best-known, in place: returns heal FORWARD (a censored row
    gains its future bars on re-run), tags heal BACKWARD (the async LLM tagging job lands
    AFTER backfill - found live 2026-07-11 when 1,741 fresh tags merged as +0 because this
    branch only looked at censoring). Rows the backfill doesn't generate (job C's daily_v1
    appends) are never touched. Returns (added, healed, retagged)."""
    added = healed = retagged = 0
    for r in rows:
        old = existing.get(r["key"])
        if old is None:
            existing[r["key"]] = r
            added += 1
            continue
        heal_fwd = (old.get("fwd") or {}).get("censored") and not r["fwd"]["censored"]
        gain_tag = old.get("catalyst_kind") is None and r.get("catalyst_kind") is not None
        if not heal_fwd and not gain_tag:
            continue
        if not heal_fwd and not (old.get("fwd") or {}).get("censored"):
            r["fwd"] = old.get("fwd", r["fwd"])     # keep already-final returns as stored
        r["ingest"] = old.get("ingest", r["ingest"])
        existing[r["key"]] = r
        healed += 1 if heal_fwd else 0
        retagged += 1 if gain_tag else 0
    return added, healed, retagged


def main() -> int:
    ap = argparse.ArgumentParser(description="catalyst memory backfill/heal (deterministic)")
    ap.add_argument("--rebuild", action="store_true", help="write the store fresh")
    args = ap.parse_args()

    MEM_DIR.mkdir(parents=True, exist_ok=True)
    if not (HARVEST / "inplay_name_days.json").exists():
        log("FATAL: harvest inputs missing")
        return 1

    rows = build_rows()
    if args.rebuild or not STORIES_PATH.exists():
        with STORIES_PATH.open("w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
        log(f"store rebuilt: {len(rows)} rows")
    else:
        existing: dict = {}
        for line in STORIES_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
                existing[r["key"]] = r
            except (ValueError, KeyError):
                continue
        added, healed, retagged = merge_heal(existing, rows)
        with STORIES_PATH.open("w", encoding="utf-8", newline="\n") as fh:
            for r in existing.values():
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
        log(f"store healed: +{added} new, {healed} censored rows healed, "
            f"{retagged} rows adopted a new LLM tag, total {len(existing)}")

    n = rebuild_index()
    kinds = Counter()
    censored = 0
    for line in STORIES_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        kinds[r.get("catalyst_kind") or "(untagged)"] += 1
        if (r.get("fwd") or {}).get("censored"):
            censored += 1
    log(f"index rebuilt: {n} rows | censored {censored} | kinds: {dict(kinds.most_common(6))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
