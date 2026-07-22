# Strategy Brief: ic_45d16d_managed

Researched 2026-07-19. Primary sources READ live (tastylive strategy pages fetched and quoted verbatim),
not recalled from memory. The tasty doctrine's deepest numeric research lives in video backtest segments
(Market Measures etc.) that cannot be text-cited precisely; where a constant's best citation is a written
secondary source documenting the tasty rule, that is stated explicitly. Every constant in §3/§4/§8
carries a direct quote + source, or an explicit UNKNOWN/ADAPTED/PLATFORM-POLICY tag. Two large public
backtest sites relevant to this exact structure were unreachable at research time (projectfinance.com - 
DNS dead; spintwig.com - 403): their numbers are tagged [unverified] and must not be built on.

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `ic_45d16d_managed`
- **Provenance class:** practitioner (tastylive/tastytrade mechanical short-premium doctrine)
- **PRIMARY citation:**
  - tastylive, **"Iron Condor Options Trading Strategy"** (concepts & strategies page, "tastylive
    Approach" + "Closing & Managing" sections) - https://www.tastylive.com/concepts-strategies/iron-condor
 - source of the 1/3-width credit rule, the 50%-of-max-profit close, and the "High" IV environment
    statement (page undated; live as of 2026-07-19).
  - tastylive, **"Strangle Option Strategy: How Long and Short Strangles Work"** - 
    https://www.tastylive.com/concepts-strategies/strangle - source of the ~45 DTE entry-timeframe quote
    and the 50%-of-credit buyback mechanics for tasty short premium generally (page undated; live as of
    2026-07-19). Same publisher; the iron condor is tastylive's defined-risk strangle analog.
  - tastytrade (brokerage arm), **"Iron Condor Strategy Guide"** (published Feb 7 2024, updated
    Apr 22 2026) - https://tastytrade.com/learn/trading-products/options/iron-condor/ - source of the
    GTC-at-50%-of-original-credit exit mechanics quote.
- **INDEPENDENT secondary sources:**
  1. Option Alpha, **"Tasty's 'Best Practices' Iron Condor Automated"** (Jack Slocum, May 27 2025) - 
     https://optionalpha.com/videos/tastys-best-practices-iron-condor-automated - independent
     documentation of the tasty best-practices template: "45+ DTE", "20 delta short legs", "takes profit
     at 50% of the opening credit", "closes positions at 21 DTE regardless of profit or loss".
  2. DTR Trading, **"45 DTE Iron Condor Results Summary - Part 2"** (Dave R., Jan 24 2017) - 
     http://dtr-trading.blogspot.com/2017/01/45-dte-iron-condor-results-summary-part.html - independent
     SPX backtest grid of exactly this family: 45 DTE entries, short deltas 8/12/16/20, wings 25/50/75
     pts, profit-taking 50%/75%/none, multiple loss-exit levels.
  3. (pointers, content unreadable at research time) projectfinance, "Iron Condor Management Results from
     71,417 Trades" - https://www.projectfinance.com/iron-condor-management/ (domain unresolvable;
     video mirror https://www.youtube.com/watch?v=cu1FXt4JEs8); spintwig, "Short SPX Iron Condor 45-DTE
     s1 signal Options Backtest" - https://spintwig.com/short-spx-iron-condor-45-dte-s1-signal-options-backtest/
     (403; per search index: 51,600+ SPX IC trades, Jan 3 2007 – Apr 30 2024, incl. 16Δ-short/5Δ-long).
- **Publication dates:** tastylive concept pages undated/maintained (doctrine televised since ~2012);
  tastytrade guide 2024/updated 2026; Option Alpha 2025; DTR Trading 2017.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**Source trades:** tastylive doctrine is taught on liquid optionable underlyings generally (their
concept-page example is a generic "$500.00" stock); the heavyweight backtest evidence for this exact
structure is on **SPX/SPY index options** (DTR Trading: SPX; spintwig: SPX; the widely-cited
managing-winners studies: SPY/SPX). The edge claim is an index-vol risk premium claim first.

**Our mapping:** SPY / QQQ / IWM (core - closest live analogs of the published SPX/SPY evidence) plus
the liquid mega-cap tier AAPL / NVDA / MSFT / TSLA / AMD / META (platform extension).

**Why the mapping preserves the edge claim:** the structure is options-native - 4 option legs, defined
risk, no stock legs, no delta-hedging - so NO vehicle adaptation is needed (unlike underlying-based
strategies). SPY/QQQ/IWM chains are penny-to-nickel wide at the 16Δ strikes near 45 DTE, matching the
liquidity assumptions of the published backtests. Two honest distortions to flag:
- **American vs European exercise:** the strongest published evidence is SPX (European, cash-settled).
  SPY/QQQ/IWM and the single names are American-style physical delivery → early-assignment risk on a
  short leg that goes ITM (esp. short call through ex-div) exists in our mapping but not in the SPX
  studies. Mitigated by the 21-DTE exit (we are always out ~3 weeks before expiry); documented in §7.
- **Single-name tier adds earnings-gap risk** the index evidence never had; gated by PLATFORM-POLICY
  (§3.6) and graded as its own covariate.

## 3. EXACT ENTRY RULES

1. **Trigger / cadence:** tasty doctrine is not signal-triggered - it is a standing short-premium
   program (sell the condor, manage, redeploy). Published form has no entry trigger to quote. Our
   shadow cadence (ADAPTED): per underlying, if flat in that name, open one condor at the next scan
   that passes gates; re-enter after each exit.
2. **DTE selection: 45 DTE target.** Primary (tastylive strangle page, tasty short-premium standard):
   "Our target timeframe for selling strangles is around 45 days to expiration." Secondary
   (Option Alpha, documenting the IC best-practices template): "45+ DTE". The tastylive iron condor
   page itself sets no DTE rule (its worked example happens to use "60 days till expiration" - 
   example, not rule). Shadow: expiration nearest 45 calendar DTE within a 35–55 band (band ADAPTED).
3. **Strike selection - short strikes: 16-delta.** The id pins 16Δ = the one-standard-deviation
   convention. IMPORTANT PROVENANCE NOTE: neither tastylive concept page prints a single mandated IC
   delta; the published tasty-standard range is 16–20Δ. Option Alpha's tasty template: "20 delta short
   legs" (verbatim). DTR Trading's 45-DTE grid tested "8, 12, 16, and 20 delta" shorts and reports "at
   16 delta, win rate grouping by profit taking level is even more pronounced" (verbatim). The
   projectfinance 71,417-trade study structure sold the 16Δ call + 16Δ put [unverified detail - site
   dead]. → short_call_delta = short_put_delta = 0.16, tagged SOURCE-RANGE (16–20 published; 16 chosen
   per id / 1SD convention). Nearest listed strike to |Δ|=0.16, acceptance band 0.12–0.20 (band ADAPTED).
4. **Strike selection - wings / credit rule.** Primary (tastylive IC page, verbatim): "We shoot for
   collecting 1/3rd the width of the strikes in premium upon trade entry." No fixed wing width is
   published (the page's example is "$50.00 wide" on a $500 stock - example, not rule; Option Alpha
   template: "configurable wing width"). Shadow mechanics (ADAPTED implementation of the verbatim
   credit rule): from listed strikes, choose the symmetric wing width (both spreads same width) that
   brings total net credit closest to 1/3 of width, tie-break narrower; skip entry if NO available
   width can collect ≥ 1/4 of width (floor relaxation ADAPTED - a hard 1/3 floor in low IV would
   starve the lane; the 1/3 target is what we optimize toward, and the shortfall is logged).
5. **Entry timing (time of day):** UNKNOWN - not published anywhere read. Shadow: platform scan window
   10:00–15:30 ET, avoid first/last 30 min (PLATFORM-POLICY).
6. **Regime / IV gate:** primary is qualitative only (tastylive IC page, verbatim): "Ideal Implied
   Volatility Environment: High". No numeric IV-rank threshold appears on any page read (the folk
   "IVR > 50" rule could NOT be verified in a citable source - recorded UNKNOWN, not implemented).
   Shadow: NO hard IV gate; log VIX percentile (IV-rank archive cold → VIX-percentile fallback) as a
   covariate. Note the ≥1/4-width credit floor acts as an implicit IV floor.
7. **Event gates:** none published. PLATFORM-POLICY: single names skip new entries when earnings fall
   before the planned 21-DTE exit date; FOMC/CPI logged only, never gated.

## 4. EXACT EXIT RULES (override platform exit doctrine for this strategy)

1. **Profit target - close at 50% of max profit.** Primary (tastylive IC page, verbatim): "we close
   iron condors when we reach 50% of our max profit." Mechanics (tastylive strangle page, verbatim):
   "The first profit target is generally 50% of the maximum profit. This is done by buying the
   strangle back for 50% of the credit received at order entry." Order style (tastytrade guide,
   verbatim): "placing a good-till-canceled (GTC) order to close the position at a specific profit
   threshold. For example, when the condor can be purchased for 50% of the original credit."
   → Shadow: buy the condor back when its mark ≤ 50% of the credit received at entry.
2. **Time exit - close at 21 DTE.** Secondary quote documenting the tasty rule (Option Alpha,
   verbatim, VERIFIED 2026-07-19): "closes positions at 21 DTE regardless of profit or loss." A second
   corroboration was cited from a Medium article (Aug 2 2025): "manage short premium trades at 21 days
   to expiration (DTE) or when you've captured 50% of the maximum profit" - but no URL was recorded and
   it could not be re-located at verification → [unverified]; the rule carries on the verified Option
   Alpha citation alone. The rule's PRIMARY home is tastylive's video research
   (Market Measures episodes); no precise text locator on tastylive.com was found - flagged in §8
   unknowns. → Shadow: if the profit target has not filled by the first mark at ≤21 calendar DTE,
   close at that mark, win or lose. Never hold past 21 DTE; hold-to-expiry is explicitly NOT the
   doctrine.
3. **Loss management - NO stop-loss.** No loss-multiple exit is published in any primary page read
   (tastytrade guide [CORRECTED 2026-07-19 - this phrase lives on the tastytrade guide, not the
   tastylive IC page]: closing a deep-ITM condor early "limits the realized loss to something below
   the maximum" - descriptive, not a trigger; Option Alpha's tasty template carries no stop either - 21 DTE is the
   only backstop; max loss is structurally capped, tastylive IC page verbatim: "The maximum loss is
   capped at the width of the widest spread, less credit received up front."). → Shadow: no premium-
   multiple stop. The 21-DTE exit and the defined-risk wings ARE the published loss management. This
   OVERRIDES the platform exit ladder for this lane.
4. **Roll rules - published but OMITTED (ADAPTED, loud).** tastylive's defensive management rolls
   "the untested side (non-losing side) closer to the stock price when our tested side (losing side)
   is breached" (tastylive strangle page, quoted phrase; no numeric roll increment published). Our
   shadow does NOT roll: 1-lot shadow ledgers treat a roll as close+reopen anyway, the roll increment
   is unpublished (UNKNOWN), and the independent tasty-template automation we cite also omits it.
   Consequence: our results will understate tasty-doctrine defense on tested condors - documented
   distortion, graded as-is.
5. **Hold-to-expiry doctrine:** none - expiry is never reached by rule 2.

## 5. SIZING CONVENTION IN SOURCE

tastylive teaches per-spread defined-risk sizing - buying power reduction = width − credit per condor
(tastylive IC page, verbatim: max loss "capped at the width of the widest spread, less credit received
up front") - with general small-relative-to-account guidance televised but no numeric %-of-buying-power
rule printed on the pages read (UNKNOWN as a constant). The backtest secondaries (DTR, spintwig) run
1 condor per entry. **Our shadow: 1 published unit = 1 iron condor (4 legs, 1 contract each),
account-blind** per platform convention.

## 6. DOCUMENTED PERFORMANCE

The tastylive/tastytrade concept pages publish NO performance table - win rate / CAGR / PF / max DD
from the primary source = **UNKNOWN [honest gap]**; the doctrine's numeric support is in video backtest
segments and independent replications.

- DTR Trading (SPX, 45 DTE, delta grid 8/12/16/20, wings 25/50/75, "96,624 iron condor (IC) trades"
  per its summary page [CORRECTED 2026-07-19: trades, not "variants"]): "at 16 delta, win rate grouping by profit taking level is even more
  pronounced"; with 50% profit-taking you "will generally be out of your trade for a profit between 16
  and 26 days"; "as wing width increases, the difference between the P&L per trade values for the
  different profit taking levels and IC structures decreases." **[verified-secondary]** (fetched
  2026-07-19; the site's per-variant metric is normalized avg P&L/day, not CAGR).
- projectfinance 71,417-trade study (16Δ shorts / 5Δ longs; also a 30Δ/16Δ version; 16 management
  combinations; search index says earlier profit-taking combos realized the highest success rates and
  the 30Δ/16Δ version realized lower success rates): **[unverified]** - domain dead at research time;
  do not build on these numbers.
- spintwig SPX IC 45-DTE study (51,600+ trades, Jan 3 2007 – Apr 30 2024, incl. 16Δ/5Δ structure):
  results paywalled → **[unverified]**.
- Often-repeated claims that managing winners at 50% lifts IC win rate from ~64% to ~82% (a "4,872 SPY
  iron condors 2005–2019" study) and that managed-at-50%/21-DTE condors win ~78–82%: found only on
  low-provenance aggregator sites → **[unverified]**; NEVER quote these as tasty research.
- Adjacent-parameter datapoint, NOT this spec (optionstradingiq, Oct 12 2021; 10–15Δ shorts, ~$1,000
  avg credit, 2× credit stop, exit 7 DTE, 50 ticker symbols backtested 2018–mid-2021 [CORRECTED
  2026-07-19: page says "50 different ticker symbols", not 50 trades]): "Actual success rate: 86%", avg win
  $460 / avg loss $677, "Average P&L per trade: $300.73", "36% annualized". **[verified-secondary]**
  but different rules - context only.

Methodology caveats: everything above is backtest, mid-price-fill territory; our WORST-fill three-ledger
convention will grade materially below mid-fill backtests; the strategy's expectancy is a vol-risk-
premium harvest whose realized edge is regime-dependent (see §7).

## 7. KNOWN FAILURE MODES

- **Volmageddon, Feb 5 2018:** the canonical short-vol wipeout day. A 45-DTE condor opened in the
  preceding low-IV grind had thin credit and both put-side legs run over intraday; defined wings cap
  the loss at width−credit, but that cap is realized, not avoided.
- **Mar-2020 COVID crash:** put side driven to near-max loss across successive cycles; vega explosion
  marks the whole condor against you long before the shorts are breached - path pain the e-process
  grader will see at every mark.
- **Aug 5 2024 yen-carry vol spike:** overnight gap + VIX spike - put spreads gapped to deep loss at
  the open with no chance to manage between marks; 21-DTE/50% management does not protect against
  overnight gaps.
- **Whipsaw double-touch:** underlying breaches the put side, condor marked near max loss, then rips
  through the call side after the untested side would have been rolled - the mode the (omitted)
  untested-side roll doctrine exists to monetize; our no-roll shadow eats it raw.
- **Gamma inside 21 DTE:** the published reason for the time exit - short-strike gamma grows as expiry
  nears, turning a quiet winner into a violent loser; our rule 4.2 removes this by construction, so a
  21-DTE-exit failure in our ledger indicates an implementation bug, not doctrine.
- **Low-IV credit starvation:** in IV troughs no width collects ≥1/4–1/3 width at 16Δ → entries skip
  (correct behavior, not a bug); expect lane droughts in vol winters.
- **Early assignment through ex-div (structural, our American-style mapping only):** a short CALL that
  goes ITM ahead of an ex-div date (SPY/QQQ/IWM quarterly distributions; AAPL/MSFT/META/NVDA pay
  dividends) can be assigned early; short ITM puts carry early-exercise risk near expiry. Largely
  neutralized by the always-out-at-21-DTE rule but not zero (deep ITM + imminent ex-div can trigger
  earlier); log any assignment as its own failure event.
- **Earnings gaps (single-name tier):** a 45-DTE mega-cap condor almost always spans an earnings date;
  the index-derived evidence says nothing about this. Gated per §3.7; entries that still span earnings
  (date moved after entry) must be flagged in grading.
- **Pin/expiration risk:** eliminated by the 21-DTE exit (never carried to expiry week).

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | underlying_universe | SPY, QQQ, IWM + AAPL, NVDA, MSFT, TSLA, AMD, META | PLATFORM-POLICY | published evidence base is SPX/SPY (DTR, spintwig); mapping rationale §2 |
| 2 | entry_cadence | per name: if flat, open at next passing scan; re-enter after exit | ADAPTED | doctrine is a standing program, no published trigger to quote |
| 3 | entry_dte_target | 45 calendar DTE | SOURCE-VERBATIM | tastylive strangle page: "Our target timeframe for selling strangles is around 45 days to expiration"; Option Alpha tasty template: "45+ DTE" |
| 4 | entry_dte_band | 35–55 (expiration nearest 45) | ADAPTED | "around 45" operationalized; no published band |
| 5 | short_call_delta | 0.16 | SOURCE-RANGE | published tasty-standard range 16–20Δ (Option Alpha: "20 delta short legs"; DTR grid tested "8, 12, 16, and 20 delta"); 16 chosen per id = 1SD convention |
| 6 | short_put_delta | 0.16 | SOURCE-RANGE | same as row 5; symmetric condor per tastylive IC page setup |
| 7 | delta_acceptance_band | nearest strike to 0.16, accept 0.12–0.20 | ADAPTED | strike-grid practicality; no published tolerance |
| 8 | credit_target | total credit ≈ 1/3 of wing width | SOURCE-VERBATIM | tastylive IC page: "We shoot for collecting 1/3rd the width of the strikes in premium upon trade entry." |
| 9 | credit_floor_skip | skip entry if best width collects < 1/4 width | ADAPTED | relaxed floor under the verbatim 1/3 TARGET (hard 1/3 floor would starve low-IV regimes); shortfall logged |
| 10 | wing_width_selection | symmetric; listed width whose credit is closest to 1/3 width; tie → narrower | ADAPTED | implements row 8; no fixed published width ("configurable wing width" - Option Alpha; example "$50.00 wide" on $500 stock is illustration) |
| 11 | wing_width_cap | ≤ $25 per side | PLATFORM-POLICY | CaR bound on width−credit basis; no source analog |
| 12 | profit_target | buy condor back at 50% of entry credit | SOURCE-VERBATIM | tastylive IC page: "we close iron condors when we reach 50% of our max profit"; strangle page: "buying the strangle back for 50% of the credit received at order entry" |
| 13 | profit_target_order_style | standing GTC-equivalent; check every mark | SOURCE-VERBATIM | tastytrade guide: GTC order "when the condor can be purchased for 50% of the original credit" |
| 14 | time_exit_dte | close at first mark ≤ 21 calendar DTE, win or lose | SOURCE-VERBATIM (secondary attribution) | Option Alpha (VERIFIED 2026-07-19): "closes positions at 21 DTE regardless of profit or loss"; Medium 2025-08-02 corroboration [unverified - no URL recorded, not re-locatable at verification]; primary = tastylive video research, text locator UNKNOWN |
| 15 | stop_loss | NONE (no premium-multiple stop) | SOURCE-VERBATIM (absence) | no loss-multiple rule on any primary page read; wings cap risk - tastylive IC page: "The maximum loss is capped at the width of the widest spread, less credit received up front." OVERRIDES platform ladder |
| 16 | roll_rules | none in shadow (published untested-side defensive roll OMITTED) | ADAPTED | tastylive rolls "the untested side (non-losing side) closer to the stock price" on breach; increment unpublished → omitted, distortion documented §4.4 |
| 17 | hold_to_expiry | never | SOURCE-VERBATIM (derived) | follows from row 14 (always out at 21 DTE) |
| 18 | iv_entry_gate | none numeric; log VIX percentile covariate | SOURCE-VERBATIM (qualitative) + PLATFORM-POLICY | tastylive IC page: "Ideal Implied Volatility Environment: High"; numeric IVR threshold UNKNOWN (folk "IVR>50" unverifiable in a citable source) |
| 19 | entry_time_of_day | 10:00–15:30 ET scan window | PLATFORM-POLICY | UNKNOWN in source; ours by policy |
| 20 | earnings_gate | single names: skip entry if earnings before planned 21-DTE exit date | PLATFORM-POLICY | index-based evidence is event-blind; ours by policy |
| 21 | fomc_cpi_gate | none; log-only | PLATFORM-POLICY | no published macro gate |
| 22 | expiration_type | any listed expiration in DTE band (monthlies preferred on ties) | ADAPTED | studies used monthly/weekly SPX cycles; no published restriction quoted |
| 23 | position_size | 1 condor (4 legs × 1 contract), account-blind | PLATFORM-POLICY | shadow convention; source sizing §5 |
| 24 | car_basis | width − net credit (max structural loss) | PLATFORM-POLICY | matches the source's own BPR framing (row 15 quote) |

UNKNOWN constants (recorded honestly, no invented values):
- **iv_rank_numeric_threshold** - only qualitative "High" is published on pages read; the folk IVR>50
  rule was NOT found in a citable source → no IV gate implemented.
- **entry_time_of_day** - never published; ours is policy.
- **published_fixed_wing_width** - no single published width exists (only the 1/3-width credit rule,
  a $50-on-$500 example, and "configurable" in the secondary).
- **untested_side_roll_increment** - the defensive roll is published qualitatively; its mechanics are
  not → rolls omitted.
- **21dte_primary_text_locator** - the 21-DTE rule's primary home is tastylive video research; no
  precise tastylive.com text locator found (rule carried here on two written secondary citations).
- **source_sizing_percent** - no numeric %-of-buying-power rule found on pages read.
- **primary_performance_table** - primary publishes no win-rate/CAGR/DD table (§6).

## 9. DATA REQUIREMENTS

- **Tradier chains:** DTE band 20–60 calendar days - 35–55 for entry hunting (strikes spanning ~0.05–0.30
  absolute delta on both sides for shorts + wing search), then marks on the held condor until exit
  (which by rule occurs at ≥21 DTE, so the held band never drops below ~20). Greeks (delta) required at
  entry scan; all four legs quoted (no_quote on any leg = skip/flag).
- **Earnings calendar (date + bmo/amc):** required for the six single names (gate row 20); not needed
  for SPY/QQQ/IWM.
- **FOMC/CPI dates:** log-only covariate (row 21).
- **VIX regime / IV rank:** IV-rank archive is cold → VIX-percentile fallback, logged as covariate at
  every entry (row 18); also drives §6 regime attribution at grading time.
- **Daily history:** modest - underlying daily closes for realized-vol context and ex-div calendar
  awareness (assignment-risk flag, §7); no long warm-up needed (no indicators).
- **1-min bars:** not required for signals (no intraday trigger); platform intraday mark cadence is
  sufficient - but marks must be frequent enough to catch the 50%-of-credit crossing same-day (see §10).

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** per name, cycle ≈ hold (16–26 days to the 50% target per DTR
  [verified-secondary], hard cap ~24 days entry→21 DTE) + immediate re-entry ≈ ~1.2–1.5 trades/month;
  × 9 names ≈ 11–13 before gates; earnings gate suppresses a fraction of single-name entries →
  **~10/month blended** (range 8–13). N≥25 gradeable in ~2.5–3 months; note SPY/QQQ/IWM condors are
  highly correlated - effective independent N grows slower than trade count.
- **Multi-leg shape:** 4 legs - short 16Δ call + short 16Δ put, one long wing beyond each short, both
  spreads same width. All four legs open and close together (no legging, no rolls).
- **Mark cadence needed:** intraday platform cadence on the whole condor (net mark), every trading day
  of the hold - required both for the GTC-style 50% profit check (row 13) and because the failure modes
  of interest (vega spikes, gap days) are invisible at daily granularity. The 21-DTE exit fires at the
  first mark of the 21-DTE session.
- **Per-family capital-at-risk basis:** **width − credit** (defined-risk max loss) per condor - matches
  the source's own buying-power framing. Do NOT use a Reg-T proxy; this family is fully defined-risk.
- **1-lot account-blind distortion:** minimal - the published unit is per-spread and the backtest
  secondaries run 1-lot too. The real distortions vs the published record are (a) WORST-fill grading on
  a 4-leg spread (four bid/ask crossings vs backtest mid-fills - expect systematic drag; grade against
  the e-process, not against mid-fill backtest stats), (b) omitted defensive rolls (§4.4 - our tested-
  side losses will run worse than tasty doctrine's), and (c) American-style assignment risk absent from
  the SPX evidence (§2, §7).
- **Doctrine override reminder:** this lane's exits are EXACTLY: 50%-of-credit profit target + 21-DTE
  time exit, no stop-loss, no rolls, never hold past 21 DTE (§4). Platform exit-ladder logic must be
  disabled for this family - the point is testing the published management doctrine as written.

## 11. VERIFICATION

**Verdict: CORRECTED** - adversarial verification pass, 2026-07-19, fresh-context verifier.

**What was checked (all cited sources fetched live 2026-07-19):**
- tastylive IC page (https://www.tastylive.com/concepts-strategies/iron-condor): VERIFIED verbatim - 
  1/3-width credit rule, 50%-of-max-profit close, "IDEAL IMPLIED VOLATILITY ENVIRONMENT: High",
  max-loss-capped-at-width-less-credit quote, the $500 stock / $50-wide / 60-DTE example; confirmed
  the page prints NO DTE rule, NO delta number, NO stop-loss trigger (matching the brief's absence
  claims).
- tastylive strangle page (https://www.tastylive.com/concepts-strategies/strangle): VERIFIED verbatim - 
  "around 45 days to expiration", the 50%-of-credit buyback mechanics, the untested-side roll quote;
  confirmed NO numeric roll increment and NO 21-DTE mention (matching the brief).
- tastytrade guide (https://tastytrade.com/learn/trading-products/options/iron-condor/, pub Feb 7 2024
  / upd Apr 22 2026 - dates confirmed): VERIFIED verbatim - the GTC-at-50%-of-original-credit quote;
  confirmed NO 21-DTE mention.
- Option Alpha (https://optionalpha.com/videos/tastys-best-practices-iron-condor-automated, Jack
  Slocum, May 27 2025 - author/date confirmed): VERIFIED verbatim - "45+ DTE", "20 delta short legs",
  "takes profit at 50% of the opening credit", "closes positions at 21 DTE regardless of profit or
  loss", "configurable wing width".
- DTR Trading (http://dtr-trading.blogspot.com/2017/01/45-dte-iron-condor-results-summary-part.html,
  Dave R., Jan 24 2017 - author/date confirmed): VERIFIED - delta grid 8/12/16/20, wings 25/50/75 pts,
  profit-taking 50%/75%/NA, "At 16 delta, win rate grouping by profit taking level is even more
  pronounced", 16–26-days-to-profit quote, wing-width convergence quote, "96,624 iron condor (IC)
  trades", SPX, normalized-P&L-per-day metric.
- optionstradingiq (https://optionstradingiq.com/iron-condor-success-rate/, Gavin, Oct 12 2021 - 
  URL located and confirmed): VERIFIED - 86% success, $460/$677 avg win/loss, $300.73 avg P&L/trade,
  ~36% annualized, 2× credit stop, 7-DTE exit, 10–15Δ shorts.
- projectfinance.com: confirmed DNS-dead (getaddrinfo ENOTFOUND) - [unverified] tag correct.
- spintwig.com study URL: confirmed HTTP 403 - [unverified] tag correct.

**Result:** ZERO invented constants. Every SOURCE-VERBATIM / SOURCE-RANGE constant in §3/§4/§8 was
located verbatim (or as an honest range) in its cited source; every ADAPTED tag carries a real
rationale and none is presented as published; every [verified-*] performance number was found; every
[unverified] tag corresponds to a genuinely unreachable source; the UNKNOWN list is honest.

**Four minor corrections applied in place (all marked CORRECTED 2026-07-19 inline):**
1. §4.3 - "limits the realized loss to something below the maximum" was attributed to the tastylive IC
   page; it actually appears on the tastytrade guide. Attribution fixed. (The no-stop-loss claim itself
   is unaffected - verified absent on all primary pages.)
2. §6 - DTR's figure is "96,624 iron condor (IC) trades", not "backtested condor variants". Fixed.
3. §4.2 / row 14 - the Medium (Aug 2 2025) corroborating quote was cited with no URL and could not be
   re-located at verification (session search budget exhausted); demoted to [unverified]. The 21-DTE
   rule stands on the verified Option Alpha citation.
4. §6 - optionstradingiq backtested "50 different ticker symbols", not "50 trades". Fixed.

**Residual doubts:** (a) the 21-DTE rule's PRIMARY tastylive text locator remains UNKNOWN as the brief
already flags - it is carried on one verified independent secondary; (b) fetch verification used an
extraction model over rendered page text, so exact-whitespace/casing fidelity of quotes is to the
rendered page, not raw HTML; (c) the Medium corroboration is plausibly real but unlocatable without a
URL - do not cite it independently; (d) DTR quotes were confirmed against the Part-2 summary page - 
per-variant tables live in linked parts not individually re-fetched.

### Independent re-verification (second pass, fresh context, 2026-07-19)

**Verdict: CONFIRMED.** A second adversarial verifier, with no access to the first pass's context,
treated the section above as untrusted and re-fetched every citable source live on 2026-07-19:

- tastylive IC page: re-confirmed verbatim - 1/3-width credit rule, 50%-of-max-profit close,
  "IDEAL IMPLIED VOLATILITY ENVIRONMENT: High", width-less-credit max-loss quote, $500/$50-wide/60-DTE
  example; re-confirmed ABSENT - any DTE rule, any delta number, any stop-loss rule.
- tastylive strangle page: re-confirmed verbatim - "Our target timeframe for selling strangles is
  around 45 days to expiration", 50%-of-credit buyback mechanics, untested-side roll quote;
  re-confirmed ABSENT - 21 DTE, numeric roll increment.
- tastytrade guide (pub Feb 7 2024 / upd Apr 22 2026, dates re-confirmed): re-confirmed verbatim - 
  GTC-at-50%-of-original-credit quote AND the "limits the realized loss to something below the
  maximum" phrase (confirming correction #1's re-attribution was right); 21 DTE ABSENT.
- Option Alpha (Jack Slocum, May 27 2025, re-confirmed): all five template quotes re-confirmed
  verbatim, including "closes positions at 21 DTE regardless of profit or loss".
- DTR Trading Part 2 (Dave, Jan 24 2017, re-confirmed): delta grid, wing widths 25/50/75, profit
  levels 50/75/NA, the 16-delta win-rate quote, the 16–26-days quote, the wing-width-convergence
  quote, SPX + normalized-P&L-per-day metric all re-confirmed. Precision note on the 96,624 figure:
  it appears on the Part-2 page inside "In the last post, 45 DTE Iron Condor Results Summary, I
  showed the backtest results from 96,624 iron condor (IC) trades." - i.e. Part 2 quoting its own
  Part-1 summary. The brief's "per its summary page" phrasing is consistent with this.
- optionstradingiq (Gavin, Oct 12 2021, re-confirmed): 86% / $460 / $677 / $300.73 / 36% annualized /
  2× credit stop / 7-DTE exit / 10–15Δ / ~$1,000 credit / "50 different ticker symbols" (2018–mid-2021)
  all re-confirmed verbatim.
- projectfinance.com: re-confirmed dead (getaddrinfo ENOTFOUND). spintwig study URL: re-confirmed
  HTTP 403. Both [unverified] tags remain correct.

Zero invented constants found on independent re-check; zero new corrections required; all four prior
inline corrections verified as correct against the live sources. The strategy's edge claim (short
index vol-risk premium harvested with 50%/21-DTE management) is supported by the primary doctrine
pages plus one verified independent secondary and one verified independent backtest series, with the
performance record honestly gapped where sources are dead or low-provenance.
