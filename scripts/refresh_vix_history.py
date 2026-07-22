"""Nightly CBOE VIX-family refresh (keyless) -> runtime/vix_history/*.csv + runtime/vol_regime.json.

    PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\refresh_vix_history.py [--once]

Registered under lab-strategy-runtime-v1 (M0 viability V4: all three CSVs HTTP 200, current,
~36yr VIX depth). The derived vol_regime.json is the strategy lab's IV-RANK FALLBACK LADDER
rung 2: iv_rank (options_iv.db, needs >=60 sessions/tenor - cold until ~Oct-2026) ->
VIX 252d percentile (THIS file, full depth on day one) -> ungated + gate_unavailable log.
Mapping IVR>30 gate ~= VIX percentile > 30 is an ADAPTED constant, tagged in each brief.

Fail-open + exit 0 always (scheduled-chain law): a dead CBOE endpoint leaves yesterday's
files in place and vol_regime.json carries its own asof for staleness checks downstream.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.config_loader import FRAMEWORK_ROOT  # noqa: E402
from atlas.fsutil import atomic_replace  # noqa: E402

CBOE_BASE = "https://cdn.cboe.com/api/global/us_indices/daily_prices"
FILES = ("VIX_History.csv", "VIX3M_History.csv", "VIX1D_History.csv")
OUT_DIR = FRAMEWORK_ROOT / "runtime" / "vix_history"
REGIME_PATH = FRAMEWORK_ROOT / "runtime" / "vol_regime.json"
PCTILE_WINDOW = 252


def parse_csv(text: str) -> list:
    """[(iso_date, close)] from CBOE 'DATE,OPEN,HIGH,LOW,CLOSE' rows (M/D/YYYY dates)."""
    out = []
    for line in text.strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            m, d, y = parts[0].split("/")
            out.append((f"{int(y):04d}-{int(m):02d}-{int(d):02d}", float(parts[4])))
        except (ValueError, IndexError):
            continue
    return sorted(out)


def pctile_252(closes: list, value: float) -> float | None:
    window = closes[-PCTILE_WINDOW:]
    if len(window) < 60:
        return None
    return round(100.0 * sum(1 for c in window if c <= value) / len(window), 1)


def build_regime(series: dict) -> dict:
    vix = series.get("VIX_History.csv") or []
    vix3m = series.get("VIX3M_History.csv") or []
    vix1d = series.get("VIX1D_History.csv") or []
    out = {"asof": None, "vix_close": None, "vix_pctile_252d": None,
           "vix3m_close": None, "vix_vix3m_ratio": None, "vix1d_close": None,
           "generated": datetime.now().isoformat(timespec="seconds")}
    if vix:
        day, close = vix[-1]
        out["asof"] = day
        out["vix_close"] = close
        out["vix_pctile_252d"] = pctile_252([c for _, c in vix], close)
    if vix3m:
        out["vix3m_close"] = vix3m[-1][1]
        if out["vix_close"] and vix3m[-1][1] > 0:
            out["vix_vix3m_ratio"] = round(out["vix_close"] / vix3m[-1][1], 4)
    if vix1d:
        out["vix1d_close"] = vix1d[-1][1]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Refresh CBOE VIX-family history + vol regime")
    ap.add_argument("--once", action="store_true", help="(compat; always one pass)")
    ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    series: dict[str, list] = {}
    for name in FILES:
        try:
            r = httpx.get(f"{CBOE_BASE}/{name}", timeout=30, follow_redirects=True)
            if r.status_code != 200 or "DATE" not in r.text[:100].upper():
                print(f"[vix] {name}: HTTP {r.status_code} - keeping prior file", flush=True)
                series[name] = parse_csv((OUT_DIR / name).read_text(encoding="utf-8")) \
                    if (OUT_DIR / name).exists() else []
                continue
            tmp = OUT_DIR / (name + ".tmp")
            tmp.write_text(r.text, encoding="utf-8")
            atomic_replace(tmp, OUT_DIR / name)
            series[name] = parse_csv(r.text)
            print(f"[vix] {name}: {len(series[name])} rows through "
                  f"{series[name][-1][0] if series[name] else '?'}", flush=True)
        except Exception as exc:  # noqa: BLE001 - fail-open, keep prior file
            print(f"[vix] {name}: {type(exc).__name__}: {exc} - keeping prior file", flush=True)
            series[name] = parse_csv((OUT_DIR / name).read_text(encoding="utf-8")) \
                if (OUT_DIR / name).exists() else []

    regime = build_regime(series)
    tmp = REGIME_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(regime, indent=1) + "\n", encoding="utf-8")
    atomic_replace(tmp, REGIME_PATH)
    print(f"[vix] vol_regime: asof={regime['asof']} vix={regime['vix_close']} "
          f"pctile={regime['vix_pctile_252d']} ratio={regime['vix_vix3m_ratio']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
