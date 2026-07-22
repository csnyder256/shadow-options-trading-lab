"""Populate the intraday 1-min bar cache (Alpaca IEX) for the volatile intraday universe (M8).

  .venv\\Scripts\\python.exe scripts\\fetch_intraday.py --start-year 2024

Proof artifact: real (non-interpolated) 1-min RTH bars cached to runtime/intraday_cache/, with a coverage
report (symbols, total bars, avg bars/session, date range). This is the data foundation for the intraday
dip-and-pop backtest (M9/M10).
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import yaml

from atlas.collect import intraday_data as idata  # relocated from atlas.backtest (2026-07-10 pivot)
from atlas.config_loader import FRAMEWORK_ROOT

CACHE = FRAMEWORK_ROOT / "runtime" / "intraday_cache"


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch + cache intraday 1-min bars (Alpaca IEX)")
    ap.add_argument("--start-year", type=int, default=2024)
    ap.add_argument("--start-month", type=int, default=7)
    ap.add_argument("--max-symbols", type=int, default=0, help="0 = all")
    ap.add_argument("--symbols-file", default="",
                    help="newline-delimited symbol list (e.g. runtime/harvest/inplay_symbols.txt); "
                         "overrides config/intraday_universe.yaml")
    args = ap.parse_args()

    if args.symbols_file:
        raw = Path(args.symbols_file).read_text("utf-8").split()
    else:
        uni = yaml.safe_load((FRAMEWORK_ROOT / "config" / "intraday_universe.yaml").read_text("utf-8"))
        raw = uni["intraday_symbols"]
    # str() defends against a bare YAML boolean (ON/OFF/YES/NO) slipping through unquoted; upper for safety.
    syms = list(dict.fromkeys(str(s).upper() for s in raw))    # de-dup, preserve order
    if args.max_symbols:
        syms = syms[: args.max_symbols]
    start = date(args.start_year, args.start_month, 1)
    end = date.today()
    print(f"Fetching 1-min IEX bars for {len(syms)} symbols, {start} -> {end} ...", flush=True)

    ok, empty, rows = [], [], []
    for i, s in enumerate(syms):
        df = idata.load_or_fetch(s, start, end, cache_dir=CACHE)
        if df.empty:
            empty.append(s)
            print(f"  [{i+1}/{len(syms)}] {s}: EMPTY", flush=True)
            continue
        n = len(df)
        n_days = df.index.normalize().nunique()
        d0, d1 = df.index[0].date(), df.index[-1].date()
        interp = 0                                               # Alpaca IEX has no interpolated flag; realness
        flat = int((df["high"] == df["low"]).sum())             # a proxy: fully-flat (h==l) bars = thin minutes
        ok.append(s)
        rows.append((s, n, n / max(n_days, 1), n_days, d0, d1, flat))
        print(f"  [{i+1}/{len(syms)}] {s}: {n} bars over {n_days} sessions "
              f"({n/max(n_days,1):.0f}/day), {d0}..{d1}, flat-min {flat}", flush=True)

    print("\n" + "=" * 78)
    print(f"  INTRADAY CACHE COVERAGE: {len(ok)}/{len(syms)} symbols with data; {len(empty)} empty")
    if rows:
        tot = sum(r[1] for r in rows)
        avgday = sum(r[2] for r in rows) / len(rows)
        print(f"  total bars {tot:,} | avg {avgday:.0f} bars/session | cache {CACHE}")
    if empty:
        print(f"  EMPTY (no IEX data): {', '.join(str(x) for x in empty)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
