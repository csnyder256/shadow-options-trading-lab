# Strategy Brief: strangle_45d16d_managed

Researched 2026-07-19 for the ATLAS options shadow platform. All quotes were read
from the cited pages during this research session unless explicitly tagged
otherwise. Anything not readable in a source is marked UNKNOWN - no invented
constants.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `strangle_45d16d_managed`
- **Provenance class:** practitioner (tastytrade/tastylive published research and
  mechanics; corroborated by a Wiley-published book from the tastytrade research
  team)
- **PRIMARY citations (tastylive, read directly this session):**
  1. "Strangle Options Strategy: How Long and Short Strangles Work" - 
     https://www.tastylive.com/concepts-strategies/strangle (no visible date) - 
     canonical mechanics page: 45 DTE target, 50%-of-credit profit target,
     untested-side rolling doctrine.
  2. Josh Fabian, "How to Manage Short Strangles" (2016-09-23) - 
     https://www.tastylive.com/news-insights/why-manage-at-50-not-25-for-short-strangles
 - the managing-winners study (SPY one-standard-deviation strangles, 45 DTE,
     data back to 2005).
  3. Kai Zeng, "Cut Your Trading Losses in Half!" (2024-06-24) - 
     https://www.tastylive.com/news-insights/Options-Trading-How-to-Cut-Your-Losses-in-Half
 - the 21 DTE loss-management study on SPY strangles.
  4. Josh Fabian, "Alternative to Managing Losers" (2016-10-20) - 
     https://www.tastylive.com/news-insights/alternative-to-managing-losers - 
     tastylive's own study of 1x–5x credit loss stops (important: it argues
     AGAINST pure P/L stops; see §4).
  5. "Standard Deviation Definition" - 
     https://www.tastylive.com/definitions/standard-deviation - the 16-delta ≈
     one-standard-deviation equivalence.
  6. "Implied Volatility (IV) Rank & Percentile Explained" - 
     https://www.tastylive.com/concepts-strategies/implied-volatility-rank-percentile
 - the IVR > 50 premium-selling gate.
  7. "Managing Winning Options Positions" - 
     https://www.tastylive.com/concepts-strategies/managing-winners - the
     close-winners-at-50% doctrine.
- **INDEPENDENT secondary source (read directly):** SJ Options, "Does Tastytrade
  Work" - https://www.sjoptions.com/does-tastytrade-work/ (article dated Feb 5,
  year unstated; backtest runs 2005 → early 2016). A *critical* third party that
  states the full canonical formula in one sentence and independently backtests
  it on SPX. Quote: "Sell the 16 delta of the call and put 45 days to expiration
  (DTE) when IV Rank is from 50% to 100%" with management "closing out winners
  when they reach 50% of the credit or stopping losses if the original credit
  doubles."
- **Additional published reference:** Julia Spina (tastytrade research team),
  *The Unlucky Investor's Guide to Options Trading*, Wiley, 2022 (ISBN
  9781119882657). Verified via a secondary review
  (https://kriminiltrading.com/blogs/must-read-economic-market-books/the-unlucky-investor-s-guide-to-options-trading-by-julia-spina-my-book-summary-review)
  quoting the book's ideal trade: "Selling a 45 Days To Expiration (DTE)
  Strangle, at 16 Delta, on a highly liquid index while the Implied Volatility
  is elevated" and "Then manage the trade at 21 DTE." Book itself NOT read
  page-by-page this session - treat book-attributed wording as
  [verified-secondary]; chapter locator UNKNOWN.
- **Publication dates:** mechanics pages undated (living pages, fetched
  2026-07-19); studies 2016-09-23, 2016-10-20, 2024-06-24; book 2022; SJ Options
  backtest through early 2016.

---

## 2. PUBLISHED UNIVERSE & OUR MAPPING

- **What the sources trade:** tastylive's management studies are on **SPY**
  (Fabian 2016: "selling one standard deviation strangles" on SPY at "45 days
  until expiration (DTE)" with data "going back to 2005"; Zeng 2024: "SPY
  options positions"). The Spina book says "a highly liquid index". SJ Options'
  independent backtest used **SPX**. tastylive also trades single-name strangles
  on air, but the published statistics above are index-ETF statistics.
- **Our mapping:** SPY / QQQ / IWM (faithful to the published evidence) plus the
  liquid mega-cap tier AAPL / NVDA / MSFT / TSLA / AMD / META (**extension
  beyond the evidence**).
- **Why the mapping preserves the edge claim:** the claimed edge is the
  volatility risk premium - options systematically price larger moves than
  realize - harvested delta-neutrally with defined management points. SPY is the
  literal study underlying; QQQ/IWM are the same instrument class (deep,
  penny-quoted index ETF chains) so the VRP mechanism and the liquidity
  assumptions carry over. **LOUD ADAPTATION FLAG:** the mega-cap tier is NOT
  what the studies measured. Single names carry idiosyncratic gap risk
  (earnings, product/news shocks) that SPY studies structurally cannot exhibit,
  and single-name IV carries a larger event component, so the same 16-delta
  strikes sit closer in gap terms. All single-name results must be graded as a
  separate lane and not pooled with the ETF lane when judging fidelity to the
  published claim. No stock legs and no delta-hedging are needed anywhere - the
  published form is options-only, so no structural adaptation is required on
  that axis (rolling is simplified, see §4/§8).

---

## 3. EXACT ENTRY RULES

- **Trigger / regime gate (IV Rank ≥ 50):**
  - Primary: "an implied volatility rank above 50% can be indicative of an
    attractive opportunity to sell options/volatility" and "short
    options/volatility trades become relatively more attractive when IV rank is
    above 50%" (tastylive IVR page). Same page: "Extreme levels in IV rank
    would be 80 and above."
  - Secondary (formula form): "Sell the 16 delta of the call and put 45 days to
    expiration (DTE) when IV Rank is from 50% to 100%" (SJ Options, describing
    tastytrade's formula).
  - IVR definition basis: IV rank "reports how the current level of implied
    volatility in a given underlying compares to the last 52 weeks of
    historical data" (tastylive IVR page, verified verbatim 2026-07-19).
    I.e. rank of current IV within its trailing 52-week high–low range.
    A similar wording previously attributed here to Sage Anderson, "IV Rank
    vs. IV Percentile" (tastylive, 2016-01-20) could NOT be located in
    verification (article unfindable; slug guesses 404) - treat that specific
    attribution as [unverified locator]; the definition itself is
    primary-verified via the IVR page above.
- **Strike selection (16-delta each side):**
  - Secondary verbatim: "Sell the 16 delta of the call and put" (SJ Options);
    book: "at 16 Delta" (Spina via review, [verified-secondary]).
  - Primary chain: the tastylive study sells "one standard deviation strangles"
    (Fabian 2016) and tastylive defines "Strikes with a probability of 16% ITM /
    84% OTM capture a one standard deviation range for an OTM option" (Standard
    Deviation definition page). 16Δ ≈ 16% ITM ≈ 1 SD - the two formulations are
    the same rule.
  - No published tolerance for "nearest strike to 16Δ" - UNKNOWN; platform picks
    nearest (see §8).
- **DTE selection:** "Our target timeframe for selling strangles is around 45
  days to expiration." (tastylive strangle page). "45 days until expiration
  (DTE)" (Fabian 2016 study). "45 Days To Expiration (DTE)" (Spina via review).
  Source says "around" - treated as target 45 with a platform band.
- **Entry timing (time of day / event T-n):** UNKNOWN - no published time-of-day
  or pre-event timing rule found in any cited source. Studies appear to use
  daily data; methodology sentence not published. Platform must pick a
  consistent entry window and record it as its own policy.
- **Event gates (earnings/FOMC):** none published for this strategy in the cited
  sources. The published SPY form has no earnings exposure at all; our
  single-name extension does (see §2, §7).

---

## 4. EXACT EXIT RULES (override platform exit doctrine for this strategy)

- **Profit target - 50% of credit received:**
  - "The first profit target is generally 50% of the maximum profit. This is
    done by buying the strangle back for 50% of the credit received at order
    entry." (tastylive strangle page)
  - "We tend to close our winners when we reach 50% profit…" (tastylive
    Managing Winning Options Positions)
  - Study support: "Trades managed at 50% were successful 90% of the time"
    vs "closing out trades at 25% max profit yielded a 95% success rate" and
    "trades held until expiration were successful 82% of the time"; "managing at
    50%, our daily P/L is around 77% greater than if we manage at 25%" (Fabian
    2016).
- **Time exit - 21 DTE:**
  - "By exiting SPY options positions at 21 DTE instead of holding them until
    expiration, the largest losses can be cut nearly in half." (Zeng 2024)
  - "Then manage the trade at 21 DTE." (Spina via review, [verified-secondary])
  - Rationale from tastylive's loss study: the most significant losses occurred
    "within about 21 DTE" as gamma risk accelerates near expiration (Fabian,
    Alternative to Managing Losers, 2016-10-20).
- **Loss management - 2x credit received:**
  - Secondary verbatim: "…or stopping losses if the original credit doubles"
    (SJ Options stating the tastytrade formula).
  - Convention (what "2x credit loss" means at tastytrade): a strangle sold for
    $1.00 trading at $2.00 is a 1x-credit loss; exiting at a 2x-credit loss
    means exiting when it trades for $3.00 - i.e. **net loss = 2× credit,
    buy-back price = 3× credit**. [unverified - this definition and the
    supporting study stats reached me only via search excerpts of
    https://20percentfreedom.home.blog/2019/07/27/managing-losers-at-2x-credit-received/
    (an image-based blog post summarizing tastytrade Market Measures "Exiting
    Losing Trades", aired 2014-12-16); the episode page itself is JS-rendered
    and unreadable by fetch.]
  - **AMBIGUITY FLAG (do not silently resolve):** the SJ Options sentence read
    literally ("the original credit doubles") means buy-back at **2× credit**
    (net loss = 1× credit); the tastytrade house convention above means buy-back
    at **3× credit** (net loss = 2× credit). We implement the house convention
    (net loss ≥ 2× credit ⇒ buy-back ≥ 3× credit) and record the alternative
    reading in §8. Grading must note which definition fired.
  - **PRIMARY-SOURCE TENSION (loud):** tastylive's own published study found
    that "managing strangles based on a negative P/L of anywhere between 1 - 5
    times total credit received was not a good strategy" and that "managing a
    strangle based on the size of its loss is an ineffective strategy" (Fabian,
    Alternative to Managing Losers, 2016-10-20) - favoring the 21 DTE time exit
    instead. Zeng 2024 adds: with the 21 DTE exit, "For 90% of occurrences, the
    loss-to-credit ratio remains below 2." The 2x stop is in this strategy's id
    and in the canonical formula as stated by secondary sources, so we implement
    it, but the shadow should track how often the 2x stop fires before 21 DTE
    would have - that differential is exactly the published dispute.
- **Exit precedence:** first-touched wins among {50% profit target, 21 DTE,
  2x-credit loss}. The "whichever comes first" framing appears in secondary
  summaries ("manage short premium trades at 21 days to expiration (DTE) or when
  you've captured 50% of the maximum profit" - Medium/summary sources,
  [unverified] as exact tastylive wording); formalized here as ADAPTED.
- **Rolling doctrine (published but NOT implemented in shadow v1):** "Rolling
  the untested side (non-losing side) closer to the stock price when our tested
  side (losing side) is breached is optimal." (tastylive strangle page). No
  numeric trigger ("breached" by what amount, roll to what delta) is published
  on that page - trigger constants UNKNOWN. Shadow v1 therefore runs
  close-only exits (ADAPTED, flagged in §8); a roll lane may be added only if a
  published numeric trigger is found.
- **Hold-to-expiry:** explicitly rejected by the sources (82% win rate but worst
  tails; see quotes above). Never hold past 21 DTE.

---

## 5. SIZING CONVENTION IN SOURCE

- The strategy is an undefined-risk naked short strangle: "Undefined risk
  refers to the risk that is accompanied with naked short options and when your
  possible max loss is unknown on order entry." (tastylive strangle page)
- Margin basis (broker convention): the margin requirement for a short
  straddle/strangle is the greater of the two sides' short uncovered margin
  requirement plus the premium of the other leg [unverified - search excerpt of
  the tastytrade support article
  https://support.tastytrade.com/support/s/solutions/articles/43000435282; page
  itself would not render].
- SJ Options' independent backtest sized at "15% of portfolio margin used on
  average" [verified-secondary; exact wording corrected in verification - 
  earlier draft paraphrased this as "15% portfolio margin utilization"].
- tastylive's per-trade buying-power allocation guidance for strangles: UNKNOWN
 - no primary quote captured this session; do not attribute a % figure.
- **Our shadow always runs 1 published unit** (one 1-lot strangle), account-blind.

---

## 6. DOCUMENTED PERFORMANCE

All from SPY/SPX index studies; none cover our single-name tier.

- Win rate, SPY 1-SD (≈16Δ) 45 DTE strangles, data back to 2005 (Fabian 2016):
  - Managed at 50% of max profit: **90%** win rate [verified-primary]
  - Managed at 25% of max profit: **95%** win rate [verified-primary]
  - Held to expiration: **82%** win rate [verified-primary]
  - Daily P/L managing at 50% "around 77% greater" than managing at 25%
    [verified-primary]
  - Average days in trade: **23.5** (50% mgmt) vs **13.5** (25% mgmt)
    [verified-primary]
- 21 DTE loss study, SPY strangles (Zeng 2024): largest losses "cut nearly in
  half" vs holding to expiration [verified-primary]; average long-term losses
  drop ~60% [verified-primary]; largest risks in stress years (2008, 2018,
  2020, 2022) reduced up to ~75% [verified-primary]; "For 90% of occurrences,
  the loss-to-credit ratio remains below 2" [verified-primary].
- Independent critical backtest, SPX, 2005 → early 2016, exact formula (16Δ, 45
  DTE, IVR 50–100, 50% winners, stop when credit doubles), 15% portfolio-margin
  utilization (SJ Options): "11-Year Portfolio growth, 2%" per their table, and
  "the system only produced 3% a year" per their text [verified-secondary].
  Methodology caveats: portfolio-margin sizing, includes the low-IVR drought
  (gate idle), pre-2018/2020 tail events, and SJ Options sells a competing
  course (adversarial incentive - but that cuts toward believing their negative
  result is a floor, not cherry-picked upside).
- 2x-loss study stats (Market Measures "Exiting Losing Trades", 2014-12-16, as
  relayed by the 20percentfreedom blog): ~17% of strangle trades reach a
  1x-credit loss, ~8% reach 2x, ~5% reach 3x, ~3% reach 4x, ~2% reach 5x;
  exiting at the 2x-credit loss was the best P/L-stop variant in that test
  (ending profit $99,275, 81% win rate) [unverified - search-snippet chain only;
  do NOT treat as verified].
- "A losing 16Δ SPY strangle at 21 DTE had an 80% chance of a P/L flip by
  expiration" (tastylive Market Measures episode "P/L Flips After 21 DTE",
  2021-05-18) [unverified - search-snippet of an unreadable episode page].
- CAGR / profit factor / max drawdown for the exact managed combo: UNKNOWN in
  primary sources (tastylive publishes episode graphics, not a consolidated
  tearsheet). The only end-to-end equity curve found is the critical secondary
  one above.

---

## 7. KNOWN FAILURE MODES

- **Feb-2018 "Volmageddon":** VIX more than doubled in a day; short strangles
  gapped through both management levels - 2x stops execute far beyond 2x.
  tastylive's own 21 DTE study names 2018 among the stress years where early
  exit cut largest risks (Zeng 2024).
- **Mar-2020 COVID crash and 2022 bear:** same mechanism; Zeng 2024 lists 2008,
  2018, 2020, 2022 as the largest-risk periods [verified-primary].
- **Aug-5-2024 vol spike:** VIX intraday spike ≈ 65; overnight gap meant
  puts opened deep ITM - loss stops are gap-through, not touch-executed.
- **Margin/BPR expansion spiral:** "when the market moves, the trader's account
  value drops quickly and margins increase simultaneously, sometimes by 200% or
  more" (SJ Options) - real accounts get force-liquidated at the lows; our
  account-blind shadow will NOT reproduce this failure mode (flagged in §10).
- **Single-name gap-through-strikes (our extension only):** earnings or news
  gaps (TSLA/NVDA/AMD routinely move >8% on earnings) blow through 16Δ strikes
  in one print; the SPY studies contain zero such events.
- **Early assignment through ex-div:** a tested short ITM call held near an
  ex-dividend date (SPY/QQQ/IWM quarterly ex-divs; AAPL/MSFT/META/NVDA pay
  dividends) can be assigned early when extrinsic < dividend. Managing at 21
  DTE reduces but does not eliminate ITM dwell time. Shadow has no assignment
  path - mark trades where extrinsic-vs-dividend crossed as
  assignment-suspect.
- **IVR-gate starvation:** IVR ≥ 50 is rare in calm regimes - long entry
  droughts (the SJ Options backtest's low return partly reflects idle periods),
  slow N accumulation for grading, and entries cluster exactly at vol spikes - 
  the strategy self-selects into the scariest tapes.
- **Correlated blowup across the universe:** all 9 names are equity-beta; a
  single vol event fires every open strangle's loss stop simultaneously. 1-lot
  shadow still records 9 correlated losses - grade lanes, not just pooled.

---

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | underlying_universe | SPY, QQQ, IWM + AAPL, NVDA, MSFT, TSLA, AMD, META | ADAPTED | Studies are SPY ("selling one standard deviation strangles" on SPY - Fabian 2016); SPX in SJ backtest; "a highly liquid index" (Spina). ETFs faithful; mega-cap tier is our extension - separate grading lane. |
| 2 | dte_target | 45 | SOURCE-RANGE (source: "around 45"; default 45) | "Our target timeframe for selling strangles is around 45 days to expiration." - tastylive strangle page |
| 3 | dte_entry_band | pick expiration nearest 45 DTE within [35, 55] | PLATFORM-POLICY | Source says only "around 45"; band is ours. |
| 4 | short_call_delta | 0.16 | SOURCE-VERBATIM | "Sell the 16 delta of the call and put" - SJ Options (formula); 1-SD chain: "Strikes with a probability of 16% ITM / 84% OTM capture a one standard deviation range" - tastylive Standard Deviation page |
| 5 | short_put_delta | 0.16 | SOURCE-VERBATIM | same as row 4 |
| 6 | strike_selection_rule | nearest listed strike to 0.16 chain delta, per side, same expiration | PLATFORM-POLICY | No published tolerance/tie-break - UNKNOWN in source. |
| 7 | ivr_entry_min | 50 | SOURCE-VERBATIM | "short options/volatility trades become relatively more attractive when IV rank is above 50%" - tastylive IVR page; "when IV Rank is from 50% to 100%" - SJ Options |
| 8 | ivr_definition | rank of current IV in trailing 52-week IV high–low range | SOURCE-VERBATIM | "reports how the current level of implied volatility in a given underlying compares to the last 52 weeks of historical data" - tastylive IVR page (Anderson 2016 attribution unlocatable; see §3) |
| 9 | ivr_fallback_metric | VIX 1-year daily-close percentile ≥ 50 (per-underlying IVR preferred once archive warms) | ADAPTED | Our IV archive is cold; VIX percentile is a stand-in for index ETFs and is WRONG-ISH for single names (understates name-specific vol states) - flagged. |
| 10 | profit_target | buy back strangle at 50% of credit received | SOURCE-VERBATIM | "The first profit target is generally 50% of the maximum profit. This is done by buying the strangle back for 50% of the credit received at order entry." - tastylive strangle page |
| 11 | time_exit_dte | close position at 21 DTE | SOURCE-VERBATIM | "By exiting SPY options positions at 21 DTE instead of holding them until expiration, the largest losses can be cut nearly in half." - Zeng 2024; "Then manage the trade at 21 DTE." - Spina (via review) |
| 12 | loss_exit_trigger | net loss ≥ 2× credit received (buy-back price ≥ 3× credit) | SOURCE-RANGE (ambiguous; alt reading: buy-back ≥ 2× credit) | "stopping losses if the original credit doubles" - SJ Options; house convention "sold for $1.00 … exiting at 2x credit loss means exiting when it trades for $3.00" [unverified snippet, 20percentfreedom blog]. Primary tension: P/L stops called "ineffective" - Fabian 2016-10-20. Log which definition fired. |
| 13 | exit_precedence | first touched of {profit_target, time_exit_dte, loss_exit_trigger} | ADAPTED | "or" framing in secondary summaries; formalized by us. |
| 14 | rolling_untested_side | NOT implemented in shadow v1 (close-only) | ADAPTED | Published doctrine is qualitative: "Rolling the untested side … when our tested side … is breached is optimal" - tastylive strangle page; numeric trigger UNKNOWN, so omitted rather than invented. |
| 15 | entry_time_of_day | UNKNOWN in source; platform: single consistent scan window during RTH (set by platform scheduler) | PLATFORM-POLICY | No published time-of-day rule found. |
| 16 | expiration_cycle_preference | UNKNOWN in source; platform: nearest listed expiration to 45 DTE, prefer monthly when tied (liquidity) | PLATFORM-POLICY | Studies do not state weekly-vs-monthly cycle. |
| 17 | earnings_gate | none (faithful to published form); single-name trades spanning earnings are TAGGED for lane-level attribution, not blocked | PLATFORM-POLICY | No earnings gate in any cited source; SPY studies have no earnings concept. |
| 18 | position_size | 1 strangle (1 lot per leg), account-blind | PLATFORM-POLICY | Shadow convention; source sizing is margin-based (§5). |
| 19 | liquidity_gate | both legs: bid > 0, quoted spread ≤ 15% of mid (or ≤ $0.05), OI ≥ 100 | PLATFORM-POLICY | Ours; source implies liquid index chains ("highly liquid index" - Spina). |
| 20 | capital_at_risk_basis | Reg-T naked-strangle proxy: max over sides of [20% notional rule per side] + other leg premium (see §10) | PLATFORM-POLICY | Broker-convention basis; strangle formula sentence [unverified snippet of tastytrade support article]. |

Constants recorded as UNKNOWN in-source: strike tolerance (row 6), entry time of
day (row 15), expiration cycle (row 16), numeric roll trigger (row 14),
per-trade buying-power % (§5), and the exact 2x-loss definition is ambiguous
(row 12).

---

## 9. DATA REQUIREMENTS

- **Tradier chains:** DTE band ~30–60 at entry scan (to find the nearest-45
  expiration with strikes bracketing 16Δ both sides); then continuous quotes on
  the two held legs from 45 → 21 DTE. Greeks (delta) per strike required at
  entry; if Tradier greeks are stale, compute delta from mid-IV.
- **Per-underlying IV history:** needed for true IVR (52-week IV range). Archive
  is cold → **VIX-percentile fallback** (row 9) until ≥ 52 weeks of
  per-underlying IV accumulates; log both values on every entry so trades can be
  re-gated retroactively.
- **VIX daily history:** required now (fallback gate) - 1+ year of daily closes.
- **Earnings calendar (date + bmo/amc):** required for the 6 single names - 
  tagging/attribution (row 17), and assignment-suspect marking near events.
- **FOMC/CPI dates:** context annotation only; no published gate. Useful for
  failure-mode attribution (§7).
- **Daily history (underlying):** for realized-vol context and grading
  annotations; already standard on platform.
- **1-min bars:** NOT required. Intraday option quotes at a modest cadence
  (15-min polling of held legs) suffice to detect 50% and 2x touches; the
  published studies are daily-resolution anyway (their exact mark cadence is
  UNKNOWN/unstated). EOD mark remains authoritative for the ledger.

---

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** universe of 9 names, one open strangle per name per
  cycle max. Unthrottled (no IVR gate) that is ~9 entries/month. The IVR ≥ 50
  gate historically passes only a minority of days (calm regimes: near zero;
  vol regimes: all 9 names at once), so long-run average is roughly **2–5
  entries/month, call it ~3** - and heavily clustered. Grading to N≥25 per lane
  will plausibly take 6–12 months for the ETF lane; plan for droughts and do
  not loosen the gate to feed the grader (that would unpublish the strategy).
- **Mark cadence:** 15-min polls on held legs for trigger detection (50%
  profit, 2x loss), EOD authoritative marks for the three-fill ledgers; 21 DTE
  exit executes as a scheduled close on the first scan of the 21-DTE session.
  Gap-throughs: record trigger price AND actual first-available fill mark - 
  the difference is the tail-risk telemetry this strategy exists to measure.
- **Multi-leg shape:** 2 legs, same expiration: short 1x 16Δ OTM call + short
  1x 16Δ OTM put, net credit. No long wings, no stock leg, no hedging.
- **Capital-at-risk basis:** undefined-risk position - use a **Reg-T CaR
  proxy** per strangle: max(per-side naked requirement ≈ 20% of underlying
  notional − OTM amount + leg premium, floor 10% rules) + premium of the other
  leg. This is a denominator convention for grading returns, not a margin
  simulation; label it as proxy in every report.
- **Account-blind 1-lot distortions (be loud in grading):**
  1. Real accounts die of margin expansion at the lows (§7); the shadow cannot
 - shadow results are *survivor-biased vs. a real margined account*.
  2. The published form's sizing (portfolio-margin utilization) compounds; our
     1-lot flat sizing understates both compounding and blowup risk.
  3. 2x loss stops assume execution near the trigger; in the gap events that
     dominate this strategy's left tail, fills are far worse. WORST-grade
     convention should use the post-gap mark, never the trigger level.
  4. The single-name lane is our extension (§2) - never present its results as
     evidence for or against the published tastylive claim; grade lanes
     separately (ETF lane = fidelity lane, mega-cap lane = extension lane).
- **The interesting scientific question this shadow can answer:** does the 2x
  stop help or hurt versus pure {50% + 21 DTE} management? tastylive's own
  primary research says P/L stops are ineffective (Fabian 2016-10-20), while
  the canonical formula includes the 2x stop. Log, for every losing trade,
  whether 2x fired before 21 DTE and the counterfactual 21-DTE exit P&L - this
  resolves the published dispute with our own data.

---

## 11. VERIFICATION

**Verdict: CORRECTED** (adversarial fresh-context verification pass,
2026-07-19).

**What was checked.** Every cited source was re-fetched live this session and
every §3 / §4 / §8 constant tagged SOURCE-VERBATIM or SOURCE-RANGE, plus every
§6 number tagged [verified-*], was located (or not) in its stated source:

- tastylive strangle page: "around 45 days to expiration", the full 50%-of-
  credit profit-target sentence, the rolling-untested-side sentence, and the
  undefined-risk definition - ALL found verbatim.
- Fabian 2016-09-23 (manage at 50 vs 25): SPY / 1-SD / 45 DTE / back-to-2005
  setup sentence, 95% / 90% / 82% win rates, "77% greater" daily P/L, and
  23.5 vs 13.5 days - ALL found verbatim.
- Zeng 2024-06-24 (21 DTE): "cut nearly in half", "drop by an impressive 60%",
  2008/2018/2020/2022 with "up to 75%", "For 90% of occurrences, the
  loss-to-credit ratio remains below 2" - ALL found verbatim.
- Fabian 2016-10-20 (Alternative to Managing Losers): "1 - 5 times total
  credit received was not a good strategy", "ineffective strategy", "biggest
  losing trades took place within about 21 DTE" + gamma rationale - ALL found
  verbatim.
- tastylive Standard Deviation page: 16% ITM / 84% OTM = 1 SD sentence - 
  found verbatim.
- tastylive IVR page: both "above 50%" sell-side sentences, "Extreme levels in
  IV rank would be 80 and above", and the 52-week definition - ALL found
  verbatim.
- tastylive Managing Winning Options Positions: "We tend to close our winners
  when we reach 50% profit" - found verbatim.
- SJ Options: formula sentence (16Δ / 45 DTE / IVR 50–100), "closing out
  winners… / stopping losses if the original credit doubles", backtest window
  "from 2005 to the beginning of 2016, 11 years and 1 month", "11-Year
  Portfolio growth, 2%", "the system only produced 3% a year", and the full
  margin-spiral sentence ("…when the market moves, the trader's account value
  drops quickly and margins increase simultaneously, sometimes by 200% or
  more") - ALL found verbatim.
- Kriminil Trading review of Spina 2022: both quoted book sentences ("Selling
  a 45 Days To Expiration (DTE) Strangle, at 16 Delta, on a highly liquid
  index…" and "Then manage the trade at 21 DTE.") - found verbatim,
  [verified-secondary] tag appropriate.
- 20percentfreedom blog (2x-loss convention + Market Measures 2014 stats):
  confirmed the post is images-only with no transcribed data - the brief's
  [unverified] tag is accurate and must stay; could neither confirm nor refute
  the ~17/8/5/3/2% ladder, the $99,275 / 81% figures, or the 3x-buy-back
  house convention.

**Corrections applied (all minor):**
1. §5: SJ Options sizing quote corrected to the page's actual words ("15% of
   portfolio margin used on average"); the earlier draft put a paraphrase in
   quotation marks.
2. §3 + §8 row 8: the IVR-definition quote attributed to Sage Anderson, "IV
   Rank vs. IV Percentile" (2016-01-20) could not be located anywhere this
   session (slug guesses 404; search engines unusable from this environment;
   archive.org unreachable) - attribution downgraded to [unverified locator]
   and the row re-anchored to the 52-week definition sentence verified
   verbatim on the tastylive IVR page. The constant itself is unchanged and
   primary-verified.
3. §6: trivial casing fix on the SJ Options "the system only produced 3% a
   year" quote.

**No invented constants found.** Every load-bearing number (45 DTE, 16Δ, IVR
50, 50% profit target, 21 DTE, 2x credit stop, all §6 [verified-*] stats) was
located verbatim in its cited source. The brief's honesty machinery
([unverified] tags, the 2x-definition ambiguity flag, the primary-source
tension over P/L stops, UNKNOWN markers) accurately reflects the sources.

**Residual doubts:** (a) the exact meaning of the 2x stop (buy-back at 2× vs
3× credit) remains genuinely ambiguous in the readable sources - the brief's
choice of the house convention rests on an unverifiable image-blog chain;
(b) the Market Measures episode stats (§6 last two bullets) remain
snippet-only and must not be promoted without reading the episodes;
(c) the Spina book was verified only through one third-party review, not
page-by-page; (d) the Anderson 2016 article may exist behind a changed slug - 
its unlocatability is an environment limitation, not evidence of fabrication.
None of these carries a load-bearing constant that isn't independently
verified elsewhere.

---

### Independent re-verification (second fresh-context pass, 2026-07-19)

**Verdict: CONFIRMED.** A second adversarial verifier with fresh context - who
treated the §11 text above as untrusted data, since it was already present in
the file it was asked to verify - independently re-fetched every cited source
and re-checked every §3/§4/§8 SOURCE-VERBATIM and SOURCE-RANGE constant and
every §6 [verified-*] number against the live pages. Results:

- tastylive strangle page: "around 45 days to expiration", the full 50%-of-
  credit profit-target wording, the rolling-untested-side sentence, and the
  undefined-risk definition - all located verbatim.
- Fabian 2016-09-23 (author/date confirmed on page): SPY 1-SD 45-DTE
  back-to-2005 setup, 95% / 90% / 82% win rates, "around 77% greater" daily
  P/L, 23.5 vs 13.5 days - all located verbatim.
- Zeng 2024-06-24 (author/date confirmed): "cut nearly in half", "drop by an
  impressive 60%", 2008/2018/2020/2022 with "up to 75%", "For 90% of
  occurrences, the loss-to-credit ratio remains below 2" - all located
  verbatim.
- Fabian 2016-10-20: "1 - 5 times total credit received was not a good
  strategy", "ineffective strategy", biggest losses "within about 21 DTE" +
  gamma rationale - all located verbatim.
- Standard Deviation page: 16% ITM / 84% OTM = 1-SD sentence - verbatim.
- IVR page: both above-50% sell-side sentences, "Extreme levels in IV rank
  would be 80 and above", 52-week definition - all verbatim.
- Managing Winners page: "We tend to close our winners when we reach 50%
  profit, or lower for certain strategies…" - verbatim (brief's ellipsized
  quote is a fair truncation).
- SJ Options: formula sentence, "…stopping losses if the original credit
  doubles", backtest window "from 2005 to the beginning of 2016, 11 years and
  1 month", "11-Year Portfolio growth, 2%", "only produced 3% a year", "15% of
  portfolio margin used on average", and the margin-spiral sentence - all
  verbatim.
- Kriminil review of Spina 2022: both book-attributed sentences - verbatim;
  [verified-secondary] tag appropriate.
- 20percentfreedom blog: independently confirmed to be images-only with no
  transcribed statistics - the brief's [unverified] tag on the 2x-loss house
  convention and the Market Measures 2014 stats is accurate and must stay.
- Anderson "IV Rank vs. IV Percentile" (2016): still unlocatable via search
  this pass - the [unverified locator] downgrade stands; the IVR definition
  itself is primary-verified on the live IVR page.

No invented constants found; no corrections needed in this pass (the three
minor corrections listed above were already in place and re-verify against
the live sources). All ADAPTED tags carry real rationale and nothing adapted
is presented as published. Residual doubts (a)–(d) above stand unchanged.
