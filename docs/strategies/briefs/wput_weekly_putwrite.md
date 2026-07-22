# Strategy Brief: wput_weekly_putwrite

WPUT-style weekly ATM put-write, hold to expiry. Researched 2026-07-19. Primary source READ IN FULL
(15-page PDF extracted to text); secondary source READ IN FULL (Bondarenko 2019, Cboe-hosted PDF).
Every constant in sections 3, 4, 8 carries a direct quote or a precise locator. UNKNOWN means UNKNOWN.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `wput_weekly_putwrite`
- **Provenance class:** CBOE-index
- **PRIMARY citation:**
  - URL: https://cdn.cboe.com/api/global/us_indices/governance/Cboe_PutWrite_Indices_Methodology.pdf
  - Title: *Cboe PutWrite Indices METHODOLOGY* (Cboe Global Indices, LLC), Version 2.0, Last Revised
    Date October 15, 2025. Covers PUTR, PUTY, PTLT, WPTR and **WPUT (Cboe S&P 500 One-Week PutWrite
    Index)**. Relevant sections: §1.1 (objective), §2.1 (constituents), §2.2 (rebalance table),
    §2.2.3 (Rebalance Details WPTR & WPUT), §3.2.3 (Roll Date Calculations WPTR & WPUT), §5 (index info).
  - Note: the formerly separate *Cboe One-Week PutWrite Indices Methodology* PDF at
    `cdn.cboe.com/api/global/us_indices/governance/Cboe_One-Week_PutWrite_Indices_Methodology.pdf`
    now returns AccessDenied; per the consolidated document's own footnote, "Prior to October 14, 2024,
    the methodologies of the Indices covered by this document were separately maintained in a legacy
    format." The consolidated methodology above is the live authority.
- **SECONDARY (independent performance study, read directly):**
  - URL: https://cdn.cboe.com/resources/spx/bondarenko-oleg-putwrite-putw-2019.pdf
  - Title: *Historical Performance of Put-Writing Strategies* (2019), Oleg Bondarenko, University of
    Illinois at Chicago. Cboe-sponsored but independently authored academic study of PUT and WPUT.
- **Tertiary corroboration (not load-bearing):**
  - Bondarenko, *An Analysis of Index Option Writing with Monthly and Weekly Rollover* (Jan 2016),
    SSRN abstract 2750188: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2750188 (first WPUT study,
    period Feb 2006 – Dec 2015; superseded by the 2019 update above).
  - CXO Advisory summary of the 2016 paper:
    https://www.cxoadvisory.com/equity-options/performance-of-cboe-putwrite-indexes/
  - Cboe WPUT dashboard: https://www.cboe.com/us/indices/dashboard/WPUT/
- **Publication dates:** WPUT index Base Date January 31, 2006; Launch Date August 3, 2015; Base
  Value 100 (methodology §5). Methodology version read: v2.0, revised 2025-10-15. Bondarenko studies:
  2016 and 2019.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**What the source trades:** one short **SPX** (S&P 500 cash index) put, European-style, cash-settled,
1-week expiration, fully collateralized by a T-bill account. Methodology §2.1 constituents for WPUT:
T-bills Long (4 weeks) + Option Short SPX, Expiration "1 week", Option Type "Put". §1.1: "collects
option premiums from writing an At-the-Money (ATM) SPX Put option on a weekly basis and holds a
Treasury bill account invested in one-month Treasury bills to cover the liability from the short SPX
Put option position."

**Our mapping:** SPY / QQQ / IWM weeklys as the core (SPY ≈ SPX/10 proxy; IWM maps to the sibling
WPTR index which uses identical mechanics on RUT), plus the liquid mega-cap tier
AAPL / NVDA / MSFT / TSLA / AMD / META as an ADAPTED extension. One short ATM weekly put per symbol,
written Friday, held to the following Friday's expiry.

**LOUD ADAPTATION NOTICE (options-only platform, American-style universe):**
1. SPX options are **European, cash-settled**; everything in our universe is **American-style,
   physically settled**. We never take delivery: the shadow closes the position at expiry-Friday
   4:00 p.m. ET at intrinsic value (the exact analogue of the methodology's PM-settlement branch,
   where the expiring put "is purchased back at the last ask price of the put option before
   4:00 p.m. ET", §2.2.3). No stock legs ever exist. Early assignment before expiry is possible in
   our universe and impossible in the source's - see §7.
2. The source's AM-settlement branch (settle vs the SOQ, strike picked vs the SOQ) has no analogue
   for PM-expiring ETF/equity weeklys, so we implement the **PM branch uniformly** (§2.2.3 gives both
   branches; modern SPXW Friday weeklys are themselves PM-settled, so this is the branch the live
   index uses on most Fridays). Constants affected are tagged ADAPTED in §8.
3. Extending from one cash index to single stocks adds idiosyncratic/earnings gap risk that the
   published edge claim (the S&P 500 volatility risk premium: Bondarenko 2019, "From 1990 to 2018,
   the average implied volatility, as measured by the Cboe Volatility Index (VIX), is 19.3%, while
   the average realized volatility of the S&P 500 index is 15.1%") does not cover. The single-name
   tier tests whether the VRP harvest generalizes; the ETF trio is the faithful replication.

**Why the mapping preserves the edge claim:** the edge is the persistent gap between implied and
realized index volatility, harvested by systematically selling the highest-theta ATM tenor (1 week)
and holding to expiry. SPY/QQQ/IWM weekly ATM puts price off the same index vol surfaces (SPX/NDX/RUT),
so the premium-vs-realized spread carries over one-for-one modulo American/physical microstructure.

## 3. EXACT ENTRY RULES

The index has **no trigger condition at all** - it writes unconditionally every week. There is no
IV gate, no regime gate, no event filter anywhere in the methodology. Absence verified against the
full 15-page document.

- **Cadence / roll day:** "Roll date is every Friday. Should an exchange holiday fall on a Friday,
  the roll date is the preceding business day." (§2.2 rebalance table, WPUT row)
- **Strike selection (AM branch, published):** "The first available SPX Put option strike below the
  Special Opening Quotation (SOQ) of the S&P 500 Index (SPX Index)" (§2.2 table, WPUT row); restated
  §2.2.3: "For AM-settlement, the first available put option strike below the SOQ is selected".
  This is the closest strike at-or-just-below spot - i.e., ATM, biased ≤ spot. No delta target, no
  credit rule, no moneyness percentage exists in the source.
- **Strike selection (PM branch, published - the branch we implement):** "For PM-settlement, the
  first available put option strike below the last disseminated value of the underlying index before
  4:00 p.m. ET is selected" (§2.2.3).
- **DTE selection:** Expiration "1 week" (§2.1 constituents table). Written on Friday expiring the
  following Friday → 7 calendar days / 5 trading days at entry (holiday rolls shift to the preceding
  business day per the roll-date rule above).
- **Entry timing & fill convention (AM branch):** "an ATM one week put option is written after the
  market opens (9:30 a.m. ET) ... The first bid quote after the market opens is the option premium
  collected from the written put option." (§2.2.3); "the option premium collected is the first bid
  quote of the put option after 9:30 a.m. ET" (§2.2.3).
- **Entry timing & fill convention (PM branch):** "the option premium collected is the last bid
  quote of the put option before 4:00 p.m. ET" (§2.2.3).
- **Published regime/IV gate:** NONE - the methodology contains no conditional language of any kind
  around entry. This absence is itself a published fact: the strategy's identity is unconditional
  weekly premium collection.

**Our entry:** every Friday (holiday → preceding business day), in the final minutes before
4:00 p.m. ET, sell 1 ATM put per universe symbol expiring the next Friday; strike = first listed
strike below last trade price; credit marked at bid (PM branch conventions, ADAPTED only in that the
reference price is the ETF/stock last trade instead of the index dissemination).

## 4. EXACT EXIT RULES

Hold to expiry. Full stop. These override all platform exit doctrine for this strategy.

- **No profit target, no stop loss, no early exit, no intra-week roll** exist anywhere in the
  methodology. The only exit event is the next roll date. For the monthly siblings the document says
  it outright: "The Indices require that the put options in the hypothetical portfolio be held to
  maturity." (§2.2.1 - that sentence sits under the PUTY & PUTR rebalance details; the WPUT section
  §2.2.3 states the same doctrine operationally by defining *only* a settlement/buyback procedure on
  the roll date and no other exit path.)
- **Expiry settlement (AM branch, published):** "If the expiring put option is AM-settlement on the
  Roll Date, the expiring put option settles against the SOQ." (§2.2.3). Settlement value formula
  (§3.2.3): "Put_old_settle = Max(0, K_old − SOQ_t) is the settlement value of the expiring put option".
- **Expiry settlement (PM branch, published - our template):** "If the expiring put option is
  PM-settlement on the Roll Date, the expiring put option is purchased back at the last ask price of
  the put option before 4:00 p.m. ET." (§2.2.3)
- **Our exit (ADAPTED mechanics, same doctrine):** hold the short put untouched until expiry Friday;
  close at 4:00 p.m. ET at intrinsic value vs the closing price (shadow equivalent of cash
  settlement / the published last-ask buyback; avoids physical delivery, which our platform cannot
  hold). If the option finishes OTM it expires worthless; if ITM the exit debit is
  max(0, K − close) × 100 per contract.
- **Early assignment (our universe only):** if the shadow's assignment model flags a deep-ITM short
  put as rationally exercised before expiry (see §7), the position is closed at intrinsic on that
  day - an ADAPTED forced-exit path that does not exist in the European-settled source; log it as
  `early_assignment`, not as a discretionary exit.

## 5. SIZING CONVENTION IN SOURCE

Fully collateralized (cash-secured), exactly one unit of short put per strike-notional of T-bills:
"a notional amount equal to the strike (K) of the put option is invested in a Treasury bill account
to cover the liability of the short put option position" (§2.2.3). Collateral earns "interest at the
4-week Bank discount rate" (§2.2.3), with the roll-day exception "interest is not accumulated in the
Treasury bill account on roll day" (§3.2.3). The index is account-blind and never levers.
**Our shadow:** always 1 published unit = 1 contract per symbol per week, account-blind per platform
convention. We do not model the T-bill interest leg (noted in §10 as a small positive bias we forgo).

## 6. DOCUMENTED PERFORMANCE

All figures below were read directly in Bondarenko 2019 (secondary source) unless noted. The primary
methodology publishes no performance numbers. Period for all WPUT rows: Jan 31, 2006 – Dec 31, 2018,
13 years, which INCLUDES pre-launch back-test history (index launched Aug 3, 2015; Cboe's own
disclaimer: back-tested values "may not produce performance commensurate with prospective application
of the methodology").

- Annual compound return: **4.51% WPUT** (vs 5.97% PUT, 7.59% S&P 500) [verified-secondary]
- Annualized standard deviation: **9.48% WPUT** (vs 10.69% PUT, 14.32% S&P 500) [verified-secondary]
- Annualized Sharpe ratio: **0.40 WPUT** (vs 0.50 PUT, 0.51 S&P 500) [verified-secondary]
- Sortino 0.53, Stutzer 0.39 (WPUT) [verified-secondary]
- Maximum drawdown: **−24.2% WPUT** (vs −32.7% PUT, −50.9% S&P 500); longest drawdown 22 months
  (WPUT) vs 29 (PUT) vs 52 (S&P 500) [verified-secondary]
- Worst single month: **−14.14% WPUT** (Exhibit 15 "Min Return") [verified-secondary]. Exhibit 15
  does not date the min return; the 2008-crisis attribution is INFERRED from Exhibit 19's WPUT
  max-drawdown month of Oct-08 [verified-secondary for the Oct-08 max-DD month; inference for
  dating the worst month]
- Average weekly premium: **0.71% of underlying value**; "Selling 1-week ATM puts 52 times a year can
  produce even higher income, but please note that transaction costs can be higher with more frequent
  trading." [verified-secondary]
- Average annual gross premium: **37.1% WPUT** vs 22.1% PUT (per-year range 18.7% in 2017 to 61.6%
  in 2008, Exhibit 22) - gross premium, NOT return; the same exhibit warns "While the gross premiums
  collected are always positive, the cash-secured put-writing strategy does have downside risk and
  its net returns can be negative." [verified-secondary]
- Earlier study (Feb 2006 – Dec 2015, Bondarenko 2016 via CXO Advisory summary): WPUT gross annual
  compound return 5.6%, stdev 9.8%, Sharpe 0.50, max drawdown −24% [verified-secondary, tertiary
  channel - read in CXO's summary of the 2016 paper, not in the 2016 paper itself]
- Win rate: UNKNOWN - not published in either source.
- Profit factor: UNKNOWN - not published in either source.
- Post-2018 performance (incl. Mar-2020 and Aug-2024): not covered by any source read for this
  brief; any number would be [unverified] and is therefore omitted. WPUT live data continues on the
  Cboe dashboard for future verification.

**Methodology caveats:** index returns are frictionless (premium at bid is realistic-conservative,
but no commissions/slippage); 2006–2018 blends back-test (pre-Aug-2015) with live; returns include
the T-bill collateral yield, which our shadow does not model.

## 7. KNOWN FAILURE MODES

Historical episodes (index-level; WPUT-specific numbers only where a read source gives them):
- **Oct/Nov 2008 GFC** - WPUT's max drawdown −24.2% and worst month −14.14% land here
  [verified-secondary]. ATM weekly puts re-strike lower every Friday in a crash, so the weekly form
  drew down less than monthly PUT (−32.7%) but still took the crash nearly one-for-one below strike.
- **Aug 2011 US-downgrade vol spike** - 2011 gross premium 55.7% (2nd highest in Exhibit 22)
  [verified-secondary]: elevated premium years are elevated-realized-vol years; the premium is
  compensation, not free income.
- **Feb 5, 2018 "Volmageddon"** - short-vol family stress date; falls inside the 2018 column of the
  study (2018 premium 35.6% yet WPUT's full-period Sharpe degraded vs the 2016 study's 0.50 → 0.40)
  [verified-secondary at the annual level; the single-day WPUT print was not read → unverified].
- **Mar 2020 COVID crash** and **Aug 5, 2024 VIX spike** - post-sample for every source read here;
  structurally identical exposure (short gap risk through the strike with only one week of premium
  as buffer) [unverified as to magnitude; flagged for live monitoring].
- **Post-2015 premium attenuation** - WPUT trailed both PUT and the S&P 500 on Sharpe over
  2006–2018 (0.40 vs 0.50/0.51) [verified-secondary]; the weekly form's paper advantage (higher
  aggregate premium) did not translate into higher risk-adjusted return, and Bondarenko explicitly
  warns weekly rollover multiplies transaction-cost drag ("transaction costs can be higher with more
  frequent trading").

Structural failure modes (our adaptation):
- **Gap-through-strike:** an ATM put is ~50Δ at entry; any overnight/weekend gap below the strike is
  taken in full minus 0.71%-ish of premium. Single-name tier: an earnings gap inside the held week
  (the source universe has no earnings) - the published rules contain no earnings filter, so trades
  held through single-name earnings must be tagged for separate grading.
- **Early assignment (American, physical):** deep-ITM short puts can be assigned before expiry once
  remaining extrinsic < carry benefit (put early exercise is interest/hard-to-borrow driven; the
  classic ex-div early-assignment channel belongs to short ITM CALLS and does not apply to this
  all-put family, but deep-ITM puts near expiry are routinely assigned). European SPX has none of
  this; treat any assignment as the ADAPTED forced exit of §4.
- **Pin risk at expiry** is settled by our intrinsic-at-close convention (no delivery in a shadow).
- **Holiday-shortened weeks:** roll shifts to the preceding business day (published rule) - DTE can
  be 6 or 8 calendar days; do not treat as a data error.
- **VIX-complex dislocation:** premium marks (bid) can be stale/wide in a vol spike exactly when the
  position needs marking - mark quality gate matters most on the worst days.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | published_underlying | SPX (S&P 500 cash index) | SOURCE-VERBATIM | "writing an At-the-Money (ATM) SPX Put option on a weekly basis" (§1.1) |
| 2 | our_universe | SPY, QQQ, IWM + AAPL, NVDA, MSFT, TSLA, AMD, META | ADAPTED | Source trades SPX only (§2.1); ETF proxies + mega-cap tier per platform mapping; single names extend beyond the published edge claim (see §2) |
| 3 | position | short 1 put, no other legs | SOURCE-VERBATIM | §2.1 constituents: "Option / Short / SPX / ... / Put" |
| 4 | option_style_published | European, cash-settled | SOURCE-VERBATIM | settlement "Max(0, K_old − SOQ_t)" (§3.2.3); our universe is American/physical → exit adapted (row 12) |
| 5 | dte | 1 week (write Friday, expire next Friday; 6–8 calendar days across holidays - derived range, not published) | SOURCE-VERBATIM (tenor) + derived (holiday range) | Expiration "1 week" (§2.1); "Roll date is every Friday" (§2.2) |
| 6 | roll_day | Friday; exchange holiday on Friday → preceding business day | SOURCE-VERBATIM | "Roll date is every Friday. Should an exchange holiday fall on a Friday, the roll date is the preceding business day." (§2.2, WPUT row) |
| 7 | strike_rule | first available strike strictly below reference price (ATM, ≤ spot) | SOURCE-VERBATIM | "The first available SPX Put option strike below the Special Opening Quotation (SOQ)" (§2.2); PM branch: "first available put option strike below the last disseminated value of the underlying index before 4:00 p.m. ET" (§2.2.3) |
| 8 | strike_reference_ours | last trade price of the underlying before 4:00 p.m. ET on roll day | ADAPTED | PM-branch analogue; ETFs/stocks have no SOQ and our weeklys are PM-expiring, so the AM/SOQ branch is inapplicable |
| 9 | entry_timing | final minutes before 4:00 p.m. ET Friday | ADAPTED (from SOURCE-RANGE) | Source has two branches: "written after the market opens (9:30 a.m. ET)" [AM] or priced at "the last bid quote ... before 4:00 p.m. ET" [PM] (§2.2.3); we standardize on the PM branch |
| 10 | entry_fill_convention | credit = option BID at entry (not mid) | SOURCE-VERBATIM | "The first bid quote after the market opens is the option premium collected" / "the option premium collected is the last bid quote of the put option before 4:00 p.m. ET" (§2.2.3) |
| 11 | entry_gate | NONE - unconditional weekly write; no IV/regime/event filter | SOURCE-VERBATIM (absence) | No conditional entry language exists anywhere in the methodology (full document read); the strategy writes every week by construction |
| 12 | exit_rule | hold to expiry; no profit target, no stop, no intra-week roll; close at intrinsic at expiry-Friday 4:00 p.m. ET | SOURCE-VERBATIM doctrine + ADAPTED settlement mechanics | "the expiring put option settles against the SOQ" [AM] / "purchased back at the last ask price of the put option before 4:00 p.m. ET" [PM] (§2.2.3); "Put_old_settle = Max(0, K_old − SOQ_t)" (§3.2.3); monthly siblings state the doctrine: "The Indices require that the put options in the hypothetical portfolio be held to maturity." (§2.2.1) |
| 13 | profit_target | NONE | SOURCE-VERBATIM (absence) | No profit-taking rule exists in the methodology |
| 14 | stop_loss | NONE | SOURCE-VERBATIM (absence) | No loss-management rule exists in the methodology |
| 15 | early_assignment_handling | forced close at intrinsic on assignment-model trigger, logged `early_assignment` | ADAPTED | Impossible in the European-settled source; required by our American/physical universe (§7) |
| 16 | collateral / CaR basis | cash-secured: strike notional K × 100 per contract (minus credit received) | SOURCE-VERBATIM | "a notional amount equal to the strike (K) of the put option is invested in a Treasury bill account to cover the liability of the short put option position" (§2.2.3) |
| 17 | collateral_yield | NOT modeled in shadow (source: 4-week Bank discount rate, USB4WTA; none on roll day) | ADAPTED | "The Treasury bill account will accumulate interest at the 4-week Bank discount rate." (§2.2.3); "interest is not accumulated in the Treasury bill account on roll day" (§3.2.3); shadow omits the interest leg → small negative bias vs index |
| 18 | position_size | 1 contract per symbol per week, account-blind | PLATFORM-POLICY | Platform shadow convention: 1 published unit; source is 1 unit per K-notional (row 16) |
| 19 | mark_convention | daily EOD mark = mid of last bid-ask before 4:00 p.m. ET | SOURCE-VERBATIM | "Put_t is the average of the last bid-ask quote of the Put option before 4:00 p.m. ET on date t for the closing value" (§3.1.1) |
| 20 | liquidity_gates | platform standard chain-quality funnel (quote presence, spread, OI, touch-feasibility) | PLATFORM-POLICY | Ours by policy; no liquidity gate exists in the source (SPX needs none). Values owned by platform config, not this brief |
| 21 | earnings_week_handling (single names) | trade through per published rules, but TAG every trade holding a single name over its earnings date for split grading | PLATFORM-POLICY | Source has no earnings exposure and no filter; skipping would deviate from the unconditional-write identity (row 11), so we write-and-tag instead |

## 9. DATA REQUIREMENTS

- **Tradier chains:** DTE band 4–9 calendar days (next-Friday expiry from a Friday, tolerant of
  holiday shifts). Needed once per week at entry (Friday afternoon snapshot) + daily EOD quotes for
  marks on the held contract. Strike resolution: full ladder near spot (first strike below last).
- **Earnings calendar (date + bmo/amc):** required for the single-name tier - not to gate entry
  (source has no gate) but to TAG trades holding through earnings (row 21).
- **FOMC/CPI dates:** not required by the strategy (no event gate published); optional as covariates
  for grading only.
- **VIX regime / IV rank:** not required for entry (row 11: no gate). Record VIX level at entry as a
  grading covariate. Our IV-rank archive is cold → VIX-percentile fallback is acceptable since the
  value is diagnostic, not a trade input.
- **Daily history:** underlying daily closes for all 9 symbols (strike reference at entry, intrinsic
  at exit, gap attribution).
- **1-min bars:** not required. Entry/exit both use end-of-day conventions; the last-bid-before-4pm
  entry credit comes from the chain snapshot, not from bar data.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** 1 per symbol per week × 9 symbols × ~4.33 weeks ≈ **39/month**
  (~9/week; ~13/month if the family launches ETF-trio-only). Fastest-grading family on the platform:
  N≥25 per lane arrives in under a month at full universe.
- **Mark cadence:** daily EOD only (row 19). No intraday ladder participation - exits are
  doctrine-fixed (hold to expiry), so the platform exit engine must be BYPASSED for this family per
  section 4 override.
- **Multi-leg shape:** none - single-leg short put, the simplest shape on the platform.
- **Per-family capital-at-risk basis:** cash-secured strike notional: CaR = K × 100 − credit
  received, per contract (row 16). This is the published Reg-T-dominating, fully-collateralized
  basis; do NOT substitute a Reg-T margin proxy or the family's returns will be silently levered
  ~5× relative to the published 4.51%-CAGR-class figures.
- **1-lot account-blind distortions:** (a) strike granularity - SPX picks among $5 strikes on a
  ~6000 index (0.08% granularity); SPY $1 strikes (~0.16%) are comparable, single names can be
  coarser near round levels; (b) we forgo the T-bill interest leg (row 17), a headwind of roughly
  the short rate on K vs the published index - grade against premium-vs-intrinsic P&L, not against
  the WPUT index level; (c) our bid-side entry matches the index's conservative fill convention, so
  no optimistic-fill bias; (d) weekly cadence means the family's e-process wealth updates every
  Friday in a lump - expect stepwise, not smooth, wealth trajectories.
- **Grading benchmark sanity:** average entry credit should sit near 0.71% of underlying per week
  (secondary-verified average) in normal vol; persistent large deviation from that anchor is a
  chain-quality or strike-selection bug, not alpha.

## 11. VERIFICATION

**Verdict: CORRECTED (minor). Date: 2026-07-19. Verifier: adversarial fresh-context pass.**

**What was checked (independently re-fetched, not reusing the author's downloads):**
- **Primary** (`Cboe_PutWrite_Indices_Methodology.pdf`, re-downloaded from cdn.cboe.com,
  text-extracted, all 15 pages read): 15 pages confirmed; v2.0 / Last Revised October 15, 2025
  confirmed; the legacy-format footnote confirmed verbatim. Every §1.1, §2.1, §2.2, §2.2.3,
  §3.1.1, §3.2.3 and §5 quote used in sections 2–5 and in parameter-table rows 1, 3, 4, 5, 6, 7,
  10, 12, 16, 17, 19 was located VERBATIM (roll-day Friday rule; both strike-selection branches;
  both premium-collection branches; both settlement branches incl. "purchased back at the last ask
  price ... before 4:00 p.m. ET"; Max(0, K_old − SOQ_t); strike-notional T-bill collateral; 4-week
  Bank discount rate + USB4WTA; no-interest-on-roll-day note; mid-of-last-bid-ask daily mark;
  held-to-maturity sentence correctly located in §2.2.1 under PUTY & PUTR). WPUT §5 row (Base Date
  Jan 31 2006, Launch Aug 3 2015, Base Value 100) confirmed. Absence claims (rows 11, 13, 14: no
  entry gate, no profit target, no stop) verified by full-document read - no conditional
  entry/exit language exists. WPTR = RUT one-week sibling confirmed. Back-test disclaimer language
  confirmed on the disclosures page. Legacy one-week-methodology URL re-tested 2026-07-19 →
  AccessDenied XML, as the brief states.
- **Secondary** (Bondarenko 2019, re-downloaded from cdn.cboe.com, all 17 pages read): every
  [verified-secondary] number in §6/§7 located: 4.51/5.97/7.59 CAGR, 9.48/10.69/14.32 stdev,
  0.40/0.50/0.51 Sharpe, Sortino 0.53 / Stutzer 0.39 (Exhibit 16); −24.2/−32.7/−50.9 max DD and
  22/29/52-month longest DD (Exhibit 19); −14.14% Min Return (Exhibit 15); 0.71% average weekly
  premium + the exact transaction-costs sentence (Exhibit 21 sidebar); 37.1% vs 22.1% average
  annual gross premium, per-year 18.7% (2017) min and 61.6% (2008) max, 55.7% (2011, verified
  second-highest), 35.6% (2018), and the exact "gross premiums ... net returns can be negative"
  warning (Exhibit 22); VIX 19.3% vs realized 15.1%, 1990–2018, quoted verbatim (page 1 /
  Exhibit 11 sidebar). Period Jan 31 2006 – Dec 31 2018 confirmed throughout.
- **Tertiary channel** (CXO Advisory page, fetched live): 2016-study WPUT numbers confirmed
  exactly as bracketed - 5.6% gross CAGR, 9.8% stdev, 0.50 Sharpe, −24% max DD, sample
  Feb 2006 – Dec 2015; CXO also confirms the 2016 title/date the brief cites. SSRN itself
  returned 403 (bot-blocked) so the abstract id 2750188 was NOT independently confirmed - 
  tertiary, not load-bearing.

**Corrections applied (both minor):**
1. §8 row 5: DTE holiday range corrected 5–8 → **6–8** calendar days and re-tagged as a derived
   range (minimum reachable DTE under the published holiday-shift rules is 6, not 5; the tenor
   itself remains SOURCE-VERBATIM "1 week").
2. §6 worst-month line: Exhibit 15 does not date the −14.14% min return; the 2008-crisis dating
   is now explicitly marked as an inference from Exhibit 19's Oct-08 WPUT max-drawdown month.

**No invented constants found.** Every SOURCE-VERBATIM quote is verbatim-present; every ADAPTED
row carries a real adaptation rationale and none is presented as published; UNKNOWNs (win rate,
profit factor) are genuinely absent from both sources; the edge claim (S&P 500 volatility risk
premium, VIX 19.3% vs realized 15.1%) is exactly what the secondary source states.

**Residual doubts:** (a) SSRN id 2750188 unverified (403); title/date corroborated only via CXO.
(b) The 2019 paper itself refers to the 2016 study as "A Comparison of Index Put Writing with
Monthly and Weekly Rollover" while CXO (and the brief) use "An Analysis of Index Option Writing
with Monthly and Weekly Rollover" - likely the same paper under working vs published titles;
immaterial, tertiary. (c) The single-name extension (row 2) is honestly flagged in the brief
itself as beyond the published edge claim - that is a design risk, not a sourcing defect.
(d) Post-2018 WPUT behavior (Mar 2020, Aug 2024) is uncovered by all read sources, as the brief
already states.

---

### 11.2 Independent second adversarial pass (fresh context)

**Verdict: CONFIRMED. Date: 2026-07-19. Verifier: independent fresh-context adversarial pass
(did NOT reuse the §11 pass above or the author's downloads; both PDFs re-downloaded from
cdn.cboe.com and re-extracted with pypdf).**

What was checked:
- **Primary methodology** (815 KB, 15 pages, v2.0 / Last Revised October 15, 2025 - all
  confirmed): every §1.1, §2.1, §2.2, §2.2.1, §2.2.3, §3.1.1, §3.2.3, §5 quote used in brief
  sections 2–5 and parameter rows 1, 3, 4, 5 (tenor), 6, 7, 10, 12, 16, 17, 19 was located
  verbatim in the extracted text, including: the §1.1 WPUT objective sentence; the §2.1
  constituents row (T-bills Long 4 weeks / Option Short SPX / 1 week / Put); the Friday roll +
  holiday-shift rule; both strike branches (SOQ and last-disseminated-before-4pm); both premium
  branches (first bid after 9:30 / last bid before 4pm); both settlement branches ("settles
  against the SOQ" / "purchased back at the last ask price of the put option before 4:00 p.m.
  ET"); Put_old_settle = Max(0, K_old − SOQ_t) in §3.2.3; the §2.2.3 strike-notional T-bill
  collateral sentence; 4-week Bank discount rate + USB4WTA; no-interest-on-roll-day notes; the
  §3.1.1 mid-of-last-bid-ask mark; "held to maturity" correctly located under §2.2.1
  (PUTY & PUTR). §5 WPUT row (Base Jan 31 2006 / Launch Aug 3 2015 / Base Value 100), the
  legacy-format footnote, the back-test "commensurate" disclaimer, and WPTR-as-RUT-sibling all
  confirmed. Absence claims (rows 11/13/14) re-verified: grep for conditional language
  (VIX/volatility/only if/unless/threshold) hits nothing in the rules sections. Legacy one-week
  methodology URL re-tested: HTTP 403 AccessDenied XML, as stated.
- **Bondarenko 2019** (17 pages): every [verified-secondary] number located - CAGR
  4.51/5.97/7.59 (Exhibit 16); stdev 9.48/10.69/14.32; Sharpe 0.50/0.40/0.51; Sortino 0.53 /
  Stutzer 0.39; max DD −24.2/−32.7/−50.9 and longest DD 22/29/52 months + WPUT Max Drawdown
  Month Oct-08 (Exhibit 19); Min Return −14.14% undated (Exhibit 15 - the brief's
  inference-marking is correct); 0.71% average weekly premium + the exact 52-times-a-year
  transaction-cost sentence (Exhibit 21 sidebar); Exhibit 22 table row-by-row: 2008 61.6% max,
  2017 18.7% min, 2011 55.7% (verified second-highest), 2018 35.6%, averages 22.1%/37.1%, and
  the "gross premiums ... net returns can be negative" note verbatim; VIX 19.3% vs realized
  15.1% (1990–2018) verbatim; sample Jan 31 2006 – Dec 31 2018 throughout.
- **Tertiary:** CXO page fetched live - 2016-study WPUT 5.6% / 9.8% / 0.50 / −24%,
  Feb 2006 – Dec 2015, title and Jan-2016 date all match the brief exactly. SSRN direct fetch
  still 403, but a web search independently returned SSRN abstract 2750188 titled "An Analysis
  of Index Option Writing with Monthly and Weekly Rollover by Oleg Bondarenko" - this RESOLVES
  residual doubt (a) of the first pass: the SSRN id, title, and author are now confirmed.

Findings: **zero invented constants; zero misquotes; zero mis-tagged rows.** All ADAPTED rows
carry genuine adaptation rationale and none is presented as published. The prior pass's two
corrections (DTE 6–8 derived range; Oct-08 inference marking) are present in the file and are
themselves correct against the sources. No edits to sections 1–10 were needed by this pass.

Residual doubts carried forward: first-pass items (b) 2016-paper working-vs-published title
discrepancy (immaterial, tertiary) and (c)/(d) design-level caveats (single-name extension
beyond the published edge claim; post-2018 behavior unsourced) - these are honestly disclosed
in the brief, not sourcing defects.
