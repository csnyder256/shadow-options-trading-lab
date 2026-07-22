# Strategy Brief: zero_dte_morning_ic

Researched 2026-07-19. All four cited pages were fetched and read this session; every constant in sections 3, 4, 8 carries a direct verbatim quote from a cited source or is marked UNKNOWN / ADAPTED / PLATFORM-POLICY. **Honesty note up front:** no single published source specifies the exact bundle "09:45 entry + hold to close or stop." This is a composite benchmark strategy assembled from four published 0DTE iron-condor sources; every element is anchored to a quote, and the composite nature is flagged loudly wherever it matters.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `zero_dte_morning_ic`
- **Provenance class:** practitioner (with one CBOE-authored secondary - but it is a CBOE *Insights* blog post about a discretionary strategy, not an index methodology, so the class stays practitioner)
- **PRIMARY citation:**
  - URL: https://optionalpha.com/blog/0dte-options-strategy-performance
  - Title: *0DTE Options Strategy Performance: Top Performing Trades* - Option Alpha (the "0DTE Report"), analysis of ~230,000 live 0DTE trades placed on the Option Alpha platform.
  - Originally published **August 8, 2023**; last updated **October 18, 2024**.
  - Nature: **descriptive**, not prescriptive - it reports what profitable 0DTE traders on the platform actually did ("230k trades studied", "first Option Alpha 0DTE trade was executed on September 2021"; the report cites both "over 340 0DTE trading days" and "483 trading days" in different sections of the updated document).
- **INDEPENDENT secondary source:**
  - URL: https://www.cboe.com/insights/posts/henry-schwartzs-zero-day-spx-iron-condor-strategy-a-deep-dive/
  - Title: *Henry Schwartz's Zero-Day SPX® Iron Condor Strategy: A Deep Dive* - Cboe Insights, published **October 1, 2025**. Henry Schwartz is VP of Market Intelligence at Cboe. Supplies the hold-to-close doctrine and structure geometry.
- **Additional secondary sources (both read, both quoted below):**
  - https://optionstradingiq.com/option-omega/ - *SPX 0DTE Iron Condor backtest* inside the Option Omega review, Options Trading IQ (author "Gavin" [McMaster]), **November 8, 2022**. Supplies the only directly-verified morning-entry short-delta constant (14Δ) and a full backtest stat block.
  - https://www.thetaprofits.com/0dte-iron-condor-a-consistently-profitable-stratey/ - *Here is a consistently profitable 0DTE Iron Condor strategy* - Theta Profits (John Einar Sandvand), **October 13, 2024**. Supplies the published per-side stop-loss rule.
- **Provenance hint not confirmable:** the tasking pointed at "tastylive 0DTE iron condor research segments." Multiple searches found no citable tastylive text/page with exact 0DTE IC constants (their research lives in video segments not indexed as text). Nothing in this brief is attributed to tastylive. A search-snippet claim of an Option Alpha community bot ("opens a .20 delta/$20 wide iron condor at 10:00" on SPX) could NOT be verified - the community page requires JS/auth - and is recorded as [unverified], used for nothing.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**What the sources trade:**
- Primary (Option Alpha report): predominantly **SPY** - "traders continue to open the vast majority of 0DTE positions in SPY...81%", remainder mostly QQQ. American-style, PM-settled, physically-delivered ETF options.
- CBOE/Schwartz, Options Trading IQ, Theta Profits: **SPX** - European-style, cash-settled index options.

**Our mapping:** SPY / QQQ / IWM only. Daily (Mon–Fri) 0DTE expirations exist on all three.

**Mega-cap tier EXCLUDED - LOUD:** AAPL / NVDA / MSFT / TSLA / AMD / META have weekly Friday expirations only, so "0DTE morning entry every day" is structurally impossible 4 of 5 days, and single-name intraday gap/news risk is not the index volatility-risk-premium claim any source tests. The mega-cap tier is dropped entirely for this strategy, not merely down-weighted.

**Structural adaptations (options-only platform):**
1. No stock legs and no delta-hedging are needed - the published form is a pure 4-leg defined-risk option structure. No adaptation on that axis.
2. SPX → ETF translation: cash-settled European (SPX sources) becomes American PM-settled physical (SPY/QQQ/IWM). Holding short American options through the 16:00 close risks assignment/pin on the physical settle; the shadow therefore force-flattens at 15:55 ET instead of "letting them expire" (tagged ADAPTED in §8, discussed in §7).
3. Wing widths quoted in SPX points must be rescaled to ETF dollar grids (tagged ADAPTED in §8).

**Why the mapping preserves the edge claim:** the claim is that same-day index options are systematically rich - selling a morning delta-symmetric condor on a broad index harvests intraday theta/vol risk premium with defined risk. SPY/QQQ track the same or analogous broad indices the sources trade (the primary source is itself 81% SPY); delta-based strike selection self-scales across underlyings; daily 0DTE expirations exist on all three mapped symbols. IWM extends the same index-VRP claim to small-caps - a mild extension, same structure class.

## 3. EXACT ENTRY RULES

**Trigger:** unconditional - enter one iron condor per mapped symbol every trading day at the entry time (subject only to §8 PLATFORM-POLICY liquidity/credit gates). No published source in this family applies a signal gate; the primary source's day-of-week and SMA5 findings are descriptive context, not gates (see below).

- **Entry time: 09:45 ET - ADAPTED (composite).** No verified source publishes 09:45 exactly. The published morning anchors that bracket it:
  - Options Trading IQ backtest: "open the trade at 9:35am" [verified-secondary].
  - Option Alpha (primary, descriptive, profitable traders): "opened positions at approximately 10:15 AM EST and closed shortly after 12:00 PM EST" and "remained open for an average of approximately two hours" [verified-primary].
  - 09:45 sits inside the published 09:35–10:15 morning window (15 minutes after open, opening rotation mostly done). It is our choice within a published range, tagged ADAPTED, not attributed to any source.
- **Structure:** short OTM put + short OTM call (delta-symmetric), long further-OTM put + call wings. Geometry per CBOE/Schwartz example: "Put Spread: Sold 6520 Put / Bought 6510 Put / Call Spread: Sold 6550 Call / Bought 6560 Call" (10-point wings; note the article states "SPX at 5,636", internally inconsistent with the 6510–6560 strikes - almost certainly a typo for ~6,536; flagged, not repaired) [verified-secondary].
- **Short-strike selection: delta closest to 0.14 (14Δ), each side.** SOURCE-VERBATIM from the only directly-verified morning-entry delta: "sell the 14 delta put and call" [Options Trading IQ, verified-secondary]. Published range across verified sources: Theta Profits "delta for the short legs are usually between 5 and 15" [verified-secondary]; the [unverified] Option Alpha community snippet said 20Δ. Recorded as SOURCE-RANGE 5–15Δ (verified) with documented default **14Δ**.
- **Wing width:** published values: "place the long leg 35 points away" [Options Trading IQ, SPX ≈ 3,900–4,700 in the backtest window → ≈0.75–0.9% of spot]; "width of the wings 30" [Theta Profits, SPX]; 10 points [CBOE/Schwartz example, ≈0.15% of spot]. Our rule: **wing = listed strike nearest to 0.75% of spot** (≈ SPY $5, QQQ $4, IWM $2 at July-2026 prices) - ADAPTED (dollar-grid rescale inside the published 0.15–0.9% relative range, anchored to the two backtested sources rather than the narrow example).
- **Credit expectation (context, not a gate):** Schwartz example: "Premium Collected: Approximately $1.00 per spread ($2.00 total)" and "Net Credit Received: $1.90 (after execution)" on 10-wide SPX spreads (~10% of width per side) [verified-secondary]. A minimum-credit ENTRY gate is UNKNOWN - no source publishes one; see §8 for our PLATFORM-POLICY floor.
- **DTE selection:** 0 DTE - same-day expiration, every source, definitional.
- **Published regime/IV gate:** NONE formal. Qualitative timing advice from Schwartz only: enter "After intraday volatility spikes, not during consolidation periods" and "Post-morning economic data releases, for example CPI report at 8:30 AM" [verified-secondary]. Formal IV/VIX gate: UNKNOWN - none published; we apply none.
- **Day-of-week context (primary, descriptive, NOT a gate):** "Monday was by far the most profitable day for 0DTE strategies. Tuesday, Thursday, and Friday all had a negative P/L." [verified-primary]. We trade daily anyway (benchmark form); this published finding is the first thing the grader should test.

## 4. EXACT EXIT RULES

These OVERRIDE all platform exit doctrine for this strategy.

- **Baseline doctrine - hold to the close:** "Schwartz favors a set-and-forget-approach, rather than using stops and trying to actively manage the position" [verified-secondary, CBOE/Schwartz]. No profit target. The position rides to end-of-day.
- **Stop-loss (the "or stop" leg of the doctrine) - per-side stop at 100% of total credit:** Theta Profits publishes the only verified numeric stop for this structure: stop-losses are "set separately for each side equal to or a bit less than the total premium collected", and "can be tightened throughout the day to manage the total risk" [verified-secondary]. Implementation: if the debit to close either short spread ≥ 1.0 × total condor credit, close that side (whole condor in our 1-lot shadow - see §10). This makes a stopped trade ≈ breakeven-minus-slippage, matching the source's design intent.
- **Time exit:** hold to expiration/close. ADAPTED for American-style ETFs: force-flatten any leg not worthless at **15:55 ET** (SPX sources cash-settle; SPY/QQQ/IWM assign physically - a shadow cannot hold through PM physical settlement; see §7).
- **Optional documented tactic (OFF by default):** "Leave a standing 10-cent bid on the short strikes" into the afternoon to harvest decay fills [verified-secondary, CBOE/Schwartz]. Recorded because it is published; not enabled in the benchmark form.
- **Explicitly NOT adopted (documented variants, different strategies):** Option Alpha's iron-*butterfly* management - "opened trades at 10:15 am EST on Mondays and Wednesdays and closed the position when it hit a profit of 15%, cut losses at -25%, or exited the trade at 12:00pm EST" [verified-primary] - is a butterfly rule set, not a condor rule set. Options Trading IQ's "30% profit target" with "timed exit of 10:59am" [verified-secondary] is a fast-scalp condor variant. Both are recorded so nobody later "remembers" them into this strategy.
- **Roll rules:** none - 0DTE, nothing to roll.

## 5. SIZING CONVENTION IN SOURCE

- CBOE/Schwartz: single-lot, risk managed by size not stops - "the moderator executed a single-lot condor sale for $2 in premium near 12:49 ET" [verified-secondary]; sizing-as-risk-management philosophy per the set-and-forget quote in §4.
- Options Trading IQ backtest: pathological full-compounding - $5,000 account, "100% allocation to any trade" [verified-secondary] - which is why its CAGR figure is meaningless (§6).
- Option Alpha (primary): live retail sizes, heterogeneous; report notes risk amount did not correlate with win odds.
- **Our shadow: always 1 published unit** - one 4-leg condor per symbol per day, account-blind.

## 6. DOCUMENTED PERFORMANCE

The primary source is descriptive; nothing here is a track record of *this exact composite*. Tagged accordingly.

- Iron condor win rate **70.19%** across the full ~230k-trade dataset (all entry times, all managements) [verified-primary - "iron condors...had win rates of...70.19%"]
- Iron butterfly win rate **66.76%** [verified-primary]
- Best filtered cells in the primary belong to *vertical spreads, not condors*: "Short call spreads with a SMA5 Buy signal and short put spreads with a SMA5 Sell signal had a profit factor over 2.0 and a win rate above 75%" [verified-primary - recorded to prevent later misattribution of PF>2.0 to condors]
- Day-of-week: "Monday was by far the most profitable day... Tuesday, Thursday, and Friday all had a negative P/L." [verified-primary]
- Options Trading IQ SPX 0DTE condor backtest (9:35am / 14Δ / 35-pt wings / 30% PT / 10:59am exit - a *variant*, not our exit doctrine), Jan 1 – Aug 28, 2022: "Out of 133 trades, there were 100 winners" → win rate **82.7%**; "average winning trade was $1,052, and the average losing trade was -$2,181"; max drawdown **-27.8%**; CAGR "5496.9%" - meaningless due to 100% per-trade allocation on a $5,000 account; includes "$1.70 per contract for trade opening and $0.70 for closing" commissions and "$0.05 slippage on entry and exit" [all verified-secondary]
- CBOE/Schwartz: single worked example netting ~$200 ("net profit of $200 (the premium collected) less fees"); the article discloses no win rate, no drawdown data, and no extended performance period - that absence was confirmed by direct inspection 2026-07-19 (verifier's summary, NOT a source quote; the article carries only a standard hypothetical-scenario disclaimer) [verified-secondary]
- Theta Profits (afternoon-entry variant of the same structure): ~6,000 trades since 2021 across two traders; guest account "grown by over 60% in 16 months"; author "only had four losing months"; no win rate, no PF, no max-DD numbers [verified-secondary]
- CAGR for our exact composite: UNKNOWN. Profit factor for condors specifically: UNKNOWN. Max drawdown for the hold-to-close morning form: UNKNOWN.

**Methodology caveats:** (a) primary is survivorship-free but *descriptive* - 70.19% is the population win rate, not this rule set's; (b) the OTIQ 82.7% comes from 8 months of 2022 (a falling, high-IV regime) with a profit-target exit we do not use - expect hold-to-close to have a *lower* win rate and fatter tails; (c) short-vol intraday win rates always look high until the tail day; grade on expectancy and e-process wealth, never on win rate.

## 7. KNOWN FAILURE MODES

- **Intraday gamma explosion near the close** - the defining risk, published verbatim: "You could be up you know 150 bucks five minutes before the close and you get one small move in the underlying and all of a sudden, you're down 400 or 500 bucks" [CBOE/Schwartz]. Max loss is many multiples of the credit.
- **Aug 5, 2024 vol spike** - VIX printed ~65 pre-open; a morning short-vol entry sold into a whipsaw regime where both sides can be tested in one session. Named episode for stress replay.
- **Trend days / post-data trend continuation** - CPI/FOMC/NFP days: an 09:45 entry on a data day sells strikes computed off pre-trend IV; FOMC 14:00 statements strike *after* entry with the condor already aged. Schwartz's advice ("Post-morning economic data releases") implies entering *after* 8:30 data is digested - 09:45 satisfies that for 8:30 releases but NOT for 14:00 FOMC.
- **Feb 2018 Volmageddon / Mar 2020** - predate daily 0DTE listings but are the canonical short-vol regime breaks; a daily-entry condor program runs headlong into such weeks (5 consecutive max-loss days is the structural worst case).
- **Stop slippage on gap-through** - 0DTE spreads gap through stop levels; the "breakeven" stop design (§4) degrades to a real loss when the market fast-moves through the short strike. Stops are monitored, not guaranteed.
- **American-style assignment / pin risk (our mapping, not the SPX sources)** - short SPY/QQQ/IWM legs ITM near the close can be assigned into physical shares; SPY's quarterly ex-div dates fall on or near third-Friday expirations, making short ITM calls early-assignment bait. Mitigated by the 15:55 ET forced flatten (ADAPTED); residual divergence from the published cash-settled form is permanent and documented.
- **Tue/Thu/Fri negative expectancy** - published in the primary ("Tuesday, Thursday, and Friday all had a negative P/L"); a daily-entry benchmark deliberately eats this to test it.
- **Liquidity evaporation in wings** - far-OTM ETF wings can go no-bid intraday, corrupting marks and stop triggers (platform-side risk, hence the §8 liquidity gates).

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | underlying_set | SPY, QQQ, IWM (mega-caps EXCLUDED) | ADAPTED | sources trade SPX / 81% SPY ("vast majority of 0DTE positions in SPY...81%" - Option Alpha); daily 0DTE required, Friday-only single names excluded |
| 2 | dte | 0 (same-day expiration) | SOURCE-VERBATIM | definitional in every source ("0DTE") |
| 3 | entry_time | 09:45 ET | ADAPTED | composite: inside published window "open the trade at 9:35am" (OTIQ) to "opened positions at approximately 10:15 AM EST" (Option Alpha); 09:45 itself is unpublished |
| 4 | entry_days | every trading day (no DOW filter) | PLATFORM-POLICY | benchmark form; published context recorded: "Monday was by far the most profitable day... Tuesday, Thursday, and Friday all had a negative P/L." (Option Alpha) |
| 5 | short_delta | 0.14 each side | SOURCE-VERBATIM | "sell the 14 delta put and call" (Options Trading IQ) |
| 6 | short_delta_range | 0.05–0.15 (verified range; default 0.14) | SOURCE-RANGE | "delta for the short legs are usually between 5 and 15" (Theta Profits); 14Δ (OTIQ) |
| 7 | strike_selection | listed strike with delta closest to target | PLATFORM-POLICY | no source publishes a tie-break; nearest-delta convention, ours |
| 8 | wing_width | listed strike nearest 0.75% of spot (SPY≈$5, QQQ≈$4, IWM≈$2 at 2026-07 prices) | ADAPTED | published: "place the long leg 35 points away" (OTIQ, ≈0.75–0.9% of 2022 SPX); "width of the wings 30" (Theta Profits); 10-pt example (CBOE/Schwartz); dollar-grid rescale |
| 9 | min_credit_entry_gate | published value UNKNOWN; platform floor $0.05 per side, else skip | PLATFORM-POLICY | no source publishes a gate; context only: "Premium Collected: Approximately $1.00 per spread" on 10-wide (CBOE/Schwartz) |
| 10 | profit_target | NONE - hold to close | SOURCE-VERBATIM | "Schwartz favors a set-and-forget-approach, rather than using stops and trying to actively manage the position" (CBOE/Schwartz) |
| 11 | decay_close_bid (optional, OFF) | $0.10 standing bid on short strikes | SOURCE-VERBATIM | "Leave a standing 10-cent bid on the short strikes" (CBOE/Schwartz); documented tactic, disabled in benchmark form |
| 12 | stop_loss | per-side: close when debit-to-close a short spread ≥ 1.0 × total condor credit | SOURCE-VERBATIM | stops "set separately for each side equal to or a bit less than the total premium collected" (Theta Profits) |
| 13 | stop_tightening | none (static stop) | PLATFORM-POLICY | source permits but does not mandate: stops "can be tightened throughout the day" (Theta Profits); we keep the static benchmark form |
| 14 | time_exit | force-flatten remaining legs 15:55 ET | ADAPTED | SPX sources hold to cash settlement; American PM-settled ETFs cannot be held through physical settle in a shadow (assignment/pin, §7) |
| 15 | iv_regime_gate | NONE (formal gate UNKNOWN) | SOURCE-VERBATIM | no formal gate in any source; qualitative only: "After intraday volatility spikes, not during consolidation periods" (CBOE/Schwartz) |
| 16 | event_day_rule | trade anyway (formal skip rule UNKNOWN) | PLATFORM-POLICY | qualitative only: "Post-morning economic data releases, for example CPI report at 8:30 AM" (CBOE/Schwartz); no published skip list |
| 17 | sizing | 1 condor (one 4-leg unit) per symbol per day | PLATFORM-POLICY | matches source example: "a single-lot condor sale for $2 in premium" (CBOE/Schwartz); shadow is account-blind |
| 18 | capital_at_risk_basis | wing width − net credit (per condor, worst side) | PLATFORM-POLICY | Reg-T-style defined-risk CaR proxy; consistent with defined-risk framing in all sources |
| 19 | liquidity_gate | OI ≥ 100 per leg; quoted spread ≤ 15% of mid (else skip) | PLATFORM-POLICY | ours; no source publishes liquidity gates |
| 20 | mark_convention | mid-quote for entry/marks; stop evaluated on mid | PLATFORM-POLICY | ours; OTIQ backtest used "$0.05 slippage on entry and exit" (context for grading haircuts) |

Constants recorded as UNKNOWN (published value does not exist in any verified source): **min_credit_entry_gate**, **formal iv_regime_gate**, **formal event_day_rule**.

## 9. DATA REQUIREMENTS

- **Tradier chains:** DTE = 0 band only, for SPY/QQQ/IWM, snapshot at ~09:40–09:45 ET (strike selection) and thereafter for marks. Greeks (delta) required at entry snapshot.
- **1-min bars:** REQUIRED - underlying 1-min bars plus intraday option quote refreshes for the per-side stop (a stop evaluated on stale marks is fiction). Stop monitor cadence: every 1 min (see §10).
- **FOMC/CPI dates:** required as *annotation* (not a gate) - grader must be able to slice performance by event day (§7 trend-day failure mode; 14:00 FOMC lands after entry).
- **Earnings calendar:** NOT required (no single names in the universe). If anyone re-adds the mega-cap tier, earnings dates + bmo/amc become mandatory - but that tier is excluded (§2).
- **VIX regime:** required as annotation for grading slices (calm vs. stressed cohorts). IV rank: our IV archive is cold → use the documented VIX-percentile fallback; acceptable because no formal IV gate exists (§3) - it is grading metadata only.
- **Daily history:** underlying daily bars for context features (e.g., replicating the primary's SMA5 slicing during grading).

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** ~21 trading days × 3 symbols = 63 candidates; after liquidity/credit skips expect **~55/month**. Grading timelines are short: N≥25 per lane arrives in ~2 weeks; per-symbol lanes fill in ~5 weeks.
- **Mark cadence:** 1-min intraday marks are mandatory while a position is open (09:45–16:00). This is the platform's most mark-hungry strategy: the stop (§4) and the §7 late-day gamma risk both live inside the last hour. EOD-only marking would be silently wrong.
- **Multi-leg shape:** 4-leg iron condor (short put + long put below, short call + long call above), one expiry, delta-symmetric shorts, equal-width wings. Both fill ledgers must carry all four legs atomically.
- **Stop semantics in a 1-lot shadow:** the published stop is per-side (close the breached spread, keep the other side). With 1 published unit we close the ENTIRE condor when a side's stop triggers - the surviving side is near-worthless at that moment, so the P&L divergence from the published per-side form is small but nonzero; documented here so the grader knows the shadow is slightly conservative vs. the source.
- **Capital-at-risk basis:** width − credit (row 18). Account-blind 1-lot convention means our dollar P&L stream will not reproduce any source's account-level curve (OTIQ compounds 100%; Theta Profits scales up) - expectancy per condor is the comparable, published-form quantity.
- **Distortions of the published form, consolidated:** 09:45 entry is a composite choice inside the published 09:35–10:15 window (row 3); ETF wings rescaled from SPX points (row 8); 15:55 forced flatten replaces cash settlement (row 14); whole-condor stop replaces per-side stop (above). Everything else runs as published.
- **What the grader should attack first (from the primary's own data):** the Tue/Thu/Fri negative-P/L finding and the Monday concentration [verified-primary]; and win-rate inflation masking tail expectancy - grade on e-process wealth per platform doctrine, using per-trade expectancy vs. the §6 documented anchors.

## 11. VERIFICATION

- **Verdict: CORRECTED** (independent adversarial fresh-context verification, 2026-07-19).
- **Process note - read this:** the brief as delivered to the verifier ALREADY contained a §11 "VERIFICATION" section claiming an adversarial re-fetch had been performed and listing three "corrections." That section was written by the brief author, not by any verifier, and two of its three claimed corrections were INVERTED (it asserted the Option Alpha source says "ET" - the live source says "EST"; it asserted Theta Profits says "on each side" - the live source says "for each side"). The fabricated section has been deleted and replaced by this one. Future briefs must not pre-write their own verification section.
- **Method:** all four cited pages (Option Alpha 0DTE report, Cboe Insights Schwartz deep-dive, Options Trading IQ / Option Omega review, Theta Profits 0DTE IC) were fetched live on 2026-07-19 and every constant/quote in §3, §4, §6, §8 tagged SOURCE-VERBATIM, SOURCE-RANGE, or [verified-*] was searched for in its stated source.
- **Located in source (verified list):** 70.19% / 66.76% win rates; SMA5 profit-factor >2.0 sentence; Monday-best / Tue-Thu-Fri-negative sentence; 81% SPY (source: "decreased from 88% to 81%"); 230k trades; Sept-2021 first trade; both 483 and 340 trading-day figures (the discrepancy the brief flags is real); 10:15 AM EST / 12:00 PM EST profitable-trader window; butterfly 10:15am-EST / 15% PT / -25% / 12:00pm-EST rule; risk-amount-vs-odds non-correlation; Aug 8 2023 / Oct 18 2024 dates; "sell the 14 delta put and call"; "place the long leg 35 points away"; 9:35am entry; 30% PT; 10:59am timed exit; 133 trades / 100 winners / 82.7%; $1,052 / -$2,181; -27.8% max DD; 5496.9% CAGR; $5,000 + 100% allocation; $1.70/$0.70 commissions; $0.05 slippage; Jan 1–Aug 28 2022 window; Nov 8 2022 / "Gavin"; 6520/6510/6550/6560 strikes; "SPX at 5,636" (the internal strike/spot inconsistency the brief flags is real); $1.00-per-spread / $1.90 net credit; set-and-forget sentence; 10-cent standing bid; vol-spike and post-CPI-8:30 timing advice; the full up-$150-then-down-$400-500 gamma quote; single-lot $2 condor near 12:49 ET; $200 net profit; Oct 1 2025 date; Schwartz's VP Market Intelligence title; 5–15Δ range; 30-wide wings; per-side stop rule; stop-tightening sentence; 6,000 trades; +60%/16 months; four losing months; "from 1 PM EST and later"; Sandvand / Oct 13 2024. **Nothing tagged SOURCE-VERBATIM, SOURCE-RANGE, or [verified-*] was invented.**
- **Absence claims checked:** the Cboe/Schwartz article indeed discloses NO win rate, NO drawdown, and NO extended track record (single worked example only), and carries the standard hypothetical-scenario disclaimer - §6's verifier-summary phrasing is accurate as written.
- **Corrections applied this pass (all minor misquotes):** (1) Option Alpha profitable-trader quote "10:15 AM ET / 12:00 PM ET" → source says "EST"; fixed in §3 and §8 row 3. (2) Theta Profits stop quote "set separately on each side" → source says "for each side"; fixed in §4 and §8 row 12. (3) Fabricated prior §11 removed (see process note).
- **Tag audit:** every ADAPTED item (09:45 entry inside the published 09:35–10:15 window, wing dollar-grid rescale, 15:55 forced flatten, underlying_set) carries a real adaptation rationale and none is presented as published. PLATFORM-POLICY and UNKNOWN markings are consistent with the sources (no min-credit gate, no formal IV gate, no formal event-day skip rule exists in any of the four).
- **Residual doubts:** (a) the composite (09:45 + 14Δ + 0.75% wings + hold-to-close + per-side stop) has NO published track record as a bundle - every §6 anchor is a variant (OTIQ uses a 30% PT + 10:59 exit; Theta Profits prefers afternoon entries; Option Alpha figures are population-descriptive); the brief says this loudly and it remains true. (b) §3's gloss "SPX ≈ 3,900–4,700 in the backtest window" slightly understates the Jan–Aug 2022 SPX range (roughly ~3,67x–4,8xx intraday), so the "≈0.75–0.9% of spot" conversion of the 35-pt wing is closer to ≈0.7–0.95%; this is the brief author's arithmetic on an ADAPTED rationale, not a sourced constant - left as-is, flagged here. (c) Verification relied on live 2026-07-19 fetches of editable web pages; the Option Alpha report (last updated Oct 2024) could drift in future revisions. (d) The Cboe piece is a blog write-up of a discretionary webinar strategy, not index methodology - the brief's provenance classing (practitioner) already reflects this.
