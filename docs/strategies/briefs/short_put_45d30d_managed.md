# Strategy Brief: short_put_45d30d_managed

Research date: 2026-07-19. All quotes below were read directly from the cited page (live or Wayback-archived copy) during this research session. Nothing in sections 3/4/8 is from memory.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `short_put_45d30d_managed`
- **Provenance class:** practitioner (tastylive / tastytrade research segments; independent retail replications)
- **PRIMARY citations (tastylive):**
  1. **"Short Puts | Managing Winners & Losers"** - Market Measures, tastylive (then tastytrade), aired **Sep 1, 2015**.
     URL: https://www.tastylive.com/shows/market-measures/episodes/short-puts-managing-winners-losers-09-01-2015
     ⚠ Removed from the live site as of 2026-07-19 (the URL now resolves to the Market Measures show landing page; no episode study content). Verified via Wayback snapshot: https://web.archive.org/web/20251212010450/https://www.tastylive.com/shows/market-measures/episodes/short-puts-managing-winners-losers-09-01-2015
  2. **"Short Puts: Expectations for Different Deltas"** - Market Measures, tastylive, aired **Jul 14, 2016**.
     URL: https://www.tastylive.com/shows/market-measures/episodes/short-puts-expectations-for-different-deltas-07-14-2016
     Verified via Wayback snapshot: https://web.archive.org/web/20250114181357/ (same URL)
  3. **"Enter at 45 DTE, Exit at 21 DTE"** - The Skinny on Options: Abstract Applications, tastylive, aired **Jul 27, 2020**.
     URL: https://www.tastylive.com/shows/the-skinny-on-options-abstract-applications/episodes/enter-at-45-dte-exit-at-21-dte-07-27-2020
     Verified via Wayback snapshot: https://web.archive.org/web/20240302110545/ (same URL)
  4. **"Managing Winning Options Positions"** - tastylive concepts page (live, read 2026-07-19): https://www.tastylive.com/concepts-strategies/managing-winners
- **INDEPENDENT secondary sources:**
  1. **spintwig - "SPY Short Put 45 DTE Cash-Secured Options Backtest"** (Jun 10, 2019; 54 backtests, >170,500 trades, includes the exact 30-delta / "50% max profit or 21 DTE" variant): https://spintwig.com/spy-short-put-strategy-performance/ (live site 403s bots; read via Wayback https://web.archive.org/web/2023/https://spintwig.com/spy-short-put-strategy-performance/)
  2. **projectoption (Chris Butler) - "Short Put Management Results from 41,600 Trades [STUDY]"** (Jun 7, 2017): https://www.projectoption.com/short-put-management-study/ (404 on live site; read via Wayback https://web.archive.org/web/20210731050616/https://www.projectoption.com/short-put-management-study/)
  3. **financialtechwiz - "tastytrade Review: The tastytrade Options Strategy"** (Aug 6, 2024): https://www.financialtechwiz.com/post/tastytrade-review/ - documents the composite "tastylive standard" mechanics list verbatim.
- **Publication dates:** 2015-09-01, 2016-07-14, 2020-07-27 (primary segments); 2017-06-07, 2019-06-10, 2024-08-06 (secondaries).
- **Note on provenance shape:** No single tastylive document publishes "45 DTE + 30-delta + 50% + 21 DTE" as one numbered spec. The id is the composite of (a) the short-put management studies (45 DTE, 50% management, loss-multiple arms), (b) the delta-grid study (15/25/35/50Δ), and (c) the 45-DTE-in / 21-DTE-out doctrine segment. The 30-delta default is documented as tastylive guidance by secondaries and replicated at exactly 30Δ by spintwig. This is flagged honestly per-constant in section 8.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

- **What the source trades:** SPY only, in every primary study read. 2015 study: "A study was conducted using the SPY (S&P 500 ETF) from 2005 to present." 2016 study: "Our study was conducted in the SPY (S&P 500 ETF) from 2005 to the present." spintwig: SPY (with companion 45-DTE cash-secured short-put backtests for QQQ, IWM, AAPL, TSLA, AMZN, and others listed on the same site). tastylive's live-show practice extends the same mechanics to liquid single names, but the *studies* read here are SPY.
- **Our mapping:** SPY/QQQ/IWM (index ETF tier - faithful to source) + AAPL/NVDA/MSFT/TSLA/AMD/META (liquid mega-cap tier - **extension beyond the published evidence base**).
- **Why the mapping preserves the edge claim:** The published edge is structural, not SPY-specific: short OTM puts harvest the equity/volatility risk premium, and early management (50% / 21 DTE) trades a small cut in average P/L per trade for higher win rate, faster capital recycling, and less gamma/tail exposure ("We enter trades at 45 DTE to maximize our returns from positive theta, and we exit trades at 21 DTE to minimize portfolio risk" - primary 3). QQQ/IWM share the SPY microstructure (penny-ish spreads, deep OI, no earnings gaps). The mega-cap tier adds idiosyncratic gap risk (earnings, product/CEO news) that the SPY studies never faced - flagged as ADAPTED in section 8 with a PLATFORM-POLICY earnings gate.
- **LOUD ADAPTATION NOTES:**
  - No stock legs, no assignment handling: the platform is options-only. If a short put goes ITM at our exit points we close the option; we never take delivery. The published cash-secured/wheel variants that accept assignment are NOT what we run.
  - Single-name tier is an extrapolation; grade it as its own lane, not pooled with the ETF tier, before believing the edge transfers.

## 3. EXACT ENTRY RULES

- **Trigger / cadence:** Enter on the **first trading day of each month**, per underlying. Source (2015 primary): "On the first trading day of every month we sold the 16 delta put closest to 45 days to expiration (DTE)." (Correction 2026-07-19: the 2016 delta study does NOT repeat this sentence - its page states no entry cadence at all, only "Using options with 45 days to expiration (DTE) we sold Puts with a 50, 35, 25 and 15 Delta." The monthly cadence rests on the 2015 study alone.) spintwig entered daily ("Entry Days: daily") to build sample size; the tastylive protocol is monthly and that is what we shadow.
- **No entry signal / no market condition required:** both primary studies entered unconditionally every cycle. spintwig: "Entry Signal: N/A".
- **DTE selection:** expiration **closest to 45 DTE**. Sources: 2015 primary, "closest to 45 days to expiration (DTE)"; secondary verbatim criteria list, "Use the expiration closest to 45 DTE."; rationale (primary 3): "the reason why we choose 45 DTE to enter trades is that the slope of the theta decay curve begins to steepen at this point, which means the extrinsic value of our positions will decrease more rapidly."
  - Acceptable band when no expiry sits at 45: projectoption used "Standard Expiration Closest to 45 Days to Expiration (resulted in trades between 30-60 days to expiration)"; spintwig used "Days Till Expiration: 45 DTE +/- 17, closest to 45".
  - Expiration type: **standard (monthly) expirations** per projectoption quote above; spintwig did not restrict to monthlies. We restrict to standard monthlies to match the tastylive-era protocol.
- **Strike selection:** sell the put **closest to 30 delta**.
  - The 2015/2016 primaries used a 16Δ base case and a Δ-grid: "Using options with 45 days to expiration (DTE) we sold Puts with a 50, 35, 25 and 15 Delta. We compared holding to expiration ... managing at 50% of max profit (if possible) or taking a loss at 2x the credit received." (2016 primary). No primary study read here uses exactly 30Δ.
  - The 30Δ default is the documented tastylive house guideline per secondary (verbatim: "Sell options with a 30 delta.") and is the exact spintwig variant: "30 delta +/- 3.5 delta, closest to 30".
  - Tagged SOURCE-RANGE in section 8, not SOURCE-VERBATIM-primary. Do not present 30Δ as a tastylive-study constant.
- **Credit rule:** none published. No minimum-credit threshold appears in any source read. UNKNOWN → no credit floor beyond platform liquidity gates.
- **Entry timing (time of day):** UNKNOWN in the tastylive studies (not stated). spintwig stamped entries at "Timing: 3:46pm ET". We use the platform's scan time and record this as ADAPTED.
- **Published regime/IV gate:** none in the primary studies (unconditional monthly entry). The composite house guidance adds a direction-only, threshold-free preference: "Sell options when IV is high." (secondary verbatim). No numeric IV-rank threshold was published in anything read → gate is OFF for the shadow; we log IV percentile at entry for later analysis (PLATFORM-POLICY).

## 4. EXACT EXIT RULES (OVERRIDE platform exit doctrine for this strategy)

- **Profit target: buy to close at 50% of max profit** (i.e., when the put can be repurchased for half the entry credit). Sources: 2015 primary - the tested arm is "exiting at 50% of max profit"; live doctrine page - "We tend to close our winners when we reach 50% profit, or lower for certain strategies like calendar spreads, diagonal spreads and iron flies." and "we've found that the target of managing our winning trades at 50% can be the sweet spot over the long run for most trades."; secondary verbatim - "Take profit when you collect 50% of the premium."
- **Time exit: close at 21 DTE** if the profit target has not been hit. Source (primary 3): "by managing our positions at 21 DTE, we are able to not only mitigate the gamma risk of our positions, but significantly reduce our overall portfolio risk." Short-form (same page): "We enter trades at 45 DTE to maximize our returns from positive theta, and we exit trades at 21 DTE to minimize portfolio risk". Composite rule = "50% max profit or when DTE = 21, whichever occurs first" (spintwig's exact managed-variant definition).
- **Loss management: NONE in the base managed variant.** The 21-DTE exit is the risk mechanism. The primaries *tested* stop-loss arms as alternatives - 2015: "taking a loss at 1x to 5x credit received"; 2016: "taking a loss at 2x the credit received" - but no source read here publishes a stop-loss as part of the default managed doctrine, and spintwig's managed arm carries no stop. We run **no stop** and let the 21-DTE exit realize whatever loss exists. Do not bolt on a platform stop for this strategy.
- **Roll rules:** we do NOT roll. Note the doctrine divergence honestly: the secondary criteria list says "Roll forward and don't change the strike price at 21 DTE to reduce gamma risk.", while primary 3 frames 21 DTE as an *exit*. Our shadow closes at 21 DTE; the next first-of-month entry re-establishes exposure, which is functionally the studied close-and-redeploy cycle. Tagged ADAPTED.
- **Hold-to-expiry doctrine:** explicitly rejected by this strategy id; hold-to-expiration was the *comparison* arm in both primaries ("This study compared holding to expiration, exiting at 50% of max profit and exiting at 50% max profit or taking a loss at 1x to 5x credit received." - 2015 primary).
- **Early exercise / assignment:** if assigned early (rare for puts, possible when deep ITM with near-zero extrinsic), the platform books the exit at intrinsic at the assignment mark and closes the position - options-only, no share position is ever carried (PLATFORM-POLICY; the sources' backtests assumed "Early assignment never occurs" - spintwig).

## 5. SIZING CONVENTION IN SOURCE

- tastylive studies: **1 contract per entry**, no account sizing stated in the study protocols read. spintwig: "Positions opened per trade: 1", collateral basis cash-secured ("Margin collateral is held as cash and earns no interest"), with a leveraged companion study at "Margin requirement for short CALL and PUT positions is 20% of notional". projectoption: "Number of Contracts: 1".
- tastylive's general show guidance ties naked-short sizing to a small % of buying power, but no specific % appears in the sources read here - UNKNOWN, and irrelevant to our shadow.
- **Our shadow:** always 1 published unit = **1 short put contract**, account-blind, per standing platform convention.

## 6. DOCUMENTED PERFORMANCE

Qualitative results are readable in the sources; the granular per-variant tables mostly are not (video tables / paywall). Every claim tagged.

- [verified-primary] 2016 delta study: "The table showed that managing the short puts greatly increased the P/L per day percentage." (direction only; the table's numbers are in the video, not the page text)
- [verified-primary] 2016 delta study, Tom Sosnoff on the delta grid: "your max risk is the same (for all the Deltas) but the expectation has to be different".
- [verified-primary] 2015 study structure: compared hold-to-exp vs 50% vs 50%+1x–5x stops on P/L, % winners, avg P/L/day, avg trade P/L, largest drawdown - the episode page documents the comparison but the numeric table is in the video only. Numbers: UNKNOWN.
- [verified-secondary] spintwig (SPY, 2007-01-03→2019-07-31, daily entries, 54 variants, >170,500 trades):
  - "Systematically selling puts on SPY was profitable across all delta targets."
  - "No option strategy outperformed buy-and-hold SPY with regard to total return."
  - "It appears that managing positions early, in general, outperforms using stop losses."
  - "Closing less-risky positions at 75% of max profit or expiration yielded the highest win rate. As trades were opened closer to the money closing positions at 25% max profit or 21 DTE began to improve the win rate."
  - "The higher the delta the greater the total return."
  - "20.77% – the blended average percent of profits spent on commission across all short put strategies."
  - Per-variant CAGR / win rate / Sharpe / max-drawdown tables: paywalled → UNKNOWN.
- [verified-secondary] projectoption (SPY, Jan 2007→May 2017, daily entries, 16Δ, 41,600 trades, 16 management combos):
  - "the 25% Profit / Exp. combination had a 98% success rate overall" (note: 25% target, 16Δ - not our variant).
  - "Since 2007, doing nothing and simply holding short put positions (16-delta, 30-60 DTE) to expiration has resulted in the highest average P/L per trade."
  - "After normalizing each short put management approach's expectancy to a 45-day period, we find that the smaller profit-taking approaches yield the highest P/L figures because trades are closed and redeployed much faster."
  - VIX regime: "more passive approaches (taking larger profits and not taking any losses) performed the best in the lower VIX environments. However, the approaches with higher profit targets that also included a loss-taking strategy performed the best in the highest VIX environments."
- [unverified] Circulating claims (e.g., "~71% win rate for 30Δ 45-DTE SPY short puts since 2005", "16Δ ~95% OTM, ~97% win managed at 50%") appeared only in search-result snippets, not in any page read end-to-end. Treat as rumor until reproduced.
- **Bottom line for grading:** there is NO verified published CAGR / win rate / PF / max-DD for the exact 30Δ managed variant. The shadow's own ledgers are the first trustworthy numbers we will have. Expect: high win rate, small average win, occasional multiple-credit losses at the 21-DTE exit, long right tail of drawdown during vol events.

## 7. KNOWN FAILURE MODES

- **Volmageddon (Feb 5, 2018):** VIX doubled in a day; short puts opened in the preceding low-IV grind marked at multi-credit losses. Positions between 45 and 21 DTE had no stop to cut them; the 21-DTE exit realizes the loss wherever it lands.
- **COVID crash (Feb–Mar 2020):** 30Δ SPY puts went deep ITM; losses of many multiples of credit. Management doctrine does not cap this - the strategy is short left-tail by construction.
- **Oct–Dec 2018 and 2022 grinding bear:** repeated cycles where the 50% target is never reached and each 21-DTE exit books a loss; monthly re-entry at fresh 30Δ strikes keeps re-shorting into the decline. Sequence-of-loss risk without a single named crash.
- **Aug 5, 2024 vol spike (VIX >60 intraday):** overnight/gap vol repricing; marks on open puts spiked against the position with no intraday exit rule to respond.
- **Single-name gap-through-strike (our extension tier only):** earnings or news gaps (e.g., NVDA/TSLA/META post-earnings moves) can jump the underlying far through a 30Δ strike between closes - a risk absent from every SPY study cited. Mitigated (not eliminated) by the PLATFORM-POLICY earnings gate.
- **Early assignment (structural):** short puts deep ITM with near-zero extrinsic can be assigned before our exit points (hard-to-borrow names and imminent large dividends increase put early-exercise incentive). Both backtests assumed it away ("Early assignment never occurs" - spintwig). Options-only platform: book intrinsic-value exit, never carry stock.
- **Replication caveat (structural):** the headline tasty claims mix monthly-entry small samples (≈126 trades 2005–2015) with daily-entry overlapping samples (spintwig/projectoption); overlapping daily entries share the same crashes, so effective sample size is far smaller than trade counts suggest.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | published_underlying | SPY | SOURCE-VERBATIM | "A study was conducted using the SPY (S&P 500 ETF) from 2005 to present." (MM 2015-09-01) |
| 2 | shadow_universe | SPY, QQQ, IWM + AAPL, NVDA, MSFT, TSLA, AMD, META | ADAPTED | Extension beyond published SPY base; ETF tier faithful, mega-cap tier extrapolation (see §2). Companion per-symbol backtests exist at spintwig for QQQ/IWM/AAPL/TSLA/AMZN. |
| 3 | dte_target | 45 | SOURCE-VERBATIM | "sold the 16 delta put closest to 45 days to expiration (DTE)" (MM 2015-09-01); "Use the expiration closest to 45 DTE." (financialtechwiz criteria list) |
| 4 | dte_band | 30–60, choose expiry closest to 45 | SOURCE-RANGE | "Standard Expiration Closest to 45 Days to Expiration (resulted in trades between 30-60 days to expiration)" (projectoption); spintwig used "45 DTE +/- 17, closest to 45" - documented default: closest to 45 |
| 5 | expiration_type | standard monthly expirations only | SOURCE-VERBATIM | "Standard Expiration Closest to 45 Days to Expiration" (projectoption; matches the monthly-cycle protocol of the tastylive studies) |
| 6 | option_type | single short put (naked, 1 leg) | SOURCE-VERBATIM | "we sold the 16 delta put" (MM 2015-09-01) |
| 7 | delta_target | 30 (put delta ≈ −0.30) | SOURCE-RANGE | Primary grid: "we sold Puts with a 50, 35, 25 and 15 Delta" (MM 2016-07-14) - 30 sits inside the tested 15–50 range but is not itself a primary-study constant; documented house default: "Sell options with a 30 delta." (financialtechwiz); exact replication variant: "30 delta +/- 3.5 delta, closest to 30" (spintwig) |
| 8 | delta_tolerance | ±3.5, closest to target | SOURCE-VERBATIM | "30 delta +/- 3.5 delta, closest to 30" (spintwig methodology) |
| 9 | entry_cadence | first trading day of each month, per underlying | SOURCE-VERBATIM | "On the first trading day of every month we sold the 16 delta put closest to 45 days to expiration (DTE)." (MM 2015-09-01) |
| 10 | entry_time_of_day | platform scan window; published value UNKNOWN | ADAPTED | tastylive studies state no time; spintwig stamped "Timing: 3:46pm ET". We use the platform's standard scan and log it. |
| 11 | entry_signal / regime gate | NONE (unconditional entry) | SOURCE-VERBATIM | "Entry Signal: N/A" (spintwig); both tastylive studies entered every cycle unconditionally |
| 12 | iv_gate | OFF; log IV percentile (VIX-percentile fallback) at entry | PLATFORM-POLICY | Direction-only guidance exists - "Sell options when IV is high." (financialtechwiz) - but no numeric threshold is published anywhere read: UNKNOWN → observe-only |
| 13 | min_credit | none | SOURCE-VERBATIM (absence) | No credit floor appears in any cited methodology; UNKNOWN/none published |
| 14 | profit_target_pct | close at 50% of entry credit captured | SOURCE-VERBATIM | "exiting at 50% of max profit" (MM 2015-09-01); "Take profit when you collect 50% of the premium." (financialtechwiz); "the target of managing our winning trades at 50% can be the sweet spot over the long run for most trades" (tastylive managing-winners page) |
| 15 | time_exit_dte | 21 | SOURCE-VERBATIM | "we exit trades at 21 DTE to minimize portfolio risk" (Skinny 2020-07-27); composite arm: "50% max profit or when DTE = 21, whichever occurs first" (spintwig) |
| 16 | stop_loss | NONE (base variant) | SOURCE-VERBATIM | Managed arm carries no stop: "50% max profit or when DTE = 21, whichever occurs first" (spintwig). Tested alternates only: "taking a loss at 1x to 5x credit received" (MM 2015-09-01), "taking a loss at 2x the credit received" (MM 2016-07-14) |
| 17 | roll_policy | no roll - close at 21 DTE; next monthly entry re-establishes | ADAPTED | Divergent doctrine documented: "Roll forward and don't change the strike price at 21 DTE to reduce gamma risk." (financialtechwiz) vs 21-DTE *exit* framing (Skinny 2020-07-27). We close; re-entry happens on cadence. |
| 18 | contracts_per_unit | 1 | SOURCE-VERBATIM | "Positions opened per trade: 1" (spintwig); "Number of Contracts: 1" (projectoption) |
| 19 | earnings_gate (single-name tier) | skip that month's entry if a confirmed earnings date falls before the planned 21-DTE exit date | PLATFORM-POLICY | Ours. The SPY studies had no earnings exposure; this gate contains the §7 gap-through-strike failure mode. |
| 20 | liquidity_gate | platform standard (two-sided quote, OI, max spread %) | PLATFORM-POLICY | Ours; no liquidity thresholds published in sources. |
| 21 | assignment_handling | book intrinsic exit, never carry shares | PLATFORM-POLICY | Options-only platform; sources assumed "Early assignment never occurs" (spintwig). |

Constants recorded as UNKNOWN: `entry_time_of_day` (published), `iv_gate threshold` (no published number), `min_credit` (none published), and all per-variant performance statistics for the 30Δ managed arm (§6).

## 9. DATA REQUIREMENTS

- **Tradier chains:** DTE band 25–65 needed at scan time (target 45, band 30–60, plus slack for expiry alignment); delta + bid/ask + OI per put strike. Standard monthly expirations must be distinguishable from weeklies.
- **Earnings calendar:** date + bmo/amc for AAPL/NVDA/MSFT/TSLA/AMD/META - feeds parameter 19. Not needed for the ETF tier.
- **FOMC/CPI dates:** not required by the published rules (unconditional entry). Log-only for failure-mode attribution.
- **VIX regime / IV rank:** log-only at entry (parameter 12). Our IV archive is cold → use the documented VIX-percentile fallback. projectoption's VIX-quartile results (§6) are the reason to log this from day one.
- **Daily history:** underlying daily closes for context marks and for the 21-DTE/expiry bookkeeping.
- **1-min bars / intraday marks:** the 50% profit trigger is path-dependent ("reach 50% profit" at any time, not at close). Minimum honest implementation: intraday option-mid polling at the platform's existing mark cadence; EOD-only checking systematically under-detects 50% touches and must be flagged on any grade if used.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** 9 (one per underlying on the first trading day of each monthly cycle; entries skipped by the earnings gate reduce this - realistically 7–9/month). Pooled N=25 arrives in ~3 months; per-symbol N=25 takes ~2+ years, so grade the ETF tier (3/month) and mega-cap tier (≤6/month) as two lanes, pooled within tier.
- **Mark cadence:** intraday mid-price polling for the 50% buy-to-close trigger (see §9); one mandatory EOD mark for the ledgers; exit day at 21 DTE uses the platform's standard exit-window fill convention. Trades live up to 24 calendar days (45→21), so open-position inventory across weeks is normal.
- **Multi-leg shape:** single leg - 1 short put. No spread bookkeeping.
- **Per-family capital-at-risk basis:** naked short put → **Reg-T CaR proxy** (max(20% × underlying − OTM amount, 10% × strike) × 100 + credit convention), consistent with spintwig's "Margin requirement for short CALL and PUT positions is 20% of notional". Cash-secured basis (strike × 100) is the conservative alternative the source's cash-secured variant used; record CaR under the Reg-T proxy but log both so returns are comparable either way.
- **1-lot account-blind distortions:** minimal - both replications are literally 1-contract-per-entry, so our convention matches the published form. What we do NOT replicate: portfolio-level buying-power throttles and tasty-style "trade small, trade often" aggregation. Also, our monthly cadence (tastylive protocol) yields far fewer occurrences than the daily-entry replications; do not compare our trade counts to spintwig's.
- **Exit-doctrine override reminder:** sections 4/8 OVERRIDE all platform exit machinery for this strategy - no platform stop-loss, no noise-reclaim/thesis-streak exits, no discretionary cuts. The only exits are 50% profit, 21 DTE, expiry-window bookkeeping if 21-DTE falls on a holiday gap, and forced intrinsic booking on early assignment.
- **Grading caveat:** with no stop, single trades can print multi-credit losses; WORST-grade discipline should evaluate the *rule*, not the outcome - a −3x loss exited at 21 DTE per spec is a CORRECT trade.

## 11. VERIFICATION

- **Verdict: CORRECTED** (one minor citation error fixed in place; no invented constants found). Date: 2026-07-19. Adversarial fresh-context verification pass.
- **What was checked:** every SOURCE-VERBATIM / SOURCE-RANGE constant in sections 3, 4, and 8, every [verified-*] performance claim in section 6, and every ADAPTED/PLATFORM-POLICY tag's rationale, against the actual cited pages fetched during this pass:
  - MM 2015-09-01 (Wayback 20251212010450, raw archive HTML): all quoted sentences located verbatim - SPY/2005 study sentence, first-trading-day monthly protocol, 16-delta put, "exiting at 50% of max profit", "taking a loss at 1x to 5x credit received", the hold-vs-manage comparison sentence, and the table-column list (P/L, % winners, avg P/L/day, avg trade P/L, largest drawdown).
  - MM 2016-07-14 (Wayback 20250114181357): "Our study was conducted in the SPY...", the 50/35/25/15 delta grid sentence, "taking a loss at 2x the credit received", "The table showed that managing the short puts greatly increased the P/L per day percentage.", and the Sosnoff max-risk quote - all located verbatim.
  - Skinny 2020-07-27 (Wayback 20240302110545): theta-slope 45-DTE rationale and 21-DTE gamma/portfolio-risk sentences located verbatim in body text; the "We enter trades at 45 DTE to maximize our returns from positive theta..." sentence located verbatim as the page's own meta/short description (page-authored, legitimately citable).
  - tastylive managing-winners concepts page (live): both 50%-management quotes located verbatim.
  - spintwig SPY short-put study (Wayback): all eight quoted findings/methodology strings located verbatim, including "30 delta +/- 3.5 delta, closest to 30", "45 DTE +/- 17, closest to 45", "50% max profit or when DTE = 21, whichever occurs first", "Entry Days: daily", "Entry Signal: N/A", "Timing: 3:46pm ET", "Early assignment never occurs", 20.77% commission figure, 54 backtests / >170,500 trades / 2007-01-03→2019-07-31, and the 20%-of-notional margin line; site symbol index confirms companion QQQ/IWM/AAPL/TSLA/AMZN studies exist.
  - projectoption management study (Wayback 20210731050616): all five quoted findings plus "Standard Expiration Closest to 45 Days to Expiration (resulted in trades between 30-60 days to expiration)", "Number of Contracts: 1", 41,600 trades, Jan 2007–May 2017, June 7 2017 publication - located verbatim.
  - financialtechwiz review (live, updated Aug 6 2024): the six-item criteria list located verbatim, including "Sell options with a 30 delta.", "Take profit when you collect 50% of the premium.", "Roll forward and don't change the strike price at 21 DTE to reduce gamma risk.", "Sell options when IV is high."
- **Correction applied:** section 3 previously claimed the 2016 delta study "repeats the same protocol sentence" (first-trading-day-of-month). It does not - the 2016 page states no entry cadence. Fixed in place; the monthly cadence now correctly rests on the 2015 study alone (parameter 9's citation was already 2015-only and is unaffected).
- **Confirmed-honest flags (spot-checked, correct as written):** 30Δ is NOT presented as a primary-study constant (SOURCE-RANGE with the 15–50 grid + secondary house-default + spintwig replication is exactly what the sources support); no stop-loss in the managed base arm matches spintwig's managed-variant definition; the roll-vs-close doctrine divergence is real and quoted accurately from both sides; the §6 "no verified CAGR/win-rate/PF/max-DD for the exact 30Δ managed variant" bottom line is accurate - the numeric tables are video-only (tastylive) or paywalled (spintwig).
- **Residual doubts:** (1) The tastylive live episode URLs now redirect to show landing pages - the studies survive only via Wayback; snapshots were readable today but are a single point of failure. (2) The per-variant numeric results were never published in readable text, so the strategy's edge magnitude rests on directional statements plus two independent replications' qualitative agreement - the shadow ledger remains the first trustworthy quantitative evidence. (3) spintwig's "No option strategy outperformed buy-and-hold SPY with regard to total return" is a verified quote that bounds expectations: the published edge claim is risk-adjusted/win-rate-shaped, not total-return dominance. (4) The live tastylive URL for the 2015 episode was not re-probed for the exact "content removed" wording; its removal is consistent with the 2016/2020 episodes redirecting to landing pages.

---

### Independent second verification pass - 2026-07-19 (fresh-context adversarial verifier)

- **Verdict: CORRECTED.** This pass was run with fresh context and NO trust in the verification entry above (which pre-existed and could not be attributed). Every source was independently re-fetched: the three tastylive episode pages via their cited Wayback snapshots (raw HTML downloaded and string-searched), the tastylive managing-winners concepts page and financialtechwiz review live, and the spintwig and projectoption studies via Wayback.
- **Result of constant-by-constant check (sections 3, 4, 8):** every SOURCE-VERBATIM and SOURCE-RANGE quote was located verbatim in its cited source - no invented constants. Confirmed independently: the 2015 monthly-cadence/16Δ/45-DTE protocol sentences, the 50%-of-max-profit and 1x–5x / 2x loss-arm strings, the 2016 50/35/25/15 delta grid (and the absence of any entry-cadence sentence on the 2016 page - the §3 correction is accurate), the 21-DTE gamma/portfolio-risk sentences (body text) and the 45-in/21-out sentence (page meta description only, as disclosed above), both managing-winners 50% quotes, the full financialtechwiz six-item criteria list including "Sell options with a 30 delta.", and all spintwig methodology strings ("30 delta +/- 3.5 delta, closest to 30", "45 DTE +/- 17", "50% max profit or when DTE = 21, whichever occurs first", "Entry Days: daily", "Entry Signal: N/A", "Timing: 3:46pm ET", "Early assignment never occurs", 20.77% commission, 54 backtests / 170,500+ trades / 2007-01-03→2019-07-31, 20%-of-notional margin, "Positions opened per trade: 1", datePublished 2019-06-10, companion QQQ/IWM/AAPL/TSLA/AMZN studies referenced on-page). projectoption: all five §6 findings plus the 30–60-DTE standard-expiration quote, 41,600 trades, January 2007–May 2017, June 7 2017 located verbatim.
- **Tag audit:** all ADAPTED rows (universe extension, entry time, roll policy) carry genuine adaptation rationale and none is presented as published; PLATFORM-POLICY rows are explicitly marked as ours; the [unverified] rumor bucket in §6 is honestly quarantined; 30Δ is correctly NOT claimed as a primary-study constant.
- **Corrections applied this pass:** (a) §1 previously claimed the live 2015 URL displays "The content you were looking for has been removed" - as of 2026-07-19 it instead resolves to the Market Measures show landing page with no error message; wording fixed (the substantive claim, that the episode content is gone from the live site and survives only on Wayback, stands).
- **Trivial non-correction noted:** projectoption's page renders "Number of Contracts : 1" (space before the colon); the brief quotes it as "Number of Contracts: 1" - content identical, left as-is.
- **Residual doubts (this pass):** same four as above, plus (5) the numeric performance tables remain unverifiable (video-only / paywalled), so §6's "no verified CAGR/win-rate/PF/max-DD for the exact 30Δ managed variant" line is the load-bearing honesty of this brief - do not let later summaries harden the directional claims into numbers.
