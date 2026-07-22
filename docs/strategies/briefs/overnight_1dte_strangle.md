# Strategy Brief: overnight_1dte_strangle

Overnight short strangle: sell ~25-delta 1DTE at the close, buy back at the open. Researched
2026-07-19. Primary source: Muravyev & Ni (JFE 2020). The published JFE body is paywalled and was
NOT read directly; the paper's official Internet Appendix (41 pages, author-hosted) was READ IN
FULL (PDF extracted to text), the published abstract was read VERBATIM (Semantic Scholar API +
EconPapers), and an independent secondary review (CXO Advisory) of the working paper was READ IN
FULL. Every constant in sections 3, 4, 8 carries a direct quote or a precise locator. UNKNOWN
means UNKNOWN.

**READ THIS FIRST - honesty box.** The published object is a *return decomposition*, not a retail
strategy spec. The paper proves that option returns are negative overnight and positive intraday,
and its appendix prices out one implementable form: "sells and delta hedges SPY options overnight"
(IA Table A.20 caption). The specific shape in our id - a ~25Δ, 1DTE, two-leg strangle, unhedged - 
is OUR adaptation of that finding, not a published recipe. There is NO published delta target, NO
published 1-DTE evidence (the paper's shortest maturity bucket is 4–15 trading days), and the
published headline numbers are for DELTA-HEDGED positions. Every one of those gaps is tagged
ADAPTED below, with the closest published quote given for each. Sections 2 and 8 are loud about
this on purpose.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `overnight_1dte_strangle`
- **Provenance class:** academic
- **PRIMARY citation:**
  - Muravyev, Dmitriy and Ni, Xuechuan (Charles), *"Why do option returns change sign from day to
    night?"*, **Journal of Financial Economics**, 2020, Vol. 136, Issue 1, pp. 219–238.
    DOI: 10.1016/j.jfineco.2018.12.006.
    URL: https://doi.org/10.1016/j.jfineco.2018.12.006
    (publisher page: https://www.sciencedirect.com/science/article/abs/pii/S0304405X19302193 - 
    closed access; abstract read verbatim via the Semantic Scholar Graph API record for
    DOI 10.1016/j.jfineco.2018.12.006 and via EconPapers RePEc:eee:jfinec:v:136:y:2020:i:1:p:219-238).
  - **Internet Appendix (READ IN FULL, author-hosted, the load-bearing primary text for this
    brief):** *"Internet Appendix for 'Why Do Option Returns Change Sign from Day to Night?'"*,
    41 pp., https://www.dmurav.com/MuravyevNi_WhyDoOptionReturnsChangeSign_IA.pdf - contains the
    trading-strategy section (A.7), the straddle/unhedged robustness (A.3 §, Table A.7), returns by
    delta and maturity (Tables A.3, A.4), alternative open/close price conventions (Table A.9), and
    the SPY cost table (Table A.20).
  - Working-paper version: SSRN abstract 2820264, first posted July 2016
    (https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2820264 - SSRN returned 403 to our
    fetcher; the SSRN page was NOT read directly, only quoted through secondary channels).
- **SECONDARY (independent, read in full):**
  - CXO Advisory, *"Intraday Versus Overnight Option Returns"* (review of the 2016 working-paper
    version), https://www.cxoadvisory.com/equity-options/intraday-versus-overnight-option-returns/
- **Publication dates:** working paper July 2016 (SSRN); published JFE 2020 (accepted Dec 2018 per
  DOI year). Sample studied: intraday option quotes January 2004 – April 2013 (per CXO summary;
  the IA states "our sample period 2004 to 2013" and Table A.15 uses index data "from January 2004
  to December 2013"; Table A.12 counts "2298 daily return observations", ≈ Jan-2004→Apr-2013).

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**What the source trades/studies:** S&P 500 (SPX) index options are the headline sample
(delta-hedged returns, quote midpoints); the panel extends to individual **equity options** and to
the three most liquid **ETF options - explicitly SPY, QQQ, and IWM**: "we also study average
option returns of the three most liquid ETFs: S&P 500 (SPY), NASDAQ 100 (QQQ), and Russell 2000
(IWM). Besides SPX, these three have the most actively traded options in OPRA data." (IA §A.1).
The implementable strategy is priced on SPY: "For the trading strategy, we focus on options on
SPDR S&P 500 ETF (ticker SPY), the world's most liquid ETF, that are a close substitute for S&P
index options but incur much lower transaction costs." (IA §A.7).

**Our mapping:** SPY / QQQ / IWM as the core - these three are **inside the published sample**
(IA Table A.2 Panel B: their pooled overnight option return is −0.48%/day, t = −16.3), so the ETF
trio is a faithful mapping, not an extension. The mega-cap tier AAPL / NVDA / MSFT / TSLA / AMD /
META maps to the paper's equity-option panel (overnight ≈ −0.4%/day per the paper's own summary,
[verified-secondary]; per-year Panel A values −0.30% to −0.50%/night [verified-primary]) - same
sign, roughly half the index magnitude, still t < −10 in every year shown.

**LOUD ADAPTATION NOTICE (four separate adaptations, all load-bearing):**
1. **No delta hedge (options-only platform).** The paper's headline −1%/night is for positions
   that are delta-hedged ("we only delta hedge once intraday" in the trade-price robustness;
   baseline hedges 5×/day per IA Figure A.1), and the IA's SPY strategy "sells and delta hedges
   SPY options overnight" (Table A.20 caption). Our platform holds NO stock legs and does NOT
   hedge. Published cover for the unhedged form: IA §A.3 + Table A.7 - **raw unhedged** option
   returns are "0.22% and -0.93% per day" (day/night, t = 2.3 / −12.1) and **straddle** returns
   (call+put combined, no underlying hedge) are "0.18% and -0.85% per day" (t = 2.5 / −17.7):
   "results for raw and straddle returns together with other robustness tests in the paper suggest
   that our main results are robust to delta-hedging." A short call + short put pair is exactly the
   straddle robustness form; striking the legs OTM (strangle) moves it to the moneyness bucket the
   paper shows has the LARGEST overnight losses (next item).
2. **~25Δ strikes (no published delta target).** The paper reports returns by delta *bucket*, not
   a target: the OTM bucket "0.1 < |∆| < 0.25" has the most negative overnight returns in every
   table (leverage-adjusted −0.102%/day, t = −13.5, shortest maturity, IA Table A.3; trade-price
   −3.84%/night, t = −18.7, IA Table A.8; straddle-form −1.00%/night, IA Table A.7). We pick 25Δ - 
   the boundary of that bucket - as our single-point implementation. Tagged ADAPTED.
3. **1 DTE (below the published maturity band).** The paper's shortest maturity bucket is
   **4–15 trading days** ("Maturity is measured as the number of trading days before expiration",
   IA Table A.4), where SPX overnight returns are −2.62%/day (t = −15.6). Options with <4 trading
   days to expiry are NOT in the published tables, and daily/1-DTE expirations mostly did not
   exist in 2004–2013. Our 1-DTE form is an EXTRAPOLATION of the published maturity gradient
   (shorter maturity → more negative overnight return), not a published result. Tagged ADAPTED,
   and grading must treat "does the effect survive at 1 DTE" as an open hypothesis.
4. **Single names extend the claim.** The published SPY-strategy pricing is index/ETF only; the
   mega-cap tier inherits idiosyncratic overnight gap risk (earnings, guidance) that the pooled
   equity panel averages over. Earnings-night handling is PLATFORM-POLICY (§8 row 17).

**Why the mapping preserves the edge claim:** the documented mechanism is that option prices fail
to discount the day-night volatility asymmetry - "option prices' failing to account for the
well-known fact that stock volatility is substantially higher intraday than overnight" (published
abstract, verbatim) - so a seller who is short only during the low-volatility overnight window
collects premium priced off too-high (average) volatility. That mispricing is a property of the
option surface on any underlying with the day-night volatility asymmetry; the paper itself
verifies it on SPX, SPY/QQQ/IWM, the equity panel, and VIX futures ("A similar return pattern
holds for all maturity and moneyness categories and equity options", abstract). Selling BOTH a
call and a put isolates the volatility premium (implicit delta-hedge: "Taking an average across
calls (positive delta) and puts (negative delta) to compute returns on a given day provides
implicit delta-hedging (the residual delta is small)", IA §A.3).

## 3. EXACT ENTRY RULES

The published strategy has **no trigger condition** - it is an unconditional every-night short:
"a hypothetical trading strategy that sells SPY options overnight" (IA §A.7); the overnight-only
form is independently described by CXO as "executing the strategy only overnight"
[verified-secondary]. (A commonly circulated WP-abstract phrasing, "selling option volatility only
overnight and holding no position during the day", could NOT be located verbatim in any source
actually read - SSRN 403, phrase absent from CXO - treat that wording as unverified-verbatim;
its substance is corroborated.) The paper explicitly
checked conditioning variables and found none that matter: "market conditions produce little
variation in overnight returns" (IA §A.1, re Table A.11 sorts on VIX, LIBOR, TED, liquidity,
sentiment, tail risk) and "none of the variables significantly predicts the day-night return
difference" (IA §A.1, re Table A.12). **There is no published IV gate, no regime gate, no event
filter.** Absence verified against the full 41-page appendix.

- **Cadence:** every trading day, at the close. Fridays INCLUDED - the baseline overnight return
  includes weekends, and excluding them SHRINKS the effect (trade-price overnight −2.26% including
  weekends vs −1.82% "Exclude Weekends", IA Table A.8 → the weekend night is at least as
  profitable to the seller).
- **Entry timing:** at the close. Published baseline: close quote midpoint at the option-market
  close ("index options close at 4:15p.m.", IA Table A.9 note); the paper's robustness row using
  "a 4 p.m. quote midpoint as the close price" gives overnight −1.08% (t = −16.1), essentially
  identical - so our 4:00 p.m. ET entry snapshot is inside the published convention band.
- **Structure:** sell 1 OTM call + sell 1 OTM put, same underlying, same expiry (short strangle).
  ADAPTED from the paper's delta-hedged singles / straddle robustness form (see §2 item 1).
- **Strike selection:** each leg at the listed strike nearest to |Δ| = 0.25 (call ≈ +0.25Δ, put ≈
  −0.25Δ), computed from the entry chain snapshot. ADAPTED - published support is the bucket
  boundary, not a target: "0.1 < |∆| < 0.25" is the most negative overnight bucket (IA Tables
  A.3/A.7/A.8; "Moneyness is measured as absolute option delta", IA Table A.3 note).
- **DTE selection:** expiry = next trading session (1 trading day at entry; Friday entry → Monday
  expiry where daily expirations exist). ADAPTED beyond the published 4–15-trading-day minimum
  bucket (IA Table A.4) - see §2 item 3.
- **Published regime/IV gate:** NONE (quotes above). Any gating we add (earnings, ex-div) is
  PLATFORM-POLICY, tagged in §8, and must be logged as ours, never attributed to the source.

## 4. EXACT EXIT RULES

These override all platform exit doctrine for this strategy. The overnight window IS the trade.

- **Time exit, unconditional:** buy back BOTH legs at the next market open. The published window
  is exact: "An overnight period is from 4:15 pm to 9:30 am." (IA Table A.10 note, set "to match
  the options results"); "night and day periods are 17.5 and 6.5 hours, respectively" (IA
  §A.4 - note the source order: NIGHT is the 17.5-hour period, day is 6.5 hours). Exit price convention in the source is the opening quote midpoint; the robustness row
  "Open at 10am" (−1.17% overnight, IA Table A.9) shows a few minutes of open-quote settling does
  not change the sign or magnitude materially.
- **No profit target.** SOURCE-VERBATIM absence - no profit-taking rule exists anywhere in the
  paper or appendix; the position is never managed intra-window.
- **No stop loss.** SOURCE-VERBATIM absence - no loss-management rule exists; a gap through a
  strike is exited at the open like any other night (this is what "generating positive gross
  returns in every 3-month interval, including the financial crisis" [verified-secondary - CXO,
  verbatim] was measured over - with delta hedges, on ≥4-DTE options; our unhedged 1-DTE tail is
  fatter, see §7).
- **No roll rules, no hold-to-expiry.** The strategy is flat from open to close by construction
  ("executing the strategy only overnight", CXO [verified-secondary]; the WP-abstract phrase
  "holding no position during the day" is unverified-verbatim - see §3).
  For the 1-DTE form the exit morning is expiration morning: the open buy-back is MANDATORY
  (failure to fill = same-day expiry/assignment exposure, which the published form never has).
  Implementation must retry the close-out and log slippage vs the 9:30 quote mid; letting a leg
  ride to same-day expiry is a rule violation, not a discretionary hold.
- **Early assignment (ours only):** American-style short legs can be assigned overnight (exercise
  notices after the close). If assigned, close the resulting exposure at the open mark, log
  `early_assignment` as a forced exit. Does not exist in the published (index/delta-hedged) form.

## 5. SIZING CONVENTION IN SOURCE

The source publishes **percentage returns on option value** (quote-midpoint to quote-midpoint,
per-day), not an account-sized program: returns "are in percentage points per day" (IA table
notes, passim); the strategy table reports "Option Overnight Returns" vs "Trading Costs" as
percentages of option price (IA Table A.20). There is no %-of-buying-power, no contract count, no
collateral convention anywhere. Delta hedges in the underlying are assumed frictionlessly
available ("We focus on the bid-ask spread as it is typically much larger than other option costs,
such as hedging costs in the underlying, brokerage/exchange commissions, margin/funding costs",
IA §A.7). **Our shadow:** 1 published unit = 1 contract per leg (1 short call + 1 short put) per
symbol per night, account-blind per platform convention.

## 6. DOCUMENTED PERFORMANCE

Decomposition facts (the paper's core result):
- SPX delta-hedged option returns: **−0.7% per day** total; **−1% per day overnight
  (close-to-open)**; **+0.3% intraday (open-to-close)** - "Average delta hedged returns for
  Standard & Poor's 500 index options are large: −0.7% per day. When we decompose these option
  returns into intraday and overnight components, average close-to-open returns are −1% per day
  and open-to-close returns are positive, 0.3%." [verified-primary - published abstract, verbatim]
- Shortest published maturity bucket (4–15 trading days), SPX: overnight **−2.62%/day**
  (t = −15.6), intraday +0.73% [verified-primary - IA Table A.4]. CXO's rendering of the same WP
  fact: "Average overnight (intraday) return is -2.6% (+.07%) for options with less than three
  weeks to expiration" [verified-secondary, verbatim].
- OTM bucket 0.1<|Δ|<0.25: leverage-adjusted overnight −0.102%/day (t = −13.5, 4–15d column)
  [verified-primary - IA Table A.3]; trade-price overnight −3.84% (t = −18.7) [verified-primary - 
  IA Table A.8]; CXO: "Average overnight (intraday) return is -1.7% (+.03%) for out-of-the-money
  options" [verified-secondary, verbatim].
- Unhedged (raw) returns: day/night **+0.22% / −0.93%** (t = 2.3 / −12.1); straddle returns
  **+0.18% / −0.85%** (t = 2.5 / −17.7) [verified-primary - IA Table A.7 and §A.3 text].
- ETF options (SPY+QQQ+IWM pooled): overnight **−0.48%/day** (t = −16.3), intraday +0.14%
  (t = 3.1), 2004–2013 [verified-primary - IA Table A.2 Panel B]. Equity options: overnight
  ≈ **−0.4%/day** [verified-secondary - paper summary via search/CXO channel; per-year Panel A
  values −0.30% to −0.50%, all t ≤ −3.5, verified-primary].

Strategy-form numbers:
- Overnight-only selling (SPX, delta-hedged): "executing the strategy only overnight increases
  average gross daily return to 1.0%", "more than doubling gross Sharpe ratio" and "generating
  positive gross returns in every 3-month interval, including the financial crisis"
  [verified-secondary - all three CXO verbatim; the SSRN working-paper abstract itself returned
  403 and was NOT read, and the published JFE abstract does not contain these sentences].
- SPY implementable version (delta-hedged, algo-quality execution): overnight option return
  **−0.64%** post-Penny-Pilot (i.e., +0.64% gross to the seller); algo trading cost **0.05%**;
  **"Profits after Costs for Algos" = 0.60% per day**; pre-Pilot the same strategy nets −0.01%
  ("breaks even") [verified-primary - IA Table A.20 + §A.7 text: "highly profitable in the
  post-Pilot period (0.6% per day)"]. Non-algo (conventional effective spread) costs 1.24%
  post-Pilot - larger than the gross edge: "The costs for average investors are too high"
  [verified-primary - IA §A.7].
- **Win rate: UNKNOWN** - not published (closest: "positive gross returns in every 3-month
  interval" [verified-secondary - CXO], which is a quarterly, not per-trade, statement).
- **Profit factor: UNKNOWN** - not published.
- **Max drawdown: UNKNOWN** - not published in any source read.
- **Absolute Sharpe ratio: UNKNOWN** - only the relative claim ("more than doubling gross Sharpe
  ratio", CXO verbatim) is published [verified-secondary].

**Methodology caveats:** all returns are frictionless quote-midpoint returns unless stated;
delta-hedged unless stated; sample ends April 2013 - **nothing after 2013 is verified by any
source read for this brief**, and the options market's structure (0DTE/daily expirations, the
very instruments we trade) postdates the sample entirely. Returns are per unit of option value,
not per unit of margin/collateral - do NOT compare them to our CaR-based P&L percentages without
conversion.

## 7. KNOWN FAILURE MODES

Historical episodes:
- **2008–2009 GFC (in-sample):** the published overnight-selling strategy generated "positive
  gross returns in every 3-month interval, including the financial crisis" [verified-secondary - 
  CXO, verbatim], and equity/ETF intraday-
  vs-overnight asymmetry held ("their 2008 returns are expectedly more positive than in other
  years", IA §A.1) - but that resilience is for DELTA-HEDGED, ≥4-DTE positions. It is NOT
  evidence that an unhedged 1-DTE strangle survives a crash night.
- **Feb 5, 2018 "Volmageddon", Mar 2020 COVID overnight limit-downs, Aug 5, 2024 overnight VIX
  spike (Nikkei-carry unwind):** ALL post-sample; the Aug-2024 event is the canonical nightmare
  for this exact shape - the vol spike built up overnight, exactly inside the held window, gapping
  25Δ strikes deep ITM before any exit was possible. [unverified as to magnitude - no source read
  covers them; flagged for live monitoring, not for silent extrapolation.]
- **Effect attenuation risk:** the mechanism is a pricing *bias*; the day-night volatility ratio
  it feeds on declined in-sample ("The ratio slowly decreases from about 3.5 in 2004 to about two
  in 2013", IA §A.4), and the post-2013 explosion of 0DTE/overnight option trading is precisely
  the marginal flow that could arbitrage it away ("marginal investors who have low execution
  costs, not average investors, are responsible for arbitraging away such 'good deals'", IA §A.7).
  Treat the live edge as hypothesis, not annuity.

Structural failure modes (mostly ours, from the adaptations):
- **Gap through a strike, no hedge, no stop:** a 25Δ 1-DTE strike sits close to spot; an
  overnight gap converts a few-dollar credit into a many-hundred-dollar debit with zero
  intra-window recourse (exit rules forbid stops by construction). The unhedged night return
  distribution has severe negative skew for the seller - the paper's own equity overnight return
  stats show excess kurtosis 61.8 (IA Table A.1 Panel B).
- **Single-name earnings nights (AMC):** an overnight gap machine pointed directly at this
  structure; the published equity panel averages over earnings nights, but 1-lot exposure does
  not. PLATFORM-POLICY skip (§8 row 17).
- **Macro releases inside the window:** CPI/NFP print at 8:30 a.m. ET - INSIDE the close→open
  hold. FOMC (2 p.m.) is outside it. The source has no event filter (§3); we trade through and
  tag (§8 row 18).
- **Early assignment:** short American legs can be assigned overnight once ITM (calls over an
  ex-div night are the classic channel - SPY/QQQ/IWM quarterly ex-div dates; deep-ITM-overnight
  puts near expiry likewise). The published (SPX/European, delta-hedged) form has none of this.
- **Expiration-morning close-out risk (1-DTE only):** the exit open IS expiry day; a missed or
  partial buy-back leaves same-day expiry/pin/assignment exposure the published form never has.
- **Execution-cost fragility:** the published net edge exists ONLY at algo-quality costs (0.05%
  vs a 0.60% net; non-algo 1.24% cost kills it - IA Table A.20). Our shadow's mid-quote fills
  implicitly assume BETTER-than-algo execution; real-fill haircuts must be applied at grading,
  and the 9:30 opening quotes (our exit) are the day's widest ("option bid-ask spreads ... about
  6% in our sample" for SPX; SPY "less than half" that, IA §A.1/A.7).

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | published_underlying | SPX index options; ETF options SPY/QQQ/IWM; equity-option panel | SOURCE-VERBATIM | "we focus on options on SPDR S&P 500 ETF (ticker SPY)" (IA §A.7); "three most liquid ETFs: S&P 500 (SPY), NASDAQ 100 (QQQ), and Russell 2000 (IWM)" (IA §A.1) |
| 2 | our_universe | SPY, QQQ, IWM + AAPL, NVDA, MSFT, TSLA, AMD, META | ADAPTED | ETF trio is in-sample (IA Table A.2 Panel B); mega-caps map to the equity panel (overnight ≈ −0.4%/day [verified-secondary]) and add earnings-gap risk the pooled panel dilutes (§2) |
| 3 | structure | short strangle: sell 1 OTM call + sell 1 OTM put, same expiry, no stock legs, no hedge | ADAPTED | Published forms: delta-hedged singles (baseline) and no-underlying-hedge robustness - straddle "0.18% and -0.85% per day" and raw "0.22% and -0.93% per day" day/night (IA §A.3, Table A.7); options-only platform forbids the hedge leg |
| 4 | delta_target | each leg nearest listed strike to \|Δ\| = 0.25 | ADAPTED | No published target exists. Bucket evidence: "0.1 < \|∆\| < 0.25" is the most negative overnight bucket in every table (IA Tables A.3/A.7/A.8; "Moneyness is measured as absolute option delta", A.3 note); 25Δ = that bucket's boundary |
| 5 | delta_tolerance_band | accept 0.15 ≤ \|Δ\| ≤ 0.30, else skip symbol that night | PLATFORM-POLICY | Ours (keeps both legs inside/near the published 0.1–0.25 bucket on coarse strike ladders); no published value |
| 6 | dte | 1 trading day (expiry = next trading session; Fri→Mon counts as 1) | ADAPTED | BELOW the published band: shortest published bucket "4-15" trading days, overnight −2.62%/day t=−15.6 ("Maturity is measured as the number of trading days before expiration", IA Table A.4); <4 DTE is untested in the source - extrapolation of the published maturity gradient |
| 7 | entry_time | last chain snapshot at/before 4:00 p.m. ET | SOURCE-RANGE | Baseline = close quote ("index options close at 4:15p.m.", IA Table A.9 note); robustness "Close at 4pm" gives overnight −1.08% t=−16.1 (IA Table A.9) - our 4:00 p.m. sits on the published alternative; default recorded: 4:00 p.m. ET |
| 8 | entry_fill_convention | both legs at quote MIDPOINT of the entry snapshot | SOURCE-VERBATIM | "Computing returns with the quote midpoints is a de facto standard" (IA §A.2); bid-only/ask-only robustness: overnight −1.08%/−0.96% (IA Table A.9) |
| 9 | entry_gate | NONE - unconditional, every trading day incl. Fridays | SOURCE-VERBATIM (absence) | No conditional entry anywhere in 41-pp appendix; "market conditions produce little variation in overnight returns" (IA §A.1, Table A.11); weekends in-sample and MORE negative (−2.26% incl. vs −1.82% excl. weekends, IA Table A.8) |
| 10 | iv_regime_gate | NONE | SOURCE-VERBATIM (absence) | VIX-sorted overnight returns: Low −0.86 / High −1.14, no significant H−L (t=1.2) (IA Table A.11 Panel A) - the source checked and found no gate-worthy variation |
| 11 | exit_time | next market open, 9:30 a.m. ET (first clean quote snapshot 9:30–9:35) | SOURCE-VERBATIM | "An overnight period is from 4:15 pm to 9:30 am." (IA Table A.10 note); "Open at 10am" robustness −1.17% (IA Table A.9) shows minutes of settling are tolerable |
| 12 | exit_fill_convention | both legs bought back at opening quote MIDPOINT | SOURCE-VERBATIM | Same midpoint convention as row 8 (IA §A.2) |
| 13 | profit_target | NONE | SOURCE-VERBATIM (absence) | No profit-taking rule exists in paper or appendix; window exit only |
| 14 | stop_loss | NONE (gap nights exit at the open like any night) | SOURCE-VERBATIM (absence) | No loss-management rule exists anywhere in the 41-pp IA (searched); the overnight-only window ("executing the strategy only overnight", CXO [verified-secondary]) defines the only exit |
| 15 | roll_rules | NONE - flat during every regular session | SOURCE-VERBATIM (absence) | Same locator as row 14; position never carried past the open |
| 16 | early_assignment_handling | if assigned overnight, close residual exposure at the open mark; log `early_assignment` forced exit | PLATFORM-POLICY | Impossible in the published SPX/delta-hedged form; required by American-style universe (§7) |
| 17 | earnings_night_handling | SKIP a single name whose earnings fall between entry close and exit open (bmo next day or amc entry day); ETFs never skipped | PLATFORM-POLICY | Source has no filter (equity panel trades through earnings in aggregate); 1-lot unhedged 1-DTE strangle through an AMC print is uncompensated single-night ruin risk - ours by policy, never attributed to the source |
| 18 | macro_release_handling | trade through CPI/NFP-eve nights (8:30 a.m. releases are inside the window); TAG for split grading | PLATFORM-POLICY | Source has no event filter (row 9 locators); tagging is ours |
| 19 | exdiv_night_handling | skip symbol when next session is its ex-div date (call-leg assignment channel) | PLATFORM-POLICY | No analogue in source (SPX European); standard American short-call ex-div discipline |
| 20 | position_size | 1 contract per leg, 1 strangle per symbol per night, account-blind | PLATFORM-POLICY | Source publishes %-of-option-value returns, no sizing (§5); platform 1-published-unit convention |
| 21 | car_basis | Reg-T short-strangle proxy: max(naked-call req, naked-put req) + other-side credit; recompute at entry | PLATFORM-POLICY | Undefined-risk two-leg short; source has no collateral convention (§5) - basis is ours for grading normalization |
| 22 | liquidity_gates | platform standard chain-quality funnel (quote presence, spread, OI, touch-feasibility ≥ 0.25) | PLATFORM-POLICY | Ours by policy; source's only cost statement is the algo/non-algo spread table (IA Table A.20) |
| 23 | expected_gross_edge_benchmark (grading reference, not a rule) | seller's gross overnight take ≈ +0.48%/day of option value (ETF trio, pooled, hedged form); net-of-algo-cost SPY reference +0.60%/day | SOURCE-VERBATIM (reference) | IA Table A.2 Panel B (−0.48% overnight, t=−16.3); IA Table A.20 ("Profits after Costs for Algos" 0.60% post-Pilot) - expect our unhedged 1-DTE realization to differ; deviations are information, not calibration targets |

## 9. DATA REQUIREMENTS

- **Tradier chains:** DTE band 0–4 calendar days, snapshot at ~3:45–4:00 p.m. ET daily for entry
  (need Δ per strike to hit row 4; both call and put sides), plus a 9:30–9:35 a.m. snapshot next
  morning for the exit marks. 1-DTE availability drives the calendar: SPY/QQQ have daily
  expirations, IWM Mon/Wed/Fri, single names Fridays only (→ Thursday-night entries only).
- **Earnings calendar (date + bmo/amc):** REQUIRED - row 17 skip rule needs exact bmo/amc
  attribution for the six single names.
- **FOMC/CPI dates:** required only as tags (row 18); CPI/NFP eve nights tagged, FOMC afternoons
  irrelevant (outside window).
- **VIX regime:** NOT a trade input (row 10). Record VIX close at entry as a grading covariate.
  IV rank likewise covariate-only; our IV archive is cold → VIX-percentile fallback acceptable
  since nothing gates on it.
- **Ex-div calendar:** SPY/QQQ/IWM quarterly + single names (row 19).
- **Daily history:** underlying closes for gap attribution and delta verification.
- **1-min bars:** NOT required - entry and exit are single chain snapshots; optionally the 9:30
  bar for exit-mark sanity checks.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** SPY ~21 nights + QQQ ~21 + IWM ~13 (M/W/F expiries) + 6 single
  names × ~4.3 Thursday nights ≈ **80–81 strangles/month** at full universe (~55/month if the
  family launches ETF-trio-only). One of the fastest-grading families on the platform: N≥25 in a
  lane arrives in ~1–2 weeks for the ETF lanes; the single-name lane needs ~1 month.
- **Mark cadence:** exactly two marks per trade - entry close snapshot and exit open snapshot. NO
  overnight marks exist (market closed); NO intraday ladder participation. The platform exit
  engine must be **BYPASSED** for this family per the §4 override: exit is unconditional at the
  open, including (especially) on gap nights.
- **Multi-leg shape:** 2 legs, both short, same expiry, different strikes (call wing + put wing).
  P&L per trade = (entry credit − exit debit) × 100, both at midpoint conventions (rows 8/12).
- **Per-family capital-at-risk basis:** Reg-T short-strangle proxy (row 21). Do NOT use
  width-credit (no wings exist) or debit-paid (it's a credit trade). Note the published returns
  are % of OPTION VALUE - converting our CaR-based returns to the paper's units requires
  dividing P&L by entry option value, worth logging both.
- **1-lot account-blind distortions:** (a) the published headline is delta-hedged and ours is
  not - night-to-night variance will be far higher than the paper's t-stats imply; grade against
  the IA's UNHEDGED benchmarks (−0.93% raw / −0.85% straddle) not the −1% hedged headline;
  (b) mid-quote fills at 9:30 are optimistic - the published edge dies at non-algo costs (IA
  Table A.20), so grading must carry a cost-sensitivity column (mid, mid±25% spread, touch);
  (c) 1-DTE is an extrapolation (row 6) - the family's e-process should treat "edge exists at
  1 DTE" as the hypothesis under test, and a failure here refutes our extrapolation, NOT the
  published 4–15-DTE result; (d) strike granularity: on a $560 SPY a $1 grid gives fine 25Δ
  resolution, but high-priced single names (NVDA post-split-era $5 grids) can miss the 0.15–0.30
  tolerance band on low-IV nights → skips are expected and logged, not bugs.

## 11. VERIFICATION

- **Verdict: CORRECTED** (adversarial fresh-context verification, 2026-07-19).
- **What was checked:** The Internet Appendix PDF was independently re-downloaded from
  https://www.dmurav.com/MuravyevNi_WhyDoOptionReturnsChangeSign_IA.pdf (41 pages, confirmed) and
  text-extracted; EVERY SOURCE-VERBATIM / SOURCE-RANGE constant in §§3, 4, 8 and every
  [verified-primary] number in §6 was located in the extracted text: the §A.1/§A.2/§A.3/§A.4/§A.7
  quotes, Table A.2 Panel A (per-year equity overnight −0.30…−0.50, all t ≤ −3.5) and Panel B
  (pooled ETF −0.48 t −16.3, intraday +0.14 t 3.1), Table A.3 (−0.102 t −13.5), Table A.4 (−2.62
  t −15.6, +0.73), Table A.7 (straddle 0.18/−0.85 t 2.5/−17.7; raw 0.22/−0.93 t 2.3/−12.1; OTM
  straddle −1.00), Table A.8 (−2.26 vs −1.82 excl-weekends; OTM −3.84 t −18.7; "only delta hedge
  once intraday"), Table A.9 (Close-at-4pm −1.08 t −16.1; Open-at-10am −1.17; bid −1.08 / ask
  −0.96), Table A.10 note ("overnight period is from 4:15 pm to 9:30 am"), Table A.11 (VIX Low
  −0.86 / High −1.14, H−L t 1.2), Table A.12 (2298 obs; "none of the variables significantly
  predicts"), Table A.15 (Jan 2004–Dec 2013), Table A.20 (−0.64 / 1.24 / 0.05 / 0.60 / −0.01),
  Table A.1 Panel B (overnight excess kurtosis 61.836), Figure A.1 (five-times-daily baseline
  hedge), vol-ratio 3.5→2, 6% SPX spread / SPY less-than-half. ALL MATCHED VERBATIM. The
  published-abstract numbers (−0.7% / −1% / +0.3%) and the JFE citation (136(1), 219–238, 2020)
  were confirmed via the Semantic Scholar Graph API and EconPapers. The CXO page was re-read: the
  1.0% gross, Sharpe-doubling, every-3-month-interval, −2.6% short-maturity, −1.7% OTM, −0.4%
  equity and Jan-2004–Apr-2013 sample statements are all present. Absence claims (no profit
  target / stop / roll / gate) were grep-verified against the full extracted IA text.
- **Corrections made (all minor, none load-bearing):** (1) §4 had flipped the day/night order of
  the "17.5 and 6.5 hours" quote - source says NIGHT is 17.5 h; fixed. (2) The WP-abstract phrase
  "selling option volatility only overnight and holding no position during the day" had been
  tagged [verified-secondary] partly via CXO, but CXO does NOT contain that phrase and SSRN
  returned 403 to this verifier too - retagged unverified-verbatim (substance corroborated by
  CXO's "executing the strategy only overnight") in §3, §4, §8 row 14. (3) Several CXO quotes in
  §§4, 6, 7 were paraphrased renderings inside quotation marks - replaced with CXO's exact
  wording ("increases average gross daily return to 1.0%", "more than doubling gross Sharpe
  ratio", "generating positive gross returns in every 3-month interval, including the financial
  crisis", full −2.6%/−1.7% sentences).
- **Residual doubts:** the SSRN working-paper abstract remains unread by anyone (403 on both
  passes) - every claim sourced to it now rests on CXO's independent summary; the 1-DTE and
  25Δ-strangle forms remain OUR extrapolations exactly as the brief already states (correctly
  tagged ADAPTED throughout - verified no adapted value is presented as published); nothing
  post-April-2013 is evidenced by any source read. Verified by fresh-context adversarial pass,
  2026-07-19.

**SECOND independent adversarial pass (fresh context, 2026-07-19) - verdict: CONFIRMED.**
- This pass found the §11 above already in the file and did NOT trust it: every check was redone
  from scratch. The IA PDF was re-downloaded from dmurav.com (41 pages confirmed, 792.8 KB) and
  text-extracted with PyMuPDF; every SOURCE-VERBATIM / SOURCE-RANGE constant in §§3, 4, 8 and
  every [verified-primary] number in §6 was located by literal string search in the extracted
  text. ALL FOUND, including: all §A.1/A.2/A.3/A.4/A.7 prose quotes; Table A.2 Panel A per-year
  equity overnight −0.30…−0.50 (all t ≤ −3.5) and Panel B pooled ETF −0.48 (t −16.3) / +0.14
  (t 3.1); Table A.3 −0.102 (t −13.5); Table A.4 4–15d −2.62 (t −15.6) / +0.73; Table A.7 Panel A
  straddle 0.18/−0.85 (t 2.5/−17.7) with OTM-bucket −1.00 and Panel B raw 0.22/−0.93
  (t 2.3/−12.1); Table A.8 −2.26/−1.82 and OTM −3.84 (t −18.7); Table A.9 Close-at-4pm −1.08
  (t −16.1), Open-at-10am −1.17, Bid −1.08 / Ask −0.96; Table A.10 note "An overnight period is
  from 4:15 pm to 9:30 am."; Table A.11 VIX Low −0.86 / High −1.14 with overnight H−L t = 1.2;
  Table A.12 "2298 daily return observations" + "none of the variables significantly predicts";
  Table A.20 exact row −0.64% / 1.24% / 0.05% / 0.60% and pre-Pilot −0.01%; Table A.1 Panel B
  overnight excess kurtosis 61.836; "night and day periods are 17.5 and 6.5 hours, respectively"
  (night IS 17.5 h - the §4 order is correct as written); vol-ratio "from about 3.5 in 2004 to
  about two in 2013"; effective SPX spread "about 6% in our sample" and ETF spreads "less than
  half the size of SPX's"; Figure A.1 baseline hedging "five times" daily. The published abstract
  was re-verified verbatim via BOTH the Semantic Scholar Graph API and EconPapers - EconPapers
  carries the brief's exact wording ("When we decompose these option returns into intraday and
  overnight components…"), and the citation (JFE 136(1), 219–238, 2020, DOI
  10.1016/j.jfineco.2018.12.006) is confirmed. The CXO page was re-fetched: all six quoted
  statements are present verbatim. Absence claims were re-grepped against the full IA text:
  zero hits for stop-loss / profit target / profit-taking / roll rules / VIX gating - and zero
  hits for "strangle", "25 delta", "1DTE"/"0DTE", confirming the honesty box: those forms are
  genuinely NOT in the source and are correctly tagged ADAPTED everywhere they appear.
- **Corrections made by this pass: NONE** - no invented constants, no misquotes, no mis-tagged
  numbers found in the current text.
- **Residual doubts (unchanged):** SSRN WP abstract still unread (403 reported by the prior pass;
  not re-attempted here - the 1.0%-gross / Sharpe-doubling / every-3-month-interval claims rest
  solely on CXO's independent summary, correctly tagged [verified-secondary]); the paywalled JFE
  body remains unread by anyone (abstract + IA only); the 1-DTE and 25Δ strangle forms are
  extrapolations whose live edge is an open hypothesis; nothing after April 2013 is evidenced.
