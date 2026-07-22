# Strategy Brief: pead_debit_spread

Post-earnings-announcement-drift (PEAD) expressed as a directional debit vertical, 14-30 DTE, direction taken from the sign of the EPS surprise.

Researched 2026-07-19. Every constant in sections 3, 4, 8 carries a source quote or is marked UNKNOWN. The options expression is an ADAPTATION of an equity anomaly - read section 2 before trusting any edge claim.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `pead_debit_spread`
- **Provenance class:** academic (signal) + practitioner (options expression). The underlying anomaly is one of the most-replicated results in empirical accounting; the debit-vertical expression is NOT in the academic source and is documented only in practitioner material.
- **PRIMARY citation (signal):** Bernard, V.L. and Thomas, J.K. (1989), "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?", *Journal of Accounting Research*, Vol. 27 (Supplement), pp. 1-36.
  - URL: https://www.jstor.org/stable/2491062 (journal record; also https://ideas.repec.org/a/bla/joares/v27y1989ip1-36.html)
  - **Access honesty note:** the full text is paywalled (JSTOR; the old Yale-hosted PDF returns HTTP 410). I could NOT read the primary directly. All magnitudes attributed to Bernard & Thomas below were verified in the full text of the Fink (2020) review and the Gow & Ding textbook replication chapter, both read in full, and are tagged [verified-secondary], never [verified-primary].
- **INDEPENDENT secondary sources (all read for this brief):**
  1. Fink, J. (2020), "A Review of the Post-Earnings-Announcement Drift", University of Graz Working Paper 2020-04 (published 2021 in *Journal of Behavioral and Experimental Finance* 29, 100446). URL: https://static.uni-graz.at/fileadmin/sowi/Working_Paper/2020-04_Fink.pdf - full text extracted and read.
  2. Katz, J.N., McCubbins, M.D., McMullin, J.L. (2018), "The Post-Earnings Announcement Drift: An Anomalous Anomaly", working paper. URL: https://jkatz.caltech.edu/documents/28622/peads.pdf - full text extracted and read (important cautionary source).
  3. Gow, I. & Ding, T., "Empirical Research in Accounting: Tools and Methods", ch. 14 "Post-earnings announcement drift" (B&T replication). URL: https://iangow.github.io/far_book/pead.html
  4. Quantpedia, "Post-Earnings Announcement Effect". URL: https://quantpedia.com/strategies/post-earnings-announcement-effect (codified trading rules + independent backtest of the Brandt et al. SUE+EAR variant)
  5. Wikipedia, "Post-earnings-announcement drift". URL: https://en.wikipedia.org/wiki/Post%E2%80%93earnings-announcement_drift
- **PRIMARY citation (options expression):** OptionsPilot blog, "Post-Earnings Drift: How to Trade the Continuation With Options", dated April 8, 2026. URL: https://optionspilot.app/blog/post-earnings-drift-options-trading-strategy - read in full; this is a low-authority practitioner source and is treated as a *template*, not as validated doctrine. Its constants are quoted verbatim where used.
- **Publication dates:** 1989 (anomaly); 2020/2021 (review); 2026-04-08 (options expression).

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**What the source trades.** Bernard & Thomas trade CASH EQUITY portfolios: "The PEAD trading strategy prescribes buying (selling) portfolios of firms that release extremely positive (negative) earnings news (unexpected quarterly earnings surprise)" (Katz et al. 2018, p.1, describing B&T). Universe = broad NYSE/AMEX (later studies add NASDAQ) across ALL firm sizes; the Quantpedia codification: "All stocks from NYSE, AMEX, and NASDAQ except financial and utility firms and stocks with prices less than $5." It is a long/short DECILE PORTFOLIO of hundreds of names, held simultaneously.

**Our mapping.** Single-name liquid mega-caps only: AAPL / NVDA / MSFT / TSLA / AMD / META tier. **SPY/QQQ/IWM are EXCLUDED - ETFs have no earnings announcements; PEAD does not exist for them.** Direction from the sign of the consensus-EPS surprise at each name's quarterly report; expression = defined-risk debit vertical (bull call spread on beat, bear put spread on miss).

**LOUD ADAPTATION WARNINGS (three separate distortions):**
1. **Equity → options.** The published anomaly is a cash-equity return drift. No academic source specifies any option structure. The debit vertical caps the payoff (truncates the drift tail that drives the published mean), adds theta cost, and adds spread-crossing costs on 2 legs x 2 sides. Every option-layer constant below is tagged ADAPTED or comes from the practitioner article.
2. **Portfolio → single names.** The published 18%-annualized number is a ~200-400 name long/short portfolio average. Katz et al. (2018) show this does not translate to single positions: "disaggregated PEADs are highly heterogeneous and highly variable over time" and "practically all firm-specific drifts do not follow the portfolio drift path." Our 1-lot single-name trades sample the noisy firm-level distribution, not the portfolio mean.
3. **All-caps → mega-caps.** Fink (2020), Observation 4: "The strength of the PEAD is inversely related to firm size." Our universe is the WEAKEST documented cohort for this anomaly (best information environments, most analyst coverage, lowest frictions). The edge claim survives in sign (PEAD "can be observed across all firm sizes" - Fink 2020) but is documented to be smallest exactly where we trade.

Why the mapping is still defensible for a shadow book: mega-caps are the only names where 14-30 DTE verticals have penny-tight chains; the shadow's purpose is to measure whether any post-earnings continuation survives in this cohort at options-level costs, not to replicate the academic portfolio.

## 3. EXACT ENTRY RULES

**Trigger - earnings surprise sign and size.**
- Published academic formation (recorded for provenance, we adapt it): firms sorted into SUE deciles, "prior research typically identifies SUE decile cutoffs based on the distribution of SUE in the prior quarter... Firm-quarters where the SUE measure is above the 90th percentile cutoff are part of the 'Good News' portfolio. Firm-quarters where the SUE measure is below the 10th percentile cutoff are part of the 'Bad News' portfolio" (Katz et al. 2018, sec. 5 "Data"; locator corrected from "sec. 3" during verification). B&T's expectation model: "Foster, Olsen, and Shevlin (1984) and Bernard and Thomas (1989) estimate expected earnings as a seasonal random walk (i.e., earnings from the prior year's same quarter are used for estimate of expected quarterly earnings)" (Katz et al. 2018); Gow & Ding: expected earnings from "Model 5 of Foster (1977)".
- Our tradable trigger (ADAPTED - a 6-name universe cannot form deciles): consensus-EPS % surprise with the practitioner threshold. OptionsPilot: "Positive surprises: Stocks that beat expectations by 5%+ outperform the market by an average of 2-4% over the next 60 days"; "Negative surprises: Stocks that miss by 5%+ underperform by 3-5% over the next 60 days". → **Enter long-call vertical if actual EPS ≥ consensus × 1.05; long-put vertical if actual EPS ≤ consensus × 0.95.** (Sign convention for negative-EPS quarters: UNKNOWN in all sources - platform must treat |consensus| < $0.05 quarters as no-trade.)
- Gap requirement: the published stop (section 4) is defined in units of "the earnings gap", so a measurable gap must exist. No source publishes a minimum gap - UNKNOWN. Platform policy: require |earnings-day open vs. prior close| ≥ 1% or skip.

**Entry timing.**
- OptionsPilot: "Entry: Day 2-3 after earnings. Skip day 1 - too volatile, wide spreads."
- Quantpedia codification of the academic strategy agrees on delay: the investor "goes long ... the second day after the actual earnings announcement and holds the portfolio one quarter (or 60 working days)."
- → **Enter on trading day T+2 (default) to T+3, where day T+1 is the first session that prices the announcement** (BMO report → that same day is T+1; AMC report → next session is T+1; this convention is PLATFORM-POLICY, no source states it). Time of day: UNKNOWN in every source; platform default 10:30 ET.

**Strike selection.** UNKNOWN - the practitioner source gives no rule: verified by direct question against the article text - "No strike-selection rule stated. The article provides only worked examples." The two worked examples are: "Buy $137/$147 call spread (30 DTE) for $3.80. Max profit: $6.20 (163% return)." and "Buy $9.50/$8.50 put spread (30 DTE) for $0.38. Max profit: $0.62 (163% return)." Both examples pay a debit of exactly 38% of the spread width. ADAPTED default (loudly ours, reverse-engineered from those two examples only): buy the nearest-to-ATM long strike in drift direction, choose the short strike so the debit lands 30-45% of width; reject if no width satisfies this.

**DTE.** Both source examples use 30 DTE ("call spread (30 DTE)", "put spread (30 DTE)"). Our band 14-30 DTE (target the listed expiry nearest 30, floor 14) is ADAPTED to the platform's chain-fetch band; the floor has no source.

**Regime / IV gate.** None published - UNKNOWN. The practitioner rationale for the structure is entering *after* the crush, not gating on it: "Options are the ideal vehicle to capture this drift because IV has already crushed, making directional options cheap." No numeric IV threshold exists in any source consulted. No VIX gate published.

## 4. EXACT EXIT RULES (override platform exit doctrine for this strategy)

All from OptionsPilot (the only source that publishes exits for an options expression); the academic holding period is recorded for context.

1. **Profit target:** exit at +100% return on debit (platform default = conservative end of the published range). Source: "Exit: 15-25 days after entry, or when the stock reaches resistance, or when you hit your profit target (typically 100-150% return on the spread)." The 100-150% is a SOURCE-RANGE; no default is documented; we pick 100%.
2. **Stop / thesis invalidation:** "Stop: Close the spread if the stock gives back 50% of the earnings gap. The drift thesis is dead at that point." → close the spread at the underlying's first observed retrace through (gap_open_price − 0.5 × gap_size) for longs (mirror for puts). This is an UNDERLYING-price stop, not an option-mark stop.
3. **Time exit:** "Exit: 15-25 days after entry..." SOURCE-RANGE, no documented default; platform picks the upper bound - flat close at 25 calendar days after entry if neither target nor stop has hit.
4. **Discretionary leg DROPPED:** "...or when the stock reaches resistance" is not mechanizable; we do not implement it. Flagged as a deliberate omission, which makes our exits slightly later than the published discretionary version.
5. **Expiry guard (PLATFORM-POLICY, no source):** if still open at 5 DTE, close. A 30 DTE entry held 25 days reaches ~5 DTE naturally, so this only binds for shorter entries within the 14-30 band.
6. **No roll rules published.** No source describes rolling this structure - none implemented.
7. Academic context (not implementable inside a 30 DTE option): the documented drift horizon is "the 60 days subsequent to the earnings announcement" / "the typical holding period examined is usually over the next quarter, or three months" (Katz et al. 2018). Our expression harvests at most the first ~half of the documented drift window - ADAPTED truncation, tagged in section 8.

## 5. SIZING CONVENTION IN SOURCE

- Academic: zero-investment long/short decile portfolios ("Buying the positive news portfolio and selling short the negative portfolio" - Katz et al. 2018), equal-weighted within decile (Quantpedia: "equal weighting within quintiles" for the Brandt et al. variant). No per-position sizing - it is a portfolio construct.
- Practitioner: "Size: 2-3% of account per drift trade."
- **Ours:** always 1 published unit = 1 debit vertical (1 lot x 2 legs), account-blind per platform convention. Recorded for context only.

## 6. DOCUMENTED PERFORMANCE

All academic numbers below are for the EQUITY long/short portfolio anomaly, NOT for any options expression. No source documents performance of the debit-vertical expression - that number is UNKNOWN and is precisely what this shadow lane will measure.

- "a strategy of zero-investment portfolios, long (short) in stocks with the most positive (negative) earnings surprise, can generate annualized abnormal returns of 18% (Bernard and Thomas, 1989)" - [verified-secondary] (Fink 2020, read in full text).
- "The results of Bernard and Thomas (1989) show a positive (negative) drift of around 2% over 60 trading days for the good (bad) news stocks. This amounts to about 4% (18%) in abnormal quarterly (annualized) excess returns." - [verified-secondary] (Fink 2020).
- "Buying the positive news portfolio and selling short the negative portfolio earns annual returns between 10% and 25%." - [verified-secondary] (Katz et al. 2018, summarizing the literature).
- Top-minus-bottom SUE decile spread "is positive in 41 of the 48 quarters from 1974 to 1985 and in 11 of the 16 quarters in which returns on the NYSE index are negative" - [verified-secondary] (Wikipedia summary of B&T 1989; wording corrected to verbatim during verification).
- Quantpedia independent backtest of the SUE+EAR quintile variant (Brandt, Kishore, Santa-Clara, Venkatachalam, "Earnings Announcements are Full of Surprises"): annual return 15%, max drawdown −11.2%, period 1987-2004, quarterly rebalanced, "most of the returns come from the long side" - [verified-secondary] (Quantpedia page; their backtest, not B&T's; wording corrected to verbatim during verification).
- Attenuation: the high-low SUE spread "has decreased substantially from the 1980s/1990s (about 5%) to the late 2010s (3% or lower)" - [verified-secondary] (Wikipedia; wording corrected to verbatim during verification); "there is also evidence that the magnitude of PEAD returns has been declining (Chordia et al., 2014; Martineau, 2019; Richardson et al., 2010)" - [verified-secondary] (Fink 2020).
- Practitioner drift-size claims: 5%+ beats "outperform the market by an average of 2-4% over the next 60 days"; 5%+ misses "underperform by 3-5%" - [verified-secondary] (OptionsPilot; no methodology disclosed - treat as weak).
- The "163% return" spread examples in OptionsPilot are ILLUSTRATIVE worked examples, not a track record - [verified-secondary] as illustrations only.
- Options-expression CAGR / win rate / PF / max DD: **UNKNOWN - never published anywhere I could find.**

Methodology caveats: academic numbers are abnormal (risk-adjusted) portfolio returns before realistic costs; Fink 2020 Observation 8 records the dispute - "there are studies that find (close to) zero abnormal profits after accounting for trading frictions (Chordia et al., 2009; Ng et al., 2008; Zhang et al., 2013)" vs. "other studies find significant profits (Battalio and Mendenhall, 2011; Ke and Ramalingegowda, 2005)."

## 7. KNOWN FAILURE MODES

- **Post-2000s attenuation.** Documented decline of PEAD magnitude (Chordia et al. 2014; Martineau 2019; Fink 2020). The anomaly we are shadowing may already be mostly arbitraged away in liquid names.
- **Large-cap weakness (structural, hits us directly).** "The strength of the PEAD is inversely related to firm size" (Fink 2020). Mega-caps with 40+ analysts are the least-drifting cohort ever documented; a null result on our universe would be consistent with the literature, not a bug.
- **Aggregation illusion (Katz et al. 2018).** Firm-level drifts are "highly heterogeneous and highly variable over time"; even in the Bad News decile 28.0% of quarters drifted POSITIVE. Single-name expectancy is far noisier than the portfolio numbers imply - expect a low hit rate rescued (if at all) by tail wins that our capped vertical partially forfeits.
- **Payoff truncation vs. drift tail.** The vertical's max profit caps exactly the right-tail continuation the anomaly's mean depends on; combined with theta, a slow grinding drift can arrive too late for a 30 DTE structure.
- **Gap reversal / false surprise.** Beat-then-fade (sell-the-news) days trigger entry then stop; the published 50%-gap-giveback stop exists precisely because this is common. Guidance-vs-EPS divergence (EPS beat + guide-down) is a known trap the academic SUE signal does not see; OptionsPilot: "Guidance raised. Forward-looking beats matter more than backward-looking ones" - we do NOT implement a guidance filter (no mechanizable rule published), so we absorb this failure mode.
- **Next-announcement reversal.** Bernard-Thomas earnings autocorrelation work shows drift concentrates and partially reverses around SUBSEQUENT announcements ("25-30% of the post-earnings announcement drift occurs during the three-day windows surrounding subsequent earnings announcements" - Wikipedia summary). Our ≤25-day hold naturally ends before the next quarterly report - do not extend holds into the next earnings window.
- **Macro event overwhelm.** FOMC/CPI landing mid-hold can dominate a single-name drift (e.g., a Mar-2020-style shock makes every drift long a market-beta trade). No published gate exists; flagged for the platform's event-awareness layer.
- **Early assignment through ex-div (structural, options-specific).** Bull call spreads on dividend payers (AAPL, MSFT, META now pay): if the SHORT call goes ITM and carry crosses an ex-div date, early assignment risk appears. Debit verticals keep the long leg as cover, so risk is operational (shadow must model assignment), not unlimited-loss. TSLA/NVDA/AMD ex-div exposure minimal-to-none at typical sizes.
- **IV-crush timing miss.** Entering day 2-3 assumes the crush is complete; a second vol event (e.g., product announcement, peer earnings) inside the hold re-marks the spread unpredictably - spreads mute but do not eliminate vega.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | direction_rule | beat → bull call vertical; miss → bear put vertical | SOURCE-VERBATIM (adapted structure) | "prescribes buying (selling) portfolios of firms that release extremely positive (negative) earnings news" (Katz et al. 2018 describing B&T); call/put spread examples per surprise sign (OptionsPilot) |
| 2 | published_signal_formation | SUE deciles; Good News > 90th pct, Bad News < 10th pct of PRIOR quarter's SUE distribution; seasonal-random-walk expected earnings | SOURCE-VERBATIM (provenance only, not implemented) | "decile cutoffs based on the distribution of SUE in the prior quarter... above the 90th percentile cutoff are part of the 'Good News' portfolio" (Katz et al. 2018 sec. 5 "Data"); "estimate expected earnings as a seasonal random walk" (ibid.) |
| 3 | surprise_metric | consensus-EPS % surprise = (actual − consensus)/|consensus| | ADAPTED | 6-name universe cannot form deciles; analyst-consensus expectation replaces B&T's seasonal random walk (precedent: "Doyle... and Livnat and Mendenhall (2006) use equity analysts estimates from IBES" - Katz et al. 2018) |
| 4 | surprise_threshold_pct | ±5% | SOURCE-VERBATIM | "Stocks that beat expectations by 5%+ outperform..."; "Stocks that miss by 5%+ underperform..." (OptionsPilot) |
| 5 | min_gap_size | UNKNOWN in sources; platform: |gap| ≥ 1% else skip | PLATFORM-POLICY | no source publishes a minimum gap; required so the gap-giveback stop (row 14) is well-defined |
| 6 | entry_day | T+2 (default) to T+3 after the announcement session | SOURCE-RANGE | "Entry: Day 2-3 after earnings. Skip day 1 - too volatile, wide spreads." (OptionsPilot); "the second day after the actual earnings announcement" (Quantpedia) |
| 7 | entry_time_of_day | UNKNOWN in sources; platform default 10:30 ET | PLATFORM-POLICY | no source states a clock time |
| 8 | bmo_amc_day_convention | BMO → report day = day 1; AMC → next session = day 1 | PLATFORM-POLICY | convention needed to implement row 6; no source states it |
| 9 | structure | 2-leg debit vertical (long nearer-ATM, short farther-OTM), same expiry | SOURCE-VERBATIM | "Buy $137/$147 call spread (30 DTE) for $3.80"; "Buy $9.50/$8.50 put spread (30 DTE) for $0.38" (OptionsPilot) |
| 10 | dte_band | target expiry nearest 30 DTE; accept 14-30 | ADAPTED | both source examples are exactly "(30 DTE)"; the 14-day floor is our platform chain band, no source |
| 11 | long_strike_selection | UNKNOWN in source; ADAPTED default: nearest-to-ATM strike in drift direction | ADAPTED | "No strike-selection rule stated" (verified against article text); default is ours |
| 12 | short_strike_width_rule | UNKNOWN in source; ADAPTED default: width such that debit = 30-45% of width | ADAPTED | reverse-engineered: both worked examples pay exactly 38% of width ($3.80/$10; $0.38/$1) - derived, not stated |
| 13 | profit_target_pct | 100-150% of debit; platform default 100% | SOURCE-RANGE | "your profit target (typically 100-150% return on the spread)" (OptionsPilot); no documented default, we take the conservative end |
| 14 | stop_gap_giveback_pct | 50% of the earnings gap (underlying-price stop) | SOURCE-VERBATIM | "Stop: Close the spread if the stock gives back 50% of the earnings gap. The drift thesis is dead at that point." (OptionsPilot) |
| 15 | time_exit_days | 15-25 days after entry; platform default 25 (upper bound) | SOURCE-RANGE | "Exit: 15-25 days after entry, or when the stock reaches resistance, or when you hit your profit target" (OptionsPilot); "resistance" leg dropped as non-mechanizable |
| 16 | expiry_guard_dte | close by 5 DTE if still open | PLATFORM-POLICY | no source; prevents expiry-week gamma/assignment ops in the shadow |
| 17 | published_holding_period | 60 trading days / 13 weeks (context only - NOT implementable within 30 DTE) | SOURCE-VERBATIM | "the typical holding period examined is usually over the next quarter... buy and hold return for each firm over the 13 weeks after the earnings announcement" (Katz et al. 2018); "60 working days" (Quantpedia) |
| 18 | iv_gate | UNKNOWN - none published; no numeric gate implemented | UNKNOWN | only rationale text exists: "IV has already crushed, making directional options cheap" (OptionsPilot) |
| 19 | liquidity_min_oi | 100 contracts per leg | PLATFORM-POLICY | ours; no source |
| 20 | liquidity_max_spread_pct | leg bid-ask ≤ 10% of mid | PLATFORM-POLICY | ours; no source |
| 21 | sizing_units | 1 debit vertical (1 lot), account-blind | PLATFORM-POLICY | source context: "Size: 2-3% of account per drift trade" (OptionsPilot); academic source sizes as a portfolio, not per-trade |

## 9. DATA REQUIREMENTS

- **Earnings calendar** - REQUIRED, the trigger: date, bmo/amc flag, consensus EPS, actual EPS (available same evening/morning of report). This is the pacing data for the whole lane.
- **Tradier chains** - REQUIRED at entry: 14-35 DTE band (target ~30 DTE plus slack for expiry spacing), calls and puts, both legs' quotes + OI for rows 19-20.
- **Daily history** - REQUIRED: prior close and earnings-day open (gap measurement for rows 5/14), plus running closes during the hold.
- **1-min bars (underlying)** - NEEDED for the stop: row 14 is an underlying-price stop ("gives back 50% of the earnings gap"); intraday checks (1-min or 15-min sampling is sufficient - drift is a multi-day phenomenon) beat close-only checks. The dormant intraday_cache infra fits.
- **FOMC/CPI dates** - advisory only (failure-mode awareness, section 7); no published gate, so no veto is implemented - log overlap for attribution.
- **VIX regime / IV rank** - NOT required: no published IV gate (row 18). If a gate is ever armed later, note our IV archive is cold → use the VIX-percentile fallback.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** universe = 6 single names (ETFs ineligible - no earnings) × 4 reports/yr = 24 events/yr. With the ±5% surprise filter and the ≥1% gap filter, roughly half qualify → **~1.0-1.5 trades/month AVERAGE, heavily clustered**: expect 3-6 entries inside each ~6-week earnings season and near-zero between. At ~12-15 trades/yr, reaching the platform's N≥25/lane verdict takes ~20-24 months - flag to the orchestrator: this lane will be slow to grade unless the eligible single-name tier is widened (each added liquid name = +4 events/yr).
- **Mark cadence:** EOD marks suffice for P&L; intraday underlying sampling (1-15 min) needed ONLY for the gap-giveback stop trigger; option re-quote on trigger.
- **Multi-leg shape:** 2-leg same-expiry vertical, net debit, one order unit. No stock legs, no hedging - the published equity form is fully replaced (section 2), nothing about the options form requires shares.
- **Capital-at-risk basis:** **debit paid** (max loss of a debit vertical = debit). Not width-credit, not Reg-T proxy.
- **1-lot account-blind distortions:** (a) the source's "2-3% of account" scaling is ignored - fine, shadow measures edge not sizing; (b) the published anomaly is a cross-sectional portfolio - our sequential 1-lot single names measure a DIFFERENT (noisier, per Katz et al.) object; grade against per-trade expectancy, never against the 18%-annualized portfolio number; (c) the $1-wide put-spread example in the source implies sub-$10 underlyings can qualify - on our mega-cap tier widths will be $5-$25; the debit-as-%-of-width rule (row 12), not absolute width, is the invariant we carry.
- **Grading caution:** the honest published benchmark for our cohort is weak-positive-to-null (large caps, post-attenuation era). A clean null here is informative, not a failed implementation.

## 11. VERIFICATION

**Verdict: CORRECTED** - adversarial verification pass, 2026-07-19, fresh-context verifier.

**What was checked.** All five secondary/practitioner sources were independently re-fetched: (1) OptionsPilot article (optionspilot.app, dated April 8, 2026) - fetched live; (2) Fink (2020) Graz working-paper PDF - downloaded and full text extracted locally (28 pp.); (3) Katz/McCubbins/McMullin working-paper PDF (jkatz.caltech.edu) - downloaded and full text extracted locally (45 pp.); (4) Quantpedia strategy page; (5) Wikipedia PEAD article; plus (6) the Gow & Ding replication chapter (iangow.github.io). Every SOURCE-VERBATIM and SOURCE-RANGE constant in sections 3, 4, and 8 was located in its cited source, and every [verified-secondary] performance number in section 6 was found in the stated source. Specifically confirmed verbatim: the ±5% surprise threshold, 2-4%/3-5% drift-size claims, "Entry: Day 2-3 after earnings", both worked spread examples ($137/$147 for $3.80; $9.50/$8.50 for $0.38, both 163%/38%-of-width), the 100-150% profit-target range, the 50%-gap-giveback stop, the 15-25-day time exit, "2-3% of account" sizing, the IV-crush rationale sentence, and the "Guidance raised." bullet (all OptionsPilot); the 18%-annualized and 2%-over-60-trading-days/4%-quarterly B&T magnitudes, Observation 4 (size), and Observation 8 (frictions dispute with all five citations) (Fink 2020); "prescribes buying (selling) portfolios...", the 10-25% annual-return range, prior-quarter 90th/10th-percentile decile cutoffs, seasonal-random-walk expectation model, "highly heterogeneous and highly variable over time", "practically all firm-specific drifts do not follow the portfolio drift path", the 28.0%-of-Bad-News-quarters-positive figure ("28.0% of drifts (or, 33 quarters) experience positive drift"), and the 13-week/next-quarter holding period (Katz et al.); the universe rule, second-day entry, 60-working-day hold, 15% annual return, -11.2% max DD, 1987-2004, equal weighting (Quantpedia); 41-of-48 quarters, attenuation figures, and the 25-30%-around-subsequent-announcements figure (Wikipedia); "Model 5 of Foster (1977)" (Gow & Ding). The OptionsPilot article was also probed for a strike-selection rule: none exists beyond the worked examples, confirming rows 11-12's UNKNOWN/ADAPTED status. Adapted rows (3, 10, 11, 12) all carry genuine rationales and none is presented as published; the 38%-of-width reverse-engineering was recomputed and is arithmetically correct.

**Corrections applied (all minor):** (a) Katz et al. locator for the decile-cutoff and expectation-model quotes was "sec. 3" - the quotes actually sit in sec. 5 "Data"; fixed in section 3 and table row 2. (b) Three quotes were near-verbatim paraphrases inside quote marks and were replaced with the true verbatim text: the Wikipedia 41-of-48-quarters sentence, the Wikipedia attenuation sentence, and the Quantpedia long-side sentence ("most of the returns come from the long side"). No constant's VALUE changed; every correction was wording/locator only.

**Residual doubts.** (1) B&T (1989) primary remains paywalled - its magnitudes rest on three independent secondaries (Fink full text, Katz full text, Gow & Ding), which agree; the brief's [verified-secondary]-never-[verified-primary] tagging honestly reflects this. (2) OptionsPilot is a low-authority practitioner blog with no disclosed methodology for its 2-4%/3-5% drift claims and no track record for the spread structure; the brief already flags this and treats it as a template - correct posture, but every option-layer constant ultimately hangs on one uncorroborated blog post. (3) The Katz "p.1" locator for the "prescribes buying (selling)" quote points at the abstract/intro region - the quote is verbatim in the extracted intro; page number not independently confirmed against print pagination. (4) The Quantpedia backtest metrics were confirmed against the page as fetched; Quantpedia periodically revises pages, so a re-check at implementation time is cheap insurance.

---
*Research provenance: primary B&T 1989 full text is paywalled (JSTOR); magnitudes verified through full-text reads of Fink (2020) and Katz et al. (2018) plus the Gow & Ding replication chapter. Options-expression constants all trace to the OptionsPilot 2026-04-08 article, quoted verbatim; where it is silent the row says UNKNOWN. No constant in this brief is from memory. Adversarially verified 2026-07-19 (section 11): verdict CORRECTED.*
