# Strategy Brief: bfly_iron_butterfly

Researched 2026-07-19. Primary source READ in full (all 11 pages of the methodology PDF downloaded and text-extracted; quoted verbatim below). Every constant in sections 3, 4, 8 carries a direct quote or is marked UNKNOWN. Sister strategy of `cndr_iron_condor_hold` (same Cboe methodology family, same roll mechanics; BFLY strikes are **price-based**, not delta-based - no Black-formula/greeks dependency at all).

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `bfly_iron_butterfly`
- **Provenance class:** CBOE-index
- **PRIMARY citation:**
  - URL: https://cdn.cboe.com/api/global/us_indices/governance/BFLY_Methodology.pdf
  - Title: *Cboe S&P 500 Iron Butterfly Index METHODOLOGY* (Cboe Global Indices, LLC)
  - Version 4.1, Last Revised Date November 27, 2025 (Appendix 2 – Document Information)
  - Index facts from §5: Base Date **June 20, 1986**, Launch Date **August 3, 2015**, Base Value **100**, Currency USD. Base date/value cross-checked against Cboe's own historical chart API (first point `1986-06-20 = 100.000000`) [verified-primary].
- **INDEPENDENT secondary source (independent authors; study commissioned by CBOE - caveat noted):**
  - URL: https://s202.q4cdn.com/174824971/files/doc_news/2016/02/study-analyzes-performance-of-cboe-spx-options-selling-indexes-pdf1691637391968.pdf
  - Title: CBOE News Release, *"Study Analyzes Performance of CBOE S&P 500 (SPX) Options-Selling Indexes"* (February 23, 2016), announcing the study *"Performance Analysis of CBOE S&P 500 Options-Selling Indices"* co-authored by Keith Black, Ph.D., CAIA, CFA (CAIA Association) and Edward Szado, Ph.D., CFA (Providence College / INGARM). Covers BFLY over "the 29½-year period from mid-1986 to the end of 2015." Press release READ in full; the underlying full paper was not located free-of-paywall.
  - 2022 update (paywalled, abstract only): Black & Szado, *"35-Year Performance Analysis of Cboe S&P 500 Option-Selling Indices,"* The Journal of Index Investing / Journal of Beta Investment Strategies, August 2022 - https://jii.pm-research.com/content/early/2022/08/22/jbis.2022.1.013
- **Additional secondary (Cboe-authored, separate document - NOT independent):**
  - https://www.cboe.com/insights/posts/benchmark-indices-series-volatility-management-with-cboes-bfly-and-cndr-indices/ - *Benchmark Indices Series: Volatility Management with Cboe's BFLY and CNDR Indices*, Cboe Insights, July 26, 2021. READ (fetched 2026-07-19).
- **Publication dates:** Index base date 1986-06-20 (back-cast); index launch 2015-08-03; methodology doc v4.1 revised 2025-11-27; secondary sources 2016-02-23, 2021-07-26, 2022-08.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**What the source trades:** SPX (S&P 500 Index) options only - European-style, cash-settled, **AM-settled** standard monthlies. §1.1: "All SPX options involved are AM-settled and roll on a monthly basis. All option positions are one unit." Plus a 4-week T-bill collateral account (see §5 of this brief).

**Our mapping:** SPY / QQQ / IWM as the core tier (index-proxy ETFs - closest analog to the published SPX edge claim), with the liquid mega-cap tier (AAPL / NVDA / MSFT / TSLA / AMD / META) as an optional extension, graded separately.

**LOUD ADAPTATIONS (structural, unavoidable on our platform):**
1. **Settlement style:** SPX monthlies are European, cash-settled against the third-Friday-morning SOQ (§2.2: "Against the Special Opening Quotation (SOQ) of the SPX Index"). SPY/QQQ/IWM and single-stock options are **American, PM-settled, physically delivered**. Our shadow holds to expiration and cash-settles legs at intrinsic value vs. the official 4:00 p.m. ET close on expiration Friday - no physical delivery in a shadow, no stock legs ever. Tagged ADAPTED in §8.
2. **Early-assignment exposure:** American style means short ITM legs can be assigned early. For an iron BUTTERFLY this is far more acute than for a condor: the short body straddles the money, so **one short leg is virtually always ITM** for most of every monthly hold. Worst case: short ITM call through an ex-dividend date - and SPY/QQQ/IWM quarterly ex-div dates typically fall ON the third-Friday expiration of Mar/Jun/Sep/Dec, i.e. on our settlement day. The published European form cannot experience any of this. The shadow does not model assignment; it is a known divergence documented in §7.
3. **Roll-day overlap:** in the published form the old options settle at the Friday-morning SOQ and the new position is entered 11:00 a.m. the same day - no overlap. Under PM settlement, our old fly is alive until the 4:00 p.m. close while the new fly opens at 11:00 a.m. - a ~5-hour same-symbol overlap on every roll date. Logged, unavoidable artifact of the AM→PM adaptation.
4. **Single-name tier caveat:** BFLY's edge claim is an *index* volatility-risk-premium claim (short ATM straddle + bought wings). Single stocks carry earnings-gap risk inside every monthly hold and the source has no event gate (see §3). The mega-cap tier therefore tests an *extension* of the published claim, not the claim itself. Grade the tiers separately.

**Why the mapping preserves the edge claim:** the core-tier ETFs track the same (or analogous) broad indices, so the same index variance-risk premium is being sold; the strike rules are pure percentages of spot ("ATM body, 5% OTM wings") and transfer to any underlying without renumbering - no delta model needed; monthly third-Friday expirations exist on all mapped symbols; and the published form has **no stock legs and no delta-hedging**, so no options-only surgery is required - the four-leg defined-risk shape carries over exactly.

## 3. EXACT ENTRY RULES

**Trigger:** unconditional - a new iron butterfly is opened every monthly roll date. There is no signal, no IV gate, no regime filter anywhere in the methodology. §2.3: "Rebalances are performed with monthly frequency". The absence of any gate is itself the published rule.

- **Roll/entry date (§2.3):** "The third Friday of each month. Should the third Friday fall on an exchange holiday, the roll date is the preceding Business Day." Strike Determination column: "Roll Date".
- **Structure (4 legs, §1.1):** "(1) sells a monthly At-the-Money (ATM) SPX Put and SPX Call option, (2) buys a monthly 5% Out-of-the-Money (OTM) SPX Put option, expiring at the next standard expiration, to reduce the risk, (3) buys a monthly 5% Out-of-the-Money (OTM) SPX Call option, expiring at the next standard expiration, to reduce the risk". (Leg (4) is the T-bill account - see §5.)
- **Strike-selection algorithm (§2.1 constituents table)** - price-based, no deltas:
  - Short ATM Call (position −1): "First listed strike above the last disseminated value of the S&P 500 Index (SPX Index) before 11:00 a.m. ET."
  - Short ATM Put (position −1): "First listed strike above the last disseminated value of the S&P 500 Index (SPX Index) before 11:00 a.m. ET." - **identical wording to the call: both short legs share ONE body strike, the first listed strike ABOVE spot.** This is a true iron butterfly with a common body, sited just above the money (the short put starts slightly ITM, the short call slightly OTM).
  - Long 5% OTM Call (position +1): "First available strike above 105% of the last disseminated value of the SPX Index before 11:00 a.m. ET."
  - Long 5% OTM Put (position +1): "First available strike below 95% of the last disseminated value of the SPX Index before 11:00 a.m. ET."
  - Both wings round AWAY from the money (call wing up, put wing down), so each wing is ≥5% of spot from the reference price. Because the body sits above spot, the put-side width (K_atm − K_put5) is structurally a touch wider than the call-side width (K_call5 − K_atm).
- **DTE selection (§2.1 table, Expiration column):** "1 month" for all four options - the next standard monthly expiration, entered on the third Friday for the following month's third-Friday expiry (~28–35 calendar days). §1.1: "expiring at the next standard expiration".
- **Entry timing (§2.1):** "the strike prices of the option positions are selected before 11 a.m. on roll dates." §3.2: new options are "deemed purchased and sold (11:00 a.m. ET)". The T-bill account "is set up at 11:00 a.m. ET on roll dates" (§2.1).
- **Entry fill price (§2.2, Option Premium Determination):** "At the average of the last bid-ask quote of the applicable option before 11:00 a.m. ET." (mid-quote at ~11:00 a.m. ET, per leg). Quote source (§2.4): "The option quotes are sourced from the Cboe Options Exchange via the Options Price Reporting Authority (OPRA) feed."
- **Published regime/IV gate:** NONE. No VIX, IV-rank, trend, or event condition appears anywhere in the document.

## 4. EXACT EXIT RULES

These OVERRIDE all platform exit doctrine for this strategy.

- **Hold-to-expiry doctrine (§2 / §3.3):** positions are never touched intra-month. §2: "On subsequent roll dates, the old options settle and the money market account is liquidated. New option positions are entered following the same rules as on the initial roll date." §3.3: "On roll dates, the Index will not be disseminated intraday." No earlier exit of any kind exists in the methodology.
- **Settlement (§2.2):** "Against the Special Opening Quotation (SOQ) of the SPX Index." Settlement payoffs per §3.2: "Put5_old_settle = Max (0, K put_5_old – SOQ t)"; "Put_atm_old_settle = Max (0, K put_atm_old – SOQ t)"; "Call5_old_settle = Max (0, SOQ t – K call_5_old)"; "Call_atm_old_settle = Max (0, SOQ t – K call_atm_old)". ADAPTED for our universe: legs settle at intrinsic vs. the official 4:00 p.m. ET close on expiration Friday (PM-settled ETFs/stocks have no SOQ).
- **Profit target:** NONE published. The methodology contains no profit-taking rule.
- **Loss management / stop:** NONE published. Loss is bounded structurally by the 5% wings; the worst payoff is "Max (K Call_5% - K Call_atm, K Put_atm - K Put_5%)" (§2.1; subscripts flattened by text extraction - in the doc they are K<sub>Call_5%</sub>, K<sub>Call_atm</sub>, K<sub>Put_atm</sub>, K<sub>Put_5%</sub>).
- **Roll rule:** expiration morning IS the roll - old position settles at the open (SOQ), new position entered same day at 11:00 a.m. ET. No mid-cycle rolling or adjustment exists.
- **Notation flag (honesty item):** §3.2's T-bill formula is printed as "M_new_t = Max(K_Call_10 − K_Call_5, K_Put_5 − K_Put_10) ∗ 10" - the `_10` subscripts appear to be a copy-editing slip (there are no 10%-strike legs anywhere in BFLY; §2.1 defines the worst payoff with atm/5% subscripts). We implement the §2.1 form. Do not invent a 10% wing from this typo.

## 5. SIZING CONVENTION IN SOURCE

Fully collateralized, index-style: one unit of each option leg against a T-bill account sized to ten times the worst possible payoff. §1.1: "All option positions are one unit." §2.1: "To provide a downside limit of negative return of the Index, a Treasury bill account with initial cash that equals ten times the worst possible payoff of the new option positions is set up at 11:00 a.m. ET on roll dates. The Treasury bill account is designed such that the worst possible payoff from final settlement of the new option positions is approximately 10% of the total value of the account." The account holds "4-week treasury bills" (§2) at the USB4WTA rate - §3.1: "USB4WTA is the 4-week Bank discount rate obtained from the website of the U.S. Department of the Treasury"; §3.2: "interest is not accumulated in the Treasury bill account on the roll day." Premium is functionally reinvested: "The Index is a total return index. The dollar value of option premium deemed received from the sold call and put options are functionally reinvested in the index portfolio." (§2).

Recorded for context only - our shadow always runs 1 published unit (one 4-leg butterfly), account-blind.

## 6. DOCUMENTED PERFORMANCE

The primary methodology publishes NO performance figures. Everything below is from secondary sources or derived from Cboe-published index levels; tags on every number.

- **Tail-loss frequency:** "the S&P 500 Index posted 15 months of losses worse than 6 percent during the period, while the CNDR Index logged 10 months of losses worse than 6 percent and the BFLY index two months of losses worse than 6 percent" - July 1986 to December 2015 (29½ years) [verified-secondary - CBOE/Black-Szado press release 2016-02-23, READ].
- **Max drawdown:** "The worst peak-to-trough monthly drawdown losses were … 47.1% for the BFLY Index, compared to 51% for the S&P 500 Index" over ~35 years (1986–2021) [verified-secondary - Cboe Insights 2021-07-26, READ]. Note the tension with the bullet above: BFLY rarely has single BAD months, yet it has ground out a near-S&P-size multi-year drawdown - the damage is slow accumulation, not single-month shocks.
- **Extreme-month behavior:** in the 11 months when the S&P 500 moved more than 10%, "neither the CNDR nor the BFLY indices rose or fell by 10% or more"; BFLY "had fewer monthly increases or decreases of more than 6% than the S&P 500 Index" [verified-secondary - Cboe Insights 2021-07-26].
- **Index level (raw, primary data):** BFLY = **405.39** as of 2026-07-17 (Cboe delayed-quote API `_BFLY.json`, fetched 2026-07-19) vs. base **100** on 1986-06-20 [verified-primary - Cboe data APIs + §5 of methodology].
- **Derived long-run CAGR ≈ 3.55%/yr** over the 40.08 years 1986-06-20 → 2026-07-17 ((405.39/100)^(1/40.08) − 1). [unverified - OUR computation from verified index levels; no source documents this number. Recorded for grading context only, never to be cited as a published figure.] For scale, the CNDR brief's secondary source put S&P 500 buy-and-hold at ~10.5% annualized over a similar span - BFLY's total-return index has badly lagged the underlying.
- **Alpha claim (2022 study):** "All six of the Cboe option-writing indices generated positive alpha over the period of study" [unverified - seen only in search-result snippets of the paywalled Journal of Beta Investment Strategies abstract; not read directly. Do not rely on it.]
- **CAGR (published): UNKNOWN. Win rate: UNKNOWN. Profit factor: UNKNOWN. Per-trade statistics: UNKNOWN.** None of these appear in any source I actually read.

**Methodology caveats:** (a) everything before the 2015-08-03 launch is back-tested - primary-source disclosure: "Index and benchmark values for dates or time periods prior to an index launch date, if any, are calculated using a theoretical approach involving back-testing historical data in accordance with the methodology in place on the launch date" [verified-primary]; (b) index returns are damped ~10× by the T-bill collateral convention (worst payoff ≈ 10% of account, §2.1) - raw per-butterfly P&L is roughly 10× swingier than the index return series; (c) fills are frictionless mid-quotes with no commissions/slippage - a 4-leg ATM structure re-entered monthly is exactly where real spread-crossing costs bite hardest.

## 7. KNOWN FAILURE MODES

**Named historical episodes** (short-vol family; BFLY's wings cap each month's loss at the published worst-payoff, so these are capped-loss months, not blowups - but the ATM body means loss months are far more FREQUENT than for a 20Δ condor):
- **Oct-1987 crash** - inside the back-cast window; a >5% down month realizes ~full put-wing width. [episode-level P&L: unverified; structural consequence of the payoff]
- **Feb-2018 "Volmageddon"** - the monthly fly entered 2018-01-19 carried the Feb 5 VIX spike and an SPX cycle move beyond the body. [episode-level P&L: unverified]
- **Mar-2020 COVID crash** - the 2020-02-21 → 2020-03-20 cycle fell ~30%+, far through the 5% put wing → worst-payoff month. [episode-level P&L: unverified; structural]
- **Aug-2024 vol spike (Aug 5)** - deep intra-cycle mark drawdown; SPX largely recovered by the 2024-08-16 expiry, illustrating that with NO stop (§4) the strategy rides mark pain to settlement, for better and worse. [unverified]
- **Melt-up months** - any month where the index rallies >~ the credit received hurts, and a >5% rally realizes ~full call-wing width (e.g. the strong 2020-2021 rebound months). An ATM butterfly loses in calm relentless rallies, not just crashes. [structural, follows from payoff]
- **Slow-grind edge decay** - the documented profile (§6) is few extreme months but a 47.1% peak-to-trough drawdown and a ~3.5%/yr derived CAGR badly lagging the S&P: death by a thousand paper cuts when realized monthly moves persistently exceed the ATM straddle credit. Grading should treat "premium no longer pays for the realized move" as the base case to disprove.

**Structural failure modes on OUR mapping (not present in the published SPX form):**
- **Early assignment through ex-div** on the short ITM call - American exercise; the ATM body makes a short ITM leg the NORM, not the exception; SPY/QQQ/IWM quarterly ex-div dates typically fall on the Mar/Jun/Sep/Dec third-Friday expiration itself, so deep-ITM short calls face assignment the night before. The shadow does not model assignment; flag every cycle where the short call is ITM approaching an ex-div date.
- **Earnings gap-through-strikes** for the mega-cap tier: every monthly hold contains at most one earnings date with no published gate; a gap through a wing realizes ~full width. Extension risk, not part of the published claim.
- **PM vs. AM settlement:** expiration-day price action (which the SPX form never sees past the morning SOQ) is in scope for our version through the 4:00 p.m. close - including expiry-day pinning dynamics around the body.
- **Pin risk exactly at the body** - the body strike is chosen to hug spot, so finishing within a hair of the short strike is common; shadow settles at intrinsic vs. official close, real trading would face assignment ambiguity.
- **Roll-day overlap** (adaptation #3 in §2): ~5 hours of doubled exposure on every roll Friday.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | underlying_universe | SPY, QQQ, IWM (core); AAPL, NVDA, MSFT, TSLA, AMD, META (extension tier, graded separately) | ADAPTED | Source trades SPX only (§1.1: "sells a monthly At-the-Money (ATM) SPX Put and SPX Call option"); mapped per §2 of this brief |
| 2 | structure | 4-leg iron butterfly: short ATM call + short ATM put at a COMMON body strike, long 5% OTM call wing, long 5% OTM put wing; net credit | SOURCE-VERBATIM | §1.1: "(1) sells a monthly At-the-Money (ATM) SPX Put and SPX Call option, (2) buys a monthly 5% Out-of-the-Money (OTM) SPX Put option … (3) buys a monthly 5% Out-of-the-Money (OTM) SPX Call option" |
| 3 | body_strike_rule (short call AND short put - one shared strike) | first listed strike ABOVE the reference price | SOURCE-VERBATIM | §2.1 table, both short legs: "First listed strike above the last disseminated value of the S&P 500 Index (SPX Index) before 11:00 a.m. ET." |
| 4 | call_wing_strike_rule | first available strike ABOVE 105% of the reference price (rounds away from the money) | SOURCE-VERBATIM | §2.1 table: "First available strike above 105% of the last disseminated value of the SPX Index before 11:00 a.m. ET." |
| 5 | put_wing_strike_rule | first available strike BELOW 95% of the reference price (rounds away from the money) | SOURCE-VERBATIM | §2.1 table: "First available strike below 95% of the last disseminated value of the SPX Index before 11:00 a.m. ET." |
| 6 | reference_price | published: last disseminated SPX value before 11:00 a.m. ET → ours: last trade of the mapped underlying before 11:00 a.m. ET | ADAPTED | §2.1: "the last disseminated value of the S&P 500 Index (SPX Index) before 11:00 a.m. ET"; ETFs/stocks have trades, not index dissemination - we substitute last trade before 11:00 a.m. ET |
| 7 | roll_date | third Friday of each month; if exchange holiday, preceding business day | SOURCE-VERBATIM | §2.3: "The third Friday of each month. Should the third Friday fall on an exchange holiday, the roll date is the preceding Business Day." |
| 8 | entry_dte | next standard monthly expiration ("1 month", ~28–35 calendar days) | SOURCE-VERBATIM | §2.1 table, Expiration column: "1 month"; §1.1: "expiring at the next standard expiration" |
| 9 | expiry_type | standard monthlies only (third-Friday cycle); never weeklies | SOURCE-VERBATIM | §1.1: "All SPX options involved are AM-settled and roll on a monthly basis." (ETF monthlies are the PM-settled analog - see row 12) |
| 10 | entry_time | strikes fixed before 11:00 a.m. ET on roll date; position deemed entered at 11:00 a.m. ET | SOURCE-VERBATIM | §2.1: "the strike prices of the option positions are selected before 11 a.m. on roll dates"; §3.2: "deemed purchased and sold (11:00 a.m. ET)" |
| 11 | entry_fill_price | mid: average of last bid-ask before 11:00 a.m. ET, per leg | SOURCE-VERBATIM | §2.2: "At the average of the last bid-ask quote of the applicable option before 11:00 a.m. ET." |
| 12 | settlement_style | published: European AM cash-settle at SPX SOQ → ours: intrinsic vs. official 4:00 p.m. ET close on expiration Friday, cash-settled in shadow, no stock legs | ADAPTED | §2.2: "Against the Special Opening Quotation (SOQ) of the SPX Index." ETF/single-name options are American/PM/physical - adaptation documented in §2 of this brief |
| 13 | exit_rule | HOLD TO EXPIRATION SETTLEMENT - no intra-month exit of any kind (overrides platform exit doctrine) | SOURCE-VERBATIM | §2: "On subsequent roll dates, the old options settle and the money market account is liquidated." No other exit appears anywhere in the document |
| 14 | profit_target | NONE | SOURCE-VERBATIM | No profit-taking rule anywhere in the methodology (documented absence) |
| 15 | stop_loss | NONE (loss bounded only by the 5% wings) | SOURCE-VERBATIM | No stop/adjustment rule in the methodology; worst payoff §2.1: "Max (K Call_5% - K Call_atm, K Put_atm - K Put_5%)" |
| 16 | mid_cycle_adjustments | NONE (no rolling, no re-centering, no defense) | SOURCE-VERBATIM | §3.3: "On roll dates, the Index will not be disseminated intraday. … On non-roll days, the Index follows the non-roll date calculations." - the only position events are roll-date settlement and entry (documented absence) |
| 17 | iv_regime_gate | NONE - enter every roll date unconditionally | SOURCE-VERBATIM | No VIX/IV/trend/event condition appears anywhere in the methodology; §2.3 rebalance is unconditional monthly (documented absence) |
| 18 | event_gate | NONE published; mega-cap-tier holds spanning earnings are FLAGGED (not skipped) so the tiers can be graded separately | PLATFORM-POLICY | Source has no event gate (row 17); flagging is our bookkeeping, entry remains unconditional to preserve the published form |
| 19 | position_size | 1 unit per leg (one butterfly) | SOURCE-VERBATIM | §1.1: "All option positions are one unit." |
| 20 | collateral_convention (context only) | T-bill account = 10 × worst possible payoff; worst payoff ≈ 10% of account; 4-week T-bills at USB4WTA; no interest on roll day | SOURCE-VERBATIM | §2.1: "initial cash that equals ten times the worst possible payoff of the new option positions"; "approximately 10% of the total value of the account"; §3.1: "USB4WTA is the 4-week Bank discount rate obtained from the website of the U.S. Department of the Treasury"; §3.2: "interest is not accumulated in the Treasury bill account on the roll day." Shadow is account-blind, 1 lot - T-bill leg dropped |
| 21 | worst_payoff_formula | Max(K_call_5% − K_call_atm, K_put_atm − K_put_5%) | SOURCE-VERBATIM | §2.1: "Max (K Call_5% - K Call_atm, K Put_atm - K Put_5%)" - implement THIS form; §3.2's "K_Call_10 / K_Put_10" subscripts are a documented notation slip (§4 of this brief), not a 10% wing |
| 22 | mark_price | daily mid: average of last bid-ask before 4:00 p.m. ET, per leg | SOURCE-VERBATIM | §3.1: "Each SPX option price with subscript t is the average of the last bid-ask quote of the applicable option before 4:00 p.m. ET." |
| 23 | quote_source | published: Cboe Options Exchange via OPRA → ours: Tradier chains/NBBO | ADAPTED | §2.4: "The option quotes are sourced from the Cboe Options Exchange via the Options Price Reporting Authority (OPRA) feed." We read Tradier - same NBBO economics, different plumbing |
| 24 | liquidity_gates | inherit the platform's existing contract-selection gates (quote present, spread, OI) on all four legs; a leg failing the gate vetoes the whole butterfly for that symbol-month | PLATFORM-POLICY | Ours by policy; the index assumes frictionless SPX liquidity and publishes no gate |
| 25 | car_basis | capital-at-risk = max(call-wing width, put-wing width) × 100 − net credit received | ADAPTED | Per-spread form of the published worst-payoff §2.1: "Max (K Call_5% - K Call_atm, K Put_atm - K Put_5%)", net of premium; the index instead holds 10× the gross worst payoff in T-bills |

No UNKNOWN constants: the BFLY strike algorithm is fully price-based and completely specified in §2.1 (unlike sibling CNDR, which leaves its Black-formula IV input unspecified). The UNKNOWNs for this strategy are all performance statistics (§6), not implementation constants.

## 9. DATA REQUIREMENTS

- **Tradier chains:** required. DTE band ~25–40 calendar days on roll morning (must contain the next standard monthly/third-Friday expiration for all mapped symbols); NBBO bid/ask snapshot at ~10:45–11:00 a.m. ET on each roll date for strike selection (rows 3–6) and entry fills (row 11). **No greeks needed** - strikes are pure price arithmetic.
- **Underlying quote/trade snapshot at ~11:00 a.m. ET** on roll dates (row 6 reference price). A single intraday snapshot suffices; full 1-min bars are NOT required.
- **Expiration calendar:** third-Friday dates + exchange-holiday adjustments (row 7).
- **Earnings calendar (date + bmo/amc):** required only for the mega-cap tier - to FLAG (not gate) butterfly-months containing an earnings date (row 18).
- **FOMC/CPI dates:** not required by the source (no gate). Optional diagnostic tagging only.
- **VIX regime:** not required by the source. Record VIX at entry as a covariate for later attribution - no gating.
- **IV rank:** not required (source has no IV condition). No need to touch the cold IV archive; the VIX-percentile fallback is unnecessary for this strategy.
- **Daily history:** required - daily 4:00 p.m. mid marks per leg (row 22) for the mark series and drawdown accounting; underlying official closes for settlement (row 12).
- **1-min bars:** NOT required (entry is one 11:00 a.m. snapshot; marks are daily; settlement is the official close).
- **Ex-dividend dates** (SPY/QQQ/IWM quarterly, single names): to flag short-ITM-call-through-ex-div cycles (§7 structural risk) - for THIS strategy the short call is ITM roughly half the time, so this flag will fire often; that is expected.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** 1 butterfly per symbol per monthly cycle = **3/month** on the core ETF tier, **9/month** with the mega-cap extension. Each butterfly = 4 legs but ONE graded trade. At N≥25: the core ETF tier pools to N=25 in ~8–9 monthly cycles; the full universe in ~3 cycles - but per-tier verdicts (the ones that matter, per §2) make this a slow-grading strategy by construction: one decision point per symbol per month, no discretion anywhere.
- **Mark cadence:** daily EOD mid (4:00 p.m. ET, per leg, row 22) matches the published convention and is sufficient; plus the 11:00 a.m. entry snapshot on roll dates and the settlement mark at expiration close. Intraday marks between those are optional telemetry, never a trigger - nothing in this strategy reacts intra-month (row 13).
- **Multi-leg shape:** 4-leg net-credit iron butterfly with a COMMON body strike (first strike above spot) - the put side enters slightly ITM by construction (row 3). Wings ≥5% of spot each side, put wing structurally a touch wider (§3). Expect large credits relative to a condor (ATM straddle premium) and correspondingly frequent partial giveback - the win/loss texture is "many medium outcomes," not "many tiny wins."
- **Capital-at-risk basis:** width-credit - CaR = max(call-wing width, put-wing width) × 100 − net credit (row 25). Do NOT use the index's 10× T-bill convention for CaR; that is a return-damping collateral choice, not risk.
- **1-lot account-blind distortions:** (a) our per-butterfly P&L is raw spread P&L - roughly **10× more volatile in % terms** than the BFLY index series (which drowns the same P&L in a 10× T-bill account and adds T-bill yield); never compare our percentage returns to published index returns without de-damping; (b) we hold no T-bill account, so the risk-free-carry component of the published total return is absent - compare our results to the index's *option-P&L component*, not its headline level; (c) premium "reinvestment" (§2 of the methodology) is meaningless at 1 lot - book credit and settlement per butterfly.
- **Roll fidelity:** old fly settles at expiration (morning SOQ in source; our close-settle adaptation shifts exposure to the full Friday session), new fly opens 11:00 a.m. the same third Friday → ~5-hour same-symbol overlap under PM settlement (§2 adaptation #3). Log it on every roll.
- **Failure-hunting prior (from §6/§7):** the honest base case is a slow bleed - documented 47.1% peak-to-trough drawdown and a derived ~3.5%/yr long-run CAGR that badly lags the underlying, despite only two >6% loss months in 29½ years. The shadow's job is to measure whether the mapped ETF/mega-cap version's ATM credit still pays for realized monthly moves - not to assume the benign 1986–2015 tail statistics imply a positive edge today.

## 11. VERIFICATION

**Verdict: CONFIRMED** - adversarial verification pass, 2026-07-19, fresh-context verifier.

**What was checked:**
- **Primary source re-fetched and re-read in full:** `BFLY_Methodology.pdf` downloaded independently from the cited cdn.cboe.com URL (11 pages, v4.1, Last Revised November 27, 2025 - matches §1). Every SOURCE-VERBATIM quote in sections 3, 4, and 8 was located verbatim in the extracted PDF text: §1.1 structure sentence and "one unit"/"AM-settled" sentences; §2.1 all four strike-rule cells (both short legs indeed read "First listed strike above" - the shared-body-above-spot reading is faithful), worst-payoff formula, 10×-worst-payoff / ≈10%-of-account T-bill sentences, "selected before 11 a.m."; §2.2 SOQ settlement and mid-quote premium determination; §2.3 third-Friday/holiday roll rule; §2.4 OPRA sourcing; §3.1 4:00 p.m. mark convention and USB4WTA definition; §3.2 settlement payoff formulas, 11:00 a.m. "deemed purchased and sold", no-roll-day-interest note; §3.3 no-intraday-dissemination; §5 base date 1986-06-20 / launch 2015-08-03 / base value 100 / USD; back-test disclosure sentence (Disclosures page). The documented-absence claims (no profit target, no stop, no IV/event gate, no mid-cycle adjustment) were checked by reading the full document - nothing of the kind appears.
- **The §3.2 `K_Call_10`/`K_Put_10` notation slip is REAL** - the PDF prints `M_new_t = Max(K_Call_10 − K_Call_5, K_Put_5 − K_Put_10) ∗ 10` on page 6 (doc p. 6, PDF page 7) while §2.1 defines the worst payoff with atm/5% subscripts and no 10% strike exists anywhere. The brief's flag and its decision to implement the §2.1 form are correct.
- **Secondary source 1 (2016 press release):** downloaded from the cited q4cdn URL and read in full. Tail-loss quote (15 / 10 / two months of losses worse than 6 percent, July 1986–December 2015, 29½ years), authors (Black, Szado), study title, and date (2016-02-23) all verified verbatim.
- **Secondary source 2 (Cboe Insights 2021-07-26):** fetched. "The worst peak-to-trough monthly drawdown losses were … 47.1% for the BFLY Index, compared to 51% for the S&P 500 Index" verified (article also gives 19% for CNDR). The 11-months->10% sentence verified verbatim. The "fewer monthly increases or decreases of more than 6%" sentence exists in BOTH a CNDR and a BFLY form in the article - the brief quotes the BFLY sentence, which is present verbatim.
- **Index levels [verified-primary]:** Cboe historical chart API `_BFLY.json` re-fetched: first point 1986-06-20 = 100.000000; 2026-07-17 close = 405.39. Derived CAGR arithmetic recomputed: (405.39/100)^(1/40.08) − 1 = 3.55%/yr - matches, and it is correctly tagged as OUR computation, never published.
- **ADAPTED tags (rows 1, 6, 12, 23, 25):** each has a real, stated structural rationale (SPX→ETF/single-name universe, index dissemination→last trade, AM-SOQ→PM-close settle, OPRA→Tradier, T-bill collateral→width-minus-credit CaR); none is presented as published. PLATFORM-POLICY rows (18, 24) correctly self-identify as ours.

**Findings:** no invented constants, no misquotes, no mis-tagged numbers. Nothing required correction.

**Residual doubts (all already disclosed in the brief):** (a) the 2022 Black/Szado "positive alpha" claim remains unread behind the paywall - correctly tagged unverified, do not rely on it; (b) the full 2016 study paper (as opposed to its press release) was not independently read; (c) the Cboe Insights article is Cboe-authored marketing, not independent - the drawdown/extreme-month figures rest on it alone; (d) all pre-2015-08-03 index history is back-cast, per the primary source's own disclosure; (e) the press-release fill quality caveat stands - published figures assume frictionless mid-quote fills.
