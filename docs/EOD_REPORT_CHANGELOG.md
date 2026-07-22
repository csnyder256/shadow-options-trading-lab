# ATLAS - EOD Report Changelog

The compounding record of the `/eodreport` post-market self-improvement pass. Each run appends a dated
entry (newest first) and updates the Change-ledger table. An armed change is not "done" until a later run
re-audits it and marks it VALIDATED or REVERTED - as the sample grows, so does our knowledge of what works.
Format: `.claude/skills/eodreport/references/changelog-format.md`.

## 2026-07-21 (Tue) - lab day 2: overnight-gap loss (QQQ), funnel warmup-guard shipped, main shadow bleeds a 6th session

**Second two-process EOD.** Both processes ran clean: lab 20/20 armed, **ZERO quarantines**, all
falsification gates `[]`, `pid_collisions []`, `registry_problems []`; main shadow 4 lanes armed ==
printer-expected, `err.log` empty, no restarts, no journal errors. Feeds all UP and richer than day 1
(news_stream **1039** · news_macro **340** · news_flags **684**; earnings_week 717 sym / 399 timing-reliable).
Both yesterday cross-process watch-items **CLOSED**: ATLAS-VixRefresh ran 15:40 (Result 0x0 →
`vol_regime` vix_close 18.65 / pctile 70.2, ladder advanced a session); and the day-1 "429" scare was a
false positive (grep hit `429` inside epoch-float substrings of routine `tick:` lines) - the main feed
pulled `quotes 12/13` every tick all session, **no real 429s, the 40/min lab cap did not starve it.**

### Lab verdict table (cohort day 2 - everything still UNPROVEN at n«25)
| strategy | state | cohort | N(exits) | day P&L worst | W_for | W_against | funnel | verdict | action |
|---|---|---|---|---|---|---|---|---|---|
| overnight_1dte_strangle | armed | 328513050c5e | 3 | **-$227** | 0.9992 | 1.0008 | OK | UNPROVEN | NONE |
| gap_fade_bull_put | armed | 6b74c8c782a2 | 1 (n=5) | **+$10** | 0.928 | 1.0721 | OK | UNPROVEN | NONE |
| ic_45d16d/jade_lizard/strangle_45d16d/vrp_short_straddle/squeeze | armed | - | 0 (holding) | open | 1.0 | 1.0 | OK | UNPROVEN | NONE |
| wput_weekly_putwrite | armed | fd9f3807bd55 | 0 | 0 | 1.0 | 1.0 | DEAD† | UNPROVEN | INVESTIGATE-FUNNEL |
| zero_dte_morning_ic | armed | 1911e123a405 | 0 | 0 | 1.0 | 1.0 | DEAD‡ | UNPROVEN | INVESTIGATE-FUNNEL |
| (11 low-freq others) | armed | - | 0 | 0 | 1.0 | 1.0 | WARMUP* | UNPROVEN | NONE |

\* **NEW: funnel warmup-guard** (`lab-funnel-warmup-guard-v1`) suppressed **11** day-1 false alarms.
† **wput DEAD is a CADENCE artifact, not a defect** - wput fires **Fridays only** (one ATM weekly put ×9
symbols = 36/20 sessions); the lab launched Monday 07-20, so **no Friday has elapsed yet** (first is 07-24).
The guard is frequency-aware but not day-of-week-aware, so it can't suppress this one; it self-resolves 07-24.
A persistent zero AFTER a Friday would be the real investigation.
‡ **zero_dte_morning_ic DEAD is REAL and correctly kept visible** - its 0DTE spread-gate
(`max_spread_frac_of_mid`) rejected every 0DTE book again (>15% spreads); it expects ~daily fires and gets 0.
This is the same TWEAK-QUEUE item opened 07-20. Fires stay 0 until the gate is (validate-first) loosened.

### Truth-validation (Tier-2 RH-MCP minute paths on ALL of today's 8 trades - both processes)
**Lab overnight_1dte_strangle** (rule `next_open_buyback` - doctrine followed exactly; bought back at
today's open as designed):
| leg (sold 07-20, bought back 07-21 open) | strike vs open | buyback worst | verdict |
|---|---|---|---|
| QQQ 703C/689P | QQQ **opened 706.6** - call breached by 3.6pt | **-$232** | UNLUCKY-BUT-SOUND (documented overnight-gap failure mode; buyback priced true) |
| SPY 746C/738P | SPY opened 746.3 - grazed the call | -$16 | UNLUCKY-BUT-SOUND |
| IWM 294C/290P | IWM opened 293.4 - in-range | +$21 | CORRECT (both legs decayed) |

The entire −$227 is the QQQ leg gapping through the short call overnight - the textbook short-gamma tail of
this strategy. e-process barely moved (R = −0.005 of the large CaR denom; W_against 1.0008). **Attribution
coverage 0.168 → UNRELIABLE-ATTRIBUTION** (residual 0.93): the entry-greek linearization cannot book an
overnight gap; the engine correctly refused a mechanism claim. **gap_fade AAPL** (`gap_filled`, +$10): the
down-gap filled as thesised → short put spread decayed → CORRECT.

**Main shadow - all 4 `b_thesis_invalid` cuts truth-check CORRECT** (v3 exit engine working; the loss is
ENTRY-driven, not an exit defect):
| lane | contract | entry→exit (ET) | worst | underlying path | verdict |
|---|---|---|---|---|---|
| index_trend | IWM 295C | 09:35→09:45 | -$41 | IWM 294.4 → **fell to 292.9**, kept falling | CORRECT (long-call thesis invalidated) |
| index_trend | SPY 747P | 09:40→10:05 | +$2 | SPY sideways 744–745, then rallied to 748 | CORRECT (scratch dodged the afternoon rally) |
| index_trend | QQQ 702P | 10:10→10:19 | -$63 | QQQ 703 → **rose to 705**, ran to 708 | CORRECT (down-thesis invalidated; cut dodged bigger loss) |
| index_trend | SPY 744C | 12:30→14:34 | -$72 | SPY 748.6 → drifted 748.1, up-move never developed | CORRECT (no recovery forgone) |

### Day P&L
- **Lab: −$217 worst** (overnight_1dte −$227 + gap_fade +$10). 17 open combos still marking.
- **Main shadow: −$174 worst, 0/4** (all index_trend directional bets whipsawed in a rangebound tape).
  Live cohort **a5ce85415e5a wealth 0.6853 → 0.6063** (n=8→12, mean R% −0.371); pooled all-time
  **−$1006 on n=15, wr 0.133**. This is the **6th straight losing-lean session** on the live cohort.
- **Combined realized day: −$391 worst.**

### Cross-strategy exposure (Phase 8 - the wired block, now with a full open book)
Open book 17 combos: **net Δ +$31,265 / gross $75,708** (ratio 0.41 < 0.6 → **no concentration**, `flags []`),
**net vega −913** (coherent short-vol posture), **net theta +$813/day**. Per-underlying: SPY +8520, QQQ
+12916, IWM +6868, MSFT +2961 - a net-LONG-delta short-premium book (short puts/jade-lizards skew delta long).
Correlation dormant (`n_series 0`; needs ≥15 overlapping sessions). **Residual risk:** the book is short-vol
into any vol spike; the QQQ overnight loss is a small live demonstration of that tail.

### Errors found + disposition
1. **Funnel warmup false alarms** (13 day-1 INVESTIGATE-FUNNEL on legitimately-quiet strategies) →
   **FIXED tonight** (`lab-funnel-warmup-guard-v1`). See Changes.
2. **overnight_1dte −$227** → NOT a defect: doctrine followed, buybacks priced true vs the real open, the
   loss is the documented overnight-gap tail. Attribution correctly self-flagged UNRELIABLE (coverage 0.17).
3. **No process/feed/gate errors, no quarantines, no 429s.** Clean day mechanically.

### Changes applied
- **`lab-funnel-warmup-guard-v1` - ARMED go-live-first (rule 3A / structural reporting-correctness).**
  `grade_strategy_lab.py` now pro-rates each strategy's `expected_fires_per_20` by the elapsed lab window
  (`min(lab_sessions_elapsed,20)/20`) for BOTH the STARVED threshold and the DEAD/WARMUP cut: a negative
  health computed from an unfull window (<1 expected fire) is overridden to **WARMUP** (action NONE); an
  actively-firing strategy stays OK. `main()` supplies `lab_sessions_elapsed` = distinct days with any lab
  entry (a conservative lower bound - never over-counts). **Byte-identical once ≥20 sessions elapse**;
  `lab_sessions_elapsed=None` → legacy behavior preserved. The trailing-20 funnel metric is definitionally
  uninformative before 20 sessions, so suppressing a signal derived from an unfull window is
  correct-by-construction (why this is 3A, not validate-first). Effect: day-1's 13 false INVESTIGATE-FUNNEL
  → **7 OK / 11 WARMUP / 2 correctly-retained** (wput cadence self-resolving + zero_dte real spread-gate).
  `verdicts.py` gains a WARMUP why-line. Test `test_funnel_warmup_guard` (WARMUP@2 sessions, DEAD@25
  preserved, high-freq never suppressed, None→legacy, **+ the (0,1)-cadence boundary below**). Registered
  `lab-funnel-warmup-guard-v1`. **Suite 736/0.**
  **A fresh-context skeptic REFUTED the first cut and the defect was fixed same-turn:** the original
  override condition (`expected_over_elapsed < 1.0` alone) permanently silenced any strategy whose
  `expected_fires_per_20 ∈ (0,1)` - the pro-rated target caps at `expected` once ≥20 sessions elapse, so
  `<1` stayed true forever, hiding a genuinely-dead rare-event strategy from INVESTIGATE-FUNNEL at every
  elapsed count. Not on today's roster (all 20 declare ≥1.0; min `pre_fomc_drift_call`=1.0) but one registry
  edit from live - and pre_fomc's TRUE cadence is ~0.63 (8 FOMC/yr) rounded up, so an honest re-declaration
  would have silently disabled its funnel detection. Fix: gate the override on `lab_sessions_elapsed < 20`
  (the trailing-20 window must be unfull) AND `expected_over_elapsed < 1`, so the guard is a **complete
  no-op once ≥20 sessions elapse**. Re-ran the skeptic's exact repro → DEAD at elapsed 25/100/10000
  (identical to legacy); added a (0,1)-cadence boundary test (WARMUP@2, DEAD@{20,25,100}). Documented
  limitations: (i) day-of-week cadence not covered (wput fires Fridays - self-resolves 07-24); (ii)
  `lab_sessions_elapsed` is lab-wide, so a strategy added AFTER 20 lab sessions gets no per-strategy warmup
 - both are future refinements needing per-strategy trigger predicates / first-arming counts in the registry.

### Watch-items (next run)
- **Main shadow 6th losing session (wealth 0.6063, n=12).** The pattern is now consistent across 07-20/07-21:
  index_trend takes short-horizon directional index bets that whipsaw in a rangebound tape; the v3 exits cut
  each one CORRECTLY, so the loss is **entry-driven, not exit-driven**. Below n=25 and with correct exits,
  no cohort fork tonight (arming discipline) - but ELEVATE to a registered design hypothesis to accrue on its
  affected-trade sample: *is index_trend's directional entry mis-fit to low-realized-vol/rangebound regimes?*
  (Note [[regime-gate-2026-06-24]] was REFUTED in the equity era - any gate must clear that bar with evidence.)
- **wput fires 07-24 (first Friday since launch).** Confirm it fires ~9 puts and its DEAD clears. A zero after
  a Friday = real defect.
- **zero_dte_morning_ic** still 0-fire on its spread-gate - the validate-first `max_spread_frac_of_mid` loosen
  is the next lab tweak once its affected 0DTE-book sample is captured.
- **Short-vol book (net vega −913)** into any vol event; overnight_1dte is the concentrated overnight-gap tail.
- Grade the 17 open combos as they exit (overnight strangles cover tomorrow's open; 45-DTE managed premium holds).

## 2026-07-20 (Mon) - STRATEGY LAB first live day + main shadow choppy-day roadkill

**First two-process EOD.** The strategy lab launched at 07:35 CT and traded its first live session
beside the main shadow. Headline: the lab **infrastructure works end-to-end on real data** - 20 entries
across 7 strategies, 4 exits, 16 open, **ZERO quarantines, ZERO crashes**, falsification gates clean,
Tier-1 validation 4/4, `pid_collisions []`. Underlying prices independently verified against the untouched
main shadow (both saw SPY ~747 / QQQ ~700 / IWM ~294 to the cent - the market genuinely rallied off Friday).

### Lab verdict table (cohort day 1 - everything UNPROVEN at n«25)
| strategy | state | cohort | N(exits) | day P&L worst | W_for | W_against | funnel | verdict | action |
|---|---|---|---|---|---|---|---|---|---|
| gap_fade_bull_put | armed | 6b74c8c782a2 | 4 | -$151 | 0.92 | 1.08 | OK | UNPROVEN | NONE |
| ic_45d16d_managed | armed | db702ea5e2cb | 0 (3 open) | open | 1.0 | 1.0 | OK | UNPROVEN | NONE |
| jade_lizard | armed | 56ae65fffc0f | 0 (3 open) | open | 1.0 | 1.0 | OK | UNPROVEN | NONE |
| overnight_1dte_strangle | armed | 328513050c5e | 0 (3 open) | open | 1.0 | 1.0 | STARVED* | UNPROVEN | INVESTIGATE-FUNNEL |
| strangle_45d16d_managed | armed | 757ffab1f822 | 0 (3 open) | open | 1.0 | 1.0 | OK | UNPROVEN | NONE |
| vrp_short_straddle | armed | 134066b002fc | 0 (3 open) | open | 1.0 | 1.0 | OK | UNPROVEN | NONE |
| squeeze_long_straddle | armed | fce588186bd0 | 0 (1 open) | open | 1.0 | 1.0 | OK | UNPROVEN | NONE |
| (13 others) | armed | - | 0 | 0 | 1.0 | 1.0 | DEAD* | UNPROVEN | INVESTIGATE-FUNNEL |

\* **DEAD/STARVED are DAY-1 ARTIFACTS** of the trailing-20-session funnel metric with 1 session of history
 - NOT defects. Every zero-fire root-caused LEGITIMATE: wput=Friday-only, tsmom/short_put=first-of-month,
pre_fomc=no FOMC, cndr=monthly-roll, earnings/pre_earnings=no qualifying reports, backspread/atm_calendar=low-IV
gate blocked (VIX pctile 71 >50), rsi2=no signal, donchian=no breakout, zero_dte=spread-gate rejected 16×
(0DTE spreads >15% of mid). FINDING: funnel-health needs a warmup guard (report NEW until ~20 sessions) - 
registered reporting refinement, ships with validation, NOT armed tonight.

**Lab day P&L:** realized net(worst) **-$151** (gap_fade only) + 16 open short-premium positions marking.
**Exposure (now wired, `opts-lab-exposure-wire-v1`):** net Δ$ +34.0k / gross Δ$ +68.5k (ratio 0.49, under
the 0.6 flag) · **net vega -910 (NET SHORT VOL - the honest "one bet")** · net theta +$844/day · no
CONCENTRATED flag (structures are delta-balanced across SPY/QQQ/IWM). A vol spike is the correlated risk, not a delta direction.

### gap_fade_bull_put truth-validation (RH minute paths)
| trade | exit | rule | net worst | verdict | evidence |
|---|---|---|---|---|---|
| TSLA | 10:12 | fade_thesis_dead | -$63 | **CORRECT** | TSLA kept falling 386→369 all day; bail avoided worse |
| META #1 | 09:57 | fade_thesis_dead | -$106 | **UNLUCKY-BUT-SOUND** | META bottom-ticked 636 at the bail then rallied to 652 - rule-correct stop, whipsaw outcome |
| META #2 | 11:05 | gap_filled | +$9 | **CORRECT** | gap filled to 648 as the fade thesis predicted |
| IWM | 11:26 | gap_filled | +$9 | **CORRECT** | IWM recovered 292.5→294 |

### Main shadow (flagship, cohort a5ce85415e5a) - 0/4, choppy-day whipsaw
| OCC | lane | entry→exit ET | rule | net worst | verdict |
|---|---|---|---|---|---|
| SPY 260724 C747 | index_trend | 09:35→09:50 | d2_costbasis_backstop | -$17 | UNLUCKY-BUT-SOUND (fast small cut; SPY drifted down) |
| QQQ 260720 C706 | index_trend | 09:35→10:00 | b_thesis_invalid | -$98 | CORRECT (QQQ fell 705→698, up-bet genuinely wrong) |
| SPY 260720 P748 | index_trend | 10:00→12:02 | b_thesis_invalid | -$47 | UNLUCKY-BUT-SOUND (bailed on a midday bounce; SPY later fell to 742) |
| QQQ 260720 P698 | index_trend | 11:00→11:25 | b_thesis_invalid | -$137 | UNLUCKY-BUT-SOUND (bailed on a bounce to 701.7; QQQ closed 696) |

**Main day P&L:** net(worst) **-$299**, 0/4. **Live cohort e-process wealth 0.6853** (n=8, mean R% -0.41 - 
underwater); prior cohort 6c1dc2a4e1a7 wealth 0.9755 (n=3); pooled all-time -$832 on n=11, wr 0.091.
The whipsaw pattern (b_thesis_invalid cutting on bounces that reverse) is the documented noise-cutting
behavior on a choppy range day - NOT a new defect. **Combined platform realized P&L day 1: -$450.**

### Feeds - all healthy
news_stream 637 · news_macro 110 · news_flags 562 (all 3 sources up) · earnings_week fresh (593 symbols,
320 timing-reliable) · vol_regime shows Friday VIX 18.77/pctile-71 (ATLAS-VixRefresh fires 16:40 ET, ~10 min
after this grade - not-yet-run today, not a failure; the fallback ladder is designed for a 1-day-stale VIX).

### Errors found + disposition
1. **Exposure block unwired in grader** (real defect) → FIXED tonight (`opts-lab-exposure-wire-v1`, rule 3A, tested, suite 735/0).
2. **Funnel-health DEAD/STARVED day-1 false alarm** → design note; warmup-guard refinement queued (registered, validate-first).
3. **zero_dte_morning_ic 16 spread-gate rejects** (>15% on 0DTE) → TWEAK-QUEUE (`max_spread_frac_of_mid` tunable) - validate over affected 0DTE trades before loosening; the gate correctly refused wide books today.

### Watch-items (next run)
- Grade the 16 open lab positions as they exit (overnight strangles cover tomorrow's open; the 45-DTE managed
  premium sits for days). Watch the net-vega -910 short-vol book into any vol move.
- Confirm ATLAS-VixRefresh ran (vol_regime asof advances to 2026-07-20) and the 40/min lab cap left the main
  shadow's feed unstarved (no 429s - hub_used was 0 at teardown; need a mid-session sample next run).
- Main shadow: 5th straight losing-lean session on the live cohort (wealth 0.6853) - the choppy-tape whipsaw
  is the standing open question, not tonight's to solve.


## Change ledger (running list of every behavior change)

Validation is by AFFECTED-TRADE count (X/N), never days - see `.claude/skills/eodreport/references/changelog-format.md`.

| Date armed | Change | Default | Status | Strategy | Affected (X/N) | Evidence / notes |
|------------|--------|---------|--------|----------|----------------|------------------|
| 2026-07-21 | **lab funnel warmup-guard** - `grade_strategy_lab.py` pro-rates `expected_fires_per_20` by the elapsed lab window; a negative funnel health (STARVED/DEAD) from an unfull window (<1 expected fire) → **WARMUP**/action NONE; firing strategies stay OK | ON | VALIDATED (structural) | lab (all 20) | n/a | GO-LIVE-FIRST rule 3A (reporting-correctness: trailing-20 metric is undefined before 20 sessions; complete no-op once elapsed≥20). Day-1's 13 false INVESTIGATE-FUNNEL → 7 OK / 11 WARMUP / 2 retained (wput cadence self-resolving 07-24 + zero_dte real spread-gate). Skeptic REFUTED cut-1 (sub-1-cadence strategies silenced forever) → fixed by bounding the override to `lab_sessions_elapsed<20`; repro re-run DEAD@elapsed≥20 + (0,1) boundary test added. `lab-funnel-warmup-guard-v1`; test `test_funnel_warmup_guard`; suite 736/0. Limitations: day-of-week cadence + lab-wide (not per-strategy) elapsed count. |
| 2026-07-20 | **STRATEGY LAB LIVE** - 2nd shadow process, 20 published strategies armed, each own cohort/doctrine (`atlas/strategy_lab/`, `run_strategy_lab.py`) | ARMED (20 cohorts) | accumulating | lab (all 20) | 0/25 each | First live day 2026-07-20: 20 entries/7 strategies, 4 exits, 16 open, ZERO quarantines, gates clean, Tier-1 4/4, prices verified vs the untouched main shadow. 20 `lab-strat-*-v1` rows. Suite 735/0. |
| 2026-07-20 | **lab exposure block wired into grader** - `grade_strategy_lab.py` now populates `scorecard.cross.exposure` + correlation from open combos (was spec-only/empty) | ON | VALIDATED (structural) | lab | n/a | GO-LIVE-FIRST rule 3A (additive reporting, no cohort/stat touched). Surfaced day-1: 16 open positions, `cross={}`. `opts-lab-exposure-wire-v1`; test `test_grader_wires_exposure_block`; suite 735/0. |
| 2026-07-17 | **AUDIT WAVES 0-3 IMPLEMENTED** - exit-engine v3 (variance-scaled blend τ²/(τ²+SE²), entry-consistent prior p·μ, 20-min persistence h/i\*, rule-b committed-close+frozen-band+0.8-hysteresis+2-eval streak, d2 EV co-requirement, MATH-CORE-1 p_regain fix, evidence-stale bound, theta unified 365/252, RTH bar gate, zero-bid books); funnel cohort (6 expirations, per-DTE λ caps 200/120/90, touch_feasibility p≥0.25, time-scaled volume + OI-or-volume, premium floor $0.50, tiered non-index spread cap, hunt-list freshness, latch-at-entry+30-min re-arm, feed retries, crew timeout 600s); evidence machine (position_id dedupe, pooled ALL row, %-of-premium e-process wealth λ{.05,.1,.2} cap 2.0, PILOT≥5/LIVE≥20 unlocks, MDE line, fill provenance, post-exit NBBO capture, mark-at-entry, grid ≥1-row, torn-tail guard, fail-closed rebuild, roll-latch-last); calendar algorithmic any-year + coverage guard; PARKED last30 + MacroReaction-FOMC + iv_rank/hv20 score terms deleted | **ARMED (new cohort `a5ce85415e5a`)** | accumulating | 4 cohort trades (e-process wealth 0.8066, n=4 after 07-17) | 7 sweep rows `opts-audit-*-v1`; suite 498/0 incl. repinned IWM worked-example (v3 semantics: noise-reclaim HOLD is the registered cure - old "sell the reclaim" pin was the noise clock, authority retracted with OWNER_RULES) + 7 new behavior pins; `--once` smoke: cohort hash live, last30/fomc parked, stale hunt list rejected loudly, post-exit capture armed for the 07-16 exits. Started by a failed Discord session (its math/trajectory/exit_engine partials adopted + completed), finished + verified in-session 2026-07-17 01:00-01:40 CT. Deferred with rationale: per-lane p_thesis values (offline cache study; plumbing shipped), variance-clock 0DTE decay refit (needs stored-path data), hub options tab (observability only), lane-2 ≤5%-spread admission probe (premium-tiered cap shipped instead). |
| 2026-07-10 | **OPTIONS: exit engine v2** - forced +100% take + trail family REMOVED (unregistered author interpolations - the hallucination incident); live mu_eff reassessment (trajectory.py); continuous P(regain) profit rule; d2* cost-basis backstop; v1 frozen as `exit_engine_legacy` A/B baseline | ARMED (cohort `6c1dc2a4e1a7`) | accumulating | **2/25** | `opts-rework-exit-core-v1` + calib rows. the owner's governing standard was recorded verbatim in `docs/OWNER_RULES.md` (retracted 2026-07-16 → `docs/OWNER_RULES_RETRACTED.md`). IWM 2026-07-10 worked-example regression pins it (v2 sells the reclaim; v1 provably later+lower). Suite 490/0. **First real graded fill 07-13: IWM 293P, rule (b) thesis_invalid cut @ −$16 worst - truth-validated CORRECT (IWM reversed up, put expired worthless; dodged ~−$172).** **07-16: QQQ 712P, rule (b) thesis_invalid @ −$97 worst 15 min after entry while engine's own state read `p_regain=0.913`** (flagged live in `docs/AUDIT_2026-07-16_options_platform.md` TRAJECTORY-1/SELECTOR-3 as the noise-clock/manufactured-EV failure pattern - none of the audit's Wave 1/2 fixes are landed yet). Same day, NVDA 210P (inplay_orb) closed `d2_costbasis_backstop` at $0.00 net worst (scratch) - the audit's EXIT-ENGINE-3 Tier-B pattern (backstop scratches winners) reproduced live same-day. Paired-replay legacy-vs-v2 seed from the 07-13 quote path still pending. |
| 2026-07-10 | **OPTIONS: math-audit fixes** - EXACT p_profit (was GH-quantized; selector 0.40 gate flipped entries), exact E[intrinsic], PV discounting, theta calendar→trading units, 0DTE ramp double-count removed, trading_T expired→MIN_T, _phi erfc, grader identity-quarantine + Infinity JSON | ON | VALIDATED (math) | n/a | **GO-LIVE-FIRST 3A**: 26-agent adversarial audit, 14 defects upheld by independent refuters with numeric repros. `opts-fix-math-audit-20260710`. |
| 2026-07-10 | **ALL-IN OPTIONS PIVOT** - equity systems archived to `attic\` (manifest-driven; nothing deleted); options-only launcher (no RH/Alpaca/llama-swap at launch); `--options-only` alerter | ON | VALIDATED (ops) | n/a | Suite 1004→325 exact reconciliation; launcher live-smoked; refute defects fixed (zombie panels, alert close-window 15:20, shim forwarding). Tags `pre-pivot-2026-07-10` / `pre-exit-correction`. |
| 2026-07-10 | **OPTIONS: premium cap removed** - `SelectorParams.premium_max_usd` 350 → None (the shadow grades decision quality, never affordability; param kept for a future "can we afford it" FINAL filter) | ARMED | accumulating | **0/25** | **owner directive 2026-07-10** + structural: at QQQ ~725 / SPY ~750 every 0.55-0.75-δ contract except deep-0DTE costs >$350 - the cap forced index-lane picks out of the registered delta skew (or to no_pick), contradicting the selector's own value-not-affordability charter. Registered `opts-tweak-remove-premium-cap-v1`; cohort by registration date (0 prior entries). Suite 1004/0; refute **FAILED-TO-REFUTE**. Sample = entries whose pick has ask×100 > 350. ⚠ watch: lane $-aggregates now premium-scale-heterogeneous - read P&L in %-of-premium alongside $. |
| 2026-07-10 | **OPTIONS: rule (c) premium stop INERT** - `ExitParams.stop_frac` −0.50 → None (never exit just because the premium is lower now; losses exit via thesis (b), theta (g), the no-anchoring EV stop (h), or the clocks) | ARMED | accumulating | **0/25** | **owner standing directive 2026-07-10** ("do not exit positions just because 'number lower now'; no risk-of-ruin in the shadow"). Old behavior stays measurable as the `opts-variant-evidence-exits-v1` paired-replay column on stored quote paths. Registered `opts-tweak-disable-premium-stop-v1`. Both call sites guarded (after-hours ladder + main flow). Suite 1004/0; refute **FAILED-TO-REFUTE** (probe: −52% position never fires (c) at 11 clock points; stop_frac=0.0 falsy-edge correct; deep −100% loser is flushed by the clocks same-day). ⚠ watch: deep losers now ride to a clock - compare first N exits vs the `opts-variant-evidence-exits-v1` replay column. |
| 2026-07-06 | `climax_reversal_guard` (rule1) - veto momentum/breakout buys ≥3% below a FRESH 52wk high | ARMED | accumulating | **1/25** | **GO-LIVE-FIRST** (rule 3B: "block a buy below a *reversed* fresh high" is a Wyckoff/O'Neil fundamental; also structural - closes the chase-cap's direction-blind bypass). n=1 blocked = GEO −3.64% (a correct block). The 3% is the TWEAK-able part the sample tunes. `atlas/scan/context.py`; `config/scanner.yaml`. |
| 2026-07-06 | `climax_gap_guard` (rule2) - veto a ≥3% gap into a fresh 52wk high | off (shadow) | shadow | **3/25** | **VALIDATE-FIRST**: +3% is eyeballed. Shadow sample MIXED (2 HELP / 1 HURT) - GEO −3.64 (HELP) + **BEAM +7.39 (HURT, 07-07)** + BZH −1.60 (HELP, 07-08, +14.2% gap into fresh high → fell). Keep accumulating; do not arm. |
| 2026-07-08 | `take_reversion_winners` - Guardian EOD TAKES a reversion/fixed-target WINNER same-day (vs riding it overnight); momentum winners still ride | off (validate-first) | shadow | **0/25** | **VALIDATE-FIRST**: overturns the validated 2026-07-01 "winners ride" default on n=1 (MGM) → earns arming on evidence. Byte-identical when off. Matrix when on: momentum=ride, reversion=flatten (take win / cut loss). Grade next-day: did riding reversion winners beat taking them? `guardian.py`; refute FAILED-TO-REFUTE; suite 726. |
| 2026-07-07 | `anti_peak_guard` (M3) - veto an A/B/D buy ≥1.5 ATR above its 21-EMA (extended chase) | off (shadow) | shadow | **0/25** | **SHADOWED 2026-07-08** (was armed n=7): it fires on setup_key A = the LIVE, validated rs_sleeve (+0.231R) whose edge IS buying extended RS leaders → an armed guard vetoes the one proven edge. Off pending N=25. **BLOCKED: cannot accumulate - recompute needs per-decision ema21/atr not in OHLC → needs a discovery shadow-logger (watch-item).** Re-arm must scope to B/D only, never A. |
| 2026-07-07 | run_loop crash-hardening - a single cycle's transient error no longer crashes the live daemon (15-consecutive breaker → fail-loud) | ON | VALIDATED | n/a | **GO-LIVE-FIRST** (rule 3A reliability; fixes the ACTUAL 07-07 crash - unhandled broker API-500 on get_portfolio → SystemExit). No trading-behavior change. `atlas/app.py`. 3 tests; **refute FAILED-TO-REFUTE**; suite 685. |
| 2026-07-07 | context-drop logging - append-only `runtime/context_drops.jsonl` of every context-gate DROP | ON | VALIDATED | n/a | **GO-LIVE-FIRST** (rule 3A pure observability, fail-safe). Makes the ARMED climax guards' blocked cohort auditable (context gates dropped names SILENTLY - no footprint). Mirrors 07-06 survivor log. `atlas/scan/discovery.py`. 3 tests; refute FAILED-TO-REFUTE. |
| 2026-07-07 | sizing-reject diagnostics - journal the binding cap on granularity_wall/below_min_notional rejects | ON | VALIDATED | n/a | **GO-LIVE-FIRST** (rule 3A observability, additive). Lets /eodreport diagnose WHICH cap floored an approved name to zero (hit this today on BCRX/CLDX). `atlas/orchestrator.py`. 2 tests; refute FAILED-TO-REFUTE. |
| 2026-07-06 | SAM.gov rate-limit fix - per-feed 6h poll floor + 429→long cooldown | ON | VALIDATED | n/a | **GO-LIVE-FIRST** (rule 3A: strictly-dominant reliability fix, no trading-behavior change → not affected-trade-gated). `atlas/collect/catalysts.py` + `app.py`; 20 tests. |
| 2026-07-06 | discovery-survivor logging - append-only `runtime/discovery_survivors.jsonl` of ranked context-passing survivors | ON | VALIDATED | n/a | **GO-LIVE-FIRST** (rule 3A: pure observability - fail-safe, cannot alter any trading decision). Gives /eodreport Phase 6 a real sample (was capped at the EOD-residual pool, n≈1). `atlas/scan/discovery.py` + `app.py`; `eod_extract.py` diffs it. Refute: live change **FAILED-TO-REFUTE**; fixed one minor offline-reader null-rank crash it surfaced (+reader tests). 8 tests; suite 678. Effective next launch. |

---

## Daily entries

### 2026-07-17 (Fri) - MANUAL run (full-access worker session, runtime junction reachable); FIRST live day of the v3 post-audit cohort `a5ce85415e5a`
**Context:** First trading session after last night's Wave 0–3 implementation (cohort hash-pinned `a5ce85415e5a`, `opts-audit-cohort-hashpin-v1`). Grading follows the rewritten `/eodreport` skill (SKILL.md + `references/options-shadow.md`, both dated 2026-07-17). Falsification gates all CLEAN: `malformed_exits [] · duplicate_exits [] · ledger_identity_violations [] · stale_fill_exits [] · halted_underlying_exits [] · expired_unexited []`. Heartbeat healthy end-to-end (`client_present:true`, teardown ts 16:20 ET, lanes_armed = the correct v3 roster `[index_trend, inplay_orb, macro_reaction, pre_earnings_straddle_stub]` - no last30/FOMC presence; `entries_today:4` reconciles the ledger).

**Shadow actions (cohort `a5ce85415e5a`):** 4 entries / 4 exits, **all `index_trend`, all 0DTE** (Friday). A choppy tape whipsawed the noise-band lane both ways - it bought two puts into an early dip, got cut when the indices rallied, then bought two calls into the rally.

| # | Contract (DTE) | Lane | Entry ET @ fill(worst) | Exit ET @ fill(worst) | Hold | Net P&L (worst / base / opt) | Rule | Correct? |
|---|---|---|---|---|---|---|---|---|
| 1 | QQQ 690P (0DTE) | index_trend | 09:40:08 @ $4.00 | 10:00:41 @ $1.66 | 20.5 min | **−$234.00** / −231.73 / −230.50 | `b_thesis_invalid` | CORRECT - put thesis (QQQ↓) invalidated; QQQ rallied 688.7→693.8, cut dodged near-total 0DTE decay (mae −0.74%, mfe +0.22%) |
| 2 | SPY 740P (0DTE) | index_trend | 09:45:07 @ $1.59 | 09:55:23 @ $0.61 | 10.3 min | **−$98.00** / −97.36 / −97.00 | `b_thesis_invalid` | CORRECT - put thesis (SPY↓) invalidated; SPY rallied 741.1→744.2, cut dodged further decay (mae −0.42%, mfe 0.00%) |
| 3 | SPY 715C (0DTE, deep-ITM δ0.99) | index_trend | 09:55:00 @ $28.94 | 14:00:00 @ $29.45 | 245.0 min | **+$51.00** / +64.97 / +72.50 | `b_thesis_invalid` | UNLUCKY-BUT-SOUND - small winner banked; call thesis (SPY↑) mildly held (mfe +0.43%). ⚠ selector quirk: a $2,894-notional near-stock-replica 0.99-δ pick from an "index_trend" 0DTE lane |
| 4 | QQQ 698C (0DTE) | index_trend | 10:10:01 @ $2.20 | 15:01:21 @ $0.81 | 291.3 min | **−$139.00** / −138.35 / −138.00 | `a_zero_dte_clock` | UNLUCKY-BUT-SOUND - thesis (QQQ↑) briefly held (mfe +0.76%) then round-tripped to entry; 0DTE clock (15:00) correctly forced the exit, salvaging $81 vs expiry-worthless |

**Day P&L:** net(worst) **−$420.00** (base −$402.47 / opt −$393.00) on 4 trades, winrate 0.25. Pooled all-time (both cohorts) net(worst) **−$533.00** on n=7, wr 0.143. **e-process wealth for the live cohort `a5ce85415e5a` = 0.8066** (n=4, mean R% −0.454; pilot ≥5, live ≥20 - a losing first day, wealth below the 1.0 restart). Prior cohort `6c1dc2a4e1a7` = 0.9755 (n=3, frozen). MDE: ~588 trades/yr → smallest detectable edge ~3.1% of premium (sd 0.305).

**Failures & feed health:** No process errors. `options_shadow.log` 2,417 lines today with **zero** error/exception/traceback; `options_shadow.err.log` empty (0 bytes); `alert_watch.err.log` empty; clean 07:30:02 CT launch (all three taps up: news 9516, news-flag 9476, mention 10324) → clean 15:20:14 teardown, no restarts. **News/scan delivery (filtered to 2026-07-17 by each stream's own ts; mentions epoch-converted from `bucket_ts`):** `news_stream` **899** rows · `news_macro` **398** · `news_flags` **576** · `mention_counts` **242** buckets (last bucket 16:15 ET, streams flowed to ~16:15–16:17 ET) - all healthy, nothing near-zero. v3 mechanism spot-checks PASS: today's quote path carries **4 mark-at-entry rows** (one per entry) + **345 post-exit capture rows** to the thesis horizon; h/i persistence clocks tracked in exit state (h_breach armed on both puts, no h/i *fire* today → the <20-min-breach bug is unreachable this session); no legacy exit-rule id anywhere; `hunt_list.json` final `session_date` = today with 13 candidates. **Two documented non-defect anomalies:** (a) a launch-time `hunt_list_stale` event (a 07-16 premarket artifact, 15 rows dropped, lane 2 armed EMPTY fail-open-loud) that **self-healed** - the fresh 07-17 crew list landed and InPlayORB ran 44 evaluations against it; watch that the premarket crew stops emitting a prior-session artifact at launch. (b) The rewritten skill's Phase 2 asserts the **news-flag tap is "PARKED per opts-audit-parks-v1"**, but the actual `opts-audit-parks-v1` registration parks only *last30 lane + FOMC arm + iv_rank/hv20 score terms* - NOT the flag tap, which the launcher still starts (PID 9476) and which produced a normal 576 rows (cf. 07-16's 607). Treating this as a **skill-doc error to reconcile**, not a system defect.

**Funnel/ladder autopsy:** Fires - `index_trend` 4 entries (100% of fills); `inplay_orb` 0 fills / **44 no_pick** (4 distinct catalyst names: TRV×13, SPFI×13, ALV×12, TFC×6); `macro_reaction` dormant (no CPI/NFP print - correct, event-gated, not a silent death); `last30` correctly `lane_parked` ×2; `pre_earnings_straddle_stub` silent (stub). InPlayORB gate kill-map (summed across 44 rejections): `no_quote` 284 · `spread_pct` 199 · `zero_dte_after_1400` 158 · `open_interest` 146 · `spread_abs` 83 · `volume` 2 - single-name catalyst options were killed at the liquidity/spread/no-0DTE-after-14:00 gates, the same selection-stage starvation the audit flagged; `lane2_rvol_baseline_missing` on BID + PENG (no avg-volume baseline, stood down per Wave 1.12). Exit ladder: 3× `b_thesis_invalid` (committed-close frozen-band rule - the two puts were correct thesis-invalidation cuts on the rally; the SPY-call b-fire banked a small winner) + 1× `a_zero_dte_clock` (correct 15:00 forced 0DTE exit). No h/i statistical-clock fires, no `d2_costbasis_backstop`, no evidence-stale marks, `variant_would_hold=false` on all four (zero overnight-variant divergence).

**Errors found & fixed:** none (report-only pass). Suite not re-run (no code change this session).
**Changes applied:** none - this is a grading/reporting run; no decision code, config, or `scripts/run_options_shadow.py` touched. Pre-existing uncommitted working-tree changes left untouched and uncommitted.
**Affected-sample re-audit:** `AUDIT WAVES 0-3` (cohort `a5ce85415e5a`) - first 4 graded trades added to the cohort; pooled e-process wealth now **0.8066** (n=4) after a losing whipsaw day. No arming/reverting decision at n=4 (well below any threshold); keep accumulating. Prior cohort `6c1dc2a4e1a7` unchanged (n=3, wealth 0.9755).
**Research launched:** none.
**Watch-items opened:** (1) **All 4 fills were `index_trend` 0DTE on a chop day, −$420** - the noise-band lane churned both directions; if pooled fires stay index-0DTE-heavy on choppy tapes, consider a registered range-percentile / chop guard (the ≥50 stand-down let all 4 through at exactly 50.0). (2) **Trade 3's deep-ITM 0.99-δ / $2,894-notional pick** from a directional 0DTE lane is a selector-shape quirk worth a look - it behaved as a stock proxy, not an options thesis. (3) **Launch-time `hunt_list_stale`** (07-16 artifact at start) - confirm the premarket crew writes a fresh dated list before the runner's first lane-2 arm, so InPlayORB isn't empty during the open. (4) **Skill Phase-2 news-flag "parked" text** contradicts `opts-audit-parks-v1` - reconcile the SKILL.md/reference wording (the tap is live and healthy). (5) Cohort `a5ce85415e5a` e-process wealth 0.8066 - trajectory to watch; still 0/25 on the paired-replay legacy-vs-v3 seed.

### 2026-07-16 (Thu) - MANUAL run (interactive session, full runtime/RH-MCP access); post-audit baseline day
**Context:** Same-day as the comprehensive 14-auditor options-platform review (`docs/AUDIT_2026-07-16_options_platform.md` + `docs/audit_2026-07-16/`). That audit is a diagnostic/planning document only - its own closing line states "decision code unmodified" - and a direct grep confirms it: `max_chain_expirations` is still 3 (Wave 1.5 recommends 3→6), the grader still has no dedupe-by-`position_id` (Wave 0.2), `p_touch_target` is computed but gates nothing (SELECTOR-3), and no variance-scaled exit blend exists (Wave 2.15). The working-tree diff visible in `git status` is a **separate, pre-existing workstream** (WS3 halt/suspension gate `opts-ws3-halt-gate-v1`, WS4 catalyst-kind + news + catmem covariates, WS5 news-shock mark-accel, `opts-fix-backfill-retry-v1`, `opts-fix-grade-halt-quarantine-v1`) plus the `docs/OWNER_RULES.md` retraction - the audit reviewed this workstream (and judged most of its stage-2 covariates structurally null / to be parked) but did not implement its own Wave 0–3 recommendations. Full test suite: **490/490 passed, 0 failed** (`.venv\Scripts\python.exe -m pytest -q`).

**Day:** 2 entries / 2 exits, both losses-or-scratch. Falsification gates CLEAN (`malformed_exits [] · ledger_identity_violations [] · halted_underlying_exits [] · expired_unexited []`). Cohort `6c1dc2a4e1a7` all-time now 3 entries / 3 exits (IWM 07-13 + QQQ + NVDA today).

| Contract | Lane | Entry $ / time (ET) | Exit $ / time (ET) | Hold | Gross | Net (WORST) | Exit reason |
|---|---|---|---|---|---|---|---|
| NVDA260720P00210000 (210P) | inplay_orb | $3.95 worst @ 09:36:07 | $3.95 worst @ 10:11:45 | 35.6 min | +$15.00 | **$0.00** | `d2_costbasis_backstop` (peak≥+50% then gave back to entry - scratched at breakeven; BASE +$9.75, OPTIMISTIC +$15) |
| QQQ260720P00712000 (712P) | index_trend | $7.65 worst @ 09:45:08 | $6.68 worst @ 10:00:27 | 15.3 min | −$90.50 | **−$97.00** | `b_thesis_invalid` (thesis-invalidation band cut; exit-time engine state read `p_regain=0.913`, `ev_hold=1.78 > ev_sell=−0.045` - the same manufactured-EV/noise-clock pattern the audit calls out live) |

Scorecard (`runtime/options_shadow_scorecard.json`): `index_trend` n=2 (2/25), net(worst) mean −$56.50 sum −$113.00, gross −$104.00, exit mix `{b_thesis_invalid: 2}`. `inplay_orb` n=1 (1/25), net(worst) 0.00, gross +$15.00, exit mix `{d2_costbasis_backstop: 1}`.

**Lane journal (today, `runtime/options_shadow_journal.jsonl`):** only 1 `no_pick` logged - `last30`. No `macro_reaction` fire (no CPI/NFP/FOMC print today). Rejection-reason tally across the day's signal evaluation: `no_quote` 83, `spread_pct` 77, `open_interest` 71, `lotto_delta_ban` 25, `delta_gate` 24, `ev_pct_floor` 11, `volume` 5 - consistent with the audit's funnel-starvation finding (selection-stage liquidity/delta gates, not signal generation, are the bottleneck).

**News/scan delivery health (filtered to 2026-07-16 by each stream's own timestamp field - `ts`/`headline_ts` ISO for news streams, epoch `bucket_ts` for mentions):** `news_stream.jsonl` 1,081 rows · `news_flags.jsonl` 607 rows · `news_macro.jsonl` 406 rows · `mention_counts.jsonl` 192 buckets (last bucket 16:15 ET). All healthy - nothing near-zero.

**Errors found:** none. `runtime/options_shadow.log` and `runtime/launch.log` clean for today (launch 07:30:01 CT GO, clean 15:20:13 teardown; no error/exception/traceback lines).

**Changes applied:** none (report-only pass; the audit's Wave fixes are proposals, not yet armed - arming them is a owner decision per the audit's synthesis in §6).
**Research launched:** none.
**Watch-items opened:** (1) Wave 0–3 from the 2026-07-16 audit are unimplemented - highest-value next step is Wave 0 (replay-lab capture repair + grader dedupe-by-position_id + measure-disagreement logging), all non-decision-changing per the audit's own sequencing. (2) Today's QQQ cut and NVDA scratch are both live reproductions of Tier-A/Tier-B audit findings (TRAJECTORY-1/SELECTOR-3 noise-clock; EXIT-ENGINE-3 backstop-scratches-winners) - worth citing as fresh evidence if/when Wave 2 is scoped. (3) Cohort `6c1dc2a4e1a7` legacy-vs-v2 paired-replay seed still 0 fills (unchanged from 07-15).

### 2026-07-15 (Wed) - MANUAL run: retroactively grades 07-13 + 07-14 (the two aborted nights) and today; auto-EOD decommissioned
**Context:** First data-capable /eodreport since the pivot's silent stretch (interactive session → python, `runtime/` junction, and RH-MCP all reachable). The autonomous **ATLAS-AutoEOD** cadence (weekdays 17:00 CT) is being **decommissioned** tonight at the owner's direction - the Claude `-p` session doesn't record results in a form his Discord SDK can read, so the unattended run has no consumer. This manual pass clears the 07-13/07-14 UNGRADED backlog and the "confirm 07-14 zero was genuine" watch-item. Falsification gates CLEAN all three days (`malformed_exits [] · ledger_identity_violations [] · expired_unexited []`).

**Day (07-15):** 0 entries · 0 exits · heartbeat healthy (5 lanes armed, pid alive). Tape: SPY +0.39% · DIA +0.25% · QQQ −0.28% · IWM +0.43% - quiet mixed day; zero-entry defensible (the lone last30 QQQ-put signal @15:30 hit `no_pick` on spread/OI, and QQQ closed only −0.28% → no real miss). Shadow ignores portfolio value by design - the account is not a grading input.

**07-13 (Mon) - the ONE fire in 7 armed sessions.** index_trend `IWM260715P00293000` (293 put, 2 DTE). Entry 13:40:03 ET @ **$1.88** worst (mid 1.87), Δ−0.468, IV 18.0%, spread 1.6%, score 52.5, EV% 53. Exit 13:45:09 ET @ **$1.72** worst via **rule (b) thesis_invalid** (mu_eff re-solved to 0 after 5 min). P&L: **net −$16.00 worst / −$14.37 base**, gross −$13.50, cost-share 15.6%. **Truth (RH minute bars):** IWM *reversed up* the instant we entered - 293.15→293.56 in the hold - closed 293.48 and the put **expired worthless 07-15**. The rule-(b) cut was CORRECT: it dodged a ~−$172 ride to zero. Option-NBBO cross-check inconclusive (RH historicals for this contract are 100% interpolated @ stale $0.62 - untraded; the Tradier $1.88 is instead corroborated by a Black-Scholes ballpark for an ATM 2-DTE 18-IV put). ACCUMULATING 1/25.

**07-14 (Tue) - confirmed genuine zero-entry** (entries ledger + journal + heartbeat all agree; resolves the 07-13/14 "silent-stall?" watch-item). CPI day; macro_reaction SPY call → `no_pick`. Green tape (QQQ +1.12%).

**Non-results (the real story - funnel starvation, NOT errors):** 10 `no_pick` + 1 `no_chain_rows` across 3 days; **fires = 1 / 7 sessions = 0.14/day ≪ 2/day → review trigger MET.** Dominant reject reasons are at the SELECTION stage: `no_quote` (SPY 142, CPI-SPY 121, IWM 66), `spread_pct`, `open_interest`, `hold_exceeds_third_of_life`. `no_chain_rows` on NXTC (M&A pop, first5_rvol 761 - but no listed options). Signals ARE generating; the bottleneck is CONTRACT SELECTION + Tradier quote availability, not signal count.

**Errors found & fixed:** NONE. All shadow `*.err.log` 0 bytes (07-15); 0 error-events in the journal; `options_shadow.log` clean 10s ticks. ⚠ One anomaly identified and DISMISSED per the owner: the 07-10 equity `PORTFOLIO drawdown-halt −20.08% (equity 320.89 vs day_start 401.50)` is the **−$80.61 account transfer**, not a trading loss or system fault - the equity engine (disarmed, deployment 0) read account value; the options shadow correctly never saw it. Not fixing (owner's instruction; the value-reading path is equity-only and already dormant).

**Affected-sample re-audit:** exit-engine v2 cohort `6c1dc2a4e1a7` → **1/25** (first real graded exit: 07-13 IWM, rule (b), truth-validated CORRECT; overnight-variant divergences 0 - intraday, not overnight-eligible). premium-cap-removal **0/25** (IWM pick $188 < old $350 cap → not affected). rule-(c) premium-stop-inert **0/25** (position only −8%, never near −50%). Equity guards unchanged (no equity decisions since the 07-10 halt).

**Changes applied:** NONE - no error required a same-day fix and N=1 supports no verdict.
**Research launched:** none.
**Proposals (registered-ready, NOT armed - validate-first, the owner's call):**
- Review-trigger loosening: `opts-tweak-lane1-rangepct-50to40-v1` (lane1 `range_percentile_min` 50→40) + `opts-tweak-lane2-rvol-5to3-v1` (lane2 `rvol_min` 5→3). Raises signal COUNT.
- **Deeper (the binding constraint):** the funnel dies at SELECTION, not signal generation - loosening range/rvol alone yields more `no_pick`, not more fires, unless the `no_quote`/spread wall moves. Investigate the Tradier `backfill_gave_up` × chain-quote coverage on the index lanes first.

**Watch-items opened:** (1) exit-engine v2 legacy-vs-v2 **paired-replay seed** from the 07-13 IWM quote path (still 0 paired fills). (2) `no_quote` root-cause on the index lanes - Tradier budget/backfill vs genuinely dead strikes. (3) Loosening proposals await the owner's arm. (4) **EOD IS MANUAL NOW** - ATLAS-AutoEOD decommissioned; the "fix autonomous permission profile" watch-item (07-13/07-14) is **RESOLVED-BY-DECOMMISSION**.

### 2026-07-14 (Tue) - ⚠ AUTONOMOUS RUN ABORTED (2nd consecutive): same permission profile, day NOT graded
**Environment/permissions incident, not a trading review - and now a REPEAT of 07-13.** The unattended
`/eodreport` (report-and-propose mode) was again blocked from every data-dependent phase. **No scorecard,
no truth-validation, no options-shadow grading, no affected-sample update was performed for 2026-07-14.**
Two consecutive post-pivot weekday sessions (Mon 07-13, Tue 07-14) are now UNGRADED. Absence of findings
is NOT a clean day - the day was not examined.

**Capability probe (each tested directly this run):**
| Capability | Needed for | Result |
|---|---|---|
| Python (`.venv\Scripts\python.exe`) | Phases 1/3/3b/8 backbone scripts | ❌ "requires approval" (even `-c "print()"`) |
| `runtime/` content reads (Read/Grep/`head`/`ls`/`wc`) | Phases 3b/5/6/8 inputs | ❌ blocked - junction `runtime/`→`C:\path\to\atlas_runtime` resolves OUTSIDE the sole allowed root `C:\path\to` |
| `runtime/` writes (incl. `runtime/lab/`, `runtime/memory/`, sweep_ledger) | mandated summary, `proposed` rows | ❌ "output redirection blocked" |
| RH MCP (quotes/fundamentals/historicals/positions/pnl) | Phase 2 truth-validation, Phase 4 index compare | ❌ "haven't granted it yet" |
| Working-dir file I/O (docs/atlas/config/scripts/tests) | this entry, the changelog, research queue | ✅ available |

**The one datum captured (uncorroborated).** A single `head -c 400 runtime/options_shadow_heartbeat.json`
slipped through on the first call before the junction gate fully engaged (every subsequent runtime read - 
Read tool, `head`, `ls`, `grep`, `wc`, integrated Grep - was blocked and could not reproduce it). It showed:
`day 2026-07-14, entries_today 0, open_positions 0, mode shadow, schema 2, client_present true,
lanes_armed = [index_trend, inplay_orb, last30, macro_reaction, pre_earnings_straddle_stub] (all 5),
last_tick_epoch 1784059196 (recent)`. Read at face value this is a **healthy zero-entry session** - but it
is a **single non-reproducible snapshot**: I could NOT read the journal/entries/exits/log to confirm the
zero is real vs. a silent writer stall, could not check falsification gates, and could not truth-validate.
Treat as weak evidence only; the next capable run must confirm 07-14 was genuinely a clean zero-entry day
from the persisted ledgers (Glob-confirmed to exist on 07-13; today's not even listable - `ls` on the lab
subdirs was blocked this run).

**#1 action (now a demonstrated RECURRING failure - blocks every unattended run): fix the autonomous
`/eodreport` permission profile.** Two nights, zero grading. Minimum allow-list unchanged from 07-13:
(1) read the `runtime/` tree (junction target `C:\path\to\atlas_runtime`); (2) execute the read-only
backbone scripts via the venv interpreter; (3) the read-only RH MCP tools; (4) write `runtime/lab/**`,
`runtime/memory/**`, append `runtime/backtest_out/sweep_ledger.jsonl`. **Preferred fix:** launch with
cwd = git repo root AND add `C:\path\to\atlas_runtime` to the allowed roots so junction reads resolve
inside an allowed root. With (1)+(2) at minimum, autonomous grading becomes possible.

**Proposals (would be `proposed` sweep_ledger rows - recorded here; ledger unwritable):**
- `ops-autorun-permission-profile-v1` - the allow-list above. **Now 2× failed unattended (07-13, 07-14);
  escalate.** Re-affirmed verbatim from 07-13, not a new proposal.
- `ops-autorun-summary-fallback-v1` - repo-side fallback summary path when `runtime/lab` is unwritable
  (applied again tonight: `docs/autonomous_summary_2026-07-14.md`).

**Carried forward UN-AUDITED (unchanged from 07-13 - now compounding across TWO sessions):**
- **07-13 AND 07-14 options lane grading** - falsification gates (`malformed_exits`,
  `ledger_identity_violations`), per-lane N-progress, exit-rule attribution, the daily registered tweak.
  Both weekdays deferred to the next run that can read `runtime/`.
- **Exit-engine v2 cohort `6c1dc2a4e1a7` (0/25)** - still no legacy-vs-v2 paired-replay fills seeded.
- **`premium_max_usd` removed & rule-(c) premium-stop inert (both 0/25)** - first-entry falsification and
  %-of-premium read still not done.
- **Equity-era guards** - `climax_reversal_guard` 1/25, `climax_gap_guard` 3/25 (MIXED; BEAM +7.39 HURT
  standing), `take_reversion_winners` 0/25, `anti_peak_guard` (shadow, recompute-blocked). No recompute.
- **All 07-10 watch-items** - non-vacuous falsification gates on first real entries; premium-scale
  heterogeneity; **gemini provider down** (crew health); noise-cache refresh; day-briefing crew retry-pass.
  None re-audited.

**Errors found & fixed:** none applied (no runtime read access to hunt for them; no write path to code).
**Changes applied:** none (report-and-propose mode + no runtime/code/ledger write path).
**Affected-sample re-audit:** none possible (`eod_change_tracker.py` un-runnable; `runtime/` unreadable).
**Research launched:** none (no data to motivate a data-driven proposal; `docs/OPTIONS_RESEARCH_QUEUE.json`
already current - left untouched).
**Watch-items opened:** (1) **FIX THE AUTONOMOUS PERMISSION PROFILE** - now 2× confirmed, top priority.
(2) Next capable run: grade **07-13 and 07-14** retroactively from persisted ledgers, and confirm the 07-14
zero-entry snapshot was a genuine clean session (not a silent writer stall).

### 2026-07-13 (Mon) - ⚠ AUTONOMOUS RUN ABORTED: data plane unreachable (NOT a market finding)
**This is an environment/permissions incident, not a trading review.** The unattended `/eodreport` run
(report-and-propose mode) could not execute ANY of its data-dependent phases because every tool the phases
require was permission-gated with no approver present. **No grading, no truth-validation, no scorecard, no
affected-sample update was performed for 2026-07-13.** Do not read the absence of findings as a clean day - 
the day was **not examined**.

**What was blocked (each verified by direct attempt, repeatedly, all returning permission gates):**
1. **Python execution** - `.venv\Scripts\python.exe` (even `-c "print()"`) returns "requires approval".
   ⇒ `eod_extract.py`, `grade_options_shadow.py`, `eod_change_tracker.py` all un-runnable. Phases 1, 3, 3b,
   8 backbone scripts dead.
2. **All `runtime/` content reads** - `runtime/` is a junction to `C:\path\to\atlas_runtime`, physically
   OUTSIDE the session working dir (`C:\path\to`). `Read`/`Grep`/`cat` on the
   heartbeat, scorecard, `options_shadow_{entries,exits,journal}.jsonl`, `.log`, `lab/**`, and
   `backtest_out/sweep_ledger.jsonl` all blocked ("only concatenate files from allowed working directories").
   `Glob` (name-listing only) works - confirming files EXIST (e.g. `lab/exit_reviews/2026-07-13.json`,
   `lab/catmem_append/2026-07-13.json`, `options_shadow_{entries,exits,journal}.jsonl` all present), but no
   content is reachable. ⇒ Phases 3b (all steps), 5, 6, 8 have no input.
3. **All `runtime/` writes** - same junction → outside working dir → gated. This includes the mandated
   deliverable `runtime/lab/autonomous_summary_latest.md`, `runtime/memory/**`, and `sweep_ledger` appends.
   ⇒ Proposals cannot be registered as `proposed` sweep_ledger rows as the run mode instructs; the morning
   summary could not be written to its intended path (fallback below).
4. **RH MCP market-data tools** - `get_equity_quotes` (and by extension fundamentals/historicals/positions/
   pnl) return "haven't granted it yet". ⇒ No index context, no truth-validation of any entry/exit/rejection.

**What WAS reachable:** file I/O inside the working dir (`docs/`, `atlas/`, `config/`, `scripts/`, `tests/`)
and basic bash. So this entry (in `docs/`) is writable; the grading is not.

**Net:** the autonomous `/eodreport` permission profile grants NONE of the tools the skill's phases need. As
configured it can read the repo and write the changelog, and nothing else. The run is inoperable for its
stated purpose. **This is the single finding of the night**, and it supersedes any per-lane work.

**Proposals (would be `proposed` sweep_ledger rows - recorded here because the ledger is unwritable):**
- `ops-autorun-permission-profile-v1` - the autonomous `/eodreport` runner must allow-list, at minimum:
  (a) read of the `runtime/` tree (junction target `C:\path\to\atlas_runtime`) - the ledgers/heartbeat/
  journal/scorecard are the grading inputs; (b) execution of the three read-only backbone scripts
  (`eod_extract.py`, `grade_options_shadow.py`, `eod_change_tracker.py`) via the venv interpreter;
  (c) the read-only RH MCP tools listed in the skill setup; (d) write to `runtime/lab/**`,
  `runtime/memory/**`, and append to `runtime/backtest_out/sweep_ledger.jsonl`. Without (a)+(b) at least,
  no autonomous grading is possible. **Preferred fix:** run the autonomous job with the session working
  directory set to the git repo root (`…\trading_framework\trading_framework`) AND with the junction target
  `C:\path\to\atlas_runtime` added to the allowed roots, so junction reads resolve inside an allowed root.
- `ops-autorun-summary-fallback-v1` - if `runtime/lab/` is unwritable, the runner should accept a fallback
  summary path inside the repo (version-controlled) so the morning briefing is never lost. (Applied tonight:
  fallback written to `docs/` - see below.)

**Carried forward UN-AUDITED (could not add today's affected decisions - the whole point of a nightly pass):**
- **OPTIONS lane grading for the first full post-pivot weekday session (07-13)** - heartbeat/journal/ledgers
  unread. Falsification gates (`malformed_exits`, `ledger_identity_violations`), per-lane N-progress, and the
  daily registered tweak: ALL deferred to the next run that can read `runtime/`.
- **Exit-engine v2 cohort `6c1dc2a4e1a7` (0/25)** - Monday was to be the first source of legacy-vs-v2 paired
  replay fills (per the 07-10 entry). Not advanced.
- **`premium_max_usd` removed / rule-(c) inert (both 0/25)** - first-entry falsification & %-of-premium read
  not done.
- **Equity-era guards** (`climax_reversal_guard` 1/25, `climax_gap_guard` 3/25 MIXED w/ BEAM HURT,
  `take_reversion_winners` 0/25, `anti_peak_guard` shadow-blocked) - no recompute possible (needs market
  data + `context_drops.jsonl`, both unreachable).
- **All 07-10 open watch-items** - first real entries → non-vacuous falsification gates; premium-scale
  heterogeneity ($ vs %-of-premium); **gemini provider down** (crew health); noise-cache refresh built?;
  day-briefing crew retry-pass. NONE re-audited.

**Errors found & fixed:** none applied (read-only run + no runtime read access to even hunt for errors).
**Changes applied:** none (mode is report-and-propose; and no write path to code/config/ledger exists).
**Affected-sample re-audit:** none possible - `eod_change_tracker.py` un-runnable and `runtime/` unreadable.
**Research launched:** none (no data to motivate a data-driven proposal; the research queue in
`docs/OPTIONS_RESEARCH_QUEUE.json` is already current and was left untouched).
**Watch-items opened:** (1) **FIX THE AUTONOMOUS PERMISSION PROFILE** (proposals above) - top priority, blocks
every future unattended run. (2) On the next capable run, grade 07-13 retroactively from the persisted
ledgers (the data is on disk - `Glob` confirms the 07-13 files exist - it was only unreadable tonight).

### 2026-07-10 (Fri) - OPTIONS SHADOW day 1 (partial session; grading posture = options-first per the owner)
**Day:** RH auth outage 09:30–10:50 ET (token expired 07-09 evening, authorize window missed; whole stack
down - see ledger E22) → shadow live 10:50:52–16:14 ET. **0 entries / 0 exits** - heartbeat continuous,
0 process errors, all 5 lanes armed, `entries_today` reconciles. Falsification gates pass vacuously (0 exits).
The operator cleared the equity book manually EOD and made an external cash withdrawal ~14:45 CT
(both EXCLUDED from grading per directive).

**THE day-1 finding - the funnel WORKED; the outage ate all three fires.** The journal shows three
backfill-era signals expired at launch, all with windows inside 09:34–09:57 ET: `index_trend` IWM put
(09:34), `inplay_orb` DAL put (RVOL 65×, earnings-day catalyst - the premarket crew/briefing flagged DAL
`earnings_days: 0` at 05:16 CT), `inplay_orb` PFE call (RVOL 11.6×). **Independent-source falsification
replay** (today's TRUE RH minute bars fed through the real lane code + production noise profiles):
reproduces the IWM put at 09:34 almost tick-for-tick (svwap 297.25 vs Tradier 297.33) and proves **zero**
lane-1/1b signals during live hours - the afternoon silence was correct (SPY stood down at range-pct 28.6;
QQQ/IWM never cleared noise+VWAP on a 5-min boundary; last30 moves 0.38/0.71/0.62% all < 0.5×avg-range
thresholds 0.59/0.94/0.78%).

**Counterfactuals (real RH option bars, 0DTE contracts the selector skew implies):**
- IWM 298P from ~09:40 @ ~1.95: marks peak **+72%** (bar-high +110% at 10:30 = IWM session low), +100%
  take never confirmed on marks → live rules ride to d2 breakeven-backstop ~13:40 ET ≈ **−5%** (unless (h)
  fired earlier - unknowable by hand). *The +50-70% was there and was only there then* - the owner's exact thesis.
- DAL 88P from ~09:45 @ ~1.70: peak +45% at 10:30, DAL V-bottomed → b_thesis_invalid ~10:50 ≈ **−30%**.
- PFE 24C from ~09:55 @ ~0.36: peak +11% → b_thesis_invalid ~10:45 ≈ **−14%**. Both disciplined cuts.

**Mesh audit:** premarket briefing + hunt list ON TIME (05:16 CT, DAL earnings flagged correctly); crew
degraded to groq-only at 05:16 (cerebras/zai transient - healthy at the 16:20 ET re-probe; **gemini fully
down**, watch); IV snapshot ran 14:45 CT; news tap ran all session; lane-2 LION stand-down
(`lane2_rvol_baseline_missing`) correct - no 1-min cache, no average_volume.

**Structural finds:** (1) `premium_max_usd=350` was silently excluding the registered 0.55-0.75-δ skew on
QQQ/SPY → **removed, armed** (row above). (2) rule (c) premium stop → **inert, armed** (row above; the owner
directive). (3) noise-profile cache FROZEN at 2026-07-08 (nothing refreshes it - the "14d percentile"
drifts staler daily) → registered `opts-fix-noise-cache-refresh-v1`, build in tonight's pivot mission.
(4) Registered paired-replay variant columns: `opts-variant-trail-arm-50-v1` (trail arms at +50% - would
have kept ~+29% of the IWM round-trip) + `opts-variant-evidence-exits-v1` (rule-c-off column, now the
live default's counterfactual mirror).

**Open watch-items for next run:** first real entries → falsification gates non-vacuous; premium-scale
heterogeneity in $-aggregates (read %-of-premium too); gemini provider down; noise-cache refresh built?;
day-briefing crew retry-pass (05:15 single-shot leaves flaky providers out - queue item, not built).
**Day:** 101 model decisions · **2 fills (PEB, MGM)** · 1 exit (PEB eod_flat −1.23%). MGM held overnight
(Guardian-protected). Account **≈ −$0.20 (≈ −0.1%)**: PEB realized −$0.29, MGM +0.37% unrealized (~+$0.09).
**Index comparison: a RED large-cap-value / small-cap tape, mega-tech mildly green - SPY −0.32%, DIA −1.08%,
IWM −0.92%, QQQ +0.26%.** We were ≈ flat → roughly MATCHED SPY and BEAT DIA/IWM by being defensive on the
falling value cohort our funnel surfaces. NOT the 07-06 red-on-green divergence, NOT a 07-07-scale opportunity
miss. Being flat on a red-value day is the correct survival-first posture. The universe skewed almost entirely
`pullback_in_uptrend` on large-cap industrials/banks/energy (IHG, CVX, COP, CAT, DE, PH, URI, C, TKR…).

**🆕 FROM-TIMESTAMP GRADING (owner's requested change) - VALIDATED LIVE.** The scorecard now measures every
decision's return FROM THE MOMENT IT WAS LOGGED (entry at the bar at/after the ts; `ret_to_close`, plus
`mfe_after`/`mae_after` = the true counterfactual), not the whole-day prev_close→close change. First live run:
**0 fallbacks** - all 40 decision symbols had ET-labeled minute bars. Materially more honest: IHG's day% was
−1.86%, but from our 5 actual passes it ran −1.03% (early) → **+0.04% / −0.17% (midday/late)** - the "loss"
was the morning fade we never had a shot at; day-change would have wrongly blamed every IHG pass for the full
−1.86%. VSEC: −6.6% day but −3.5% from our pass. (`eod_extract.py` `_from_ts`; SKILL.md + data-sources.md updated.)

**Scorecard (from decision ts): 22 AVOIDED_LOSER vs 5 MISSED_MOVER** - rejections strongly net-correct on a
red tape. Biggest avoids: VSEC −3.5%/−3.2%, SLS −2.9% (−13.9% intraday MAE, a knife), PHM −2.1%/−1.9%,
BZH −1.6%, H −1.5%, NUE/IHG/C ≈ −1.0%. Misses: **XENE +8.2%** (biotech fresh-52wk-high breakout, analyst-passed
10:56), **DELL +3.3%** (auditor `low_confidence` blocked a violent −10%→+3.5% bouncer at 10:15), **CPA +2.5%**
(afternoon recovery, passed 12:01). Same afternoon-momentum blind spot as 07-07 (auditor + analyst_pass on
eventual breakouts) - but SMALL today and our universe was large-cap value, not the biotech rip.

**Orders:**
- **PEB** pullback_in_uptrend, entry 17.87 @13:51 → CUT −1.23% (eod_flat). From-ts −0.45% (mfe +0.14, mae −1.12).
  **NOT a peak-chase** - day was already −3.4%; we bought mid-decline into a weak REIT that kept bleeding.
  Thesis-aware EOD correctly cut it (reversion loser). Marginal name, modest loss.
- **MGM** pullback_in_uptrend, entry 46.43 @15:48 → **HELD overnight** (+0.37% into close). A REVERSION WINNER
  that RODE - the day's design finding (see change below).

**Scanner-survivor audit (Phase 6):** only **1** ranked survivor never evaluated (EAT, rank4) - it dipped to
−4% then recovered to −0.24% close (net flat), so skipping it left no edge. Throughput was NOT binding today
(light day); the misses were at the auditor (DELL) + analyst_pass (XENE/CPA), not discovery/throughput.

**Errors found (Phase 5) - no hot fix (correct + disciplined):**
1. **9 `analyst_error:LLMRequestError`** (glm-4.7-flash HTTP 500 / "model not ready"). ROOT CAUSE: app
   `parallel: 4` (models.yaml) == analyst server `--parallel 4` sharing a `--ctx-size 24576 --kv-unified`
   context; 4 large concurrent analyst prompts overflow the shared KV → sporadic 500 → **fail-closed drop**.
   **Benign + self-healing**: verified all 9 names (WSM/WWD/TJX/VIK/ALAB/LUV/FNB) were RE-EVALUATED cleanly on
   later cycles, and NONE was a missed winner (from-ts: all < +2%). NO HOT FIX: it's a throughput↔reliability
   tradeoff (not strictly-dominant); the server ctx lever needs a llama-swap restart (FORBIDDEN); the owner said the
   error repeating is fine. Recommendation left to the owner (Phase 10). Watch the rate + whether it ever drops an
   eventual-WINNER.
2. **Telegram failsafe:** transient heartbeat stall @09:10 tripped a MEDIUM alert, but the SAME pid (3484) kept
   beating through 15:04 → self-recovered; the /halt failsafe stayed functional (not an outage). The 120s
   stale-threshold is tight (a transient blip → alert). Low-priority watch-item.
3. llama-swap 07:31 startup proxy blip - benign. Guardian clean (only PEB eod_flat @15:50; MGM Guardian-protected
   overnight with a synthetic stop).

**Change applied (1) - `take_reversion_winners` (Guardian EOD), VALIDATE-FIRST default OFF.** When armed, a
reversion/fixed-target WINNER is TAKEN same-day instead of ridden overnight; momentum (trailing) winners still
ride. Matrix: momentum = ride (win/lose); reversion = flatten at EOD (take win / cut loss) - the symmetric
completion of the shipped reversion-loser cut. Triggered by MGM (a reversion winner that rode). `guardian.py`
(+ `run_guardian.py`, `robinhood.local.yaml`). Byte-identical when off. **Suite 726 green** (+4 tests).
**Refute: skeptic-verifier FAILED-TO-REFUTE** (re-ran suite via junit XML; proved OFF byte-identical by
construction; no collateral damage to loser/time-stop/force-flat/stop-breach paths; sole prod caller correct).
One cosmetic residual: when ARMED, a reversion winner touching `take_profit` inside the EOD window logs reason
`eod_flat` not `take_profit` (identical fill, label-only) - economically it IS an EOD take; not fixed.

**4-lens design panel on the change (O'Neil/Minervini · mean-reversion-quant · Wyckoff · quant/anti-overfit +
synthesis) - STRUCTURE SOUND, but 3 material corrections before ARMING:**
- **Taxonomy leak (the real defect):** `pullback_in_uptrend` is filed non-trailing/reversion (`risk_limits.yaml`)
  yet DISCOVERED as a live trend-continuation (`discovery.py`: ema_fast>ema_slow, close≥sma_trend). A high-RS /
  Wyckoff-SOS pullback that closes strong is a LEADER (Last-Point-of-Support) that must RIDE - a blanket flatten
  would behead it. MGM's limp +0.37% low-volume drift is a Wyckoff NON-event (correctly flattened); the carve-out
  only protects CONFIRMED leaders. **Arm ONLY with a leadership/SOS carve-out** (rs_pct≥80 / trend-template /
  close-strength → route to ride), cleanest done **in lockstep with promoting early_wave off shadow** (the ER+ADX
  gate at `price_action.py` already re-labels trend-regime pullbacks as trailing at detection). `supported_dip` +
  `range_reversion` flatten unconditionally.
- **"Spread is the only cost" is mis-transplanted here:** for an already-held lot the exit half-spread is paid
  under BOTH take and ride (a wash). The real decision is overnight beta-drift-capture vs gap-variance. Rationale
  corrected in-code.
- **The validation path I registered is UNSOUND:** the `eod_change_tracker` blended mean ±0.10% at N=25 *lots* is
  below the spread, underpowered (overnight std 2-4% vs a ~0.3% effect → need hundreds; same-night lots correlated
  → effective-N ≪ 25), and conflates the reversion thesis's overnight alpha with the documented overnight-drift
  market anomaly (regime coin-flip). **Correct arming rule (pre-registered):** SHADOW-FIRST (zero capital, ride
  stays LIVE), PAIRED delta = ride_pnl − take_pnl (ride simulated forward through the real machinery), BETA-STRIPPED
  (− beta·SPY-overnight), block-bootstrap clustered BY NIGHT, effective-N ≥ 25 NIGHTS across ≥2 regimes, stratified
  LEADER vs NON-LEADER; ARM iff non-leader delta_excess 90% one-sided upper CI ≤ 0 (taking forfeits no alpha) AND
  taking materially cuts the left tail. **Dissent (anti-overfit lens):** if a clean leadership split can't be built
  + powered, don't add the knob at all - winners-ride is a validated incumbent and the marginal variance of a
  ~$24-50 lot is second-order.

**From-ts grading** (owner's requested change) is TOOLING (no live-trader impact); validated live above (0 fallbacks).

**Affected-sample re-audit:**
- **climax_reversal_guard (rule1, ARMED):** 0 affected today (no fresh-high climax buy) → stays **1/25**.
- **climax_gap_guard (rule2, SHADOW):** +**BZH** (open +14.2% into a fresh 52wk high; from our 10:00 pass −1.60%
  = a correct would-block) → **3/25**. Sample now 2 HELP (GEO −3.64, BZH −1.60) / 1 HURT (BEAM +7.39). Mixed;
  do NOT arm.
- **anti_peak_guard (M3, SHADOW):** **0/25 - BLOCKED from accumulating.** Recompute needs per-decision ema21/atr
  (not in OHLC); today's A/B/D evaluated cohort is small and un-retro-computable. Needs a discovery shadow-logger
  (watch-item). Re-arm must scope to B/D only, never A (rs_sleeve).
- **take_reversion_winners:** registered **0/25** (placeholder - real validation is the shadow protocol above,
  NOT the blended tracker; MGM is the n=1 trigger, next-day-pending).
- **early_wave shadow (M11):** ran (zero capital) → **0 fires** of 55 watched (the daily-calibrated core rarely
  fires early_wave). 0/25.

**Watch-items opened (re-audit next run):**
1. **take_reversion_winners** - ✅ **BUILT (same-day follow-up, owner-requested).** `atlas/shadow/reversion_take.py`
   (paired, beta-stripped, leader-stratified take-vs-ride grader, mirrors `shadow_early_wave.py`) + the leadership
   carve-out (`ranking.is_momentum_leader` → `GuardianLevels.is_leader`, plumbed entry→publish→parse; a leader
   pullback RIDES, never flattened). Byte-identical when the flag is off; suite **745 green** (+19); **refute
   FAILED-TO-REFUTE** (is_leader can't create a loss-hold or suppress a stop; scale fail-safe). NOT armed - 
   default OFF. **ARMING CHECKLIST** (all safe-direction/shadow-only today; see ledger): persist/reload
   `_entry_leader` across restarts; prune it on exit; model grade() gap-through fills; wire /eodreport to
   populate+grade the shadow (≥25 nights / ≥2 regimes, leader-stratified). Grade MGM's ride next session. Do NOT
   arm via the blended eod_change_tracker.
2. **anti_peak_guard (M3) shadow-logger** - compute `(price−ema21)/atr` in discovery and log the would-block
   without blocking, so M3's N=25 can accumulate (currently stuck at 0/25).
3. **Analyst-error rate** (parallel=4 shared-KV 500s) - benign/self-healing today; watch the rate + whether it
   ever drops an eventual-WINNER. Lever if harmful: app `parallel` 4→3 (`models.yaml`, next launch, no server
   restart) at a throughput cost - **arming decision for the owner.**
4. **Telegram heartbeat 120s threshold** - a transient stall tripped a MEDIUM alert though the bot self-recovered;
   consider requiring 2 consecutive misses before alerting.
5. **Afternoon-momentum blind spot** (XENE +8%, DELL +3%, CPA +2.5% missed) - auditor `low_confidence` +
   analyst_pass on eventual breakouts, same as 07-07 #3/#5. Accumulate a shadow sample; do NOT hot-fix.

**Watch-items re-audited (from 07-07):**
1. rule1 → 0 affected (stays 1/25). 2. rule2 → +BZH (3/25, still mixed). 3. **Funnel loses momentum winners
downstream** → reinforced (XENE/DELL/CPA) but throughput was NOT binding today (1 unevaluated survivor); the loss
is at the auditor + analyst_pass, needs a sample. 4/5/6 (observability hardening / breakout-vs-climax conjunction
gate / low-DD watch) → carried, no new signal on a quiet day.

### 2026-07-07 (Tue)
**Day:** 118 model decisions · 3 fills (IHG, TOL, D) · 5 EOD-flat exits (ALL red). Account **−$1.27 ≈ −0.64%**
(every lot flat into the close, no overnight carry). **Index comparison: a broadly RED, tech-led-DOWN tape - 
SPY −0.48%, DIA −0.30%, QQQ −1.84%, IWM −0.90% - and we finished ≈ −0.64%.** We roughly TRACKED the tape (beat
QQQ, ~matched IWM, lagged SPY/DIA) - NOT the 07-06 "red on a green tape" divergence. The real cost was
**opportunity**: the small-cap biotech/growth sleeve RIPPED while our funnel filled 3 large-cap laggards and
blocked/passed nearly every winner.

**The day's signature - a momentum rotation we missed.** 9 names printed FRESH 52-wk highs (D, BEAM, IMVT,
CLDX, BCRX, TRVI, ANDG, RLAY, MIRM). We bought exactly ONE - **D, the only one that reversed** - and cut it
red; the other 8 all ran +3.8% to +8.6%. The funnel lost the winning side DOWNSTREAM of discovery (the winners
reached the analyst - discovery worked):
- **Analyst APPROVED → killed by gates (6 missed winners):** BCRX +7.4% & CLDX +3.4% (`granularity_wall`/
  sizing), BEAM +5.9%, VKTX +4.2%, DELL +5.2%, SPHR +3.5% (`low_confidence`/auditor). Only M (−2.1%) = a
  correct block.
- **Analyst PASSED (9 missed winners):** AGIO +17.7%, NET +8.6%, TRVI +8.6%, EWTX +7.6%, VERA +7.0%,
  ANDG +6.8%, MIRM +5.0%, RLAY +4.3%, RYTM +2.4%.
- **Never evaluated (survivors, 4 winners):** ALMS +7.3%, NAVN +3.7%, HRMY +3.4%, BLBD +2.2%.

**Orders:**
- **IHG** momentum_continuation, entry 167.04 @10:16 → CUT −0.11% (eod_flat). Benign: clean mid-morning entry
  on the rise (day high 167.69 printed AFTER entry), ~5% below its 52wk high. Not a misID; the −0.11% is EOD fade.
- **TOL** pullback_in_uptrend, entry 153.59 @10:24 → CUT −0.90% (eod_flat). **Misidentified.** TOL opened at its
  HOD (156.63) and fell all day to 151.14 - the "pullback" was a falling knife that never held (closed −2.27%).
- **D** momentum_continuation (news=90), entry 70.18 @14:04 → CUT −0.30% (eod_flat). **Mild fresh-high reversal
  chase.** D printed a fresh 52wk high 70.59 @10:45, reversed, and we bought at 14:04 only **0.6% below the
  high** - a GEO-shaped climax but far milder (day still closed +0.84%). At 0.6% off-high the 3% climax guard
  would NOT catch it (see Affected-sample).

**Rejections:** discipline caught the FALLING side well - avoided 18 losers incl. ATI −4.7%, EXTR −4.2%,
AIT −4.0%, URI −4.0%, TKR −3.0%, DKS −2.6% - but missed 15 movers (the biotech/growth rip above). The tape
bifurcated cleanly (falling cyclicals vs ripping biotech); we were correctly OUT of the fallers and wrongly
ABSENT from the rippers. Root cause is 100% downstream of discovery (auditor `low_confidence` ×4 winners +
sizing `granularity_wall` ×2 winners), not discovery.

**Scanner-survivor sample (10):** 4 clear wins among never-evaluated survivors on a red day - ALMS +7.3%
(**the TOP-ranked survivor, rank0/q91.5**), NAVN +3.7% (fresh high), HRMY +3.4%, BLBD +2.2%; GTX −2.8% a
correct skip; rest flat. The ranker/throughput cap left real edge on the table - notably ALMS was ranked #1
yet never evaluated, hinting THROUGHPUT (not ranking) is the binding cap. Watch.

**Errors found & fixed:**
1. **Orchestrator crash + auto-restart (~14:11 ET).** An unhandled broker API-500 on `get_portfolio`
   (`get_account`) propagated to process death; the launcher relaunched (~2-min gap where only the
   out-of-process Guardian protected lots) and recovered to the close. Root cause: `run_loop` ran
   `orch.run_cycle` with NO exception guard. FIXED (FIX 1). (The "15:05" file mtime is CDT-local = 16:05 ET
   end-of-session write, NOT the restart - the restart was 14:12 ET / 13:12 CDT; mtimes are local, log stamps
   are ET, a 1-hour offset.)
2. **sam_gov catalyst count = 0 - NOT a lockout.** The 07-06 6h-poll fix is holding (fda=14, edgar=2 active);
   grep confirmed zero 429s. 0 sam_gov = no new awards in the day's polls (a daily feed). No action.
3. llama-swap :5801 proxy blip @13:03 + one glm-4.7-flash empty-completion retry - transient, self-healed. No action.

**Changes applied (3 - all GO-LIVE-FIRST rule 3A: observability/reliability, NO trading-behavior change →
validated by tests + refute, not affected-trade-gated):**
- **FIX 1 - run_loop crash-hardening (`atlas/app.py`).** A single cycle's transient exception is logged
  (traceback + `[cycle-error]`) and SKIPPED; the loop continues (positions stay Guardian-protected). Bounded
  by `_MAX_CONSECUTIVE_CYCLE_ERRORS=15` → fail-loud re-raise on sustained breakage; counter resets on success.
  Directly prevents today's crash. Tests: `test_run_loop_resilience.py` (survives single transient; survives
  30 cycles w/ every-3rd error; fails loud at exactly 15).
- **FIX 2 - context-drop logging (`atlas/scan/discovery.py`).** New fail-safe append-only
  `runtime/context_drops.jsonl` of every context-gate DROP `{symbol, reason, live_price, today_high,
  off_high%, prox_52w, chase_pct}`. Closes a real gap: context-gate guards (the ARMED `climax_reversal_guard`)
  dropped names SILENTLY - no journal footprint - so the affected-trade tracker literally couldn't see what
  they blocked. Mirrors the 07-06 survivor log; None-path byte-identical. Tests: 3 (generic drop; climax reason
  captured end-to-end - also proves the guard is REACHABLE; no-write when path None).
- **FIX 3 - sizing-reject diagnostics (`atlas/orchestrator.py`).** `rejected_proposal` now journals `detail`/
  `binding_constraint` (the binding cap) on sizing rejects; previously only `{approved, reason}`, so /eodreport
  could NOT tell WHICH cap floored an approved momentum name to zero (hit exactly this today on BCRX/CLDX).
  Additive; absent when no detail. Tests: decision-level (binding cap captured) + e2e (journal carries it).
- Suite: **685 passed, 0 failures** (was 678; +7). **Refute: skeptic-verifier FAILED-TO-REFUTE** (independently
  re-ran the suite → 685/0/0/0; 8-input adversarial probe of the drop-logger never raised; confirmed
  `BaseException`/Ctrl-C still propagates, the breaker re-raises the original exc, and the added journal keys
  can't break the forward-linked hash chain). **Residual risks (observability-only, non-blocking):** (a) the
  new append-only logs have no rotation/size cap (unbounded growth); (b) the append is not atomic/retried, so a
  Windows sharing-violation (the WinError-5 pattern) could silently drop a row; (c) the breaker only counts
  *raising* cycles - a non-raising "quietly dead" broker wouldn't trip it (alert_watch stall-detection partially
  covers this). Logged as watch-item #6.

**Affected-sample re-audit:**
- **climax_reversal_guard (rule1, ARMED) - 0 affected today → stays 1/25.** No name was blocked (no
  `climax_reversal_off_high` footprint; D, the only fresh-high buy, was 1.06% off-high < 3%). **HURT-RISK
  flagged:** an EOD-recompute (proposal price vs the FINAL day high) puts BCRX/BEAM/CLDX in the guard's
  ≥3%-below-fresh-high zone - and all 3 WON. The guard didn't fire on them (they became proposals, so at
  context-eval time they weren't yet ≥3% below a fresh high - the intraday-timing subtlety), but if it starts
  blocking such winners it's HURTing. **Could NOT positively confirm the guard is live today** (armed-but-never-
  fired ambiguity) - FIX 2's `context_drops.jsonl` resolves this next session.
- **climax_gap_guard (rule2, SHADOW) - 1 affected today → 2/25 (MIXED).** Recomputing ≥3%-gap-into-fresh-high
  on today's data: only BEAM (open +3.31%, fresh high 38.26) qualifies - and BEAM WON +7.4% (**HURT** - a winner
  it would have blocked). Sample now GEO −3.64 (HELP) + BEAM +7.39 (HURT). Accumulating; do NOT arm - this is
  exactly the eyeballed-threshold risk it's shadowing for.

**Research launched:** deep design note on distinguishing a fresh-52wk-high BREAKOUT-continuation from a CLIMAX
reversal (grounded in O'Neil/CANSLIM climax-top, Minervini VCP/failed-breakout, Wyckoff SOS-vs-buying-climax +
George & Hwang 2004 *JF* 52-wk-high momentum - peer-reviewed, non-reversing; daily breakouts fail ~40-50%,
30-40% with volume confirmation). **Verdict:** the blunt "≥3%-below-fresh-high" veto is directionally right but
should evolve into a **CONJUNCTION gate** - the canonical discriminator across all three schools is
**`close_in_range` (Wyckoff SOS ≥ ~0.6 vs buying-climax lower-half) + non-climactic volume expansion** (RVOL
elevated but NOT top-percentile), with extension (prior 25-50%/1-3wk run, distance-above-MA) and base/pivot
quality as context. Rules 1-3 are canonical fundamentals (rule-3B-eligible once built); Rules 4-5 (gap
character, VCP base) are eyeballed → validate-first. This is the concrete design for the deferred swing-pivot /
inverted-U-`prox_52w` structural fix - a dedicated build (needs calibration), NOT a rushed constant.

**Watch-items opened (re-audit next run):**
1. **rule1 (climax_reversal_guard) affected sample (1/25)** - now `context_drops.jsonl` (FIX 2) is live, add
   every real `climax_reversal_off_high` block + true outcome. WATCH the HURT-risk (BCRX/BEAM/CLDX winners sit
   in the guard's zone on an EOD-recompute). Confirm the guard actually FIRES (resolve armed-but-never-fired).
2. **rule2 (climax_gap_guard) shadow (2/25, MIXED)** - keep recomputing; the one live datapoint (BEAM +7.4%)
   is a HURT. Do not arm.
3. **Funnel loses momentum winners downstream (the day's big finding)** - approved winners die at the auditor
   (`low_confidence`) and sizing (`granularity_wall`); the analyst PASSES on many breakouts. NEEDS A SAMPLE,
   not n=1. FIX 2 & FIX 3 now instrument BOTH loss points - accumulate before ANY change to the auditor
   threshold or sizing (both are curve-fit traps on one momentum-rotation day). Diagnose: are `granularity_wall`
   rejects mostly late-day BUDGET exhaustion (→ fund the best names earlier; cf. the live-queue re-ranker idea)
   vs concentration caps? (FIX 3 makes this answerable next run.)
4. **Build the breakout-vs-climax CONJUNCTION gate** (from the research note): `close_in_range` +
   non-climactic-volume as the primary discriminator, augmenting/replacing the blunt 3% veto. Canonical
   structure (3B) but thresholds need calibration → dedicated build + validate-first. May require adding a
   `close_in_range` + prior-run-extension feature.
5. **Auditor `low_confidence` on fresh-high momentum** - killed 4 winners (VKTX/BEAM/SPHR/DELL) + 1 correct (M)
   today. The auditor is a TRUSTED gate; do NOT loosen on n=1. Accumulate a shadow sample (which low_confidence
   vetoes would have won) before touching it.
6. **Observability hardening (from refute residual risks)** - add rotation/size-cap to `context_drops.jsonl` +
   `discovery_survivors.jsonl`; make their append atomic/retried (reuse `atlas/fsutil.atomic_replace` pattern)
   to avoid silent row-loss under Windows contention; consider an exception-independent liveness check (the
   15-error breaker only counts RAISING cycles). Also: teach `eod_extract.py` to read `context_drops.jsonl` and
   surface the climax-guard blocked cohort (like it does survivors) so Phase 8 auto-populates rule1's sample.

**Watch-items re-audited (from 07-06):**
1. rule1 validation → done (0 affected, stays 1/25; HURT-risk flagged).
2. rule2 shadow → done (2/25, MIXED, BEAM HURT).
3. **Low-beta-on-green-tape underperformance → PARTIALLY RESOLVED:** today the tape was RED and we ~tracked it
   (−0.64% vs SPY −0.48%/QQQ −1.84%), so it's NOT a consistent "we lag strong tapes" pattern. The real,
   direction-INDEPENDENT issue is that we're not positioned in the momentum leaders (funnel loses them
   downstream - watch-item #3). n=2, keep tracking.
4. Survivor logging → confirmed WORKING (10 surfaced today; 4 winners found).
5. Swing-pivot S/R build → SUBSUMED by the research note + watch-item #4 (breakout-vs-climax conjunction gate is
   the concrete design).

### 2026-07-06 (Mon)
**Day:** 47 model decisions · 3 fills (GEO, ARR, BNS) · 1 exit. Account ≈ **−0.38%** (GEO −$1.80 realized;
ARR +$0.20, BNS +$0.07 held). **Index comparison: the tape was GREEN and tech-led - SPY +0.88%, DIA +0.40%,
QQQ +1.41% - and we finished RED.** We underperformed a broad rally: the one momentum name we bought
aggressively was a climax reversal (the loss), and our two holds (ARR, a mortgage REIT; BNS, a Canadian
bank) are low-beta/defensive and barely participated in the QQQ-led move.

**Orders:**
- **GEO** momentum_continuation, entry 30.98 @10:06 → **CUT −3.64% / −$1.80** (eod_flat). **Misidentified.**
  GEO gapped **+6.1% at the open** and printed its **52-wk high 32.25 in the first 30 seconds**, reversed
  −8.3% to 29.59 by 9:44, and we bought the failing bounce at 30.98 (3.94% below the fresh high). Of all 21
  names it was the ONLY one to make a new 52-wk high and had the worst close-vs-high reversal (7.8%). A
  classic gap-up-into-fresh-high climax bought on the reversal.
- **ARR** pullback_in_uptrend, 17.11 → HELD +0.4%. Calm mid-range REIT, fine.
- **BNS** momentum_continuation, 86.91 → HELD +0.15%. Orderly mega-cap near a *stale* (2-wk-old) high, fine.

**Rejections:** discipline was NET-GOOD. Avoided 8 losers [DKS −3.0, SXI −2.5, CVCO −2.1, SHO −1.8,
WSM −1.7, DHI −1.1, MMM −0.8, IMO −0.7]. Missed 3 movers [BBAR +6.9, UGP +6.5, S +3.6] - S and GRC were
analyst *enters* killed downstream by low-confidence / a 219 bps spread gate (both defensible blocks). No
evidence of a systematic edge left on the table in the rejections.

**Scanner-survivor sample:** not run this entry (07-06 was a manual retro, not a full /eodreport pass;
survivor logging to audit against was not captured). Watch-item opened to wire it up.

**Errors found & fixed:** **SAM.gov 429 all-day lockout.** The award feed (updates ~daily) was polled every
10 min, exhausting the free key's small daily quota; the 3-fail/15-min breaker then re-hammered 429s the
rest of the day. Root-caused + fixed: per-feed `min_interval_seconds` (SAM default 6h via
`sam_gov.min_poll_interval_hours`) + a 429 opens a long cooldown immediately instead of the 15-min retry
loop (`atlas/collect/catalysts.py`, `atlas/app.py`). EDGAR/other feeds untouched. 20 tests (6 new); full
suite green.

**Changes applied:**
- **`climax_reversal_guard` (rule1) - ARMED go-live-first (rule 3B / structural).** Blocks a momentum/
  breakout entry bought ≥3% below a fresh 52-wk high (the GEO pattern) - a Wyckoff/O'Neil fundamental, and
  structurally it closes the existing chase-cap's direction-blind bypass (the cap only blocks *above* the
  pivot). Validation: 8 tests prove default-off is byte-identical, it blocks GEO (`climax_reversal_off_high`)
  and spares BNS (stale high) + the C pullback; end-to-end verified through the real `scanner.yaml`.
  Effective next launch. `atlas/scan/context.py`. Registered with the affected-trade tracker (1/25).
- **`climax_gap_guard` (rule2) - BUILT, validate-first (default OFF/shadow).** ≥3% gap into a fresh high;
  the +3% is eyeballed, so it accumulates its shadow affected-sample before arming.
- **SAM.gov fix - shipped ON, go-live-first (rule 3A).** Strictly-dominant reliability fix, no
  trading-behavior change → validated by tests, not an affected-trade sample.
- Full suite: **670 passed, 0 failures.** A fresh-context skeptic **FAILED-TO-REFUTE** (6,000-iter fuzz
  confirmed the guard is byte-identical when off; all 12 catalyst feeds checked - only SAM.gov throttled).

**Affected-sample re-audit:** seeded `docs/eod_change_samples.json` - climax_reversal_guard blocked cohort
= 1/25 (GEO −3.64%, a correct block). `climax_gap_guard` 0/25. Both `accumulating` - no verdict until 25
affected decisions.

**Research launched:** a 3-lens expert panel (O'Neil/Minervini growth-momentum · Wyckoff/classical S/R ·
quant/anti-overfitting) validated the S/R + 52-wk-high logic. Unanimous verdicts: **S/R identification is
structurally wrong** - no swing-pivot / consolidation / volume-by-price levels; only MA proxies (the "real
support" for GEO, ~29.1 swing low, was never computed). **52-wk-high usage is inverted** - `prox_52w` scored
linearly, maxing AT the high (highest score where climax risk is highest). The real structural fix (build
genuine swing-pivot support + an inverted-U `prox_52w` conditioned on base quality) is deferred to a
dedicated deep-research + build - it needs calibration, not a rushed constant.

**Watch-items opened (re-audit next run):**
1. **rule1 affected-trade validation** - armed go-live-first; accumulating its sample (1/25 = GEO −3.64%, a
   correct block). Each run, add every `climax_reversal_off_high` block + the near-boundary *kept* names,
   with true outcomes, via `eod_change_tracker.py`. At 25 affected → HELP (blocked cohort loses → mark
   VALIDATED), HURT (killing winners - O'Neil's best names ride repeated new highs → revert/loosen), or
   TWEAK (move the 3% to where the blocked losers cluster). Judged on affected-trade count, not days.
2. **`climax_gap_guard` (rule2)** - accumulate its shadow affected-sample (recompute the ≥3%-gap-into-fresh-
   high condition on each run's fetched data); arm once the sample shows HELP.
3. **Low-beta-on-a-green-tape underperformance** - we were red on a +0.9%/+1.4% day. Track account
   participation vs SPY/QQQ; if we systematically lag strong tapes, investigate whether the pullback/
   defensive bias is mis-fit to up-trending regimes. Needs its own sample - not n=1.
4. **Wire scanner-survivor logging - DONE 2026-07-06.** Built `runtime/discovery_survivors.jsonl`
   (append-only, fail-safe) in `atlas/scan/discovery.py`; `eod_extract.py` now diffs it against the
   evaluated set to surface surfaced-but-never-evaluated names. Effective next launch → Phase 6 gets a real
   sample from tomorrow (the 07-06 dry run could only recover n=1 from the EOD-residual organizer pool).
5. **Swing-pivot-S/R build** - the real structural fix for the S/R blind spot; deep-research + build (a
   rule 3B fundamental once designed), don't rush a constant.

**Watch-items re-audited:** none (first entry).
