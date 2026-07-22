# 10 - Edge sources: catalyst pipeline, symbol-state defense, context feeds (2026-07-04)

Phase-4 integration of the 2026-07-04 edge-source research (memory
`edge-source-research-2026-07-04`). Governing rule, unchanged from the pipeline's birth:
**events decide WHEN we look; gates + models decide WHETHER we trade.** No code path exists from
event magnitude to quality or rank - magnitude orders feed ingest only.

## Source classes (enforced in code, not just config)

| Class | Sources | May watch/eval? | Purpose |
|---|---|---|---|
| Normal | `edgar` (8-K positive items), `insider` (Form 4 buys), `edgar13d`, `sam_gov`, `defense_gov`, `sentinel` | only if listed in `catalysts.watch.sources` AND mode ≥ watch | context + (post-validation) tape-confirmation watches |
| Watch-capped | `borrow` | watch at most - `_WATCH_CAPPED_SOURCES` blocks eval/inject forever | shorting-premium evidence: a fee spike may only pre-arm a re-look |
| Defensive | `fda`, `dilution`, `edgar_neg` | NEVER (`_DEFENSIVE_SOURCES`) | risk FLAGS: entry blackout + `force_eod_flat` |
| Context-only | `gnw`, `apewisdom` | NEVER (`_CONTEXT_ONLY_SOURCES`) | pure LLM context (+ optional crowding ride-caution) |

### The watch.sources allowlist (the ladder's missing rung)

`catalysts.mode` is global, so promoting it for one validated source would arm every normal
source. `catalysts.watch.sources` (default `[]`) is a per-source allowlist checked in BOTH
`register_watches` and `eligible_for_eval`: **mode alone arms nothing.** The 8-K 1.01 trigger is
REFUTED at n=752 (2026-07-03) - `edgar` stays out permanently unless a narrowed cohort validates.
`insider` may be added ONLY by the user after `scripts/validate_form4_catalyst.py` PASSES + 5
clean shadow sessions.

## Symbol-state defense layer (`atlas/collect/symbol_state.py`)

Operational state, not events: Nasdaq cross-exchange trading-halt RSS (parsed stdlib, ≤1
poll/cycle), SEC trading-suspension RSS (declared User-Agent REQUIRED - 403 without it; names
resolve via EntityResolver; entries expire by their release date, ~14 calendar days), and
SELF-COMPUTED SSR (`intraday low <= 0.90 x prior close`, from the Tradier candidates+held batch - 
the SSR *file* is archival-proven to regenerate only ~4:15AM/~4:30PM ET and is banned as an
intraday source).

Consumers: (1) scan-context veto (`halted`/`sec_suspended` drop before any trend math; `ssr_active`
is context only - SSR restricts shorts, we only buy); (2) pre-submit ORDER GUARD at step 11a'
(reason `symbol_halted`/`sec_suspended`); (3) LLM features + hub card. **Fail-open contract:**
"halted" is asserted only on affirmatively-fresh data (≤ `max_state_age_seconds`, default 180s) - 
missing symbol / stale snapshot / dead feed ⇒ no reasons ⇒ trading proceeds. Suspensions are
durable (no wall-age bound). Halts deliberately go stale across a restart.

## Overnight-ride protection (defensive flags)

`CatalystPipeline.risk_flags(sym)` → `binary_event_days` (min over live FDA events),
`dilution_risk`, `bankruptcy_risk`, `delisting_risk`. `risk_reasons(sym)` applies
`catalysts.fda.blackout_days` and feeds: the risk-engine blackout (BlackoutContext fields →
gate 8 reasons `binary_event_blackout`/`dilution_risk`/`bankruptcy_risk`/`delisting_risk`), the
scan-context early drop (saves LLM throughput), and - via `no_ride_reasons(sym)`, which adds
`crowded_no_ride` when `apewisdom.feeds_no_ride` is armed - the per-lot **`force_eod_flat`** flag
in `synthetic_stops.json`. The Guardian beheads a flagged lot at EOD regardless of P&L
(short-circuits the losers-only winner exemption; reason stays `eod_flat`). Flags recompute from
LIVE events at every publish: a TTL-expired or dead feed clears them (fails open to winners-ride).

- **FDA feed** (`fda`): clinicaltrials.gov v2 Phase-3 primary-completion dates + Federal Register
  AdComm notices. **HONEST COVERAGE: PDUFA action dates exist in NO free API** - the blackout is
  best-effort (AdComm + trial dates + recalls), not a guarantee. Do NOT buy BPIQ.
- **Dilution feed** (`dilution`): EDGAR EFTS forms S-3 / 424B5 / EFFECT / 25 / 15, same-day.
  Thesis unverified-as-alpha but defensive → ships enabled.
- **Negative 8-K** (`edgar_neg`): items 1.03 (bankruptcy) + 3.01 (delisting notice) split from the
  positive stream by `EdgarMaterialEventsFeed`.

## Form 4 insider channel (`insider`) - the one new alpha-bearing sector

EDGAR getcurrent atom → per-filing ownershipDocument XML (`parse_form4_xml`, shared with the
validator) → officer/director open-market P-purchases ≥ `min_value_usd` ($20k). Cluster (≥3
distinct insiders / 15d rolling window, pipeline-persisted) raises MAGNITUDE only. Ships
context_only. Promotion ladder: `scripts/validate_form4_catalyst.py` (EDGAR daily-index cohort vs
matched above-trend baseline, 3.5×ATR bracket, price-tiered costs, n≥100 + CI-low>0 + 50%-haircut
edge >0.02R) → PASS → 5 clean shadow sessions → **USER adds `insider` to watch.sources**. The
script never edits config. Evidence: Oenschläger-Möllenhoff FRL 2025 (decayed-positive, small-cap
concentrated; note the general "edges survive in illiquid names" claim was refuted 1-2 - the
thesis rests on this one paper, hence the own-cohort gate).

## Context extras (M5)

- **GlobeNewswire PRs** (`gnw`): ticker-tagged in-feed (`Exchange:TICKER` category), category
  whitelist + law-firm-spam blacklist, 20-item window. GNW only - PRNewswire ToS bans bots.
- **Options flow** (top-level `options_flow`): self-computed from Tradier chains at selection time
  (≤ max_candidates × 2 req/cycle): `put_call_vol_ratio`, `call_vol_vs_prior_oi`,
  `options_activity_note`. OI updates only overnight - live volume vs prior-day OI IS the
  opening-activity heuristic. Features only; no gate.
- **FINRA short context** (top-level `short_context`, `atlas/collect/short_context.py`):
  once-daily CNMS daily short-volume file (walk-back fail-open), features `short_vol_ratio` +
  cross-sectional `short_vol_percentile`. days_to_cover NOT included - FINRA SI download requires
  api.finra.org registration (no keyless channel). Predictive value refuted (WYZ JFE 2020) - 
  context only.
- **ApeWisdom crowding** (`apewisdom`): rank ≤ 10 ⇒ `wsb_crowded` (herding-peak caution,
  ~-2.3%/20d after haircut). `feeds_no_ride: false` by default; true joins `force_eod_flat`.
  Never a look-trigger (WSB long signal dead post-GME).
- **Federal Register public-inspection**: SKIPPED this phase (plan's lowest-priority item,
  time-boxed out; the FedReg NOTICE leg inside the FDA feed covers the AdComm channel).

## Do-NOT-build list (evidence in memory `edge-source-research-2026-07-04`)

Halt-reopening entries (spreads 2x+, vol ~9x at resume); index-add trades (effect dead,
announcements land after-hours); crypto→equity lead-lag (inverted - ETFs lead); BJZZ subpenny
retail-flow proxy (broken by half-penny ticks); PRNewswire polling (ToS); paid vendors
(BPIQ/sec-api.io/Form4API dependence); congressional-trade feeds (45-day lag); the SSR *file*
intraday; watch-promotion of the 8-K 1.01 govcon trigger (refuted n=752).

## Failure modes

Every feed is breaker-wrapped and fail-open: a dead/bot-walled/stale source can veto nothing,
block nothing, and crash nothing - halts age out (≤180s), suspensions expire by release date,
defensive flags vanish with their events' TTLs, context features are simply absent. The order
guard and the blackout gate act ONLY on affirmatively-fresh, affirmatively-parsed data.
