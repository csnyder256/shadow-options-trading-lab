# Strategy Brief: zero_dte_pin_fly - 0DTE Afternoon Pin Butterfly at Max-OI Strike

Researched 2026-07-19. Both academic PDFs were downloaded and read in full (text-extracted);
practitioner pages were fetched and quoted directly. Every constant in sections 3, 4, 8 carries a
direct quote or is marked UNKNOWN.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `zero_dte_pin_fly`
- **Provenance class:** hybrid - **academic** (the pinning/clustering anomaly) + **practitioner**
  (the butterfly trade construction). The academic sources document the anomaly but publish **no
  trading rules**; the trade construction comes entirely from practitioner writeups. NPP 2005
  says so explicitly: "An interesting question, which we leave for future research, is how
  effectively the stock price deviations can be predicted from publicly available information
  prior to expiration Friday. If these predictions can be made with sufficient precision, then it
  may be possible to devise a trading strategy that exploits the expiration date clustering to
  produce abnormal profits after trading costs." (NPP 2005, Conclusion)
- **PRIMARY citation (anomaly):** Sophie Xiaoyan Ni, Neil D. Pearson, Allen M. Poteshman,
  "Stock Price Clustering on Option Expiration Dates," *Journal of Financial Economics*, Vol. 78,
  Issue 1 (October 2005), pp. 49–87.
  - Publisher page: https://www.sciencedirect.com/science/article/abs/pii/S0304405X05000577
  - Full text read at: https://optionsoffice.ru/wp-content/uploads/2020/01/Stock-Price-Clustering-on-Option-Expiration-Dates.pdf
    (working-paper version dated August 27, 2004; 53 pp.; abstract identical to the JFE version)
  - SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=519044
- **PRIMARY citations (trade construction, practitioner):**
  - "Butterfly Options Strategy & Secrets to Success" ("Increasing Your Odds of Pinning a
    Butterfly"), 0-DTE.com (author "ernie" - Ernie Varitimos), published August 14, 2022:
    https://0-dte.com/increasing-your-odds-of-pinning-a-butterfly/
  - "0DTE Trading Strategies - 5 Data-Driven Approaches With Live Examples," FlashAlpha
    (Tomasz Dobrowolski), dated March 20, 2026:
    https://flashalpha.com/articles/guide-to-0dte-trading-strategies-real-time-data
- **INDEPENDENT secondary source:** Benjamin Golez, Jens Carsten Jackwerth, "Pinning in the
  S&P 500 Futures," *Journal of Financial Economics*, Vol. 106, Issue 3 (December 2012),
  pp. 566–585. Full text read at: https://d-nb.info/1112655492/34 · publisher page:
  https://www.sciencedirect.com/science/article/abs/pii/S0304405X12001365
- **Additional secondary (variant performance, different entry form):** "Zero DTE SPX Iron
  Butterfly: 431% Returns and a Brutal 2025," Options Cafe:
  https://options.cafe/blog/zero-dte-spx-iron-butterfly-strategy/
- **Publication dates:** NPP working paper 2004-08-27, JFE October 2005; Golez–Jackwerth JFE
  December 2012; 0-DTE.com article 2022-08-14; FlashAlpha article 2026-03-20 (0DTE daily
  expirations exist on SPX/SPY/QQQ/IWM only since 2022–2023, consistent with both).

**Contested-evidence warning (must stay attached to this strategy):** the academic pinning
evidence is for **individual stocks** (NPP) and **S&P 500 futures on futures-option expirations**
(GJ). For **cash-settled index options** the evidence is contested: NPP footnote 4 quotes Mayhew
(2000, p. 32) that for index derivatives "there is little evidence of a strong, systematic price
effect around expiration," and GJ found the *opposite* of pinning around SPX option expirations:
futures "are pushed away from the cost of carry adjusted at the money strike price right before
the expiration of options on the S&P 500 index (anti cross pinning)" (GJ abstract). The 0DTE
index-ETF leg of this strategy rests on practitioner dealer-gamma claims, not on verified
academic evidence.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

- **What the sources trade/study:**
  - NPP 2005: ~2,500 optionable **individual US stocks**, monthly expiration Fridays, 1996–2002.
    Clustering measured at the **closing price** on expiration Friday.
  - GJ 2012: **S&P 500 futures** around expirations of serial options on those futures,
    Nov 1992–Nov 2009.
  - 0-DTE.com: SPX 0DTE butterflies (site's program trades SPX/NDX weeklies at 0 DTE).
  - FlashAlpha: 0DTE pin butterfly at a "magnet strike"; article's examples elsewhere use SPY;
    the pin-play section itself names no ticker.
- **Our mapping:**
  - **SPY / QQQ / IWM** - daily (Mon–Fri) 0DTE expirations; this is the practitioner form.
    LOUD ADAPTATION: published index-pinning evidence is contested (see section 1); the ETF leg
    is graded as a practitioner-claim test, not an academically anchored edge.
  - **AAPL / NVDA / MSFT / TSLA / AMD / META** - these have **weekly Friday** expirations only,
    so the strategy runs on their expiration Fridays with DTE=0. This leg is actually the
    *closest match to the primary source*: NPP documented single-stock expiration-Friday
    clustering with mechanisms (market-maker hedge rebalancing when net-long options +
    writer manipulation) that live in single names.
  - No stock legs and no delta-hedging are required anywhere: the published form is a static,
    defined-risk multi-leg option position held into the close. No adaptation needed on that
    axis (the platform's options-only constraint is naturally satisfied).
- **Why the mapping preserves the edge claim:** the claimed edge is that dealer hedge
  rebalancing (and, in single names, writer manipulation) pulls spot toward a high-open-interest
  strike into the expiration close, so a butterfly bodied at that strike converges to max value.
  NPP's mechanism is strike-OI-driven and stock-level - mega-cap weeklies preserve it directly.
  GJ show the effect concentrates late in the day ("An amazing $59 million shifts solely within
  the last 30 min of trading"), which is what the afternoon entry harvests. The ETF leg assumes
  the same dealer-gamma mechanics operate on 0DTE OI; that is the practitioner claim under test.

## 3. EXACT ENTRY RULES

Trigger and construction, with the source text for every constant:

1. **DTE = 0.** Trade only options expiring the same day. (Practitioner form: "The purest pin
   play is a **0DTE butterfly** centered at the magnet strike." - FlashAlpha.) For single names
   this means expiration Friday, the setting of the primary source: clustering occurs "on
   expiration dates" at "the closing prices" (NPP abstract).
2. **Entry timing: final two hours of the session (≥ 14:00 ET).** Source: "Condition:
   `pin_risk.pin_score > 70` and `time_to_close_hours < 2`." (FlashAlpha). Academic support for
   late-day concentration: "An amazing $59 million shifts solely within the last 30 min of
   trading." (GJ, Section 5). Last-entry cutoff is not published - we set 15:00 ET as
   PLATFORM-POLICY so the published 30-minutes-left management rule (section 4) can still
   operate.
3. **Center (body) strike = the max-OI strike of today's expiration.** Published version is a
   proprietary composite: FlashAlpha's pin-score components table lists OI Concentration (30%,
   "how much OI sits in the top 3 strikes"), Magnet Proximity (25%, "how close spot is to the
   highest-GEX strike"), Time Remaining (25%), and Gamma Magnitude (20%) - table rows, compressed
   here into one sentence. We cannot reproduce their GEX inputs; ADAPTED to: center = strike with the
   maximum same-expiration call+put open interest among strikes within the proximity gate (rule
   4). GJ's measurement convention for the attracting strike: "at the money open interest is
   measured on the Thursday before expira tion with respect to the at the money strike price on
   the expiration Friday" - i.e., prior-day OI attached to expiration-day strikes; our OI
   snapshot is the morning-of OCC value (Tradier chains), the 0DTE equivalent.
4. **Proximity gate (how close spot must be to the body):** "the ideal probability of touch
   measure when entering a fly, is that the nearest strike is > 67% Probability of Touch (PoT).
   At this distance, you will have about a 10-15% chance of a pinned trade. 70-80% seems ideal"
   (0-DTE.com). Delta proxy from the same source: "the PoT is approximately 2X the delta of a
   strike." → nearest fly strike must carry delta ≥ ~0.34 (PoT ≈ 2 × delta ≥ 67%). If the
   max-OI strike is too far from spot to satisfy this, **no trade**.
5. **Wing width:** "A 15 wide fly has a much greater chance at a pin than a 10 wide, and a 20
   wide a better chance than a 15." (0-DTE.com, SPX points). SOURCE-RANGE 10–20 SPX points,
   wider preferred. ADAPTED to our universe by index-level scaling: SPY/QQQ/IWM wings = $2
   (≈ 15–20 SPX pts ÷ 10, rounded to a listed strike); single names: nearest listed width to
   0.30% of spot. Published alternative (recorded, not default): wings at "magnet ± expected
   move" (FlashAlpha).
6. **Price/risk-reward gate:** "The sweet spot for me is 6-8." (risk-to-reward, 0-DTE.com), and
   "Your 15 wide spread that only costs $1 will have a greater probability of profit than one
   that has a cost of $2.50. The former risk to reward is 14, while the latter is 5."
   (0-DTE.com). → require (width − debit)/debit ≥ 6, i.e. debit ≤ width/7. Skip if the market
   won't fill at that debit.
7. **Structure:** long butterfly, 1 × long lower wing / 2 × short body at the max-OI strike /
   1 × long upper wing, calls (or the put equivalent; same payoff). **LOUD NOTE:** FlashAlpha's
   literal sentence is "Buy the magnet strike straddle, sell the wings (magnet ± expected
   move)." - taken literally that is a SHORT butterfly, which contradicts the same article's own
   exit rule ("If price converges to within $0.25 of the magnet strike ... take 70% of max
   profit"), a rule only coherent for a position that profits AT the pin. We implement the
   payoff-consistent reading (long fly / long iron fly bodied at the magnet), tag ADAPTED.
8. **Regime / IV gate:** none published in any source read. UNKNOWN - recorded as no gate.
   FOMC-day exclusion is ours (PLATFORM-POLICY): the 14:00 ET decision sits exactly at the
   published entry window and afternoon pinning claims presuppose no scheduled macro shock.

## 4. EXACT EXIT RULES

These OVERRIDE all platform exit doctrine for this strategy.

1. **Profit take:** "If price converges to within $0.25 of the magnet strike with 30+ minutes
   left, take 70% of max profit and close." (FlashAlpha). The $0.25 convergence band is
   ETF/SPY-scale; scale to the underlying: ADAPTED as |spot − body| ≤ 0.125 × wing width
   (= $0.25 on a $2-wing ETF fly). Take-profit price = 0.70 × (width − debit) over debit.
2. **Failure stop:** "If price breaks beyond the call wall or put wall, the pin has failed. Exit
   the butterfly at market." (FlashAlpha). ADAPTED mapping: our wall = the fly's wing strikes;
   spot trading through either wing (1-min close beyond wing strike) → exit at market.
3. **Setup-deterioration exit:** published as "If it drops below 50 (e.g., a large block trade
   shifts OI), exit - the setup has deteriorated." (FlashAlpha, about their proprietary
   pin_score). UNIMPLEMENTABLE as published (proprietary composite). ADAPTED equivalent: if the
   max-OI strike among in-band strikes migrates away from our body strike on an intraday OI/
   volume refresh, exit at market. No numeric threshold invented - migration is binary.
4. **Time exit / hold-to-expiry doctrine:** otherwise hold to the close - the anomaly pays at
   the closing bell: clustering is measured at "the closing prices of stocks with listed
   options" (NPP abstract); GJ's shift is "from Thursday PM to expiration Friday PM" with the
   last 30 minutes carrying the largest share. No published early time-stop exists. Shadow
   settles at 16:00 ET intrinsic value against the closing mark (PLATFORM-POLICY; avoids
   physical-settlement ambiguity when the close lands exactly on the body strike).
5. **Roll rules:** none published. Not applicable at 0 DTE.

## 5. SIZING CONVENTION IN SOURCE

- 0-DTE.com sizes per-spread by debit at risk (risk-to-reward framing; no account-percent rule
  published in the article read).
- FlashAlpha publishes no per-spread sizing rule; its risk-management section carries only
  generic guidance ("Use defined-risk structures", size to the structure's max loss, ~1-2% of
  account per trade).
- Options Cafe (morning ATM iron-fly variant, for context): "Position size: 1 contract per
  $6,000 of account. Max risk per trade is roughly $1,000."
- **Our shadow:** always 1 published unit (1 × 1/-2/1 fly), account-blind, per platform
  convention.

## 6. DOCUMENTED PERFORMANCE

Anomaly-level (academic):

- "On each expiration date, the returns of optionable stocks are altered by an average of at
  least 16.5 basis points, which translates into aggregate market capitalization shifts on the
  order of $9 billion." [verified-primary - NPP abstract; conclusion refines to "$9.1 billion
  per expiration date" and "at least two percent of optionable stocks have their returns
  changed"]
- "more than 19 percent of optionable stocks close within $0.25 of a strike price on option
  expiration Fridays while less than 18 percent do so on the Fridays before and after
  expiration" ; z-statistic 8.15. [verified-primary - NPP Section 3.1]
- Sample: 80 expiration dates, January 1996–August 2002; ~2,500 optionable stocks.
  [verified-primary]
- Futures pinning: expected 15% within $0.375 of the ATM strike under uniformity; observed
  pinning from above 6.62% + from below 14.71% (= 21.33%) full sample (Nov 1992–Nov 2009);
  22.47% in the short sample (Oct 1998–Nov 2009). Shift "of at least 11.00 bps from Thursday PM
  to expiration Friday PM", ≥$115M notional per expiration ($240M short sample), of which
  "$59 million shifts solely within the last 30 min of trading" ($105M short sample).
  [verified-primary - GJ Section 5]
- Caveat [verified-primary]: NPP measure *price distortion*, not strategy P&L; NPP explicitly
  leave a tradable strategy to "future research."

Strategy-level (practitioner; no audited track record found for the afternoon max-OI pin fly):

- Pin frequency for the fly as constructed: "you will experience a pinned trade about 10-15% of
  the time" at the >67% PoT entry distance, against a 6–8:1 (up to 14:1) payoff.
  [verified-primary - 0-DTE.com article, self-reported, no sample size given]
- Win rate / PF / CAGR / max drawdown for THIS exact form: **UNKNOWN - not published in any
  source read.**
- Adjacent variant for calibration only (morning ATM 30-wide SPX iron fly, NOT this strategy):
  2024: "168 trades with a 77% win rate", "$5,079 of profit" on $6,000, "431% on the test
  account" annualized; 2025: "gave back $5,472 in just 86 trades, even with a 78% win rate";
  average loser grew from ~$800 to ~$1,500. [verified-secondary - Options Cafe blog,
  self-reported test account, no audit]

## 7. KNOWN FAILURE MODES

- **Contested index evidence / anti-pinning:** GJ document futures being "pushed away from the
  cost of carry adjusted at the money strike price right before the expiration of options on the
  S&P 500 index" - the sign can flip depending on whose hedges dominate. Mayhew's survey (quoted
  in NPP fn. 4): little evidence of systematic index expiration price effects. The ETF leg may
  simply have no edge.
- **Trend/breakout afternoons:** a directional afternoon (macro headline, index rebalance, MOC
  imbalance) runs spot through a wing; the published wall-break stop exists precisely because of
  this. Max loss is capped at debit, but at a 10–15% pin rate long loss streaks are the norm - 
  binomial math, not a malfunction (25+ consecutive losers is unremarkable at p≈0.125).
- **Sample-era decay:** NPP's sample is 1996–2002 - eighths/sixteenths ticks, pre-decimalization
  (2001), pre-penny-strikes, pre-algorithmic MM. The 16.5 bps distortion is not a current-market
  measurement. GJ end in 2009. Nothing academic covers the 0DTE era.
- **Dealer-positioning regime flips:** the pin claim assumes dealers are net long gamma at the
  max-OI strike. NPP found market makers net-purchased on only 62% of stock-dates; when dealers
  are net short gamma the same mechanics *amplify* moves away from the strike (accelerant, not
  magnet). No public feed tells us the sign on a given day - this is the strategy's biggest
  unhedgeable model risk.
- **Scheduled-event afternoons:** FOMC 14:00 ET decisions land inside the entry window;
  CPI/NFP are morning prints but set trend days. (Feb-2018 Volmageddon / Mar-2020 / Aug-2024
  style vol spikes are less lethal here than for short-vol families - the fly is long-premium,
  defined-risk - the loss is the debit, but pin probability collapses.)
- **Win-rate illusion (variant evidence):** the Options Cafe iron-fly log shows a stable ~77–78%
  win rate while average losses nearly doubled (2024→2025) - grade this family on expectancy and
  tail losses, never on win rate.
- **Early assignment / settlement edge case:** the short body legs are exactly ATM at expiry by
  design. On ETFs/single names (physical delivery), a close pinned to the body strike makes
  assignment on the shorts genuinely ambiguous. Real-world doctrine would be to close before the
  bell; our shadow cash-settles at the 16:00 mark (PLATFORM-POLICY), which slightly flatters the
  strategy vs. reality - noted for grading honesty. SPX-style cash settlement (not in our
  universe) would not have this issue.
- **Max-pain fallacy risk:** max-OI ≠ guaranteed magnet. NPP's clustering is an average 1.3%
  excess propensity, not a determinism; most expiration days do NOT pin to the max-OI strike.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | `dte` | 0 (same-day expiry; single names: their expiration Friday) | SOURCE-VERBATIM | "The purest pin play is a 0DTE butterfly centered at the magnet strike." (FlashAlpha); NPP: clustering "on expiration dates" |
| 2 | `entry_window_start_et` | 14:00 ET (final 2 hours) | SOURCE-VERBATIM | "Condition: `pin_risk.pin_score > 70` and `time_to_close_hours < 2`." (FlashAlpha) |
| 3 | `entry_window_end_et` | 15:00 ET | PLATFORM-POLICY | not published; leaves ≥30 min for the published profit-take rule ("with 30+ minutes left") to be reachable |
| 4 | `center_strike_rule` | strike with max same-expiration call+put OI within the proximity band | ADAPTED | published composite unreproducible: "OI concentration in top 3 strikes (30% weight), proximity to highest-GEX strike (25%), time remaining (25%), and gamma magnitude (20%)" (FlashAlpha) |
| 5 | `oi_snapshot` | morning-of OCC open interest (Tradier chain OI field) | ADAPTED | GJ convention: "at the money open interest is measured on the Thursday before expira tion with respect to the at the money strike price on the expiration Friday" - prior-day OI vs expiry-day strikes; morning-of is the 0DTE equivalent |
| 6 | `pot_entry_gate` | nearest fly strike PoT > 67% (ideal 70–80%) | SOURCE-VERBATIM | "the ideal probability of touch measure when entering a fly, is that the nearest strike is > 67% Probability of Touch (PoT) ... 70-80% seems ideal" (0-DTE.com) |
| 7 | `pot_delta_proxy` | PoT ≈ 2 × delta → nearest-strike delta ≥ 0.34 | SOURCE-VERBATIM | "the PoT is approximately 2X the delta of a strike." (0-DTE.com) |
| 8 | `wing_width_spx_pts` | range 10–20 SPX pts, wider preferred; documented default 15–20 | SOURCE-RANGE | "A 15 wide fly has a much greater chance at a pin than a 10 wide, and a 20 wide a better chance than a 15." (0-DTE.com) |
| 9 | `wing_width_etf` | SPY/QQQ/IWM: $2 | ADAPTED | index-scale conversion of row 8 (≈15–20 SPX pts ÷ 10 → nearest listed $ strike); no published ETF width found |
| 10 | `wing_width_single_name` | nearest listed width ≥ 0.30% of spot | ADAPTED | no published single-name width; 0.30% ≈ 15–20 SPX pts on a ~6000 index, price-scaled |
| 11 | `wing_alt_rule` (recorded, not default) | wings at body ± expected move | SOURCE-VERBATIM | "sell the wings (magnet ± expected move)" (FlashAlpha); EM proxy if used: ATM straddle mid (ADAPTED) |
| 12 | `min_reward_risk` | ≥ 6 (sweet spot 6–8) → `max_debit` ≤ width/7 | SOURCE-VERBATIM | "The sweet spot for me is 6-8." ; "The former risk to reward is 14, while the latter is 5." (0-DTE.com); width/7 algebra is ours (ADAPTED derivation) |
| 13 | `structure` | long fly 1/-2/1, body at center strike (calls or puts) | ADAPTED | FlashAlpha's literal "Buy the magnet strike straddle, sell the wings" is a short fly and contradicts their own pin-profit exit; implemented payoff-consistent (see §3.7) |
| 14 | `profit_take_frac` | 0.70 × max profit | SOURCE-VERBATIM | "take 70% of max profit and close" (FlashAlpha) |
| 15 | `profit_take_convergence_band` | \|spot − body\| ≤ $0.25 (ETF scale); other scales: 0.125 × wing width | SOURCE-VERBATIM + ADAPTED scale | "If price converges to within $0.25 of the magnet strike with 30+ minutes left" (FlashAlpha; ticker scale unstated in the pin section) |
| 16 | `profit_take_min_time_left` | ≥ 30 minutes to close | SOURCE-VERBATIM | "with 30+ minutes left" (FlashAlpha) |
| 17 | `stop_rule` | spot breaks beyond a wing strike → exit at market | SOURCE-VERBATIM + ADAPTED (wall→wing) | "If price breaks beyond the call wall or put wall, the pin has failed. Exit the butterfly at market." (FlashAlpha) |
| 18 | `setup_deterioration_exit` | max-OI in-band strike migrates off our body → exit | ADAPTED | published form proprietary: "If it drops below 50 ... exit - the setup has deteriorated." (FlashAlpha pin_score); numeric composite UNKNOWN |
| 19 | `time_exit` | hold to close; settle 16:00 ET intrinsic vs closing mark | ADAPTED / PLATFORM-POLICY | anomaly pays at "the closing prices" (NPP abstract); GJ: largest shift in "the last 30 min of trading"; cash-settle convention ours |
| 20 | `iv_regime_gate` | none | UNKNOWN | no IV/VIX gate published in any source read |
| 21 | `fomc_gate` | no entry on FOMC decision days | PLATFORM-POLICY | 14:00 ET decision sits inside the published entry window; ours |
| 22 | `earnings_gate` | single names: no entry if earnings between entry and expiry (incl. same-day AMC) | PLATFORM-POLICY | ours; pin mechanism presupposes no scheduled idiosyncratic shock |
| 23 | `expected_pin_rate` (context, not a gate) | 10–15% | SOURCE-VERBATIM | "you will experience a pinned trade about 10-15% of the time" (0-DTE.com) |
| 24 | `liquidity_gates` | leg bid ≥ $0.05; leg spread ≤ 10% of mid or ≤ $0.05; leg OI ≥ 100 | PLATFORM-POLICY | ours; standard platform funnel gates |
| 25 | `size` | 1 published unit (1/-2/1), account-blind | PLATFORM-POLICY | platform shadow convention |

## 9. DATA REQUIREMENTS

- **Tradier chains:** DTE = 0 band only (same-day expiration; on single names, Friday weekly at
  DTE 0). Needed fields: per-strike OI (calls+puts, morning snapshot AND an intraday refresh for
  the migration exit), bid/ask, delta (for the PoT ≈ 2×delta gate). Note Tradier OI is a daily
  (OCC overnight) value - the intraday "migration" check can only use volume + fresh chain pulls;
  document that limitation in grading.
- **1-min bars:** required 14:00–16:00 ET for the underlyings - the convergence band (row 15),
  wing-breach stop (row 17), and settlement mark all key off them. Existing intraday cache
  (Alpaca 1-min, runtime/intraday_cache) covers this.
- **FOMC calendar:** required (hard gate, row 21). CPI dates: not gated (morning print), but log
  as covariate.
- **Earnings calendar (date + bmo/amc):** required for the single-name leg (row 22).
- **VIX regime / IV rank:** NOT required by published rules (row 20 UNKNOWN/none). Log VIX
  percentile as a covariate only (our IV archive is cold → VIX-percentile fallback per platform
  standard).
- **Daily history:** only for covariate logging and the 0.30% single-name wing computation.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** ETF leg - 3 tickers × ~21 sessions, gated by (a) max-OI strike
  inside the >67%-PoT band at 14:00, (b) debit ≤ width/7 fill, (c) FOMC-day skips; rough pass
  rate 40–60% → ~25–35/month. Single-name leg - 6 names × ~4 expiration Fridays × similar gates
  → ~5–10/month. **Planning number: ~30/month combined** (range 20–40). At that cadence the
  N≥25/lane verdict threshold is reachable in roughly 1 month per lane if ETF and single-name
  legs are graded as separate lanes (recommended - their provenance quality differs sharply, see
  §1 warning).
- **Mark cadence:** 1-min marks on the underlying 14:00–16:00 ET; option-leg NBBO marks at entry,
  at any exit trigger, and at 15:55; settlement = intrinsic at the 16:00 close. The three-fill
  ledger convention applies at entry and any pre-close exit.
- **Multi-leg shape:** 3 legs / 4 contracts, 1 × +1 lower call, 2 × −1 body call, 1 × +1 upper
  call (ratio 1/-2/1). Same-expiry, single-class. No stock legs, no hedging.
- **Capital-at-risk basis:** **debit paid** (long fly; max loss = debit by construction). If the
  iron-fly form is ever run instead, CaR = width − credit. Reg-T proxy not needed.
- **Account-blind 1-lot distortions:** minimal - the published practitioner form is already
  per-spread and defined-risk. Two honest distortions to carry into grading: (1) our 16:00
  cash-settlement flatters reality vs. the real-world need to close physical-delivery flies
  before the bell (pin-on-body assignment ambiguity, §7); (2) 0DTE fly quotes are wide and
  fast-moving in the final hours - fills at mid are optimistic; use the platform's WORST-grade
  fill convention on all three ledgers.
- **Grading caution:** with a published pin rate of 10–15%, the per-trade win indicator is
  nearly useless at N=25; grade on expectancy (mean P&L / debit) and on whether pin frequency
  at the body beats the no-skill baseline implied by the entry-time straddle-implied
  distribution.

## 11. VERIFICATION

**Verdict: CORRECTED (minor).** Adversarial verification pass, 2026-07-19, fresh-context verifier.

**What was checked and how:**
- **NPP 2005** - the cited full-text PDF (optionsoffice.ru mirror, working paper dated
  2004-08-27, 53 pp.) was downloaded and text-extracted locally. Located verbatim: the 16.5 bps
  / "$9 billion" abstract sentence; the ">19% within $0.25 on expiration Fridays vs <18%
  before/after" finding with z-statistic 8.15; 80 expiration dates Jan 1996–Aug 2002 and
  "roughly 2,500 optionable stocks"; footnote 4's Mayhew (2000, p. 32) quote "there is little
  evidence of a strong, systematic price effect around expiration"; the conclusion's
  "future research ... abnormal profits after trading costs" passage; "$9.1 billion per
  expiration date"; "at least two percent of optionable stocks"; the ~1.3% excess propensity;
  market makers net purchased on 62% of stock-trade-date pairs. All match.
- **Golez–Jackwerth 2012** - the cited d-nb.info full text (20 pp.) downloaded and
  text-extracted. Located verbatim: the abstract's "pushed away from the cost of carry adjusted
  at the money strike price ... (anti cross pinning)"; "An amazing $59 million shifts solely
  within the last 30 min of trading" (+$105M short sample) in Section 5; 15%-under-uniformity
  vs 6.62% above + 14.71% below (22.47% short sample); "shift of at least 11.00 bps from
  Thursday PM to expiration Friday PM"; ≥$115M/$240M notional; the Section 4.2 Thursday-OI
  measurement convention sentence. All match, including section attributions.
- **0-DTE.com (Varitimos, 2022-08-14)** - fetched live; all seven quoted constants (>67% PoT,
  10–15% pin rate, 70–80% ideal, PoT ≈ 2× delta, 15-vs-10-vs-20-wide, "sweet spot for me is
  6-8", the 14-vs-5 risk-to-reward example) confirmed VERBATIM.
- **FlashAlpha (Dobrowolski, 2026-03-20)** - fetched live; pin_score>70 & <2h condition, "purest
  pin play" sentence, $0.25/30-min/70% profit take, wall-break stop, drops-below-50 exit, and
  the literal "Buy the magnet strike straddle, sell the wings" sentence all confirmed VERBATIM
  (the brief's §3.7 short-fly contradiction note is accurate). The magnet composite is a
  components TABLE (30/25/25/20 with "top 3 strikes" / "highest-GEX strike" phrasing), not one
  sentence - brief corrected to say so.
- **Options Cafe** - fetched live; 2024 168 trades / 77% / $5,079 / 431%-annualized, 2025
  −$5,472 in 86 trades at 78%, avg loser ~$800→~$1,500, 1-contract-per-$6,000 sizing, 9:45 ET
  entry, 30-point wings - all confirmed.

**Corrections applied (both minor, non-load-bearing):**
1. §3.3 / context of table row 4: FlashAlpha composite re-labeled as a compressed rendering of
   their components table rather than a direct quote (all weights and phrases are genuine).
2. §5: "FlashAlpha publishes no sizing" tightened to "no per-spread sizing rule; generic
   defined-risk/~1–2% guidance only."

**No invented constants found.** Every SOURCE-VERBATIM/SOURCE-RANGE constant in §§3, 4, 8 was
located in its cited source; every ADAPTED tag carries a real rationale and none is presented
as published; every [verified-*] performance number in §6 was found in its stated source.

**Residual doubts:** (1) GJ's serial-expiration sample excludes October 2008 (their Table 1
note) - the brief's "Nov 1992–Nov 2009" elides this; immaterial to any rule. (2) The two
practitioner sources are unaudited self-reports; the brief already flags this. (3) The
academic-vs-0DTE era gap and contested index evidence are correctly and loudly disclosed in
§§1, 7 - the brief's honesty about what is NOT academically supported (the ETF 0DTE leg) is
accurate as written.
