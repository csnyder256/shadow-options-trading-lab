# OPTIONS SHADOW PLATFORM - COMPLETE END-TO-END FLOW

**Generated 2026-07-10 night from the audited tree (post `opts-rework-exit-core-v1` +
`opts-fix-math-audit-20260710`). Authority for the rules text WAS `docs/OWNER_RULES.md` - 
RETRACTED AND DELETED 2026-07-16 by owner directive (see `docs/OWNER_RULES_RETRACTED.md`):
the rules text below is historical context, not authority; behaviors stand on evidence.**

> **RESOLVED same night:** `docs/OWNER_RULES.md` was written 2026-07-10 ~19:15 CT, minutes after
> this doc's tree scan (a race between two concurrent writers, kept here for audit honesty - 
> the scan-time flag read: "does not exist … verified by full-repo search"). The file now
> carries the verbatim 26 (recovered transcript, provenance line included), the owner's 2026-07-10
> governing correction, and the dated directives. `[OWNER-VERBATIM]` tags below cite the engine
> docstring quotes, which match OWNER_RULES.md word-for-word.
> **Tamper-evidence pin (added 2026-07-10 triage):** OWNER_RULES.md SHA-256 =
> `d25e74fe6658117746b25996576330491f17139a1c48e7a4b2f10a39ff448425` (first-12 `d25e74fe6658`);
> re-hash before trusting any quote chain.
>
> **2026-07-10 LATE-NIGHT TRIAGE UPDATE:** an external no-code-access AI audited this document;
> every finding was verified against the code (6 read-only agents + 2.2M-path Monte-Carlo).
> Sections below carry dated corrections where this doc trailed the code. Changes shipped from
> that triage: alerts.json BOM pager fix, nightly cache refresh BUILT (ATLAS-CacheRefresh),
> heartbeat schema 2 + data-plane pager, lane-2 RVOL scale fix (opts-fix-lane2-rvol-scale-v1),
> mu_blend label correction, provenance-enforcement test (tests/test_provenance_registry.py).

**Purpose of this document:** the owner audits it to verify that NO invented behaviors remain
anywhere in the decision flow after tonight's corrections. Every factual claim below was taken
by reading the current code; each claim cites file + function. Where the code is ambiguous the
claim is marked **AMBIGUOUS** with the code quoted. Nothing here is written from memory or
assumption.

**Provenance tags used in this document (exit rules and constants):**

| Tag | Meaning |
|---|---|
| `[OWNER-VERBATIM rule N]` | Direct implementation of one of the owner's 26 considerations; quote given from the engine docstring |
| `[DIRECTIVE - date, name]` | A dated explicit owner order outside the 26 (policy clocks, overnight rule, carve-outs) |
| `[DERIVED - citation]` | Mathematically derived; derivation cited in code |
| `[CALIBRATION - sweep id]` | Author-proposed number, pre-registered in `runtime/backtest_out/sweep_ledger.jsonl` |
| `[ADDITION - sweep id]` | A new rule (not one of the 26), pre-registered |

---

## 1. SCHEDULERS - what fires when (times CT; live-verified via `Get-ScheduledTask` 2026-07-10)

| Task | Trigger (CT) | State now | Action (verified command line) |
|---|---|---|---|
| ATLAS-Premarket | daily 05:15 | Ready | `.venv\Scripts\python.exe scripts\build_day_briefing.py` |
| ATLAS-LiveDay | daily 07:30 | Ready | `powershell ... scripts\launch_live_day.ps1 -Scanner -BuildRsTable -UntilTime 15:20` |
| ATLAS-IVSnapshot | daily 14:45 | Ready | `.venv\Scripts\python.exe scripts\snapshot_iv.py --once` |
| ATLAS-OvernightLab | daily 15:25 | **Disabled** | `.venv\Scripts\python.exe scripts\run_overnight_lab.py --once` |

> **AUDIT FLAG (explained):** ATLAS-OvernightLab is **deliberately Disabled for the
> 2026-07-11/12 weekend** (Wave-0 step 4 of the pivot plan: it would otherwise fire at 15:25
> Saturday mid-refactor). It is re-enabled during the Sunday rehearsal (2026-07-12 evening)
> before Monday's first corrected-engine session.

### 1.1 ATLAS-Premarket → `scripts/build_day_briefing.py`

- `main()` first invokes the research crew as a subprocess unless `--skip-crew`
  (`_run_crew()` → `scripts/research_crew.py`, 300 s timeout, ANY failure tolerated silently).
- `scripts/research_crew.py` (`main`): gathers earnings (Finnhub `/calendar/earnings`),
  overnight catalyst artifacts (`runtime/catalyst_*.json[l]`), prior-day movers
  (`runtime/harvest_daily_cache/*.parquet`), fans ONE fenced packet to every configured free
  cloud provider (`atlas/crew/providers.load_crew_providers`), merges cross-model consensus,
  validates against a HARD symbol allowlist, and atomically writes
  `runtime/hunt_list.json` with a top-level **`candidates`** key (`payload` dict in `main`,
  capped `MAX_CANDIDATES = 25`). Output is explicitly a LOOK-trigger: untrusted data.
- `build_day_briefing.main()` then compiles `runtime/day_briefing.json` (atomic write):
  session shape (`session_close_minute`/`is_trading_day`), events today + next-7-days,
  opex/witching/month-end/quarter-end flags (`is_opex`, `is_witching`, `is_month_end` - 
  deliberately holiday-blind, documented in the function docstring), hunt list enriched with
  signed days-to-earnings (Finnhub, fail-open) + `earnings_flag` (|days| <= 1), prior scorecard
  digest, `vix: null` (stable schema placeholder). `build_briefing()` is pure; every section
  fails open into `notes`; the process always exits 0.
- **Consumer note:** the shadow runner reads `runtime/hunt_list.json` directly
  (`run_options_shadow.load_hunt_list`), not `day_briefing.json`. The briefing is the
  human/mesh artifact; the hunt list is the machine feed.

### 1.2 ATLAS-LiveDay → `scripts/launch_live_day.ps1` (forwarding SHIM)

`scripts/launch_live_day.ps1` is a 34-line shim (header comment: "FORWARDING SHIM (2026-07-10
all-in options pivot)"). The scheduled task still passes the archived-equity flags
`-Scanner -BuildRsTable` (verified in the live task action); the shim accepts and **ignores**
them, logs the forward to `runtime/launch.log`, and dot-invokes
`scripts/launch_options_day.ps1 -UntilTime 15:20` in-process (comment: `-File` cannot bind
`-Switch:$false` in PowerShell 5.1). The repoint one-liner for retiring the shim is in its own
header.

### 1.3 `scripts/launch_options_day.ps1` - the day supervisor

Read top to bottom (all claims from the script itself):

1. **Tradier preflight - WARN-and-launch, never abort.** Writes
   `runtime/options_preflight.py` (inline heredoc), which tries
   `TradierData.from_local_config` on `config/tradier_shadow.local.yaml` then
   `config/tradier.local.yaml` and does one `get_quotes(['SPY'])`. Non-zero exit → log line
   `TRADIER PREFLIGHT WARN ... launching anyway` + ntfy page (priority `high`); the stack
   still launches (a token-less shadow degrades to heartbeat-only by design).
2. **Starts** (hidden windows, stdout/stderr redirected to `runtime/*.log`):
   `scripts/run_options_shadow.py` (abort + page ONLY if it dies within 3 s of spawn - exit 3),
   `scripts/news_tap.py --poll-seconds 30 --heartbeat runtime/news_tap_heartbeat.json`
   (best-effort, self-exits without creds, never respawned),
   `scripts/watch_hub.py` on :8770 if not already healthy (`-Hub` default on; browser
   auto-open unless `-NoBrowser`), and `scripts/alert_watch.py --options-only`
   (`-Alerts` default on).
3. **Run loop until `-UntilTime` (default 15:20 CT)**: sleeps 60 s per pass; honors
   `runtime/STOP_DAY.flag` (written by `scripts/stop_all.ps1`, cleared at start). **Flag
   lifecycle (verified 2026-07-10):** stop_all writes it BEFORE killing anything (so the crash-
   restart loop can't resurrect the shadow), the launcher deletes it at START (never in the
   `finally` - a post-stop leftover is benign because the next launch clears it), worst-case
   flag-to-exit delay ≈ 60-65 s (sleep-first loop; the flag check precedes the respawn check,
   so no post-flag respawn is possible); the shadow
   gets up to **3 crash-restarts** with fresh log files
   (`options_shadow.restartN.{out,err}.log`); the 4th death gives up for the day and pages
   ("ATLAS: options shadow DOWN for the day"). News-tap death is tolerated without respawn.
4. **Teardown** (`finally`): stops shadow + news tap + alerter; the hub is left running.
5. **Pager** = `Page()` → ntfy topic from `config/alerts.json`; page failures never block.

UntilTime rationale (script header): 16:00 ET close + late-close window - index-ETF options
quote to 16:15 ET, and the 16:10 ET hard flat needs the stack alive past 15:10 CT.

### 1.4 ATLAS-IVSnapshot → `scripts/snapshot_iv.py`

15:45 ET single pass: for each watch symbol (default `SPY,QQQ,IWM`), nearest 3 expirations'
chains via Tradier `greeks=true`, ATM strike per expiration, `atm_iv` = vendor ORATS IV first,
else solved from the ATM mid (`_atm_iv_for_expiration`); rows upserted into
`runtime/options_iv.db` via `atlas/options/iv_archive.IVArchive`. Fail-open per symbol; missing
token exits 0. **Note:** `main()` reads `config/tradier.local.yaml` only - NOT the shadow
token file. Registered half-day caveat (in `register_mesh_tasks.ps1`): fires 14:45 CT
year-round, so on 13:00-close half days the snapshot lands post-close (known limitation).
The archive feeds `IVArchive.iv_rank()` (0–100 rank vs archived history; `None` while warming
up under 10 sessions), which the runner passes to the selector as nullable context.

### 1.5 ATLAS-OvernightLab → `scripts/run_overnight_lab.py` - see §9.4.

### 1.6 ATLAS-AuthKeepalive (broker auth keepalive)

A read-only weekly OAuth refresh probe kept the **grading-side** broker token warm for
truth-validation. Its client and probe script are excluded from the public copy, so neither
ships here. The options day path itself needs **no Robinhood** - stated in
`scripts/launch_options_day.ps1` header: "It needs NO Robinhood, NO Alpaca and NO llama-swap at
launch."

---

## 2. DAY-ROLL - `run_options_shadow.OptionsShadowCore._roll_day`

Runs on the first `tick()` whose ET date differs from `self._day`. Steps, in code order:

1. **Reset per-day state**: fresh `LiveBarBuilder`; clears `_session_open`, `_last_ctx`,
   `_backfilled`, `_iv_series`.
2. **Session calendar** (`atlas/options/session_calendar.py`):
   `close_min = session_close_minute(d, days=load_days(client=...))` - 960 normal / 780 on the
   2026-11-27 and 2026-12-24 half days; `days` comes from a weekly-cached Tradier
   `/v1/markets/calendar` fetch (`refresh_calendar`, cache
   `runtime/market_calendar.json`) failing open to the hardcoded NYSE-2026 tables; a date
   missing from the mapping falls back to weekday-open-at-960 ("the fetch is an UPGRADE,
   never a dependency" - module docstring). `_late_close_flat_min = close_min + 10`.
3. **Per-day param derivation**: `self._exit_params = ExitParams.for_close(close_min)`
   (`exit_engine.ExitParams.for_close` - shifts every close-anchored clock by
   `close_min − 960`; `for_close(960) == ExitParams()` field-for-field is the pinned
   byte-identity; a 13:00 half day derives 12:00/12:30/12:45/12:59 clocks + 13:10 hard flat)
   and `self._selector_params = SelectorParams.for_close(close_min)`
   (`selector.SelectorParams.for_close` - `no_0dte_after_min = close_min − 120`, keeping the
   "two hours before the close" intent: 14:00 normal, 11:00 half days).
4. **Journals** a `session_calendar` event (`day`, `close_min`, `trading_day`).
5. **Events today**: `_events_today = oevents.is_event_day(date)` (see §4 lane 3 and §8 policy
   clocks; event source = `atlas/options/events.py`: hardcoded 2026 FOMC + FRED-fetched or
   fallback BLS CPI/NFP tables, cached weekly at `runtime/econ_calendar.json`).
6. **Noise profiles**: for each `watch` symbol, `_read_cached_profile` reads
   `runtime/intraday_cache/{SYM}_1min.parquet` (READ-ONLY - "never fetches at runtime") and
   builds `lanes.build_noise_profile(symbol, df, lookback_days=14)`; `None` (absent/thin cache,
   fewer than 5 usable sessions) → log "lane1/1b stand down" for that symbol.
   **BUILT 2026-07-10 (was a known gap):** `opts-fix-noise-cache-refresh-v1` is implemented - 
   `scripts/refresh_intraday_cache.py` (Alpaca IEX via `fetch_intraday_bars`, multi-day
   catch-up, sanity-gated atomic writes, fail-open exit-0) + scheduled task `ATLAS-CacheRefresh`
   daily 15:35 CT. First run caught up 07-09 + 07-10 (SPY last bar now `2026-07-10 15:59 ET`).
   Source is deliberately Alpaca, NOT Tradier: the cache's volume column is IEX single-venue
   scale and mixing consolidated bars would corrupt it (see the lane-2 RVOL note, §4.3).
7. **Lane arming** (fresh instances per day - per-day dedup is per-instance,
   `lanes.py` module docstring): `IndexTrendLane(profiles, p_thesis, range_percentile_min,
   close_min)`, `Last30Lane(profiles, ...)`, `InPlayORBLane(cands, rvol_min, price_min, ...)`,
   `MacroReactionLane(events_today, ...)`, `PreEarningsStubLane()`.
8. **Lane-2 candidates** (`_lane2_candidates`): `load_hunt_list()` reads
   `runtime/hunt_list.json` tolerantly - accepts list, `{"symbols": [...]}` **or the crew's
   actual `{"candidates": [...]}` shape** (2026-07-09 fix `opts-fix-huntlist-candidates-key`;
   reading only `symbols` had silently starved lane 2); one malformed row never disarms the
   day. Optional `lane2_scan_symbols` gap scan (|gap| >= `lane2_gap_min_pct` 4%) adds
   non-hunt-list names. Any candidate missing a Tradier `average_volume` (THE lane-2 RVOL
   baseline since `opts-fix-lane2-rvol-scale-v1` - the cached `avg_first5_volume` never
   gates) gets a dedicated quote fetch for it; if still absent the runner journals
   `lane2_rvol_baseline_missing` - "InPlayORB stands down for this name"
   (observed live 2026-07-10 for symbol LION). Candidates sorted by |gap| desc, capped at
   `lane2_max_candidates` (10).
9. **Cross-day position rebuild**: `self.positions` is rebuilt from
   `ledger.open_positions_all()` (`shadow.ShadowLedger.open_positions_all` - ALL unexited,
   un-merged entries regardless of day; the docstring states why: an overnight hold "would be
   orphaned at the next day roll: never marked, never exited"). Per position the loader
   re-primes `peak_mid`, **`peak_bid`** (d2* high-water), MFE/MAE via `observe_underlying`,
   `last_mark_ts`, and re-counts consecutive `theta_share` **breaches** against the ENGINE's
   own `ExitParams().theta_share_max` (lazy import in `_open_positions` so a registered tweak
   can't desync restart memory). Entries whose `expiry < today` are excluded from live
   tracking and journaled ONCE as `expired_unexited_position` (dedup against prior journal
   rows) - the grader still sees them (§9.1).
10. **`entries_today`** = count of today's entry records (drives the position-id suffix).
11. **IV-series re-seed**: each open position's trailing-45-min IV deque is rebuilt from its
    stored marks so a restart doesn't blank the IV trend "and a single failed solve doesn't
    collapse iv to 1e-4 mid-position" (comment in `_roll_day`).

**`config_hash` semantics** (`run_options_shadow.config_hash` + `load_shadow_config`): SHA-256
(first 12 hex) of the *effective options_shadow config only* - the in-code `DEFAULTS` dict
overlaid by `config/hunter.yaml`'s top-level `options_shadow:` block. Nothing else (no exit
params, no selector params) enters the hash. The yaml block currently does **not exist**
(verified: loaded cfg == DEFAULTS), so the hash is that of DEFAULTS:
**`6c1dc2a4e1a7`** (computed live from the tree while writing this doc). It is stamped on
every entry record (`build_entry_record(config_hash=...)`) - a config change starts a new
entry cohort.

> **AUDIT NOTE (RESOLVED 2026-07-10):** `opts-runner-defaults-v3` records the
> `3512f9a723da → 6c1dc2a4e1a7` move in its note text, and `opts-runner-defaults-v3-hashpin`
> pins `6c1dc2a4e1a7` as a machine-greppable `config_hash` FIELD (append-only correction; v3
> also carries a mislabeled `type`). `tests/test_provenance_registry.py` now asserts the LIVE
> `config_hash(load_shadow_config())` always has a `config_hash`-field row - this class of gap
> is machine-checked from here on.

---

## 3. FEEDS / BARS

### 3.1 Polling - `atlas/hunter/feed.HunterFeed`

- `poll(symbols)` = ONE batched Tradier quotes call for the whole watch →
  `Tick(symbol, ts_epoch, last, bid, ask, spread_bps, day_cum_volume)`. Fail-open: any
  transport/parse error or budget exhaustion returns `{}`. Self-caps its own request rate
  (`cap_per_min` - runner passes `tradier_self_cap_per_min` = 60 of the account's 120/min).
- Watch set per tick (`OptionsShadowCore._watch_symbols`): `cfg["watch"]`
  (SPY/QQQ/IWM) + lane-2 candidates + every open position's underlying, deduped.

### 3.2 Tick → 1-min commit - `feed.LiveBarBuilder`

- `on_tick`: pure per-symbol accumulation; a **left-labeled** 1-min bar is emitted only when a
  tick arrives in a LATER minute ("the FSM only ever sees closed bars"); bar volume =
  day-cumulative-volume delta, guarded to never go negative on cumvol resets; stale /
  out-of-order ticks and minutes already covered by history are ignored.
- `_commit` is "the ONE path every completed bar takes (live tick roll-over AND backfill
  seed)" - maintains session VWAP (typical-price × volume accumulation), running HOD, ATR5m,
  retrace fraction, per-bar context snapshots.
- `session_arrays(symbol)` exposes committed-only session bars - the exit engine's
  live-trajectory estimator reads trailing closes from here; "the forming minute never leaks
  (causality)" (method docstring).

### 3.3 The tick gate at close - `run_options_shadow.OptionsShadowCore.tick`

```python
if dt.hour * 60 + dt.minute < self._close_min:
    # the tick gate IS the after-hours freeze: _last_ticks/_last_ctx stop updating at
    # the close (S freezes at the last in-session print with zero new state) and the
    # bar builder never forms post-close synthetic bars
    ticks = self.feed.poll(watch)
```

Underlying quotes are simply not polled at/after `close_min`; position marks continue via the
option-NBBO path (§7), which is what makes the after-hours ladder S-free by construction.

### 3.4 Backfill - `OptionsShadowCore._backfill`

Once per symbol per day: `feed.backfill(symbol)` (one Tradier timesales call → today's
completed 1-min bars) seeded through `builder.seed_bar` + `_on_completed_bar(backfill=True)`.
Backfill-era signals are not entered: `_on_signal` journals `signal_expired` when
`minute_now > sig.expires_minute` ("stale (backfill-era or slow loop)") - but lane dedup state
still arms (module docstring: "stale backfill-era signals die on expires_minute - dedup state
still arms"). Observed live 2026-07-10 in the journal (IWM/DAL/PFE `signal_expired` rows from
an evening `--once` run).

### 3.5 Bar routing + C5 shock revals - `OptionsShadowCore._on_completed_bar`

- Bars with `minute < 09:30` or `minute >= close_min` **never reach lanes** (2026-07-10 refute
  find, comment in code: premarket bars "were burning IndexTrendLane's one-per-side latch and
  priming session_open off a premarket print"; registered in
  `opts-structural-fixes-20260710-r2`).
- **C5 price-shock reval** (registered `opts-tweak-reval-triggers-v1`): per underlying, a
  trailing deque (maxlen 21) of 1-min close-to-**previous**-close |moves| (comment: sparse
  single-tick bars carry the move BETWEEN bars); once >= 6 history entries exist, a move
  `> max(reval_shock_floor=0.002, reval_shock_mult=3.0 × trailing mean |move|)` sets
  `last_mark_ts = 0` on every open position on that underlying (marks NOW instead of waiting
  the cadence) and journals `reval_trigger`. Explicitly **observability only** - "WHEN we
  mark, never WHAT we do" (DEFAULTS comment).
- Each in-session bar builds a `lanes.MinuteCtx` (symbol, minute, OHLCV, session_open, svwap,
  `blackout` = `events.in_blackout` at the bar-close instant) and is fed to every lane;
  a lane exception journals `lane_error` and never kills the loop.

---

## 4. LANES - `atlas/options/lanes.py` (all pure: no clock, no IO, no network)

Shared conventions (module docstring "Interpretations pinned here"): bars are left-labeled
(bar `m` closes at `m+1`); 5-min boundary close = `(minute + 1) % 5 == 0`; noise is
**gap-adjusted** (measured from TODAY'S OPEN, never the prior close);
`range_percentile_14d` = percentile rank of the most recent complete session's high−low range
within the trailing window (< 50 = dead-vol regime). Each `LaneSignal` carries
`target_move`, `p_thesis` (runner default 0.5), `horizon_T`, `mu_thesis`
(= `ln(1 + signed target) / horizon`, `_mu_from_target`), and `expires_minute`.

### 4.1 Lane 1 `index_trend` - `IndexTrendLane`

- **Stand-down (MANDATORY vol condition):** `range_percentile_14d < 50`
  (`range_percentile_min`, runner cfg) → `update()` returns None all day ("the unconditional
  version is dead post-2015", module docstring).
- **Trigger** (`update`): only on a 5-min boundary close; `move = close/session_open − 1`;
  CALL when `move > noise_at(minute)` AND `close > svwap > 0`; PUT when `move < −noise` AND
  `0 < close < svwap`. One signal per (symbol, direction) per day (`_fired` set).
- **Target** = `max(0.35 × remaining_range_at(minute), 2 × noise)`; horizon = rest of day;
  signal TTL 10 min.
- **Invalidation** (`invalidated`): VWAP recross against the position OR
  `|close/session_open − 1| < noise_at(minute)` (re-entry into the noise area). An unreadable
  mark (`close <= 0` or `session_open <= 0`) never flips the thesis.

### 4.2 Lane 1b `last30` - `Last30Lane`

- **Trigger:** `trigger_minute = close_min − 31` (bar 929 on normal days - the bar that
  **closes at 15:30:00**), with a 5-min late-arrival window for sparse feeds; ONE decision
  (fire or pass) per symbol per day. Fires the continuation side when
  `|close/session_open − 1| > 0.5 × avg_daily_range(14d)`.
- **Target** = `max(0.15 × |ret|, 0.001)` (comment: "v1 continuation target: 15% of the day
  move so far (floor 10 bps); refit at N=25"); horizon = 25 min (15:30 → 15:55); signal
  expires `minute + 6`.
- **Notes stamped:** `one_dte_only: True` and
  `planned_exit_minute = trigger_minute + 1 + 25` (= 955 → **15:55 planned exit**,
  `opts-tweak-planned-exit-v1`; honored by the engine's `planned_exit_flat`, §8).
- **Contract preference:** `run_options_shadow._chain_rows` - for `one_dte_only`, the NEAREST
  expiration `>= 1` calendar day ("so Friday fires pick Monday - a strict dte==1 match would
  kill the 15:30 lane every Friday", docstring).
- **Invalidation:** always False - "clock-bound: exit engine's 0DTE/EOD rules govern".

### 4.3 Lane 2 `inplay_orb` - `InPlayORBLane`

- **Universe:** the runner-supplied premarket candidate list (§2 step 8).
- **Opening range:** bars 09:30–09:34 accumulate `or_high/or_low/first5_vol`.
- **Gates, evaluated once at OR completion** (`st.ready`):
  `RVOL = first5_vol / baseline >= 5.0` where baseline = `average_volume ×
  FIRST5_UCURVE_FRAC` (0.04, the documented intraday-U-curve share) - **UNIFORMLY since
  2026-07-10 (`opts-fix-lane2-rvol-scale-v1`)**: live first-5 volume is CONSOLIDATED tape
  (Tradier day-cum-volume deltas) while the cached `avg_first5_volume` is Alpaca IEX
  single-venue (~2-3% of tape), so gating against the cache inflated RVOL ~30-50x for
  cache-backed names; the cache value is informational only now. AND price >= $5.00 at the OR
  close. A name with no `average_volume` never fires (the §2 `lane2_rvol_baseline_missing`
  stand-down - the runner quote-fetches it for hunt-list names first).
- **Trigger:** any subsequent 1-min close above `or_high` (CALL) / below `or_low` (PUT); one
  per side per day.
- **Target** = `2 × (or_high − or_low) / close` (2 × OR height, fractional); horizon = rest of
  day; TTL 10 min.
- **Invalidation:** close back inside the OR, or VWAP recross against the position.

### 4.4 Lane 3 `macro_reaction` - `MacroReactionLane`

- Armed ONLY when the runner passes today's event kinds (`events.is_event_day`); SPY only.
- **CPI/NFP:** measured on the first bar with `minute >= 584` (closes 09:45):
  `move = close / session_open − 1`; **FOMC:** reference = close of the first bar with
  `minute >= 839` (the 14:00 close), measured on the first bar with `minute >= 854`
  (closes 14:15). `move == 0.0` → no signal. Once per kind per day.
- **NEVER pre-print:** the measured direction is held `_pending` and emitted only on a bar
  whose `ctx.blackout is None` - "the FOMC presser windows make 14:15 structurally dirty",
  so the actual FOMC emission lands on the first clean bar (registered reconciliation
  `opts-lane3_macro_reaction-amend1` notes ~14:46).
- Direction = sign of the measured move; **target** = `max(|move|, 0.002)` ("v1: the measured
  reaction repeats; floor 20 bps"); horizon runs to `exit_minute = close_min − 5` (955 →
  15:55) and `planned_exit_minute` is stamped in notes; the signal also carries
  `print_minute` (09:30 market-ref for the 08:30 prints; 14:00 for FOMC) which feeds the
  engine's `minutes_since_print` (rule f).
- **Invalidation:** always False - "rule (f) post-print forced decision governs".

### 4.5 Lane 4 - `PreEarningsStubLane`

Emits NOTHING (`update` returns None). "It exists so the runner's lane roster names it and
the spread-gate measurement week has a hook to fill in later" (class docstring;
plan: deferred-measure-first). Consequence for §8: the engine's rule (e) event-straddle exit
is currently unreachable - the runner also hardcodes `is_event_straddle=False` and
`event_tminus1_close=False` in `_reval_positions`' `PositionView` construction.

### 4.6 Signal → entry gates - `run_options_shadow.OptionsShadowCore._on_signal`

In order: stale (`minute_now > expires_minute`) → journal `signal_expired`; outside
09:30–close or weekend → `signal_after_hours_skip`; `events.in_blackout(now)` non-None →
`signal_blackout_skip` (hard window `[release−5m, release+15m]` returns the kind; else
`pre_print` inside `[release−60m, release)` - `events.in_blackout`); same-underlying
same-direction open position → **merge** (lane tag appended to `pos.lanes` + a
`shadow_merge` record via `shadow.build_merge_record`; duplicate lane → journal only);
`len(positions) >= max_concurrent` (3) → `signal_concurrency_skip`; no Tradier client →
`signal_no_client_skip`; else `_enter` (§6).

---

## 5. SELECTOR - `atlas/options/selector.select_contract` (pure; O2)

Charter (module docstring): "value-based contract choice, NOT affordability (owner, 2026-07-09:
'some contracts have better intrinsic value than others')". Chain scope: the runner fetches
expirations with DTE 0–5, bounded to `max_chain_expirations` (3) chain requests
(`run_options_shadow._chain_rows`).

### 5.1 Hard gates - exact order, values, rejection codes (each failed row is logged)

Rows of the wrong option type are skipped silently (not a rejection). Then, per row, in code
order:

| # | Rejection code | Condition to PASS (values from `SelectorParams`) |
|---|---|---|
| 1 | `crossed_nbbo` | NOT (bid>0 AND ask>0 AND ask<bid) - "crossed book - never price off it" |
| 2 | `no_quote` | mid>0 AND bid>0 AND ask>=bid |
| 3 | `non_standard_contract` | no DIGIT in the OCC root (adjusted series like NLY1, deliverable != 100, can't be priced ×100; root-vs-underlying equality rejected as false-positive-prone on BRK.B→BRKB; "the OI floor never catches these") |
| 4 | `dte_out_of_scan` | 0 <= DTE <= `max_dte` = 5 |
| 5 | `zero_dte_after_1400` | NOT (dte==0 AND minute >= `no_0dte_after_min` = close−120; 14:00 normal days) |
| 6 | `overnight_needs_dte2` | NOT (`may_run_overnight` AND dte < `overnight_min_dte` = 2). Runner sets `may_run_overnight = sig.horizon_T > rest_of_day × 1.001` (`_enter`) |
| 7 | `hold_exceeds_third_of_life` | `horizon_T <= T/3` (`hold_max_frac_of_life = 1/3`) - **0DTE CARVE-OUT**: dte==0 is exempt (`zero_dte_third_of_life_exempt = True`) [DIRECTIVE owner 2026-07-09 night; `opts-tweak-0dte-carveout-v1`] - "a same-day 0DTE's remaining life IS the rest-of-day horizon, so the gate structurally banned the 0DTE skew the plan explicitly allows before 14:00" |
| 8 | `spread_pct` | (ask−bid)/mid <= `spread_max_pct` = 0.10 |
| 9 | `spread_abs` | index underlying OR spread <= `spread_abs_max_nonindex` = $0.30 |
| 10 | `open_interest` | OI >= 1000 (index: SPY/QQQ/IWM/DIA) / 300 (non-index) |
| 11 | `volume` | volume >= `volume_min` = 100 |
| 12 | `premium_cap` | **SKIPPED - `premium_max_usd = None` by default** [DIRECTIVE owner 2026-07-10; `opts-tweak-remove-premium-cap-v1`]: "the shadow grades decision quality, never affordability - the old 350.0 rejected every 0.55–0.75-delta index contract except deep-0DTE, fighting the delta skew. Set a number to re-enable as a 'can we afford it' FINAL filter" |
| 13 | `event_{kind}` | `event_blackout is None`. **AUDIT NOTE:** the runner ALWAYS passes `event_blackout=None` (`_enter` → `select_contract(..., event_blackout=None, ...)`) because entry blackout is enforced upstream at `_on_signal` (§4.6) - this gate is live code but dead in current wiring |
| 14 | `no_iv` | `implied_vol(mid, ...)` solvable, else vendor IV > 0 |
| 15 | `lotto_delta_ban` | \|delta\| >= `delta_ban_below` = **0.35** - "lotto zone - permanent ban" |
| 16 | `delta_gate` | 0.40 <= \|delta\| <= 0.80 |
| 17 | `lambda_band` | 15 <= λ (= \|delta\|·S/mid, effective leverage) <= 90 |

### 5.2 EV stage - full-BSM scenario repricing ("never linear-greek-only")

- `om.ev_hold_thesis(...)` (`atlas/options/math.py`): thesis mixture
  `p_thesis × ev_hold(mu that reaches target over horizon) + (1 − p_thesis) × ev_hold(mu=0)`;
  each `ev_hold` revalues the contract by full BSM over a Gauss-Hermite grid (n=11) of
  underlying scenarios; entry priced at the **ask** (worst-ledger fill), horizon capped at
  remaining life; the estimated exit half-spread is subtracted (`ev_share = res["ev"] −
  spread/2`).
- Gates in order: `ev_pct_floor` (EV% of ask >= **10.0**), `ev_vs_spread`
  (EV$ >= **2×** round-trip spread × 100), `p_profit_floor` (p_profit >= **0.40**).
- **p_profit is now EXACT** [`opts-fix-math-audit-20260710`]: `ev_hold` computes
  P(value at horizon > mid) as a single lognormal tail probability at the monotone critical
  spot S\* (`_critical_spot`, geometric bisection) - replacing the Gauss-Hermite
  indicator-through-quadrature that "was quantized to ~10 attainable values and flipped the
  selector's 0.40 floor" (`ev_hold` docstring). Same audit: exact truncated-lognormal
  E[intrinsic] at expiry (`_expected_intrinsic`), discounting of e_value by `exp(−r·dt)`
  (undiscounted was a pro-hold bias), and the erfc-form `_phi` (left-tail underflow fix).
- Also logged per pick: `p_touch_target` = exact GBM first-passage probability to the target
  (`om.p_touch`, mu=0) - logged context, not a gate.

### 5.3 Score, skew, top-N - `select_contract` stage 3

```
score = ev_pct
        − 0.5 × spread_pct × 100
        − 0.3 × max(0, iv/hv20 − 1.2) × 100     (only if hv20 given; runner passes hv20=None)
        − 0.2 × max(0, iv_rank − 50)            (only if iv_rank given; nullable IVArchive)
        + 5.0 if 0.55 <= |delta| <= 0.75        (delta_preferred)
```

The **+5 delta-skew** is a **[CALIBRATION - `opts-calib-plan-era-constants-v1` (catch-all row
registering the plan-era constants)]**. Honesty note (2026-07-10 triage): at typical ev_pct
scales (10–40) a +5 bonus is a real skew WEIGHT, not the "TIEBREAK" the module docstring
claims - the wording overstates; the number itself is registered, and the entry records'
`runner_up_snapshot` exists precisely to measure its cost/benefit at N (counterfactual-selector
lab). Change it only on that evidence. Picks are score-sorted; `top_n` (3) returned;
`best_dte_outside_skew` flags when the argmax lands at DTE 4–5 ("evidence to renegotiate the
cap, never a silent override" - module docstring). Flags added per pick: `spread_5_10pct`,
`zero_dte`; the runner appends `zero_dte_afternoon` (dte==0, minute >= 12:00),
`spread_gt_5pct`, `overnight_exception` (`_enter`).

No picks → journal `no_pick` with the full rejection-code histogram (the overnight lab's
question generator watches for one code holding > 50%, §9.4).

---

## 6. ENTRY / FILLS - `atlas/options/shadow.py`

### 6.1 Three-fill ledgers (module docstring "THREE FILL LEDGERS per trade")

| Ledger | Entry fill (`entry_fills`) | Exit fill (`exit_fills`) | Role |
|---|---|---|---|
| WORST | ask | bid | **the grading ledger** (buy at ask, sell at bid) |
| BASE | mid + 0.35 × (ask − mid) | mid − 0.35 × (mid − bid) | price-improvement model (`BASE_FILL_FRAC = 0.35`) |
| OPTIMISTIC | mid | mid | the mid-fill bound |

Identities enforced by construction and unit-tested: entry `optimistic <= base <= worst`;
exit `worst <= base <= optimistic`; hence net P&L `worst <= base <= optimistic`. The grader
quarantines any row violating them (§9.1).

### 6.2 Entry record schema - `shadow.build_entry_record` (written by `_enter`)

One `shadow_entry` JSONL row: `schema`, `ts_epoch`, `day`, `entry_minute`,
`position_id` (= `occ:day:minute:entries_today` - the suffix keeps same-minute re-entries
unique, `_enter` comment), `lanes`, **`config_hash`**, `signal` (full `asdict(LaneSignal)`),
`pick` (occ, strike, expiry, bid/ask, S, score, ev_usd/ev_pct, p_profit, p_touch_target,
solved_iv, delta/gamma/theta_day/vega, λ, spread_pct, dte, flags, EV `decomposition`
{delta_capture, theta_paid, spread_paid, vega_per_pt}, `best_dte_outside_skew`),
`runner_up_occs`, `nbbo` {bid, ask}, `fills` (all three ledgers), **`contracts: 1`**,
`risk_flags` (sorted, deduped), `iv_rank`, `hv20` (None), `vix` (None),
**`covariates`** and **`runner_up_snapshot`** [both registered `opts-covariates-v1`]:

- `covariates` = `{idx_ret_disp, vwap_dist, is_friday}` - "day-1 regime context (graded at N,
  never a gate)" (`build_entry_record` docstring; assembled in `_enter`).
- `runner_up_snapshot` = `[{occ, bid, ask, strike, expiry, dte, delta, score, ev_pct}]` of the
  beaten candidates - "the counterfactual-selector lab's input".

### 6.3 Merge records - `shadow.build_merge_record`

A same-underlying same-direction multi-lane fire folds into the existing position: the
position carries both lane tags (both graded); **no second entry is booked**; a
`shadow_merge` event is appended to the entries file (`ShadowLedger.write_merge` - "merges
live with entries (same grading stream)").

### 6.4 One-contract accounting; account size deliberately ABSENT

`contracts: 1` always (`build_entry_record`, `ShadowPosition.contracts = 1`). No account
value, buying power, or affordability input exists anywhere in `atlas/options/` or
`scripts/run_options_shadow.py` (verified by reading; the premium cap - the last
affordability-shaped gate - was removed per §5.1 row 12). Provenance: [DIRECTIVE - the owner
2026-07-10, recorded in `opts-tweak-remove-premium-cap-v1`: "shadow must fully ignore account
size and grade decision quality only"].

---

## 7. MARKS / HOLD - `run_options_shadow.OptionsShadowCore._reval_positions`

### 7.1 Cadence - `_mark_interval_s`

| Situation | Interval |
|---|---|
| Default (DTE >= 1, in-session) | 300 s (5 min) |
| 0DTE, minute >= close−120 (14:00 normal) | 120 s |
| 0DTE, minute >= close−30 | 60 s |
| After the equity close (late-close window) | 60 s |

Plus the C5 shock trigger (§3.5) which zeroes `last_mark_ts` out of band.

### 7.2 Quote path per mark - `_fresh_option_quote`

Batched quotes endpoint for the OCC first; chain-row fallback when the OCC is missing; `None`
when nothing usable. A no-quote mark journals `mark_no_quote`; a streak of exactly 3 journals
`mark_no_quote_streak` ("a persistently unusable book is a data problem, not routine noise").

### 7.3 IV solve + trend

In-session: `implied_vol(mid, S, K, r, 0, T, type)` per mark (vendored solver); a failed/
non-positive solve **carries the last good IV** (never appended to the series); the series
keeps a trailing 45-min window and `iv_trend_per_hour` = OLS slope of (ts, iv) per hour
(`_ols_slope_per_hour`; 0 when degenerate). After-hours: "frozen S: a solve would be fiction - 
carry the last good IV, don't extend the trend series, and hand the engine a flat trend"
(code comment).

### 7.4 UnderlyingState - `atlas/options/trajectory.py` [`opts-rework-exit-core-v1`]

Per mark (in-session only; after-hours → `under = None`, no view), from the builder's
committed closes over the trailing `mu_window_min` = 20 minutes
[CALIBRATION `opts-calib-mu-window-v1`, swept 10/20/30 - "an author-proposed value, NOT a the owner
number", module docstring]:

```
T_K    = span_minutes / (390 × 252)      window length in trading years
r_K    = ln(close_now / close_back)      window log return
mu_hat = r_K / T_K                       raw annualized drift
s_K    = iv × sqrt(T_K)                  1σ window move under the position's OWN solved IV
t_stat = r_K / s_K                       evidence strength in sigmas
```

Fails toward NO VIEW (mu_hat=None, t=0) on: < max(3, window//2) bars, non-positive close,
degenerate IV (<= 1e-3, the stale-IV sentinel), zero span (`underlying_state` docstring).

**The blend** (`trajectory.mu_blend`, applied in `exit_engine.decide_exit`):

```
w      = t² / (1 + t²)                   evidence-gated shrinkage weight - CALIBRATION-class
                                         HEURISTIC (label corrected 2026-07-10: the old
                                         "DERIVED - inverse-variance with prior variance =
                                         observation variance" claim was FALSE; that setup
                                         yields a constant w = 1/2 for every t)
mu_eff = w × mu_hat + (1 − w) × mu_prior     mu_prior = mu_thesis while thesis holds, else 0
```

Registered: the formula is named in `opts-rework-exit-core-v1`; the weight family
(w = t²/(c+t²), c ∈ {0.5, 1, 2} + a window-length conjugate column) is replay-swept under
`opts-calib-mu-blend-weight-v1` - live change only on N-evidence. Properties (module
docstring): t≈0 → the lane thesis governs; 1σ → 50/50; 2σ → 80% live.
`opposing_defense` / `defense_zone_score` are **state-only** placeholders in v1
(`UnderlyingState` comment: "populated once atlas/options/structure.py lands";
`opts-calib-defense-params-v1` / `opts-variant-defense-exit-v1` - the defense-exit is a
replay column, not live).

### 7.5 Thesis validity - `_thesis_valid`

Merged positions are invalid only when **EVERY** constituent lane's `invalidated()` says so
("each lane tag is an independent thesis for the same exposure"). After-hours: forced True
(the ladder never reads it).

### 7.6 Quote rows schema 2 with `ext` - `shadow.build_quote_record`

EVERY reval cycle appends one row to `runtime/options_shadow_quotes/YYYY-MM-DD.jsonl`:
`{schema: 2, event: shadow_quote, ts_epoch, occ, bid, ask, S, position_id, ext}` where `ext`
carries "the full engine-input snapshot so a decide_exit-based paired replay can rebuild
PositionView per stored step" [`opts-rework-exit-core-v1`]: solved_iv, iv_trend_per_hour,
mu_hat, mu_t_stat, thesis_valid, opposing_defense, defense_zone_score, minutes_to_next_print,
minutes_since_print, planned_exit_minute, named_catalyst_tomorrow, is_friday, after_hours,
theta_share_breaches, minute. "Readers are tolerant: rows without ext replay
premium-threshold variants only" (builder docstring).

### 7.7 Mark / exit bookkeeping

HOLD → `shadow_mark` row (bid/ask/mid, solved_iv, S, the engine's full `state` dict, action,
rule). SELL → `shadow_exit` row via `build_exit_record`: three exit fills, per-ledger gross
(mid-to-mid, ledger-independent) + net P&L, theta/spread decomposition
(`theta_paid = entry_theta_day × hold_trading_days × 100`), underlying MFE/MAE, hold duration,
`variant_would_hold`, rule id, full decision state. `peak_mid`/`peak_bid` high-waters update
each mark (peak_bid only on live bids - "d2* cost-basis high-water (realizable)").
`possible_halt` journaled once per stretch when a held single name's S is frozen >= 10 min
mid-session. Positions open past the close on a **non-index** underlying without a plausible
overnight grant are force-flattened (`post_close_forced_flat` via `_force_exit`, with a
journaled NBBO degradation chain fresh-quote → last-mark → entry-NBBO); index positions
proceed into the S-free after-hours ladder (index-ETF options quote to close+15,
`session_calendar.options_close_minute`).

---

## 8. THE EXIT LADDER - `atlas/options/exit_engine.decide_exit` (v2, 2026-07-10)

**The governing standard** (module docstring, owner 2026-07-10, quoted verbatim there): "the
aforementioned ~26 rules are not law. Law = mathematically + philosophically correct stances
to maximize profit taking. You are still allowed to get creative; just not allowed to say
'sell at a specific price point.' ... 'slightly casino, but educated.'"

**Standing prohibition:** NO rule fires at a premium threshold. Docstring hard consequence
(as reconciled in code - exit_engine.py:12-16): "The entry price is read in exactly THREE
places - the inert rule-(c) knob (a directive-disabled parameter), the d2\* cost-basis
backstop (a winner-protection rule whose conditions are OBSERVED COSTS, not chosen numbers),
and the (i\*) profit_present APPLICABILITY gate (which can only prevent a sale of a loser,
never cause one) - and NOWHERE in any hold/sell EV or probability computation."

> **AUDIT NOTE (RECONCILED):** this doc previously quoted an older docstring with a TWO-place
> count and flagged the (i\*) `profit_present` gate as an uncounted third read. The code
> docstring was corrected to THREE the same night; line-by-line enumeration of every
> `entry_mid`/`entry_ask`/`ret_frac` read in `decide_exit` (2026-07-10 triage verification)
> confirms the THREE-place count is literally exact.

Every decision is pure and total: `decide_exit(PositionView, now_et, ExitParams)` →
`ExitDecision(action, rule, state, variant_would_hold, theta_share_breaches)`. First match
wins; every SELL names its rule; HOLD logs the full state dict (mid, dte, T, iv, delta,
theta_day, mu_hat/t_stat/mu_eff, p_target under mu=0/thesis/eff, theta_share, ev_hold under
eff/thesis/mu0, ev_sell, p_profit, p_regain + regain_pct, profit_present, d2_armed,
defense fields, iv_trend, ret_frac, vehicle_mismatch).

**Precomputed state (top of `decide_exit`):**
- `theta_day = greeks.theta × 365/252` - theta converted to TRADING-day units
  [`opts-fix-math-audit-20260710`]; the old extra 0DTE afternoon multiplier is **REMOVED**
  from the engine's theta ("live-T BSM theta already carries its own 1/√T acceleration (the
  empirical ramp was double-counting; it survives only inside `zero_dte_effective_T` where it
  REPLACES the model clock for the p_regain barrier)" - code comment).
- `mu_eff = mu_blend(mu_hat, t_stat, mu_prior)` with `mu_prior = mu_thesis if thesis_valid
  else 0` (§7.4). ALL decision probabilities/EVs run on `mu_eff`; the `mu_thesis` and `mu=0`
  columns are logged "for divergence evidence (rule-1 upgrade audit trail)".
- `ev_h = om.ev_hold(...)` to the next decision horizon (rest of day for 0DTE, one trading
  day otherwise), IV path = observed trend capped at ±5 vol pts/day;
  `ev_sell = bid − mid` (realize now = pay the half-spread). `S <= 0` (worst-case after-hours
  restart with no backfill) zeroes all BS states - the after-hours ladder is S-free.
- `pr = om.p_regain(...)`: owner rule 2 made continuous - the regain barrier is solved at the
  horizon END (`regain_move` at `t_minus`, so the level already prices the interval's decay - 
  "the conservative-toward-holding bound"), then exact first-passage `p_touch` under `mu_eff`
  answers whether we reach it in time. 0DTE horizon = the engine's OWN rule-(a) clock (incl.
  the deep-ITM extension) with the empirical clock `zero_dte_effective_T` [MAPPING DERIVED - 
  TV∝√T ⇒ T_eff = T·e^(−2I), shown in the `math.py` docstring; the decay RAMP inside it
  (0.02/0.14 sigmoid, midpoint 14:00, slope 45) is a REGISTERED CALIBRATION
  (`opts-calib-plan-era-constants-v1`), hardcoded-v1 from published observation, refit from
  our own stored quote paths at N (plan §O5) - tag precision per the 2026-07-10 triage]. Rule 18:
  the reference is TODAY'S value (current mid), never the high-water mark.
- `tshare = om.theta_share(theta_day, |delta|, S, iv, dt_days=min(1, T×252))` - dt capped at
  remaining life [audit fix]; `breaches` = consecutive-cycle counter (carried via
  `PositionView.theta_share_breaches`, persisted through restarts §2 step 9).
- `d2_armed = entry_ask > 0 and peak_bid > entry_ask`;
  `profit_present = entry_mid > 0 and mid > entry_mid`; `iv_fresh = solved_iv > 1e-3`
  ("degraded-IV sentinel: a data failure never sells a winner").

### 8.1 RTH ladder - first-match order (exact conditions + provenance)

| # | Rule id | EXACT condition (defaults for a 960-close day) | Provenance |
|---|---|---|---|
| 1 | `a_zero_dte_clock` | `dte == 0 AND minute >= sell_clock`; `sell_clock` = 15:30 (close−30) if \|delta\| >= 0.80 else 15:00 (close−60) | [OWNER-VERBATIM rule 3 - "Always sell a 0DTE contract same-day, but do not force an early exit solely because of the clock" (quoted in `exit_engine_legacy.py` docstring; paraphrased in `exit_engine.py` line-3 mapping)]. The clock TIMES (15:00/15:30) and the 0.80 delta are POLICY "from the registered plan, not the 26" (`exit_engine.py` docstring rule-3 mapping). This is "the ONLY expiry clock". |
| 2 | `b_thesis_invalid` | `not thesis_valid` (lane invalidation, §4/§7.5) - "sell winners too" | [OWNER-VERBATIM rules 12, 20 - docstring mapping] |
| 3 | `c_premium_stop` | `stop_frac is not None AND entry_mid > 0 AND ret_frac <= stop_frac` - **INERT: `stop_frac = None` default** | [DIRECTIVE - owner 2026-07-10, `opts-tweak-disable-premium-stop-v1`]: "never exit just because the premium is lower now - losses exit via thesis (b), theta (g), the no-anchoring EV stop (h), or the clocks"; the old −0.50 behavior stays measurable as the `opts-variant-evidence-exits-v1` replay column |
| 4 | `d2_costbasis_backstop` | `d2_armed AND bid <= entry_ask` - arm when `peak_bid > entry_ask` (the round trip was realizably profitable at worst-ledger fills); fire when that gain is gone | [ADDITION - `opts-rule-d2-costbasis-v1`; conditions DERIVED (observed costs only, no chosen numbers); implements owner rules 17/23] |
| 5 | `e_event_straddle_tminus1` | `is_event_straddle AND event_tminus1_close` | [plan, Lane 4] - **currently unreachable**: lane 4 is a stub and the runner hardcodes both inputs False (§4.5) |
| 6 | `f_post_print_no_edge` | `minutes_since_print >= 15 AND ev_hold <= ev_sell` | [OWNER-VERBATIM rule 6]; the 15-min window `post_print_decision_min` is [CALIBRATION - plan-era] (marked "CALIBRATION (plan-era)" in `ExitParams`) |
| 7 | `print_window_flat` | `0 <= minutes_to_next_print <= 10` (`print_flat_lead_min`) - never hold long premium through a print | [DIRECTIVE - POLICY CLOCK, docstring "POLICY CLOCKS (provenance = the owner's explicit dated directives, not the 26)"]. `minutes_to_next_print` computed per sweep from the real calendar (`_reval_positions`; the old hardcoded-False stubs "made [this rule] unreachable dead code" - comment) |
| 8 | `planned_exit_flat` | `dte >= 1 AND planned_exit_minute set AND minute >= min(planned_exit_minute, close−1)`; a set-but-unreached planned exit SUPERSEDES the 15:45 checkpoint (returns HOLD-through) | [DIRECTIVE - `opts-tweak-planned-exit-v1`]; lanes 1b/3 stamp 15:55 (§4.2/§4.4); cap `planned_exit_cap_min` = close−1 |
| 9 | `overnight_evidence_rule` | `dte >= 1 AND minute >= 15:45 (close−15)` UNLESS (`dte >= 3 AND \|delta\| >= 0.70 AND named_catalyst_tomorrow AND not Friday`); on SELL, `variant_would_hold = ev_hold > ev_sell` | [DIRECTIVE - the owner's fork answer 2026-07-09, docstring "OVERNIGHT POLICY"]: 0–2 DTE always closed same-day; DTE>=3 may ride only with delta>=0.7 + a named next-morning catalyst + not Friday; the unrestricted arm is graded via the nightly paired replay |
| 10 | `g_theta_dominates` | `breaches >= 2 AND p_target(mu_eff) < 0.30` where a breach = a cycle with `theta_share > 0.50` | theta_share_max 0.50 [DERIVED-BY-DEFINITION - owner rule 24 "dominant" = majority share]; cycles=2 [CALIBRATION - `opts-calib-theta-cycles-v1`]; 0.30 floor [CALIBRATION - `opts-calib-p-target-floor-v1`]; P_target input = `mu_eff` per rule 11. Also feeds the logged `vehicle_mismatch` flag [owner rule 13] |
| 11 | `h_ev_hold_below_sell` | `ev_hold(mu_eff) < ev_sell` - the entry price appears NOWHERE here | [OWNER-VERBATIM rules 4, 5, 14, 15, 19, 26 - docstring mapping; "the default-deny: hold only while EV_hold > EV_sell"] [DERIVED - optimal stopping under the live drift] |
| 12 | `i_regain_low` | `profit_present AND iv_fresh AND p_regain < 0.25` - profit is present and the math says we will not see this contract value again within the actionable horizon → take it while realizable | [OWNER-VERBATIM rule 2, made CONTINUOUS per rules 11/25; also rules 15/16/18 - docstring mapping: "when the final portion arrives, P(regain today's value) collapses ... NO take-profit threshold exists"]; `p_regain_min = 0.25` [CALIBRATION - `opts-calib-p-regain-min-v1`, swept .15/.25/.35]; the profit_present applicability gate is per [DIRECTIVE - "owner directive: never exit just because the number is lower now" (code comment)] |
| 13 | `j_hold` | everything above passed → HOLD + full state log | [owner rule 11 - every mark is a full re-decision; "the once-daily 09:35 gate is GONE (v1's rule-i gating was an author restriction, removed)" - docstring rule-10 mapping] |

### 8.2 AFTER-HOURS restricted ladder (`pv.after_hours = True`; equity close passed, S frozen)

Rationale (code comment): every BS-state rule and the lane thesis "would run on fiction - 
only PREMIUM/COST-anchored rules and the hard clock survive. peak_bid keeps updating on live
after-hours NBBO (truthful - the option market trades to close+15)."

| # | Rule id | Condition | Provenance |
|---|---|---|---|
| 1 | `overnight_grant_hold` | `dte >= 3 AND \|delta\| >= 0.70 AND named_catalyst_tomorrow AND not Friday` → **HOLD** - "outrides even the late-close flat - a granted ride holds through every after-hours mark and carries to tomorrow via the ledger rebuild" | [DIRECTIVE - fork answer 2026-07-09] |
| 2 | `late_close_flat` | `minute >= close + 10` (16:10 normal / 13:10 half days) - "nothing ELSE outrides this" | [DIRECTIVE - `opts-tweak-late-close-mode-v1`; owner 2026-07-09 "don't cut off early"] |
| 3 | `planned_exit_flat` | `minute >= min(planned_exit_minute, close−1)` | [DIRECTIVE - `opts-tweak-planned-exit-v1`] |
| 4 | `c_premium_stop` | inert (`stop_frac = None`), as in RTH | [DIRECTIVE - `opts-tweak-disable-premium-stop-v1`] |
| 5 | `d2_costbasis_backstop` | `d2_armed AND bid <= entry_ask` | [ADDITION - `opts-rule-d2-costbasis-v1`] |
| 6 | `ah_hold` | else HOLD | - |

Runner-side backstops around the ladder (§7.7): `post_close_forced_flat` (non-index,
no plausible grant) and a forced `late_close_flat` at last stored mark when the NBBO dies
before flattening - both journaled, `decision_state.forced = True`, distinct from engine
decisions.

### 8.3 Policy-clock parameter table (`ExitParams`, per-day via `for_close`)

| Param | Default (960 close) | Half day (780) | Provenance |
|---|---|---|---|
| `zero_dte_sell_min` | 15:00 | 12:00 | policy clock (registered plan) |
| `zero_dte_deep_itm_ext_min` / delta | 15:30 / 0.80 | 12:30 | policy clock |
| `print_flat_lead_min` | 10 min | 10 min | policy clock (print flat) |
| `stop_frac` | **None (inert)** | None | `opts-tweak-disable-premium-stop-v1` |
| `post_print_decision_min` | 15 min | 15 min | CALIBRATION (plan-era) |
| `theta_share_max` / `theta_share_cycles` | 0.50 / 2 | same | derived / `opts-calib-theta-cycles-v1` |
| `p_target_floor` | 0.30 | same | `opts-calib-p-target-floor-v1` |
| `p_regain_min` | 0.25 | same | `opts-calib-p-regain-min-v1` |
| `eod_flat_min` | 15:45 | 12:45 | fork answer 2026-07-09 |
| `planned_exit_cap_min` | 15:59 | 12:59 | `opts-tweak-planned-exit-v1` |
| `session_close_min` / `late_close_flat_min` | 16:00 / 16:10 | 13:00 / 13:10 | `opts-tweak-late-close-mode-v1` |
| `overnight_min_dte` / `overnight_min_delta` | 3 / 0.70 | same | fork answer 2026-07-09 |

### 8.4 REMOVED tonight (with registration ids) - verify none of these behaviors remain

| Removed behavior | Where it lived | Removal id | Survives as |
|---|---|---|---|
| Forced SELL at +100% (`take_frac` rule d) - "an unregistered author interpolation citing his qualitative rules 16/21, which contain no number and no forced sell" | v1 `exit_engine.py` rule (d) | `opts-fix-remove-forced-take-v1` (immediate), completed under `opts-rework-exit-core-v1` | frozen in `exit_engine_legacy.py` BY DESIGN for measurement; replay columns |
| The trail family (trail latch, `d_trail_giveback`, `d_trailing_hold`, `trail_p_target_min`, `trail_giveback`, `take_frac` field) - "kills the g/h/i bypass BY CONSTRUCTION" | v1 rule (d) + runner latch persistence | `opts-rework-exit-core-v1` | 25%-trail replay columns only (`opts-variant-trail-arm-50-v1` adds an arm-at-+50% column) |
| Once-daily rule (i) (the 09:35 daily re-decision gate) | v1 rule (i) | `opts-rework-exit-core-v1` (item 3) | REPLACED by the continuous `i_regain_low` |
| −50% premium stop (rule c live value) | v1 `stop_frac = −0.50` | `opts-tweak-disable-premium-stop-v1` | inert param (re-armable); `opts-variant-evidence-exits-v1` replay column |
| v1 `d2_breakeven_backstop` (peak >= +50% → breakeven sell) | v1 rule (d2) | `opts-rework-exit-core-v1` (item 2) | REPLACED by the d2\* cost-basis backstop |
| 0DTE afternoon theta multiplier stacking onto rule (g) | v1 theta_day | `opts-fix-math-audit-20260710` | ramp survives only inside `zero_dte_effective_T` (p_regain clock) and the selector's logged decomposition |

The frozen baseline: `atlas/options/exit_engine_legacy.py` - header: "FROZEN 2026-07-10 (git
tag pre-pivot-2026-07-10) ... DO NOT EDIT and DO NOT WIRE INTO THE RUNNER ... Nothing imports
it at runtime" (also asserted in `exit_engine.py` docstring). Its own header flags that its
rule-16/21 attributions are WRONG - kept intact for A/B measurement.

Scale-out (owner rule 22) is deliberately NOT live: [ADDITION - `opts-variant-scaleout-v1`]
"a paired-replay column (2-lot split), default OFF - the owner specified no trigger/split; inventing
them live would repeat the interpolation failure mode. Promotion = the owner's call"
(`exit_engine.py` docstring rule-22 mapping).

---

## 9. GRADING / EVIDENCE

### 9.1 Nightly scorecard - `scripts/grade_options_shadow.py` (`grade`)

Reads the ledgers (all-time; per-day slice reported inside) →
`runtime/options_shadow_scorecard.json` + stdout. **Falsification gates first:**

1. **`malformed_exits`** (`_malformed`): any exit row missing
   `ledgers.{worst,base,optimistic}.{net,gross}_pnl_usd` or a rule id is EXCLUDED from stats
   and reported loudly - "the original 2026-07-09 grader read fields the builders never wrote
   and would have graded every lane as all-zero P&L without noticing" (docstring). The field
   contract is pinned by `tests/test_grade_options_shadow.py` against the `shadow.py`
   builders.
2. **`ledger_identity_violations`** + **quarantine** [`opts-fix-math-audit-20260710`]: a row
   breaking `worst <= base <= optimistic` is now QUARANTINED like a malformed row - "a row
   whose fill accounting is provably broken must not pool into lane means/PF/verdicts it
   would silently poison" (code comment). (Same audit: `profit_factor` infinity serialized as
   the string `"inf"`, never bare JSON `Infinity`.)
3. **`expired_unexited`**: process-gap entries are kept visible with an OCC-reality terminal
   value (auto-exercise intrinsic at the expiry day's last stored quote-path S) - "never
   graded at a stale NBBO, never silently dropped, never pooled into lane stats".

Per lane: n, three-ledger net (WORST = grading), gross (mid-to-mid), win rate, profit factor,
exit-rule mix, risk-flag decomposition (joined from ENTRY records by `position_id` - exit
rows don't carry flags), spread/theta paid totals, `cost_share_of_losses` (falsification #1 - 
the ledger must SEE the cost tax), `overnight_variant_divergences` (count of
`variant_would_hold`), `top_day_share`.

**Lane PASS bar** (`grade`, `passes = ...`): `n >= 25` AND WORST-ledger mean net > 0 AND
gross sum > 0 AND PF(worst) >= 1.2 AND top-day share < 0.5. Verdicts: PASS / ACCUMULATING
(n < 25) / FAILING.

**N policy** [registered `opts-n-policy-v1`]: verdict N = 25 per lane (unchanged statistical
floor; `PASS_N_MIN`), go-live talk at 50–100 (`GO_LIVE_N = 50` in code; the ledger row says
"50-100"), plus a **NON-BINDING interim directional read at N = 10** ("reported in /eodreport
as 'interim, no verdict, no arming'").

### 9.2 Registration discipline - `runtime/backtest_out/sweep_ledger.jsonl`

Every behavior change is a pre-registered JSONL row (`config_id`,
`type: options_shadow_{lane,tweak,fix,policy,records,...}`, `registered`, `status`) written
BEFORE first fire / effect. Verified present in the ledger tonight (all cited in this doc):
lanes (`opts-lane1_index_trend` + amend1, `opts-lane1b_last30` + amend1,
`opts-lane2_inplay_orb`, `opts-lane3_macro_reaction` + amend1), runner configs
(`opts-runner-defaults`, `-v2`), fixes (`opts-structural-fixes-20260709`, `-r2`,
`opts-structural-fixes-20260710-r2`, `opts-fix-huntlist-candidates-key`,
`opts-fix-remove-forced-take-v1`, `opts-fix-math-audit-20260710`,
`opts-fix-noise-cache-refresh-v1` [registered, NOT yet built]), tweaks
(`opts-tweak-0dte-carveout-v1`, `-planned-exit-v1`, `-late-close-mode-v1`,
`-reval-triggers-v1`, `-remove-premium-cap-v1`, `-disable-premium-stop-v1`), the master
rework row (`opts-rework-exit-core-v1`), calibrations (`opts-calib-mu-window-v1`,
`-p-regain-min-v1`, `-theta-cycles-v1`, `-p-target-floor-v1`, `-defense-params-v1`), variants
(`opts-variant-trail-arm-50-v1`, `-evidence-exits-v1`, `-defense-exit-v1`, `-scaleout-v1`),
records (`opts-covariates-v1`), policy (`opts-n-policy-v1`), research
(`opts-research-queue-v1`).

### 9.3 Paired-replay design

- **A/B baseline:** `atlas/options/exit_engine_legacy.py` - the frozen v1 engine (§8.4), for
  old-vs-new on identical stored quote paths. For the original v1-with-stop flavor, replay
  with `ExitParams(stop_frac=-0.50)` (its header says so).
- **`atlas/options/replay.py` EXISTS (landed 2026-07-10 ~19:30 CT, after this doc's scan - 
  same-night race, original flag preserved for audit honesty):** `replay_decide_exit` rebuilds
  each engine's own PositionView per stored schema-2 `ext` row (mirroring the runner's reval
  loop: peak_mid/peak_bid before the decision, breaches carried) and sells at the first SELL at
  that row's bid (worst convention); `exit_engine_ab` runs every entry through the five
  pre-registered variants (legacy_v1, legacy_v1_stop50, v2_default, v2_pregain_15/35) - 
  wired as overnight-lab stage 1b, report key `exit_engine_ab`. 6 tests in
  `tests/test_options_replay.py`. Alongside it:
- **`run_overnight_lab.exit_grid_replay`** - the pre-registered premium-threshold grid
  (STOP −0.25/−0.50/−0.75 × TAKE 0.5/1.0/2.0 × trail off/trail25) replayed PAIRED on each
  exited position's stored quote path: a variant sells at the FIRST row whose mid return from
  entry-mid crosses its stop/take, at that row's BID (worst-ledger convention); uncrossed →
  the ACTUAL exit row's bid; ACTUAL aggregated over the SAME cohort (>= 2 quote rows).
- The **overnight-fork variant** (owner's unrestricted arm) is carried per-exit as
  `variant_would_hold` (§8.1 row 9) and counted per lane by the grader.

### 9.4 Overnight lab - `scripts/run_overnight_lab.py`

Guards: REFUSES 09:15–16:15 ET weekdays (exit 3, "no override exists" - `rth_blocked`);
pid lock (dead-pid reclaim, live holder → exit 6); reads ONLY the shadow ledgers; writes ONLY
`runtime/overnight_lab_report.json` (+ lock/heartbeat); "NO import of atlas.execution or
anything order-related"; NEVER starts/stops llama-swap (module docstring). Stages, each in
per-stage containment (a raised stage → `{"error": ...}`, exit 6, others still run):

1. `exit_grid_replay` (§9.3) - full ledger history, cumulative by design.
2. `exit_efficiency` - per exit-rule MFE-capture ratio
   `(exit worst fill − entry worst fill) / (peak mark mid − entry worst fill)`.
3. `anomaly_questions` - deterministic questions from the day's journal + scorecard: zero
   entries on a trading day; lane/chain/exit-engine error counts; a `no_pick` code holding
   > 50% of rejections; malformed exits.
4. `llm_stages` - STUB: `localgate.py` (exit 0 required; anything else fail-closed) AND a
   live `health()` on the already-running server, then ONE temp-0 JSON smoke call
   (glm-4.7-flash); otherwise `{"skipped": reason}`.

### 9.5 Nightly grading procedure pointer

The nightly options grading procedure (the authority doc for grading posture) is maintained
outside this repository, one level above the repo root, and is not part of the public copy.
It pins the same ledger paths, falsification gates, and pre-registration discipline
described here.

---

## 10. MESH ARTIFACTS, CONFIG SURFACES, HARD INVARIANTS

### 10.1 Runtime artifact map (writer → file → reader)

| File (`runtime/` = junction to `C:/path/to/atlas_runtime`) | Writer | Readers |
|---|---|---|
| `hunt_list.json` (`candidates` key) | `research_crew.py` | shadow runner (lane 2), `build_day_briefing.py` |
| `day_briefing.json` | `build_day_briefing.py` | human / mesh consumers |
| `options_shadow_entries.jsonl` (`shadow_entry` + `shadow_merge`) | `ShadowLedger.write_entry/write_merge` | grader, lab, rebuild path |
| `options_shadow_marks.jsonl` | `write_mark` (HOLD cycles) | grader, lab, restart re-prime |
| `options_shadow_exits.jsonl` | `write_exit` | grader, lab |
| `options_shadow_quotes/YYYY-MM-DD.jsonl` (schema 2 + `ext`) | `write_quote` (every reval) | paired replay (lab; future decide_exit replay) |
| `options_shadow_journal.jsonl` | `ShadowLedger.journal` (skips/errors/no-picks/session_calendar/reval_trigger/...) | lab questions, /eodreport |
| `options_shadow_heartbeat.json` | `_write_heartbeat` each loop | alert_watch, hub |
| `options_shadow.lock` / `.log` / `.out.log` / `.err.log` / `.restartN.*` | runner / launcher | ops |
| `options_shadow_scorecard.json` | `grade_options_shadow.py` | briefing digest, /eodreport |
| `overnight_lab_report.json` + `overnight_lab.lock`/heartbeat | `run_overnight_lab.py` | /eodreport |
| `options_iv.db` | `snapshot_iv.py` (via `IVArchive`) | selector iv_rank context |
| `econ_calendar.json` / `market_calendar.json` | `events.refresh_calendar` / `session_calendar.refresh_calendar` (weekly caches) | events/session queries |
| `intraday_cache/{SYM}_1min.parquet` | `scripts/refresh_intraday_cache.py` nightly append (ATLAS-CacheRefresh 15:35 CT; Alpaca IEX; built 2026-07-10) after the one-shot O3 build | noise profiles (lanes 1/1b) - PRICE stats only; never a lane-2 RVOL baseline since `opts-fix-lane2-rvol-scale-v1` |
| `news_stream.jsonl` + `news_tap_heartbeat.json` | `news_tap.py` (Benzinga REST poll) | in-play correlation (context) |
| `STOP_DAY.flag` | `stop_all.ps1` | launcher run loop |
| `launch.log`, `options_preflight.py` | launchers | ops |
| `backtest_out/sweep_ledger.jsonl` | manual registration | grading discipline (§9.2) |

### 10.2 Config surfaces

- **`config/hunter.yaml` top-level `options_shadow:` block** - read tolerantly by
  `load_shadow_config`; absent keys fall back to in-code `DEFAULTS`. **The block does not
  currently exist** (verified: effective cfg == DEFAULTS; hash `6c1dc2a4e1a7`). DEFAULTS
  (all in the hash): watch SPY/QQQ/IWM; poll 10 s; max_concurrent 3; top_n 3; p_thesis 0.5;
  range_percentile_min 50; lane2 max 10 / gap 4% / RVOL 5 / price $5 / scan [];
  max_chain_expirations 3; tradier_self_cap_per_min 60; noise_lookback_days 14; r 0.04;
  reval_shock_mult 3.0 / floor 0.002; mu_window_min 20.
- **`config/tradier_shadow.local.yaml`** - the shadow's DEDICATED Tradier token (its own
  120/min budget; header comment: "the equity platform's token is untouched"). Shape:
  top-level `token:` + `env: production`. Loader (`tradier_from_yaml`) tolerates a UTF-8 BOM
  and a token at top level OR under a `tradier:` mapping; falls back to
  `config/tradier.local.yaml`.
  **AUDIT NOTE:** the runner's module docstring claims "the shadow file uses the latter"
  (nested `tradier:` mapping) - the actual file uses the TOP-LEVEL shape. Functionally moot
  (both parse); the comment is stale.
- **`config/alerts.json`** - alerter config (stdlib-only JSON on purpose): ntfy topic
  `atlas-stall-CHANGE-ME-TO-A-LONG-RANDOM-STRING` (enabled), Gmail SMTP email path gated on
  `ATLAS_ALERT_SMTP_PASS`, market-hours window 08:30–15:20 local. In `--options-only` mode
  (`alert_watch.py`, 2026-07-10 pivot) the equity analyst/:8080/halt/broker/app watches are
  DISABLED ("would false-page every session"); the **options-shadow heartbeat watch stays
  active**: heartbeat missing/stale > 180 s during market hours → page "ATLAS: options shadow
  OFFLINE (evidence gap) ... ZERO capital at risk - the shadow ledger is simply not
  recording"; recovery notice on freshness.
  **2026-07-10 triage additions:** (1) `load_config` reads `utf-8-sig` - the live file had
  silently acquired a UTF-8 BOM that degraded the alerter to DEFAULTS (EMPTY topic = pager
  dead); file re-saved BOM-free + CI canary (`tests/test_alert_watch.py`). (2) Heartbeat is
  now **schema 2** (`client_present`, `last_tick_epoch`, `last_bar_epoch`, `last_mark_epoch`)
  and a second, independent **data-plane watch** (`options_shadow_data_reason`, own latch)
  pages when the process is alive but the FEED is dead: no client, or ticks stale >
  `tick_stale_threshold_sec` (120 s OPS constant) in-session - bounded by the heartbeat's own
  `session_close_min` (the tick gate stops polling at the close BY DESIGN, half days handled
  free). This closes the verified zombie mode: token death mid-day left open positions
  UNMANAGED with a fresh-looking heartbeat.

### 10.3 Hard invariants

1. **ZERO order path.** `run_options_shadow.py` docstring: "There is NO broker-order code
   path anywhere in this module or its imports - structurally a shadow." Pinned by
   `tests/test_keep_imports.py::test_no_order_machinery_reachable_from_options`, which runs a
   **clean subprocess** import of `atlas.options.{shadow,exit_engine,selector,lanes}` +
   `atlas.hunter.feed` and asserts none of `atlas.execution.order_lifecycle`,
   `atlas.execution.broker_adapter`, `atlas.execution.guardian`,
   `atlas.execution.robinhood_adapter`, `atlas.orchestrator`, `atlas.app` appears in
   `sys.modules` ("the shared pytest process's sys.modules is polluted by whatever sibling
   tests imported first" - hence the subprocess). The shadow's entire side-effect surface is
   the fsync'd JSONL ledgers (`shadow.py` docstring).
2. **Account-blindness.** No account/buying-power/affordability input anywhere in the
   decision flow; 1 contract always; premium cap removed (§5.1/#12, §6.4)
   [DIRECTIVE - `opts-tweak-remove-premium-cap-v1`].
3. **Local-model gate is irrelevant to the day path.** The shadow runner, launcher, lanes,
   selector, and exit engine touch NO local LLM. The only local-LLM contact in the whole
   options mesh is the overnight lab's stage-4 stub, which is double-gated
   (`localgate.py` exit 0 + server `health()`), never starts/stops llama-swap, and runs
   post-16:15 ET only (§9.4).
4. **Single-writer, append-only, fsync'd ledgers** (`shadow.append_jsonl`); atomic replaces
   everywhere else (`atlas/fsutil.atomic_replace` - the WinError-5 idiom).
5. **Fail-open data plane, fail-closed compute gate.** Every feed/calendar/crew/briefing path
   degrades to a journaled fallback instead of aborting the day (§1.3, §2, §3.1); the only
   fail-CLOSED check in the mesh is the lab's localgate (§9.4).
6. **Machine-authored inputs are DATA.** `hunt_list.json` is "a LOOK-trigger only: untrusted
   DATA" (`research_crew.py` docstring); one malformed row never disarms the day
   (`load_hunt_list`); news headlines are never echoed/format-strung (`news_tap.py`
   docstring).

---

## APPENDIX - gaps & flags from the original audit, with 2026-07-10 triage status

1. ~~`docs/OWNER_RULES.md` ABSENT~~ - **RESOLVED**: exists (6,915 bytes), SHA-256 pinned in the
   header (`d25e74fe6658…`).
2. ATLAS-OvernightLab scheduled task **Disabled** (§1) - still deliberate; re-enabled at the
   Sunday 2026-07-12 rehearsal. (A weekend runtime guard was proposed by the external audit
   and REJECTED: it would block that rehearsal, and the lab's write surface is only its own
   report.)
3. ~~cache frozen at 2026-07-08~~ - **BUILT**: `scripts/refresh_intraday_cache.py` +
   `ATLAS-CacheRefresh` 15:35 CT; data current through 2026-07-10 close (§2 step 6).
4. ~~hash `6c1dc2a4e1a7` not pinned~~ - **RESOLVED**: `opts-runner-defaults-v3` +
   `opts-runner-defaults-v3-hashpin` (config_hash field); machine-checked by
   `tests/test_provenance_registry.py` (§2 audit note).
5. Selector's `event_{blackout}` gate is dead in current wiring (runner enforces blackouts
   upstream and passes `event_blackout=None`) (§5.1 row 13) - still true, accepted.
6. Engine rule (e) event-straddle exit unreachable while Lane 4 is a stub and the runner
   hardcodes its inputs False (§4.5, §8.1 row 5) - still true, accepted.
7. ~~two-place entry-price count imprecise~~ - **RECONCILED**: code docstring says THREE and the
   enumeration confirms it (§8 audit note).
8. ~~token-file docstring stale~~ - **FIXED**: both docstrings now state the top-level shape
   (§10.2).
9. ~~`atlas/options/replay.py` absent~~ - **STALE THE OTHER WAY**: it landed the same
   night (221 lines, `replay_decide_exit` + `exit_engine_ab`, 6 tests in
   `tests/test_options_replay.py`; the 5 pre-registered AB variants live in
   `run_overnight_lab.AB_VARIANTS`) (§9.3).
10. NEW (2026-07-10 triage): lane-2 RVOL consolidated-vs-IEX scale mismatch - **FIXED live**
    (`opts-fix-lane2-rvol-scale-v1`, §4.3); extending the nightly cache refresh to lane-2
    names is deferred to a future row now that the cache never gates RVOL.
11. NEW (2026-07-10 triage, register-only): the physical measure runs on σ=IV (vol-risk
    premium ⇒ mildly pro-hold everywhere) - documented in `math.py`, measured via the
    `opts-variant-realized-vol-physical-v1` replay column; and the mu_blend weight family is
    replay-swept under `opts-calib-mu-blend-weight-v1`. Neither changes live behavior without
    N-evidence.
