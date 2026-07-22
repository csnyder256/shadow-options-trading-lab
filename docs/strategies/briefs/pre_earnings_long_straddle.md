# Strategy Brief: pre_earnings_long_straddle

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `pre_earnings_long_straddle`
- **Provenance class:** academic (peer-reviewed, JFQA)
- **PRIMARY citation:** Gao, Chao; Xing, Yuhang; Zhang, Xiaoyan. *"Anticipating Uncertainty: Straddles around Earnings Announcements."* Journal of Financial and Quantitative Analysis, Vol. 53, Issue 6 (December 2018), pp. 2587–2617. Cambridge University Press.
  - Published-version landing/PDF (paywalled): https://www.cambridge.org/core/services/aop-cambridge-core/content/view/7B34877AD5E06304BA3C55FBA3219FDD/S0022109018000285a.pdf/anticipating-uncertainty-straddles-around-earnings-announcements.pdf
  - SSRN abstract id 2204549: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2204549
  - **Full text actually READ for this brief:** the November 2017 working-paper version (63 pp., same title/authors; its abstract and headline 3.34% number match the JFQA published abstract verbatim), hosted at Tsinghua PBCSF: https://www.pbcsf.tsinghua.edu.cn/__local/B/7B/EF/9C90E5DE82928B64858EFBA685C_E7B3C45C_4183B.pdf?e=.pdf - all quotes below are from this text. Minor differences vs. the final JFQA typeset version are possible.
- **Secondary sources (independent):**
  1. Bocconi Students Investment Club, *"Straddling outside and into earnings: Part II"* - independent out-of-sample replication (2011–2021) of the Gao/Xing/Zhang methodology: https://bsic.it/straddling-outside-and-into-earnings-part-ii-2/
  2. CXO Advisory, *"Option Straddles Around Earnings Announcements"* - independent review; NOTE: CXO reviewed an EARLIER DRAFT (sample 1996–2010, 0.95–1.05 moneyness band), so its parameter values differ from the published version and must not be mixed in: https://www.cxoadvisory.com/volatility-effects/option-straddles-around-earnings-announcements/
  3. Bibliographic confirmation (RePEc): https://ideas.repec.org/a/cup/jfinqa/v53y2018i06p2587-2617_00.html
- **Publication dates:** SSRN first posted 2013 (earlier drafts, sample through 2010); working paper November 2017 (sample 1996–2013); JFQA December 2018.

**PROVENANCE-HINT CORRECTION (important):** The orchestrator hint described this strategy as "buy T-5..T-7, exit before the print." **The primary source never tests a T−5..T−7 entry.** Published entry days are T−3 and T−1 only: "the starting dates of the straddles are chosen among -3 and -1, and the ending dates are -1, 0 or 1" (Section III.C). This brief implements the published form: **buy at T−3 close, exit at T−1 close** (window [−3,−1] - the paper's "pre-announcement effect," its most robust result, and the only published window that is "strictly prior to the announcement"). A T−5..T−7 entry has UNKNOWN published performance and must not be attributed to this source.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

- **Source universe:** ALL optionable U.S. single stocks passing liquidity filters, 1996–2013 - "For each quarter, the number of sample firms ranges between 165 and 1162," average 669 firms/quarter; median market cap $2.297B. This is an earnings-event strategy on individual equities; there is no index version (indices have no earnings announcements).
- **Our mapping:** single-name mega-cap tier only - AAPL / NVDA / MSFT / TSLA / AMD / META. **SPY/QQQ/IWM are EXCLUDED from this strategy** (no earnings prints; the trigger is undefined for them).
- **Why the mapping partially preserves - and partially ATTENUATES - the edge claim (documented loudly):** The paper's central cross-sectional finding is that the effect is *strongest in small, noisy, illiquid names and weakest in large liquid ones*: "positive straddle returns are more pronounced for smaller firms" (abstract); "For options with the lowest and highest bid-ask spreads, the straddle returns are 1.14% and 4.93%, respectively"; "For options with the lowest and highest volumes, the straddle return is 5.82% and 0.90%" (Table 4 Panel C discussion). Our mega-caps sit in the lowest-spread / highest-volume quartiles, so the relevant published gross expectation is roughly **~0.9–1.4% per event, not the 3.34% headline**. The dollar-open-interest-weighted results (which emphasize large liquid names) still show a significant pre-announcement effect - "[−3,−1] has a holding period return of 1.37%, with a significant t-statistic of 3.81" - which is why the mapping is defensible at all: the pre-print IV run-up effect survives in liquid names, just smaller. The paper's delta-neutral construction uses *fractional* call/put weights; our options-only 1-lot platform trades the simple 1×1 straddle instead - the paper itself validates this: "the simple straddle returns are between 0.80% and 2.25%, and they all have t-statistics above 6.0" (Section III.C). No stock legs and no delta-hedging are needed anywhere in the published design ("we adopt a buy and hold strategy … we do not rebalance the share numbers over the event window"), so the platform's no-hedging constraint costs nothing beyond the delta-neutral→simple substitution (tagged ADAPTED in Section 8).

## 3. EXACT ENTRY RULES

All constants below are from Section II ("we apply the following filters to the option data") and Section III.C of the primary source.

- **Trigger:** a scheduled quarterly earnings announcement for a universe name. "We define day 0 as the event day, during which earnings is announced. The trading day before the announcement is day -1." Earnings dates in the source are actual IBES announcement dates: "We obtain the earnings announcement dates from IBES." The source deliberately ignores announcement hour: "we choose to only use the announcement date and make no adjustments for announcement hour."
- **Entry day:** trading day **T−3** relative to the announcement date. "For instance, for the strategy over [-3,0], we buy the straddle on day -3…" and "The first three strategies are [-3,-1], [-3,0] and [-3,1], all of which involve buying an at-the-money straddle on day -3 before the uncertainty peaks."
- **Entry time of day / fill convention:** end-of-day, at the closing bid-ask midpoint. "to avoid the bid-ask bounce from daily closing prices, we use the closing bid-ask average value to compute option returns."
- **Strike-selection algorithm (verbatim filter list, Section II):**
  - "(1) the option prices are at least $0.125"
  - "(2) the underlying stock prices are at least $5"
  - "(3) options have positive open interests"
  - "(4) we require the bid and ask price to satisfy basic arbitrage bounds" (footnote 4: "bid>0, bid<offer; for put options we require strike >= bid and offer >= max(0, strike price-stock price); for call options we require stock price >=bid and offer >= max(0, stock price-strike price)")
  - "(5) we only include options with 10 to 60 days to maturity"
  - "(6) at the time of the straddle formation, we include only options with an absolute delta between 0.375 and 0.625 (as in Bollen and Whaley (2004))"
  - "(7) we define moneyness of the option, 'money', as strike price over the previous day's stock price, and to be considered at-the-money, we require options to have moneyness between 0.9 and 1.1" (NOTE: one later passage inverts this to "stock price divided by strike price" - an internal inconsistency in the text; filter (7) is the operative definition)
  - "(8) to form straddles, we only include paired calls and puts with matching time-to-maturity and matching strike price"
  - "(9) … we require options to have price information at the beginning and the end of the holding period"
  - Filter (10) (Section III.D, stricter-liquidity time-series sample - the one that produces the 3.34% headline): "we only include matching call and put options with daily non-missing bid and ask price quotes, daily positive open interests, and daily positive trading volumes for every day during the holding period."
- **When multiple qualifying strike/expiry pairs exist:** the source AVERAGES across all qualifying pairs per firm ("we consider three weighting schemes across straddles for the same firm: equal weight, volume weight and dollar open interest weight"). A 1-lot shadow cannot average; we take the single pair with moneyness closest to 1.00 (ties → higher combined volume). Tagged ADAPTED.
- **DTE selection:** 10–60 calendar days to maturity at formation (filter (5)); sample average was ~38 days ("days to maturity are on average about 38 days," Table 1 Panel B discussion). The expiration must postdate the announcement by construction (an option 10–60 days out on T−3 always does).
- **Published regime/IV gate:** NONE. The source applies no IV-rank, VIX, or regime filter anywhere. Do not add one.

## 4. EXACT EXIT RULES

These override all platform exit doctrine for this strategy.

- **Time exit, unconditional:** sell the straddle at the **closing bid-ask midpoint on trading day T−1** - the [−3,−1] window. "the starting dates of the straddles are chosen among -3 and -1, and the ending dates are -1, 0 or 1"; "[s]trategies ending on day -1 or earlier … [are] strictly prior to the announcement"; "The strategy of [-3,-1] mainly captures the run up of uncertainty." This is the only published window guaranteed to exit before the print for both BMO and AMC announcers, matching the strategy id's mandate.
- **Published alternative windows (documented, NOT implemented):** [−3,0] (sell at day-0 close; 2.60% pooled EW, 3.34% time-series EW - but for BMO announcers day-0 close is AFTER the print), [−3,1], [−1,0], [−1,1]. The paper's own day-by-day decomposition shows the post-print day is worthless-to-negative: "The [0,1] return is -0.33%, and it is insignificant" (EW) and "the daily return over [0,1] is -1.37% with a t-statistic of -3.07" (dollar-open-interest weights) - reinforcing exit-before-print.
- **Profit target:** NONE published. Pure time exit.
- **Stop loss / loss management:** NONE published. Pure time exit.
- **Roll rules:** NONE published.
- **Rebalancing during hold:** NONE - "the share numbers of calls and puts are set at the formation period, and we do not rebalance the share numbers over the event window."
- **Hold-to-expiry doctrine:** explicitly NOT this strategy; maximum published hold is 4 trading days ("The longest holding period is 4 trading days for strategy [-3,1]"); ours is 2.
- **Failsafe (ADAPTED, ours):** if the announcement date moves earlier such that the print occurs before our scheduled T−1 exit, exit at the first available mark and flag the event as calendar-error; the source assumed dates were known ("we assume that earnings announcements are pre-scheduled events and the timing of the events are public information").

## 5. SIZING CONVENTION IN SOURCE

The source computes percentage returns per straddle (position value at midpoints), then averages cross-sectionally under equal / volume / dollar-open-interest weighting - "we first use equal weight/volume weight/dollar open interest weight for different pairs of straddle for one firm at the same time. Next, we average straddle returns over time and stocks." There is no capital, margin, or portfolio-percentage sizing anywhere; it is a per-unit return study. Delta-neutral weights are fractional (w_call = −Δput/(Δcall−Δput), equations (1)–(2)). Our shadow runs **1 published unit = one 1×1 simple straddle** (long 1 call + long 1 put, same strike/expiry), account-blind, consistent with the source's per-unit framing.

## 6. DOCUMENTED PERFORMANCE

Sample: "Our sample period is January 1996 to December 2013," OptionMetrics options data, IBES earnings dates. All returns are GROSS, at closing bid-ask midpoints - the authors say so and disclaim tradability: "The main focus of this paper is to document investors' anticipation of uncertainty around earnings announcements rather than to search for a profitable trading strategy. As a result, we only use end of the day bid and ask prices." (Conclusion.)

Pooled sample, filters (1)–(9), equal-weighted, delta-neutral (Table 2 Panel B):
- [−3,−1]: **+1.90%** per event, [−3,0]: **+2.60%**, [−3,1]: **+1.98%** - "All returns have significant t-statistics, ranging from 8.55 to 16.35." [verified-primary]
- [−1,0]: **+1.88%** (t=16.36); [−1,1]: **+2.43%** (t=13.39). [verified-primary]

Time-series sample, filters (1)–(10), EW across firms/EW within firm (Table 3 Panel A): "the holding period returns for our 5 straddle strategies range between 2.10% and 3.34%, all with highly significant t-statistics." The 3.34% abstract headline is this sample's [−3,0]. [verified-primary]

Dollar-open-interest weighted (≈ large-liquid-name proxy, closest to OUR universe): [−3,−1] **+1.37%** (t=3.81); [−3,0] **+1.10%**; [−1,0] **+0.54%**; "[f]inally, for strategies [-3,1] and [-1,1] … the holding returns are not significantly different from zero." [verified-primary]

Day-by-day (Table 3 Panel B, EW/EW): [−3,−2] +0.70%, [−2,−1] +1.62% (both significant); [−1,0] +0.63% "marginally significant"; [0,1] −0.33% insignificant. DOI-weighted: [−2,−1] +1.11% (t=4.19); [0,1] −1.37% (t=−3.07). [verified-primary]

Consistency over time (quarterly time series, DOI weights, Figure 2): [−3,−1] "positive and large 74% of the time"; [−3,0] "positive 55% of the time." These are QUARTERLY-AVERAGE positive rates, NOT per-trade win rates. Per-trade win rate: UNKNOWN (not published). [verified-primary]

Simple (1×1, non-delta-neutral) straddles: "the simple straddle returns are between 0.80% and 2.25%, and they all have t-statistics above 6.0." [verified-primary]

Out-of-sample replication (BSIC, 2011–2021, [T−3,T+1] window per Gao/Xing/Zhang filters): gross "on average 1.17%", and **with transaction costs −9.07%**. [verified-secondary] - the single most important number for expectations-setting on this strategy.

CXO Advisory (reviewing the earlier 1996–2010 draft): "market makers increase bid-ask spreads around earnings announcements, thereby undermining net profitability." [verified-secondary]

CAGR / PF / max drawdown: UNKNOWN - never published in any form (event-return study, not a portfolio backtest).

## 7. KNOWN FAILURE MODES

- **Transaction costs are the strategy's primary killer.** Primary source is gross-at-midpoint by design (quote in §6); the BSIC replication's net figure for 2011–2021 is **−9.07%** vs +1.17% gross - crossing earnings-week spreads twice on two legs can consume several percent. Our shadow's three-fill ledgers (mid/worst/model) will measure exactly this gap; expect WORST-fill grades to be brutal.
- **Post-publication attenuation:** gross edge fell from 3.34% (1996–2013) to 1.17% (2011–2021, BSIC). Classic post-publication decay for a 2013-circulated anomaly.
- **Effect concentrated where we don't trade:** biggest returns sit in small/illiquid/noisy names (5.82% lowest-volume quartile vs 0.90% highest-volume quartile). Our mega-cap universe is the weakest published segment; expected gross per event ~1%, easily inside the spread.
- **Market-downturn sensitivity:** "straddle returns are relatively low around 2001 and 2008, which coincide with market downturns" - the pre-print IV run-up is partly already in prices when ambient vol is elevated.
- **Theta offset risk:** "option prices might not increase prior to an earnings announcement as the effect of an increase in uncertainty might be offset by a shortened time-to-maturity" (citing Dubinsky-Johannes 2006). Structurally, this is a long-premium position paying ~2 days of theta against an anticipated IV ramp.
- **Calendar-error / date-drift risk:** if the actual print lands earlier than the calendar date used at entry, the "exit before print" becomes hold-through-print - a different (and post-2013, on average negative) trade. The source used realized IBES dates ex post, which a live implementation cannot; only ~28–29% of announcements fell exactly on naive prior-year-projected dates in their subsample checks (Givoly-Palmon 28.45%, Cohen et al. 29.29%) - modern vendor calendars are far better, but bmo/amc and same-week reschedules must be verified at T−1.
- **Hold-through-print tail (if exit fails):** day [0,1] return is −0.33% to −1.37% (DOI t=−3.07) - the announcement day itself is not the edge; missing the exit converts a vol-run-up trade into a negative-EV vol-crush lottery.
- **No early-assignment risk:** both legs are LONG; there are no short legs, no ex-div assignment exposure.
- **Not applicable but noted for family completeness:** Volmageddon/short-vol episodes are not failure modes here (long-vol structure); a market-wide vol spike during the hold helps this position.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | entry_day | T−3 (3rd trading day before announcement), at close | SOURCE-VERBATIM | "buying an at-the-money straddle on day -3 before the uncertainty peaks" (§III.C) |
| 2 | entry_fill_basis | closing bid-ask midpoint | SOURCE-VERBATIM | "we use the closing bid-ask average value to compute option returns" (§II) |
| 3 | exit_day | T−1 (last trading day before announcement), at close | SOURCE-VERBATIM | windows "[-3,-1], [-3,0], [-3,1], [-1,0] and [-1,1]" (§III.C); [−3,−1] chosen - "strictly prior to the announcement" (§III.C) |
| 4 | exit_fill_basis | closing bid-ask midpoint | SOURCE-VERBATIM | same as row 2; "sell the straddle on…" convention (§III.C) |
| 5 | holding_period | 2 trading days | SOURCE-VERBATIM | implied by [−3,−1]; cf. "[t]he longest holding period is 4 trading days for strategy [-3,1]" (§III.C) |
| 6 | dte_min | 10 calendar days at formation | SOURCE-VERBATIM | "(5) we only include options with 10 to 60 days to maturity" (§II) |
| 7 | dte_max | 60 calendar days at formation | SOURCE-VERBATIM | same filter (5) (§II) |
| 8 | atm_moneyness_def | strike / previous day's stock close | SOURCE-VERBATIM | "(7) we define moneyness of the option, 'money', as strike price over the previous day's stock price" (§II) |
| 9 | atm_moneyness_band | 0.9 to 1.1 | SOURCE-VERBATIM | "we require options to have moneyness between 0.9 and 1.1" (§II filter (7)) |
| 10 | abs_delta_band | 0.375 to 0.625 (both legs, at formation) | SOURCE-VERBATIM | "(6) … absolute delta between 0.375 and 0.625 (as in Bollen and Whaley (2004))" (§II) |
| 11 | min_option_price | $0.125 | SOURCE-VERBATIM | "(1) the option prices are at least $0.125" (§II) |
| 12 | min_stock_price | $5 | SOURCE-VERBATIM | "(2) the underlying stock prices are at least $5" (§II) |
| 13 | open_interest_filter | OI > 0 both legs; daily OI > 0 and volume > 0 every hold day (strict sample) | SOURCE-VERBATIM | "(3) options have positive open interests" (§II); filter (10): "daily positive open interests, and daily positive trading volumes for every day during the holding period" (§III.D) |
| 14 | quote_sanity_filter | bid>0, bid<ask, arbitrage bounds | SOURCE-VERBATIM | footnote 4: "bid>0, bid<offer; for put options we require strike >= bid and offer >= max(0, strike price-stock price)…" (§II) |
| 15 | leg_pairing | same strike, same expiration, 1 call + 1 put | SOURCE-VERBATIM | "(8) … paired calls and puts with matching time-to-maturity and matching strike price" (§II) |
| 16 | leg_weights | 1×1 simple straddle (NOT delta-neutral fractional weights) | ADAPTED | source primary spec is delta-neutral w_call=−Δput/(Δcall−Δput) (eq. (2)) - untradable in integer 1-lots; source's own robustness: "the simple straddle returns are between 0.80% and 2.25%, and they all have t-statistics above 6.0" (§III.C) |
| 17 | pair_selection | single pair, moneyness closest to 1.00; tie → higher combined volume | ADAPTED | source averages ALL qualifying pairs per firm ("equal weight, volume weight and dollar open interest weight," §III) - impossible at 1 lot; nearest-ATM matches sample mean moneyness 1.011 (Table 1 Panel B) |
| 18 | rebalancing | none during hold | SOURCE-VERBATIM | "we do not rebalance the share numbers over the event window" (§III) |
| 19 | profit_target | none | SOURCE-VERBATIM | no target published anywhere; exits are purely calendar-day (§III.C) |
| 20 | stop_loss | none | SOURCE-VERBATIM | no stop published anywhere; exits are purely calendar-day (§III.C) |
| 21 | iv_or_regime_gate | none | SOURCE-VERBATIM | no IV/VIX/regime filter appears in §II–III; entry is unconditional on vol level |
| 22 | day0_definition | announcement DATE, no hour adjustment (source); we add bmo/amc verification at T−1 | SOURCE-VERBATIM + ADAPTED | "We define day 0 as the event day"; "we choose to only use the announcement date and make no adjustments for announcement hour" (§III.B); our bmo/amc check guards the exit-before-print mandate |
| 23 | universe | AAPL/NVDA/MSFT/TSLA/AMD/META (single names only; no ETFs) | ADAPTED | source: all optionable stocks, "165 and 1162" firms/quarter (§II); our tier = source's weakest quartile - see §2 |
| 24 | entry_hint_T5_T7 | NOT IMPLEMENTED - UNKNOWN performance | UNKNOWN | no [−7,x] or [−5,x] window exists in the source; hint corrected in §1 |
| 25 | max_spread_pct_gate | platform standard options liquidity gate (spread % of mid, OI floors) | PLATFORM-POLICY | ours; source's filters (1)/(3)/(10) are the published analogs |
| 26 | capital_at_risk_basis | debit paid (long-premium; max loss = debit) | PLATFORM-POLICY | per-family CaR convention; consistent with source's per-unit % returns (§5) |

## 9. DATA REQUIREMENTS

- **Tradier chains:** DTE band 10–60 at T−3, calls+puts with bid/ask, OI, volume, and delta (greeks needed for the 0.375–0.625 filter; if greeks missing, moneyness band 0.9–1.1 is the published fallback filter - both are published, delta filter is binding "at the time of the straddle formation").
- **Earnings calendar:** REQUIRED, date + bmo/amc. Date drives T−3/T−1 scheduling; bmo/amc + a T−1 re-verification guards the exit-before-print mandate (source ignored hour; we cannot, see §4/§7). Re-check the date daily during the hold for reschedules.
- **FOMC/CPI dates:** not required (no macro gate published).
- **VIX regime:** not required (no gate published). Do not add one.
- **IV rank:** not required (no IV gate published; archive-cold/VIX-percentile fallback irrelevant here).
- **Daily history:** required - previous day's stock close for the moneyness computation (filter (7)).
- **1-min bars:** not required. All published marks are EOD closing quotes; EOD mark cadence reproduces the source exactly. Intraday marks optional for platform telemetry only.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** 6 names × 4 earnings/year = ~24 events/year ≈ **2.0/month average**, but heavily clustered in earnings seasons (late Jan–Feb, Apr–May, Jul–Aug, Oct–Nov); expect 4–8 in peak months and 0 in dead months. N≥25 per-lane verdict therefore needs ~12–13 months of runtime - this is a SLOW-grading lane; flag for patience in the e-process wealth schedule.
- **Mark cadence:** EOD closing bid/ask midpoint is the published basis for both entry and exit; grade the source-faithful ledger on EOD mid. The platform's three-fill ledgers (mid / worst / model) are exactly the right instrument here because the published edge (~1–2% gross) is smaller than typical earnings-week spreads - the mid-vs-worst gap IS the research question (see §6 BSIC −9.07% net).
- **Multi-leg shape:** 2-leg debit: long 1 ATM call + long 1 ATM put, same strike, same expiry (10–60 DTE). No short legs, no stock leg, no hedging, no rebalancing. Fits the options-only constraint natively.
- **Per-family capital-at-risk basis:** debit paid (max loss = premium outlay; defined-risk long premium).
- **1-lot account-blind distortions:** (a) we trade the simple 1×1 straddle, not the delta-neutral fractional-weight straddle - small residual delta at entry (|net delta| ≤ 0.25 by the delta filter), which the source shows is immaterial ("quantitatively similar"); (b) we take one nearest-ATM pair instead of averaging all qualifying pairs - adds idiosyncratic strike noise vs. the published averaged returns; (c) published returns are cross-sectional averages over hundreds of firms/quarter, ours is 6 names - per-event variance will be far higher than published t-stats imply, another reason grading needs the full N≥25.
- **Doctrine override reminder:** exits here are calendar-only (T−1 close). No profit-target, no stop, no ladder - the platform exit engine must be fully suppressed for this family per §4.
- **What would falsify the lane:** persistent negative WORST-fill (and even MID-fill) P&L on [−3,−1] across ≥25 events would be consistent with the BSIC 2011–2021 net result and should retire the lane; the published prior for our liquid tier is only ~+1.4% gross (DOI-weighted [−3,−1]).

## 11. VERIFICATION

- **Verdict: CONFIRMED** - date 2026-07-19, adversarial fresh-context verification.
- **Method:** downloaded the exact cited primary full text (Tsinghua PBCSF working paper PDF, 63 pages - page count matches the brief's claim), extracted full text, and grepped for every SOURCE-VERBATIM / SOURCE-RANGE constant in §3, §4, §8 and every [verified-primary] number in §6. Fetched both secondary sources live.
- **Primary-source results:** ALL located verbatim. Filters (1)–(9) incl. $0.125 / $5 / OI>0 / footnote-4 arbitrage bounds / 10–60 DTE / |Δ| 0.375–0.625 / moneyness strike-over-prev-close 0.9–1.1 / matched pairs (paper §II, PDF p.11); filter (10) strict-liquidity text (§III.D); windows quote "starting dates … -3 and -1, ending dates -1, 0 or 1"; "strictly prior to the announcement"; no-rebalance quote; "longest holding period is 4 trading days"; announcement-hour quote; IBES dates quote; pre-scheduled quote; eq. (2) w=−Δput/(Δcall−Δput). Performance: pooled EW 1.90/2.60/1.98/1.88/2.43% with t 8.55–16.35/16.36/13.39 (Table 2 Panel B); time-series 2.10–3.34%; DOI [−3,−1] 1.37% t=3.81, [−3,0] 1.10%, [−1,0] 0.54%, "[-3,1] and [-1,1] … not significantly different from zero"; day-by-day 0.70/1.62/0.63/−0.33% and DOI 1.11% t=4.19, −1.37% t=−3.07; simple straddle "between 0.80% and 2.25% … t-statistics above 6.0"; 74%/55% Figure 2 positive-quarter rates; spread quartiles 1.14%/4.93%; volume quartiles 5.82%/0.90%; 165–1162 firms, avg 669 (fn. 6), median mktcap $2.297B, mean moneyness 1.011, ~38 DTE avg; 28.45%/29.29% expected-date hit rates; 2001/2008 downturn quote; Dubinsky-Johannes theta-offset passage; conclusion not-a-trading-strategy disclaimer. The brief's note about the internal moneyness-definition inconsistency (filter (7) strike/price vs. table captions "stock price divided by strike price") is itself accurate - both passages exist.
- **Secondary sources:** BSIC replication confirmed live - sample Dec 2011–Dec 2021, window [T−3,T+1], gross "on average 1.17%", net "−9.07%" with transaction costs, all verbatim. CXO confirmed live - reviewed the 1996–2010 draft with 0.95–1.05 moneyness (matching the brief's mix-in warning), and the market-makers/spreads quote is verbatim (source ends "…net profitability of straddles").
- **ADAPTED / PLATFORM-POLICY tags:** all five ADAPTED rows (16, 17, 22-partial, 23, plus the §4 failsafe) have genuine platform-constraint rationales and none is presented as published; rows 25–26 are clearly labeled platform policy. Row 24 correctly refuses to attribute the orchestrator's T−5..T−7 hint to the source - no [−5,x] or [−7,x] window exists anywhere in the paper (checked).
- **Corrections made:** none required - no edits beyond this section.
- **Residual doubts:** (a) verification used the cited Nov-2017 working paper, exactly as the brief discloses; the JFQA 2018 typeset version (paywalled) could differ in minor numbers, but the abstract 3.34% headline matches the published abstract; (b) the brief's "Cohen et al. 29.29%" vs. the paper's in-text "Cohen (2007)" is a citation-style nit, not a constant error; (c) the CXO quote in §6 drops the trailing words "of straddles" without an ellipsis - meaning unchanged.

### 11b. INDEPENDENT RE-VERIFICATION (2026-07-19, second fresh-context adversarial pass)

- **Process note:** this brief ALREADY carried the Section 11 above claiming CONFIRMED when this verifier opened it. That pre-existing self-verification was treated as untrusted data, not as evidence. Everything below was re-derived from scratch: the cited Tsinghua PBCSF PDF was re-downloaded (63 pages, Nov 2017, title/authors match), full text extracted locally, and every tagged constant grepped independently; both secondary URLs and the RePEc record were fetched live.
- **Verdict: CONFIRMED (independently).**
- **Primary source:** every SOURCE-VERBATIM constant in §3/§4/§8 and every [verified-primary] number in §6 was located in the extracted text, including: filters (1)–(10) with $0.125 / $5 / OI>0 / footnote-4 "bid>0, bid<offer" bounds / 10–60 DTE / |Δ| 0.375–0.625 (Bollen-Whaley) / moneyness = strike over previous day's stock price, band 0.9–1.1 / matched strike+maturity pairs; windows "starting dates of the straddles are chosen among -3 and -1 … ending dates are -1, 0 or 1"; "strictly prior to the announcement"; "share numbers of calls and puts are set at the formation period, and we do not rebalance the share numbers over the event window"; "longest holding period is 4 trading days"; "The trading day before the announcement is day -1"; announcement-hour and IBES and pre-scheduled quotes; Table 2 pooled EW row "[-3,-1] 1.90% 16.35 … [-3,0] 2.60% … [-3,1] 1.98% 8.55 … [-1,0] 1.88% 16.36 … [-1,1] 2.43% 13.39" plus text "8.55 to 16.35"; time-series "2.10% and 3.34%"; DOI "holding period return of 1.37%, with a significant t-statistic of 3.81", 1.10%, 0.54%, "not significantly different from zero"; day-by-day 0.70/1.62/0.63/−0.33 and DOI row "[0,1] −0.33% −1.04 … −1.37% −3.07", 1.11% t=4.19; "the simple straddle returns are between 0.80% and 2.25% … t-statistics above 6.0"; "Results using simple straddles are quantitatively similar"; Figure-2 "positive … and large 74% of the time" / "positive 55% of the time"; 1.14%/4.93% spread and 5.82%/0.90% volume quartiles; "165 and 1162" firms, avg 669, median mktcap "$2.297 billion", moneyness mean 1.011, "about 38 days"; 28.45%/29.29% expected-date rates; "relatively low around 2001 and 2008, which coincide with market downturns"; Dubinsky-Johannes theta-offset passage; conclusion "rather than to search for a profitable trading strategy … only use end of the day bid and ask prices". The moneyness-definition internal inconsistency noted in §3 is real (both passages exist). No [−5,x] or [−7,x] window exists anywhere in the paper - the §1 provenance-hint correction stands.
- **Secondaries:** BSIC live-confirmed (Dec 2011–Dec 2021, [T−3,T+1], gross "on average 1.17%", net "−9.07%", cites Gao/Xing/Zhang 3.34%). CXO live-confirmed (reviews the January 2013 draft, sample 1996–2010, moneyness 0.95–1.05 - the §1 do-not-mix warning is correct; market-makers/spreads quote verbatim, ending "…net profitability of straddles"). RePEc live-confirmed: JFQA Vol. 53 Issue 6, 2018, pp. 2587–2617, Gao/Xing/Zhang.
- **Tags:** ADAPTED rows (16, 17, 22-partial, 23, §4 failsafe) all carry genuine platform-constraint rationales and none is passed off as published; rows 25–26 clearly PLATFORM-POLICY; row 24 correctly refuses the T−5..T−7 attribution. Zero INVENTED constants found.
- **Corrections made:** none required.
- **Residual doubts:** same three as §11 above (working-paper vs JFQA typeset; Cohen citation style; CXO ellipsis nit) - all cosmetic. Additionally: the paper's text says t-range "8.55 to 16.35" while its own table prints 16.36 for [−1,0]; this is the paper's internal rounding inconsistency, and the brief quotes both faithfully.
