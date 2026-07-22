I have confirmed every load-bearing integration point. The reviews' claims check out against the code: `position_meta`/`_cycle` reset at lines 114-115, the `skipped_reason` early-return at 287 before any settle hook, symbol-keyed journaling (`decision_id=f"{self._cycle}-{proposal.symbol}"`), the validate/size seam at 322/356, and `CandidateSetup` is frozen (line 125). Here is the finalized design.

---

# ATLAS Queue Organizer + World-Size Design - FINAL (engineer build spec)

## 0. The one-line correction (state this first)

Your instinct - "find the world size where one full picker scan ≈ 30s" - optimizes the wrong resource. At the measured **0.9 ms/symbol**, the picker only reaches a 30s scan at **~33,000 symbols**, ~5x the entire liquid US universe. **The picker is free and is not the binding constraint.** The ~30s you sense is real but lives in the **model cascade**: it is the **per-candidate auditor drain**, not a picker scan and not a "cycle."

**The corrected objective:** keep the sequential auditor saturated with the *current* globally-best candidates, and never let it spend a single 28-ish-second call on a stale, held, or already-rejected name. That is the Queue Organizer's entire job. "World size" stops being a tuned number: **scan the whole affordable universe (free), and size the re-ranked working pool, not the universe.**

**One hard caveat carried from the throughput review (do not skip):** every load-bearing latency number below (`auditor`, `enter_rate`, `pass_rate`) is from a **superseded auditor model** or a **disputed small sample**. They are written here as *defaults for the simulation*, **not** as constants to hard-code. **The B.4 simulation is mandatory-before-merge.** Re-measure on the current auditor (Qwen3-30B-A3B-Thinking-2507) first; treat `28.2s / 63 / 640` as a *worked example of the formulas*, not committed values.

---

# PART A - The Queue Organizer

## A.1 What it is

A second deterministic component between the picker (`SignalEngine.scan`) and the model cascade (`DualModelAnalyzer.run`). Not a scanner - a **persistent, bounded, best-first priority pool with demand-pull leasing**. It replaces orchestrator step 5's build-sort-throwaway list (lines 226–242) with **state that survives across cycles and across process restarts**.

- The picker re-scans the whole world cheaply and **merges** results into the pool.
- The pool keeps the best ~N names, re-ranked by an **effective score** (quality, with freshness decay and a bounded-but-escapable anti-starvation term), never FIFO.
- The models **lease demand-pull** - a small `k` (1–4) each time the auditor goes idle - not a 63-name batch (see B.2; this is the single most important correction from the throughput review).
- After each verdict, the organizer **settles** the leased name onto cooldown so the slow models never re-audit it; cooldown is **adaptive** so it cannot starve the auditor on thin tape.

## A.2 Two clocks (resolves review C2/M1: one integer cannot drive both cadences)

The design uses **two separate monotonic counters**, because the picker re-ranks every ≤60s while the model lease is event-driven:

```
scan_seq    : increments once per picker update() (every ≤60s / per bar batch).
              Drives freshness_decay and dwell.
lease_epoch : increments once per demand-pull lease event.
              Drives cooldown and the starvation escape hatch.
```

Every constant below is labeled with which clock it uses. Neither clock keys on wall-clock, so replay with the same call-stream is byte-identical (see A.9).

## A.3 State (lives in `signal_engine.py`, owned by `Orchestrator`) - and it is PERSISTED

```
PoolEntry:
    symbol, setup_type              # identity key = (symbol, setup_type)
    quality                         # latest deterministic picker quality (0-100)
    quality_fp                      # quality fingerprint: round(quality / FP_BUCKET) - for material-move re-lease
    quality_components, features, entry_price, atr, direction   # carried from CandidateSetup
    snapshot_id                     # the bar/snapshot these features came from (consistency seam, M4)
    first_seen_scan                 # for dwell aging (scan_seq units)
    last_scored_scan                # re-stamped every time the picker re-confirms it (scan_seq units)
    data_age_seconds                # from the bar that produced it
    leased_at_epoch                 # lease_epoch when leased; None if FRESH
    state: FRESH | IN_FLIGHT
    times_leased                    # for the starvation escape hatch

QueueOrganizer state (ALL PERSISTED - see A.8):
    pool      : dict[(symbol,setup_type) -> PoolEntry]
    cooldown  : dict[(symbol,setup_type) -> release_wallclock_ts]   # ABSOLUTE timestamps, not cycle counts (C1/C2)
    scan_seq, lease_epoch : int
    # `held` is NOT persisted - it is rehydrated from the broker every startup (C1).
```

## A.4 The effective-score / priority function (resolves C3 + M2: survival-first vs anti-starvation)

Survival-first means **quality strictly dominates**; the dwell bonus may only arbitrate within a quality-quantization band, and starvation is handled by a **separate eligibility escape hatch**, not by inflating the score. This is the key fix to the reviews' sharpest objection (a worse name leasing ahead of a better one).

```
# Ranking key is LEXICOGRAPHIC, so dwell can never reorder genuinely different quality.
rank_key(e, scan_seq) = ( quality_bucket(e, scan_seq),    # primary: freshness-decayed quality, BUCKETED
                          dwell(e, scan_seq) )             # tie-break ONLY, within a bucket

  quality_bucket(e, s) = floor( e.quality * freshness_decay(e, s) / QUALITY_QUANTUM )
  freshness_decay(e, s) = exp( -(s - e.last_scored_scan) / TAU_FRESH )
  dwell(e, s)           = min( s - e.first_seen_scan, DWELL_CAP )
```

- `QUALITY_QUANTUM` is set to the picker's genuine score-quantization (e.g. 1.0 point). Two candidates ≥1 quantum apart can **never** be reordered by dwell - survival-first preserved. Within one quantum (a true near-tie) dwell breaks the tie deterministically.
- **Anti-starvation is NOT in the score** (this is the M2 fix). Bounded dwell + scarce slots otherwise guarantees permanent starvation of the (N+1)th-best persistent setup. Instead, an explicit escape hatch in `lease()` force-promotes any FRESH, never-leased entry that has dwelled `DWELL_CAP` scans, once every `STARVE_ESCAPE_EPOCHS` lease epochs - accounted separately from the quality ranking, capped at 1 promoted slot per lease so it never displaces more than one genuinely-best name.

## A.5 The algorithm

```
# --- called once per picker scan (every <=60s, or on actual bar arrival; see B.2/§review-7) ---
update(new_candidates, scan_seq, data_age_by_symbol, now_wallclock):
    self.scan_seq = scan_seq
    reclaim_in_flight(now_wallclock)                         # (C4) unconditionally reclaim stuck leases FIRST
    drop_expired_cooldowns(now_wallclock)                    # release_ts <= now -> eligible again

    for c in new_candidates:                                 # CandidateSetup from SignalEngine.scan
        key = (c.symbol, c.setup_type)
        if c.symbol in held:            continue             # we hold it: never re-enter (mirrors orch 331)
        new_fp = round(c.quality / FP_BUCKET)
        if key in cooldown:
            # ADAPTIVE re-lease (C5 / review-5): a MATERIAL quality move bypasses cooldown. MANDATORY, not optional.
            prior_fp = self._fp_at_cooldown.get(key)
            if new_fp <= prior_fp:      continue             # not materially better -> stay suppressed
            del cooldown[key]                                # materially better -> re-admit now
        if key in pool:
            e = pool[key]
            e.quality = c.quality; e.quality_fp = new_fp; e.features = c.features
            e.entry_price = c.entry_price; e.atr = c.atr; e.direction = c.direction
            e.data_age_seconds = data_age_by_symbol.get(c.symbol, BIG)   # (M-c) .get, never []
            e.snapshot_id = current_snapshot_id
            e.last_scored_scan = scan_seq                    # freshness reset
            # do NOT touch state here; if IN_FLIGHT it stays IN_FLIGHT
        else:
            pool[key] = PoolEntry(..., first_seen_scan=scan_seq, last_scored_scan=scan_seq,
                                  times_leased=0, state=FRESH, snapshot_id=current_snapshot_id)

    # EVICTION - never evict IN_FLIGHT (M-b: evicting in-flight orphans the verdict -> re-churn)
    evictable = [e for e in pool.values() if e.state != IN_FLIGHT]
    ranked = sort(evictable, key=lambda e: rank_key(e, scan_seq), desc)
    for e in ranked[POOL_CAP:]:                       evict(e)     # over capacity
    for e in evictable:
        if quality_bucket(e, scan_seq) < MIN_BUCKET:  evict(e)     # decayed below floor
        if e.data_age_seconds > DATA_TTL:             evict(e)     # data too stale to trust


reclaim_in_flight(now_wallclock):                              # (C4) authoritative, runs every update()
    for e in pool.values():
        if e.state == IN_FLIGHT and (self.lease_epoch - e.leased_at_epoch) >= 1:
            e.state = FRESH; e.leased_at_epoch = None           # never strands a slot, even if no verdict ever came


# --- demand-pull lease: called whenever the auditor goes idle, leasing a SMALL k (B.2) ---
lease(k, lease_epoch, now_wallclock) -> list[CandidateSetup]:
    self.lease_epoch = lease_epoch
    eligible = [e for e in pool.values() if e.state == FRESH]
    leased = []

    # starvation escape hatch (M2): at most ONE force-promoted starved name per lease
    if lease_epoch % STARVE_ESCAPE_EPOCHS == 0:
        starved = [e for e in eligible
                   if e.times_leased == 0 and dwell(e, self.scan_seq) >= DWELL_CAP]
        if starved:
            pick = max(starved, key=lambda e: rank_key(e, self.scan_seq))
            leased.append(pick); eligible.remove(pick)

    top = sort(eligible, key=lambda e: rank_key(e, self.scan_seq), desc)[: max(0, k - len(leased))]
    leased.extend(top)
    for e in leased:
        e.state = IN_FLIGHT; e.leased_at_epoch = lease_epoch; e.times_leased += 1
    return [as_candidate_setup(e) for e in leased]              # carries snapshot_id (M4)


# --- settle: AUTHORITATIVE over the FULL leased set, not only keys with verdicts (C4) ---
settle(leased_keys, verdicts, lease_epoch, now_wallclock):
    for key in leased_keys:                                     # EVERY leased key is resolved here
        outcome = verdicts.get(key, LEASED_NO_VERDICT)          # missing verdict (error/skip) -> explicit fallback
        e = pool.pop(key, None)
        if outcome == ENTERED_POSITION:
            held.add(key.symbol)                                # hard-suppress for the position's life
        elif outcome in (REJECTED, ANALYST_PASS, MODEL_ERROR):
            ts = now_wallclock + cooldown_seconds(now_wallclock)   # ADAPTIVE duration (below)
            cooldown[key] = ts
            self._fp_at_cooldown[key] = key_fp_at_settle         # baseline for material-move re-lease
        elif outcome == LEASED_NO_VERDICT:
            if e: e.state = FRESH; e.leased_at_epoch = None      # return to pool, do NOT cooldown


cooldown_seconds(now_wallclock):                               # (review-5 / C5) adaptive: never starve the auditor
    base = COOLDOWN_SECONDS_BASE
    eligible_now = count(e for e in pool.values() if e.state == FRESH)
    if eligible_now < self._last_clearable:                     # auditor is at risk of idling
        return COOLDOWN_SECONDS_MIN                             # collapse cooldown so names re-admit fast
    return base


on_position_closed(symbol):                                    # from orchestrator step 4 exits (~line 195)
    held.discard(symbol)                                        # re-admit on next scan at full score
```

**Why this stops re-churn AND can't starve the bottleneck:** cooldown is the dedup, but it is (a) keyed on absolute wall-clock so it survives restart, (b) bypassed by a **material quality-fingerprint move** (mandatory), and (c) **adaptively collapsed** to a floor when the eligible pool drops below what the auditor can clear. Held names are suppressed for the whole position lifetime, re-admitted only via `on_position_closed` or the startup broker rehydration.

## A.6 Persistence + restart rehydration (resolves C1 - the cited `position_meta` bug, the #1 must-fix)

The reviews are correct that RAM-only state silently repeats the exact bug this design claims to respect. **All organizer state is persisted to a sidecar next to `risk_state.json`** and rehydrated in `__init__`:

```
# Persisted (organizer_state.json, written alongside save_risk_state at line 418):
pool, cooldown (absolute ts), _fp_at_cooldown, scan_seq, lease_epoch

# Rehydrated on Orchestrator.__init__:
1. Load organizer_state.json if present (else empty pool, scan_seq=lease_epoch=0).
2. held = { p.symbol for p in broker.get_positions() }     # BROKER IS TRUTH (same source as reconcile.py)
   -- never trust an in-RAM held across restart; rebuild from the broker, every start.
3. Because aging keys on PERSISTED scan_seq/lease_epoch (not a counter reset to 0), the
   freshness/dwell math is continuous across restart -- no exp(5000/3)=inf garbage (C1).
4. Cooldown entries with release_ts already in the past are dropped on first update().
```

This also closes the related orchestrator hole: the `if proposal.symbol in self.position_meta` guard at line 331 is RAM-only and empty on restart, so it cannot be the sole duplicate-entry defense. With broker-rehydrated `held`, a held name never re-enters the pool in the first place - the organizer becomes the durable suppression layer the in-RAM guard only approximated.

## A.7 Consistency seam (resolves M4): features and risk-sizing must come from the same snapshot

`as_candidate_setup(e)` carries `e.snapshot_id`. The leased `CandidateSetup.features` (which `_validate_cited_numbers` checks at line 322) and the `data_age_seconds` the risk engine sizes on (line 356, currently read **live** from `bars[...].age_seconds`) must reference the **same** snapshot. Two acceptable resolutions - pick one in implementation:

- **(preferred)** stamp `data_age_seconds` and `entry_price` into the proposal-handling path from the leased `PoolEntry.snapshot_id`, so validation and sizing agree; OR
- if the risk engine must read the freshest bar, **re-validate cited numbers against that same fresh bar**, not the lease-time features.

Either way, do not let `_validate_cited_numbers` pass against lease-time features while the risk engine sizes off a different live price. This is survival-relevant (it gates position size).

## A.8 Suggested constants (defaults for the sim - NOT committed values; see §0)

| Constant | Clock | Default | Rationale |
|---|---|---|---|
| `POOL_CAP` | - | **from sim** (worked ex. ~640) | the *simulation's* smallest pool with novelty≈100% & starvation=0. Do **not** hard-code `clearable/pass_rate` (M3) - see B.2. |
| `TAU_FRESH` | scan_seq | 3 scans | a name unconfirmed ~3 scans decays to ~37% |
| `QUALITY_QUANTUM` | - | = picker score quantization (~1.0) | dwell can't reorder names ≥1 quantum apart (C3) |
| `DWELL_CAP` | scan_seq | 10 | bound dwell so it only breaks within-quantum ties |
| `STARVE_ESCAPE_EPOCHS` | lease_epoch | ~20 | force-promote a never-leased dwelled name ≤1/lease (M2) |
| `MIN_BUCKET` | - | = `min_quality_score`×0.6 / QUANTUM | floor below which an entry isn't worth holding |
| `DATA_TTL` | - | ~900s | drop entries whose freshest bar is older than this |
| `FP_BUCKET` | - | ~3 points | "material move" granularity for cooldown bypass |
| `COOLDOWN_SECONDS_BASE` | wall-clock | 1800–3600s | don't re-audit a just-killed name (absolute ts, restart-safe) |
| `COOLDOWN_SECONDS_MIN` | wall-clock | ~300s | adaptive floor when eligible_pool < clearable (C5) |

## A.9 Determinism / replay (resolves C2.2)

Replay is byte-identical **only if the call-stream is replayed, not just market inputs.** The replay harness must record and replay the ordered sequence of `(scan_seq | lease_epoch, call_type, inputs)` events - because real cadence depends on `asyncio.sleep` and variable model latency. State this as an explicit harness requirement. Aging is integer-clock-keyed (not wall-clock), so given the same call-stream the lease order is deterministic. Note: `data_age_seconds` enters only the `DATA_TTL` gate, not a score - so the "integer-bucketed data_age" determinism claim is dropped as moot; the real guarantee is the call-stream replay.

## A.10 Orchestrator integration (`orchestrator.py`)

`self.organizer = QueueOrganizer(cfg)` in `__init__`, rehydrated per A.6. Then:

- **Step 4 exits (~line 195):** after `self.position_meta.pop(fill.symbol, …)`, call `self.organizer.on_position_closed(fill.symbol)`.
- **Step 5 (replace 226–242):**
  ```
  raw = []
  for symbol, b in bars.items():
      raw.extend(self.signal_engine.scan(symbol, ..., benchmark_close=benchmark))
  data_age = {s: bars[s].age_seconds for s in bars}
  self.organizer.update(raw, scan_seq=self._scan_seq, data_age_by_symbol=data_age, now_wallclock=now)
  res.candidates = self.organizer.pool_size()          # TRUE pool depth for journaling
  ```
  Leasing is **no longer a once-per-cycle batch** - it is demand-pull from the cascade driver (B.2). `max_proposals_per_cycle` is now redundant; downgrade it to a hard assertion/log (and fix its default - M-d below).
- **Cascade driver:** each time the auditor goes idle, `candidates = self.organizer.lease(k, lease_epoch=self._lease_epoch, now_wallclock=now)` with small `k`; remember `leased_keys`.
- **Verdict map (resolves M-a):** the map **must be keyed `(symbol, setup_type)`**, not `symbol`. Today journaling keys on `symbol` alone (`decision_id=f"{self._cycle}-{proposal.symbol}"`, `cand_by_symbol` at line 292) which collapses multiple setups per symbol. Carry `setup_type` through: build `verdicts[(sym,setup)] = outcome` from `result.results` (analyst-pass/reject/error at lines 296–313), the risk rejections (322–379), and fills (`ENTERED_POSITION` at 399–409).
- **Settle on EVERY exit path (resolves C4):** call `self.organizer.settle(leased_keys, verdicts, lease_epoch, now)` before `save_risk_state` - **including** the `result.skipped_reason` early-return at line 287 and the reconciliation early-return at line 189. Any leased key without a verdict on those paths settles as `LEASED_NO_VERDICT` → returns to FRESH, never stranded IN_FLIGHT.
- **Persist:** write `organizer_state.json` wherever `save_risk_state` is called (line 418 and every early-return that persists risk state).

**M-d (must-fix):** `max_proposals_per_cycle` defaults to **3** (orchestrator signature line 88; wired from `app.py:139`). Demand-pull leasing with adaptive clearable will exceed 3 and trip the flood WARN (238–242) constantly. Remove the breaker or raise the config default to above the clearable ceiling; do not leave it firing every cycle.

## A.11 `signal_engine.py` additions

Add `PoolEntry` (dataclass) + `QueueOrganizer` alongside `SignalEngine`. Depends only on `CandidateSetup` (line 125, currently `frozen=True` - `as_candidate_setup` constructs a fresh instance, so frozen is fine) and the two integer clocks - no LLM, no wall-clock in the *scoring* path (wall-clock only times cooldown release), no I/O beyond the JSON sidecar load/save. `as_candidate_setup(e)` reconstructs a `CandidateSetup` (carrying `snapshot_id` via an added field or side-channel) so the downstream cascade and `_validate_cited_numbers` path is unchanged in shape.

---

# PART B - World Size + Cadence

## B.1 The binding constraint (numeric - worked example, re-measure before committing)

| Stage | Cost | Notes |
|---|---|---|
| Picker | 0.9 ms/symbol | 8,000 names = 7.2s. **Free.** |
| Analyst (batched) | 13.6 s/cand | 19s ÷ 1.40 continuous-batch (GLM-4.7-Flash; confirmed) |
| Auditor (sequential) | 43 s/call × 0.34 enter-rate = 14.6 s/cand | **bottleneck**; `auditor_parallelism=1` confirmed (`dual_model.py:69,132`). **43s/0.34 are STALE** (pre-swap projection / disputed n=10). |
| Swap | ~10s, bounded ≤1–2/cycle | see B.5 |
| **Per-candidate amortized** | **~28.2s** | worked example only |

**Model ceiling (worked example):** `per_cand = 19/1.40 + 0.34×43 = 28.2s`. The honest band, because the inputs are uncertain, is **`per_cand ≈ 22–44s`** across auditor 36–50s and enter-rate 0.25–0.45 → **clearable ≈ 40–80 candidates per 30-min equivalent**, **POOL_CAP ≈ 400–1,600**. The point estimates 28.2 / 63 / 640 are a **false-precision midpoint of a ~4x band** - that is exactly why B.4 is mandatory-before-merge.

## B.2 Recommended world size + cadence (with the two key throughput-review corrections folded in)

- **World (picker universe): the entire affordable liquid US universe - 3,000–8,000 names, uncapped.** 8,000 scans in 7.2s. Free Alpaca tier is feasible *in principle*: cache the 200-SMA daily `StockBars` once/day, run a per-cycle multi-symbol **Snapshots** sweep for re-ranking. **Caveat (review-7):** the "1 request / 1,666 symbols" and "200 req/min = 500x headroom" claims **must be verified against the current API** (multi-symbol snapshot pagination + per-request symbol cap), not asserted. Do not pay for Algo Trader Plus to grow the universe.

- **Working pool (`POOL_CAP`): sized by the simulation, not by formula.** **Drop `POOL_CAP = clearable / pass_rate` (M3 - it is dimensionally wrong:** it computes *scan width* - how many universe symbols you scan to find `clearable` passes - not *retained-pool depth*, and the universe is already 3,000–8,000). Size POOL_CAP from B.4's empirical **smallest pool that keeps novelty≈100% and starvation=0**, reported as a band over `(auditor_latency, enter_rate, pass_rate)`.

- **Picker/organizer re-rank cadence: gate on ACTUAL bar arrival (review-7), not a blind 30–60s timer.** Free-tier IEX is a thin feed (~2–3% of consolidated volume); on thinly-traded small/mid-caps the snapshot bar may only refresh every minute or slower. Re-ranking 3,150 times against a bar that changed twice is churn, not freshness. So: re-rank **when a new snapshot batch actually lands**, target ≤60s. Validate IEX refresh frequency for thin names before trusting per-cycle re-confirmation.

- **Model lease cadence: DEMAND-PULL, k=1–4 when the auditor goes idle - NOT a 63-name batch once per 30 min (review-2, the headline correction).** There is **no real 30-minute quantum** in the throughput physics; `1800s` is just an assumed `cycle_seconds`. Leasing 63 names at t=0 means name #63 is audited ~30 min after it was scored - *maximally stale*, manufacturing the exact FIFO-staleness the organizer exists to kill. Instead the auditor pulls a few names whenever it frees up, re-ranking against the *current* pool at each pull. The picker rescan stays decoupled and fast; the lease is event-driven off auditor idle.

So the cadences are explicitly split and **neither is the fictional 30-min batch**: **picker/organizer = on bar arrival (≤60s); model lease = demand-pull on auditor-idle (k=1–4).**

## B.3 The corrected target, stated plainly

- "World size where a full picker scan ≈ 30s" → 33,000 symbols, meaningless.
- "Lease 63 names once per 30-min cycle" → **also wrong** (review-2): re-introduces lease-to-verdict staleness. Lease demand-pull, k=1–4.
- **World = whole data-feasible liquid universe (uncapped).** Tune `min_quality_score` so the picker *passes* roughly the clearable rate. Size the **pool from the sim**. Re-rank on bar arrival; lease demand-pull. The "30s" you intuited is the **per-candidate auditor drain**, which the organizer keeps saturated.
- **Highest-leverage throughput work is the auditor** (52% of per-cand cost, sequential): cut its latency (50→36s lifts the ceiling materially) or trim `enter_rate` (0.34→0.25 raises clearable ~74/30-min-equiv). Universe/picker is not the lever.

## B.4 The runnable simulation to build - MANDATORY BEFORE MERGE

Extend `scripts/measure_pipeline.py` with a `--simulate` discrete-event throughput model (no LLM calls for the sweep - feed it measured latency constants, reusing the per-candidate math at lines 184–204 and the threshold sweep at 113–116). **Re-measure the auditor/enter-rate on the current model first and feed those in** (review-1).

**Inputs (defaults = measured ground truth, all sweepable):**
`analyst_raw=19s`, `batch_factor=1.40`, `auditor` (sweep 36/43/50), `enter_rate` (sweep 0.25–0.45), `swap=10s`, `cycle_seconds` (sweep 900/1800 - pool scales ~linearly), `pass_rate` (sweep 0.05–0.15 for the small/mid-cap unknown), `picker_ms=0.9`, `universe` (sweep 1,500/3,000/8,000), `pool_cap`, `rerank_period`, `cooldown_seconds`, `lease_k` (sweep 1/2/4 - demand-pull), `batch_size` (for the swap/staleness tension, §B.5).

**Per-combination computation:**
```
per_cand   = analyst_raw/batch_factor + enter_rate*auditor
clearable  = floor((cycle_seconds - swap*swaps_per_cycle) / per_cand)
# Simulate N cycles: picker feeds pool (on bar-arrival cadence), organizer ages/evicts,
# auditor demand-pull leases lease_k on idle, settle puts rejects on ADAPTIVE cooldown.
# Track:
#   - novelty            = fraction of leased names NOT seen in the previous L epochs (target ~100%)
#   - starvation         = lease epochs where eligible_pool < clearable (auditor idle = bad)
#   - queue_growth       = pool-size trend (passed>clearable => backlog; passed<clearable => starving)
#   - lease_to_verdict_staleness  (review-6, REQUIRED new metric): wall-clock-equiv gap between
#         when a name was scored and when its auditor verdict lands. THIS is the dominant staleness,
#         not picker-cycle age; tie TAU_FRESH to it, not just to scan_seq.
#   - swaps_per_cycle    (§B.5): count model swaps induced by lease order changes; assert <= 1-2.
#   - cooldown_starvation: epochs where adaptive cooldown still left eligible_pool < clearable.
```

**Output:** for each `(auditor, enter_rate, cycle_seconds, pass_rate, lease_k)`, the **smallest universe + pool_cap with novelty≈100%, starvation=0, swaps≤2/cycle, and minimized lease_to_verdict_staleness**, plus the `min_quality_score` (from the existing threshold sweep) that makes the picker pass ~clearable. **Steady-state assertions to log:** `passed > clearable` (models falling behind → raise threshold) and `passed < clearable` (models starving → lower threshold or shorten cooldown).

## B.5 Swap thrash + batch-vs-staleness tension (resolves review-3, review-4, M1)

Re-ranking the sort is free, **but a re-rank that changes which model must be resident is not.** Two guards, both required:

1. **Swap guard (review-4 / M1, missing from the original algorithm):** re-ranking may reorder the **unleased** pool freely, but **must not trigger a model swap mid-drain.** The model-resident phase is frozen; bound swaps to **≤1–2 per cycle** with an explicit guard. The "~3,150 reranks per drain" headroom is real for the *sort* and a thrash generator for the *swap* if unguarded.

2. **Batch-vs-staleness is a real tradeoff the design must surface (review-3):** the 10s swap only amortizes if you batch many analysts before swapping to auditors - but a large analyst batch maximizes **lease-to-verdict staleness** (a candidate's verdict can land 14+ min after its analyst pass). Small batches = fresh candidates but swap-thrash; large batches = one swap but stale verdicts. The sim must **sweep batch size against `lease_to_verdict_staleness`**, not just picker-rescan novelty, and pick the batch size that minimizes staleness subject to swaps≤2/cycle. **`TAU_FRESH` must be tied to wall-clock-equivalent lease-to-verdict latency, not only picker scans** - that intra-cycle gap is the dominant staleness source and was unmodeled in the original.

**Within-drain staleness policy (resolves M1, state it explicitly - do not leave implicit):** the organizer does **NOT** preempt in-flight auditor work. Therefore, during a drain the auditor works *the best-as-of-lease-time*, not the instantaneous best. With demand-pull `k=1–4` (B.2) this window shrinks to a couple of candidates, which is acceptable; with the old `k=63` batch it was 30 min, which was not. No mid-drain re-leasing - that would thrash the swap (item 1). This is the deliberate, documented tradeoff.

---

## Files / integration points (all absolute)

- **`C:\path\to\shadow-options-trading-lab\atlas\signals\signal_engine.py`** - add `PoolEntry` dataclass + `QueueOrganizer` (`update`/`lease`/`settle`/`reclaim_in_flight`/`on_position_closed`/`as_candidate_setup`/`pool_size`/JSON load+save). Reuses `CandidateSetup` (line 125). Two integer clocks; wall-clock only for cooldown release.
- **`C:\path\to\shadow-options-trading-lab\atlas\orchestrator.py`** - instantiate + **rehydrate** `self.organizer` in `__init__` (load sidecar + `held` from `broker.get_positions()`, A.6); `on_position_closed` in step 4 (~line 195); **replace** step 5 build-sort-cap (226–242) with `update()`; demand-pull `lease()` in the cascade driver; build a **`(symbol,setup_type)`-keyed** verdict map from existing journaling (296–313, 322–379, 399–409); call `settle()` on **every** persist/early-return path including the `skipped_reason` return at **line 287** and reconcile return at **189**; persist `organizer_state.json` alongside `save_risk_state` (line 418). Fix `max_proposals_per_cycle` default (currently 3, line 88 / `app.py:139`).
- **`C:\path\to\shadow-options-trading-lab\atlas\app.py`** - add organizer-state path + broker handle so `__init__` can rehydrate (line 134 currently constructs `Orchestrator` with no rehydration).
- **`C:\path\to\shadow-options-trading-lab\atlas\execution\reconcile.py`** - the broker-truth source pattern to mirror for `held` rehydration.
- **`C:\path\to\shadow-options-trading-lab\scripts\measure_pipeline.py`** - add `--simulate` (B.4 sweep, incl. `lease_to_verdict_staleness`, `swaps_per_cycle`, demand-pull `lease_k`, batch-size sweep), reusing threshold sweep (113–116) and per-candidate math (184–204).

**Load-bearing decisions (committed):** demand-pull lease k=1–4 (not 63-batch); two clocks (scan_seq vs lease_epoch); state persisted + `held` broker-rehydrated; quality strictly dominates (lexicographic rank, dwell only within a quantum); separate starvation escape hatch; adaptive + material-move cooldown; never evict/strand IN_FLIGHT; settle authoritative over all leased keys on every exit path; verdict map keyed `(symbol,setup_type)`; swaps bounded ≤1–2/cycle, no mid-drain preemption.

**Load-bearing NUMBERS (provisional - sim re-measures before any commit):** `per_cand≈28.2s` (band 22–44s); `clearable≈63/30-min-equiv` (band 40–80); `POOL_CAP` from sim (worked-ex band 400–1,600, midpoint ~640 is NOT to be hard-coded); universe uncapped 3,000–8,000; auditor is the only real throughput lever.

**Open items the sim must close (each shifts POOL_CAP directly):** the live `pass_rate` and `enter_rate` on the *expanded small/mid-cap* universe (10%/34% are S&P-500-era / disputed n=10); the true production cycle period; the real IEX bar-refresh frequency for thin names; and the verified Alpaca Snapshots symbols-per-request cap.