#!/usr/bin/env python3
"""MENTION TAP (opts-svc-mention-tap-v1) - social attention collector, stage 0.

Polls PUBLIC endpoints only (no auth, no scraping-behind-login, real User-Agent):
  * reddit r/wallstreetbets/new.json + r/stocks/new.json  (60s cadence)
  * stocktwits trending symbols                            (30s cadence; ENTRY transitions count)

Extraction is regex + known-universe intersection (atlas/collect/social_mentions.py - NO LLM).
Writes its OWN files (single-writer idiom):
  runtime/mention_counts.jsonl   one row per (closed 5-min bucket, symbol)
  runtime/mention_flags.jsonl    z>=3 acceleration flags - only after >=5 sessions of baseline
  runtime/mention_tap_heartbeat.json

THE BASELINE CLOCK STARTS AT FIRST RUN: z-scores are refused (None) until the same
bucket-of-day has >=5 trailing observations, so the first week is pure collection.
NOTHING consumes these files yet (covariate = its own future registration).

Framing law: attention/acceleration is a DIRECTION-AGNOSTIC in-play detector; the WSB-long
thesis is dead (Bradley RFS 2024) and stays dead. Fail-open everywhere: a blocked endpoint
just slows the baseline clock. Session-scoped v1 (launched manually or by the day launcher);
a 24/7 schtask is a later, separate decision.

Run: .venv\\Scripts\\python.exe scripts\\mention_tap.py [--once]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.collect import social_mentions as sm               # noqa: E402
from atlas.fsutil import atomic_replace                       # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RUNTIME = REPO / "runtime"
COUNTS = RUNTIME / "mention_counts.jsonl"
FLAGS = RUNTIME / "mention_flags.jsonl"
HEARTBEAT = RUNTIME / "mention_tap_heartbeat.json"
UNIVERSE_DIR = RUNTIME / "harvest_daily_cache"

UA = "atlas-mention-tap/1.0 (research collector; contact via repo owner)"
REDDIT_URLS = ("https://www.reddit.com/r/wallstreetbets/new.json?limit=100&raw_json=1",
               "https://www.reddit.com/r/stocks/new.json?limit=100&raw_json=1")
STOCKTWITS_URL = "https://api.stocktwits.com/api/2/trending/symbols.json"
REDDIT_EVERY_S = 60.0
STOCKTWITS_EVERY_S = 30.0
TZ_OFFSET_S = -4 * 3600            # ET summer; bucket-of-day matching tolerance is 5 min anyway


def log(msg: str) -> None:
    print(f"[mention_tap {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _get_json(url: str, timeout: float = 10.0):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def load_universe() -> frozenset:
    """Known-symbol universe = harvest_daily_cache filenames (~12.5k active US names)."""
    try:
        return frozenset(p.name[:-8].upper() for p in UNIVERSE_DIR.glob("*.parquet"))
    except OSError:
        return frozenset()


def load_baseline() -> dict:
    """{(symbol, bucket_of_day): [counts by prior session]} from mention_counts.jsonl - 
    one observation per (symbol, bucket_of_day, date)."""
    out: dict = defaultdict(list)
    seen_dates: dict = defaultdict(set)
    try:
        for line in COUNTS.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
                bts = float(r["bucket_ts"])
                key = (r["symbol"], sm.bucket_of_day(bts, tz_offset_s=TZ_OFFSET_S))
                day = time.strftime("%Y-%m-%d", time.gmtime(bts + TZ_OFFSET_S))
                if day not in seen_dates[key]:
                    seen_dates[key].add(day)
                    out[key].append(int(r["count"]))
            except (KeyError, TypeError, ValueError):
                continue
    except OSError:
        pass
    return out


def append_rows(path: Path, rows: list[dict]) -> int:
    if not rows:
        return 0
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="social mention collector (stage 0; own files only)")
    ap.add_argument("--once", action="store_true", help="one poll cycle then flush + exit")
    args = ap.parse_args()

    universe = load_universe()
    baseline = load_baseline()
    log(f"start: universe={len(universe)} symbols, baseline keys={len(baseline)}")
    if not universe:
        log("WARN: empty universe (harvest_daily_cache unreadable) - collecting nothing")

    seen_posts: set = set()
    trending_prev: set = set()
    bucket: dict = defaultdict(lambda: defaultdict(int))    # sym -> source -> count
    bucket_id = sm.bucket_key(time.time())
    last_reddit = 0.0
    last_st = 0.0
    counts_written = 0
    flags_written = 0
    polls = 0

    def flush_bucket(bts: int) -> None:
        nonlocal counts_written, flags_written
        rows = sm.merge_bucket(bucket)
        out = [{"schema": 1, "bucket_ts": bts, "bucket_min": sm.BUCKET_MIN, **r} for r in rows]
        counts_written += append_rows(COUNTS, out)
        flag_rows = []
        for r in rows:
            key = (r["symbol"], sm.bucket_of_day(bts, tz_offset_s=TZ_OFFSET_S))
            acc = sm.acceleration_z(r["count"], baseline.get(key, []))
            if acc and acc["flag"]:
                flag_rows.append({"schema": 1, "event": "mention_accel", "bucket_ts": bts,
                                  "symbol": r["symbol"], "count": r["count"], **acc})
            baseline.setdefault(key, []).append(r["count"])   # today joins tomorrow's baseline
        flags_written += append_rows(FLAGS, flag_rows)
        if out:
            log(f"bucket {bts}: {len(out)} symbols, {len(flag_rows)} accel flags")
        bucket.clear()

    while True:
        try:
            now = time.time()
            nb = sm.bucket_key(now)
            if nb != bucket_id:
                flush_bucket(bucket_id)
                bucket_id = nb
            if now - last_reddit >= REDDIT_EVERY_S:
                last_reddit = now
                for url in REDDIT_URLS:
                    try:
                        data = _get_json(url)
                        for child in (data.get("data") or {}).get("children") or []:
                            d = child.get("data") or {}
                            pid = str(d.get("name") or d.get("id") or "")
                            if not pid or pid in seen_posts:
                                continue
                            seen_posts.add(pid)
                            if len(seen_posts) > 20000:
                                seen_posts.clear()            # crude cap; dedup window resets
                            text = f"{d.get('title') or ''} {str(d.get('selftext') or '')[:2000]}"
                            for sym in sm.extract_symbols(text, universe):
                                bucket[sym]["reddit"] += 1
                    except Exception:  # noqa: BLE001 - fail-open per endpoint
                        pass
            if now - last_st >= STOCKTWITS_EVERY_S:
                last_st = now
                try:
                    data = _get_json(STOCKTWITS_URL)
                    cur = {str(s.get("symbol") or "").upper()
                           for s in data.get("symbols") or [] if s.get("symbol")}
                    cur &= universe
                    for sym in cur - trending_prev:           # ENTRY transitions only
                        bucket[sym]["stocktwits_trend"] += 1
                    trending_prev = cur
                except Exception:  # noqa: BLE001
                    pass
            polls += 1
            try:
                tmp = HEARTBEAT.with_name(HEARTBEAT.name + ".tmp")
                tmp.write_text(json.dumps({
                    "schema": 1, "ts_epoch": round(now, 3), "polls": polls,
                    "counts_written": counts_written, "flags_written": flags_written,
                    "open_bucket_symbols": len(bucket), "baseline_keys": len(baseline),
                }, indent=2, sort_keys=True), encoding="utf-8")
                atomic_replace(tmp, HEARTBEAT)
            except OSError:
                pass
        except KeyboardInterrupt:
            flush_bucket(bucket_id)
            log("interrupt - flushed + clean exit")
            return 0
        except Exception as exc:  # noqa: BLE001
            log(f"tolerated error: {exc!r}")
        if args.once:
            flush_bucket(bucket_id)
            return 0
        time.sleep(5.0)


if __name__ == "__main__":
    raise SystemExit(main())
