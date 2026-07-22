# Strategy Brief: gap_fade_bull_put

Researched 2026-07-19. Primary source READ IN FULL (the 2011 Dow Award paper PDF from the CMT
Association); secondary sources read as noted. The provenance hint "Connors Research gap studies"
resolved to an ebook whose rules I could NOT read - it is recorded honestly below as provenance
color, and NO constant in this brief is attributed to it. The options expression is ENTIRELY
ADAPTED (loudly documented in §2): every published source trades the underlying (stocks, SPY, ES
futures), never options.

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `gap_fade_bull_put`
- **Provenance class:** practitioner (Dow-Award practitioner research + practitioner gap-fade
  statistics; the companion book is textbook-grade)
- **PRIMARY citation:** Julie R. Dahlquist, Ph.D., CMT & Richard J. Bauer, Jr., Ph.D., CFA, CMT,
  **"Analyzing Gaps for Profitable Trading Strategies"**, Market Technicians Association 2011
  Charles H. Dow Award winning paper.
  - URL (official, read in full, all 21 pages): https://docs.cmtassociation.org/pdfs/2011-dowaward.pdf
  - Relevant sections: "Data and Methodology"; "Gap Downs" (Tables 9–16).
  - Companion book (same authors/data program, identity verified via publisher sample pages, body
    NOT read): *Technical Analysis of Gaps: Identifying Profitable Gaps for Trading*, FT Press /
    Pearson, June 2012, ISBN 978-0-13-290043-0 - esp. Ch. 9 "Closing the Gap" (pp. 205–217) per
    the sample's table of contents.
- **INDEPENDENT secondary sources:**
  1. MyPivots, **"Fading the Gap"** - https://www.mypivots.com/article/details/43/fading-the-gap
     (read; ES-futures opening-gap fill statistics, 2002–2004 sample; author unnamed).
  2. Cory Mitchell, CMT, **"S&P 500 (SPY) Gap Fill Strategy and Statistics"**, TradeThatSwing - 
     https://tradethatswing.com/sp-500-spy-es-gap-fill-strategy-and-statistics/
     (read via mirror; SPY gap-fill probabilities by gap size + an explicit intraday fade rule set;
     original analysis dated 2025-08-14, updated 2026-03-03).
  3. Provenance color ONLY (rules unread): Connors / Alvarez / Connors Research / Radtke,
     *Stock Gap Trading Strategies That Work* (Connors Research Trading Strategy Series), Connors
     Research, Oct 7 2013 - https://www.amazon.com/Trading-Strategies-Connors-Research-Strategy-ebook/dp/B00FPSRJL0
- **Publication dates:** paper May 2011 (award) - data 2006–2010; book June 2012; MyPivots article
  undated (data window Jan-2002→Feb-2004); TradeThatSwing 2025-08-14 / 2026-03-03; Connors ebook
  2013-10-07.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**What the sources trade:**
- Dahlquist & Bauer (primary): individual **Russell 3000 stocks** - "we consider stocks included
  in the Russell 3000 between January 1, 2006 and December 31, 2010", with a liquidity filter of
  "a trading volume of over 1 million shares on the gap day and the four prior trading days"
  (paper, Data and Methodology + footnote 1). Long/short THE STOCK; entries at Day-1 open, exits
  at close of the horizon day.
- MyPivots (secondary): the **S&P 500 e-mini (ES)** futures contract, fading the RTH opening gap.
- TradeThatSwing (secondary): **SPY** shares, intraday gap-fill day trade.

**Our mapping:** SPY / QQQ / IWM plus the liquid mega-cap tier AAPL / NVDA / MSFT / TSLA / AMD /
META. The index-ETF tier maps directly onto the ES/SPY fade statistics; the mega-cap tier maps
onto the primary paper's single-stock evidence (all nine tickers trivially clear the paper's
">1 million shares" liquidity filter).

**LOUD ADAPTATION NOTICE - the options expression is entirely OURS.** Every published form buys
(or shorts) the underlying. This platform is options-only (no stock legs, no delta-hedging), so
the bullish gap-fade thesis - "a moderate opening gap down tends to fill upward, and gap-down
stocks are net positive by Day 5" - is expressed as a **defined-risk bull put spread** (short put
+ lower long put) opened after the gap-down morning confirms, 0–5 DTE. NOTHING about the option
legs (strikes, delta, width, credit, DTE) is published anywhere in the cited sources; all such
constants are tagged ADAPTED or PLATFORM-POLICY in §8 and must never be quoted as
Dahlquist/Bauer/Mitchell/Connors values. What is preserved: the trigger (moderate opening gap
down), the size band that predicts a fill, the confirmation entry, the gap-fill profit objective,
and the ≤5-session horizon (primary paper: gap-down stocks average positive by Day 5). What is
distorted: payoff is capped at the credit; a fill beyond the prior close pays no more; path/IV
marks can hurt mid-hold even when the fade thesis ends correct.

**Two gap definitions exist in the sources - do not conflate them (this brief uses the OPENING
gap).** The primary paper's gap is the full bar-chart gap: "A gap down occurs when today's high
is lower than yesterday's low." The fade statistics we trigger on use the opening gap: "A measure
from the close of the previous trading session to the opening price of the following trading
session's Regular Trading Hours (RTH)" (MyPivots). Our trigger is the OPENING-gap definition
(open vs. prior RTH close); the primary paper is used for the multi-day horizon evidence and the
liquidity/volume/MA context, not the trigger arithmetic.

## 3. EXACT ENTRY RULES

Underlying-signal rules (published, with quotes):

1. **Trigger - opening gap down:** today's 09:30 ET RTH open is below yesterday's RTH close.
   Source definition (MyPivots): a gap is "a measure from the close of the previous trading
   session to the opening price of the following trading session's Regular Trading Hours (RTH).
   RTH is from 09:30 to 16:15 EST."
2. **Gap-size band (the fade-probability gate):** TradeThatSwing publishes SPY gap-down fill
   probabilities by size bucket: gaps of "0-0.19%" filled 92% (Aug-2025 sample) / 88% (Mar-2026
   sample); "0.2% to 0.39%" filled 69% / 79%; ">0.4%" filled below 50% / 36%. MyPivots (ES,
   points): 1/2/3-point gaps filled 93%/90%/82% (fill-rate table); extreme-range gaps - a gap
   larger than the prior day's entire range - filled only 6 of 17 = 35%. → We trade the band **0.20% ≤ gap ≤ 0.40%** (SOURCE-RANGE upper bound: the >0.4% bucket
   is the published fade-failure zone; ADAPTED lower bound: sub-0.2% gaps fill most often but
   offer no premium - see §8 rows 3–4).
3. **Entry confirmation + timing:** TradeThatSwing rule set (quoted from the article's rules):
   entry waits for "breakout of the opening 15-minute range" following a gap down; timing
   context: "80%+ of gaps fill by noon EST." → We require the underlying to break ABOVE the
   09:30–09:45 ET opening range high, and we enter at the first options mark after that breakout,
   no later than the ADAPTED cutoff 11:30 ET (past midday the published fill odds are mostly
   spent).
4. **Day-of-week (advisory covariate, NOT a gate):** MyPivots: overall "on average 76% or three
   quarters of all gaps close at some point during RTH"; by day of week Thursday highest at 82%,
   Monday lowest at 65%. Logged for the grader; no published source gates on it, so neither do we.
5. **Regime / IV gate:** NONE PUBLISHED in any cited source. (The primary paper's Table 15/16
   context - gap downs occurring above the 30/90-day moving average "tend to outperform the
   market by over 1.3% over the next 20 days" - is logged as a covariate, not gated on.) VIX
   percentile logged observe-only, PLATFORM-POLICY.
6. **Multi-day context from the primary (why holding past day 0 is defensible):** Table 9 of the
   paper - gap-down stocks average −0.159% on Day 1 and −0.300% by Day 3, but **+0.455% by Day 5**
   and +1.412% by Day 20; the paper: "The positive 5-day and 20-day price movements for the gap
   down stocks suggests that the downward stock price movement is short lived." Also: "Down gaps
   occurring on light volume tend to reverse trend quickly; a long position should be taken in
   these stocks" (Tables 12–13: below-30-day-average-volume down gaps: 5-day +1.025%, 20-day
   +3.200%). Relative volume at entry time is unknowable intraday for the full session - logged
   as a covariate using volume-so-far vs. same-time average, ADAPTED, not gated.

Option-leg construction (ALL ADAPTED - no published values exist; §8 rows 8–13):

- Structure: **bull put spread**, 1 spread: sell 1 put, buy 1 further-OTM put, same expiry.
- Short strike: at or below the session's opening-range LOW (i.e., below the morning's low print,
  so an ordinary fill-and-hold day never threatens the strike), nearest listed strike; delta
  ceiling ≈ 0.35.
- Long strike: 1–2 strikes below the short (width per underlying's strike grid).
- Expiry: nearest listed expiration with **0–5 calendar DTE** (0DTE allowed on index ETFs when
  the gap day itself has an expiration; single names use the nearest weekly ≤5 DTE).
- Liquidity gates (OI, max spread %, quote presence): platform-standard, PLATFORM-POLICY.
- Earnings gate (single names): skip if earnings fall between entry and expiry, PLATFORM-POLICY - 
  the published statistics are event-blind, and earnings gaps are the canonical
  breakaway-not-common gap.

## 4. EXACT EXIT RULES (override platform exit doctrine for this strategy)

1. **Profit objective - the gap fill:** published target (TradeThatSwing rule): "prior day's
   close." → Shadow mapping (ADAPTED): when the underlying trades at/above the prior session's
   RTH close after entry, close the spread at the next mark. Statistical basis: MyPivots - 76%
   of all ES gaps "close at some point during RTH"; TradeThatSwing - "80%+ of gaps fill by noon
   EST."
2. **Stop - the published fade stop, mapped:** TradeThatSwing places the stop "at 75% of the
   opening range" (stock day-trade form). → Shadow mapping (ADAPTED): if, after entry, the
   underlying trades back BELOW the opening-range low (our short-strike shelf; the published 75%
   level rounded to the range boundary we can mark cleanly), close the spread at the next mark.
   This is the fade-thesis-dead exit.
3. **Time exit / hold-to-expiry:** if neither (1) nor (2) triggers, HOLD; if the short strike is
   OTM at 15:30 ET on expiration day, let the spread expire worthless (max profit). If any leg is
   ITM or within 0.25% of spot at 15:30 ET on expiration day, force-close at the mark (no
   assignment path on a shadow platform), ADAPTED. The ≤5-session cap is consistent with the
   primary's horizon evidence (Day-5 average +0.455%, Table 9 [verified-primary]); no cited
   source publishes an options time exit.
4. **Roll rules:** none published anywhere; we do NOT roll. A new trade requires a fresh
   qualifying gap.
5. **Half-gap note (recorded, not implemented):** MyPivots (table figure): for gaps over 2
   points, half the gap closed 80% of the time (282/351) - a half-gap variant exists in the source but is NOT our
   default; recorded so nobody later "remembers" it as our rule.

## 5. SIZING CONVENTION IN SOURCE

- Primary paper: per-stock percentage returns on one unit of stock, equal-treatment across
  signals; no capital allocation scheme, no leverage, no options.
- MyPivots: implicitly one ES contract ("just over 2 ticks of profit on average per trade/day").
- TradeThatSwing: retail stock day-trade, size unspecified.
- Connors ebook: UNKNOWN (rules/sizing unread).
Our shadow runs **1 bull put spread per signal, account-blind** (platform convention); CaR basis
in §10.

## 6. DOCUMENTED PERFORMANCE

All published numbers are for UNDERLYING forms (stock/ES/SPY-shares). There is NO published
performance for the bull-put-spread expression - that is what this shadow lane measures.

Primary (Dahlquist & Bauer 2011; Russell 3000, 2006-01-01→2010-12-31, 17,435 gap downs; returns
measured from Day-1 open; all values percent):
- Gap-down all: 1-day −0.159, 3-day −0.300, **5-day +0.455**, 20-day +1.412; market-adjusted
  1-day −0.132, 3-day −0.012, 5-day +0.178, 20-day +0.829 (Table 9). **[verified-primary]**
- Below-3-day-average-volume down gaps: 3-day +0.316, 5-day +1.123, 20-day +3.073 (Table 12);
  below-30-day-average-volume: 5-day +1.025, 20-day +3.200 (Table 13). **[verified-primary]**
- Down gaps above the 30-day MA: 1-day +0.085, 3-day +0.440, 20-day mkt-adj +1.358 (Table 15);
  "outperform the market by over 1.3% over the next 20 days." **[verified-primary]**
- Caveat the paper itself forces: at the 1–3-day horizon the AVERAGE gap-down stock keeps
  falling ("going short the day after a gap down" is the paper's short-horizon suggestion) - the
  bull thesis is an intraday-fill + ≥5-day phenomenon, not a day-1 average phenomenon.
  **[verified-primary]**
- Methodology caveats: 2006–2010 sample brackets the GFC; no transaction costs modeled in the
  tables; full-gap (not opening-gap) definition; stock universe, not ETFs.

Secondary (MyPivots, ES daily RTH data 2002-01-15→2004-02-20, 529 trading days / 528 gaps):
- "On average 76% ... of all gaps close at some point during RTH"; Thursday 82%, Monday 65%;
  1/2/3-point gaps fill 93%/90%/82%; extreme-range gaps (gap larger than the prior day's range)
  fill 6/17 = 35%; (>15-point gaps: only 12 in-sample, and fading all of them WITHOUT stops
  totaled +21.25 points - small-N, NOT a fade-failure statistic); half-gap closure 80% for gaps
  >2 points;
  raw fade P&L "just over 2 ticks of profit on average per trade/day." **[verified-secondary]**
- Caveats: 2002–2004 microstructure; points not percent; no costs beyond a commissions note.

Secondary (TradeThatSwing / Cory Mitchell, SPY, rolling 6-month samples):
- Gap-down fill rates: 0–0.19% → 92% (2025-08) / 88% (2026-03); 0.2–0.39% → 69% / 79%; >0.4% →
  below 50% / 36%. **[verified-secondary]**
- Caveats: 6-month windows only (regime-sensitive), no P&L distribution published.

Provenance color (Connors Research ebook, product description only - rules and tables UNREAD):
- Claims of "correct greater than 68% of the time" and "average gain per trade ... up to 6.25%
  per trade since 2001." **[verified-secondary]** as marketing claims ONLY - methodology unread;
  build NOTHING on these numbers.
- CAGR / profit factor / max drawdown: **UNKNOWN** - no cited source publishes them for any form
  of this strategy.
- A widely-circulated fade band "gap down between −0.15% and −0.6%" (QuantifiedStrategies)
  appeared only in search snippets; the page sat behind bot verification on every fetch attempt:
  **[unverified]** - recorded so it is never promoted to a rule without being read.

## 7. KNOWN FAILURE MODES

- **Breakaway/news gaps do not fill (structural, the big one):** the fade's published edge dies
  precisely when the gap is informational. Both secondaries show fill probability collapsing with
  size (>0.4% SPY → ≤36–50%; ES extreme-range gaps → 35%); the primary paper shows the AVERAGE gap-down
  stock still falling at Days 1–3. The size band is the main defense; it is probabilistic, not a
  guarantee.
- **Trend-day-down regimes:** clustered gap-downs that never fill (Aug-2011 debt-ceiling week,
  Feb-2018 Volmageddon 2/5–2/8, Mar-2020 COVID cascade, Aug-5-2024 yen-carry spike). A morning
  15-min-range breakout can print and then fail on the same day the market makes a −3% trend day;
  the short put goes deep ITM fast. Defined-risk width caps the damage (max loss = width −
  credit) but the e-process will see full-width losers in these regimes.
- **Signal correlation:** SPY/QQQ/IWM (and the mega-caps) gap together; a morning that fires all
  nine is ONE bet on "the open was an overreaction," not nine independent trades.
- **Gap-through-strikes at the single-name tier:** an earnings or guidance gap in NVDA/TSLA can
  open below BOTH strikes - instant near-max loss with no path. Earnings gate (PLATFORM-POLICY)
  removes the scheduled cases; unscheduled news remains.
- **Early assignment (structural, American-style short leg):** a short put driven ITM near
  ex-dividend/expiry can be assigned early in the real world; shadow platform closes ITM-risk
  positions at 15:30 ET on expiry day instead (§4.3) - a real-world implementation would need the
  assignment desk-check.
- **0DTE gamma:** at 0–1 DTE the short strike sits one air-pocket from ITM; marks whip violently
  into the close. This is the cost of the premium richness at the short end of the band.
- **Sample-era caveats:** primary data 2006–2010 (GFC-heavy); MyPivots 2002–2004; TTS windows are
  6 months. Nothing here is a 2020s full-cycle backtest of the assembled rule set - that is what
  the shadow ledger will produce.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | gap_definition | opening gap: 09:30 ET RTH open vs prior session RTH close | SOURCE-VERBATIM | MyPivots: "a measure from the close of the previous trading session to the opening price of the following trading session's Regular Trading Hours (RTH)" |
| 2 | gap_direction | down (open < prior RTH close) | SOURCE-VERBATIM | fade-the-gap long side; TTS gap-down fill tables; primary "gap down" defined Data/Methodology |
| 3 | gap_min_pct | 0.20% | ADAPTED | TTS buckets "0-0.19%" vs "0.2% to 0.39%": sub-0.2% gaps fill most often (88–92%) but carry no fadeable premium; lower bound is OURS at the published bucket boundary |
| 4 | gap_max_pct | 0.40% | SOURCE-RANGE | TTS: ">0.4%" gap-downs filled "below 50%" / 36% - published fade-failure zone; band 0.2–0.4% has published fills 69–79% |
| 5 | opening_range_minutes | 15 (09:30–09:45 ET) | SOURCE-VERBATIM | TTS entry: "breakout of the opening 15-minute range" |
| 6 | entry_confirmation | underlying breaks above opening-range high | SOURCE-VERBATIM | TTS rule 1 (mapped from stock day-trade to spread entry timing) |
| 7 | entry_cutoff | 11:30 ET | ADAPTED | derived from TTS "80%+ of gaps fill by noon EST" - after midday the published fill odds are mostly spent; exact cutoff is OURS |
| 8 | option_structure | bull put spread (1 short put + 1 long lower put), 1 spread | ADAPTED | options-only platform; no source trades options |
| 9 | short_strike_rule | nearest strike at/below the session opening-range low | ADAPTED | strike shelf placed below the morning low so a fill-and-hold day never touches it; no published analog |
| 10 | short_strike_delta_cap | 0.35 max (typical 0.20–0.35 band) | PLATFORM-POLICY | no published value; ours, to keep the short leg meaningfully OTM |
| 11 | spread_width | 1–2 strikes (≈$1 IWM … $5 NVDA-class), per strike grid | PLATFORM-POLICY | no published value; defined-risk cap is ours |
| 12 | credit_floor | ≥15% of width, else no trade | PLATFORM-POLICY | no published value; ours, to refuse premium-dead entries |
| 13 | dte_band | 0–5 calendar DTE (0DTE only where listed; single names nearest weekly ≤5) | ADAPTED | horizon built from published evidence: intraday fill stats (MyPivots/TTS) + primary Table 9 Day-5 +0.455%; no source publishes an options DTE |
| 14 | profit_target | underlying touches prior-day RTH close (gap filled) → close spread at next mark | SOURCE-VERBATIM + ADAPTED mapping | TTS: "Target: prior day's close"; spread-closing mechanics ours |
| 15 | stop_rule | underlying trades back below opening-range low → close spread at next mark | SOURCE-VERBATIM + ADAPTED mapping | TTS: stop "at 75% of the opening range"; we mark the range boundary (cleanly markable) - mapping is OURS |
| 16 | expiry_doctrine | OTM at 15:30 ET expiry day → expire worthless; ITM/within 0.25% of spot → force-close at mark | ADAPTED | shadow platform cannot take assignment; no published options doctrine exists |
| 17 | roll_rule | none - never roll | ADAPTED | no source publishes rolls; re-entry requires a fresh qualifying gap |
| 18 | half_gap_variant | recorded only, NOT implemented | SOURCE-RANGE | MyPivots table: gaps >2 pts half-closed 282/351 = 80% - variant exists in source; not our rule |
| 19 | dow_covariate | log day-of-week; no gate | SOURCE-VERBATIM | MyPivots: Thursday 82% vs Monday 65% fill; advisory only |
| 20 | rel_volume_covariate | log volume-so-far vs same-time average; no gate | SOURCE-VERBATIM (finding) + ADAPTED (measure) | primary: "Down gaps occurring on light volume tend to reverse trend quickly; a long position should be taken" - full-session volume unknowable at entry; intraday proxy is ours |
| 21 | ma_position_covariate | log open vs 30-day MA; no gate | SOURCE-VERBATIM (finding) | primary Tables 15–16: above-30/90-day-MA down gaps "outperform the market by over 1.3% over the next 20 days" |
| 22 | earnings_gate | single names: skip if earnings ≤ expiry | PLATFORM-POLICY | published stats are event-blind; ours (breakaway-gap defense) |
| 23 | event_dates_logging | FOMC/CPI morning flagged, log-only (no published gate) | PLATFORM-POLICY | no source gates on macro events |
| 24 | liquidity_gates | platform-standard OI / max-spread% / quote presence | PLATFORM-POLICY | echoes primary's stock filter "trading volume of over 1 million shares on the gap day and the four prior trading days" (footnote 1) - options-chain gates are ours |
| 25 | position_size | 1 spread, account-blind | PLATFORM-POLICY | shadow convention; source sizing in §5 |
| 26 | vix_iv_gate | none (VIX percentile logged observe-only) | PLATFORM-POLICY | no published IV/VIX gate in any cited source |

UNKNOWN constants (recorded honestly - no invented values):
- **published_options_parameters** - delta, width, credit, DTE, option exits: DO NOT EXIST in any
  cited source; every option-leg value above is ADAPTED/PLATFORM-POLICY and must never be
  attributed to the cited authors.
- **connors_ebook_exact_rules** - *Stock Gap Trading Strategies That Work* (2013) rules/tables
  unread (paywalled ebook); only its marketing claims are recorded (§6). UNKNOWN.
- **qs_fade_band** - the "−0.15% to −0.6% go long at the open" band attributed to
  QuantifiedStrategies: seen only in search snippets, page bot-blocked on every fetch → UNKNOWN /
  [unverified]; not used.
- **published_profit_target_pct_of_credit** - no source states a %-of-credit take-profit. UNKNOWN.
- **single_name_gap_band** - TTS band is SPY-only; no published per-name band exists. We apply
  the same 0.2–0.4% band to the mega-caps (ADAPTED); expect sparse qualification (their typical
  gaps run larger).
- **book_ch9_gap_fill_timing** - the primary book's Ch. 9 "Closing the Gap" timing tables
  (pp. 206–216) were not accessible; only the paper was read. UNKNOWN.

## 9. DATA REQUIREMENTS

- **Daily history:** prior RTH close per underlying (gap arithmetic) + ≥100 trading days for the
  30-day MA covariate (row 21) and volume averages (row 20).
- **1-min bars:** REQUIRED - opening-range construction (09:30–09:45 ET), breakout confirmation,
  gap-fill touch detection (row 14), stop-touch detection (row 15). Intraday cache
  (runtime/intraday_cache) covers backfill.
- **Tradier chains:** DTE band 0–7 calendar days (selection targets 0–5; the extra margin covers
  strike hunting on Fridays/holidays). Puts only, both legs.
- **Earnings calendar (date + bmo/amc):** required for the six single names (row 22). Not needed
  for SPY/QQQ/IWM.
- **FOMC/CPI dates:** log-only flag (row 23).
- **VIX regime / IV rank:** log-only covariate (row 26). IV-rank archive is cold → use the
  platform's VIX-percentile fallback.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month (drives grading timeline):** ESTIMATE, not measured: SPY gap-downs in
  the 0.2–0.39% bucket appear a handful of times per month in the TTS samples; with confirmation
  (row 6) filtering some out, figure ~2–3/mo each on SPY/QQQ/IWM and ~0.5–1/mo each on the six
  mega-caps (their gaps usually overshoot the 0.4% cap) → **≈8–12/month, call it 10**. At N≥25
  per lane, first verdicts in ~10–12 weeks. Correlated-morning clustering means effective
  independent observations accrue slower than the raw count (§7).
- **Mark cadence:** 1-min underlying bars through the entry session (range breakout, fill touch,
  stop touch are all intraday events); options marks at platform cadence, plus a mandatory
  15:30 ET expiry-day mark for the row-16 doctrine. Multi-day holds (1–5 DTE) revert to standard
  cadence after day 0.
- **Multi-leg shape:** 2-leg vertical (short put + long put, same expiry), credit opening, both
  legs closed together always (no legging). Three-fill ledger convention applies per leg; WORST
  grades will punish stressed morning spreads - expected.
- **Capital-at-risk basis:** **width − credit** (defined-risk max loss of the credit vertical).
  Not Reg-T CaR proxy, not debit paid.
- **Account-blind 1-lot distortion:** the published stock forms scale P&L linearly with gap size
  and share count; a 1-lot spread caps profit at the credit regardless of how far past the fill
  level the underlying travels, and converts the sources' continuous stock stop into a discrete
  spread mark. Win RATE should track the published fill statistics; win MAGNITUDE will not track
  the published per-trade returns - grade this lane on its own credit-based expectancy, never
  against §6's stock numbers.
- **Doctrine override reminder:** §4 exits OVERRIDE the platform exit ladder for this strategy - 
  notably hold-to-expiry when OTM (row 16) and the thesis-dead stop (row 15). No platform
  noise-reclaim/persistence logic applies inside this lane.

## 11. VERIFICATION

**Verdict: CONFIRMED** - independent adversarial fresh-context verification pass, 2026-07-19.

**Process note:** this brief arrived already carrying a §11 claiming verdict CORRECTED (a prior
pass that says it fixed a MyPivots 35%-attribution error). That pre-existing section was NOT
trusted; every source was re-fetched and every tagged constant re-located from scratch. The
prior section's content is superseded by the record below (its one overreach - asserting both
TTS snapshots were "taken in uptrends per the article itself" when the article states the
uptrend regime only for the original Aug-2025 window - is dropped). The brief BODY (§1–§10)
required NO edits in this pass: as it stands, every checked claim is supported.

**What was checked (every source independently re-fetched 2026-07-19):**
- **Primary (Dahlquist & Bauer 2011):** official CMT PDF downloaded
  (docs.cmtassociation.org/pdfs/2011-dowaward.pdf), 21 pages, full text extracted locally.
  VERIFIED VERBATIM/EXACT: gap-down definition ("A gap down occurs when today's high is lower
  than yesterday's low"); Russell 3000, 2006-01-01→2010-12-31; 17,435 gap downs; footnote-1
  liquidity filter ("a trading volume of over 1 million shares on the gap day and the four
  prior trading days"); return convention Day-1 open → horizon close; Table 9 All column
  (−0.159 / −0.300 / +0.455 / +1.412; mkt-adj −0.132 / −0.012 / +0.178 / +0.829); Table 12
  below-avg-volume totals (+0.316 / +1.123 / +3.073); Table 13 (+1.025 / +3.200); Table 15
  above-30-day-MA All (1-day +0.085, 3-day +0.440, 20-day mkt-adj +1.358); the "short lived",
  "light volume … a long position should be taken", "outperform the market by over 1.3% over
  the next 20 days", and "going short the day after a gap down" quotes. Every
  [verified-primary] tag in §6 held. No number in the brief deviates from the paper.
- **MyPivots "Fading the Gap":** fetched live. VERIFIED: gap/RTH definitions verbatim (incl.
  "RTH is from 09:30 to 16:15 EST"); ES, 2002-01-15→2004-02-20, 529 days / 528 gaps; 76%
  overall; Thursday 82% (highest) / Monday 65% (lowest); 1/2/3-point fills 93% (71/76) / 90%
  (78/87) / 82% (61/74); extreme-range gaps 6 of 17 = 35%; >15-point gaps: 12, faded without
  stops totaling +21.25 points (the brief's attribution of 35% to extreme-range - not
  >15-point - gaps is CORRECT as written); half-gap 80% (282/351, gaps >2 points); "just over
  2 ticks of profit on average per trade/day". Every [verified-secondary] MyPivots tag held.
- **TradeThatSwing (Cory Mitchell, CMT):** WebFetch 403; full live article retrieved via
  browser. VERIFIED: gap-down fill buckets 0–0.19% → 92% (orig.) / 88% (update); 0.2–0.39% →
  69% / 79%; >0.4% → "below 50%" / 36%; original date August 14 2025 and update March 3 2026
  both stated in the article; "wait for a breakout of the opening 15-minute range"; "Place a
  stop loss at 75% of the opening range"; "The target is the prior day's close"; "80%+ of
  gaps fill by noon EST"; 6-month sample windows. Every [verified-secondary] TTS tag held.
  Regime caveat: the article flags the ORIGINAL window as an uptrend; the Mar-2026 update
  does not state its regime.
- **Connors ebook (Amazon product page):** VERIFIED verbatim: "correct greater than 68% of
  the time"; "averaged up to 6.25% per trade since 2001"; authors Connors / Alvarez / Connors
  Research / Radtke; pub date October 7, 2013. The brief's quarantine (marketing color only,
  rules UNREAD, "build NOTHING on these numbers") is accurate and preserved.
- **Companion book identity:** *Technical Analysis of Gaps* (Dahlquist & Bauer), FT Press,
  June 2012, ISBN 978-0-13-290043-0 confirmed via AbeBooks/Pearson listings. Body remains
  unread - correctly UNKNOWN in §8.
- **Tag audit (§3/§4/§8):** all SOURCE-VERBATIM quotes located verbatim; both SOURCE-RANGE
  rows (4, 18) match the published tables; every ADAPTED row states a real adaptation
  rationale; every option-leg constant (structure, strikes, delta cap, width, credit floor,
  DTE, expiry doctrine, roll rule) is ADAPTED/PLATFORM-POLICY with an explicit
  no-published-analog statement - nothing adapted is presented as published.
  **NO INVENTED CONSTANTS FOUND.**

**Residual doubts:** (1) Companion book Ch. 9 and the Connors rules remain unread - nothing
in the brief rests on them (correctly UNKNOWN). (2) The QuantifiedStrategies band stays
[unverified] and quarantined; the page was not re-attempted this pass. (3) The award month
"May 2011" in §1 is unverified (the paper header says only "2011 Charles H. Dow Award
Winner") - cosmetic, no constant depends on it. (4) TTS statistics are 6-month-window,
regime-sensitive snapshots from an uptrend (original window explicitly; update regime
unstated) - §6/§7 already carry this caveat. (5) The strategy's edge claim rests on the
sources as characterized: an intraday fill tendency (secondaries) plus a ≥5-day mean-reversion
average (primary); the primary also shows Days 1–3 NEGATIVE on average, which the brief
states loudly rather than hiding - the options expression's profitability is correctly framed
as unmeasured and to-be-established by the shadow ledger.
