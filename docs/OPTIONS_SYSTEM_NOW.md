# OPTIONS SHADOW PLATFORM - HOW IT WORKS NOW (and how it changes when live)

**Written 2026-07-10 night, code-grounded across the whole tree by a 6-agent read-only sweep
(info sources · AI touchpoints · decision flow · watch/sell · shadow→live · ops/discipline).**

This is the **plain-language operating picture**. Its companion `docs/OPTIONS_SYSTEM_FLOW.md`
is the exhaustive line-by-line audit (every gate value, every math derivation); this file is the
map you read first. Where I say "unchanged from FLOW §X" I mean the mechanism is exactly as that
document describes and I am not repeating the math. Where the code and FLOW disagree, this file
follows the **code** and says so.

> **What changed since the last FLOW regeneration (2026-07-10 external-audit triage):** the ntfy
> pager was resurrected (a UTF-8 BOM in `alerts.json` had silently disabled it); the nightly
> intraday-cache refresh was **built and scheduled** (`ATLAS-CacheRefresh`); the heartbeat gained
> **schema 2** data-plane fields and a matching zombie-mode pager; lane-2 RVOL was rescaled to a
> consolidated baseline; the `mu_blend` weight was relabeled from a false "DERIVED" to a
> registered CALIBRATION heuristic; and a provenance-enforcement test now machine-checks every
> tunable constant. None of that touched the trade-decision math.

---

## 0. The one-paragraph mental model

ATLAS-options is a **shadow trader**: on live 1-minute bars it decides the option it *would* buy,
tracks that hypothetical position mark-by-mark, and decides when it *would* sell - writing every
decision to append-only JSONL ledgers and **placing no orders**. The decision core (lanes →
selector → exit engine) is **pure deterministic math with no AI, no network, and no account
awareness**. AI touches the system only at the edges: five free **cloud** LLMs suggest a premarket
*watchlist* (untrusted names that still walk every gate), and one **local** LLM does a gated
post-close smoke-test. Going live is a *build*, not a flag: there is literally no code path to
place an option order today, and a lane must first clear a statistical bar (N≥25 profitable on the
pessimistic fill ledger) before live is even discussed.

---

## 1. Where all the information comes from

One real-time market-data provider drives the live day; everything else is premarket, overnight,
or best-effort context. **Every source fails open** - any transport/parse error returns
`{}`/`[]`/`None` and the day continues on a journaled fallback.

### 1.1 The live-day feed - Tradier (the only real-time provider)

A single production Tradier brokerage token (dedicated `config/tradier_shadow.local.yaml`, its own
~120/min budget; the client self-caps at ~100/min) supplies **everything the live loop needs**:

| What | Endpoint / call | When | Feeds |
|---|---|---|---|
| Underlying quotes + RVOL | batched `/markets/quotes` (`HunterFeed.poll`, 100 symbols/POST) | every **~10 s** poll | lane bars, the RVOL baseline (`average_volume`), position underlying marks |
| Option chains + greeks | `/markets/options/expirations` then `/chains?greeks=true` (DTE 0–5, ≤3 expirations) | on each signal | the selector's contract universe (ORATS greeks + prior-day OI) |
| Option NBBO | `/markets/quotes` for the OCC, chain-row fallback | every position mark | the mark price, P&L, exit decision |
| Intraday timesales | `/markets/timesales?interval=1min` | once/symbol at startup | backfills today's bars so lanes have session context (backfill-era signals never enter) |
| Market calendar | `/markets/calendar` | day-roll, **weekly cache** | today's close minute + half-day/holiday detection |

The **watch set** each poll = `SPY/QQQ/IWM` + the day's lane-2 candidates + every open position's
underlying, deduped. Greeks used for *decisions* are **self-computed from the live mid** each mark
(the vendor ORATS greeks refresh only ~hourly); IV is solved per mark with the vendored
Black-Scholes solver. No token → the process still runs a **degraded heartbeat-only loop** (and
the new data-plane pager, §5.4, fires on exactly that).

### 1.2 Macro-event calendar (live context, weekly cache)

`atlas/options/events.py` supplies the macro blackout windows and event-day arming. **FOMC 2026
dates are hardcoded** (decision 14:00 / presser 14:30 ET). CPI and NFP dates are meant to come from
the **FRED** release-dates API - but **no `fred:` key is configured today**, so the system runs on
the **hardcoded BLS-2026 fallback tables** (the FRED HTTP path is live code but currently
unreached). Blackouts: a hard `[release−5m, +15m]` window returns the event kind; `[release−60m,
release)` returns `"pre_print"`.

### 1.3 Noise-profile cache - Alpaca IEX (built overnight, read live)

`runtime/intraday_cache/{SYM}_1min.parquet` holds 1-minute bars from **Alpaca's IEX feed** (single
venue, ~2-3% of consolidated tape - deliberately *not* Tradier, so the volume column stays one
scale). At day-roll the runner reads these **read-only** to build the lane-1/1b noise profiles
(per-minute noise band, average daily range, 14-day range percentile). As of 2026-07-10 the
**nightly refresh is built and scheduled** (`scripts/refresh_intraday_cache.py`, task
`ATLAS-CacheRefresh` 15:35 CT): it appends each closed session with multi-day catch-up, so the
profiles no longer age one day per session. **Scope is SPY/QQQ/IWM only.** Critical rule (post
`opts-fix-lane2-rvol-scale-v1`): the cache's `avg_first5_volume` is IEX-scale and **never gates
lane-2 RVOL** - it is informational; lane-2 uses the consolidated Tradier `average_volume` instead.

### 1.4 IV archive - ORATS via Tradier (EOD, `options_iv.db`)

`scripts/snapshot_iv.py` (`ATLAS-IVSnapshot` 14:45 CT) writes one ATM-IV row per (symbol, day,
tenor) into a SQLite archive - vendor ORATS IV at the ATM strike, else solved from the ATM mid. The
runner reads `iv_rank` (0–100, `None` until ≥10 sessions accumulate) **at entry only**, as nullable
context to the selector. (Note: `snapshot_iv` reads `config/tradier.local.yaml`, not the shadow
token.)

### 1.5 Premarket watchlist - Finnhub + the crew (see §2)

`runtime/hunt_list.json` (the crew's output, §2) plus Finnhub `/calendar/earnings` feed the lane-2
candidate universe and the human `day_briefing.json`. The runner reads `hunt_list.json` **directly**
(the briefing is a human/mesh artifact).

### 1.6 Live news tap - Benzinga via Alpaca (context only)

`scripts/news_tap.py` polls Alpaca's bundled Benzinga REST feed every 30 s → `news_stream.jsonl`.
It is **best-effort context, gates nothing**, treats all headline text as untrusted, self-exits
without creds, and is never respawned.

### 1.7 What is *not* wired (honest flags)

- **VIX/VXN regime** - `iv_archive.py` docstrings mention a "FRED VIX/VXN percentile" regime
  fallback; **no such feed exists** on the options path (`vix` is hardcoded `None` everywhere). It
  is aspirational plan text, not a source.
- **Equity-era feeds** (`alpaca_feed.py` daily bars, `market_collector.py`, SAM.gov contracts, the
  Robinhood day feed) are archived/dormant and **not on the options path**.

---

## 2. When we consult AI - cloud vs local (and never on the live path)

AI touches the platform in **exactly two isolated, non-live places**, and the trade-decision path
touches **none**.

### 2.1 CLOUD - the research crew (premarket only, once per morning)

- **When:** the `ATLAS-Premarket` task, **05:15 CT (06:15 ET)**, runs `build_day_briefing.py`, which
  spawns `research_crew.py` as a subprocess (300 s timeout, any failure tolerated). There is **no
  intraday or live-session cloud call anywhere.**
- **Who:** five free-tier providers, each a fail-to-`None` HTTPS adapter over stdlib `urllib` (no
  SDKs): **OpenRouter** (nemotron-3-super-120b:free), **Groq** (llama-3.3-70b-versatile),
  **Cerebras** (zai-glm-4.7), **Google Gemini** (gemini-flash-latest), **Z.ai** (glm-4.7-flash).
  Only providers with a configured key are built; zero configured is a normal exit-0.
- **What they get:** one plaintext packet of **public-market data only** (today's earnings,
  catalyst artifacts, prior-day movers) with all external text sealed inside fenced
  `UNTRUSTED DATA BLOCK` sections, backticks/newlines scrubbed so nothing can break the fence. The
  system prompt tells the model it is a research assistant, that fenced text is data-never-
  instructions, and to reply with **only** a JSON array of `{symbol, catalyst_kind, summary,
  confidence}`.
- **How it's merged & gated:** tolerant-parse → cross-model consensus (a symbol counts once per
  model, ranked by how many distinct models name it) → a **hard drop-never-repair allowlist**
  (`^[A-Z]{1,5}$` symbols, a closed 11-kind catalyst enum, 280-char summaries) → capped at 25 →
  `hunt_list.json`.
- **The crucial property:** the output is **untrusted LOOK-trigger DATA, never a command.** Every
  candidate is just a symbol worth *evaluating* - it still must pass lane-2's opening-range-break +
  RVOL≥5 + price≥$5 gates and the entire selector/EV cascade before any hypothetical entry. One
  malformed row never disarms the day.

### 2.2 LOCAL - the overnight lab (post-close, gated, currently a stub)

- **When/where:** the *only* local-LLM contact is `run_overnight_lab.py` **stage 4**, a one-shot
  temperature-0 JSON smoke call to `glm-4.7-flash` at `127.0.0.1:8080`. It is a **stub** - the
  wiring is proven without a real job yet. Its task (`ATLAS-OvernightLab` 15:25 CT) is **currently
  Disabled** for the pivot weekend.
- **Double-gated, fail-closed:** it runs only if (1) `localgate.py` returns exit 0 **and** (2) the
  server answers `health()` (HTTP 200). Anything else - gate blocked, crash, timeout, server down - 
  is a silent recorded skip.
- **Hard rails:** it **refuses 09:15–16:15 ET** on weekdays (exit 3, "no override exists"), reads
  only the shadow ledgers, and **never starts/stops llama-swap**.

### 2.3 The live decision path imports ZERO AI (the proof)

An exhaustive grep of `atlas/options/` for any LLM/provider/HTTP-to-8080 reference returns **"No
matches found."** `run_options_shadow.py` imports only Tradier/feed/options-math modules. The four
decision modules are self-described pure math (`lanes.py`, `selector.py` "no IO, no clock reads";
`exit_engine.py` imports only math/greeks). This is mechanically pinned by
`tests/test_keep_imports.py::test_no_order_machinery_reachable_from_options`, a clean-subprocess
import that asserts no execution/orchestrator module is even reachable. **AI only ever suggests
premarket watchlist names and runs post-close analysis - it never sees, sizes, or vetoes a live
trade.** (Note: `mu_hat`/`mu_blend`/`mu_eff` in the exit engine are *ordinary trailing-close OLS
statistics*, not a model call - the "mu" naming is unfortunate.)

---

## 3. How a decision to open gets made

The pipeline, per completed 1-minute bar:

**Bars (causal by construction).** `LiveBarBuilder` emits a **left-labeled** bar only when a tick
arrives in a later minute - so lanes only ever see *closed* bars; the forming minute never leaks.
Backfilled and live bars flow through the same commit path. The runner's `_on_completed_bar` gates
**pre-open and post-close bars out entirely** (they were burning lane latches), then runs the **C5
price-shock trigger**: a 1-min close-to-close move beyond `max(0.2%, 3× trailing-mean move)` forces
an immediate re-mark of every open position on that underlying (observability only - *when* we mark,
never *what* we do).

**The five lanes** (fresh instances each day; per-day dedup):

| Lane | Universe | Fires when | Target / horizon |
|---|---|---|---|
| **1 IndexTrend** | SPY/QQQ/IWM | on a 5-min boundary, price breaks the noise band *and* clears VWAP in-trend - **but stands down all day if the 14-day range percentile < 50** (dead-vol regime) | max(0.35×remaining range, 2×noise) / rest of day |
| **1b Last30** | SPY/QQQ/IWM (1DTE) | at **15:30** (bar 929) if the day's move exceeds 0.5×avg-daily-range - continuation | 15% of the move / 15:30→15:55 planned exit |
| **2 InPlayORB** | premarket hunt-list names | 1-min close breaks the 09:30–09:34 opening range, **RVOL≥5** (consolidated baseline) and **price≥$5** | 2× OR height / rest of day |
| **3 MacroReaction** | SPY only, event days | measures the CPI/NFP (09:45) or FOMC (14:00→14:15) reaction, then emits on the first non-blackout bar | the measured move / →15:55 |
| **4 PreEarningsStub** | - | **never** (a placeholder hook; makes the engine's event-straddle exit unreachable) | - |

**Signal → entry gates** (`_on_signal`, in order): stale (past its TTL) → after-hours/weekend →
event blackout → **merge** (a same-underlying-same-direction fire folds into the open position - new
lane tag, no second entry) → concurrency (max 3 open) → no-client. Survivors reach `_enter`.

**The selector** (`select_contract`) fetches the DTE 0–5 chain and runs **17 hard gates in order**
(crossed/no-quote/non-standard, DTE 0–5, no-0DTE-after-14:00, overnight-needs-DTE≥2, hold≤⅓-of-life
[0DTE-exempt], spread ≤10% and ≤$0.30 non-index, OI ≥1000/300, volume ≥100, **premium cap SKIPPED - 
`None`**, IV solvable, lotto-delta ban <0.35, delta 0.40–0.80, leverage λ 15–90), then an **EV
stage** (expected net return on the ask ≥10%, EV ≥2× round-trip spread, P(profit) ≥40%), then
**scores** on EV% with penalties for spread/richness and a **+5 bonus for the 0.55–0.75 delta
skew**, returning the top 3. It picks the contract *"we would buy"* - deep math unchanged from
FLOW §5. **Account size never enters** (premium cap removed; the affordability filter is a
deliberately-deferred future *final* filter).

**Entry recording** (`shadow.py`, the *only* side-effect surface - fsync'd append-only JSONL):
one `shadow_entry` row with **three fill ledgers** (WORST = buy-ask/sell-bid = the grading ledger;
BASE = mid ± 0.35×half-spread; OPTIMISTIC = mid), **always 1 contract**, the config-hash stamp
(`6c1dc2a4e1a7`), the full signal + pick + greeks + EV decomposition, the beaten `runner_up_snapshot`
(counterfactual lab input), and day-regime covariates. **No order is placed.**

---

## 4. How positions are watched and sold

*(Deep math - EV, P(regain), theta-share, the drift blend - is unchanged from FLOW §7–8; here is
what happens and in what order.)*

**Mark cadence** (`_mark_interval_s`): **300 s** for DTE≥1 in-session; **120 s** for a 0DTE
afternoon (after 14:00); **60 s** in the last 30 minutes before expiry and throughout the
after-hours late-close window - plus the C5 shock out-of-band mark. A persistently unusable book
journals `mark_no_quote`, and a streak of exactly 3 raises a one-shot `mark_no_quote_streak`.

**What each mark computes** (state, not the formulas): fresh bid/ask/mid; solved IV + its 45-minute
OLS trend (a failed solve *carries* the last good IV rather than collapsing it); the **live
trajectory** `mu_eff` (a blend of the entry thesis and the observed trailing-20-minute drift - the
weight is a registered calibration heuristic, **not** a derivation, per the 2026-07-10 relabel);
thesis validity; and the `peak_mid`/`peak_bid` high-waters (peak_bid only on real bids - the
realizable cost-basis water-mark).

**The RTH exit ladder** (`decide_exit`, pure, first-match-wins):

1. `a_zero_dte_clock` - 0DTE at/after 15:00 (15:30 if deep-ITM |delta|≥0.80)
2. `b_thesis_invalid` - the lane's thesis broke (sell winners too)
3. `c_premium_stop` - **INERT** (`stop_frac=None`; no fixed-price-point stop, by directive)
4. `d2_costbasis_backstop` - was realizably profitable (peak_bid > entry_ask) and that gain is now
   gone (bid ≤ entry_ask) - the winner-protection ratchet, on *observed costs only*
5. `e_event_straddle` - **unreachable** (lane 4 is a stub)
6. `f_post_print_no_edge` - ≥15 min after a macro print with no EV edge
7. `print_window_flat` - never hold long premium into the 10-min window before a print
8. `planned_exit_flat` - a lane's designed exit (1b/3 stamp 15:55)
9. `overnight_evidence_rule` - the 15:45 checkpoint (see below)
10. `g_theta_dominates` - decay has dominated for ≥2 cycles *and* P(target) < 0.30
11. `h_ev_hold_below_sell` - holding is worth less than selling now (the default-deny; entry price
    appears **nowhere** here)
12. `i_regain_low` - profit is present and the math says today's value won't return in the
    actionable window → take it while it's realizable
13. `j_hold` - everything passed; hold and log the full state

**Standing prohibition:** no rule fires at a premium threshold. The entry price is read in **exactly
three places** - the inert rule-(c) knob, the d2 backstop's `entry_ask`, and the i\* `profit_present`
*applicability* gate (which can only *prevent* selling a loser) - and never in any EV/probability
computation. *(FLOW §8 is already reconciled to "three"; the older "two" wording is gone.)*

**After-hours** (equity close passed, underlying frozen): a **restricted, S-free ladder** short-
circuits at the top - overnight-grant-hold → late-close-flat (close+10) → planned-exit → inert
rule-c → d2 backstop → hold. Only premium/cost-anchored rules and the hard clock survive; `peak_bid`
keeps updating on live after-hours NBBO (index options trade to close+15).

**Overnight policy:** at 15:45 a non-0DTE position is **force-sold** unless it qualifies for an
overnight grant (DTE≥3 **and** |delta|≥0.70 **and** a named next-morning catalyst **and** not
Friday). On a forced sell it records `variant_would_hold = ev_hold > ev_sell` - the owner's unrestricted
arm - which the nightly paired replay grades as a divergence.

**Force-flats** (runner-side, marked `forced=True`): non-index positions open past the equity close
without a grant are flattened (`post_close_forced_flat`); if the NBBO dies before flattening, a
degradation chain falls back fresh-quote → last-mark → entry-NBBO and journals it.

---

## 5. How we know it's working, and the operational skeleton

### 5.1 Grading (`grade_options_shadow.py`, nightly)

Grades on the **WORST fill ledger** (buy-ask/sell-bid). **Falsification gates run first:** malformed
exit rows (missing ledger fields or a rule id) are excluded and reported loudly; rows that break the
`worst ≤ base ≤ optimistic` identity are **quarantined** out of lane stats; a cost-share metric
proves the ledger actually *sees* the spread tax. A lane **PASSES** only at **N≥25 AND WORST mean
net > 0 AND gross > 0 AND profit-factor ≥ 1.2 AND top-day share < 0.5**; verdicts are
PASS / ACCUMULATING (N<25) / FAILING. Go-live is *discussed* at **N=50** (the ledger says 50–100). A
non-binding N=10 "interim read" exists only in the `/eodreport` layer, not in the grader script.

### 5.2 Schedulers (all Central time)

| Task | Time | Does | State |
|---|---|---|---|
| ATLAS-Premarket | 05:15 | crew fan-out + day briefing | Ready |
| ATLAS-LiveDay | 07:30 | starts the shadow day (via a forwarding shim) | Ready |
| ATLAS-IVSnapshot | 14:45 | ATM-IV archive snapshot | Ready |
| ATLAS-OvernightLab | 15:25 | paired-replay lab + local-LLM stub | **Disabled** (pivot weekend) |
| **ATLAS-CacheRefresh** | **15:35** | **nightly IEX cache append (new 2026-07-10)** | **Ready** |
| ATLAS-AuthKeepalive | Sun 18:00 | keeps the grading-side RH token warm | Ready |

> ⚠ Re-running `register_mesh_tasks.ps1` re-registers **every** task **enabled** - it would silently
> re-enable OvernightLab (a CAUTION now sits in the script header).

### 5.3 The day launcher (`launch_options_day.ps1`)

Tradier preflight **warns-and-launches** (a bad token pages ntfy at high priority but the stack
still runs heartbeat-only - an observable degraded day beats a silent lost one). It starts the
shadow, the news tap, the monitoring hub (`:8770`), and `alert_watch --options-only`; gives the
shadow **3 crash-restarts**; honors `runtime/STOP_DAY.flag`; and needs **no Robinhood, Alpaca, or
llama-swap**. (The scheduled `ATLAS-LiveDay` still targets the equity-named `launch_live_day.ps1`,
now a thin forwarding shim to the options launcher - a cosmetic pending cleanup, repointing needs an
admin shell.)

### 5.4 Alerting (`alert_watch.py --options-only`)

All equity-era watches are off; two options watches remain, on **separate latches**:
- **Process staleness** - heartbeat missing/older than 180 s in market hours → "OFFLINE (evidence
  gap)".
- **Data-plane zombie** (new 2026-07-10) - the process is alive and heartbeating but the *feed* is
  dead: `client_present == false`, or in-session ticks stale > **120 s** (an OPS constant, bounded
  by the heartbeat's own `session_close_min` so the after-hours freeze reads healthy). The recovery
  notice only claims "quotes flowing again" when a genuinely fresh tick proves it; otherwise the
  latch clears silently. This closes the exact hole where a mid-day token death left open positions
  *unmanaged* behind a fresh-looking heartbeat. (The `alerts.json` UTF-8 BOM that had been silently
  disabling the pager was fixed and is now CI-guarded.)

The shadow's **schema-2 heartbeat** carries the fields this watch reads: `client_present`,
`last_tick_epoch`, `last_bar_epoch`, `last_mark_epoch` (observability only, never a decision input).

### 5.5 Discipline & hard invariants

- **Registration:** every behavior change is a pre-registered row in
  `runtime/backtest_out/sweep_ledger.jsonl` (75 rows: 31 equity-era + 44 `opts-*`). The live config
  hash `6c1dc2a4e1a7` is pinned as a machine-greppable field, and
  `tests/test_provenance_registry.py` now **fails CI** if any `ExitParams`/`SelectorParams`/runner
  constant lacks a registry entry + ledger row, or if the live hash isn't pinned. Every constant is
  owner-verbatim, DERIVED, POLICY (a dated directive), or CALIBRATION (with a sweep id).
- **Zero order path** - import-tested (§2.3).
- **Single-writer, append-only, fsync'd ledgers**; atomic heartbeat replaces.
- **Fail-open data / fail-closed compute** - a dead feed produces *no* entries and *no* marks (which
  is exactly why the data-plane pager exists).
- **Machine-authored inputs are DATA** - crew and news output shape behavior only through validated,
  bounded fields.

---

## 6. What changes when it goes live

**Going live is a build, not a config flip.** Today there is *no code that could place an option
order* anywhere in the platform's import closure.

**What makes it a shadow now:**
- No reachable order path (structurally pinned by the import tripwire).
- **Account-blind:** value-based selection, **1 contract always**, premium cap removed, and **no
  buying-power/account input exists** in `atlas/options/` or the runner.

**What would have to be built:**
1. **An options order path + submit seam.** The equity era had the pattern - a
   journal-until-`submit_fn`-injected "two-key" executor - but it (and the whole
   `broker_adapter`/`order_lifecycle`/`guardian`/`robinhood_adapter` stack) is **archived to
   `attic/` and equity-shaped**. The options shadow uses none of it and has **no submit seam at
   all**; an options-order equivalent would be built and injected from scratch.
2. **A real order channel.** The kept `atlas/execution/` is a stripped shell - a stdlib rate gate
   and nothing else. The broker MCP client that used to sit beside it (a data-token refresher for
   grading-side truth validation, never an order caller) is excluded from this public copy, so no
   broker transport of any kind ships here.
3. **The affordability filter, re-enabled as a FINAL gate.** By directive, account size returns
   *only* as a last "can we afford it" filter applied *after* value selection - set
   `premium_max_usd` to a number to arm it. (The dormant `options_live_min_equity: $2000` config is
   **equity-era scaffolding wired to the archived app**, not a live gate on the options shadow - 
   trust the code, not that config.)
4. **Clearing the statistical bar first.** No live discussion until a lane clears the grader's
   per-lane **PASS bar (N≥25, profitable on the WORST ledger, PF≥1.2, not concentrated in a few
   days)**, with **go-live talk at N=50**, under the registration discipline.

In short: the decision engine is designed to be *identical* live - the same lanes, selector, and
exit ladder, still account-blind for decision quality - with a newly-built order path bolted on
behind a re-enabled affordability filter, and only after the shadow's own ledgers prove a lane
edge exists.

---

## 7. Known gaps & doc flags (from the 2026-07-10 sweep)

- **FRED CPI/NFP is fallback-table-only** in the current config (no `fred:` key) - dates are the
  hardcoded BLS-2026 tables, not live FRED.
- **VIX/VXN regime** referenced in `iv_archive.py` docstrings **does not exist** in code (`vix` is
  `None` everywhere).
- **Lane 4 / event-straddle exit** is a permanent stub → the engine's rule (e) is unreachable.
- **The selector's `event_blackout` gate** is dead in wiring (blackouts are enforced upstream at
  the signal stage).
- **Cosmetic:** `ATLAS-LiveDay` still routes through the equity-named launcher shim; an in-code
  `market_close_local` default comment reads `15:05` while the effective value (from `alerts.json`)
  is `15:20`. Neither is a behavior bug.

---

*Companion documents: `docs/OPTIONS_SYSTEM_FLOW.md` (exhaustive line-by-line audit + all math)
and the sweep ledger `runtime/backtest_out/sweep_ledger.jsonl` (every registered behavior
change). `docs/OWNER_RULES.md` - formerly cited here as the canonical exit-rule authority - was
**retracted and deleted 2026-07-16 by owner directive**; see `docs/OWNER_RULES_RETRACTED.md`.*
