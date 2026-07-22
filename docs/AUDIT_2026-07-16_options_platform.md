# ATLAS OPTIONS PLATFORM - COMPREHENSIVE AUDIT (2026-07-16)

**Commissioned by the owner 2026-07-16 (pre-dawn), delivered same day.** Method: 14 subsystem
math/stat auditors + 3 live-machine probes, adversarial verification (2 independent refuters per
critical/high finding; ~70 refuter runs completed across two passes), 6 end-to-end coherency seam
judges, 4 external web researchers, 3-perspective design panel. Full evidence:
`docs/audit_2026-07-16/` (digests + raw JSON). Verification legend: **CONFIRMED** = upheld by
independent refuters with executable repros; **REFUTED** = killed by refuters (listed so nobody
re-litigates); **PLAUSIBLE** = numeric repro on record, adversarial pass incomplete (usage limits).

Standing context: `docs/OWNER_RULES.md` was **retracted and deleted 2026-07-16** by owner directive
(`docs/OWNER_RULES_RETRACTED.md`). Every "owner-verbatim" behavior was judged on merits here.
The owner's goal: *an autonomous options trader that plays with the edge the house gives it,
making informed decisions, in a slightly casino posture to maximize profit taking.*

---

## 0. Run-safety for the 2026-07-16 session - GREEN (proven by the run itself)

- The "no money in the portfolio" fear is **structurally impossible as a stopper**: the options
  path has **zero account reads** (grep-verified across runner/launcher/lanes/selector/engine/feed;
  `tradier_data.py` touches only `/v1/markets/*`). The only "money" surfaces are the watch-hub's
  stale **equity-era $0 pills** (display-only, fed by a log nothing writes anymore) and the Sunday
  auth-keepalive printout (print-only; not part of the public copy). *The only path by which "$0" ends a day is a human panicking
  at the cosmetic panel - don't.*
- The day launched clean at 07:30:01 CT: Tradier preflight GO, fresh hunt list
  (`session_date 2026-07-16`, 15 candidates), 5 lanes armed, cohort `6c1dc2a4e1a7`. Two entries by
  mid-morning (see §2). Probes verified: scheduler correct (OptionsDay Ready / LiveDay+AutoEOD
  Disabled), calendar says trading day, token authenticates, clocks sane, disk fine, ntfy pager
  parseable (no BOM).
- Residual operational risks (all degradations, not stoppers): premarket crew at 1–2/5 providers
  (groq carried 07-15; groq+1 carried 07-16); interactive-logon-only scheduled tasks (a reboot
  without login kills the day silently); ATLAS-Rehearsal is a still-enabled tombstone that bypasses
  the session guard if run manually (disable when convenient); GDELT 429-blocked (fail-open).

---

## 1. The verdict in one paragraph

The machine is operationally excellent - clean launches, append-only ledgers, fail-open feeds,
registration discipline - but the **trading logic manufactures its own edge at entry, destroys its
own samples at exit, and grades the wreckage with a test that can't tell luck from skill.** The
selector's claimed +10–53% EV is produced by a hardcoded coin-flip prior (`p_thesis=0.5`) applied
to a drift that reaches the lane's target *by construction*; the market-implied weight on the one
fully-graded trade was **−0.004** - i.e., the market says the trade was worth exactly its
transaction costs, and 100% of the claimed edge was assumption. At exit, a 20-minute two-point
drift estimate whose sampling noise is ~14 *annualized* units drives EV rules with a ~0.016
threshold - a **noise clock** that force-sells within ~30–50 minutes under pure noise (Monte Carlo
through the real `decide_exit`; 4/4 refuters upheld) - and the zero-hysteresis thesis-invalidation
band cuts marginal entries in minutes (2 of 3 lifetime trades died this way, including today's QQQ
put at −$97 while the engine's own state read `p_regain=0.913`). The grader then needs N≥25 per
lane at ~0.14 fires/day (months–years) using a PASS bar that false-passes a zero-edge lane ~33%
of the time (~69% with nightly peeking, ~87% familywise). None of the three layers measures the
same quantity as the next. The good news: the seams are exactly identifiable, the fixes are mostly
small and registered-tweak-sized, ~5,000 lines of stage-mismatched auxiliary stack can be parked
or deleted without loss, and the three independent designs converged on the same repair plan (§6).

---

## 2. Empirical record (all decisions to date)

| Trade | Lane | Entry | Exit | Net (WORST) | What it proves |
|---|---|---|---|---|---|
| 07-13 IWM 293P | index_trend | 13:40 ET, band cleared by **1.07bp**, claimed ev **+53.31%**, `mu_thesis −8.22/yr` | +306s, `b_thesis_invalid` on a 25¢ reclaim; engine state said HOLD (ev_hold>ev_sell, p_regain 0.775) | **−$16** | manufactured EV; hair-trigger (b); truth-validated correct *that day* (put expired worthless) |
| 07-16 QQQ 712P | index_trend | ~09:4x ET, ev +21.52% | **15 min later**, `b_thesis_invalid`; `p_regain=0.913` at exit | **−$97** | the same failure pattern, live, during this audit |
| 07-16 NVDA 210P | inplay_orb | 09:36 ET, spread 3.87%, RVOL 9.6 | (open at time of writing) | - | lane 2 CAN pick on mega-cap books (refutes SELECTOR-7) |

Funnel telemetry (6 sessions): ~3 lane fires/day → 33% lost pre-selector (stale/stand-down) →
selector kills ~82% of surviving signals; 1,487 same-direction contract rows died first-fail at
OI 32% / no_quote 25% / spread 19% / third-of-life 11%; **0.4% of rows ever reached the EV stage**.
Plus: 21 `lane2_rvol_baseline_missing` stand-downs, 39 `backfill_gave_up`, 36 `signal_expired`.

---

## 3. Part 1 - confirmed defects (mathematical/statistical), ranked

### Tier A - wrong decisions being made now (CONFIRMED)

1. **TRAJECTORY-1 (critical, 4/4 upheld, blocks-goal): the exit ladder is a noise clock.**
   `mu_hat = r_K/T_K` over 20 one-minute closes has SE `= iv/√T_K ≈ 14` annualized (iv 0.20);
   rule (h) flips at `mu_eff ≈ +0.016`. Per-mark P(false SELL)=0.34 under zero drift; median
   time-to-forced-sale ~30 min at 300s marks. "Maximize profit taking" is mathematically
   impossible: no winner can be held. *Fix (one changeset with the prior fix, §6 Wave 2):
   variance-scaled blend weight `w·τ²/(τ²+SE²)`, robust endpoints, time-based persistence.*
2. **SELECTOR-3 / PROBABILITY-MEASURE-1 (critical, upheld + independently reproduced): the EV
   stage prices ambition, not edge.** `mu_thesis = ln(1+target)/horizon` attains the target by
   construction; with `p_thesis=0.5` hardcoded, `ev_pct` is ~linear in target size while true
   attainability collapses (same contract: target −0.20% → ev 6.5% [fails floor]; −1.16% → 53.3%;
   −3.0% → 176%). Market-implied mixture weight on the live trade: **−0.004**. The selector's own
   `p_touch_target` (0.086) is computed, logged, and gated on **nothing**.
3. **MATH-CORE-1 (high, 2/2 upheld): p_regain double-decays the 0DTE clock.** `math.py:299`
   feeds the horizon-END time into `zero_dte_effective_T`, whose own derivation requires the
   CURRENT time - model decay × empirical decay charged for the same interval (13:00 example:
   coded 41.9 min vs intended 125.8; p_regain 0.53 vs 0.82). Every historical p_regain is biased
   toward selling winners. One-line fix + re-sweep `p_regain_min`.
4. **LANES-4 (high, 3/4 upheld): last30 is a designed-in no-pick generator** - its 15%-of-move
   target cannot arithmetically clear the selector's `ev_pct≥10` floor except on ~2σ days
   (6/6 lifetime EV-stage deaths). Park or re-derive the target.
5. **LANES-6 (high, 3/4 upheld): no target-feasibility check.** Late-session fires request
   ~10–13σ moves (15:50 fire: `mu_thesis≈116/yr`), which the mixture happily prices at 50%
   certainty and which then poison the exit prior. Fix: `|ln(1+target)| ≤ k·iv·√horizon` (k≈2).
6. **SHADOW-LEDGER-2 (high, 4/4 upheld): evidence-corruption path.** An unreadable exits file at
   day-roll (Windows AV/backup lock - reproduced with a real share-mode-0 lock) resurrects every
   unexpired historical position; re-exits double-count; the grader **never dedupes by
   position_id**. Fail-closed the rebuild; dedupe loudly.
7. **SELECTOR-6 (high, upheld + measured live): OI/volume floors use mismatched clocks.**
   Prior-day OI + full-day volume judged at 09:35. Measured this morning: QQQ's most-ATM 0DTE
   strike had **OI=0 with 6,255 contracts traded** (fresh strike after a gap) - hard-vetoed; ITM
   strikes the delta gate targets routinely fail both. Convert to OR-gates with time-scaled volume.
8. **IV-ARCHIVE-2 (high, 2/2 upheld): `iv_rank` is a provable no-op** - a per-call scalar
   subtracted identically from every candidate before a within-call sort. Delete the penalty
   (decision-neutral, cohort-safe); keep the snapshotter with a heartbeat.
9. **GRADER-1/EVIDENCE-MACHINE-1 (high, MC-confirmed twice): the PASS bar is not a test.**
   PF≥1.2 ≡ t=0.36. Zero-edge lane false-PASSes: ~33% single-look at N=25, ~69% under nightly
   all-history re-grading (unbounded peeking), ~87% familywise across 5 lanes. One $2–3k QQQ
   contract carries ~94% of a lane's dollar variance post-premium-cap-removal.
10. **REPLAY-LAB-1/2 (high, empirically proven): the validation lab cannot validate.** Quote
    capture stops at the live exit (no hold-longer variant can ever be credited) and stored
    `thesis_valid` + rule-(b)-first ordering make all 5 registered variants **byte-identical on
    100% of recorded history**. This is the mandatory stage-4 toll gate - fix it first.

### Tier B - plausible, repro on record, verification incomplete

- **EXIT-ENGINE-3**: the d2 cost-basis backstop arms on ~0.17σ of spread noise (P≈0.99/day on a
  martingale) and, sitting above (g)/(h)/(i*), scratches winners at ~$0 - the exact opposite skew
  of both PF≥1.2 and the casino posture. (One vote pending; treat as design question for v3.)
- **RUNNER-1/TIMESCALE-STACK-4** (mechanism confirmed by two independent agents): premarket ticks
  from 08:30 permanently contaminate session VWAP/HOD and the mu window (prevclose-echo bars
  included) - both entry admission and the kill switch consume it. RTH-gate the bar builder.
- **RUNNER-3**: overnight grantees are thesis-judged next morning by TODAY's fresh lane objects in
  TODAY's frame (`move_from_open≈0` ⇒ inside band ⇒ near-certain 09:35 cut), structurally
  defeating the overnight grant.
- **RUNNER-4/PREMARKET-CREW-1**: no `session_date` check on `hunt_list.json` - a failed 05:15
  premarket silently arms lane 2 with yesterday's names (observed 07-11).
- **PREMARKET-CREW-2/3/5/8**: crew can exceed its own 300s kill window (hunt list silently
  stale); single-model days rank candidates **alphabetically** (07-15 artifact literally
  BLK<BNY<CTAS<ELV<FHN<JNJ<MS<MTB<PNC); yesterday's after-close reporters - the richest gap
  cohort - are structurally absent; the deterministic gap-scan fallback is dead code
  (`lane2_scan_symbols=[]`), making 5 flaky free LLMs the sole lane-2 universe source.
- **TRADIER-FEED-1**: retries cover only HTTP 429 - one transient timeout kills a whole signal
  (~7 days of funnel output at current rates).
- **EVENTS-CALENDAR-1**: all macro/holiday tables are 2026-only with no rollover guard - on
  2027-01-01 the entire macro-protection layer silently disarms (repro: `upcoming_events(2027)`
  = `[]`; `is_trading_day(2027-01-01)=True`).
- **MATH-CORE-4/5/6**: theta_share ignores the gamma earn-back (labels the most convex positions
  "decay-dominated"); selector still applies the 0DTE theta multiplier the exit engine removed as
  double-counting AND omits the 365/252 rescale (two theta conventions in one ledger); vendor-IV
  fallback plugs calendar-annualized IV into trading-time math (±20–31% vol error on that path).

### Refuted (do not re-litigate; full refutations in `new_votes.md`)

- **SELECTOR-7** ("lane-2 spread gates unpassable") - killed by today's live NVDA pick.
- **SELECTOR-1** ("λ×δ jointly EMPTY") - narrowed, not empty: puts pass at DTE-2; but the flat
  λ≤90 IS a de-facto 0-1 DTE index ATM ban (measured ATM λ 107–271), so per-DTE caps remain right.
- **TRAJECTORY-3/4** (endpoint sensitivity / cadence compounding as stated) - cosmetic as framed;
  the better-founded cadence result is TIMESCALE-STACK-2's: count-debounce is *not*
  cadence-invariant, time-based persistence is.
- **LANES-1/EXIT-ENGINE-1 as a *defect*** - mechanics fully confirmed (92% eventual cut, median
  10-min hold, 34–41% cut at first reval in 500-session replays), **but** paired replays of the
  proposed hysteresis fixes did **not** improve P&L on history, and the one graded cut was
  truth-validated correct. Verdict: the *entry* criterion (band-edge admission) and the *exit*
  asymmetry are the disease; hysteresis alone is not the cure. Handle via §6 Wave 2 + band
  recalibration sweep, judged by the repaired lab.
- **LANES-2** (latch burns at emission) - 4/4 refuted as a starvation cause; retained only as a
  throughput multiplier idea (latch-at-entry) to be validated.
- **MATH-CORE-2** (p_regain "understates 2–3×") - refuters showed the benchmark was degenerate.
- **IV-ARCHIVE-1** (iv_rank warm-up as an "edge leak") - inert either way (see IV-ARCHIVE-2).
- **LANES-3** (range-percentile gate) - genuinely contested 2U/2R across passes: the ~43–46%
  stand-down arithmetic is exact; whether rank-vs-level detects "regime" is disputed. Decide via
  the band/gate sweep, not argument.

---

## 4. Part 2 - coherency verdicts (the 105-agent-stack question)

1. **Probability measure: five unreconciled probabilities for the same event** on one position
   (market 0.042 / logged-p_touch 0.086 / entry 0.5 / exit ~1.0 via life-extrapolated
   `p_target_thesis` / 0.0 on the (b) flip). Entry prices the thesis at 50%, exit holds at 100%
   (`mu_prior = mu_thesis`, `p_thesis` never read by the engine) - and that unregistered doubling
   is currently the only brake on the noise clock. **The pieces do not share a worldview.**
2. **Funnel vs evidence engine:** morning index signals have exactly ONE marginal expiration to
   shop (`max_chain_expirations=3` truncates daily-expiry indexes to DTE 0-2; 0DTE λ-infeasible
   below ~16% IV or clock-banned; ⅓-of-life bans DTE-1 before 12:45) - the "0DTE carve-out" has
   gated zero rows since birth. The evidence machine needs N≥25/lane; at the observed rate the
   one-year minimum detectable edge (~17% of premium) **exceeds the selector's own 10% design
   target** - the machine cannot verify its own spec on any horizon.
3. **Cost and edge:** the strategy class survives WORST fills only on index/mega-cap penny books
   (0.9–2.1% round-trip) held to horizon. The configured lane-2 catalyst universe quotes
   **13.9–108% of premium** round-trip - 5–25× any plausible edge; unpassable by construction.
   The realized behavior (5-min insta-cuts) sits at the worst point of the cost curve: full
   spread paid over a near-zero drift window (~0.17σ per 5-min hold needed just to break even).
   Score to date: selector claimed +$184 EV on 3 entries; realized −$113 WORST (2 graded).
4. **Timescales:** entry evidence = committed 5-min closes; kill evidence = raw 10-second ticks
   against a √t-growing band with mixed clocks (tick-fresh S, bar-stale svwap). Time-based
   persistence (~one non-overlapping mu window) makes exits cadence-invariant; count-based does
   not. Premarket contamination and no staleness bound on the evidence clock (a halted tape reads
   as "thesis fully intact" - h can never fire) complete the picture.
5. **Dead layers (~5,000 lines influencing zero decisions):** journal tally across all sessions - 
   0 C5/news-shock reval triggers, 0 halt-gate rejections, 9/13 stage-2 covariates structurally
   null on the only lane that ever entered, `day_briefing.json` has zero consumers, the replay lab
   zero discriminating power, watch_hub renders 7 archived equity tabs while the options view is
   computed server-side and **never rendered**. Verdicts: DELETE iv_rank penalty + hv20 term +
   C5/news-shock accel blocks + equity hub tabs + `prob_itm` + briefing fat; PARK news/catmem
   covariate stack, mention_tap, last30 (each with a written re-arm condition per ladder rule 3);
   FIX-CHEAPLY replay lab, hub options tab, symbol-state poller (90s cadence + exit-side
   `halted_while_held` journal); KEEP the WORST ledger, the lanes→selector→ladder shape, halt
   entry gate, news_tap collection. **Standing rule adopted: no new stage-2+ instrumentation
   while the funnel is below ~2 entries/week.**
6. **Evidence machine:** replace mean>0 + PF≥1.2 with an **anytime-valid betting e-process on
   %-of-premium WORST returns** (bounded below by −1), pooled ALL row (deduped, merges once) as
   the primary verdict, per-lane wealth for allocation; nightly re-grading becomes legitimately
   peek-proof (Ville). Graduated go-live: wealth ≥5 unlocks a tuition-capped 1-lot pilot (which
   also measures real fills, settling WORST-vs-BASE empirically); ≥20 unlocks sized live. Publish
   the honest MDE table nightly. Variants promoted from replay start fresh wealth (no
   selection-then-confirmation).

---

## 5. External research anchors (full citations in `part2_digest.md`)

- **0DTE decay:** the hardcoded sigmoid is wrong in both directions - leaves ~66% of morning time
  value "alive" at the closing bell (truth: 0), understates post-14:00 0DTE decay 3–6×, overstates
  1-2 DTE afternoon decay ~5–7×. Structural fix: a variance-clock hazard
  `rate = η(t)/(2·RemainingVariance(t,expiry))` with a U-shaped intraday profile (Todorov-Zhang);
  refit from ATLAS's own stored quote paths. Also: undifferentiated long-premium 0DTE is
  negative-EV for takers (~60% of retail losses are spread/fees - Beckmeyer et al.), which makes
  the liquidity gates the platform's most defensible layer.
- **Lane theses vs literature:** `p_thesis=0.5` is defensible **only** for ~0.3×-daily-range
  targets with EOD horizons on RVOL-confirmed breaks; measured win rates for published
  cost-surviving intraday systems are 17–43% with 2:1+ payoffs (+0.02R to +0.18R/trade).
  Stocks-in-play ORB expectancy flips sign exactly at RVOL=100% (keep the RVOL≥5 gate hard).
  Last-30-min index momentum is peer-reviewed (54.4% hit, gamma-flow mechanism, 3-4× stronger on
  macro days) - the lane direction is right; its target arithmetic is what's broken. **Post-FOMC
  intraday continuation is NOT supported** (pre-2015 drift died; the modern pattern is 2:30pm
  presser *reversal*): MacroReactionLane's FOMC arm bets against the published record - park or
  re-found as a reversal/fade lane. No unconditional intraday drift exists (all of SPY's premium
  is overnight).
- **Microstructure (measured live this morning + literature):** index ATM 0-5 DTE spreads sit at
  the $0.01 tick floor by 09:35 (0.5–1.5% of premium); ATM λ measured 107–271 (the λ≤90 cap is a
  de-facto 0-1 DTE index ban); OI gate is wrong-shaped (fresh ATM strikes: OI=0, volume 6k);
  add a ~$0.50 premium floor (below it the minimum tick alone is 3-6%); WORST (ask/bid) is a
  realistic bound for Robinhood-routed 1-lots (worst-PI venue in the 7,000-order broker study;
  effective spreads average ~25% inside quoted - BASE≈mid±0.35·half-spread is near the measured
  effective-fill line).
- **Small-N statistics:** N=25 can only certify edges ≥39% (t=1.96) to ≥60% (Harvey-Liu t≥3) of
  premium; the hypothesized 5–20% band needs ~155–2,500 trades. PF folklore is noise below ~50
  trades (zero-edge 95th percentile at N=25 ≈ **2.2**). Sequential designs save ~38% at best - 
  no test turns 25 trades into evidence; the honest answers are (a) raise throughput, (b) pool,
  (c) anytime-valid monitoring, (d) a skeptical-prior posterior as the headline number
  (+10% mean at N=25 ⇒ only ~59% P(edge>0)).

---

## 6. The judged synthesis (design panel → one plan)

Three designs were produced: **Repair-in-Place** (minimal registered diffs), **ONE-MEASURE**
(single calibrated touch-probability object end-to-end), **PIT BOSS** (casino-first: priced
tables only, calibrated odds vs the market's price, premium-as-the-only-stop, systematic
right-tail harvest, graduated bankroll go-live). My judgment (the panel judge died on a usage
limit; scores mine, criteria: coherence / evidence-capability / owner-goal fidelity / solo-operator
realism / self-deception risk):

- **Repair-in-Place ~82** - best sequencing and realism; alone it patches the manufactured-EV
  root with a gate rather than fixing the measure.
- **ONE-MEASURE ~85** - the correct destination for the probabilistic core; honest about the
  possibility that calibration reveals *no* lane clears the market's price (that is discovery,
  not failure); heaviest single cohort.
- **PIT BOSS ~80** - the truest reading of the owner's goal and the best go-live design
  (graduated, bounded-tuition); its exit-harvest ladder is the least validated piece and must
  enter through replay columns, not straight to live.

**The plan = Repair-in-Place's wave skeleton, ONE-MEASURE's calibrated `p_t` core as the Wave-3
destination, PIT BOSS's objective function and graduated go-live as the evidence machine.**
All three designs independently converged on ~80% of this content - that convergence is itself
evidence.

### Wave 0 - make truth observable (days; no decision-math changes)
1. **Replay-lab capture repair** (the prerequisite for validating everything else): keep polling
   exited positions' NBBO to the thesis horizon (`post_exit:true` rows); store per-lane thesis
   *inputs* so variant thesis policies can be recomputed; mark-at-entry row; ≥1-row grid gate.
2. **Grader integrity + pooled row + e-process**: dedupe by position_id (loud quarantine),
   merged trades counted once, %-of-premium `R_i` as the statistic, pooled ALL row primary,
   e-process wealth per (scope, cohort), MDE line in the nightly scorecard, fill-provenance
   (`nbbo_source`, `nbbo_age_s`) on forced exits.
3. **Measure-disagreement instrumentation** (hours): log `p_mkt` (RN touch) beside the
   already-logged `p_touch_target` and `ev_mu0` on every entry; horizon-consistent `p_target` at
   exit. This accumulates the calibration data Wave 3 needs.
4. **Hub options tab** (hours): render the already-computed `snap.options` as default; delete the
   seven equity tabs (kills the $0-pill red herring for good).

### Wave 1 - unstarve the funnel, one registered cohort (days)
5. `max_chain_expirations` 3→6 (restores the declared DTE 0-5 scan; DTE 3-5 clears ⅓-of-life
   with ≥1.6× slack). 6. Per-DTE λ caps ~{0:200, 1:120, ≥2:90} + λ floor conditioned on delta
   (or drop the floor for δ≥0.7). 7. **Coherence gate: `p_touch_target ≥ 0.25`** (already
   computed; kills the priced-lottery class the extra tenors would otherwise admit) + feasibility
   cap `|ln(1+target)| ≤ 2·iv·√horizon` at signal build. 8. Clock-consistent liquidity floors:
   volume ≥ 100·min(1, elapsed/390); index DTE≤1 accepts OI≥1000 **or** day-volume≥500; premium
   floor ~$0.50. 9. Lane-2 universe by measured spread, not catalyst romance: hunt-list admission
   requires live spread ≤5% at the 0.5-δ strike; hunt-list freshness contract
   (`session_date == today` else journal `hunt_list_stale` + fall back to a deterministic movers
   screen - the crew becomes a ranking enricher, not a single point of failure); crew timeout
   budget-aware; fetch yesterday's after-close reporters. 10. Feed retry beyond 429 (timeouts/5xx,
   capped backoff) + chain-fetch one retry. 11. Latch-at-entry with 30-min re-arm (validate via
   telemetry; split verdicts). 12. Backfill/RVOL-baseline hourly retry.

### Wave 2 - exit engine v3, ONE registered cohort, validated on the repaired lab first (week)
13. Rule (b) evaluated only on **committed closes on the entry's own grid**, hysteresis + 2-bar
    (or time-based) persistence, band frozen at entry width - *and* judged against the replay
    evidence that hysteresis alone didn't pay: the sweep includes band-quantile recalibration
    (p80–p85 vs mean) per LANES-5. 14. **Time-based persistence for h/i\*** (~one non-overlapping
    mu window) → cadence-invariant. 15. Variance-scaled blend `w·τ²/(τ²+SE²)` + robust endpoints +
    entry-consistent prior (`mu_prior = p_thesis·mu_thesis` en route to `p_t`) - shipped together
    (the current inflated prior is the only brake on the noise clock; TRAJECTORY-6). 16. MATH-CORE-1
    one-liner + re-sweep `p_regain_min`; d2 co-requires `ev_hold<ev_sell` or demotes to replay;
    theta conventions unified (trading-time everywhere); RTH-gate the bar builder; staleness bound
    on the evidence clock (halt ⇒ `mu_prior=0`, not full thesis); overnight grantees exempt from
    rule (b) until their frame is re-establishable. 17. Replace the 0DTE sigmoid with the
    variance-clock hazard; refit from stored quote paths (registered protocol in the research doc).

### Wave 3 - the calibrated core + go-live bar (week-plus)
18. **Per-lane `p_thesis` calibration** offline from the ~500-session intraday cache (replay the
    pure lane predicates; measure P(touch target within horizon), bucketed by lane × target-size ×
    RVOL/percentile); delete the global 0.5; selector gates on `p_0 ≥ p_mkt + margin` - the
    system's edge claim finally becomes falsifiable. If no cell clears the market: **that is the
    honest discovery**, and the answer is re-founding lanes on the three published cost-surviving
    mechanisms (index noise-area EOD-hold; stocks-in-play ORB above the RVOL flip; last-30
    momentum), not loosening gates. 19. Graduated go-live per PIT BOSS: pooled wealth ≥5 ⇒
    tuition-capped 1-lot pilot (measures real fills); ≥20 ⇒ sized live behind the affordability
    filter. 20. Fix EVENTS-CALENDAR-1 before year-end (2027 tables + loud rollover guard);
    MacroReaction FOMC arm parked or re-founded as a presser-reversal lane.

### Deletions/parks (from the dead-layers seam, all with written re-arm conditions)
DELETE: iv_rank penalty + hv20 term, C5/news-shock accel blocks, equity hub tabs + feeders,
`prob_itm`, briefing fat (25 Finnhub calls/day, scorecard digest, null vix), stale-comment cleanup.
PARK: last30 (until target re-derivation), news/catmem covariate stack + mention_tap (re-arm:
trailing-20-session entries ≥10), MacroReaction-FOMC (re-arm: reversal design). KEEP: WORST
ledger as the go-live bar, lanes→selector→ladder architecture, halt entry gate, news_tap, the
registration discipline itself.

---

## 7. Red-herring prevention (Q3 answers, condensed)

| Trigger | Red herring | Prevention (mapped fix) |
|---|---|---|
| Hub $0 pills | "no money!" panic-stop | Wave 0.4 (delete equity tabs); never stop a shadow day over any portfolio display |
| 20-min drift noise | h/i* forced sales of good positions | Wave 2.14/15 (persistence + variance scaling) |
| Band-edge entries | (b) insta-cuts read as "thesis was wrong" | Wave 2.13 + band sweep; grade cuts only via the repaired lab |
| Premarket echo bars | phantom VWAP/mu extremes at the open | Wave 2.16 RTH gate |
| Fresh ATM strikes OI=0 | "illiquid" veto of the most liquid strike | Wave 1.8 OR-gate |
| Halted/frozen tape | "thesis fully intact" infinite hold | Wave 2.16 staleness bound + `halted_while_held` |
| Single-model crew day | alphabetical top-10 read as ranked conviction | Wave 1.9 (tie-breaks, degraded-consensus flag) |
| One $3k contract | lane "verdict" driven by premium mix | Wave 0.2 (%-of-premium stats) |
| Early PF ≥ 1.2 | "we have edge" at N=25 (~33% false) | Wave 0.2 e-process + MDE line; PF≥2.2 nominal bar at N=25 |
| Replay "best variant" | promoting a variant selected by the same sample | fresh wealth per cohort; replay = hypothesis generator only |
| 2027-01-01 | macro layer silently gone | Wave 3.20 rollover guard |

---

*Audit performed 2026-07-16 in two parts (Part 1 + probes + verify, then Part 2). The live
session was never touched: all probes read-only, all edits doc-only, decision code unmodified
(suite green after the OWNER_RULES errata).*

---

## IMPLEMENTATION ADDENDUM (2026-07-17, pre-open)

**Waves 0–3 are IMPLEMENTED and armed for the 2026-07-17 07:30 CT session** under the new
registered cohort **`a5ce85415e5a`** (7 sweep-ledger rows `opts-audit-*-v1`; suite 498/0;
`--once` smoke green: last30 + MacroReaction-FOMC parked, stale hunt list rejected loudly,
post-exit capture armed for the 07-16 exits). A Discord-dispatched session had started this
work (mission `20260716-audit-wave-fixes`) and died mid-changeset, leaving
`math.py`/`trajectory.py`/`exit_engine.py` partially edited and 15 tests failing; those
partials matched the audit spec, were adopted, completed, and verified.

Notable semantic decision recorded here: `tests/test_iwm_worked_example.py` was **repinned to
v3** - the old pin required selling the reclaim on ~1σ evidence, which is precisely the
noise-clock mechanism TRAJECTORY-1 refuted (and its authority, OWNER_RULES, was retracted).
v3 pins: no forced take (unchanged), 1σ reclaim = HOLD, close by the 0DTE clock family; the
v1-vs-v3 divergence is measured by the repaired lab on real stored paths, not asserted.

Deferred with rationale: per-lane `p_thesis` values (offline ~500-session cache study - 
plumbing shipped, global 0.5 + `touch_feasibility` gate carry coherence until then);
variance-clock 0DTE decay refit (needs the stored-path data the post-exit capture now
collects); watch-hub options tab (observability only); lane-2 live-spread admission probe
(the premium-tiered abs cap shipped instead). Also intentionally NOT done: no git commit - 
the working tree carries other streams' uncommitted work.*
