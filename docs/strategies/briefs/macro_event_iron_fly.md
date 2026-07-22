# macro_event_iron_fly - CPI/FOMC event iron fly through the print

Researched 2026-07-19. Every constant in sections 3, 4, 8 carries a direct quote or a precise
locator, or is marked UNKNOWN / ADAPTED / PLATFORM-POLICY. Sources were read directly (PDF text
extraction or page fetch) on 2026-07-19 unless tagged otherwise.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `macro_event_iron_fly`
- **Provenance class:** academic (edge claim) + practitioner (trade structure). This is a
  SYNTHESIS family: no single published source specifies the complete rulebook. The edge claim
  (macro-announcement option premium) is academically documented; the iron-fly-through-the-print
  is the defined-risk practitioner expression of "short the event straddle." All structural
  constants not pinned by a source are tagged accordingly in section 8.
- **PRIMARY citation (academic, edge claim):**
  Londono, Juan M. and Mehrdad Samadi (2023). *"The Price of Macroeconomic Uncertainty: Evidence
  from Daily Option Expirations."* International Finance Discussion Papers **1376**, Board of
  Governors of the Federal Reserve System, June 2023. DOI 10.17016/IFDP.2023.1376.
  URL: https://www.federalreserve.gov/econres/ifdp/files/ifdp1376.pdf (full PDF read; 55 pp.)
- **SECONDARY sources (independent):**
  1. Windmar, Carl (2025). *"Risk Premium around Macroeconomic Announcements: Evidence from
     Delta-Neutral Straddles."* Master thesis, Department of Economics, Lund University, seminar
     date 3 June 2025. URL: https://lup.lub.lu.se/student-papers/record/9197108/file/9197117.pdf
     (full PDF read; 28 pp.). Also relays DeSimone (2017) straddle results.
  2. Rhoads, Russell (2023-12-10). *"Historical Index And Option Price Action Around CPI (Tuesday)
     And FOMC (Wednesday)."* russellrhoads.substack.com.
     URL: https://russellrhoads.substack.com/p/historical-index-and-option-price (read via fetch).
  3. Du Plessis, Kirk & Steve Henry (2024-09-17, upd. 2024-10-14). *"Trading the FOMC Meeting:
     0DTE & Next Day Strategies."* Option Alpha.
     URL: https://optionalpha.com/blog/trading-the-fomc-meeting-0dte-next-day-strategies (read).
  4. Option Alpha, *"Iron Butterfly Options Strategy Guide."*
     URL: https://optionalpha.com/strategies/iron-butterfly (read; structure conventions).
  5. Matthews, Spicer (2026-05-17). *"Zero DTE SPX Iron Butterfly: 431% Returns and a Brutal
     2025."* Options Cafe. URL: https://options.cafe/blog/zero-dte-spx-iron-butterfly-strategy/
     (read; NON-event daily fly - used for structure precedent and contra-evidence).
  6. Olson, Jim. *"Jim Olson Iron Butterfly 0DTE Trade Plan."* 0DTE.COM.
     URL: https://0dte.com/jim-olson-iron-butterfly-0dte-trade-plan (read; NON-event daily fly - 
     wing-width precedent only).
- **Publication dates:** primary June 2023 (first version April 2023); secondaries Dec 2023,
  Sep 2024, June 2025, May 2026.
- **Calendar anchors (read directly):** FOMC statement release time verified from the Fed's
  2025-01-29 press release (release-line reads "For release at 2:00 p.m. EST",
  https://www.federalreserve.gov/newsevents/pressreleases/monetary20250129a.htm); 2026 FOMC
  meeting dates (8 meetings) from https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

- **What the sources trade/measure:**
  - Londono & Samadi: daily-expiration **S&P 500 index (SPX) options** - "recently available
    daily S&P 500 index option expirations" - European-style, cash-settled.
  - Rhoads: **SPX and NDX** 1-day ATM straddles (plus SX5E/DAX price action, options not traded).
  - Windmar: delta-neutral straddles on SINGLE-STOCK options of the 52 largest S&P 500
    constituents by market cap (Bloomberg API data; long-dated - see caveats in section 6).
    NOT index options - this secondary is single-name evidence. [corrected 2026-07-19]
  - Option Alpha FOMC piece and both daily-fly plans: **SPX**.
- **Our mapping:** **SPY, QQQ, IWM only.** QQQ maps Rhoads' NDX evidence; SPY maps SPX; IWM is a
  platform-universe extension with NO direct published evidence (tagged ADAPTED in section 8).
  **Mega-caps (AAPL/NVDA/MSFT/TSLA/AMD/META) are EXCLUDED from this family**: the documented
  macro-announcement premium of the PRIMARY is an index-level phenomenon (Windmar's single-name
  straddle evidence exists but is long-dated and structurally distant); no source documents a
  single-stock macro-event fly, and single names add idiosyncratic (non-macro) gap risk that the
  primary edge claim does not cover.
- **LOUD ADAPTATION #1 - structure:** the academically measured object is the **short ATM
  straddle / event-expiration variance premium** (naked). We trade the **iron fly** = that same
  short ATM straddle **plus bought wings** (defined risk; platform is options-only and
  account-blind, naked index straddles are not runnable). Wings cost premium, so our capture will
  be strictly SMALLER than the published straddle premia; the tail-loss profile is capped at
  width − credit instead of unlimited. All wing constants are ADAPTED (section 8).
- **LOUD ADAPTATION #2 - settlement:** sources trade European cash-settled SPX. SPY/QQQ/IWM
  options are American-style with physical delivery → early-assignment and pin risk exists that
  the published form does not have. Mitigated by the PLATFORM-POLICY close-out before expiry
  close (section 4). Option Alpha's structure guide states the reason: "At expiration, one of the
  short options will likely be in-the-money and at risk of assignment, so the position must be
  closed if assignment is to be avoided."
- **Why the mapping preserves the edge claim:** the premium is priced into the *event-spanning
  expiration* of index-linked options; SPY/QQQ options on the same expirations track SPX/NDX
  event IV nearly one-for-one. The claim ("options spanning CPI/FOMC are ex ante overpriced
  relative to neighboring expirations") transfers to the ETF proxies; only the tail mechanics
  (assignment, settlement) differ, and those are documented above.

## 3. EXACT ENTRY RULES

**Trigger (event set):** trade only scheduled **CPI** and **FOMC** release dates.
- Primary documents the premium for four releases: "The cost of insurance against price,
  variance, and downside risk is higher for options that span U.S. CPI, FOMC, Nonfarm Payroll,
  and GDP releases compared to neighboring expirations." (Londono & Samadi 2023, abstract.)
- Our restriction to CPI+FOMC (strategy-id scope) leans on the primary's ranking evidence:
  IV premium is largest for FOMC - "Implied volatilities of treated options are between 44 basis
  points (GDP) and 134 basis points (FOMC) larger than control options, which represents an
  increase between 2.5% (GDP) and 7.5% (FOMC) with respect to the implied volatilities for
  control options" (p. 11) - and "CPI releases are associated with larger risk premia during
  2022, as policy makers have communicated dependence on incoming economic data" (p. 20).
  NFP/GDP omission is an ADAPTED scope choice, not a published rule.
- Event times, quoted: "CPI and Nonfarm Payrolls are announced monthly at 8:30 am based on the
  schedule of releases provided by the Bureau of Labor Statistics" (primary, p. 7-8). FOMC:
  "FOMC monetary policy rates are announced right after each of the 8 routine FOMC meetings each
  year" (primary, p. 8); statement time verified by the release line "For release at 2:00 p.m. EST"
  (Fed press release 2025-01-29).
- Only *scheduled* releases qualify; the primary identifies releases from a calendar
  ("Macroeconomic release dates are identified using the Bloomberg U.S. Economic Calendar,"
  p. 7). Unscheduled/intermeeting Fed actions are NOT tradeable events for this family.

**Structure:** short iron fly (4 legs, same expiration): sell ATM call + ATM put, buy 1 OTM call
+ 1 OTM put. Option Alpha structure guide: the iron butterfly "consists of selling an
at-the-money short straddle and buying out-of-the-money options 'on the wings'".

**Strike selection:**
- Body: nearest listed strike to spot at entry. Quote: "Iron butterflies are typically sold
  at-the-money of the underlying asset" (Option Alpha guide). Olson's plan (SPX 3150.47 →
  sold the 3150 call/put) is the same convention.
- Wings: **no published event-fly wing width exists → UNKNOWN canonical; ADAPTED default:**
  wing distance = 1.0 × ATM straddle mid price at entry (the market-implied move), rounded UP to
  the next listed strike; both wings equidistant. Precedent for scaling wings to the implied
  move is Olson's (non-event) plan: "Use $50 wings if implied move under $30" (increase by $10
  increments for larger moves). Rationale: puts max-loss onset at the market's own priced move,
  keeping CaR comparable across events and tickers.

**DTE selection:**
- CPI (08:30 ET, pre-open print): use the expiration that is the CPI day itself; enter the PRIOR
  trading day → 1 DTE at entry. Source convention (Rhoads): his tracked series is the
  "1-day at-the-money (ATM) straddle price the day before and at expiration."
- FOMC (14:00 ET, intraday print): use same-day expiration → 0 DTE. Source (Option Alpha FOMC
  piece): their announcement-day structure is the section headed "0DTE Strategy" (the FOMC
  announcement-day strategy; parenthetical is ours, not part of the heading).
- Note: the PRIMARY paper's premium measurements use 7–21 calendar-day expirations ("we examine
  option expirations with 7 to 21 calendar days to expiration (7 ≤ Tcaldays ≤ 21)", p. 8) - the
  premium is documented on the event-spanning expiration curve, not specifically at 0–1 DTE. Our
  0–1 DTE concentration follows the practitioner sources (Rhoads, Option Alpha) and is tagged
  SOURCE-VERBATIM to them, not to the primary.

**Entry timing:**
- CPI: prior trading day, near the close (Rhoads: "the day before"; exact minutes not published
  → PLATFORM-POLICY window 15:30–15:50 ET).
- FOMC: announcement day, "15-30 mins before the FOMC announcement" (Option Alpha FOMC piece,
  quoted verbatim) → default entry 13:35 ET, window 13:30–13:45 ET.

**Regime / IV gate:** NONE PUBLISHED → UNKNOWN. The primary documents the premium
unconditionally on release-spanning expirations (2017–2023 sample). No IV-rank or VIX gate is
adopted at launch; premium magnitude covariates in the primary (risk aversion, MPU) are
diagnostics only.

## 4. EXACT EXIT RULES (OVERRIDE platform exit doctrine for this family)

- **Hold-through-the-print to expiration; no pre-print management.** This is the measurement
  convention of every documented result:
  - Rhoads values the short straddle "the day before and at expiration" - nothing in between.
  - Windmar's tightest event window is [-1,1] (enter 1 day before, exit 1 day after) with no
    intraperiod management.
- **Profit target: NONE** (hold to expiry). No published event-form profit target exists.
  (Options Cafe's 2x-credit stop and Olson's "$1.50" target belong to NON-event daily flies and
  are NOT adopted; recorded here so nobody later "remembers" them into this family.)
- **Stop loss: NONE pre-print.** The bought wings are the loss cap (max loss = width − credit).
  The published straddle results are unmanaged; adding a stop would un-publish them.
- **Time exit (PLATFORM-POLICY adaptation, LOUD):** close all four legs in the 15:45–15:55 ET
  window on expiration day rather than letting ETF legs expire. Reason (Option Alpha guide
  quote): "At expiration, one of the short options will likely be in-the-money and at risk of
  assignment, so the position must be closed if assignment is to be avoided." Sources' SPX is
  cash-settled and needs no such rule; SPY/QQQ/IWM do.
  - CPI variant: entry T−1 near close → exit CPI-day 15:45–15:55 ET (position held through the
    08:30 print and the full session).
  - FOMC variant: entry 13:30–13:45 ET → exit same day 15:45–15:55 ET (held through the 14:00
    statement and press conference).
- **Roll rules: NONE.** No source publishes rolls for the event form.

## 5. SIZING CONVENTION IN SOURCE

- Londono & Samadi and Windmar measure per-unit option returns/premia (no account sizing).
- Rhoads quotes single-straddle P&L in index points (e.g., one NDX straddle sold at 142.25).
- Options Cafe (non-event daily fly): "1 contract per $6,000 of account" (author suggests ~10%
  risk per trade for real accounts) - context only.
- **Our shadow: always 1 published unit = 1 iron fly (4 legs), account-blind**, per platform
  convention. No compounding, no %-of-buying-power.

## 6. DOCUMENTED PERFORMANCE

All numbers tagged. The primary documents *ex ante premia*, not strategy P&L.

- **Ex ante premium (primary, Londono & Samadi 2023, SPX, Jan 2017–May 2023):**
  - "At-the-money (ATM) options spanning releases are up to 7.5% more expensive than neighboring
    control expirations." [verified-primary]
  - ATM IV premium of release-spanning expirations: +44 bps (GDP) to +134 bps (FOMC), i.e.
    +2.5% to +7.5% relative [verified-primary].
  - "The average annualized forward daily expected equity risk premium is 2.4%, and the average
    annualized forward daily variance risk premium is 1.4%." [verified-primary]
  - "release premia for all announcements have increased substantially starting in 2022 without
    a commensurate increase in market volatility" [verified-primary]
- **Long-straddle event returns (Windmar 2025 thesis; negative = premium accrues to the
  seller; sample 2, 1 Jan 2024–1 Apr 2025, equal-weighted):** [verified-secondary]
  - CPI window [-1,1]: **−5.15%** (t = −5.12); window [-3,3]: −9.91% (t = −6.99).
  - FOMC window [-1,1]: **−5.60%** (t = −3.99); window [-3,3]: −12.85% (t = −7.18).
  - PPI [-1,1]: −3.48%; employment data inconclusive (+2.14%, t = 1.32).
  - METHODOLOGY CAVEATS: underlyings are SINGLE-STOCK options on the 52 largest S&P 500
    constituents, NOT index options [corrected 2026-07-19]; thesis straddles average **270 DTE**
    and are slightly ITM (median moneyness 1.11) - NOT 0–1 DTE flies; small event counts
    (16 CPI, 10 FOMC); returns are not per-day normalized.
- **DeSimone (2017), as relayed by Windmar (not read directly):** "DeSimone (2017) found
  aggregated average daily returns of -1.86% for announcements of CPI, non-farm payrolls and
  Industrial production. However, DeSimone (2017) finds significant positive returns of 2.6% for
  straddles held under FED meetings." (2010–2014 sample.) [verified-secondary, second-hand]
- **Implied vs realized (Rhoads 2023-12-10, trailing-12-event samples):** [verified-secondary]
  - SPX CPI-day average move ±0.64% vs ±1.07% average daily move (CPI days QUIETER than
    average → CPI straddles overpriced in that window).
  - SPX FOMC-day average move ±1.20% vs ±0.84% average daily (June 2022 onward) - "FOMC day has
    been more volatile than the average trading day"; "The last two straddles on FOMC day
    underpriced the following day's SPX move"; "Straddle sellers got hit on the last two FOMC
    announcements."
  - NDX: CPI ±0.98% vs ±1.34% daily; FOMC ±1.77% vs ±1.13% daily.
- **FOMC-day volatility (Option Alpha 2024):** FOMC days average 2% SPX move vs 1.25% non-FOMC
  (60% higher); day after averages 1.6%, closes lower 66.7% of the time. [verified-secondary]
- **Seeking Alpha, "The FOMC Volatility Premium: Evidence From 1-Day Nasdaq-100 Straddles"**
  (paywalled, NOT read): shorting 1-day NDX ATM straddles reportedly profitable in 10 of the
  last 12 FOMC events, cumulative +450.04 points. [unverified - search snippet only]
- **CAGR / PF / max drawdown for the event iron fly itself: UNKNOWN. No source publishes them.**

## 7. KNOWN FAILURE MODES

1. **FOMC regime flip.** The FOMC edge is NOT stable: DeSimone found straddle BUYERS earned
   +2.6% over Fed meetings in 2010–2014 (ZIRP era) [verified-secondary, second-hand], and Rhoads
   documents "Straddle sellers got hit on the last two FOMC announcements" (late 2023, realized
   ±1.20% > implied) [verified-secondary]. Windmar's 2024–25 sample flips it back to strongly
   seller-favorable (−5.60% [-1,1]). Expect the FOMC leg to swing between regimes; grade the CPI
   and FOMC lanes separately.
2. **Inflation-shock tails through the wings.** Rhoads' concrete example: an NDX Nov 14 (2023
   CPI) ATM straddle "could have taken in 142.25 and the straddle's value on the close was
   almost 190 points higher at 332.47" - a >2x-credit loss for the seller; the 2022 CPI prints
   produced multi-sigma index moves [unverified from memory for specific 2022 dates]. The fly's
   wings cap this at width − credit - expect FULL max-loss events, not partial ones, on shock
   prints.
3. **CPI gap risk is unmanageable by construction.** The 08:30 ET print lands before the options
   market opens; the position CANNOT be exited between the print and the open. Wings are the
   only protection. This is inherent to the published day-before-entry form.
4. **Short-vol episode family:** Feb-2018 Volmageddon, Mar-2020 COVID (including unscheduled
   intermeeting Fed actions, which our scheduled-only rule excludes as entries but which can
   still detonate an open CPI-week position), Aug-2024 vol spike [all unverified from memory - 
   named as episode families, no numbers claimed]. Any of these landing on an event day produces
   max loss.
5. **Win-rate mirage.** Options Cafe's adjacent (daily, non-event) SPX ATM fly logged 77–78% win
   rates in BOTH its +85% year (2024) and its −$5,472 losing year (2025): "A 78% win rate
   doesn't make a strategy profitable" when average losses dwarf average wins.
   [verified-secondary] Grade this family on expectancy, never on win rate.
6. **Structural (ETF adaptation):** American-style early assignment on the post-print ITM short
   leg (worst around SPY/IWM quarterly ex-div dates for deep-ITM short calls) and pin risk at
   expiry - mitigated but not eliminated by the 15:45–15:55 ET close-out policy.
7. **Practitioner contra-evidence:** the one daily-fly author who backtested around events
   explicitly EXCLUDES them: "No major macro release before close. No FOMC, no CPI, no NFP."
   (Options Cafe.) [verified-secondary] The through-the-print form is the *opposite* bet - it is
   supported by the academic premium evidence, not by that practitioner's rule. Recorded so the
   tension is visible.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | event_set | {CPI, FOMC} | ADAPTED | Primary studies "U.S. CPI, FOMC, Nonfarm Payroll, and GDP releases" (abstract); our CPI+FOMC subset = strategy-id scope; FOMC has largest IV premium ("134 basis points (FOMC)", p. 11), "CPI releases are associated with larger risk premia during 2022" (p. 20) |
| 2 | cpi_release_time | 08:30 ET | SOURCE-VERBATIM | "CPI and Nonfarm Payrolls are announced monthly at 8:30 am" (primary, p. 7-8) |
| 3 | cpi_frequency | monthly | SOURCE-VERBATIM | "announced monthly at 8:30 am based on the schedule of releases provided by the Bureau of Labor Statistics" (primary) |
| 4 | fomc_release_time | 14:00 ET | SOURCE-VERBATIM | release line "For release at 2:00 p.m. EST" (Fed press release 2025-01-29) |
| 5 | fomc_meetings_per_year | 8 | SOURCE-VERBATIM | "8 routine FOMC meetings each year" (primary, p. 8) |
| 6 | scheduled_only | true (no intermeeting/unscheduled events) | SOURCE-VERBATIM | "Macroeconomic release dates are identified using the Bloomberg U.S. Economic Calendar" (primary, p. 7); "routine FOMC meetings" |
| 7 | entry_day_cpi | T−1 (prior trading day) | SOURCE-VERBATIM | Rhoads tracks the "1-day at-the-money (ATM) straddle price the day before and at expiration" |
| 8 | entry_window_cpi | 15:30–15:50 ET on T−1 | PLATFORM-POLICY | Rhoads publishes "the day before" only; exact minutes are ours (late-day to match his day-before close pricing) |
| 9 | entry_day_fomc | T (announcement day) | SOURCE-VERBATIM | "15-30 mins before the FOMC announcement" (Option Alpha FOMC piece) |
| 10 | entry_window_fomc | 13:30–13:45 ET (default 13:35) | SOURCE-RANGE | source gives the range "15-30 mins before the FOMC announcement"; documented default = midpoint |
| 11 | dte_cpi | 1 at entry (expiry = CPI day) | SOURCE-VERBATIM | Rhoads "1-day ... straddle ... the day before and at expiration" |
| 12 | dte_fomc | 0 (same-day expiry) | SOURCE-VERBATIM | "0DTE Strategy" heading in the FOMC-announcement-day section (Option Alpha FOMC piece) |
| 13 | body_strike | nearest listed strike to spot (ATM) | SOURCE-VERBATIM | "Iron butterflies are typically sold at-the-money of the underlying asset" (Option Alpha guide); Olson example SPX 3150.47 → 3150 body |
| 14 | wing_width | 1.0 × ATM straddle mid at entry, rounded UP to next listed strike; equidistant wings | ADAPTED (canonical value UNKNOWN) | no published event-fly width; implied-move-scaled precedent: "Use $50 wings if implied move under $30" (Olson, non-event plan); rationale: max-loss onset at the market-priced move |
| 15 | min_credit_frac | UNKNOWN | UNKNOWN | no published credit floor for the event form (Options Cafe's "credit is at least 50% of max profit" is their NON-event daily fly - recorded, NOT adopted) |
| 16 | profit_target | none (hold through print to expiry) | SOURCE-VERBATIM | measurement convention: valued "the day before and at expiration" (Rhoads); Windmar event window [-1,1] unmanaged |
| 17 | stop_loss | none pre-print; max loss = width − credit via wings | ADAPTED | published straddle results are unmanaged (same quotes as row 16); wings replace the naked straddle's unlimited tail - platform is defined-risk-only |
| 18 | exit_time | expiry day 15:45–15:55 ET, close all 4 legs | PLATFORM-POLICY | ETF assignment avoidance: "the position must be closed if assignment is to be avoided" (Option Alpha guide); sources' SPX is cash-settled |
| 19 | roll_rules | none | SOURCE-VERBATIM | no roll appears in any cited event-form source (absence, not invention) |
| 20 | iv_entry_gate | none | UNKNOWN | no published gate; primary documents the premium unconditionally over Jan 2017–May 2023 |
| 21 | universe | SPY, QQQ, IWM (1 fly each per event); mega-caps excluded | ADAPTED | sources trade SPX ("daily S&P 500 index option expirations", primary) and NDX (Rhoads); ETF proxies + IWM extension ours; index-level edge does not transfer to single names |
| 22 | unit_size | 1 iron fly (4 legs) | PLATFORM-POLICY | platform 1-published-unit, account-blind convention |

Constants recorded UNKNOWN: **min_credit_frac**, **iv_entry_gate**, **canonical wing_width**
(row 14 default is ADAPTED, not published).

## 9. DATA REQUIREMENTS

- **Tradier chains:** 0–2 DTE band for SPY/QQQ/IWM (FOMC needs same-day expiry; CPI needs
  next-day expiry quoted on T−1 afternoon). Full ATM ± wings strike ladder with NBBO.
- **FOMC calendar:** federalreserve.gov FOMC calendar (2026: Jan 27-28, Mar 17-18, Apr 28-29,
  Jun 16-17, Jul 28-29, Sep 15-16, Oct 27-28, Dec 8-9 - statement day = second day, 14:00 ET).
  Scheduled meetings only.
- **CPI calendar:** BLS release schedule (bls.gov/schedule/news_release/cpi.htm; note: BLS
  blocked our fetcher with 403 - scrape via alternate route or hand-maintain; dates are also in
  any economic calendar). Time is fixed 08:30 ET.
- **Earnings calendar:** NOT required (no single names in this family).
- **VIX regime:** optional diagnostic only (no gate at launch); record VIX at entry for later
  regime analysis. IV rank NOT required (no gate; our IV archive is cold anyway - if a gate is
  ever added, use the VIX-percentile fallback).
- **1-min bars:** event-day 1-min bars for SPY/QQQ/IWM - mark the fly around the FOMC 14:00
  print (14:00–16:00) and into both variants' 15:45–15:55 close-out; also T−1 15:30–16:00 for
  CPI entry fills.
- **Daily history:** for the implied-vs-realized event diagnostic (Rhoads-style scorecard: ATM
  straddle price at entry vs realized move at expiry - this is the family's health metric).

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trade count:** 12 CPI + 8 FOMC = 20 events/yr × 3 tickers = **60 trades/yr ≈ 5.0
  trades/month** (pooled). Pooled N≥25 arrives in ~5 months; per-ticker lanes (20/yr each) need
  ~15 months - grade CPI vs FOMC as separate lanes (regime-flip risk, section 7.1) but pool
  tickers within each lane first.
- **Mark cadence:** entry fill at 4-leg mid inside the entry window; 1-min marks from entry
  through event-day close (critical: the 14:00–14:30 FOMC repricing and both variants'
  15:45–15:55 exit). CPI variant carries an overnight mark gap (T−1 close → T open) that no mark
  cadence can fill - the open mark IS the post-print reality.
- **Multi-leg shape:** 4-leg iron fly, one expiration: −1 ATM call, −1 ATM put, +1 call at
  body+W, +1 put at body−W. Net credit structure.
- **Capital-at-risk basis:** **width − credit** (defined-risk Reg-T style). This is the
  denominator for all P&L%/grading. Max gain = net credit (only if pinned at body); expected
  outcome distribution is bimodal-ish: small wins near the body, full width−credit losses on
  shock prints.
- **1-lot account-blind distortion:** minimal - the published objects are per-unit straddle
  returns, so 1 fly per ticker per event is faithful. What IS distorted vs the literature: (a)
  wings truncate both the losses AND the measured premium relative to the published naked
  straddle numbers (section 6 magnitudes will NOT match ours - expect smaller); (b) ETF
  early-assignment tail the sources don't have (mitigated by row 18); (c) our 0–1 DTE
  concentration is the practitioner form, while the primary's premium is measured at 7–21 DTE - 
  the edge claim transfers directionally, not numerically.
- **Grading note:** log the ATM straddle mid at entry (the implied move) and the realized
  open-to-print-to-close path per event - the Rhoads implied-vs-realized scorecard is the
  fastest falsification signal for this family, ahead of P&L significance.

## 11. VERIFICATION

- **Verdict: CORRECTED** (adversarial verification pass, 2026-07-19, fresh context).
- **What was checked:** every SOURCE-VERBATIM / SOURCE-RANGE constant in sections 3, 4, 8 and
  every [verified-*] performance number in section 6 was searched for in its cited source.
  Primary (Londono & Samadi, IFDP 1376) and the Windmar thesis were downloaded as PDFs and
  text-extracted locally (WebFetch could not read the binary streams); Rhoads substack, both
  Option Alpha pages, Options Cafe, and the Olson 0DTE.COM plan were fetched and quote-checked;
  Fed 2025-01-29 press release and the 2026 FOMC calendar were fetched directly.
- **Verified verbatim in the primary:** abstract edge claim; "up to 7.5% more expensive"
  (PDF p. 4, introduction); 44–134 bps / 2.5%–7.5% (PDF p. 11); CPI/NFP 8:30 am + "8 routine FOMC meetings"
  (PDF pp. 7–8); Bloomberg calendar identification (p. 7); "7 to 21 calendar days ...
  (7 ≤ Tcaldays ≤ 21)" (PDF p. 8); 2.4% / 1.4% forward premia; "increased substantially
  starting in 2022 without a commensurate increase in market volatility"; "CPI releases are
  associated with larger risk premia during 2022" (PDF p. 20); sample Jan 2017–May 2023.
- **Verified in secondaries:** all Rhoads numbers (±0.64/±1.07, ±1.20/±0.84, ±0.98/±1.34,
  ±1.77/±1.13, 142.25→332.47, all three seller-got-hit quotes); Windmar table 5 sample-2
  (1 Jan 2024–1 Apr 2025) returns exactly as stated (CPI −5.15/t −5.12, −9.91/t −6.99; FOMC
  −5.60/t −3.99, −12.85/t −7.18; PPI −3.48; EMP +2.14/t 1.32), 270 DTE, median moneyness 1.11,
  16 CPI / 10 FOMC events, DeSimone relay verbatim (−1.86% / +2.6%, 2010–2014), author +
  seminar date 3 June 2025; Option Alpha FOMC piece ("15-30 mins before the FOMC announcement",
  2% vs 1.25%, 1.6% day-after, 66.7% lower, authors/dates); Option Alpha structure guide (both
  structure and assignment quotes verbatim); Options Cafe (431% title, 85% 2024 return on
  starting capital, −$5,472 2025, 77%/78% win rates, the win-rate quote, $6,000 sizing, 50%
  credit floor, 2x-credit stop, the "No FOMC, no CPI, no NFP" exclusion - all verbatim); Olson
  ($50 wings under $30 implied move, $10 increments, SPX 3150.47→3150 body, $1.50 target);
  2026 FOMC calendar dates (all 8 match federalreserve.gov); Seeking Alpha snippet (10-of-12,
  +450.04 points) corroborated by search snippet - full text still unread/paywalled, tag stands.
- **Corrections applied (all minor, none load-bearing):**
  1. Fed press-release quote was a paraphrase presented as verbatim - actual release line is
     "For release at 2:00 p.m. EST" (fixed in sections 1, 3, row 4; 14:00 ET constant stands).
  2. Option Alpha guide sentence subject is "Iron butterflies are typically sold
     at-the-money...", not "short straddles are..." (fixed in section 3 and row 13).
  3. Option Alpha FOMC heading is "0DTE Strategy"; the "(FOMC Announcement Day)" parenthetical
     was ours inside quote marks (fixed in section 3 and row 12).
  4. Windmar universe was mischaracterized as "S&P 500-linked" straddles - it is single-stock
     options on the 52 largest S&P 500 constituents (fixed in sections 2 and 6; the section 6
     numbers themselves were transcribed correctly).
- **Residual doubts:** primary page locators cite PDF pages (printed pages run ~1 lower) - 
  acceptable since the PDF is the cited object. DeSimone (2017) remains second-hand via
  Windmar (dissertation not fetched). The Seeking Alpha item remains snippet-level. Windmar's
  single-name, ~270-DTE universe makes it structurally distant support for a 0–1 DTE index-ETF
  fly - it corroborates the direction of the event premium, nothing more; the edge claim rests
  on the verified primary plus Rhoads/Option Alpha event-day statistics. No INVENTED constants
  were found; every ADAPTED/PLATFORM-POLICY/UNKNOWN tag was found honest as labeled.
