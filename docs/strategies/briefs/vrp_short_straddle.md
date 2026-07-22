# Strategy Brief: vrp_short_straddle

Volatility-risk-premium-gated 30DTE short ATM straddle (unhedged adaptation).
Researched 2026-07-19. Every constant in sections 3, 4, 8 carries a direct quote or a
precise locator; anything not found in a published source is marked **UNKNOWN**.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `vrp_short_straddle`
- **Provenance class:** academic (with a practitioner management overlay, flagged ADAPTED wherever it binds)
- **PRIMARY citation:**
  - Gurdip Bakshi and Nikunj Kapadia, **"Delta-Hedged Gains and the Negative Market Volatility Risk Premium"**, *The Review of Financial Studies*, Summer 2003, Vol. 16, No. 2, pp. 527–566, DOI: 10.1093/rfs/hhg002.
    - URL (author-hosted full text, read in full for this brief): https://people.umass.edu/~nkapadia/docs/Bakshi_and_Kapadia_2003_RFS.pdf
    - Publisher page: https://academic.oup.com/rfs/article-abstract/16/2/527/1579962
- **Co-primary (named in provenance pointers, read in full):**
  - Joshua D. Coval and Tyler Shumway, **"Expected Option Returns"**, *The Journal of Finance*, Vol. 56, No. 3 (June 2001), pp. 983–1009.
    - URL (working-paper full text read, June 2000 draft, mirrors the published results): https://business.baylor.edu/don_cunningham/Option%20Returns.pdf
    - Publisher page: https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00352
- **INDEPENDENT secondary sources (all read for this brief):**
  1. Amit Goyal and Alessio Saretto, **"Cross-section of option returns and volatility"**, *Journal of Financial Economics* 94 (2009) 310–326 - the published academic basis for GATING straddle selling on realized-minus-implied volatility. Author-hosted full text: https://drive.google.com/file/d/1lAvSaDxJn-fbe8sBTd0bkAnpoo--pscY/view (linked from https://sites.google.com/view/agoyal145); publisher: https://www.sciencedirect.com/science/article/abs/pii/S0304405X09001251
  2. Chris Butler / projectfinance, **"Selling SPY Option Straddles | In-Depth Study"** (last updated April 5, 2022), https://www.projectfinance.com/selling-straddles/ - 25–35 DTE SPY ATM short straddle P/L-frequency study with VIX entry filters. NOTE: the live domain currently fails DNS; full text was retrieved and read via the Internet Archive (snapshot 2026-05-09, http://web.archive.org/web/20260509141124/https://www.projectfinance.com/selling-straddles/).
  3. Chris Butler / projectfinance, **"Short Straddle Adjustment Results (11-Year Study)"** (last updated April 25, 2022), https://www.projectfinance.com/straddle-management/ - SPY ATM short straddle profit-target/stop-loss study (read via Internet Archive snapshot, web.archive.org/web/2023/https://www.projectfinance.com/straddle-management/).
  4. tastylive, **"Straddle"** concepts-strategies page, https://www.tastylive.com/concepts-strategies/straddle - practitioner DTE convention (45 DTE), read live.
- **Publication dates:** 2001 (Coval-Shumway), 2003 (Bakshi-Kapadia), 2009 (Goyal-Saretto), 2022 (projectfinance studies, as last-updated).

**What each source contributes:** Bakshi-Kapadia establishes that the market volatility risk
premium is negative (selling vol on the index is compensated). Coval-Shumway establishes that
short ATM index straddles specifically earned ~3%/week. Goyal-Saretto establishes that gating
straddle selling on IV-vs-realized-vol (the VRP gate) selects the profitable shorts. The
projectfinance studies supply the only quotable practitioner management constants (profit
target / stop-loss) for unhedged SPY short straddles. **No single source publishes this exact
strategy end-to-end; the composition is ours and is flagged ADAPTED throughout.**

---

## 2. PUBLISHED UNIVERSE & OUR MAPPING

- **Bakshi-Kapadia:** S&P 500 (SPX) index options - "We test model implications using options written on the S&P 500 index" (p. 528). Sample Jan 1, 1988 – Dec 30, 1995.
- **Coval-Shumway:** SPX (weekly, Jan 1990–Oct 1995) and OEX/S&P 100 (daily, Jan 1986–Dec 1995) index options; futures options (bonds, Eurodollar, Nikkei, DM) as robustness.
- **Goyal-Saretto:** the **entire U.S. single-stock option market** - "The data contain information on the entire U.S. equity option market" (OptionMetrics Ivy DB, Jan 1996–Dec 2006; 4,344 stocks, 75,627 monthly call/put pairs).
- **projectfinance:** SPY (S&P 500 ETF) options, Jan 2007 onward.
- **tastylive:** SPY and liquid ETFs/single names (practitioner convention).

**Our mapping:** SPY / QQQ / IWM (index-ETF tier - maps to the SPX/OEX/SPY evidence) plus
liquid mega-caps AAPL / NVDA / MSFT / TSLA / AMD / META (single-name tier - maps to the
Goyal-Saretto single-stock evidence).

**Why the mapping preserves the edge claim:** the documented edge is the negative volatility
risk premium - index option IV persistently exceeds subsequently realized vol, and delta-neutral
option sellers collect the difference. SPY/QQQ/IWM options are economically the same exposure as
the SPX/OEX options in the primary sources (same underlying index risk, American-style ETF
options instead of European index options - a structural difference flagged in section 7). The
single-name tier is exactly the Goyal-Saretto universe restricted to its most liquid members;
their per-name VRP gate (sell when IV is rich vs realized) is the same gate we run.

**LOUD ADAPTATION FLAGS (options-only platform, no stock legs, no continuous hedging):**
1. **Bakshi-Kapadia's test asset is a continuously delta-hedged option portfolio** ("buy the
   option and hedge with stock", rebalanced daily). Our platform cannot hold stock legs. We do
   NOT implement their portfolio; we use the paper only as evidence that the volatility risk
   premium is negative. The tradeable expression we run is the **unhedged 1:1 short ATM
   straddle**.
2. **Coval-Shumway's straddles are "zero-beta" weighted** - call/put weights θ chosen so the
   position beta is zero, not 1:1. Our 1:1 ATM straddle is approximately delta-neutral at entry
   only, and drifts. Tagged ADAPTED in section 8.
3. **Goyal-Saretto's gate is cross-sectional** (deciles across ~4,300 stocks; also a
   sign-of-(HV−IV) two-group split). On a 9-symbol universe a decile sort is meaningless; we
   adapt to the published **sign split** applied per symbol (their "N" group = IV above HV =
   the group whose straddles lose money for buyers, i.e., the shorts' side). Tagged ADAPTED.
4. **Hold-to-expiry (academic) vs managed (practitioner):** all three academic sources hold to
   expiration (or fixed horizon) with no management. The profit-target/stop-loss overlay comes
   from the projectfinance studies and is a deliberate practitioner adaptation, quoted in
   section 4.

---

## 3. EXACT ENTRY RULES

Every constant below is quoted; the composition of the rules into one strategy is ADAPTED (see section 2).

**3.1 Trigger condition - the VRP gate (per symbol):** enter only when the symbol's ~30-day
ATM implied volatility is ABOVE its trailing 12-month realized volatility (IV − HV > 0).
- Source construction (Goyal-Saretto, p. 311): "we sort stocks based on the difference between
  HV and IV. HV is calculated using the standard deviation of daily realized stock returns over
  the most recent 12 months and IV is computed by taking the average of the implied volatilities
  of the call and put contracts which are closest to at the money (ATM) and are one month to
  maturity."
- Source sign-split (p. 313): "we sort stocks into two groups depending on the sign of the
  difference between HV and IV. We label these groups P (for positive, HV higher than IV) and
  N (for negative, HV lower than IV)." Their N-group straddles (IV rich) LOSE −9.4%/month for
  buyers (Table 3, Panel A) - that group is the published short-side selection.
- **No published absolute threshold exists** beyond the sign / decile membership: absolute
  cutoff = **UNKNOWN** (recorded in section 8). Decile-1 membership in their data is "the
  lowest (negative) difference" (p. 313) - cross-sectional, not reproducible on 9 names.
- Documented ALTERNATIVE gate for the ETF tier (projectfinance, VIX study): straddles "entered
  when the VIX was above 23 (the top 25% of VIX readings on the days of trade entries)" "had
  by far the best results." The 23 level is their sample's 75th percentile, not a magic number
 - we record it as a documented high-vol regime marker.

**3.2 Strike selection:** the at-the-money strike, nearest to spot.
- projectfinance (selling-straddles study, methodology step 2): "we 'sold' an at-the-money straddle."
- Goyal-Saretto ATM band (p. 312): "Since it is not always possible to select options with
  moneyness (defined as the ratio of strike to stock price) exactly equal to one, we keep
  options with moneyness between 0.975 and 1.025."

**3.3 DTE selection:** target ~30 days; accept 25–35 DTE.
- projectfinance: "On every trading day with a standard expiration cycle between 25-35 days to
  expiration (DTE), we 'sold' an at-the-money straddle. We chose 25-35 DTE to target an
  approximate one-month straddle."
- Coval-Shumway (p. 9 of draft): "We take options which are to expire during the following
  calendar month, and therefore are roughly between 20 and 50 days to expiration."
- Goyal-Saretto (p. 312): "we consider only options that mature in the next month."
- Practitioner dissent, recorded: tastylive says "Our target timeframe for selling straddles is
  around 45 days to expiration. Our studies show this is a great balance between shorter and
  longer timeframes." We run 30 DTE per the strategy id; 45 DTE is the documented alternative.

**3.4 Entry timing:**
- Goyal-Saretto signal/trade lag (p. 314): "we form portfolios on the first trading day
  (typically a Monday) after the expiration Friday of the month and we initiate option
  portfolio strategies on the second trading day (typically a Tuesday) after the expiration
  Friday of the month" - i.e., compute the gate on day t, trade on day t+1.
- Time of day: **UNKNOWN** - no source prescribes an intraday entry time for trading.
  (Coval-Shumway *measure* returns from "the first bid-ask quote after 9AM (Central Time
  Zone)"; Goyal-Saretto use closing quotes. Platform convention: evaluate the gate on prior
  close, enter near the open, mark from mid.)
- T−n for events: no published event timing rule in any source. Earnings blackout for single
  names is OUR policy (section 8, PLATFORM-POLICY).

**3.5 Published regime/IV gate:** the VRP gate of 3.1 IS the published regime gate
(Goyal-Saretto). Additionally Bakshi-Kapadia (abstract): "Third, the underperformance is
greater at times of higher volatility" - i.e., the premium collected by sellers is larger in
high-vol states, consistent with the projectfinance VIX>23 result. No FOMC/last-30-minute or
calendar gates are published in any of these sources.

---

## 4. EXACT EXIT RULES (OVERRIDE platform exit doctrine for this strategy)

**4.1 Published academic doctrine - hold to expiration.**
- Goyal-Saretto (p. 314): straddle returns use "as the closing price, the terminal payoff of
  the option that expires in the money"; footnote 15: "held until expiration and not
  rebalanced during the holding period (similar to the straddle portfolios)."
- Coval-Shumway hold one week (weekly rebalance): "The S&P 500 straddles are rebalanced each
  week."
- The academic form has NO profit target, NO stop, NO roll.

**4.2 Practitioner management overlay (ADAPTED; constants quoted from projectfinance
"Short Straddle Adjustment Results (11-Year Study)", SPY, ATM, 60-DTE monthly cycle - note
their management study used 60 DTE, not 30; applying these constants at 30 DTE is our
adaptation):**
- Profit target menu tested: "Management: None, 10% Profit Target, 25% Profit Target, 50%
  Profit Target." Finding: "Taking profits at 10-25% of the maximum profit potential
  significantly increased the consistency of returns relative to not managing trades at all."
  → **We adopt the 25% profit target** (25% of credit received), the top of their recommended
  10–25% band. Example semantics from the source: "if a straddle was sold for $10 ... A 25%
  profit would be reached when the straddle's price decreased to $7.50."
- Stop-loss menu tested: "Management: None (hold to expiration), -50% loss, -100% loss, -150%
  loss." Findings: "the best-performing approach was to use a -100% stop-loss, which means the
  short straddles were closed if the price doubled from the initial entry price" and "The data
  suggests that using a stop-loss of -100% is strategically better than using a slightly wider
  stop-loss of -150%." → **We adopt the −100% stop** (close when straddle mark ≥ 2× credit).
  Source semantics: "-100% Loss: Straddle price increases by 100% to $20" (on a $10 sale).
- Combined-rule form (their combined study): "25% Profit OR 100% Loss" - exactly our adopted
  pair. Source example: "if a straddle was sold for $10 and a trader used the 25% Profit OR
  50% Loss management, they'd close the straddle if the price reached $7.50 (a 25% profit) or
  $15 (a 50% loss)" (we use the 100%-loss variant per the best-performing finding above).
- **Time exit:** if neither target nor stop is hit, hold to expiration (academic doctrine,
  4.1) and exit at terminal intrinsic value. Their re-entry rule: "Next Entry Date: First
  trading day after previous trades were closed."
- **Roll rules: none.** projectfinance FAQ mentions rolling only descriptively ("typically
  adjusted by either rolling the options to a different expiration cycle or rolling the
  options to a different strike price") with no tested constants - we do NOT roll.
- **The "21 DTE" management rule** widely attributed to tastylive could NOT be verified
  against a fetchable primary page during this research (their strategy pages carry no such
  number; the retired Market Measures episode pages 404). It is recorded as [unverified]
  practitioner lore and is **NOT adopted**. An honest UNKNOWN beats an invented rule.
- **Early-close on gate reversal (IV falls back under HV): not published anywhere - not
  adopted.**

---

## 5. SIZING CONVENTION IN SOURCE

- Coval-Shumway / Bakshi-Kapadia / Goyal-Saretto: per-unit option returns (one option or one
  straddle per observation, returns as % of entry price/premium) - academic convention, no
  account sizing.
- Goyal-Saretto margin context (p. 311): "margin requirements for short positions are roughly
  equal to one and a half times the cost of written options."
- projectfinance management study: "One straddle sold for all trades." (also: "keep trade
  size small" - selling-straddles study, closing thoughts).
- tastylive: percent-of-buying-power convention on their broadcasts (no quotable page found;
  [unverified]).
- **Our shadow always runs 1 published unit = 1 short straddle (1 call + 1 put), account-blind** - which coincidentally matches the projectfinance study convention exactly.

---

## 6. DOCUMENTED PERFORMANCE

All numbers below are what the SOURCES report for THEIR forms - none of them is a backtest of
our exact adapted composite. Tags per platform rule.

**Coval-Shumway (long-straddle returns; short side earns the negative of these, before costs):**
- "zero-beta, at-the-money straddle positions produce average losses of approximately three percent per week" (abstract) [verified-primary]
- "At-the-money SPX straddles have average returns of -3.15 percent per week while all the SPX straddles we examine lose between 2.89 percent and 4.49 percent per week" (SPX, weekly, Jan 1990–Oct 1995) [verified-primary]
- "average returns on at-the-money S&P 100 straddles are -0.5 percent per day" (OEX daily zero-beta straddle series, Jan 1986–Oct 1995 per the paper's own straddle-analysis window - includes the 1987 crash; the paper's underlying OEX option-return dataset runs Jan 1986–Dec 1995) [verified-primary]
- Crash-neutral variant (long deep-OTM put added) "still generates average losses of nearly three percent per week" [verified-primary]
- Methodology caveats: midpoint pricing (no spread cost), 305-week sample without a 1987-scale crash in the SPX window, weekly Tuesday marks.

**Bakshi-Kapadia (delta-hedged long option portfolio, i.e., the hedged expression of the same premium):**
- "the strategy loses about 0.05% of the market index, and about 0.13% for at-the-money calls ... for at-the-money options, this amounts to 8% of the option value" (pp. 528–529, per ~month-scale hedge horizons) [verified-primary]
- "the delta-hedged strategy underperforms zero ... the underperformance is greater at times of higher volatility" (abstract) [verified-primary]
- Sample Jan 1988–Dec 1995, S&P 500 options, 14–60 day maturities, ±10% moneyness [verified-primary]

**Goyal-Saretto (VRP-sorted one-month ATM single-stock straddles, held to expiration, 1996–2006):**
- "a long-short decile portfolio of straddles yields a monthly average return of 22.7% and a Sharpe ratio of 0.710" [verified-primary]
- Decile 1 (IV rich - the short candidates) long-straddle mean return −12.8%/month; decile 10 +9.9%/month; sign-split N portfolio −9.4%/month, P +4.4%/month (Table 3, Panel A; signs per the paper's definitions - the printed table renders magnitudes with deciles 1/N negative) [verified-primary]
- Costs bite hard: "the long-short decile straddle portfolio returns are reduced to 3.9% per month if we consider trading options at an effective spread equal to the quoted spread" [verified-primary]
- Methodology caveats: equal/relative-value-weighted portfolios of hundreds of names, monthly formation, midpoint entry pricing, 1996–2006 sample (pre-GFC).

**projectfinance (SPY ATM short straddles - closest published test of our exact ETF-tier shape):**
- 25–35 DTE study, Jan 2007–2022, n = "823 short straddle trades": "84% of trades reached a 20% profit but only 51% reached a 20% loss"; "less than 50% of one-month short straddles in SPY have reached the 50% profit level" [verified-secondary]
- VIX>23 entries "realized the highest percentage of trades that reached each profit level and the lowest percentage of trades that reached each loss level" [verified-secondary]
- Management study (60 DTE): the per-rule win-rate / avg-P&L / worst-loss table values are rendered as images in the archived page and could not be read - **UNKNOWN**, only the qualitative rankings quoted in section 4 are verified. [verified-secondary for the qualitative findings]
- "all approaches suffered significant losses in February of 2018" [verified-secondary]

**CAGR / PF / max drawdown for our exact adapted composite (30DTE, VRP-gated, 25%PT/100%SL, 9-symbol universe): UNKNOWN - no source publishes it. The shadow ledger will establish it.**

---

## 7. KNOWN FAILURE MODES

**Named historical episodes:**
- **Feb-2018 "Volmageddon"** - direct source hit: "all approaches suffered significant losses in February of 2018, which highlights the importance of keeping risk in mind before selling straddles" (projectfinance management study). VIX doubled in a day; short straddles gapped through stops (their study: "the losses were sometimes far more than the stop-loss levels ... substantial one-day market movements can lead to a large change in the option prices by the time the market closes").
- **Mar-2020 COVID crash** - post-dates the academic samples; VIX to ~82; a 30DTE short straddle entered in late Feb 2020 would have blown far through a −100% stop on gap. The VRP gate is NO protection here - IV was already rich vs trailing RV on the way in (gate would have been open).
- **Aug-2024 vol spike (Aug 5, VIX intraday ~65)** - modern instance of the same gap risk on SPY/QQQ/IWM and high-beta names (NVDA, TSLA, AMD).
- **2008 GFC / Aug-2015 flash episode** - source: "Over a long enough period of time, there will be market crashes worse than what was experienced in 2008, 2015 and 2018" (projectfinance).
- **General source warning:** "When markets turn volatile, a trader can have years of straddle selling profit wiped out in a single trade" (projectfinance FAQ). Coval-Shumway's own caveat: the SPX sample contains no 1987-scale crash; the OEX sample that does still shows −0.5%/day for longs, but a single crash week is catastrophic for an unhedged short.

**Structural failure modes:**
- **Unbounded loss, negatively skewed P&L** - max gain = credit, loss unlimited on the call side, ~strike-sized on the put side.
- **Early assignment (American-style)** - our SPY/QQQ/IWM and single-name options are American (unlike the European SPX options in Coval-Shumway). The short ITM call is assignment-prone **through ex-dividend dates** (SPY/IWM/QQQ quarterly ex-div; AAPL/MSFT/NVDA/META pay dividends); the short ITM put is assignment-prone when deep ITM / near expiry. Assignment converts the position into a stock leg the platform cannot hold - shadow must model assignment as an immediate exit at intrinsic.
- **Gap-through-stop** - stops are monitored on marks; overnight gaps mean realized loss >> −100% stop level (quoted source evidence above).
- **Earnings gap (single-name tier)** - a 30DTE single-name straddle window nearly always contains an earnings date; the IV-vs-HV gate is systematically fooled by event-inflated IV (IV looks rich vs trailing RV precisely because a known jump is coming - the premium is not "free"). Goyal-Saretto did NOT filter earnings, but they held a diversified portfolio of hundreds of names; at 1-lot on 6 names we cannot diversify the jump. Hence the PLATFORM-POLICY earnings blackout (section 8).
- **Pin/settlement mechanics at expiry** - ATM at expiration maximizes gamma; terminal intrinsic marking per Goyal-Saretto convention.
- **Small-N concentration** - the published single-name edge is a portfolio average (equal-weighted deciles of ~53 stocks); per-name realizations are wildly dispersed. Expect long stretches where the shadow's 9-symbol sample diverges from the published mean.

---

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | `underlying_universe` | SPY, QQQ, IWM + AAPL, NVDA, MSFT, TSLA, AMD, META | PLATFORM-POLICY | Mapping of SPX/OEX/SPY (Bakshi-Kapadia p.528; Coval-Shumway p.8; projectfinance) + Goyal-Saretto "entire U.S. equity option market" (p.312) to our liquid tiers |
| 2 | `dte_target` | 30 days | SOURCE-RANGE (default 30) | projectfinance: "between 25-35 days to expiration (DTE) ... to target an approximate one-month straddle"; Coval-Shumway: "roughly between 20 and 50 days to expiration"; Goyal-Saretto: "one month to maturity" (p.311). tastylive dissents: "around 45 days to expiration" - not adopted |
| 3 | `dte_window` | 25–35 DTE acceptance band | SOURCE-VERBATIM | projectfinance: "standard expiration cycle between 25-35 days to expiration (DTE)" |
| 4 | `strike_selection` | single ATM strike nearest spot, same strike both legs | SOURCE-VERBATIM | projectfinance: "we 'sold' an at-the-money straddle"; mgmt study: "Sell the at-the-money call and put." |
| 5 | `moneyness_band` | strike/spot must be within 0.975–1.025 | SOURCE-VERBATIM | Goyal-Saretto p.312: "we keep options with moneyness between 0.975 and 1.025" |
| 6 | `legs` | short 1 call + short 1 put, same strike, same expiry, 1:1 ratio | SOURCE-VERBATIM (definition) + ADAPTED (weights) | projectfinance: "selling a call and put option at the same strike price and in the same expiration cycle"; ADAPTED vs Coval-Shumway zero-beta weights θ (their eq. for zero-beta straddle) - we run 1:1 unhedged |
| 7 | `hedging` | NONE (no stock leg, no delta rebalance, ever) | ADAPTED | Bakshi-Kapadia's evidence portfolio hedges daily with stock (p.539, "hedge ratio ... recomputed daily"); platform is options-only - we deliberately run the unhedged expression |
| 8 | `vrp_gate` | enter only if IV_atm30 − HV_12m > 0 (per symbol) | ADAPTED (from SOURCE-VERBATIM construction) | Goyal-Saretto sign split p.313: "N (for negative, HV lower than IV)" = the group whose straddles lose for buyers (−9.4%/mo, Table 3); we apply their cross-sectional sign rule per-symbol. Absolute threshold beyond sign: **UNKNOWN** (none published) |
| 9 | `hv_definition` | std dev of daily log returns, trailing 12 months (252 td), annualized | SOURCE-VERBATIM | Goyal-Saretto p.311: "HV is calculated using the standard deviation of daily realized stock returns over the most recent 12 months" |
| 10 | `iv_definition` | mean of ATM call IV and ATM put IV at ~30d maturity | SOURCE-VERBATIM | Goyal-Saretto p.311: "IV is computed by taking the average of the implied volatilities of the call and put contracts which are closest to at the money (ATM) and are one month to maturity" |
| 11 | `vix_regime_marker` | VIX > 23 = documented best-performing entry regime (ETF tier); recorded as regime tag, not a hard gate | SOURCE-VERBATIM | projectfinance: "entered when the VIX was above 23 (the top 25% of VIX readings on the days of trade entries)" - "the high VIX entries had by far the best results" |
| 12 | `entry_lag` | gate computed on day t close → trade day t+1 | SOURCE-VERBATIM | Goyal-Saretto p.314: "we form portfolios on the first trading day (typically a Monday) after the expiration Friday ... initiate option portfolio strategies on the second trading day (typically a Tuesday)" |
| 13 | `entry_time_of_day` | **UNKNOWN** (platform convention: near open, after gate check on prior close) | UNKNOWN | No source prescribes a trading entry time. (Coval-Shumway sample "the first bid-ask quote after 9AM (Central Time Zone)" for measurement only) |
| 14 | `profit_target` | close at 25% of credit received | SOURCE-RANGE (menu {10%, 25%, 50%}; adopted 25%) | projectfinance mgmt study: "Management: None, 10% Profit Target, 25% Profit Target, 50% Profit Target."; "Taking profits at 10-25% of the maximum profit potential significantly increased the consistency of returns" |
| 15 | `stop_loss` | close when straddle mark ≥ 2× credit (−100% of credit) | SOURCE-VERBATIM (menu {−50%, −100%, −150%}; adopted −100%) | projectfinance mgmt study: "the best-performing approach was to use a -100% stop-loss, which means the short straddles were closed if the price doubled from the initial entry price"; "-100% is strategically better than ... -150%" - NOTE their mgmt study ran at 60 DTE; applying at 30 DTE is ADAPTED |
| 16 | `time_exit` | hold to expiration if neither #14 nor #15 fires; exit at terminal intrinsic | SOURCE-VERBATIM | Goyal-Saretto p.314: "as the closing price, the terminal payoff of the option that expires in the money"; fn.15 "held until expiration and not rebalanced" |
| 17 | `roll_rules` | NONE | SOURCE-VERBATIM (absence) | No tested roll rule in any source; projectfinance FAQ describes rolling without constants - not adopted. 21-DTE exit lore: [unverified], not adopted |
| 18 | `reentry` | eligible again first trading day after exit (max 1 open straddle per symbol) | SOURCE-VERBATIM | projectfinance mgmt study: "Next Entry Date: First trading day after previous trades were closed." |
| 19 | `earnings_blackout` | single-name tier only: no entry if an earnings date falls inside (entry, expiry]; ETF tier exempt | PLATFORM-POLICY (deviation from Goyal-Saretto, who did not filter earnings - flagged LOUDLY: portfolio diversification justified their inclusion; 1-lot concentration justifies our exclusion) | n/a (ours) |
| 20 | `liquidity_gate` | open interest > 0 on both legs; bid > 0; quote sanity (ask ≥ bid; spread ≥ min tick) | SOURCE-VERBATIM + PLATFORM-POLICY | Goyal-Saretto p.312: "we remove all observations for which the option open interest is equal to zero, in order to eliminate options with no liquidity"; "eliminate all observations for which the ask price is lower than the bid price, the bid price is equal to zero" |
| 21 | `position_size` | 1 straddle (1 contract each leg), account-blind | PLATFORM-POLICY (coincides with source) | projectfinance mgmt study: "One straddle sold for all trades." |
| 22 | `car_basis` | capital-at-risk proxy = max(1.5× credit received, Reg-T naked-straddle proxy) - see section 10 | PLATFORM-POLICY (informed by SOURCE-VERBATIM) | Goyal-Saretto p.311: "margin requirements for short positions are roughly equal to one and a half times the cost of written options" |

**UNKNOWN constants (honest gaps, never invent):** `vrp_gate_absolute_threshold` (only sign /
cross-sectional decile published), `entry_time_of_day`, per-rule managed win-rate/avg-P&L table
values from the projectfinance management study (images, unreadable in archive).

---

## 9. DATA REQUIREMENTS

- **Tradier chains:** yes - full chains for the 9 symbols, DTE band **20–50** (to cover the
  25–35 acceptance window on both sides and track open positions to expiry). Need per-contract
  bid/ask/mid, OI, greeks/IV for both legs; ATM call+put IV for the gate (#10).
- **Earnings calendar:** yes - date + bmo/amc for AAPL/NVDA/MSFT/TSLA/AMD/META, for the
  `earnings_blackout` (#19). ETF tier does not consume it.
- **FOMC/CPI dates:** context tags only - NO published gate in any cited source (do not
  re-arm the parked last30/FOMC machinery for this strategy).
- **VIX regime:** yes - daily VIX close for the `vix_regime_marker` (#11) and regime tagging
  of results. The published "23" corresponds to their sample's top quartile; recompute the
  rolling percentile rather than hard-coding 23 as timeless.
- **IV rank:** not required by the published rules (the gate is IV-vs-HV, not IV rank). Our IV
  archive is cold anyway → where an IV-richness percentile is wanted for reporting, use the
  documented **VIX-percentile fallback** (ETF tier) and the IV−HV spread itself (single names).
- **Daily history:** yes - 252 trading days of daily closes per symbol for HV (#9), continuously.
- **1-min bars:** not required. Marking can be EOD-minimum (the projectfinance stops are
  EOD-evaluated - quoted in section 7), but intraday chain marks at the platform's normal
  cadence improve stop fidelity (#15). No published intraday rule exists.

---

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** universe = 9 symbols, at most 1 open straddle per symbol, ~monthly
  cycle. Gate pass-rate: in Goyal-Saretto's data the N-group (IV>HV) held ~252 of ~531 gated
  stocks on average (p.313) ≈ half the universe; the single-name earnings blackout will kill
  roughly the cycle straddling each name's earnings (≈1 of every 3 monthly cycles per name).
  Realistic expectation: **~4–8 entries/month, call it 6** (ETF tier ~2–3, single names ~2–5).
  At the platform's N≥25/lane grading bar, first verdicts in ~4–6 months.
- **Mark cadence:** EOD marks minimum (matches the management-study methodology); use the
  platform's standard intraday poll for the −100% stop and 25% target between closes. Terminal
  mark = intrinsic at expiration (#16).
- **Multi-leg shape:** 2 legs, same strike, same expiry: SHORT 1 ATM call + SHORT 1 ATM put.
  Net credit position; fills ledgered per platform three-fill convention.
- **Per-family capital-at-risk basis:** naked short straddle has no debit and no width - use a
  **Reg-T CaR proxy**: max over legs of [20% × underlying − OTM amount + leg premium] + other
  leg premium (standard naked-equity-option initial requirement shape), floored at the
  published academic proxy of **1.5× total credit** (Goyal-Saretto, #22). Denominator for %
  returns = that CaR, NOT the credit (a −100% stop = −1× credit, which is a much smaller % of
  CaR; do not let the two bases get conflated in grading).
- **1-lot account-blind distortions:** (a) the published single-name result is a diversified
  portfolio average - our 6-name 1-lot sample will be noisier and skewed by single events;
  (b) academic returns are midpoint-priced - Goyal-Saretto show quoted-spread costs cut the
  edge from 22.7% to 3.9%/month, so shadow fills must charge the platform's standard
  fill-model, not midpoint; (c) no compounding/BP constraint in the shadow - fine, the sources'
  per-unit convention matches; (d) assignment risk (American ETF/single-name options vs
  European SPX in the primaries) must be modeled as forced exit at intrinsic when short ITM
  legs face ex-div (section 7).
- **What would falsify the thesis here:** persistent negative expectancy in the IV>HV-gated
  cohort net of fills across ≥25 trades/lane - the published claim (Goyal-Saretto Table 3,
  N-group −9.4%/mo for buyers; Coval-Shumway ~−3%/wk) is specific enough to grade against.

---

## 11. VERIFICATION

- **Verdict: CORRECTED** (one minor date-range fix; every load-bearing constant verified against source text). Verified 2026-07-19 by an adversarial fresh-context verifier whose goal was to refute this brief.
- **What was checked and how:**
  - **Coval-Shumway** - the cited Baylor-hosted working-paper PDF was downloaded and its full text extracted. Located verbatim: "zero-beta, at-the-money straddle positions produce average losses of approximately three percent per week" (abstract); "At-the-money SPX straddles have average returns of -3.15 percent per week while all the SPX straddles we examine lose between 2.89 percent and 4.49 percent per week"; "average returns on at-the-money S&P 100 straddles are -0.5 percent per day"; crash-neutral "still generates average losses of nearly three percent per week"; "roughly between 20 and 50 days to expiration"; "the first bid-ask quote after 9AM (Central Time Zone)"; "The S&P 500 straddles are rebalanced each week"; SPX weekly Jan 1990–Oct 1995; 305-week interval; futures-options robustness set (T-bond, Eurodollar, Nikkei, DM). Table I confirms the -4.49/-3.15/-2.89 strike-bucket means.
  - **Bakshi-Kapadia** - the cited UMass-hosted RFS PDF was downloaded and text-extracted. Located verbatim: "We test model implications using options written on the S&P 500 index"; "the strategy loses about 0.05% of the market index, and about 0.13% for at-the-money calls ... this amounts to 8% of the option value"; abstract "the delta-hedged strategy underperforms zero" and "Third, the underperformance is greater at times of higher volatility"; sample "January 1, 1988" to "December 30, 1995"; maturity buckets 14–30 / 31–60 days ("maturity no more than 60 days"); "restricted to the ±10% moneyness range"; "hedge ratio ... recomputed daily at the close of the day price".
  - **Goyal-Saretto** - the cited Google-Drive PDF (author-hosted, Elsevier JFE version) was downloaded via the direct-download endpoint and text-extracted. Located verbatim: "we sort stocks based on the difference between HV and IV" + the full HV/IV construction sentence; the P/N sign-split sentence; "decile one consists of stocks with the lowest (negative) difference"; "moneyness between 0.975 and 1.025"; "we consider only options that mature in the next month"; "22.7% and a Sharpe ratio of 0.710"; "reduced to 3.9% per month ... effective spread equal to the quoted spread"; Table 3 Panel A means (decile 1 = −0.128, decile 10 = 0.099, N = −0.094, P = 0.044); the Monday-formation/Tuesday-initiation sentence; "terminal payoff of the option that expires in the money"; footnote 15 "held until expiration and not rebalanced"; "the entire U.S. equity option market"; 4,344 stocks / 75,627 pairs; OI=0, bid=0, ask<bid, sub-tick-spread filters; "margin requirements for short positions are roughly equal to one and a half times the cost of written options"; P/N average counts 279/252 (sum 531, matching section 10's ~252-of-~531 claim).
  - **projectfinance (both studies)** - the live domain still fails DNS; both cited Internet Archive snapshots were downloaded (web.archive.org, snapshots dated 20260509 for selling-straddles and the 2023-nearest capture for straddle-management) and their article text extracted. Located verbatim: 25–35 DTE methodology sentence; "823 short straddle trades"; "84% of trades reached a 20% profit but only 51% reached a 20% loss"; "less than 50% of one-month short straddles in SPY have reached the 50% profit level"; "entered when the VIX was above 23 (the top 25% of VIX readings on the days of trade entries)"; "the high VIX entries had by far the best results"; Jan-2007 study start; "keep trade size small"; 60-DTE management methodology; "Sell the at-the-money call and put."; both management menus ("None, 10% Profit Target, 25% Profit Target, 50% Profit Target." and "None (hold to expiration), -50% loss, -100% loss, -150% loss."); "Taking profits at 10-25% ... significantly increased the consistency of returns"; the $10/$7.50 and $10/$20 examples; "the best-performing approach was to use a -100% stop-loss ..." (source sentence begins "Visually, the best-performing approach ..."); "-100% is strategically better than ... -150%"; "25% Profit OR 100% Loss" among the four combined rules with the $7.50/$15 example; "Next Entry Date: First trading day after previous trades were closed."; "One straddle sold for all trades."; Feb-2018 loss admission; gap-through-stop EOD-data explanation; "2008, 2015 and 2018" crash warning; the rolling and wiped-out FAQ quotes; last-updated dates April 5th, 2022 and April 25th, 2022. Confirmed the per-rule win-rate/avg-P&L tables are images in the archive (correctly marked UNKNOWN in section 6).
  - **tastylive** - live page fetched; "Our target timeframe for selling straddles is around 45 days to expiration. Our studies show this is a great balance between shorter and longer timeframes." found verbatim; no 21-DTE rule on the page (consistent with the brief's [unverified]/not-adopted treatment).
- **Correction applied:** section 6, Coval-Shumway OEX bullet - the −0.5%/day zero-beta straddle series is Jan 1986–**Oct** 1995 per the paper's straddle analysis (intro and Table III); Dec 1995 is the end of the paper's OEX option-return dataset, not the straddle series. No other change; no constant was invented; ADAPTED/PLATFORM-POLICY/UNKNOWN tags were found honest (notably: the 60-DTE→30-DTE management transplant, the cross-sectional→per-symbol sign-gate adaptation, and the zero-beta→1:1 weights are all loudly flagged).
- **Residual doubts:** (1) Page-number locators for Goyal-Saretto (pp. 311–314) could not be pixel-checked against the journal pagination from extracted text order, but all quoted sentences exist and sit in the expected sections; (2) the Coval-Shumway PDF verified is the June-2000 working draft the brief cites, not the final JF typeset version - wording of the published version may differ trivially; (3) the projectfinance numeric table values (win rates, avg P&L per management rule) remain unverifiable (images), exactly as the brief itself flags; (4) the brief's expected-trades/month estimate (section 10) and the Reg-T CaR proxy are platform constructions, correctly not tagged as sourced.
