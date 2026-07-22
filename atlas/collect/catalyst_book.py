"""CatalystBook - the OPTIONS-side event book + writer (mission reincorporate-cut-systems, 2026-07-12).

The slim descendant of the archived atlas/catalyst_pipeline.CatalystPipeline: it polls the context
feeds, dedups + TTL-prunes an event book, and persists runtime/catalyst_state.json in the NATIVE
schema the research crew (scripts/research_crew.gather_catalyst_events) and the archiver
(scripts/archive_catalyst_events) already read - so the whole catalyst chain (crew hunt-list,
catalyst-memory, archive) un-starves with ZERO downstream change.

DROPPED vs the equity pipeline: the RevisitQueue tape-confirmation WATCH mechanism
(register_watches / mark_fired / eligible_for_eval) - it re-entered names into the discovery gate
set that does not exist in the options stack, and it imported the archived atlas.revisit. Defensive
event kinds (fda / dilution / edgar_neg) are carried as event METADATA only (observe-first): the
crew sees them as context and later they become GRADED entry covariates - never a live veto here.

Fail-open, single-writer (atomic_replace), account-blind, no AI, public data only.
"""

from __future__ import annotations

import json
from pathlib import Path

from atlas.fsutil import atomic_replace


class CatalystBook:
    def __init__(self, feeds=(), *, state_path=None, max_events_per_cycle: int = 25,
                 max_active_events: int = 200, verify_fn=None):
        self.feeds = list(feeds)
        self.state_path = Path(state_path) if state_path else None
        self.max_events_per_cycle = int(max_events_per_cycle)
        self.max_active_events = int(max_active_events)
        self.verify_fn = verify_fn or (lambda s: True)
        self.events: dict[str, dict] = {}      # event_id -> {"event": {...}, "status": "pending"}
        self.seen: dict[str, float] = {}
        self.borrow_snapshots: dict[str, list] = {}   # BorrowFeeFeed ring state (persisted)
        self.insider_window: dict[str, list] = {}     # Form4InsiderBuyFeed cluster window (persisted)
        self.dropped_unverified = 0
        self.load()

    def poll(self, now_iso: str, now_epoch: float) -> list:
        """Poll all feeds (each NEVER raises), dedup by event_id, storm-cap, book, TTL-prune.
        Returns the NEWLY ACCEPTED events."""
        fresh: list = []
        for feed in self.feeds:
            fresh.extend(feed.poll(now_iso, now_epoch))
        fresh.sort(key=lambda e: (-e.magnitude, e.symbol))
        accepted: list = []
        for ev in fresh:
            if len(accepted) >= self.max_events_per_cycle:
                break
            if ev.event_id in self.seen or len(self.events) >= self.max_active_events:
                continue
            if not self._verify(ev.symbol):
                self.dropped_unverified += 1
                continue
            self.seen[ev.event_id] = now_epoch
            self.events[ev.event_id] = {"event": ev.__dict__ | {"numbers": dict(ev.numbers)},
                                        "status": "pending"}
            accepted.append(ev)
        self._prune(now_epoch)
        return accepted

    def _verify(self, symbol: str) -> bool:
        try:
            return bool(self.verify_fn(symbol))
        except Exception:                      # an unverifiable ticker is a NO (fail-safe)
            return False

    def _prune(self, now_epoch: float) -> None:
        for eid in list(self.events):
            e = self.events[eid]["event"]
            if now_epoch - float(self.seen.get(eid, now_epoch)) > float(e["ttl_seconds"]):
                del self.events[eid]
        for eid in list(self.seen):
            ttl = float(self.events[eid]["event"]["ttl_seconds"]) if eid in self.events else 86400.0
            if now_epoch - self.seen[eid] > 2.0 * ttl:
                del self.seen[eid]

    def snapshot(self) -> dict:
        return {
            "mode": "options_context",
            "active_events": [{"symbol": r["event"]["symbol"], "kind": r["event"]["kind"],
                               "magnitude": r["event"]["magnitude"], "status": r["status"]}
                              for r in self.events.values()],
            "dropped_unverified": self.dropped_unverified,
            "feeds": [{"name": getattr(f, "name", "?"), "breaker_error": getattr(f, "last_error", "")}
                      for f in self.feeds],
        }

    def save(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"events": self.events, "seen": self.seen,
                "borrow_snapshots": self.borrow_snapshots, "insider_window": self.insider_window,
                "snapshot": self.snapshot()}
        tmp = self.state_path.with_name(self.state_path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        atomic_replace(tmp, self.state_path)

    def load(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.events = {str(k): v for k, v in (data.get("events") or {}).items()
                       if isinstance(v, dict) and isinstance(v.get("event"), dict)}
        self.seen = {str(k): float(v) for k, v in (data.get("seen") or {}).items()}
        self.borrow_snapshots.update({str(k): list(v) for k, v in (data.get("borrow_snapshots") or {}).items()})
        self.insider_window.update({str(k): list(v) for k, v in (data.get("insider_window") or {}).items()})
