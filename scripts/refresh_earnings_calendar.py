"""Premarket earnings-calendar refresh (Finnhub) -> runtime/earnings_week.json.

    PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\refresh_earnings_calendar.py [--days 7]

Feeds strategy-lab earnings strategies (earnings_iv_crush_strangle, pre_earnings_long_straddle).
M0 viability V3 finding: Finnhub `hour` is EMPTY on ~39% of all rows (small caps dominate) - 
so rows without hour in {bmo, amc} are kept but flagged `timing_reliable: false`; the
strategies' universe screens REQUIRE timing_reliable (plus the RH high-market-cap cross-check
at EOD truth-validation time, per docs/strategies/SOURCE_VIABILITY.md consequence 5).

Fail-open + exit 0 (scheduled-chain law): on any failure yesterday's file stands, with its
own `generated` stamp for staleness checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.config_loader import FRAMEWORK_ROOT  # noqa: E402
from atlas.fsutil import atomic_replace  # noqa: E402

OUT_PATH = FRAMEWORK_ROOT / "runtime" / "earnings_week.json"


def _finnhub_key() -> str:
    p = FRAMEWORK_ROOT / "config" / "credentials.local.yaml"
    try:
        cfg = yaml.safe_load(p.read_text(encoding="utf-8-sig")) or {}
        return str(((cfg.get("finnhub") or {}).get("api_key")) or "").strip()
    except (OSError, yaml.YAMLError):
        return ""


def fetch_calendar(key: str, start: date, end: date) -> list:
    r = httpx.get("https://finnhub.io/api/v1/calendar/earnings",
                  params={"from": start.isoformat(), "to": end.isoformat(), "token": key},
                  timeout=30)
    r.raise_for_status()
    return (r.json() or {}).get("earningsCalendar") or []


def normalize(rows: list) -> dict:
    """{symbol: {date, hour, timing_reliable, eps_estimate}} - one row per symbol (earliest
    upcoming report wins on duplicates)."""
    out: dict[str, dict] = {}
    for x in sorted(rows, key=lambda r: str(r.get("date") or "9999")):
        sym = str(x.get("symbol") or "").upper()
        if not sym or sym in out:
            continue
        hour = str(x.get("hour") or "").strip().lower()
        out[sym] = {"date": str(x.get("date") or ""), "hour": hour,
                    "timing_reliable": hour in ("bmo", "amc"),
                    "eps_estimate": x.get("epsEstimate")}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Refresh the week-ahead earnings calendar")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args(argv)

    key = _finnhub_key()
    if not key:
        print("[earnings] no finnhub key - keeping prior file", flush=True)
        return 0
    today = date.today()
    try:
        rows = fetch_calendar(key, today, today + timedelta(days=args.days))
    except Exception as exc:  # noqa: BLE001 - fail-open
        print(f"[earnings] fetch failed: {type(exc).__name__}: {exc} - keeping prior file",
              flush=True)
        return 0
    by_symbol = normalize(rows)
    reliable = sum(1 for v in by_symbol.values() if v["timing_reliable"])
    payload = {"generated": today.isoformat(), "window_days": args.days,
               "n_symbols": len(by_symbol), "n_timing_reliable": reliable,
               "by_symbol": by_symbol}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    atomic_replace(tmp, OUT_PATH)
    print(f"[earnings] {len(by_symbol)} symbols ({reliable} timing-reliable) through "
          f"{(today + timedelta(days=args.days)).isoformat()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
