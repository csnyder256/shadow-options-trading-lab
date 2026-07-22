# Strategy Brief: earnings_iv_crush_strangle

Researched 2026-07-19. Every constant in sections 3, 4, 8 carries a direct quote or a precise
locator, or is marked UNKNOWN / ADAPTED / PLATFORM-POLICY. Sources were read directly
(archived episode pages and full working-paper PDFs), not recalled from memory.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `earnings_iv_crush_strangle`
- **Provenance class:** practitioner (tastytrade/tastylive published backtest doctrine), with
  academic support and an academic COUNTER-result (see §6).
- **PRIMARY citation (practitioner, the published form of the trade):**
  - tastytrade **Market Measures, "Exploring Expirations for Earnings," Oct 29 2018** - 
    archived page read directly:
    `http://web.archive.org/web/20191209152640/https://www.tastytrade.com/tt/shows/market-measures/episodes/exploring-expirations-for-earnings-10-29-2018`
    Study card verbatim: "Study: AMZN, JPM, IBM 2013 - Present Sold 16 delta Strangles Weekly
    Expirations Front Week, 2 Weeks, 3 Weeks Sold the Day Before Earnings Covered the Day
    After Recorded Average P/L, Standard Deviation (Risk)". (Re-aired with identical study
    card as "Trading Around Earnings," Apr 25 2019, archived snapshot 20190819040325.)
  - tastytrade **Market Measures, "Selling Premium Around Earnings," Oct 23 2015** - archived
    page read directly:
    `http://web.archive.org/web/20201020201107/https://www.tastytrade.com/tt/shows/market-measures/episodes/selling-premium-around-earnings-10-23-2015`
    Verbatim: "A study was conducted from 2002 to present. The study examined 22,760 earnings
    announcements. We sold a 1 Standard Deviation (SD) Strangle before the earnings
    announcement and closed it immediately after."
- **Academic support (the priced announcement-variance premium):** Dubinsky & Johannes,
  *"Earnings announcements and equity options"*, Columbia GSB working paper (first draft Nov
  2003; draft read: Sept 2004) - full PDF read:
  `https://business.columbia.edu/sites/default/files-efs/pubfiles/6051/DJ_2006.pdf`
  Published as: Dubinsky, Johannes, Kaeck & Seeger, **"Option Pricing of Earnings
  Announcement Risks," Review of Financial Studies 32(2), Feb 2019, 646–687**, doi
  10.1093/rfs/hhy060 (`https://academic.oup.com/rfs/article-abstract/32/2/646/5001193`).
- **INDEPENDENT secondary sources:**
  - Xing & Zhang working paper (Apr 22 2013), *"Anticipating Uncertainty: Straddles Around
    Earnings Announcements"* - full PDF read:
    `https://www.ruf.rice.edu/~yxing/straddle_201305_03.pdf`. Published as Gao, Xing & Zhang,
    JFQA 53(6), Dec 2018, 2587–2617
    (`https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2204549`). **This is the OPPOSITE
    side** - it documents that LONG straddles through earnings were profitable on the average
    optionable stock 1996–2010; see §6/§7.
  - tastylive Learn Center, "Earnings" concepts page (`https://www.tastylive.com/concepts-strategies/earnings`),
    read 2026-07-19: "We can take advantage of the implied volatility crush by selling
    premium prior to the announcement, and buying it back after the announcement."
  - Supporting episodes read (archived): "Duration | Earnings Trades" (Jul 16 2015,
    snapshot 20190723135010, slug duration-earnings-trades-07-16-2015), "Earnings vs Short Premium" (Jan 14 2019, snapshot
    20190722231939), "The Earnings Edge" (Jul 29 2019, snapshot 20190821150042).
- **Publication dates:** practitioner doctrine 2013–2020 (episodes above); academic 2003–2019.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

- **What the sources trade:** single stocks with listed options around their own quarterly
  earnings. tastytrade study universes read directly: "AMZN, JPM, IBM 2013 - Present"
  (MM 2018-10-29); "AAPL, AMZN, GS, IBM, GOOGL, 5 DTE, 2010- 2018" (MM 2019-01-14); the 2015
  study pooled "22,760 earnings announcements" from 2002 across optionable names. Dubinsky &
  Johannes: "a sample of 20 low-dividend firms with the most actively traded options from
  1996 to 2002."
- **Our mapping:** the strategy fires ONLY on single names. From our platform universe
  (SPY/QQQ/IWM + mega-cap tier AAPL/NVDA/MSFT/TSLA/AMD/META), **SPY/QQQ/IWM contribute zero
  entries - index ETFs have no earnings announcements.** Trades trigger on the 6 mega-caps'
  quarterly report dates.
- **Why the mapping preserves the edge claim:** the tastytrade studies themselves were run on
  liquid mega-caps (AAPL, AMZN, GOOGL, IBM, GS, JPM) - our tier is the same liquidity class,
  same weekly-option availability, same announcement-IV term-structure spike. **Caveat
  recorded honestly:** Xing & Zhang's cross-section shows the (long-straddle) announcement
  mispricing is *smallest* in the largest names - "the average straddle return is 4.10% and
  1.71% for firms in the smallest and the largest size quartile, respectively" - which cuts
  BOTH ways: the short side loses least (or wins) exactly in large liquid names, but no
  source demonstrates a positive short edge specific to mega-caps.
- **Options-only check:** the published form is a naked short strangle - pure options, no
  stock leg, no delta-hedging. **No structural adaptation required.** Adaptations that were
  made: clock-time operationalization of entry/exit (§3/§4), always-close-never-roll (§4),
  universe substitution (this section). All tagged in §8.

## 3. EXACT ENTRY RULES

- **Trigger:** a universe name has a confirmed earnings announcement scheduled such that the
  announcement occurs between today's close and tomorrow's open (AMC today, or BMO tomorrow).
  Source frames the trade as event-driven premium selling: "An earnings announcement is a
  binary event and we expect a contraction of volatility afterwards." (MM 2015-10-23).
- **Structure - short strangle:** "We sold a 1 Standard Deviation (SD) Strangle before the
  earnings announcement" (MM 2015-10-23); "Sold 16 delta Strangles" (MM 2018-10-29). One
  short OTM call + one short OTM put, same expiration.
- **Strike selection:** **16-delta per leg** - "Sold 16 delta Strangles" (MM 2018-10-29,
  identical card re-aired MM 2019-04-25; same convention in MM 2019-01-14: "16 delta
  strangles"). The 2015 study's "1 Standard Deviation (SD) Strangle" is the same family
  (1 SD ≈ 16-delta). Select the strike whose absolute delta is nearest 0.16 on each side at
  entry time.
- **DTE / expiration selection:** the expiration **nearest after the announcement** (front
  weekly): "We generally use the options with the closest expiration to take maximum
  advantage of the expected decline in IV." (MM 2015-10-23); "Typically, we use the closest
  expiration to place an earnings trade." (MM 2018-10-29). Concrete DTE in a published study
  card: "AAPL, AMZN, GS, IBM, GOOGL, 5 DTE" (MM 2019-01-14). The 2018 duration study tested
  "Weekly Expirations Front Week, 2 Weeks, 3 Weeks" - front week is the documented default.
- **Entry timing:** published as day-granular only: "Sold the Day Before Earnings"
  (MM 2018-10-29); "selling premium prior to the announcement" (tastylive Learn, Earnings
  page). **No clock time is published.** Our operationalization: enter in the last 15
  minutes of the final regular session before the announcement (T-0 15:45–16:00 ET for AMC
  reporters; prior-day close for BMO reporters) - tagged ADAPTED in §8.
- **Regime / IV gate:** none published as an entry condition for the earnings play. The 2015
  study *split* results by VIX regime - "with a low VIX (under 15) and a high VIX (over 20)"
  (MM 2015-10-23) - but the per-regime numbers were shown only on slides not retrievable from
  the archived page; whether a VIX gate helps is **UNKNOWN**. We record VIX at entry but gate
  nothing.

## 4. EXACT EXIT RULES - OVERRIDE PLATFORM EXIT DOCTRINE

- **Time exit (the rule):** close the entire strangle at the first opportunity after the
  announcement. "…and closed it immediately after." (MM 2015-10-23); "Covered the Day After"
  (MM 2018-10-29); "Managed day after earnings" (MM 2019-01-14). **No clock time published**;
  our operationalization = T+1 09:30–09:35 ET open - tagged ADAPTED in §8.
- **Profit target:** NONE published for the earnings play. The exit is unconditional and
  time-boxed. (The famous tastylive "manage at 50% of credit" rule belongs to their 45-DTE
  non-event strangle program, NOT to the overnight earnings play - do not import it.)
- **Stop loss:** NONE published pre-announcement (the position is opened at the close and the
  event happens overnight; there is no intra-hold management window).
- **Loss handling after the event / roll doctrine:** published as a discretionary either-or:
  "We then have the choice of taking the loss by closing out the position or rolling out for
  duration and to collect additional premium." (MM 2015-10-23). **Our shadow always takes the
  first branch (close at T+1 open, win or lose) - never rolls.** The close branch is itself
  published; dropping the roll option is tagged ADAPTED in §8.
- **Hold-to-expiry doctrine:** not applicable - the published form never holds to expiry.

## 5. SIZING CONVENTION IN SOURCE

The tastytrade study tables record per-trade dollar P/L of a single strangle ("Recorded
Average P/L, Standard Deviation (Risk)" - MM 2018-10-29; "The table included the average P/L,
percentage of profitability, largest gain and largest loss" - MM 2015-10-23), i.e. a 1-lot
convention. No percent-of-buying-power sizing rule for earnings plays appears in any page
read; tastylive's general small-allocation doctrine was not retrievable in quotable form - 
recorded as UNKNOWN. **Our shadow runs 1 published unit (one 1-lot strangle), account-blind**
 - which matches the study convention almost exactly.

## 6. DOCUMENTED PERFORMANCE

All practitioner tags refer to archived episode pages read directly (URLs in §1).

- Setup scale: "A study was conducted from 2002 to present. The study examined 22,760
  earnings announcements." [verified-primary] - but the actual results table ("average P/L,
  percentage of profitability, largest gain and largest loss") lived on slides that are not
  in the archived text: **win rate, average P/L, largest gain/loss = UNKNOWN numerically.**
- Qualitative result, strangle earnings plays: "The study shows that the strangles have high
  win rates, but relatively flat average P/L because of the large outlier moves. We also
  found that defining our risk with iron condors does not significantly outperform the
  strangles." (MM 2019-07-29) [verified-primary]
- Versus baseline premium selling: "We find that earnings trades have much larger variance in
  P/L and lower P/L on average than short premium trades. The reason we trade earrings [sic],
  however, is due to their engagement value." (MM 2019-01-14) [verified-primary]
- Duration trade-off, 2015 study: "using the shortest dated expiration provided the largest
  amount of profits and you were able to capture the highest percentage of the overall
  premium. If you were to use the longer dated expirations, you should see a small reduction
  in profits but a higher overall win rate." (MM 2015-07-16) [verified-primary]
- Duration trade-off, 2018 study (mild tension with the above - record both): "For these
  underlyings, it seems that adding duration slightly improves the Average P/L while lowering
  the Standard Deviation." (MM 2018-10-29) [verified-primary]
- Academic support (risk premium exists): "the ratio of Pvol to Qvol is 0.74 while the
  average scaled ratio is 0.82, so that the volatility under Q is about 20 to 30 percent
  higher than under P." (Dubinsky & Johannes WP, §on risk premiums) [verified-primary].
  Mean earnings-jump vol: "the mean estimate of σQ_j is 10.4 percent for the term structure
  estimator and 8.5 percent for the time series estimator" (20 firms, 1996–2002)
  [verified-primary]. IV-crush magnitude example: Intel Jul 15 1997 - ATM July IV "71.15
  percent prior to the announcement… fell drastically to 42.96 percent" the day after
  [verified-primary].
- **Academic COUNTER-result (the other side wins on the average stock):** Xing & Zhang
  1996–2010, delta-neutral ATM straddles held THROUGH the announcement: "The average holding
  straddle returns for [-5,1], [-3,1] and [-1,1] are 2.68%, 1.25% and 3.09%, respectively,
  and they remain highly significant." [verified-primary] - i.e. the SHORT side of the exact
  hold-through window lost on average, pre-costs, on the pooled optionable universe.
  Announcement-window IV path: "the implied volatility increases to 0.532 on day -1… On day
  1, the implied volatility crashes down to 0.491." [verified-primary]. Size cross-section
  ([-3,0] window): smallest quartile 4.10% vs largest 1.71% [verified-primary]. Published
  JFQA version headline: "average at-the-money straddles from 3 days before an earnings
  announcement to the announcement date yield a highly significant 3.34% return"
  [verified-secondary, abstract]. NO CAGR/PF/drawdown exists in any source read; any such
  number attached to this strategy would be invented.

**Methodology caveats:** tastytrade backtests are mid-price fills, no commissions/slippage,
survivor-biased symbol lists, and the headline numbers were never published in retrievable
text. Xing & Zhang use OptionMetrics mid-quotes ("We take the mid-quote value as a fair
reflection of the option price"), options "with 10 to 60 days to maturity," delta 0.375–0.625
at formation - longer-dated than the front-weekly practitioner form, and 1996–2010 predates
dense weekly listings.

## 7. KNOWN FAILURE MODES

- **Gap-through-strikes (THE failure mode):** a 16-delta strangle is short both tails of a
  binary event; one outsized gap wipes many winners. Source's own warning: "The problems with
  playing binary events such as earnings is that one bad loss can wipe out all our winners."
  (MM 2015-10-23). Named episodes of mega-cap earnings gaps far beyond the priced move:
  META 2022-02-03 (~-26% overnight) [unverified], NVDA 2023-05-24/25 (~+24%) [unverified],
  AMZN, TSLA multiple >±10% overnight earnings gaps [unverified]. Our TSLA/NVDA/META names
  are precisely the high-kurtosis kind.
- **The average-stock edge is negative:** Xing & Zhang (§6) - shorting through the
  announcement lost on the pooled universe 1996–2010. The practitioner case survives only as
  "high win rate, flat average P/L" on liquid mega-caps. This strategy is a win-rate/casino
  profile with severe left tail; the e-process grader must expect exactly that shape.
- **Overnight no-exit window:** the loss is realized entirely between T-0 close and T+1 open;
  no stop can execute inside the gap. Platform can never "manage" this trade mid-hold.
- **Opening-auction exit slippage:** T+1 09:30 spreads on single-name options are at their
  widest; a mid-based shadow fill will systematically overstate the recoverable exit price.
- **Early assignment:** a leg that gaps deep ITM overnight can be assigned before our T+1
  exit, particularly calls through an ex-dividend date (AAPL/MSFT pay dividends) and hard-ITM
  puts. Structural for all short ITM legs; one-night exposure makes it rare but nonzero.
- **Announcement-timing errors (structural, ours):** a bmo/amc misclassification or a
  company moving its report date means entering AFTER the event (selling post-crush premium
  for nothing) or holding through the wrong night. Berkman & Truong, cited in Xing & Zhang:
  "more than 30% of firms announce their earnings after the market close" - timing metadata
  is load-bearing. Xing & Zhang themselves punt: "data on exact announcement hours can be
  imprecise; therefore we choose to only make use of announcement date".
- **Vol-regime shocks stacking on event risk:** entering earnings shorts during a market-wide
  vol spike (Feb-2018 Volmageddon week, Mar-2020, Aug-2024 VIX spike) compounds single-name
  gap risk with systemic gap risk; the 2015 study's VIX<15 / VIX>20 split shows tastytrade
  considered regime dependence material, but its result is UNKNOWN (slides only).

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | structure | short strangle (1 short OTM call + 1 short OTM put, same expiration) | SOURCE-VERBATIM | "We sold a 1 Standard Deviation (SD) Strangle before the earnings announcement" (MM 2015-10-23) |
| 2 | strike_delta_per_leg | 0.16 (nearest-to-16-delta strike each side) | SOURCE-VERBATIM | "Sold 16 delta Strangles" (MM 2018-10-29); "1 Standard Deviation (SD) Strangle" (MM 2015-10-23) |
| 3 | expiration_rule | nearest expiration strictly after the announcement (front weekly) | SOURCE-VERBATIM | "We generally use the options with the closest expiration to take maximum advantage of the expected decline in IV." (MM 2015-10-23) |
| 4 | dte_at_entry | ~5 DTE default; studied range front-week / 2 wk / 3 wk | SOURCE-RANGE | "5 DTE" (MM 2019-01-14); "Weekly Expirations Front Week, 2 Weeks, 3 Weeks" (MM 2018-10-29). Default = front week per row 3 |
| 5 | entry_day | last regular session ending before the announcement (AMC → T-0; BMO → T-1) | SOURCE-VERBATIM | "Sold the Day Before Earnings" (MM 2018-10-29); "selling premium prior to the announcement" (tastylive Learn: Earnings) |
| 6 | entry_time | 15:45–16:00 ET window, last feasible quote before the close | ADAPTED | No clock time published anywhere read; latest-before-close maximizes captured event premium and matches "prior to the announcement". Honest operationalization, not a sourced constant |
| 7 | exit_day | first regular session after the announcement (T+1) | SOURCE-VERBATIM | "Covered the Day After" (MM 2018-10-29); "closed it immediately after" (MM 2015-10-23); "Managed day after earnings" (MM 2019-01-14) |
| 8 | exit_time | 09:30–09:35 ET, T+1 opening prints | ADAPTED | No clock time published; T+1 open is the earliest tradable moment consistent with "closed it immediately after". Slippage caveat in §7 |
| 9 | profit_target | NONE (unconditional time exit) | SOURCE-VERBATIM (absence) | Exit is unconditional in every study card read; no profit-target sentence exists for the earnings play. Do not import the 45-DTE "50% of credit" rule |
| 10 | stop_loss | NONE (gap risk unmanageable overnight) | SOURCE-VERBATIM (absence) | No stop appears in any study card; hold window is a single overnight gap |
| 11 | roll_rule | never roll; always close at T+1 | ADAPTED | Source allows a choice: "taking the loss by closing out the position or rolling out for duration" (MM 2015-10-23). We fix the (also published) close branch for determinism and gradability |
| 12 | vix_split_thresholds | record VIX at entry; thresholds of historical interest 15 / 20; NO gate | SOURCE-VERBATIM (thresholds), no action | "with a low VIX (under 15) and a high VIX (over 20)" (MM 2015-10-23); per-regime results UNKNOWN (slides only) |
| 13 | iv_entry_gate | none | SOURCE-VERBATIM (absence) | No IV-rank entry filter is stated for the earnings play in any page read (high IV is intrinsic to the event) |
| 14 | universe | AAPL, NVDA, MSFT, TSLA, AMD, META quarterly reports; SPY/QQQ/IWM never trigger | ADAPTED | Study universes were "AMZN, JPM, IBM" (MM 2018-10-29) and "AAPL, AMZN, GS, IBM, GOOGL" (MM 2019-01-14); same mega-cap liquidity class, names swapped to platform tier |
| 15 | position_size | 1 strangle (1-lot), account-blind | PLATFORM-POLICY | Matches the studies' per-trade 1-lot P/L accounting (§5) |
| 16 | liquidity_gate | positive OI both legs; quoted spread sanity cap per platform standard | PLATFORM-POLICY | Ours; academic precedent for OI>0 + arbitrage-bound quote filters in Xing & Zhang sample construction |
| 17 | capital_at_risk_basis | Reg-T naked-strangle proxy (greater single-side requirement + other side's premium) | PLATFORM-POLICY | Undefined-risk structure has no width; Reg-T proxy is our family convention (§10) |

## 9. DATA REQUIREMENTS

- **Earnings calendar with date + bmo/amc (CRITICAL):** wrong timing metadata = entering
  after the event or holding the wrong night (§7). Need confirmed report date and session
  (bmo/amc/unspecified) for the 6 names; treat "unspecified" as amc-with-flag or skip.
- **Tradier chains:** DTE band 0–21 covering front weekly and next two weeklies (rows 3–4);
  need greeks/IV (16-delta selection) and NBBO at T-0 15:45–16:00 ET, plus T+1 09:30–09:35
  quotes for the exit fill.
- **1-min bars (options + underlying):** entry-window and opening-window marks for the three
  fill ledgers; opening prints are the exit.
- **Daily history (underlying):** gap statistics, context for grading; already on platform.
- **VIX:** daily close at entry, recorded per row 12 (no gate). IV rank NOT required - no
  published IV gate exists for this strategy; if the VIX split is ever re-armed as a gate,
  note our IV archive is cold → VIX-percentile fallback is the documented substitute.
- **FOMC/CPI dates:** not part of the published strategy - not required (optional overlap
  annotation only).

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** 6 single names x 4 reports/yr = 24 entries/yr ≈ **2.0/month
  average**, but heavily clustered: ~4–6 trades in each earnings-season month (Jan/Feb,
  Apr/May, Jul/Aug, Oct/Nov) and zero in dead months. At N≥25-per-lane verdict discipline,
  ~12–13 months to a graded verdict; consider widening the mega-cap tier if faster grading
  is wanted.
- **Mark cadence:** one entry mark (T-0 15:45–16:00), one exit mark (T+1 09:30–09:35), no
  intra-hold marks possible (overnight event). Optionally record T+1 10:00 and T+1 close
  marks to measure how much the ADAPTED open-exit costs vs later exits (feeds the row-8
  audit).
- **Multi-leg shape:** 2 legs, both short, same expiry: -1 call @ ~16Δ, -1 put @ ~16Δ.
  Credit received at entry; P&L = entry credit − exit debit.
- **Capital-at-risk basis:** Reg-T CaR proxy for a naked strangle - per-side requirement ≈
  premium + 20% of underlying − OTM amount (10% floors), CaR = max(call side, put side) +
  other side's premium. No width exists (undefined-risk family); do NOT use debit-paid or
  width-credit bases.
- **1-lot account-blind distortions:** minimal vs the published studies (they also account
  per-1-lot). The real divergence is portfolio-level: tastylive doctrine assumes many small
  occurrences across names/quarters diversifying the tail ("one bad loss can wipe out all
  our winners"); a 6-name shadow realizes that tail lumpily. Grade on pooled e-process
  wealth, expect high win rate with rare deep losers - a flat-to-thin mean is the honest
  published expectation (§6), not a platform bug.
- **Exit override reminder:** §4 time-boxed exit OVERRIDES all platform exit doctrine
  (persistence clocks, shrink-blend ladder, etc.) for this strategy. No roll, no hold, no
  "manage winners."

## Unknowns ledger (honest gaps, do not fill by invention)

- `win_rate_pct` - UNKNOWN (2015 study slides only; qualitatively "high win rates")
- `avg_pnl_per_trade` - UNKNOWN (qualitatively "relatively flat average P/L"; "lower P/L on
  average than short premium trades")
- `largest_gain` / `largest_loss` - UNKNOWN (slides only)
- `vix_split_results` - UNKNOWN (thresholds 15/20 published; per-regime P/L not retrievable)
- `sizing_pct_of_buying_power` - UNKNOWN (no earnings-specific sizing rule found in text)

## 11. VERIFICATION

- **Verdict: CORRECTED** (adversarial re-verification, 2026-07-19, fresh-context verifier).
- **What was checked:** every SOURCE-VERBATIM / SOURCE-RANGE constant in §3, §4, §8 and every
  [verified-*] performance number in §6 was located in its cited source, read directly:
  - Archived tastytrade episode pages re-fetched from the exact snapshot IDs cited (Wayback):
    MM 2018-10-29 "Exploring Expirations for Earnings" (20191209152640) - study card
    "AMZN, JPM, IBM / 2013 - Present / Sold 16 delta Strangles / Weekly Expirations / Front
    Week, 2 Weeks, 3 Weeks / Sold the Day Before Earnings / Covered the Day After / Recorded
    Average P/L, Standard Deviation (Risk)" VERBATIM MATCH, plus the "closest expiration" and
    "adding duration slightly improves the Average P/L while lowering the Standard Deviation"
    sentences. MM 2015-10-23 "Selling Premium Around Earnings" (20201020201107) - all six
    quoted sentences (22,760 announcements / 1 SD strangle closed immediately after / binary
    event contraction / one bad loss / close-or-roll choice / VIX under 15 over 20) VERBATIM
    MATCH; results tables confirmed slide-only (win rate / avg P/L / largest gain-loss are
    genuinely not in the archived text - the UNKNOWN tags are honest). MM 2019-01-14
    "Earnings vs Short Premium" (20190722231939) - "AAPL, AMZN, GS, IBM, GOOGL, 5 DTE,
    2010- 2018", "16 delta strangles", "Managed day after earnings", and the larger-variance /
    lower-P/L / "earrings" [sic] engagement-value sentence VERBATIM MATCH. MM 2015-07-16
    (20190723135010) and MM 2019-07-29 "The Earnings Edge" (20190821150042) - both quoted
    result paragraphs VERBATIM MATCH. MM 2019-04-25 "Trading Around Earnings" (20190819040325)
 - study card confirmed identical to the 2018-10-29 card.
  - Dubinsky & Johannes working-paper PDF (Columbia URL cited) downloaded and text-extracted:
    "20 low-dividend firms with the most actively traded options from 1996 to 2002", Pvol/Qvol
    0.74 / scaled 0.82 / "20 to 30 percent higher", σQ_j 10.4% (term structure) and 8.5%
    (time series), Intel 71.15% → 42.96% - ALL VERBATIM MATCH. RFS 32(2) 2019, 646–687,
    doi 10.1093/rfs/hhy060 publication details confirmed via OUP/RePEc.
  - Xing & Zhang working-paper PDF (Rice URL cited) downloaded and text-extracted: sample
    "January 1996 to December 2010", [-5,1]/[-3,1]/[-1,1] = 2.68%/1.25%/3.09% "remain highly
    significant", IV 0.532 day -1 → 0.491 day 1, size quartiles 4.10% vs 1.71% (and the
    cross-section section explicitly uses the [-3,0] window as the brief states), mid-quote
    sentence, 10–60 DTE / |delta| 0.375–0.625 / positive OI filters, Berkman & Truong ">30%
    after the market close", announcement-hours punt sentence - ALL VERBATIM MATCH. JFQA
    53(6) Dec 2018, 2587–2617 and the published abstract's 3.34% headline confirmed from the
    Cambridge Core PDF.
  - tastylive Learn "Earnings" page fetched live: the IV-crush sentence exists.
  - ADAPTED rows (6, 8, 11, 14) each carry a real rationale and none is presented as
    published. PLATFORM-POLICY rows make no source claim. Absence claims (rows 9, 10, 13)
    are consistent with every page read.
- **Corrections applied (both trivial):** (1) tastylive Learn quote was truncated two words
  early - completed to "...buying it back after the announcement."; (2) supporting-episode
  title corrected from "Duration and Earnings Trades" to the archived page's actual title
  "Duration | Earnings Trades" (snapshot ID was already correct; slug added).
- **Nothing was found INVENTED.** No constant in §3/§4/§8 and no [verified-*] number in §6
  failed to locate in its cited source.
- **Residual doubts:** (a) the §7 gap examples (META 2022-02-03 ~-26%, NVDA 2023-05-24/25
  ~+24%) remain [unverified] as tagged - not checked against price data here; (b) the
  tastytrade headline result tables (win rate, avg P/L, largest gain/loss, VIX-split P/L)
  exist only on non-archived slides, so the strategy's practitioner edge remains
  QUALITATIVE ("high win rates, relatively flat average P/L") - the brief says exactly this
  and the Unknowns ledger is accurate; (c) Xing & Zhang cite Berkman & Truong as 2008 in
  text but their reference list prints 2009 - the brief takes no position on the year;
  (d) SSRN landing page itself returned 403 (paywall/robot block) - the published-version
  numbers were verified via Cambridge Core instead.
- **Verifier access note:** web.archive.org was unreachable from the default fetch tool;
  all archived pages were read through the user's browser at the exact cited snapshots.
