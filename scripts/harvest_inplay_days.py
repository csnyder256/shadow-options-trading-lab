"""Harvest historical IN-PLAY name-days for the Floor Hunter replay gate (P0b).

  PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\harvest_inplay_days.py --screen-start 2024-07-01

Three stages, all resumable (per-symbol parquet cache + dead-list):
  1. Asset list from Alpaca (ACTIVE + INACTIVE for survivorship accounting), filtered to plain
     US-equity commons.
  2. Batched DAILY bars (Alpaca IEX, multi-symbol requests) into runtime/harvest_daily_cache/.
  3. Causal screen for in-play name-days:
       open >= $5  AND  20d-median dollar-vol (shifted) >= $10M  AND
       ( gap% = open/prev_close - 1 >= +4%  OR  volume >= 3x 20d-median volume (shifted) )
     Full-day RVOL here is HARVEST-ONLY (decides what 1-min data to fetch) - the replay engine
     re-derives in-play status causally (by-minute volume pace), never from this screen.

Outputs (runtime/harvest/):
  inplay_name_days.json   {"SESSION": [{symbol, gap_pct, vol_mult, dollar_vol20, rank}, ...]}
  inplay_symbols.txt      symbols with >= --min-hits name-days (feed to fetch_intraday --symbols-file)
  harvest_report.json     counts incl. INACTIVE (delisted) coverage for the survivorship note

Survivorship honesty: INACTIVE assets are attempted too; the report separates their coverage so the
replay gate can quantify (not hide) the missing-delisted bias.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

from atlas.config_loader import FRAMEWORK_ROOT

HARVEST_DIR = FRAMEWORK_ROOT / "runtime" / "harvest"
DAILY_CACHE = FRAMEWORK_ROOT / "runtime" / "harvest_daily_cache"

_PLAIN_SYMBOL = re.compile(r"^[A-Z]{1,5}$")     # skip units/warrants/preferreds (dots, dashes, digits)
_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL"}    # DOS device names; SYMBOL.parquet would open the device


def _daily_path(sym: str) -> Path:
    stem = f"{sym}_RES" if sym.upper() in _WIN_RESERVED else sym
    return DAILY_CACHE / f"{stem}.parquet"


def _creds() -> dict:
    return yaml.safe_load(
        (FRAMEWORK_ROOT / "config" / "credentials.local.yaml").read_text("utf-8"))["alpaca"]


def list_assets(include_inactive: bool) -> tuple[list[str], list[str]]:
    """(active, inactive) plain-common US-equity symbols from Alpaca."""
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import AssetClass, AssetStatus
    from alpaca.trading.requests import GetAssetsRequest

    c = _creds()
    tc = TradingClient(c["api_key"], c["secret_key"], paper=True)

    def _pull(status: AssetStatus) -> list[str]:
        assets = tc.get_all_assets(GetAssetsRequest(status=status, asset_class=AssetClass.US_EQUITY))
        out = []
        for a in assets:
            sym = str(a.symbol)
            if not _PLAIN_SYMBOL.match(sym):
                continue
            exch = str(getattr(a, "exchange", "") or "")
            if exch.upper() in ("OTC",):
                continue
            out.append(sym)
        return sorted(set(out))

    active = _pull(AssetStatus.ACTIVE)
    inactive = _pull(AssetStatus.INACTIVE) if include_inactive else []
    return active, [s for s in inactive if s not in set(active)]


def fetch_daily_batched(symbols: list[str], start: date, end: date, *, chunk: int = 200) -> dict[str, int]:
    """Batched Alpaca IEX daily bars -> per-symbol parquet in DAILY_CACHE. Resumable: cached symbols
    and known-dead symbols are skipped. Returns {"fetched": n, "cached": n, "dead": n}."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    DAILY_CACHE.mkdir(parents=True, exist_ok=True)
    dead_path = DAILY_CACHE / "_unavailable.json"
    dead: set[str] = set(json.loads(dead_path.read_text())) if dead_path.exists() else set()

    need = [s for s in symbols if not _daily_path(s).exists() and s not in dead]
    cached = len(symbols) - len(need) - len([s for s in symbols if s in dead])
    if not need:
        return {"fetched": 0, "cached": cached, "dead": len(dead & set(symbols))}

    c = _creds()
    dc = StockHistoricalDataClient(c["api_key"], c["secret_key"])
    fetched = 0
    for i in range(0, len(need), chunk):
        batch = need[i:i + chunk]
        try:
            req = StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day,
                                   start=datetime(start.year, start.month, start.day),
                                   end=datetime(end.year, end.month, end.day), feed=DataFeed.IEX)
            data = dc.get_stock_bars(req).data
        except Exception as e:  # one bad batch must not kill an hours-long run
            print(f"  batch {i//chunk}: ERROR {type(e).__name__}: {e}", flush=True)
            continue
        got = set()
        for sym in batch:
            bars = data.get(sym, [])
            if not bars:
                continue
            df = pd.DataFrame({
                "open": [float(b.open) for b in bars], "high": [float(b.high) for b in bars],
                "low": [float(b.low) for b in bars], "close": [float(b.close) for b in bars],
                "volume": [float(b.volume) for b in bars],
            }, index=pd.DatetimeIndex([b.timestamp for b in bars]).tz_localize(None).normalize())
            df = df[~df.index.duplicated(keep="last")].sort_index()
            try:
                df.to_parquet(_daily_path(sym))
            except OSError as e:              # one unwritable symbol must not kill an hours-long run
                print(f"  {sym}: WRITE FAILED {e}", flush=True)
                continue
            got.add(sym)
            fetched += 1
        dead |= set(batch) - got
        dead_path.write_text(json.dumps(sorted(dead)))
        print(f"  batch {i//chunk + 1}/{(len(need)+chunk-1)//chunk}: +{len(got)} symbols "
              f"({fetched} total)", flush=True)
    return {"fetched": fetched, "cached": cached, "dead": len(dead & set(symbols))}


def screen_symbol(sym: str, screen_start: date, *, min_price: float, max_price: float,
                  min_dollar_vol: float, gap_min: float, vol_mult_min: float) -> list[dict]:
    """Causal in-play screen over one symbol's cached dailies. All rolling stats are SHIFTED
    (yesterday's trailing window) so every input is knowable at the session open."""
    fp = _daily_path(sym)
    if not fp.exists():
        return []
    try:
        df = pd.read_parquet(fp)
    except Exception:
        return []
    if len(df) < 25:
        return []
    prev_close = df["close"].shift(1)
    gap = (df["open"] / prev_close - 1.0) * 100.0
    med_vol20 = df["volume"].rolling(20).median().shift(1)
    med_dvol20 = (df["close"] * df["volume"]).rolling(20).median().shift(1)
    vol_mult = df["volume"] / med_vol20
    elig = ((df.index >= pd.Timestamp(screen_start))
            & (df["open"] >= min_price) & (df["open"] <= max_price)
            & (med_dvol20 >= min_dollar_vol)
            & ((gap >= gap_min) | (vol_mult >= vol_mult_min)))
    out = []
    for ts in df.index[elig]:
        out.append({
            "symbol": sym, "session": ts.date().isoformat(),
            "gap_pct": round(float(gap.loc[ts]), 2),
            "vol_mult": round(float(vol_mult.loc[ts]), 2) if pd.notna(vol_mult.loc[ts]) else None,
            "dollar_vol20": int(med_dvol20.loc[ts]),
            "range_pct": round(float((df["high"].loc[ts] / df["low"].loc[ts] - 1.0) * 100.0), 2),
        })
    return out


# --------------------------------------------------------------------------- #
# DAILY-APPEND mode (opts-fix-harvest-daily-append-v1): incremental nightly update of the
# already-cached symbols, mirroring scripts/refresh_intraday_cache.py's multi-day catch-up. Unlike
# the full backfill (which re-lists the entire Alpaca universe over an hours-long run), this updates
# only symbols already in DAILY_CACHE and screens only the newly-appended sessions - idempotent,
# bounded, and schedule-friendly (ATLAS-Harvest nightly). New listings are picked up by a periodic
# full backfill, not here.
# --------------------------------------------------------------------------- #

def _cached_symbols() -> list[str]:
    """Symbols with a parquet already in DAILY_CACHE (reversing the _RES reserved-name suffix)."""
    out: list[str] = []
    for p in DAILY_CACHE.glob("*.parquet"):
        stem = p.stem
        out.append(stem[:-4] if stem.endswith("_RES") else stem)
    return sorted(set(out))


def _append_bars_to_cache(sym: str, df_new: pd.DataFrame) -> set[date]:
    """Merge df_new (date-indexed OHLCV) into sym's parquet: keep existing dates, drop duplicate
    dates keep=last, sort. Returns the set of session dates NEWLY added (empty => no-op / idempotent)."""
    if df_new is None or df_new.empty:
        return set()
    df_new = df_new[~df_new.index.duplicated(keep="last")].sort_index()
    path = _daily_path(sym)
    existing = None
    if path.exists():
        try:
            existing = pd.read_parquet(path)
        except Exception:
            existing = None
    if existing is not None and not existing.empty:
        added_idx = df_new.index.difference(existing.index)
        if len(added_idx) == 0:
            return set()
        merged = pd.concat([existing, df_new])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
    else:
        added_idx = df_new.index
        merged = df_new
    try:
        merged.to_parquet(path)
    except OSError as e:                      # one unwritable symbol must not kill the nightly run
        print(f"  {sym}: APPEND WRITE FAILED {e}", flush=True)
        return set()
    return {ts.date() for ts in added_idx}


def fetch_daily_append(symbols: list[str], start: date, end: date, *, chunk: int = 200) -> set[date]:
    """Fetch [start,end] daily bars for already-cached symbols and APPEND new dates to each parquet.
    Returns the union of session dates newly added across all symbols. Fail-open per batch/symbol."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    DAILY_CACHE.mkdir(parents=True, exist_ok=True)
    c = _creds()
    dc = StockHistoricalDataClient(c["api_key"], c["secret_key"])
    new_sessions: set[date] = set()
    for i in range(0, len(symbols), chunk):
        batch = symbols[i:i + chunk]
        try:
            req = StockBarsRequest(symbol_or_symbols=batch, timeframe=TimeFrame.Day,
                                   start=datetime(start.year, start.month, start.day),
                                   end=datetime(end.year, end.month, end.day), feed=DataFeed.IEX)
            data = dc.get_stock_bars(req).data
        except Exception as e:
            print(f"  append batch {i//chunk}: ERROR {type(e).__name__}: {e}", flush=True)
            continue
        for sym in batch:
            bars = data.get(sym, [])
            if not bars:
                continue
            df = pd.DataFrame({
                "open": [float(b.open) for b in bars], "high": [float(b.high) for b in bars],
                "low": [float(b.low) for b in bars], "close": [float(b.close) for b in bars],
                "volume": [float(b.volume) for b in bars],
            }, index=pd.DatetimeIndex([b.timestamp for b in bars]).tz_localize(None).normalize())
            new_sessions |= _append_bars_to_cache(sym, df)
    return new_sessions


def run_daily_append(args, *, fetch_fn=None) -> int:
    """Nightly incremental update: append the latest session(s) to the cached symbols, then screen
    ONLY the newly-added sessions and merge them into inplay_name_days.json. Idempotent + fail-open."""
    fetch_fn = fetch_fn or fetch_daily_append
    cached = _cached_symbols()
    if not cached:
        print("daily-append: DAILY_CACHE is empty - run a full backfill first", flush=True)
        return 1
    end = date.today()
    start = end - timedelta(days=max(1, args.catchup_days))
    print(f"[append] {len(cached)} cached symbols; catch-up window {start} -> {end}", flush=True)
    new_sessions = fetch_fn(cached, start, end)
    if not new_sessions:
        print("daily-append: no new sessions (cache already current)", flush=True)
        return 0
    new_iso = {d.isoformat() for d in new_sessions}
    screen_from = min(new_sessions)
    fresh: dict[str, list[dict]] = {}
    for sym in cached:
        for r in screen_symbol(sym, screen_from, min_price=args.min_price, max_price=args.max_price,
                               min_dollar_vol=args.min_dollar_vol, gap_min=args.gap_min,
                               vol_mult_min=args.vol_mult_min):
            if r["session"] in new_iso:                      # only the just-appended sessions
                r["delisted"] = False
                fresh.setdefault(r["session"], []).append(r)
    for sess, rows in fresh.items():
        rows.sort(key=lambda r: max(r["gap_pct"] or 0.0, (r["vol_mult"] or 0.0) * 1.5), reverse=True)
        for k, r in enumerate(rows):
            r["rank"] = k + 1
        fresh[sess] = rows[: args.per_day_cap]

    HARVEST_DIR.mkdir(parents=True, exist_ok=True)
    path = HARVEST_DIR / "inplay_name_days.json"
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            existing = {}
    existing.update(fresh)                                    # new sessions overwrite (idempotent)
    path.write_text(json.dumps(dict(sorted(existing.items())), indent=1))

    sym_hits: dict[str, int] = {}
    for rows in existing.values():
        for r in rows:
            sym_hits[r["symbol"]] = sym_hits.get(r["symbol"], 0) + 1
    fetch_syms = sorted(s for s, n in sym_hits.items() if n >= args.min_hits)
    (HARVEST_DIR / "inplay_symbols.txt").write_text("\n".join(fetch_syms) + "\n")
    print(f"[append] +{sum(len(v) for v in fresh.values())} name-days over {len(fresh)} new "
          f"session(s): {sorted(new_iso)}", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Harvest in-play name-days for the Floor Hunter replay gate")
    ap.add_argument("--screen-start", default="2024-07-01")
    ap.add_argument("--min-price", type=float, default=5.0)
    ap.add_argument("--max-price", type=float, default=500.0)
    ap.add_argument("--min-dollar-vol", type=float, default=10_000_000.0)
    ap.add_argument("--gap-min", type=float, default=4.0)
    ap.add_argument("--vol-mult-min", type=float, default=3.0)
    ap.add_argument("--per-day-cap", type=int, default=8, help="fetch-manifest attention cap per session")
    ap.add_argument("--min-hits", type=int, default=2, help="name-day hits for a symbol to enter the 1-min fetch list")
    ap.add_argument("--no-inactive", action="store_true", help="skip delisted (survivorship accounting off)")
    ap.add_argument("--max-symbols", type=int, default=0, help="debug: cap the asset list (0 = all)")
    ap.add_argument("--daily-append", action="store_true",
                    help="incremental nightly update of cached symbols + screen new sessions (ATLAS-Harvest)")
    ap.add_argument("--catchup-days", type=int, default=7, help="daily-append catch-up window in days")
    args = ap.parse_args()

    if args.daily_append:
        return run_daily_append(args)

    screen_start = date.fromisoformat(args.screen_start)
    fetch_start = screen_start - timedelta(days=45)          # 20-session rolling warmup + slack
    end = date.today()
    HARVEST_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/3] Listing Alpaca US-equity assets ...", flush=True)
    active, inactive = list_assets(include_inactive=not args.no_inactive)
    if args.max_symbols:
        active, inactive = active[: args.max_symbols], inactive[: max(0, args.max_symbols // 10)]
    print(f"  active={len(active)} inactive(delisted)={len(inactive)}", flush=True)

    print(f"[2/3] Daily bars {fetch_start} -> {end} (batched, resumable) ...", flush=True)
    cov_a = fetch_daily_batched(active, fetch_start, end)
    cov_i = fetch_daily_batched(inactive, fetch_start, end) if inactive else {"fetched": 0, "cached": 0, "dead": 0}
    print(f"  ACTIVE {cov_a} | INACTIVE {cov_i}", flush=True)

    print("[3/3] Screening name-days ...", flush=True)
    hits: list[dict] = []
    inactive_set = set(inactive)
    for j, sym in enumerate(active + inactive):
        rows = screen_symbol(sym, screen_start, min_price=args.min_price, max_price=args.max_price,
                             min_dollar_vol=args.min_dollar_vol, gap_min=args.gap_min,
                             vol_mult_min=args.vol_mult_min)
        for r in rows:
            r["delisted"] = sym in inactive_set
        hits.extend(rows)
        if (j + 1) % 1000 == 0:
            print(f"  screened {j+1} symbols, {len(hits)} hits so far", flush=True)

    by_session: dict[str, list[dict]] = {}
    for r in hits:
        by_session.setdefault(r["session"], []).append(r)
    for sess, rows in by_session.items():
        rows.sort(key=lambda r: max(r["gap_pct"] or 0.0, (r["vol_mult"] or 0.0) * 1.5), reverse=True)
        for k, r in enumerate(rows):
            r["rank"] = k + 1
        by_session[sess] = rows[: args.per_day_cap]

    kept = [r for rows in by_session.values() for r in rows]
    sym_hits: dict[str, int] = {}
    for r in kept:
        sym_hits[r["symbol"]] = sym_hits.get(r["symbol"], 0) + 1
    fetch_syms = sorted(s for s, n in sym_hits.items() if n >= args.min_hits)

    (HARVEST_DIR / "inplay_name_days.json").write_text(
        json.dumps(dict(sorted(by_session.items())), indent=1))
    (HARVEST_DIR / "inplay_symbols.txt").write_text("\n".join(fetch_syms) + "\n")
    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "params": vars(args), "sessions": len(by_session),
        "name_days_raw": len(hits), "name_days_kept": len(kept),
        "name_days_delisted": sum(1 for r in kept if r["delisted"]),
        "symbols_in_fetch_list": len(fetch_syms),
        "active_assets": len(active), "inactive_assets": len(inactive),
        "daily_coverage": {"active": cov_a, "inactive": cov_i},
    }
    (HARVEST_DIR / "harvest_report.json").write_text(json.dumps(report, indent=1))

    print("\n" + "=" * 78)
    print(f"  IN-PLAY HARVEST: {len(kept)} name-days over {len(by_session)} sessions "
          f"({report['name_days_delisted']} on delisted names)")
    print(f"  1-min fetch list: {len(fetch_syms)} symbols (>= {args.min_hits} hits) "
          f"-> {HARVEST_DIR / 'inplay_symbols.txt'}")
    print(f"  next: PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\fetch_intraday.py "
          f"--symbols-file runtime/harvest/inplay_symbols.txt --start-year {screen_start.year} "
          f"--start-month {max(1, screen_start.month - 1)}")
    return 0 if kept else 1


if __name__ == "__main__":
    raise SystemExit(main())
