# Strategy Brief: tsmom_long_options

Time-series momentum (TSMOM) expressed via 60-90 DTE long calls/puts, monthly rebalance.

Researched 2026-07-19. Primary source READ in full (23-page JFE PDF, text-extracted); all
quotes below are verbatim from the extracted text (ligatures/equation glyphs normalized).
**The published strategy is a FUTURES strategy. It contains ZERO options content. Every
option-leg constant in this brief is an ADAPTATION and is tagged as such.**

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `tsmom_long_options`
- **Provenance class:** academic (options overlay ADAPTED - no published options form)
- **PRIMARY citation:** Tobias J. Moskowitz, Yao Hua Ooi, Lasse Heje Pedersen,
  "Time Series Momentum," *Journal of Financial Economics* 104 (2012), pp. 228-250.
  - URL (author copy, read for this brief): https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf
  - Also: SSRN abstract id 2089463 (https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463);
    journal listing https://ideas.repec.org/a/eee/jfinec/v104y2012i2p228-250.html
  - Key sections: 2.4 (ex-ante volatility estimator), 3.2 (trading-strategy definition),
    4 / 4.1 (the TSMOM factor: k=12, h=1, 40%/sigma sizing, Eq. 5), 4.3 (extreme markets).
- **INDEPENDENT secondary sources (both read):**
  1. Quantpedia, "Time Series Momentum Effect," https://quantpedia.com/strategies/time-series-momentum-effect
     (independent description + independent backtest numbers).
  2. Brian Hurst, Yao Hua Ooi, Lasse Heje Pedersen, "A Century of Evidence on Trend-Following
     Investing," *Journal of Portfolio Management*, Fall 2017 (read via
     https://fairmodel.econ.yale.edu/ec439/hurst.pdf). Overlapping authors with the primary but an
     independent, out-of-sample dataset (1880-2016, 67 markets); used here mainly for failure modes.
- **Publication dates:** JFE paper © 2011 Elsevier, journal issue 2012 (Vol. 104, Issue 2).
  Century paper Fall 2017. Quantpedia page undated (living document, fetched 2026-07-19).

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**What the source trades** - liquid FUTURES/forwards, long AND short, across four asset classes:

> "Our data consist of futures prices for 24 commodities, 12 cross-currency pairs (from nine
> underlying currencies), nine developed equity indexes, and 13 developed government bond
> futures, from January 1965 through December 2009." (Sec. 2.1, p. 230)

Signals are on futures **excess returns**; for equity indexes this is equivalent to cash index
minus T-bills:

> "For the equity indexes, our return series are almost perfectly correlated with the
> corresponding returns of the underlying cash indexes in excess of the Treasury bill rate."
> (Sec. 2.1, p. 231)

**Our mapping:** SPY / QQQ / IWM + liquid mega-caps AAPL, NVDA, MSFT, TSLA, AMD, META.
One 60-90 DTE long ATM call (if 12-mo sign positive) or long ATM put (if negative) per symbol,
re-formed monthly. Three adaptations, in decreasing order of support:

1. **Index ETFs for index futures - well supported.** The S&P 500 is one of the paper's nine
   equity indexes, and the authors state: "we confirm that the time series momentum results are
   almost identical if we use the cash indexes for the stock index futures." (Sec. 3.2 run-out, p. 236 - the paper has no Sec. 3.3).
   SPY/QQQ/IWM are cash-index trackers, so the SIGNAL transfers directly.
2. **Long options for linear futures exposure - LOUD ADAPTATION.** The paper's payoff is linear
   (futures, long or short). We replace it with a convex long-premium position: capped downside
   (debit), added theta bleed and vega exposure that the source does not have. Conceptual (not
   parametric) support exists in the trend-following literature: the Century paper's return
   "smile" - "trend following has done particularly well in extreme up or down years for the
   stock market" (citing Fung and Hsieh [1997]) - i.e., TSMOM's payoff is already option-like,
   so a long-option expression preserves the shape of the claimed edge while paying premium for
   it. NO published source specifies the 60-90 DTE / ATM parameterization; those constants are
   ours (Sec. 8).
3. **Single-stock application (AAPL/NVDA/MSFT/TSLA/AMD/META) - UNSUPPORTED EXTRAPOLATION.**
   The paper deliberately contains NO individual stocks (single-stock momentum in the literature
   is cross-sectional, and 12-month single-stock momentum conventionally SKIPS the last month to
   dodge short-term reversal - the TSMOM rule does not). Single names add idiosyncratic
   earnings-gap risk absent from index TSMOM. We carry them as a separate, explicitly
   experimental tier; grade the ETF tier and the single-name tier separately.

**Why the edge claim can survive the mapping:** the documented effect is per-instrument sign
predictability ("All 58 futures contracts exhibit positive time series momentum returns"),
verified to transfer to cash equity indexes, and strongest in "extreme markets" where a long
option is the most efficient expression. What does NOT survive: the headline diversified Sharpe
(built on 58 instruments across four asset classes - our 9 correlated equity underlyings cannot
replicate it), and the 40%/sigma vol-balancing (dropped by our 1-lot convention, Sec. 5).

## 3. EXACT ENTRY RULES

**Trigger (signal) - SOURCE-VERBATIM.** At each month-end t, compute the trailing 12-month
excess return of the underlying; go long if positive, short if negative:

> "For each instrument s and month t, we consider whether the excess return over the past k
> months is positive or negative and go long the contract if positive and short if negative,
> holding the position for h months." (Sec. 3.2, p. 233)

> "we focus on the properties of the 12-month time series momentum strategy with a 1-month
> holding period (e.g., k=12 and h=1), which we refer to simply as TSMOM." (Sec. 4, p. 236)

The factor definition (Eq. 5, p. 236): `r_TSMOM(s, t→t+1) = sign(r_s(t−12,t)) × (40%/σ_s(t)) × r_s(t→t+1)`.
There is no threshold other than the SIGN - no minimum trend strength, no filter:

> "Another way to look at time series predictability is to simply focus only on the sign of the
> past excess return. This even simpler way of looking at time series momentum underlies the
> trading strategies we consider in the next section." (Sec. 3.1, p. 233)

- **Excess return basis (ADAPTED computation, same in spirit):** source uses compounded daily
  futures excess returns. We use 12-month total return (dividends included) minus the compounded
  13-week T-bill return. Support: the paper's own equivalence quote ("cash indexes in excess of
  the Treasury bill rate," Sec. 2.1, p. 231).
- **Direction → option mapping (ADAPTED, no source):** sign > 0 → long call; sign < 0 → long
  put. The source goes long/short futures; options are our substitution.
- **Strike selection: NO PUBLISHED VALUE.** ADAPTED: nearest-to-ATM strike, target delta
  0.50 ± 0.05 (calls) / −0.50 ± 0.05 (puts). Rationale: ATM is the closest single-leg proxy for
  a linear position per unit premium; any other delta is equally unsupported by the source.
- **DTE selection: NO PUBLISHED VALUE.** ADAPTED: buy 60-90 calendar DTE at entry, so a 1-month
  hold (per h=1) exits with ≥30 DTE remaining, clear of the gamma/theta acceleration zone.
- **Entry timing (time of day): UNKNOWN.** The source is monthly-close academic data and says
  nothing about intraday execution. PLATFORM-POLICY: compute the signal on the last trading
  day's close; execute during the first regular session of the new month, 15:30-15:55 ET.
- **Regime / IV gate: NONE PUBLISHED.** The paper applies the rule unconditionally to every
  instrument every month. We add no IV gate (an IV gate here would be an invented rule).

## 4. EXACT EXIT RULES

These OVERRIDE all platform exit doctrine for this strategy.

**The only published exit is the monthly re-formation.** The position is held h = 1 month, then
re-formed from the fresh signal:

> "...and go long the contract if positive and short if negative, holding the position for
> h months." (Sec. 3.2, p. 233) - with h = 1 per the TSMOM definition: "the 12-month time
> series momentum strategy with a 1-month holding period (e.g., k=12 and h=1)." (Sec. 4, p. 236)

> "We set the position size to be inversely proportional to the instrument's ex ante
> volatility, 1/σ_s(t−1), each month." (Sec. 3.2, p. 233) - i.e., positions are refreshed
> **each month**; nothing is touched intra-month.

- **Profit target: NONE PUBLISHED.** No profit-taking rule of any kind appears in the source.
  Do not impose one.
- **Stop loss / loss management: NONE PUBLISHED.** No stop, no drawdown cut, no intra-month
  exit appears in the source. Do not impose one. (Max loss is structurally capped at the debit
  paid - that cap is a property of our ADAPTED long-option expression, not a published rule.)
- **Time exit / roll (ADAPTED mechanization of h=1):** at each monthly rebalance date, CLOSE
  the open option entirely and open a fresh 60-90 DTE position per the new signal - whether or
  not the sign flipped. This implements "1-month holding period" exactly and keeps DTE inside
  the entry band. Hold-to-expiry never occurs (exit at ~30-60 DTE remaining by construction).
- **Sign flip:** handled by the same monthly re-formation - close the call, open the put (or
  vice versa). No intra-month flip: the signal is only read monthly in the source.

## 5. SIZING CONVENTION IN SOURCE

Recorded for context only; **our shadow always runs 1 published unit = 1 contract**.

> "We size each position (long or short) so that it has an ex ante annualized volatility of
> 40%. That is, the position size is chosen to be 40%/σ(t−1), where σ(t−1) is the estimate of
> the ex ante volatility of the contract as described above. The choice of 40% is
> inconsequential, but it makes it easier to intuitively compare our portfolios to others in
> the literature." (Sec. 4.1, p. 236)

The vol estimator (Sec. 2.4, p. 233, Eq. 1): exponentially weighted moving average of lagged
squared daily returns, annualized by 261, with "the center of mass of the weights
... = δ/(1−δ) = 60 days," always lagged: "we use the volatility estimates at time t−1 applied
to time-t returns throughout the analysis."

Leverage context (footnote 8, p. 236): "this portfolio construction implies a use of margin
capital of about 5-20%, which is well within what is feasible to implement in a real-world
portfolio."

**Distortion note:** dropping 40%/σ scaling (our 1-lot convention) removes the vol-balancing
that made per-instrument returns comparable and stabilized the published factor. Expect our
per-symbol P&L dispersion to be dominated by the high-premium names (NVDA/TSLA). See Sec. 10.

## 6. DOCUMENTED PERFORMANCE

All published numbers are for the DIVERSIFIED 58-instrument FUTURES factor (or its variants),
gross of transaction costs unless noted. NONE of them are a forecast for our equity-only
long-options expression - the premium bleed of always-long-options is not in any published
number below.

- Diversified TSMOM Sharpe: "yielding a Sharpe ratio greater than one on an annual basis, or
  roughly 2.5 times the Sharpe ratio for the equity market portfolio, with little correlation
  to passive benchmarks" (Sec. 1, p. 230). **[verified-primary]**
- Factor-model alpha: "TSMOM delivers a large and significant alpha or intercept with respect
  to these factors of about 1.58% per month or 4.75% per quarter" (vs. MSCI World + SMB/HML/UMD,
  Sec. 4.2, p. 236); still "1.09% per month with a t-stat of 5.40" vs. the Asness-Moskowitz-
  Pedersen everywhere factors (p. 237). **[verified-primary]**
- Breadth: "All 58 futures contracts exhibit positive time series momentum returns and 52 are
  statistically different from zero at the 5% significance level." (Sec. 4.1, p. 236)
  **[verified-primary]**
- Factor volatility: "an annualized volatility of 12% per year over the sample period
  1985-2009" (Sec. 4.1, p. 236). **[verified-primary]**
- Out-of-sample (pre-sample): 1966-1985 factor has "a statistically significant return and an
  annualized Sharpe ratio of 1.1" (Sec. 4.3, pp. 237-238). **[verified-primary]**
- Extreme markets: "performs best during extreme markets" (abstract); largest profits Oct-Dec
  2008 (Sec. 4.3, p. 238). **[verified-primary]**
- Quantpedia independent backtest of the rule (1965-2009 per their page): annualized monthly
  return 1.26% (geometric), volatility 15.74%, Sharpe 1.31, max drawdown −33.87%.
  **[verified-secondary]** (Quantpedia's own methodology, not the paper's table.)
- Century extension (1880-2016, 67 markets, equal-weight 1/3/12-mo signals): positive average
  returns in each market, "average Sharpe ratio of approximately 0.4" per market (gross);
  positive in every decade; strategy drawdowns "losing up to 25%, over extended time periods."
  **[verified-secondary]**
- **Win rate: UNKNOWN (not published). Profit factor: UNKNOWN (not published).** Neither paper
  reports per-trade statistics; do not invent them.
- Post-2009 attenuation: widely discussed in practitioner literature (AQR's forward-looking
  net Sharpe assumptions ~0.4); I did not verify the specific attenuation numbers in a primary
  text. **[unverified]** - treat 2010s-era expected performance as materially below the
  1985-2009 headline numbers.

## 7. KNOWN FAILURE MODES

Published/named episodes (for the futures strategy):

1. **Crisis-end V-reversal - Mar-May 2009.** "TSMOM suffers sharp losses when the crisis ends
   in March, April, and May of 2009. The ending of a crisis constitutes a sharp trend reversal
   that generates losses on a trend following strategy such as TSMOM." (p. 238)
   **[verified-primary]** Same shape: Nov-2020 vaccine rotation, Jan-2023 reversal [unverified
   as TSMOM episodes, same mechanism].
2. **Pre-profit whipsaw - Q3 2008.** "time series momentum suffers losses in the third quarter
   of 2008" before the Q4 gains (p. 238). **[verified-primary]**
3. **Fast crashes the monthly signal cannot catch - 1987-type.** "the strategy may not perform
   well in bear markets that occur very rapidly, such as the 1987 stock market crash, because
   the strategy may not be able to take positions quickly enough" (Century, JPM Fall 2017).
   **[verified-secondary]** Feb-2020: the 12-month sign was still LONG equities into the COVID
   crash - in our expression that month's long calls expire worthless-ish, loss capped at debit
   (the cap is our adaptation's one mercy; the futures form lost linearly).
4. **Trendless chop / multi-market reversals.** TSMOM's own worst stretches "tend to be
   associated with periods of sharp reversals across multiple markets or prolonged periods in
   which many markets exhibit a lack of clear trends," with drawdowns "up to 25%" (Century).
   **[verified-secondary]** The 2010s were the canonical trendless stretch [unverified
   specifics]. **For our long-options form, chop is DOUBLY bad: no trend P&L plus ~9 debits of
   theta burned every month.** This is the dominant expected failure mode of the adaptation.
5. **Post-spike IV-crush entries (adaptation-specific, e.g. Aug-2024 vol spike).** Sign flips
   arrive right after large moves, exactly when IV is richest - the strategy systematically
   buys puts at post-crash peak IV and can lose on vega even when direction is right. Not in
   the source (futures have no vega). **[structural, ours]**
6. **Single-name earnings gaps (adaptation-specific).** Every 60-90 DTE mega-cap position
   spans at least one earnings report; a gap against the 12-month sign is an instant large
   debit loss, and there is no published gate to dodge it (we add none). **[structural, ours]**
7. **Early assignment: NOT APPLICABLE** - long-only single-leg options, no short legs, no
   assignment risk; ex-div only matters as an exercise-decision on deep-ITM long calls near
   ex-date (platform should exercise/sell rather than bleed carry; cosmetic, not a risk).

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | signal_lookback_months | 12 | SOURCE-VERBATIM | "the 12-month time series momentum strategy ... (e.g., k=12 and h=1)" (Sec. 4, p. 236) |
| 2 | signal_rule | sign of trailing 12-mo excess return; >0 long, <0 short | SOURCE-VERBATIM | "whether the excess return over the past k months is positive or negative and go long the contract if positive and short if negative" (Sec. 3.2, p. 233) |
| 3 | signal_strength_threshold | NONE (sign only) | SOURCE-VERBATIM | "simply focus only on the sign of the past excess return" (Sec. 3.1, p. 233) |
| 4 | excess_return_reference | 13-week T-bill total return over same 12 mo | ADAPTED | source uses futures excess returns; equivalence: "cash indexes in excess of the Treasury bill rate" (Sec. 2.1, p. 231). We substitute ETF/stock total return minus T-bill |
| 5 | holding_period_months | 1 | SOURCE-VERBATIM | "1-month holding period (e.g., k=12 and h=1)" (Sec. 4, p. 236) |
| 6 | rebalance_frequency | monthly | SOURCE-VERBATIM | "position size ... 1/σ(t−1), each month" (Sec. 3.2, p. 233); factor computed "for each instrument and each available month" (Sec. 4.1) |
| 7 | lookback/holding variants | k AND h each scanned over {1,3,6,9,12,24,36,48} months in Table 2; effect strongest ≤12 | SOURCE-RANGE (default k=12, h=1) | "The existence and significance of time series momentum is robust across horizons and asset classes, particularly when the look-back and holding periods are 12 months or less." (Sec. 3.2 run-out, p. 236 - no Sec. 3.3 exists) |
| 8 | signal_observation_date | last trading day of month, official close | PLATFORM-POLICY | source convention (monthly data) not stated at trade-date resolution; UNKNOWN in source |
| 9 | entry_time_of_day | UNKNOWN in source → 15:30-15:55 ET, first session of new month | PLATFORM-POLICY | no intraday timing anywhere in source |
| 10 | direction_to_option_map | sign>0 → long call; sign<0 → long put | ADAPTED | source trades futures long/short; NO options in source. Our convex substitution (Sec. 2) |
| 11 | dte_entry_min | 60 calendar days | ADAPTED | NO published value (source has no options). Chosen so h=1 exit lands ≥30 DTE, outside gamma/theta acceleration |
| 12 | dte_entry_max | 90 calendar days | ADAPTED | NO published value. Upper bound keeps premium/vega moderate and chains liquid |
| 13 | strike_selection | nearest ATM; delta 0.50 ± 0.05 | ADAPTED | NO published value. ATM = closest single-leg proxy to linear futures exposure per unit premium |
| 14 | exit_rule | close entire position at next monthly rebalance; re-enter fresh 60-90 DTE per new sign | ADAPTED (mechanizes h=1) | "holding the position for h months" with h=1 (Secs. 3.2, 4); close-and-reopen is our DTE-band-preserving implementation |
| 15 | profit_target | NONE | SOURCE-VERBATIM (absence) | no profit-taking rule appears anywhere in the source; only exit is monthly re-formation |
| 16 | stop_loss | NONE | SOURCE-VERBATIM (absence) | no stop/intra-month exit appears anywhere in the source; max loss = debit (structural, ours) |
| 17 | iv_or_regime_gate | NONE | SOURCE-VERBATIM (absence) | rule applied unconditionally to all instruments, all months; no vol/regime filter in Secs. 3-4 |
| 18 | per_instrument_vol_target | 40% annualized - RECORDED, NOT USED (1-lot shadow) | SOURCE-VERBATIM | "position size is chosen to be 40%/σ(t−1)"; "The choice of 40% is inconsequential" (Sec. 4.1, p. 236) |
| 19 | vol_estimator | EWMA of daily squared returns, center-of-mass 60 days, ×261 annualized, lagged t−1 - RECORDED, NOT USED | SOURCE-VERBATIM | Eq. 1 and "center of mass of the weights ... = 60 days" (Sec. 2.4, p. 233) |
| 20 | position_size | 1 contract per symbol per month | PLATFORM-POLICY | shadow convention (account-blind, 1 published unit); replaces #18 |
| 21 | universe | SPY, QQQ, IWM + AAPL, NVDA, MSFT, TSLA, AMD, META (single names = experimental tier) | ADAPTED | source: 58 futures (Sec. 2.1, p. 230); cash-index equivalence quoted in Sec. 2; single names UNSUPPORTED by source (Sec. 2 of this brief) |
| 22 | option_liquidity_gates | OI ≥ 100, bid-ask ≤ 10% of mid (platform standard) | PLATFORM-POLICY | ours; source silent on options entirely |

## 9. DATA REQUIREMENTS

- **Daily history:** ≥ 13 months of dividend-adjusted daily closes per symbol (12-mo total
  return at month-end) + 13-week T-bill yield series for the excess-return sign. This is the
  only input the SIGNAL needs.
- **Tradier chains:** 60-90 DTE band, fetched ONLY on the monthly rebalance day (9 symbols).
  Need deltas (or compute from mid-IV) for the ATM pick, plus OI/spread for the gates.
- **Earnings calendar (date + bmo/amc):** required for LOGGING/diagnostics on the six single
  names (every hold spans earnings) - NOT a gate; no gate is published and we add none.
- **FOMC/CPI dates:** not required - no macro gate in source. Optional context tagging only.
- **VIX regime / IV rank:** not required as a gate (none published). Log entry IV per contract
  for the IV-crush failure-mode diagnostics (Sec. 7 #5); our IV archive is cold, so use the
  VIX-percentile fallback purely as a diagnostic covariate, never as a filter.
- **1-min bars:** not needed. Monthly cadence; daily close marks suffice (Sec. 10).

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month: ~9** (one position per symbol, always-in-market - the sign is never
  flat - closed and re-opened monthly; 9 round trips = 18 fills/month). Two lanes fill
  unevenly: in a bull tape nearly all 9 are calls; the put lane may take many months to reach
  N≥25. Per-lane N≥25 on the combined book ≈ 3 months; per-direction could be 6-12+ months.
  Grade the ETF tier (3/month) separately from the experimental single-name tier (6/month).
- **Mark cadence:** daily close marks are sufficient (no intra-month rules exist to trigger).
  Standard three-ledger fills at the monthly entry/exit only.
- **Multi-leg shape:** single-leg long option (1 leg, debit). Simplest family on the platform.
- **Capital-at-risk basis: debit paid.** Max loss = premium; no margin, no width.
- **1-lot / account-blind distortions (LOUD):** (a) the published 40%/σ sizing is dropped - 
  our aggregate P&L will be premium-weighted, i.e., dominated by NVDA/TSLA-priced contracts,
  unlike the vol-balanced published factor; (b) the published edge is a DIVERSIFIED
  multi-asset portfolio effect - our 9 correlated equity names test only the per-instrument
  sign-predictability claim, not the headline Sharpe; (c) the long-option expression converts
  the published linear exposure into sign-exposure + convexity − theta: in a trendless month
  the published strategy is ~flat while ours bleeds ~9 debits of theta. Expect the shadow's
  base rate to look WORSE than Sec. 6 in chop and BETTER in large moves; grade against that
  shape, not against the futures Sharpe.
- **Signal hygiene:** compute the 12-mo window as month-end to month-end (no lookahead: signal
  from last close, execution next session). Use dividend-adjusted total returns; an
  unadjusted-price sign is a silent bug on IWM/high-div months.

---

*Provenance discipline note: the platform was previously damaged by invented "documented
rules." Sections 3, 4, 8 above quote the source for every published constant; every constant
without a quote is tagged ADAPTED or PLATFORM-POLICY and is OURS, carrying no published
authority. UNKNOWNs: entry time-of-day and trade-date convention (not stated in source);
win rate and profit factor (not published).*

## 11. VERIFICATION

**Verdict: CORRECTED** - adversarial verification pass, 2026-07-19, fresh context.

**Method.** Both cited PDFs were downloaded and text-extracted in full (primary: NYU Stern
author copy of Moskowitz-Ooi-Pedersen JFE 2012, 23 pages; secondary: Yale-hosted Hurst-Ooi-
Pedersen, confirmed to be the JPM Vol. 44 No. 1 Fall 2017 issue, 1880-2016, 67 markets). The
Quantpedia page was fetched live. Every quote tagged SOURCE-VERBATIM or SOURCE-RANGE in
Secs. 3, 4, 8 and every [verified-primary]/[verified-secondary] number in Sec. 6 and Sec. 7
was string-searched against the extracted text (ligature/whitespace/hyphenation-normalized).

**Confirmed verbatim (no invention found):** the k=12/h=1 definition; the sign-only entry
rule; "simply focus only on the sign of the past excess return"; the 40%/σ(t−1) sizing and
"The choice of 40% is inconsequential"; the EWMA vol estimator (261 annualization, 60-day
center of mass, t−1 lag); the 58-instrument universe sentence and Jan 1965-Dec 2009 dates;
the cash-index equivalence quotes; footnote 8's 5-20% margin; Sharpe > 1 / 2.5x equity;
alpha 1.58%/mo and 4.75%/qtr (Table 3 Panel A vs MSCI World+SMB/HML/UMD confirmed);
1.09%/mo t=5.40; all-58-positive / 52-significant-at-5%; 12% factor vol 1985-2009; 1966-1985
OOS Sharpe 1.1; "performs best during extreme markets"; Q3-2008 losses; Mar-May 2009
crisis-end losses; Eq. (5) is the factor equation as stated. Century paper: 1880-2016, 67
markets, equal-weight 1/3/12-mo signals, ~0.4 avg per-market gross Sharpe, the 1987
"quickly enough" sentence, "losing up to 25%, over extended time periods", the smile /
"extreme up or down years" + Fung-Hsieh [1997] cite, positive returns in each decade - all
verbatim-confirmed. Quantpedia: 1,26% geometric monthly, 15.74% vol, Sharpe 1.31, max DD
−33.87%, 1965-2009 - all on the live page. All ADAPTED/PLATFORM-POLICY rows correctly claim
no published authority (the source indeed contains zero options content; no false attribution
found). The absence claims (no profit target, no stop, no IV/regime gate in source) were
checked by reading Secs. 3-4 in full: correct.

**Corrections applied (all minor, none load-bearing):**
1. Parameter row #7 had a fabricated-sounding paraphrase presented as a quote ("largest
   t-statistics ...") and a wrong scan range (h "1-12"). Table 2 actually scans BOTH k and h
   over {1,3,6,9,12,24,36,48}; the quote was replaced with the paper's actual sentence.
2. The paper has no Sec. 3.3 (only 3.1 and 3.2); two "Sec. 3.3" citations re-pointed to the
   Sec. 3.2 run-out on p. 236.
3. Journal-page fixes (extraction maps PDF page n → journal p. n+227): "almost perfectly
   correlated" quote is p. 231 not 230 (3 spots); intro Sharpe quote p. 230 not 229; Mar-May
   2009 and Q3-2008 quotes p. 238 not 237; OOS Sharpe-1.1 spans pp. 237-238.

**Residual doubts:** (a) journal page numbers are computed from the author-copy PDF's printed
footers (footer 236 on PDF p. 9 anchors the offset) - trust section numbers over page numbers
if they ever disagree; (b) Quantpedia's "20.7% p.a. estimated alpha (Fama-French)" appears on
their page but is not in the brief - omission, not error; (c) the post-2009 attenuation bullet
remains [unverified] as the brief itself states; (d) the strategy's edge for OUR expression
(equity-only, long-options, 1-lot) is, as the brief loudly states, NOT documented anywhere - 
the sources support only the futures/cash-index sign-predictability claim. That framing is
honest and was left untouched.

---

**INDEPENDENT ADVERSARIAL RE-VERIFICATION - second pass, fresh context, 2026-07-19.
Verdict: CONFIRMED (no edits required).**

The pre-existing Section 11 above was treated as untrusted file content and NOT relied on.
Both PDFs were independently re-downloaded from the cited URLs (NYU Stern author copy, 23
pages, and the Yale-hosted JPM Fall 2017 Century paper) and text-extracted with pypdf; the
Quantpedia page was independently re-fetched live.

Checked and confirmed against the sources directly:
- Every SOURCE-VERBATIM / SOURCE-RANGE row in Sec. 8 and every quote in Secs. 3-5 located
  verbatim in the extracted primary text (extraction artifacts only: "k1⁄412 and h1⁄41" is
  the PDF glyph form of "k=12 and h=1"; "t/C01" is "t−1"; "kmonths"/"hmonths"/"Mayof" are
  space-merge artifacts). Eq. (5) appears exactly as stated: rTSMOM = sign(r t−12,t) ×
  (40%/σ) × r t,t+1, labeled (5). Table 2 scans BOTH lookback and holding over
  {1,3,6,9,12,24,36,48} - the Sec. 8 row #7 range is correct. Footnote 8 is genuinely
  footnote 8 and contains the 5-20% margin sentence. The paper has Secs. 3.1/3.2 and no 3.3,
  as the brief states.
- Journal page numbers verified against printed running-head page numbers on each PDF page
  (offset PDF p.n → journal p.n+227 exact): sign-only quote p.233; entry rule p.233; universe
  and Sharpe>1 p.230; cash-equivalence p.231; k=12/h=1, 1.58%, 12% vol, robust-≤12,
  cash-identical all p.236; 1.09%/t=5.40 p.237; OOS-Sharpe-1.1 sentence starts p.237 ends
  p.238; Q3-2008 and Mar-May-2009 p.238. Every citation in the brief matches.
- All six [verified-primary] Sec. 6 numbers found verbatim; both [verified-secondary] blocks
  found (Century: 1880-2016, 67 markets, equal-weight 1/3/12-mo, ~0.4 avg per-market Sharpe,
  positive returns in each decade, "losing up to 25%, over extended time periods", the 1987
  "quickly enough" sentence, the smile + Fung-Hsieh cite, the sharp-reversals/no-clear-trends
  drawdown sentence). Quantpedia live page: 1,26% geometric monthly, 15.74% vol, Sharpe 1.31,
  max DD −33.87%, 1965-2009 - all present.
- Absence claims (no profit target, no stop, no IV/regime gate, no per-trade win rate or
  profit factor published) - consistent with the full extracted text; no such rules exist in
  either source.
- ADAPTED / PLATFORM-POLICY rows: none claims published authority; each carries a real
  rationale; the 60-90 DTE / ATM-delta / option-mapping / universe / liquidity constants are
  correctly flagged as OURS with no source.
- One immaterial observation, recorded for completeness: the primary DOES contain a single
  option-analogy sentence ("TSMOM, therefore, has payoffs similar to an option straddle on
  the market", p. 244 area, citing Fung and Hsieh 2001) - this contains no parameters and if
  anything strengthens the brief's Sec. 2 adaptation rationale; the brief's "zero options
  content" claim (meaning zero option parameters/strategy content) stands.

No invented constants found. No misattributed numbers found. The prior pass's corrections
(Sec. 3.3 → 3.2 run-out, page renumbering, Table 2 range) were independently re-derived and
are correct as applied. Residual doubts (a)-(d) above remain accurate and are inherited.
