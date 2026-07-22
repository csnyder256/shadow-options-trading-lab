"""QueueOrganizer (Phase 1) - a persistent best-first candidate pool feeding the cascade.

Replaces the orchestrator's per-cycle build-sort-throwaway candidate list with state that survives
across cycles AND process restarts, so the scarce model cascade (the sequential auditor, ~40s/call)
spends its capacity on the freshest, best, NOT-recently-evaluated candidates - instead of
re-analyzing and re-auditing the same qualifying names every 120s cycle.

Option A (see docs/queue_organizer_design.md + the plan): the existing once-per-cycle batch cascade
is UNCHANGED - the organizer only chooses WHICH candidates enter it. Consequences:
  * ONE integer cycle clock (`cycle_seq`) drives freshness decay + dwell; cooldown uses ABSOLUTE
    wall-clock seconds so it survives a restart. No lease/in-flight state (that was demand-pull only).
  * Quality STRICTLY dominates the ranking (lexicographic): a candidate >= one quality quantum better
    can never be out-ranked by a fresher/older one - survival-first. Dwell only breaks within-quantum
    ties; starvation is a separate, bounded escape hatch (never score inflation).
  * Deterministic: a given call-stream yields byte-identical `select()` order (final tie-break on
    (symbol, setup_type)); aging keys on the integer clock, never wall-clock.
  * `held` (symbols we hold) is rehydrated from the broker every startup and is NEVER persisted - 
    the broker is the source of truth, which also closes the position_meta-is-RAM-only restart hole.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from atlas.fsutil import atomic_replace
from atlas.signals.signal_engine import CandidateSetup

_BIG = 1.0e12

# settle() outcomes for a selected candidate
ENTERED = "entered"        # became (or already was) a held position -> suppress for its life
REJECTED = "rejected"      # analyst pass / consensus / risk veto / broker / model error -> cooldown
NO_VERDICT = "no_verdict"  # selected but the cascade never produced a verdict (skip) -> stay in pool


def _kstr(key: tuple[str, str]) -> str:
    return f"{key[0]}|{key[1]}"


def _kparse(s: str) -> tuple[str, str]:
    sym, setup = s.split("|", 1)
    return (sym, setup)


@dataclass(frozen=True)
class OrganizerParams:
    select_n: int = 5                      # candidates handed to the cascade per cycle
    pool_cap: int = 256                    # max retained pool depth (~ universe*pass_rate)
    tau_fresh_cycles: float = 3.0          # freshness e-fold (in cycles): unconfirmed -> decays
    quality_quantum: float = 1.0           # ranking quantization; dwell can't reorder across a quantum
    dwell_cap_cycles: int = 10             # cap on the within-quantum dwell tie-break
    starve_escape_cycles: int = 20         # force-promote a never-selected dwelled entry this often
    min_bucket_factor: float = 0.6         # evict floor = min_quality_score * this / quantum
    data_ttl_seconds: float = 900.0        # evict an entry whose freshest bar is older than this
    fp_bucket: float = 3.0                 # "material quality move" granularity (cooldown bypass)
    cooldown_seconds_base: float = 1800.0  # don't re-audit a just-evaluated name for this long
    cooldown_seconds_min: float = 300.0    # adaptive floor when the pool is thin (avoid starving)
    min_quality_score: float = 55.0        # reused from the picker for the evict floor
    # Same-day repeat-rejection escalation (2026-07-01 audit: BTI was re-evaluated 11x in one day at
    # exact 30-min intervals with verbatim-identical vetoes - 55% of the scarce cascade burned on
    # re-litigating rejected names). Each same-day rejection multiplies the cooldown: 30m -> 2h -> 8h.
    reject_escalation_factor: float = 4.0
    reject_escalation_max_steps: int = 2

    @classmethod
    def from_raw(cls, raw_signal_params: Mapping[str, Any]) -> "OrganizerParams":
        qo = dict(raw_signal_params.get("queue_organizer", {}))
        mq = float(dict(raw_signal_params.get("quality_score", {})).get("min_quality_score", 55.0))
        g = qo.get
        return cls(
            select_n=int(g("select_n", 5)),
            pool_cap=int(g("pool_cap", 256)),
            tau_fresh_cycles=float(g("tau_fresh_cycles", 3.0)),
            quality_quantum=float(g("quality_quantum", 1.0)),
            dwell_cap_cycles=int(g("dwell_cap_cycles", 10)),
            starve_escape_cycles=int(g("starve_escape_cycles", 20)),
            min_bucket_factor=float(g("min_bucket_factor", 0.6)),
            data_ttl_seconds=float(g("data_ttl_seconds", 900.0)),
            fp_bucket=float(g("fp_bucket", 3.0)),
            cooldown_seconds_base=float(g("cooldown_seconds_base", 1800.0)),
            cooldown_seconds_min=float(g("cooldown_seconds_min", 300.0)),
            reject_escalation_factor=float(g("reject_escalation_factor", 4.0)),
            reject_escalation_max_steps=int(g("reject_escalation_max_steps", 2)),
            min_quality_score=mq,
        )


@dataclass
class PoolEntry:
    symbol: str
    setup_type: str
    quality: float
    quality_fp: int
    entry_price: float
    atr: float
    direction: str
    quality_components: dict
    features: dict
    first_seen_cycle: int
    last_scored_cycle: int
    data_age_seconds: float
    times_selected: int = 0

    @property
    def key(self) -> tuple[str, str]:
        return (self.symbol, self.setup_type)


class QueueOrganizer:
    def __init__(self, params: OrganizerParams):
        self.p = params
        self.pool: dict[tuple[str, str], PoolEntry] = {}
        self.cooldown: dict[tuple[str, str], float] = {}      # key -> release wall-clock epoch secs
        self.fp_at_cooldown: dict[tuple[str, str], int] = {}
        self.reject_count: dict[tuple[str, str], int] = {}    # same-day rejections -> cooldown escalation
        self.reject_day: int = -1                             # UTC day the counts belong to
        self.cycle_seq: int = 0
        self.last_clearable: int = 1
        self.held: set[str] = set()                           # symbols; rehydrated from broker, NOT persisted

    # ---- ranking (quality strictly dominates) -----------------------------
    def _freshness(self, e: PoolEntry, cycle: int) -> float:
        # Clamp at 0: after a process restart the caller's cycle counter can sit BELOW a persisted
        # last_scored_cycle; un-clamped, exp(+large) overflows (crash) or ranks stale entries ~1e13
        # ahead of fresh ones. Freshness can never exceed 1.
        return math.exp(-max(0.0, cycle - e.last_scored_cycle) / self.p.tau_fresh_cycles)

    def _bucket(self, e: PoolEntry, cycle: int) -> int:
        return math.floor(e.quality * self._freshness(e, cycle) / self.p.quality_quantum)

    def _dwell(self, e: PoolEntry, cycle: int) -> int:
        return min(max(0, cycle - e.first_seen_cycle), self.p.dwell_cap_cycles)

    def _ranked(self, entries: Iterable[PoolEntry], cycle: int) -> list[PoolEntry]:
        """Best-first, deterministic. Stable two-pass sort: (symbol,setup) asc as the base order,
        then (quality_bucket, dwell) desc on top - so quality dominates and ties resolve identically."""
        xs = sorted(entries, key=lambda e: (e.symbol, e.setup_type))
        xs.sort(key=lambda e: (self._bucket(e, cycle), self._dwell(e, cycle)), reverse=True)
        return xs

    # ---- the cycle API ----------------------------------------------------
    def update(self, new_candidates: Iterable[CandidateSetup], *, cycle_seq: int,
               data_age_by_symbol: Mapping[str, float], now: float,
               suppress: "set[str] | None" = None) -> None:
        """Merge this cycle's freshly-scanned candidates into the persistent pool, then evict.

        `suppress` (symbols with a still-pending Revisit watch) are kept OUT of the pool so the queue
        REPLACES blind recycling rather than adding to it - the revisit watcher owns those names until
        their price/time condition fires. Default None -> existing callers are byte-identical."""
        self.cycle_seq = cycle_seq
        for k in [k for k, ts in self.cooldown.items() if ts <= now]:   # drop expired cooldowns
            self.cooldown.pop(k, None)
            self.fp_at_cooldown.pop(k, None)

        for c in new_candidates:
            if c.symbol in self.held:                       # we hold it: never re-enter the pool
                continue
            if suppress and c.symbol in suppress:           # a pending revisit watch owns this name
                continue
            key = (c.symbol, c.setup_type)
            new_fp = round(c.quality / self.p.fp_bucket)
            if key in self.cooldown:
                # Stay suppressed UNLESS the quality moved materially (a real re-qualification).
                if new_fp <= self.fp_at_cooldown.get(key, new_fp):
                    continue
                self.cooldown.pop(key, None)
                self.fp_at_cooldown.pop(key, None)
            age = float(data_age_by_symbol.get(c.symbol, _BIG))
            if key in self.pool:
                e = self.pool[key]
                e.quality = c.quality
                e.quality_fp = new_fp
                e.entry_price = c.entry_price
                e.atr = c.atr
                e.direction = c.direction
                e.quality_components = dict(c.quality_components)
                e.features = dict(c.features)
                e.data_age_seconds = age
                e.last_scored_cycle = cycle_seq             # freshness reset
            else:
                self.pool[key] = PoolEntry(
                    symbol=c.symbol, setup_type=c.setup_type, quality=c.quality, quality_fp=new_fp,
                    entry_price=c.entry_price, atr=c.atr, direction=c.direction,
                    quality_components=dict(c.quality_components), features=dict(c.features),
                    first_seen_cycle=cycle_seq, last_scored_cycle=cycle_seq,
                    data_age_seconds=age, times_selected=0)

        self._evict(cycle_seq)

    def _evict(self, cycle: int) -> None:
        floor = math.floor(self.p.min_quality_score * self.p.min_bucket_factor / self.p.quality_quantum)
        for key in list(self.pool):
            e = self.pool[key]
            if e.data_age_seconds > self.p.data_ttl_seconds or self._bucket(e, cycle) < floor:
                del self.pool[key]
        if len(self.pool) > self.p.pool_cap:                # over capacity -> drop the worst
            for e in self._ranked(self.pool.values(), cycle)[self.p.pool_cap:]:
                del self.pool[e.key]

    def select(self, n: int, cycle_seq: int) -> list[CandidateSetup]:
        """Return the top-n candidates for the cascade this cycle (best-first, deterministic)."""
        self.cycle_seq = cycle_seq
        entries = list(self.pool.values())
        picked: list[PoolEntry] = []

        # Anti-starvation: occasionally force-promote ONE never-selected, max-dwelled entry so a
        # persistent (N+1)th-best name is not starved forever. Bounded to <=1 displacement per cycle.
        if self.p.starve_escape_cycles > 0 and cycle_seq % self.p.starve_escape_cycles == 0:
            starved = [e for e in entries
                       if e.times_selected == 0 and self._dwell(e, cycle_seq) >= self.p.dwell_cap_cycles]
            if starved:
                pick = self._ranked(starved, cycle_seq)[0]
                picked.append(pick)
                entries = [e for e in entries if e.key != pick.key]

        picked.extend(self._ranked(entries, cycle_seq)[: max(0, n - len(picked))])
        for e in picked:
            e.times_selected += 1
        self.last_clearable = max(1, len(picked))
        return [self._as_candidate(e) for e in picked]

    def settle(self, selected_keys: Iterable[tuple[str, str]],
               verdicts: Mapping[tuple[str, str], str], *, now: float) -> None:
        """Resolve every selected key. ENTERED -> held + drop; REJECTED -> cooldown + drop; a missing
        verdict (cascade skipped) -> leave in pool (re-scored next cycle, never stranded)."""
        cd = self._cooldown_seconds()
        day = int(now // 86400)
        if day != self.reject_day:                            # counts are same-day only
            self.reject_day = day
            self.reject_count.clear()
        for key in selected_keys:
            outcome = verdicts.get(key, NO_VERDICT)
            if outcome == ENTERED:
                self.pool.pop(key, None)
                self.held.add(key[0])
            elif outcome == REJECTED:
                e = self.pool.pop(key, None)
                n_rej = self.reject_count.get(key, 0)
                self.reject_count[key] = n_rej + 1
                # Escalate on repeats: temp-0 models re-veto an unchanged setup verbatim, so re-asking
                # every 30 min only burns cascade capacity that unique names need. The escalated term
                # uses the BASE cooldown so a thin pool can't collapse a repeat offender back to 5 min.
                steps = min(n_rej, self.p.reject_escalation_max_steps)
                eff = max(cd, self.p.cooldown_seconds_base * (self.p.reject_escalation_factor ** steps))                     if steps > 0 else cd
                self.cooldown[key] = now + eff
                self.fp_at_cooldown[key] = e.quality_fp if e is not None else 0
            # NO_VERDICT: leave it in the pool untouched.

    def _cooldown_seconds(self) -> float:
        # Adaptive: if the eligible pool is thinner than what we clear per cycle, collapse the cooldown
        # to its floor so a just-rejected name can re-admit fast and the auditor never idles.
        return (self.p.cooldown_seconds_min if len(self.pool) < self.last_clearable
                else self.p.cooldown_seconds_base)

    def on_position_closed(self, symbol: str) -> None:
        self.held.discard(symbol)                           # re-admit on the next scan at full score

    def clear_cooldown(self, symbol: str) -> None:
        """Lift the organizer cooldown for a symbol (all its setups). Called when the Revisit queue FIRES
        a re-look: the name was cooled down by a prior analyst_pass / blackout reject, but its watched
        condition has now materially changed, so it must be re-admittable this cycle (FLAG 2)."""
        for key in [k for k in self.cooldown if k[0] == symbol]:
            self.cooldown.pop(key, None)
            self.fp_at_cooldown.pop(key, None)

    # ---- helpers ----------------------------------------------------------
    def _as_candidate(self, e: PoolEntry) -> CandidateSetup:
        return CandidateSetup(
            symbol=e.symbol, setup_type=e.setup_type, direction=e.direction,
            entry_price=e.entry_price, atr=e.atr, quality=e.quality,
            quality_components=dict(e.quality_components), features=dict(e.features))

    def pool_size(self) -> int:
        return len(self.pool)

    # ---- persistence (mirror state_machine.load/save) ---------------------
    def save(self, path: Path | str | None) -> None:
        if path is None:
            return
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cycle_seq": self.cycle_seq,
            "last_clearable": self.last_clearable,
            "pool": [asdict(e) for e in self.pool.values()],
            "cooldown": {_kstr(k): ts for k, ts in self.cooldown.items()},
            "fp_at_cooldown": {_kstr(k): fp for k, fp in self.fp_at_cooldown.items()},
            "reject_count": {_kstr(k): n for k, n in self.reject_count.items()},
            "reject_day": self.reject_day,
        }
        tmp = path.with_name(path.name + ".tmp")   # atomic: a crash mid-write must not brick the pool
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        atomic_replace(tmp, path)

    def load(self, path: Path | str | None) -> None:
        if path is None:
            return
        path = Path(path)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.cycle_seq = int(data.get("cycle_seq", 0))
        self.last_clearable = int(data.get("last_clearable", 1))
        fields = set(PoolEntry.__dataclass_fields__)
        self.pool = {}
        for d in data.get("pool", []):
            e = PoolEntry(**{k: v for k, v in d.items() if k in fields})
            self.pool[e.key] = e
        self.cooldown = {_kparse(k): float(ts) for k, ts in data.get("cooldown", {}).items()}
        self.fp_at_cooldown = {_kparse(k): int(fp) for k, fp in data.get("fp_at_cooldown", {}).items()}
        self.reject_count = {_kparse(k): int(n) for k, n in data.get("reject_count", {}).items()}
        self.reject_day = int(data.get("reject_day", -1))
