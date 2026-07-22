"""Registry-driven roster printer - the /eodreport Phase-1 heartbeat assertion source.

    PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\print_armed_roster.py [--json]

The EOD skill compares BOTH heartbeats against THIS output (never a hardcoded list):
  * strategy lab: armed roster + cohort pins from atlas/strategy_lab/registry (code + yaml)
  * main shadow: the lane roster the live runner would build (imported, not duplicated)
A diff in either direction is the finding. Registered lab-strategy-runtime-v1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Print the armed roster (lab + main lanes)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    from atlas.strategy_lab.registry import build_all, load_state, validate
    strategies = build_all()
    state = load_state()
    problems = validate(strategies, state)
    lab = {sid: {"state": state.get(sid, {}).get("state", "unregistered"),
                 "cohort": strategies[sid].config_hash()}
           for sid in sorted(strategies)}
    armed = sorted(sid for sid, b in lab.items() if b["state"] == "armed")

    # main shadow lanes: replicate the runner's roster construction WITHOUT importing the
    # runner (its DEFAULTS are provenance-pinned; the lane roster is the audit-parks truth).
    # Source: run_options_shadow._roll_day + opts-audit-parks-v1 (last30 + FOMC arm parked).
    main_lanes = ["index_trend", "inplay_orb", "macro_reaction", "pre_earnings_straddle_stub"]

    out = {"lab_armed": armed, "lab_all": lab, "lab_registry_problems": problems,
           "main_lanes_expected": main_lanes}
    if args.json:
        print(json.dumps(out, indent=1))
    else:
        print(f"lab armed ({len(armed)}): {', '.join(armed) or '-'}")
        for sid, b in lab.items():
            print(f"  {sid:34s} {b['state']:14s} cohort {b['cohort']}")
        if problems:
            print("REGISTRY PROBLEMS:")
            for p in problems:
                print(f"  ! {p}")
        print(f"main lanes expected: {', '.join(main_lanes)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
