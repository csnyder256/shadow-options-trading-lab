# Strategy Brief: pre_fomc_drift_call

Pre-FOMC announcement drift, expressed as a long ATM call held ~24 hours into the scheduled
FOMC statement release. Researched 2026-07-19. Primary and secondary sources were READ in
full-text (FRBNY Staff Report 512 PDF; Kurov/Wolfe/Gilbert working-paper PDF), not recalled
from memory. Every constant below carries a tag; UNKNOWN means the literature does not
publish a value.

> **LOUD ADAPTATION WARNING (read section 2):** the published strategy holds the **index
> itself** (delta-one SPX spot / E-mini futures). It is NOT an options strategy in the
> source. The long ATM call is entirely our options-only platform's adaptation. Every
> option-leg constant (strike, delta, DTE) is ADAPTED or PLATFORM-POLICY - none of them
> has published authority.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `pre_fomc_drift_call`
- **Provenance class:** academic
- **PRIMARY citation:**
  - Lucca, David O. and Emanuel Moench, *"The Pre-FOMC Announcement Drift"*, Federal
    Reserve Bank of New York Staff Reports, no. 512, September 2011, revised August 2013.
    PDF: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr512.pdf
    (landing page: https://www.newyorkfed.org/research/staff_reports/sr512.html)
  - Journal of record: Lucca, D.O. and Moench, E. (2015), "The Pre-FOMC Announcement
    Drift", **The Journal of Finance**, 70(1), 329–371.
    https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12196
  - The staff-report full text is what was read for this brief (63 pp.); the JF 2015
    version is the peer-reviewed publication of the same paper.
- **INDEPENDENT secondary source (read in full text):**
  - Kurov, Alexander, Marketa Halova Wolfe, and Thomas Gilbert, *"The Disappearing
    Pre-FOMC Announcement Drift"*, Finance Research Letters 40 (2021), 101781. Working
    paper draft dated September 14, 2020 ("Finance Research Letters (Forthcoming)"), read at
    https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf
    Open-access published version: https://pmc.ncbi.nlm.nih.gov/articles/PMC7525326/
    SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3134546
- **Additional references cited within the secondary (not independently read):** Boguth,
  Grégoire, Martineau (2019) ["BGM"] on press-conference dependence; Ben Dor & Rosa
  (2019, The Journal of Fixed Income 28(4), 60–72) finding no drift April 2011–December 2017.
- **Publication dates:** staff report September 2011 (rev. August 2013); Journal of
  Finance January 2015; attenuation paper 2020/2021.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**What the source trades.** The S&P 500 **index itself** - cash index (SPX) in Lucca–Moench
(LM), E-mini S&P 500 futures in Kurov et al.: "the black solid line ... represents the mean
point-wise cumulative intraday percentage return of the S&P500 index (SPX henceforth)" (LM
§3.1); "We use intraday E-mini S&P 500 nearby contract futures prices" (Kurov §2, who note
"LM use the spot index and note that the futures returns are almost identical"). The
published trading strategy is a **delta-one index switch**: "The simple strategy that
consists in buying the SPX at 2 pm the day before a scheduled FOMC announcement, selling
fifteen minutes before the announcement and holding cash on all other days" (LM §3.1).

**Our mapping.** Options-only platform, no index/futures/stock legs allowed. We express the
long delta with a **1-lot long ATM call on SPY** (primary), optionally QQQ and IWM as
secondary underlyings. Mega-cap single names (AAPL/NVDA/MSFT/TSLA/AMD/META) are **excluded
by default**: the documented effect is a market-level drift; LM show it is "broad-based
across U.S. industry and size portfolios" (LM §1), which supports broad index ETFs
(SPY/QQQ/IWM) but says nothing about single names, whose idiosyncratic vol (tens of bp/day)
would swamp a ~49bp market drift and destroy the grading signal.

**Why the mapping (partially) preserves the edge claim - and where it does not:**
- Preserved: SPY tracks SPX; the drift is a directional underlying move, and a long call
  holds positive delta over the identical window. QQQ/IWM are defensible because the drift
  is broad-based across size portfolios and "Other major foreign stock markets exhibit
  similarly large and significant pre-FOMC returns" (LM §1) - the effect is not SPX-specific.
- **NOT preserved (loud):** an ATM call is delta ≈ 0.5, short ~1 day of theta, and long
  vega. LM explicitly document that "realized volatility and trading volume are **lower** in
  the hours before FOMC announcements compared to other days" (LM §1) - i.e., the pre-FOMC
  window is a LOW-realized-vol window, the worst environment for paying theta. A ~49bp
  underlying drift × 0.5 delta must beat ~24h of theta plus spread; under the post-2015
  attenuated drift (~9bp, see §6) the option form is likely negative-EV even where the
  index form is marginally positive. This is a structural adaptation cost, not a source
  claim. The shadow exists to measure exactly this.

## 3. EXACT ENTRY RULES

The source publishes a **time window**, not a signal - entry is unconditional on every
scheduled FOMC announcement.

- **Trigger:** a scheduled FOMC meeting with a statement release. "These FOMC meetings have
  taken place eight times per year since the early 1980s" (LM §1). Unscheduled/intermeeting
  announcements are NOT in the tested set (LM exclude them; §2 lists unscheduled dates
  separately). SOURCE-VERBATIM.
- **Entry timing (published):** "buying the SPX at 2 pm the day before a scheduled FOMC
  announcement" (LM §3.1). The measured window: "the 24-hour period from 2 pm on the day
  before a scheduled FOMC announcement until 2 pm on the day of a scheduled FOMC
  announcement, or about fifteen minutes before the announcement release time" (LM §2).
  In LM's sample the release was "at, or a few minutes after, 2:15 pm" (LM §2), so the
  window is **[announcement − 24h15m, announcement − 15m]**.
- **Entry timing (modern clock, ADAPTED):** statements have been released "at 2:00 pm since
  March 2013" (Kurov §2). Preserving LM's structure relative to the release time: **enter
  13:45 ET on T−1, exit 13:45 ET on announcement day T**. Kurov et al. define the
  announcement-day return as "the return in 24 hours ending 15 minutes before the
  announcement" and use the "1:45 pm-to-1:45 pm window" as the matching post-April-2011
  non-announcement benchmark (Kurov §2) - identical clocks for a 14:00 ET release. Verify the
  scheduled release time per meeting; if it is not 14:00 ET, shift the window to
  [release − 24h15m, release − 15m].
- **Alternative published window start (SOURCE-RANGE):** BGM/Kurov find "the drift begins
  at the stock market open of the previous day" (Kurov §1) and Kurov's Table 2 measures
  "from the stock market open on the day before the announcement to 15 minutes before the
  announcement" (Kurov §3). Documented range for window start: {previous-day 14:00 ET (LM,
  our default), previous-day 09:30 ET (BGM/Kurov)}.
- **Strike selection:** UNKNOWN in source (no options are traded). Our rule: nearest listed
  strike to spot at entry (ATM, delta ≈ 0.50). ADAPTED.
- **DTE selection:** UNKNOWN in source. Our rule: nearest listed expiration strictly AFTER
  the announcement day (never expiring before our exit), typically 1–7 DTE on SPY/QQQ/IWM
  dailies/weeklies. ADAPTED.
- **Published regime / IV gate:** none is part of the traded strategy. LM document
  conditioning **associations** only: "Pre-FOMC returns are higher in periods when the
  slope of the Treasury yield curve is low, implied equity market volatility is high, and
  when past pre-FOMC returns have been high" (LM Abstract). Specifically "the VIX is
  strongly significant with a coefficient of 0.31 in the 1994-2011 sample" using "the VIX
  at the market close two days before scheduled meetings" (LM §4), and the trailing mean of
  the "past eight FOMC meetings (a variable that we label MA8)" is "highly statistically
  significant" (LM §4). **No threshold is published for either** - any gate we impose is a
  platform choice. We run UNGATED (matching the published strategy) and log VIX(close, T−2)
  and MA8 as covariates for the grader.

## 4. EXACT EXIT RULES

These override all platform exit doctrine for this strategy. The published exit is purely
**time-based**; there is no profit target, no stop, no roll.

- **Time exit (the only exit):** "selling fifteen minutes before the announcement" (LM
  §3.1). Modern clock: **13:45 ET on announcement day** for a 14:00 ET release. The
  position must NEVER be held through the announcement - the published claim is explicitly
  about the pre-announcement window: "the average return on the S&P500 index from right
  before the announcement until the market close is essentially zero" (LM §1), and by
  construction the window "does not contain meeting outcomes" (LM §2). SOURCE-VERBATIM.
- **Profit target:** none published. "The simple strategy ... buying the SPX at 2 pm the
  day before ... selling fifteen minutes before the announcement" (LM §3.1) - the position
  is held for the full window regardless of interim P&L. SOURCE-VERBATIM (absence).
- **Loss management / stop:** none published - same quote; the strategy held through the
  −2.9% June 26, 2002 window (LM fn. 13). SOURCE-VERBATIM (absence).
- **Roll rules:** none - the position exists only inside the ~24h window. SOURCE-VERBATIM
  (absence).
- **Hold-to-expiry:** never. The option is sold at the time exit; expiry is deliberately
  chosen after the exit so the exit is always a sale, not settlement. ADAPTED (consequence
  of the option wrapper; the source sells the index at the same clock time).

## 5. SIZING CONVENTION IN SOURCE

The source is an academic study; the "strategy" is fully invested in the index inside the
window and in cash otherwise: "buying the SPX at 2 pm the day before a scheduled FOMC
announcement, selling fifteen minutes before the announcement **and holding cash on all
other days**" (LM §3.1). That is a 100%-of-capital delta-one index switch, 8 times per
year - no leverage, no per-trade risk fraction. Recorded for context only; our shadow
always runs **1 published unit = 1 long call contract**, account-blind.

## 6. DOCUMENTED PERFORMANCE

All figures are for the **index** (delta-one), NOT for any options implementation. No
options-form performance exists in the sources.

| Metric | Value | Period | Tag |
|---|---|---|---|
| Mean pre-FOMC 24h excess return (SPX, 2pm-to-2pm) | 49 bp, "t-statistic of more than 4.5" (Huber-White) | Sep 1994–Mar 2011, 131 scheduled meetings | [verified-primary] |
| Mean return all other 2pm-to-2pm windows | "less than .5 basis points" | same | [verified-primary] |
| Annualized: pre-FOMC window vs rest | 3.89%/yr vs 0.88%/yr → "about 80% of realized excess stock returns" from the window | same | [verified-primary] |
| Annualized Sharpe of the switch strategy | 1.14 | same | [verified-primary] |
| Close-to-2pm window variant | Sharpe 1.43 | same | [verified-primary] |
| Close(T−2)-to-2pm window variant | 54 bp drift, Sharpe "about 1" | same | [verified-primary] |
| Pre-FOMC day return (daily data) | 20 bp (significant) | 1980–1993 | [verified-primary] |
| Pre-FOMC return | "essentially zero" | 1960–1979 | [verified-primary] |
| Combined pre-FOMC excess return | 36 bp, t = 4.86, Sharpe 0.92; ">half of realized excess stock returns" | 1980–2011, 524 meetings over 1960–2011 | [verified-primary] |
| Reversion | none: "we do not find evidence of pre-FOMC return reversals in either sample" | both samples | [verified-primary] |
| Largest single-window outcomes | +9.5% (Oct 29, 2008), −2.9% (Jun 26, 2002, WorldCom fraud news) | post-1994 | [verified-primary] |
| Post-sample, press-conference meetings | mean 0.445% | Apr 2011–Dec 2015 (20 meetings) | [verified-secondary] (Kurov Table 2) |
| Post-sample, press-conference meetings | mean **0.092%**; Wilcoxon rejects equality with prior period at 1%; NOT distinguishable from non-announcement days (mean 0.054%) | Jan 2016–Dec 2019 (20 meetings) | [verified-secondary] (Kurov Table 2) |
| Meetings without press conferences, post-2011 | "mean pre-FOMC return ... is close to zero" | Apr 2011–Dec 2018 | [verified-secondary] |
| Per-event win rate | 98 of 131 windows positive ("or three quarters of the total - but only 33 are negative"), i.e. ~75% | Sep 1994–Mar 2011 | [verified-primary] (LM §3.1); also "positive for the vast majority" of 1980–2011 on one-year rolling averages |

**Methodology caveats:** windows measured on index/futures excess returns, frictionless, no
options; the 49bp headline is in-sample 1994–2011; the independent extension shows the
effect is statistically dead 2016–2019 (Kurov: the drift "essentially disappeared after
2015"). No source documents post-2019 (COVID/2022-hike-cycle/2024+) behavior - treat
recent-era edge as UNVERIFIED, which is precisely what the shadow measures.

## 7. KNOWN FAILURE MODES

- **Post-2015 attenuation (the dominant one, documented):** "since January 2016 the
  pre-FOMC drift has also substantially weakened in announcements with press conferences"
  (Kurov §1); mean fell 44.5 bp → 9.2 bp and became indistinguishable from ordinary days.
  Candidate explanation: "reduced uncertainty" (Kurov Abstract). Corollary: the drift is
  documented to load on high VIX - in calm regimes the published edge may be ~zero while
  our theta cost is not.
- **Press-conference dependence (structural regime change):** BGM "find that the pre-FOMC
  drift is limited to announcements with press conferences" (Kurov §1). Since 2019 every
  meeting has a press conference, so the filter is moot going forward, but pre-2019
  backtests must respect it.
- **Publication decay:** JF 2015 publication → McLean–Pontiff-style erosion is explicitly
  discussed (and only partially rejected) by Kurov §3.
- **In-window event shock:** the strategy holds ~24h with an overnight and no stop. LM's
  largest negative window was "-2.9% ... on June 26, 2002, driven mainly by news of an
  accounting fraud at phone company WorldCom" (LM fn. 13). A Mar-2020-style overnight gap
  inside a pre-FOMC window would hit at full delta with no published loss rule. (For the
  long-call form this loss is capped at the debit - one mercy of the adaptation.)
- **Emergency / unscheduled meetings:** not in the tested set (LM §2 lists them
  separately); trading an intermeeting surprise announcement as if scheduled has no
  published support.
- **Release-time drift:** announcement time moved across history (2:15pm → 12:30/2:15pm →
  2:00pm; Kurov §2). A hard-coded clock that misses a schedule change would hold through
  the announcement - the one thing the published strategy never does.
- **Low realized vol in the window (structural, for OUR option form):** "realized
  volatility and trading volume are lower in the hours before FOMC announcements" (LM §1);
  long premium bleeds theta precisely when realized vol is documented to be low. Any IV
  run-up into the announcement partially offsets via vega since we sell 15 min before the
  release (before the post-announcement IV crush) - unmodeled, unpublished, shadow will
  measure.
- **Not applicable:** early assignment / ex-div risk (long-only single-leg call, no short
  legs); gap-through-strikes (no short strikes).

## 8. PARAMETER TABLE

| # | Name | Value | Tag | Source quote / locator |
|---|---|---|---|---|
| 1 | event_type | scheduled FOMC statement release (8/yr; unscheduled meetings excluded) | SOURCE-VERBATIM | "scheduled meetings have, instead, always occurred eight times per year" (LM §1/§2) |
| 2 | entry_offset | announcement_time − 24h15m (= 2pm ET on T−1 for a 2:15pm release) | SOURCE-VERBATIM | "buying the SPX at 2 pm the day before a scheduled FOMC announcement" (LM §3.1); window = "from 2 pm on the day before ... until 2 pm on the day of" (LM §2) |
| 3 | entry_clock_modern | 13:45 ET on T−1 (for the modern 14:00 ET release) | ADAPTED | derived from row 2 + "at 2:00 pm since March 2013" (Kurov §2); Kurov use the "1:45 pm-to-1:45 pm window" post-2011 |
| 4 | exit_offset | announcement_time − 15 min; NEVER hold through the release | SOURCE-VERBATIM | "selling fifteen minutes before the announcement" (LM §3.1); "about fifteen minutes before the announcement release time" (LM §2) |
| 5 | announcement_time_assumed | 14:00 ET (verify per meeting against the Fed calendar) | SOURCE-VERBATIM (as of source) | "at 2:00 pm since March 2013" (Kurov §2) |
| 6 | window_start_alternative | previous-day market open 09:30 ET | SOURCE-RANGE (default = row 2/3) | "the drift begins at the stock market open of the previous day" (Kurov §1, citing BGM) |
| 7 | direction | long only | SOURCE-VERBATIM | "the S&P500 index has on average increased 49 basis points in the 24 hours before scheduled FOMC announcements" (LM §1) |
| 8 | underlying_published | SPX cash index (LM) / E-mini futures (Kurov) | SOURCE-VERBATIM | "the S&P500 index (SPX henceforth)" (LM §3.1); "E-mini S&P 500 nearby contract futures" (Kurov §2) |
| 9 | underlying_ours | SPY (primary); QQQ, IWM (secondary); mega-cap singles excluded | ADAPTED | market-level effect, "broad-based across U.S. industry and size portfolios" (LM §1); single names add idiosyncratic noise ≫ 49bp |
| 10 | instrument | long call, 1 leg (source holds delta-one index - no options anywhere in source) | ADAPTED | "buying the SPX ... selling ... holding cash" (LM §3.1) |
| 11 | strike_rule | nearest strike to spot at entry (ATM, Δ ≈ 0.50) | ADAPTED | UNKNOWN in source (no options traded); chosen for max gamma/liquidity per strategy id |
| 12 | dte_rule | nearest listed expiry strictly AFTER announcement day (never expires before exit); practical band 1–7 DTE | ADAPTED | UNKNOWN in source; exit must be a sale (row 4), so expiry > exit by construction |
| 13 | profit_target | NONE (hold full window) | SOURCE-VERBATIM (absence) | full-window switch strategy quote (LM §3.1); no interim exit appears anywhere in source |
| 14 | stop_loss | NONE (held through the −2.9% window) | SOURCE-VERBATIM (absence) | same; "largest negative outlier is a -2.9% return on June 26, 2002" was included (LM fn. 13) |
| 15 | roll_rule | NONE (position lives only inside the window) | SOURCE-VERBATIM (absence) | "holding cash on all other days" (LM §3.1) |
| 16 | vix_gate | NONE in published strategy; UNKNOWN threshold; log VIX(close, T−2) as covariate | SOURCE-VERBATIM (association only) | "the VIX is strongly significant with a coefficient of 0.31" measured "at the market close two days before scheduled meetings" (LM §4) - no trading threshold published |
| 17 | ma8_covariate | trailing mean pre-FOMC return over past 8 meetings; UNKNOWN threshold; log only | SOURCE-VERBATIM (association only) | "average over the past eight FOMC meetings (a variable that we label MA8) ... highly statistically significant" (LM §4) |
| 18 | press_conference_filter | not applied (all meetings have press conferences since 2019); mandatory for pre-2019 backtests | SOURCE-VERBATIM (secondary) | "the pre-FOMC drift is limited to announcements with press conferences" (Kurov §1, citing BGM); "2019 when they started taking place after every announcement" (Kurov §2) |
| 19 | size | 1 contract | PLATFORM-POLICY | shadow convention: 1 published unit, account-blind (source is a 100% index switch, §5) |
| 20 | liquidity_gates | platform standard (quote present, spread cap, OI floor) on the selected contract | PLATFORM-POLICY | ours; no source basis |

## 9. DATA REQUIREMENTS

- **FOMC calendar (critical):** scheduled meeting dates AND per-meeting statement release
  time (assume 14:00 ET, verify each meeting). This is the entire signal. Must distinguish
  scheduled vs unscheduled/emergency announcements (only scheduled qualify).
- **Tradier chains:** SPY/QQQ/IWM, 0–10 DTE band around each meeting (need the expiry
  strictly after announcement day; dailies exist on all three). Quotes needed at T−1 13:45
  ET (entry) and T 13:45 ET (exit).
- **1-min bars:** yes - entry/exit are clock-precise intraday times (13:45 ET); marks at
  minute granularity around the window; also to verify the exit landed before the release.
- **Daily history:** SPY for context/covariates; not signal-bearing.
- **VIX regime:** VIX close at T−2 logged per trade (documented covariate, LM §4). Our IV
  archive is cold → use the VIX-percentile fallback for any regime tagging; no gate is
  applied so this is covariate-only.
- **IV rank:** not required by the published form; nice-to-have for the theta-cost
  postmortem. Cold-archive → VIX-percentile fallback acceptable.
- **Earnings calendar:** not required (index ETFs; no earnings interaction in source).
- **CPI dates:** not required for the signal (LM: "Other major U.S. macroeconomic new
  announcements also do not give rise to pre-announcement excess equity returns" - 
  Abstract); optionally log CPI-collision days as a covariate.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Cadence / grading timeline:** 8 scheduled meetings/year. SPY-only = 0.67 trades/month
  (N=25 takes ~3.1 years - too slow). With SPY+QQQ+IWM per meeting = **~2 trades/month**,
  N=25 in ~12.5 months, though the three are ~one bet (market beta) - the grader should
  treat per-meeting cross-ETF trades as correlated, not independent.
- **Mark cadence:** 1-min marks from entry (T−1 13:45 ET) through exit (T 13:45 ET),
  including the overnight open; a hard mark at 13:44–13:45 ET on announcement day. The
  exit is time-critical: a late exit contaminates the trade with announcement variance the
  published claim explicitly excludes - grade any post-release fill as a process failure,
  whatever its P&L.
- **Multi-leg shape:** single leg, long 1 call. No hedging legs (platform has none; source
  needs none - it is delta-one, see §2 warning).
- **Capital-at-risk basis:** debit paid (long premium; max loss = debit).
- **1-lot account-blind distortion:** the source is a 100%-notional index switch; our 1-lot
  call is both smaller and convex. Direction of distortion: our P&L ≈ 0.5 × index move ×
  100 × S minus ~24h theta and spread, plus vega into the release. Under the LM-era 49bp
  drift the option form plausibly clears costs; under the post-2015 ~9bp drift
  [verified-secondary] theta+spread almost certainly dominate. **The honest hypothesis
  this shadow tests is whether any post-2019 revival of the drift is large enough to
  survive the option wrapper - the sources say nothing about post-2019.**
- Never enter for unscheduled/emergency meetings; never carry past 13:45 ET on
  announcement day; if the release time for a given meeting is not 14:00 ET, re-anchor
  both entry and exit to (release − 24h15m, release − 15m).

## 11. VERIFICATION

- **Verdict: CORRECTED** (adversarial re-verification, 2026-07-19, fresh-context verifier).
- **Method:** both cited full texts were independently re-downloaded and text-extracted
  (FRBNY sr512.pdf, 63 pages - matches the brief's page count; Skidmore-hosted Kurov/
  Wolfe/Gilbert working paper, 20 pages). Every SOURCE-VERBATIM / SOURCE-RANGE constant
  and every [verified-primary] / [verified-secondary] number in sections 3, 4, 6, and 8
  was grep-located in the extracted source text.
- **Confirmed verbatim in LM sr512:** 49 bp with t > 4.5 (Huber-White); "less than .5
  basis points" on other windows; 3.89%/yr vs 0.88%/yr and ~80% share; Sharpe 1.14
  (2pm-to-2pm), 1.43 (close-to-2pm), 54 bp with Sharpe "about 1" (close T−2); 131 and
  524 scheduled meetings; 20 bp 1980–1993; essentially-zero 1960–1979; 36 bp, t = 4.86,
  Sharpe 0.92, ">half" for 1980–2011; no reversals; +9.5% Oct 29 2008 and −2.9% Jun 26
  2002 WorldCom (both in footnote 13 as cited); VIX coefficient 0.31 at close T−2; MA8
  "highly statistically significant"; all entry/exit clock quotes (§2, §3.1); eight
  meetings/year; unscheduled-meeting exclusion; low realized vol/volume quote;
  broad-based / foreign-markets / macro-announcement / vast-majority quotes; "does not
  contain meeting outcomes."
- **Confirmed verbatim in Kurov et al.:** Table 2 means 0.445 (with-PC 04/2011–12/2015,
  Obs. 20), 0.092 (with-PC 01/2016–12/2019, Obs. 20), 0.054 (non-FOMC 01/2016–12/2019);
  Wilcoxon rejection at 1% between halves and non-rejection vs non-announcement days;
  without-PC "close to zero" 04/2011–12/2018 (Obs. 30, mean −0.051); "essentially
  disappeared after 2015"; "reduced uncertainty"; release-time history (2:15pm →
  12:30/2:15pm → 2:00pm since March 2013); E-mini futures and the LM-spot-index
  footnote; BGM press-conference limitation and previous-day-open window start;
  post-2019 every-meeting press conferences; McLean–Pontiff discussion.
- **Corrections applied (all minor):** (1) §6 win-rate row - the brief claimed the
  per-event win rate was UNKNOWN, but LM §3.1 explicitly report "98 of the 131 pre-FOMC
  announcement returns are positive ... or three quarters of the total - but only 33 are
  negative" (~75%); row updated to [verified-primary]. Error was in the conservative
  direction (under-claiming), not an invention. (2) §1 - Ben Dor & Rosa (2019) is
  published in The Journal of Fixed Income 28(4), 60–72 per Kurov's reference list, not
  an FRBNY publication; fixed. (3) §3 - clarified that Kurov's literal "1:45 pm-to-1:45
  pm window" phrase describes their post-2011 non-announcement benchmark; their
  announcement-day rule ("24 hours ending 15 minutes before the announcement") yields
  the identical clock for a 14:00 ET release, so the brief's derived window stands.
- **No invented constants found.** All ADAPTED rows (strike, DTE, modern clock, ETF
  mapping, instrument) carry explicit rationale and none is presented as published; the
  §2 loud warning correctly discloses that the source strategy is delta-one index, not
  options. The primary source supports the stated edge claim for its 1994–2011 sample;
  the secondary genuinely documents post-2015 attenuation exactly as the brief states.
- **Residual doubts:** (a) The JF 2015 published version (70(1), 329–371) was not
  re-fetched (paywalled); the brief correctly states the staff report is what was read,
  and the citation matches the standard record. (b) BGM (2019) and Ben Dor & Rosa (2019)
  were verified only as characterized inside Kurov, consistent with the brief's
  "not independently read" label. (c) Nothing post-2019 exists in any cited source - 
  the brief already flags this; recent-era edge is genuinely unverified and is what the
  shadow measures. (d) Section 6's "Post-sample 0.445%/0.092%" rows apply to
  press-conference meetings measured from the previous-day OPEN (Kurov Table 2 window),
  not LM's 2pm window - the brief cites Kurov Table 2 correctly, but note the window
  mismatch when comparing 44.5 bp to LM's 49 bp.

### Second independent verification pass (2026-07-19, fresh-context adversarial verifier)

- **Verdict: CONFIRMED.** The pre-existing verification block above was treated as
  UNTRUSTED and everything was re-verified from scratch: both cited PDFs were freshly
  re-downloaded (newyorkfed.org sr512.pdf, 63 pages; skidmore.edu Kurov/Wolfe/Gilbert
  working paper, 20 pages) and text-extracted with an independent toolchain (pypdf),
  then every SOURCE-VERBATIM / SOURCE-RANGE constant in sections 3, 4, and 8 and every
  [verified-primary] / [verified-secondary] figure in section 6 was grep-located in the
  extracted text. No edits were needed; no invented constants were found.
- **Independently re-confirmed in LM sr512 (exact text located):** 49 bp / t > 4.5
  Huber-White; "less than .5 basis points"; 3.89% vs 0.88% and ~80% share; Sharpe 1.14 /
  1.43 / 54 bp with Sharpe "about 1"; 131 and 524 scheduled meetings; 20 bp 1980–1993;
  essentially-zero pre-1980; 36 bp t = 4.86 Sharpe 0.92 and "more than half" 1980–2011;
  "no evidence of pre-FOMC return reversals"; +9.5% Oct 29 2008 and −2.9% Jun 26 2002
  WorldCom; "98 of the 131 ... three quarters of the total - but only 33 are negative";
  VIX coefficient 0.31 at market close two days before; MA8 "highly statistically
  significant"; every entry/exit clock quote ("2 pm on the day before", "fifteen minutes
  before the announcement", "holding cash on all other days", release "at, or a few
  minutes after, 2:15 pm", "do not contain meeting outcomes"); eight meetings/year;
  unscheduled-meeting separation; "realized volatility and trading volume are lower";
  broad-based / foreign-markets / vast-majority / no-other-macro-announcement quotes.
- **Independently re-confirmed in Kurov et al.:** Table 2 means −0.051 / 0.445 / 0.092 /
  0.054 with Obs. 30/20/20; both Wilcoxon results; "essentially disappeared after 2015";
  "reduced uncertainty"; release-time history (2:15pm → 12:30 or 2:15pm → 2:00pm since
  March 2013); "return in 24 hours ending 15 minutes before the announcement";
  "1:45 pm-to-1:45 pm window" as the post-April-2011 non-announcement benchmark (the
  first pass's correction (3) is accurate); E-mini futures + LM-spot-index footnote; BGM
  press-conference limitation and previous-day-open window start; press conferences
  after every announcement since January 2019; McLean–Pontiff discussion; Ben Dor &
  Rosa (2019) The Journal of Fixed Income 28(4), 60–72 per the reference list.
- **Additional residual notes:** (e) The "fn. 13" locator for the +9.5%/−2.9% outliers
  could not be pinned to a footnote number in the raw text extraction (footnote markers
  are mangled by extraction), but the quoted sentences are verbatim present at the cited
  location in §3.1's discussion; same caveat applies to all §-number locators generally
  (content verified, section numbering taken on the paper's structure). (f) The LM
  abstract's PDF text reads "macroeconomic new announcements" where §1 reads "news
  announcements" - the brief's §9 quote follows the §1 wording; trivial.
