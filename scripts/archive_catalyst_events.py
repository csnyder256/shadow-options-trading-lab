#!/usr/bin/env python3
"""CATALYST EVENT ARCHIVER (opts-catalyst-archive-v1) - rescue events from TTL death.

runtime/catalyst_state.json is the equity-era catalyst pipeline's LIVE event book: events
appear, age out by ttl_seconds, and vanish. This ten-line-idea script makes every event ever
observed a PERMANENT, joinable record for the catalyst memory (kind attribution with
provenance instead of headline guessing).

Behavior: read the state file, append any event_id not yet archived to
runtime/memory/catalyst_events_archive.jsonl (append-only truth), track seen ids in
runtime/memory/catalyst_events_seen.json (atomic). Idempotent - a second run appends
nothing. Fail-open, exit 0 always (scheduled-chain safe). Stage 0 evidence factory:
nothing consumes the archive yet.

Scheduled as ATLAS-CatalystArchive 3x/day (08:30 / 12:30 / 17:30 CT).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.fsutil import atomic_replace  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
STATE = REPO / "runtime" / "catalyst_state.json"
MEM_DIR = REPO / "runtime" / "memory"
ARCHIVE = MEM_DIR / "catalyst_events_archive.jsonl"
SEEN = MEM_DIR / "catalyst_events_seen.json"


def main() -> int:
    try:
        MEM_DIR.mkdir(parents=True, exist_ok=True)
        try:
            state = json.loads(STATE.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            print(f"[catalyst-archive] state unreadable ({exc}) - nothing to do", flush=True)
            return 0
        try:
            seen = set(json.loads(SEEN.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            seen = set()
        events = state.get("events") or {}
        fresh = []
        for eid, rec in events.items():
            if not isinstance(rec, dict) or eid in seen:
                continue
            ev = rec.get("event") or {}
            fresh.append({"schema": 1, "archived_ts": round(time.time(), 3),
                          "event_id": str(eid), "status": rec.get("status"),
                          "event": ev})
            seen.add(str(eid))
        if fresh:
            with ARCHIVE.open("a", encoding="utf-8") as fh:
                for row in fresh:
                    fh.write(json.dumps(row, separators=(",", ":")) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        tmp = SEEN.with_name(SEEN.name + ".tmp")
        tmp.write_text(json.dumps(sorted(seen)), encoding="utf-8")
        atomic_replace(tmp, SEEN)
        print(f"[catalyst-archive] archived {len(fresh)} new events "
              f"(seen total {len(seen)})", flush=True)
    except Exception as exc:  # noqa: BLE001 - scheduled chain must never see nonzero
        print(f"[catalyst-archive] FATAL (tolerated): {exc!r}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
