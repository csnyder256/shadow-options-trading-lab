"""enrich_catalyst_context (opts-catmem-covariates-v1, mission reincorporate-cut-systems):
premarket, translate each hunt-list catalyst into historical forward-move CONTEXT via
catalyst_memory.recall(kind, direction), and write runtime/catalyst_context.json =
{SYM: {kind_hist_n, kind_hist_ret2d_med, kind_hist_p_pos2d}} - read O(1) at entry as stage-2
covariates (graded at N, gate nothing). Gives recall() its first production consumer.

Runs AFTER build_catalyst_memory (rebuild_index). Pure sqlite read, fail-open, public data only,
NO account awareness, NO live-loop contact.

  .venv\\Scripts\\python.exe scripts\\enrich_catalyst_context.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from atlas.config_loader import FRAMEWORK_ROOT     # noqa: E402
from atlas.memory.catalyst_memory import recall    # noqa: E402

HUNT_LIST = FRAMEWORK_ROOT / "runtime" / "hunt_list.json"
OUT = FRAMEWORK_ROOT / "runtime" / "catalyst_context.json"


def extract(rec: dict) -> dict:
    """Map a recall() result to the 3 covariate keys, guarding the exact naming traps: fwd_2d is a
    NESTED {median,...} (or None on the empty shape), and p_pos_2d carries an underscore."""
    fwd2 = rec.get("fwd_2d") if isinstance(rec, dict) else None
    return {"kind_hist_n": rec.get("n") if isinstance(rec, dict) else None,
            "kind_hist_ret2d_med": fwd2.get("median") if isinstance(fwd2, dict) else None,
            "kind_hist_p_pos2d": rec.get("p_pos_2d") if isinstance(rec, dict) else None}


def build_context(rows: list) -> dict:
    """For each hunt-list row carrying a catalyst_kind, recall the kind's (optionally gap-directional)
    base rates. Direction is used only when a gap_pct is available (crew candidates often lack it - 
    then recall conditions on kind alone and self-downgrades below its min_cell)."""
    out: dict = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("symbol") or "").upper()
        kind = r.get("catalyst_kind")
        if not sym or not kind:
            continue
        direction = None
        gap = r.get("gap_pct")
        if gap is not None:
            try:
                direction = "pos" if float(gap) >= 0 else "neg"
            except (TypeError, ValueError):
                direction = None
        try:
            rec = recall(str(kind), direction)
        except Exception:                          # noqa: BLE001 - a bad cell never disarms enrichment
            continue
        out[sym] = extract(rec)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="premarket catalyst-memory context enrichment")
    ap.add_argument("--hunt-list", default=str(HUNT_LIST))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    try:
        raw = json.loads(Path(args.hunt_list).read_text("utf-8"))
        rows = (raw.get("candidates") or raw.get("symbols") or []) if isinstance(raw, dict) else raw
    except Exception:                              # noqa: BLE001
        rows = []
    ctx = build_context(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(ctx, indent=1), encoding="utf-8")
    print(f"catalyst_context: {len(ctx)} symbols enriched -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
