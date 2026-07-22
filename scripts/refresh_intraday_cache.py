#!/usr/bin/env python3
"""Nightly intraday 1-min cache refresh - implements the registered
`opts-fix-noise-cache-refresh-v1` (sweep_ledger 2026-07-10): append each CLOSED
session's 1-min bars to runtime/intraday_cache/{SPY,QQQ,IWM}_1min.parquet so the
lane 1/1b noise profiles, 14d range percentile and avg_daily_range track reality
instead of aging one day per session (the cache froze at 2026-07-08 because the
one-shot build never re-ran and `fetch_intraday_bars` treats `end` as
midnight-EXCLUSIVE).

Source = ALPACA IEX via the existing atlas.collect.intraday_data.fetch_intraday_bars - 
deliberately NOT Tradier: the cache's volume column is IEX single-venue scale
(~2-3% of consolidated tape) and mixing sources would corrupt avg_first5_volume
semantics. Same fetcher, same RTH filter (09:30-15:59 ET left-labeled), same tz.

Behavior contract:
  * multi-day catch-up is the DEFAULT: every trading session strictly after the
    last cached bar whose close has already passed is fetched (a machine that was
    off Friday self-heals on Saturday; a mid-session manual run never appends a
    partial day).
  * fail-open, exit 0 ALWAYS: no creds / API down / unreadable file -> log + skip,
    the parquet on disk is never touched except by a sanity-gated atomic replace.
  * idempotent: dedupe on the timestamp index; re-runs append nothing.
  * scope = SPY/QQQ/IWM (the registered row). Extending to lane-2 names needs its
    own ledger row (pending opts-fix-lane2-rvol-scale-v1's source decision).

Scheduled as ATLAS-CacheRefresh, daily 15:35 CT (register_mesh_tasks.ps1); safe
no-op on weekends/holidays.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO / "runtime" / "intraday_cache"
LOG_PATH = REPO / "runtime" / "cache_refresh.log"
ET = ZoneInfo("America/New_York")
DEFAULT_SYMBOLS = "SPY,QQQ,IWM"
RTH_START, RTH_END = "09:30", "15:59"          # must mirror intraday_data.py's window
MIN_BARS_WARN = 30                             # build_noise_profile drops <30-bar sessions


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def missing_sessions(last_cached: date, now_et: datetime, *, days=None) -> list[date]:
    """Trading days strictly after `last_cached` whose session has ALREADY CLOSED at
    `now_et`. Pure when `days` (session-calendar mapping) is injected. Today counts
    only past its own close_min - half days close early, so a 15:35 CT run after a
    13:00 ET half-day close still appends it, but a mid-session run never does."""
    from atlas.options import session_calendar as scal

    out: list[date] = []
    today = now_et.date()
    now_min = now_et.hour * 60 + now_et.minute
    d = last_cached + timedelta(days=1)
    while d <= today:
        if scal.is_trading_day(d, days=days):
            if d < today or now_min >= scal.session_close_minute(d, days=days):
                out.append(d)
        d += timedelta(days=1)
    return out


def refresh_symbol(sym: str, now_et: datetime, days, *, dry_run: bool = False) -> str:
    """Refresh one symbol's parquet; returns a one-line status. Never raises past
    its own try (caller wraps anyway); never writes except the final atomic replace."""
    import pandas as pd

    from atlas.collect import intraday_data as idata
    from atlas.fsutil import atomic_replace

    p = CACHE_DIR / f"{sym}_1min.parquet"
    if not p.exists():
        return "no cache file - first build is fetch_intraday.py's job; skipped"
    old = pd.read_parquet(p)
    if old.empty:
        return "cache file empty - skipped"
    last_ts = old.index[-1]
    todo = missing_sessions(last_ts.date(), now_et, days=days)
    if not todo:
        return f"up to date (last bar {last_ts})"
    if dry_run:
        return f"DRY RUN: would fetch {todo[0]}..{todo[-1]} ({len(todo)} session(s))"
    # end is midnight-exclusive in fetch_intraday_bars -> +1 day to include todo[-1]
    new = idata.fetch_intraday_bars(sym, start=todo[0], end=todo[-1] + timedelta(days=1))
    if new.empty:
        return (f"fetch returned EMPTY for {todo[0]}..{todo[-1]} - skipped "
                "(fail-open; Alpaca serves years back, next run catches up)")
    merged = idata.merge_1min(old, new)
    appended = merged[merged.index > last_ts]
    # sanity gates - refuse the write rather than corrupt the cache
    if len(appended) == 0 or len(merged) <= len(old):
        return "no new rows after merge - nothing to write"
    if not merged.index.is_monotonic_increasing:
        return "REFUSED write: merged index not monotonic"
    if len(appended.between_time(RTH_START, RTH_END)) != len(appended):
        return "REFUSED write: appended rows outside 09:30-15:59 ET"
    per_day = appended.groupby(appended.index.normalize()).size()
    thin = {str(d.date()): int(n) for d, n in per_day.items() if n < MIN_BARS_WARN}
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    try:
        merged.to_parquet(tmp)
        atomic_replace(tmp, p)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    note = f"; THIN sessions (<{MIN_BARS_WARN} bars, profile will drop them): {thin}" if thin else ""
    return (f"appended {len(appended)} rows across {len(per_day)} session(s) "
            f"({todo[0]}..{todo[-1]}); last bar now {merged.index[-1]}{note}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Append closed sessions' 1-min IEX bars to the intraday cache.")
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS,
                    help=f"comma-separated (default {DEFAULT_SYMBOLS} - the registered scope)")
    ap.add_argument("--dry-run", action="store_true", help="print planned appends, write nothing")
    ap.add_argument("--skip-harvest", action="store_true",
                    help="do not also run harvest --daily-append (opts-fix-harvest-daily-append-v1)")
    args = ap.parse_args(argv)
    try:
        from atlas.options import session_calendar as scal
        now_et = datetime.now(ET)
        days = scal.load_days()                    # fail-open at every layer inside
        for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
            try:
                log(f"{sym}: {refresh_symbol(sym, now_et, days, dry_run=args.dry_run)}")
            except Exception as exc:  # noqa: BLE001 - one symbol never blocks the rest
                log(f"{sym}: ERROR (tolerated, cache untouched): {exc!r}")
    except Exception as exc:  # noqa: BLE001 - a scheduled chain must never see nonzero
        log(f"FATAL (tolerated): {exc!r}")
    # Fold the harvest daily-append (opts-fix-harvest-daily-append-v1) into this nightly task so it
    # shares ATLAS-CacheRefresh instead of a new schtask. Incremental + idempotent + batched (~fast);
    # best-effort - a scheduled chain must never see a nonzero exit.
    if not args.skip_harvest and not args.dry_run:
        try:
            import subprocess
            _repo = Path(__file__).resolve().parents[1]
            r = subprocess.run([sys.executable, str(_repo / "scripts" / "harvest_inplay_days.py"),
                                "--daily-append"], cwd=str(_repo), capture_output=True, text=True,
                               timeout=1800.0)
            log(f"harvest --daily-append: {'ok' if r.returncode == 0 else 'rc=' + str(r.returncode)}")
        except Exception as exc:  # noqa: BLE001 - never fails the cache-refresh chain
            log(f"harvest --daily-append: ERROR (tolerated): {exc!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
