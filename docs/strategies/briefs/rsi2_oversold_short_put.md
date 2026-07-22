# Strategy Brief: rsi2_oversold_short_put

Researched 2026-07-19. Primary source READ (full-text copy of the 2008 book), not recalled from memory.
Copyright note: the book is under copyright, so this brief records constants as short rule fragments +
precise locators rather than long verbatim passages. Every constant below carries a locator into the
cited source or an explicit ADAPTED/PLATFORM-POLICY/UNKNOWN tag.

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `rsi2_oversold_short_put`
- **Provenance class:** textbook (practitioner textbook, backtest-documented)
- **PRIMARY citation:** Larry Connors & Cesar Alvarez, *Short Term Trading Strategies That Work*,
  TradingMarkets Publishing Group, 2008 (ISBN 978-0981923901).
  - Entry chapter: **Chapter 9, "The 2-period RSI - The Trader's Holy Grail of Indicators?"** (pp. 65–67
    in the online full-text copy read).
  - Exit chapter: **Chapter 13, "Exit Strategies"** (incl. the section "What about Using Trailing Stops?").
  - Full text read at: https://epdf.pub/short-term-trading-strategies-that-work.html
  - Book identity/edition: https://www.amazon.com/Short-Term-Trading-Strategies-That/dp/0981923909
- **INDEPENDENT secondary sources:**
  1. StockCharts ChartSchool, "RSI(2)" - 
     https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2
     (independent restatement of the rules: 200-day SMA filter, RSI(2)<5 preferred / <10 acceptable,
     exit on close above the 5-day SMA, no stops).
  2. QuantifiedStrategies (Substack), "RSI 2 Strategy Explained: Larry Connors' 2-Period RSI Trading Rules" - 
     https://quantifiedstrategies.substack.com/p/rsi-2-strategy-explained-larry-connors
     (independent SPY backtest 1993–present; performance numbers in §6. Exact rules paywalled;
     the www.quantifiedstrategies.com mirror sat behind bot verification on fetch.)
- **Publication dates:** book 2008; ChartSchool article undated/maintained; Substack article recent (2024–2025 era).

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**Source trades:** the S&P index (SPX points example in Ch. 9), SPY (Cumulative-RSI test, Jan-1993 to
Dec-2007), and per Ch. 9's strategy list "the market and stocks"; the book also reports that most of the
indices and ETFs it examined beat 75% correct under the cumulative-RSI variant. All tests are LONG THE
UNDERLYING (buy stock/ETF on the close). No options anywhere in the published form.

**Our mapping:** SPY / QQQ / IWM plus the liquid mega-cap tier AAPL / NVDA / MSFT / TSLA / AMD / META.

**LOUD ADAPTATION NOTICE:** the published strategy buys the underlying. This platform is options-only
(no stock legs, no delta-hedging), so we express the same long-delta mean-reversion thesis as a
**single-leg short put** opened at the entry signal and bought back at the exit signal. Everything about
the option leg (structure, delta, DTE, expiry failsafe) is OURS, tagged ADAPTED in §8 - Connors/Alvarez
published none of it. What is preserved: the entry condition, the exit condition, the no-stop doctrine,
and the holding rhythm (avg ~3.5–3.7 trading-day holds in the primary tests). What is distorted: payoff
shape (upside capped at credit received; short-vega/short-gamma path risk added; a winning bounce can
still mark badly mid-hold if IV spikes). The edge claim being tested is the ENTRY/EXIT TIMING, which maps
1:1; the short put additionally monetizes the IV elevation that typically accompanies the oversold print.

**Why these tickers:** the book's own strongest evidence is on SPY (index ETF); SPY/QQQ/IWM are the
closest live analogs with penny-wide chains. The mega-cap tier matches the book's "and stocks" extension
while keeping chains liquid enough for our WORST-fill grading convention.

## 3. EXACT ENTRY RULES

Underlying-signal rules (published, Ch. 9):

1. **Trend gate:** the security's close is above "its 200-day moving average" - Ch. 9 rule list, p. 65-67
   region of the full-text copy. (MA type not specified in the text read; SMA per secondary - see §8.)
2. **Trigger:** 2-period RSI of daily closes is "below 5" - Ch. 9; also the book's strategy summary list
   ("Strategy 9": buy the market and stocks when the 2-period RSI is below 5).
   Secondary corroboration (StockCharts): below 5 preferred, below 10 acceptable - we implement the
   primary's 5, not the secondary's relaxation.
3. **Entry timing:** buy on the close of the signal day - Ch. 9 example ("Buy on the close"; the S&P
   example describes an RSI reading under 5 after a 60-point, 7-day sell-off, buying that close).
   Our shadow computes RSI(2) from the near-final daily close during 15:30–15:50 ET and enters then
   (ADAPTED mechanics; the signal itself is close-based per source).
4. **Regime / IV gate:** NONE published beyond the 200-day MA. The book has no IV, VIX, or event gate in
   this chapter. Any VIX-percentile logging we do is observe-only (PLATFORM-POLICY, §8/§9).
5. **Published aggressive variant (recorded, NOT our default):** Cumulative RSI - sum the past X days of
   the 2-period RSI, buy if the sum is below Y; tested with X=2, Y=35 and X=2, Y=50 on SPY (Ch. 9).

Option-leg construction (ALL ADAPTED - no published values exist; see §8 for tags):

- Sell 1 put on the signal underlying, target delta ≈ 0.30 (band 0.25–0.35), nearest listed strike.
- Expiry: nearest weekly with 7–14 calendar DTE (must be ≥7 so the typical 3–4 trading-day hold is never
  truncated by expiry).
- Liquidity gates (OI, max spread %, quote presence): platform-standard, PLATFORM-POLICY.
- Earnings gate (single names only): skip entry if earnings fall before entry+7 calendar days,
  PLATFORM-POLICY - the published form has no event awareness.

## 4. EXACT EXIT RULES (override platform exit doctrine for this strategy)

1. **Primary published exit:** exit when the 2-period RSI "closes above 65" - Ch. 9, verbatim rule
   (which adds that any of the exit methods from the Exits chapter may be used instead).
   → Shadow: when the underlying's daily close prints RSI(2) > 65, buy back the short put at the first
   mark thereafter (next-session open in practice; ADAPTED execution mapping of a close-based signal).
2. **Published alternative exits (Ch. 13 "Exit Strategies," recorded, not default):** close above the
   5-period moving average; RSI-level exits generally. Secondary (StockCharts) states the 5-day-SMA-cross
   exit as the standard form. We implement the RSI>65 exit because it is the one printed inside Ch. 9 itself.
3. **Stop loss: NONE - published doctrine.** Ch. 13, "What about Using Trailing Stops?": across hundreds
   of tests, few if any stop strategies consistently improved results. NO price stop, NO premium-multiple
   stop on the short put. This explicitly OVERRIDES the platform exit ladder for this strategy.
4. **Time exit:** none published (exits are indicator-based; avg holds 3.57–3.7 trading days in the Ch. 9
   SPY tests). ADAPTED failsafe forced by the option vehicle: if the exit signal has not fired by 1 DTE,
   buy the put back at ≤1 DTE (we cannot carry through expiry/assignment on an options-only shadow).
5. **Roll rules:** none published; we do not roll (a new entry requires a fresh RSI(2)<5 signal).
6. **[unverified] variant seen only in tertiary articles:** abandon if close falls below the 200-day MA.
   Not found in the primary text read; NOT implemented.

## 5. SIZING CONVENTION IN SOURCE

The book trades one unit of the underlying per signal - SPX points / SPY shares, fully invested in the
single position while the signal is on, no leverage, no per-trade risk formula stated in Ch. 9 (results
are reported as % gain per trade and index points). No options sizing exists in the source. Our shadow
runs **1 short put contract per signal, account-blind** (platform convention), CaR basis in §10.

## 6. DOCUMENTED PERFORMANCE

All published numbers are for the LONG-UNDERLYING form. There is NO published performance for the
short-put expression - that is exactly what this shadow lane exists to measure.

- Cumulative RSI, SPY, Jan-1993 → Dec-31-2007, X=2 Y=35: 50 signals, 88% correct, 65.53 SPY points,
  avg gain +1.26%/trade, avg hold 3.7 trading days. **[verified-primary]** (Ch. 9 test table)
- Cumulative RSI, SPY, same period, X=2 Y=50: 105 signals, 85.47% correct, 105.95 SPY points,
  avg gain +1.05%/trade, avg hold 3.57 trading days. **[verified-primary]** (Ch. 9 test table)
- Majority of indices/ETFs examined were correct >75% of the time using 2-day cumulative RSI(2)
  readings under 40. **[verified-primary]** (Ch. 9)
- The SPY variant captured approximately the whole 15-year SPY gain while in the market <20% of the
  time. **[verified-primary]** (Ch. 9, paraphrased from the full-text copy)
- SPY, 1993–present (rules paywalled, RSI(2) family): avg gain +0.9%/trade, CAGR ≈ 9%, max drawdown 34%,
  time invested 28%. **[verified-secondary]** (QuantifiedStrategies Substack)
- Often-quoted stat that stocks with RSI(2)<2 averaged ≈ +0.79% the following week: **[unverified]** - 
  appears in search summaries; I did not find it in the primary text read. Do not build on it.
- No standalone trade table for the PLAIN RSI(2)<5 rule (as opposed to the cumulative variant) was found
  in the primary text read: plain-form win rate / avg gain = **UNKNOWN**. Do not quote the 88% figure for
  the plain rule.

Methodology caveats: in-sample-era book (published 2008, data through 2007); close-based fills, no costs
mentioned in the text read; the cumulative variant's 88% is on 50 trades (small N); post-publication
attenuation of daily mean-reversion is widely claimed but **[unverified]** here.

## 7. KNOWN FAILURE MODES

- **Falling-knife left tail (structural):** mean-reversion entry with NO stop rides losers until RSI
  recovers; the 34% max DD [verified-secondary] on the stock form is this failure realized. The short-put
  form concentrates it: gap-through-strike overnight turns a small-credit trade into a multiple-of-credit
  loss.
- **Vol-spike episodes while still above the 200-day MA** (the trend gate does NOT protect against the
  first leg down): Feb-2018 Volmageddon; Oct-2018; late-Feb-2020 COVID break (first oversold prints fired
  above the 200-day); **Aug-5-2024 yen-carry vol spike** - in each, a short put opened on the oversold
  print marked violently against the position as IV exploded, even when the bounce eventually came
  (path risk our e-process grader will see that the stock backtest never did).
- **Signal clustering / correlated book:** RSI(2)<5 fires market-wide on the same day; SPY+QQQ+IWM+six
  mega-caps can all trigger at once - nine correlated short puts is one trade, not nine.
- **Early assignment (structural, short ITM put):** deep-ITM puts near expiry get exercised early
  (dividend on the SHORT-CALL side is not our issue, but ITM-put early exercise around ex-div/interest
  is); mitigated by the ≤1-DTE failsafe buyback, PLATFORM-POLICY.
- **Earnings gaps (single-name tier):** the published form is event-blind; an oversold print two days
  before NVDA earnings is a different animal - hence the ADAPTED earnings gate.
- **Regime attenuation:** daily mean-reversion edge is widely claimed weaker post-2008 [unverified];
  the 2008 book is effectively all pre-2008 evidence.
- **Spread/liquidity stress:** the signal fires exactly when put spreads are widest; WORST-fill grading
  will punish entries in stressed chains - expected, not a bug.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | signal_timeframe | daily closes | SOURCE-VERBATIM | Ch. 9 tests are on daily closing prices; entry "on the close" |
| 2 | rsi_period | 2 | SOURCE-VERBATIM | Ch. 9 title/rules: "2-period RSI" |
| 3 | rsi_formula | Wilder RSI | ADAPTED (assumed) | standard RSI definition; formula variant not restated in the text read → recorded in unknowns |
| 4 | trend_filter_length | 200 days | SOURCE-VERBATIM | Ch. 9 rule: above "its 200-day moving average" |
| 5 | trend_filter_ma_type | SMA | ADAPTED (assumed) | primary says only "moving average"; SMA per secondary (StockCharts) → recorded in unknowns |
| 6 | entry_rsi_threshold | RSI(2) < 5 | SOURCE-VERBATIM | Ch. 9 / Strategy list #9: 2-period RSI "below 5" (secondary notes <10 acceptable; not used) |
| 7 | entry_execution | at signal-day close (shadow: 15:30–15:50 ET compute + enter) | SOURCE-VERBATIM + ADAPTED mechanics | Ch. 9 example: "Buy on the close" |
| 8 | exit_rsi_threshold | RSI(2) daily close > 65 | SOURCE-VERBATIM | Ch. 9: exit when 2-period RSI "closes above 65" |
| 9 | exit_execution_mapping | buy put back at first mark after exit-signal close (next open) | ADAPTED | close-based signal mapped to option fill; no published option mechanics |
| 10 | alt_exit_5ma | close > 5-period MA (recorded alternative, NOT default) | SOURCE-VERBATIM | Ch. 13 exit list: close above the 5-period MA; StockCharts standard form |
| 11 | stop_loss | NONE (overrides platform ladder) | SOURCE-VERBATIM | Ch. 13 "What about Using Trailing Stops?": stop strategies did not consistently improve results |
| 12 | time_exit | none published; option failsafe row 16 | SOURCE-VERBATIM | Ch. 9: exits are indicator-based; avg holds 3.57–3.7 days |
| 13 | cum_rsi_variant_X | 2 (variant only, not implemented) | SOURCE-VERBATIM | Ch. 9 cumulative test: X=2 days summed |
| 14 | cum_rsi_variant_Y | 35 (also tested 50) (variant only) | SOURCE-RANGE | Ch. 9 cumulative test: buy if sum < Y; Y=35 and Y=50 both tabled |
| 15 | option_structure | single-leg short put, 1 contract | ADAPTED | options-only platform; expresses published long-underlying entry |
| 16 | expiry_failsafe_exit | buy back at ≤1 DTE if exit signal hasn't fired | ADAPTED | option vehicle cannot hold through expiry; no source analog |
| 17 | strike_delta_target | 0.30 (band 0.25–0.35), nearest strike | ADAPTED | no published value; premium-selling convention balancing bounce-delta vs assignment risk |
| 18 | dte_target | 7–14 calendar days, nearest weekly ≥7 | ADAPTED | no published value; sized so the 3–4-day published hold fits inside the option's life |
| 19 | earnings_gate | skip single-name entry if earnings < entry+7 cal days | PLATFORM-POLICY | published form is event-blind; ours by policy |
| 20 | liquidity_gates | platform-standard OI / max-spread% / quote-presence | PLATFORM-POLICY | ours by policy; no source analog |
| 21 | position_size | 1 contract, account-blind | PLATFORM-POLICY | shadow convention (source sizes one underlying unit, §5) |
| 22 | iv_regime_gate | none (VIX percentile logged observe-only) | PLATFORM-POLICY | no published IV/VIX gate in Ch. 9 |

UNKNOWN constants (recorded honestly, no invented values):
- **rsi_formula_variant** - Wilder assumed; the text read never restates the RSI formula.
- **trend_filter_ma_type** - SMA vs EMA not specified in the primary text read (SMA adopted per secondary).
- **plain_rsi5_trade_stats** - no standalone published trade table for the plain RSI(2)<5 rule was found
  (only the cumulative variant is tabled); plain-form published win rate/avg gain = UNKNOWN.
- **all option-leg published values** - delta, DTE, credit, roll: UNKNOWN in source (do not exist);
  our values are ADAPTED and must never be attributed to Connors/Alvarez.

## 9. DATA REQUIREMENTS

- **Daily history:** ≥210 trading days of daily closes per underlying (200-SMA + RSI(2) warm-up). Core.
- **Tradier chains:** DTE band 5–21 calendar days (selection targets 7–14; the wider band covers strike
  hunting and the ≤1-DTE failsafe marks). Puts only.
- **1-min bars:** for the 15:30–15:50 ET near-close signal compute and for entry/exit marks.
- **Earnings calendar (date + bmo/amc):** required for the six single names (gate row 19). Not needed for
  SPY/QQQ/IWM.
- **FOMC/CPI dates:** NOT a published gate; log-only covariate for the grader.
- **VIX regime / IV rank:** NOT a published gate; log VIX percentile as covariate (IV-rank archive is
  cold → VIX-percentile fallback per platform note).
- **Mark cadence:** daily close is decision cadence; intraday marks (existing platform cadence) for the
  three-fill ledgers and vol-spike path visibility.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** the cumulative variant fired ~7/yr on SPY (105 signals / 15 yrs); the plain
  RSI(2)<5 rule fires materially more often - order of 1–2/month per liquid underlying in normal regimes,
  but CLUSTERED (all nine tickers tend to fire in the same pullback week). Blended estimate across the
  9-ticker universe: **~8 trades/month**, arriving in bursts with dead calm between. N≥25 gradeable in
  roughly 3–4 months; clustering means effective independent N grows slower than trade count.
- **Multi-leg shape:** none - single-leg short put. Simplest possible chain requirements.
- **Capital-at-risk basis:** short naked put → **Reg-T CaR proxy** per platform convention for undefined-
  downside-to-zero legs (cash-secured equivalent = strike × 100 − credit is the hard ceiling; use that as
  the CaR denominator if the family wants a bounded basis - flag which one the grader adopts, do not mix).
- **Mark cadence needed:** daily-close decisions; intraday marks required anyway because the failure mode
  of interest (IV-spike path pain before the bounce) is invisible at daily granularity.
- **1-lot account-blind distortion:** minimal for signal fidelity - the source is effectively 1-unit
  in/out too (§5). The REAL distortion vs the published record is the vehicle (short put vs long stock):
  capped upside means the published +1.05–1.26%/trade avg gains do NOT translate; expect a
  high-win-rate / small-credit / fat-left-tail profile instead. Grade against the e-process, not against
  the book's stock-form numbers.
- **Doctrine override reminder:** NO stop-loss and NO profit-target on this lane (§4 rule 3) - the exit
  is RSI(2)>65, the ≤1-DTE failsafe, nothing else. Platform exit-ladder logic must be disabled for this
  family; the whole point is testing the published exit doctrine as written.

## 11. VERIFICATION

**Verdict: CONFIRMED** - adversarial re-verification by a fresh-context verifier, 2026-07-19.

What was checked (all sources re-fetched live, not recalled):

- **Primary (epdf.pub full text of Connors & Alvarez 2008):** every SOURCE-VERBATIM / SOURCE-RANGE
  constant in §3, §4, and §8 was located: 200-day moving average gate ("above its 200-day moving
  average"); 2-period RSI; plain entry rule ("Strategy 9: Buy the market and stocks when the 2-period
  RSI is below 5"); "Buy on the close" incl. the S&P example (60-point / 7-day sell-off, RSI under 5);
  exit "Exit when the 2-period RSI closes above 65"; cumulative-RSI variant X=2 with Y=35 and Y=50;
  5-period-MA alternative exit ("The best are the close above the 5-period moving average, and the RSI
  exits"); no-stop doctrine verbatim ("But in hundreds and hundreds of tests, few if any 'stop
  strategies' consistently improved test results").
- **[verified-primary] performance numbers, all found exactly:** Y=35 test - 50 signals, 88% correct,
  65.53 points, +1.26%/trade, 3.7-day holds; Y=50 test - 105 signals, 85.47%, 105.95 points,
  +1.05%/trade, 3.57-day holds; period "mid-January 1993 through December 31, 2007"; majority of
  indices/ETFs correct >75% with 2-day cumulative readings under 40; "picked up approximately all the
  SPY gains made in 15 years while only being in the market less than 20% of the time."
- **Secondary 1 (StockCharts ChartSchool):** confirms 200-day SMA, below-5-preferred / below-10-
  acceptable entry, 5-day-SMA exit, and Connors' finding that stops "hurt" performance - matches the
  brief's use of it for the SMA-type assumption.
- **Secondary 2 (QuantifiedStrategies Substack):** [verified-secondary] numbers all present - +0.9%
  avg/trade, ~9% CAGR, 34% max drawdown, 28% time invested; rules confirmed paywalled, as the brief
  states.
- **ADAPTED / PLATFORM-POLICY tags:** every option-leg value (short-put structure, 0.30 delta band,
  7–14 DTE, ≤1-DTE failsafe, earnings gate, sizing) carries an explicit adaptation rationale and is
  nowhere attributed to the source. UNKNOWN items (RSI formula variant, MA type in primary, plain-form
  trade table) are honestly recorded as unknown rather than filled in.
- **No corrections were required.** The one phrase spot-checked beyond the tags ("across hundreds of
  tests") is actually understated relative to the source's "hundreds and hundreds of tests."

Residual doubts: page numbers (pp. 65–67) could not be confirmed from the HTML copy (no pagination) - 
locators are chapter-level, which is what the brief's claims actually rest on. The epdf.pub copy is an
unofficial full-text mirror; its fidelity to the print edition is assumed but the constants it contains
are internally consistent and match both independent secondaries. Post-2008 edge attenuation remains
[unverified] as flagged - the shadow lane itself is the test.

---

### Independent adversarial re-verification - 2026-07-19 (second, fresh-context pass)

**Verdict: CONFIRMED.** This pass did NOT rely on the verification text above (which pre-existed in the
file); all three cited sources were re-fetched live and every checked constant was located independently.

Checked and FOUND in the primary (epdf.pub copy of Connors & Alvarez 2008):
- 200-day moving average gate ("above its 200-day moving average"; renders as "20D-day" in one OCR spot).
- Strategy 9 entry: "Buy if the 2-period RSI is below 5"; "Buy on the close"; the S&P example ("A
  60-point sell-off in the S&Ps in 7 days triggering an RSI reading under 5").
- Exit: "Exit when the 2-period RSI closes above 65".
- Cumulative-RSI tests, both rows exact: X=2 Y=35 → 50 signals / 88% / 65.53 SPY points / +1.26% /
  3.7-day holds; X=2 Y=50 → 105 signals / 85.47% / 105.95 points / +1.05% / 3.57-day holds; period
  "mid-January 1993 through December 31, 2007".
- ">75% correct" statement, verbatim tied to "2-day … cumulative RSI readings under 40".
- "picked up approximately all the SPY gains made in 15 years while only being in the market less than
  20% of the time".
- Ch. 13 no-stop doctrine: "in hundreds and hundreds of tests, few if any 'stop strategies' consistently
  improved test results"; 5-period-MA alternative exit listed in the Exit Strategies section.
- Options: NOT mentioned anywhere in the source - confirming the brief's loud-adaptation framing is
  accurate (the entire option leg is correctly tagged ADAPTED/PLATFORM-POLICY, nothing attributed to source).

Checked and FOUND in secondaries: StockCharts (200-day MA per Connors, below-5 higher-return vs
below-10 acceptable, 5-day-SMA exit, "stops actually 'hurt' performance"); QuantifiedStrategies Substack
(+0.9%/trade, 9% CAGR, 34% max DD, 28% time invested, rules confirmed behind the paid-subscriber wall).

No INVENTED constants found; no corrections required. Residual doubts unchanged from above, plus one:
the epdf.pub page presents as a landing/excerpt page rather than confirmed complete pagination-faithful
text, so chapter-level locators (not page numbers) remain the reliable citation grain.
