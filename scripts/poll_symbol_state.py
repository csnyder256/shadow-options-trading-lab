"""poll_symbol_state (opts-svc-symbol-state-poller-v1, mission reincorporate-cut-systems): poll the
nasdaqtrader trading-HALT RSS and write runtime/symbol_state.json, so the options selector's halt
DATA-VALIDITY gate (opts-ws3-halt-gate-v1) has a LIVE data source. Launcher-scoped, fail-open
(SymbolStatePoller.poll never raises; a torn state file never crashes anything), NO account
awareness, NO AI, off the trading loop.

SEC suspensions are OFF in v1 - they need an EntityResolver name->ticker map (a follow-up);
halts (the primary intraday risk) carry their own tickers from the feed and need no resolver.

  .venv\\Scripts\\python.exe scripts\\poll_symbol_state.py --once
  .venv\\Scripts\\python.exe scripts\\poll_symbol_state.py --poll-seconds 45   # loop (launcher)
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from atlas.collect.symbol_state import SymbolStateParams, SymbolStatePoller  # noqa: E402
from atlas.config_loader import FRAMEWORK_ROOT  # noqa: E402

STATE = FRAMEWORK_ROOT / "runtime" / "symbol_state.json"


def _now() -> tuple[str, float]:
    dt = datetime.now(timezone.utc)
    return dt.isoformat(), dt.timestamp()


def _make_poller(state_path: str) -> SymbolStatePoller:
    params = SymbolStateParams(enabled=True, poll_every_cycles=1, halt_rss=True,
                               sec_suspensions=False, ssr_self_compute=False)  # halt-only v1
    return SymbolStatePoller(params, resolver=None, state_path=state_path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ATLAS symbol-state poller (trading halts -> symbol_state.json)")
    ap.add_argument("--once", action="store_true", help="single poll then exit")
    ap.add_argument("--poll-seconds", type=float, default=45.0)
    ap.add_argument("--state", default=str(STATE))
    args = ap.parse_args(argv)

    poller = _make_poller(args.state)
    if args.once:
        now_iso, now_epoch = _now()
        poller.poll(now_iso, now_epoch, cycle=0)
        print(f"symbol_state: halts={len(poller.halts)} suspensions={len(poller.suspensions)} "
              f"-> {args.state}")
        return 0

    cycle = 0
    while True:
        try:
            now_iso, now_epoch = _now()
            poller.poll(now_iso, now_epoch, cycle=cycle)
        except Exception as exc:  # noqa: BLE001 - the poller itself is fail-open; this is a backstop
            print("symbol_state poll error:", repr(exc), flush=True)
        cycle += 1
        time.sleep(max(5.0, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
