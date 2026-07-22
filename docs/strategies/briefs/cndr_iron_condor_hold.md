# Strategy Brief: cndr_iron_condor_hold

Researched 2026-07-19. Primary source READ in full (all 10 pages of the methodology PDF extracted and quoted verbatim below). Every constant in sections 3, 4, 8 carries a direct quote or is marked UNKNOWN.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `cndr_iron_condor_hold`
- **Provenance class:** CBOE-index
- **PRIMARY citation:**
  - URL: https://cdn.cboe.com/api/global/us_indices/governance/CNDR_Methodology.pdf
  - Title: *Cboe S&P 500 Iron Condor Index METHODOLOGY* (Cboe Global Indices, LLC)
  - Version 4.1, Last Revised Date December 12, 2025 (Appendix 2 – Document Information)
  - Index facts from §5: Base Date **June 20, 1986**, Launch Date **August 3, 2015**, Base Value **100**, Currency USD.
- **INDEPENDENT secondary source:**
  - URL: https://optionsjive.com/blog/iron-condor-options-strategy/
  - Title: *Never Trade Iron Condors Blindly: Here's How to Actually Profit With This Strategy* - Options Jive, published June 8, 2024. (Title corrected 2026-07-19 by independent verification; URL slug unchanged.) Independently describes CNDR as "a monthly SPX iron condor; selling short options at approximately 20 deltas, buying long options at approximately 5 deltas, no adjustments, no management, mechanical monthly roll" and computes long-horizon CAGR from index levels (see §6).
- **Additional secondary (Cboe-authored, separate document):**
  - https://www.cboe.com/insights/posts/benchmark-indices-series-volatility-management-with-cboes-bfly-and-cndr-indices/ - *Benchmark Indices Series: Volatility Management with Cboe's BFLY and CNDR Indices*, Cboe Insights, July 26, 2021.
  - https://cdn.cboe.com/resources/indices/documents/benchmarks-fact-sheet.pdf - *Benchmark Indexes* fact sheet, © 2020 Cboe Exchange, Inc., v1.9 (drawdown chart 2006–2019).
- **Publication dates:** Index base date 1986-06-20 (back-cast); index launch 2015-08-03; methodology doc v4.1 revised 2025-12-12; secondary sources 2020, 2021-07-26, 2024-06-08.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

**What the source trades:** SPX (S&P 500 Index) options only - European-style, cash-settled, **AM-settled** standard monthlies. Methodology §1.1: "All SPX options involved are AM-settled and roll on a monthly basis. All option positions are one unit." Plus a 1-month T-bill collateral account (see §5).

**Our mapping:** SPY / QQQ / IWM as the core tier (index-proxy ETFs - closest analog to the published SPX edge claim), with the liquid mega-cap tier (AAPL / NVDA / MSFT / TSLA / AMD / META) as an optional extension.

**LOUD ADAPTATIONS (structural, unavoidable on our platform):**
1. **Settlement style:** SPX monthlies are European, cash-settled against the third-Friday-morning SOQ. SPY/QQQ/IWM and single-stock options are **American, PM-settled, physically delivered**. Our shadow holds to expiration and cash-settles legs at intrinsic value vs. the official 4:00 p.m. ET close on expiration Friday - no physical delivery in a shadow, no stock legs ever. Tagged ADAPTED in §8.
2. **Early-assignment exposure:** American style means short legs that go ITM (especially short calls through an ex-dividend date on SPY/IWM/single names) can be assigned before expiry. The published European form cannot experience this. The shadow does not model assignment; it is a known divergence documented in §7.
3. **Single-name tier caveat:** CNDR's edge claim is an *index* volatility-risk-premium claim. Single stocks carry earnings-gap risk inside every monthly hold (the source has no event gate - see §3). The mega-cap tier therefore tests an *extension* of the published claim, not the claim itself. Grade the ETF tier and the mega-cap tier separately.

**Why the mapping preserves the edge claim:** the core-tier ETFs track the same (or analogous) broad indices; delta-targeted strikes self-scale to each underlying's IV, so "20Δ short / 5Δ wing" transfers without renumbering; monthly third-Friday expirations exist on all mapped symbols; the claim being tested - collecting the index volatility risk premium via a defined-risk short strangle with wings, unmanaged, monthly - survives the ETF translation. Both delta-hedging and stock legs are absent from the published form, so no options-only adaptation is needed there.

## 3. EXACT ENTRY RULES

**Trigger:** unconditional - a new condor is opened every monthly roll date. There is no signal, no IV gate, no regime filter anywhere in the methodology. §2.3: rebalances are "performed with monthly frequency". Absence of any gate is itself the published rule.

- **Roll/entry date:** §2.3: "The third Friday of each month. Should the third Friday fall on an exchange holiday, the roll date is the preceding Business Day."
- **Structure (4 legs, from §1.1):** "(1) sells a monthly Out-of-the-Money (OTM) SPX Put option (delta ≈ - 0.20) and a monthly Out-of-the-Money (OTM) SPX Call option (delta ≈ 0.20), (2) buys a monthly OTM SPX Put option (delta ≈ - 0.05) and a monthly OTM SPX Call option (delta ≈ 0.05) to reduce the risk".
- **Strike-selection algorithm (§2.1 constituents table):** for each leg, the strike is the "Option with delta closest to 0.20." / "Option with delta closest to -0.20." / "Option with delta closest to 0.05." / "Option with delta closest to -0.05." Tie-break when two strikes are equidistant: **UNKNOWN** (not specified in the methodology).
- **Delta model (§2.1):** "All inputs used in the delta calculation using the Black formula should be the last available values before 11:00 a.m. ET." The exact IV/surface input to the Black formula is **UNKNOWN** (not specified). Our shadow uses Tradier chain greeks instead - ADAPTED.
- **DTE selection (§2.1 table, "Option expiration" column):** "1 month" - the next standard monthly expiration, i.e. entered on the third Friday for the following month's third-Friday expiry (~28–35 calendar days).
- **Entry timing (§2.1):** "The strike prices of the option positions are selected before 11 a.m. ET on roll dates." New positions are "deemed purchased and sold (11:00 a.m. ET)" (§3.2).
- **Entry fill price (§2.2):** "At the average of the last bid-ask quote of the applicable option before 11:00 a.m. ET." (i.e., mid-quote at ~11:00 a.m. ET).
- **Published regime/IV gate:** NONE. No VIX, IV-rank, trend, or event condition appears anywhere in the document.

## 4. EXACT EXIT RULES

These OVERRIDE all platform exit doctrine for this strategy.

- **Hold-to-expiry doctrine (§2 / §3.3):** positions are never touched intra-month. §2 Index Construction: "On subsequent roll dates, the old options settles and a new option position is entered." §3.3: "On roll dates, the CNDR index will not be disseminated intraday." There is no earlier exit of any kind in the methodology.
- **Settlement (§2.2):** "Against the Special Opening Quotation (SOQ) of the SPX Index." Settlement payoffs per §3.2, e.g. "Put_N20_old_settle = Max (0, KPut_N20_old – SOQt)". ADAPTED for our universe: legs settle at intrinsic vs. the official close on expiration Friday (PM-settled ETFs/stocks have no SOQ).
- **Profit target:** NONE published. The methodology contains no profit-taking rule. Independent confirmation (Options Jive, 2024): "no adjustments, no management, mechanical monthly roll."
- **Loss management / stop:** NONE published. Loss is bounded structurally by the long 5Δ wings; the worst payoff is "Max (KCall_P5 - KCall_P20, KPut_N20 - KPut_N5)" (§2.1).
- **Roll rule:** expiration morning IS the roll: old position settles at the open (SOQ), new position entered same day at 11:00 a.m. ET. There is a ~1.5-hour flat gap; the shadow reproduces this (no overlap of old and new condors on the same underlying).

## 5. SIZING CONVENTION IN SOURCE

Fully collateralized, index-style: one unit of each option leg against a T-bill account sized to ten times the maximum possible loss. §1.1: "All option positions are one unit." §2.1: "a Treasury bill account with initial cash that equals ten times the maximum possible loss of the new option positions is set up at 11:00 a.m. ET. The Treasury bill account is designed such that the maximum possible loss from final settlement of the new option positions is approximately 10% of the total value of the account." The account earns the 4-week T-bill rate (§3.1, rate "USB4WTA … obtained from the website of the U.S. Department of the Treasury"; "interest is not accumulated in the Treasury bill account on the roll day" §3.2). Premium is functionally reinvested: "The Index is a total return index. The dollar value of option premium deemed received from the sold call and put options are functionally reinvested in the Iron Condor Index portfolio." (§2).

Recorded for context only - our shadow always runs 1 published unit (one 4-leg condor), account-blind.

## 6. DOCUMENTED PERFORMANCE

The methodology itself publishes NO performance figures. All numbers below are from secondary sources; none appear in the primary doc.

- CAGR **+9.11%** Jan 1987 – Jan 2010 [verified-secondary - Options Jive 2024-06-08: "Compound annual growth rate of +9.11%. The strategy appeared to work."]
- CAGR **≈ −0.72%** Jan 2010 – 2024; "The index moved from 770 to approximately 784 – essentially flat for 14 years." [verified-secondary - Options Jive 2024-06-08]
- Full-period CAGR **5.28%** (~37 years, 1987–2024), vs. S&P 500 buy-and-hold "approximately 10.5% annualized" over the same period [verified-secondary - Options Jive 2024-06-08]
- Worst peak-to-trough monthly drawdown **−19%** for CNDR vs. −51% for the S&P 500 over ~35 years (1986–2021) [verified-secondary - Cboe Insights 2021-07-26]
- Monthly return distribution: "59% of the time, the CNDR Index had returns between 0% and 2%" [verified-secondary - Cboe Insights 2021-07-26]
- In the 11 months when the S&P 500 moved more than 10%, "neither the CNDR nor the BFLY indices rose or fell by 10% or more" [verified-secondary - Cboe Insights 2021-07-26]
- Max drawdown 2006–2019: **−13.7%**, the least severe on Cboe's cross-asset drawdown chart [verified-secondary - Cboe Benchmark Indexes fact sheet v1.9, "Most Severe Drawdowns Since 2006 (From 2006 through 2019)"]
- Win rate: UNKNOWN (not published anywhere found). Profit factor: UNKNOWN. Per-trade statistics: UNKNOWN.

**Methodology caveats:** (a) everything before the 2015-08-03 launch is back-tested - primary-source disclosure: "Index and benchmark values for dates or time periods prior to an index launch date, if any, are calculated using a theoretical approach involving back-testing historical data" [verified-primary]; (b) index returns are damped ~10× by the T-bill collateral convention (max loss ≈ 10% of account, §2.1) - raw per-spread P&L is roughly 10× swingier than the index return series; (c) index is frictionless mid-quote fills, no commissions/slippage; (d) the post-2010 flat stretch [verified-secondary] means the headline 1987–2010 CAGR is regime-dependent - treat "edge attenuation since ~2010" as the base case to disprove, not a surprise.

## 7. KNOWN FAILURE MODES

**Named historical episodes** (short-vol family; CNDR's wings cap each month's loss at the published worst-payoff, so these are capped-loss months, not blowups):
- **Oct-1987 crash** - inside the back-cast; the ~19% worst drawdown window of the 35-year series [drawdown number verified-secondary; attribution to 1987 unverified].
- **Feb-2018 "Volmageddon"** - short-vol repricing; monthly 20Δ condors entered mid-January carried the Feb 5 VIX spike. [episode-level P&L for CNDR: unverified]
- **Mar-2020 COVID crash** - put side blown through both strikes → full put-spread width realized at settlement. [episode-level P&L: unverified]
- **Aug-2024 vol spike (Aug 5)** - same shape, smaller. [unverified]
- **Post-2010 attenuation** - the documented killer for this strategy is not tail loss but edge decay: essentially flat 2010–2024 [verified-secondary, Options Jive]. Grading should test whether the premium collected still pays for the tail months at all.
- Melt-up months (e.g. strong 2013/2017/2021 rallies): the SHORT CALL side breaches - an iron condor loses in calm relentless rallies too, not just crashes. [structural, follows from payoff]

**Structural failure modes on OUR mapping (not present in the published SPX form):**
- **Early assignment through ex-div** on short ITM calls (SPY/IWM quarterly ex-div dates; single names) - American exercise; the shadow does not model it; flag any expiry where a short call is ITM at an ex-div date.
- **Earnings gap-through-strikes** for the mega-cap tier: every monthly hold contains at most one earnings date with no published gate; a gap through the wing realizes full width. This is an extension risk, not part of the published claim.
- **PM vs. AM settlement**: expiration-day price action (which SPX condors never see past the open) is in scope for our ETF version through the 4 p.m. close.
- **Pin/assignment ambiguity at the close** near a short strike - shadow settles at intrinsic vs. official close; real trading would face pin risk.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | underlying_universe | SPY, QQQ, IWM (core); AAPL, NVDA, MSFT, TSLA, AMD, META (extension tier, graded separately) | ADAPTED | Source trades SPX only ("sells a monthly … SPX Put option", §1.1); mapped per §2 of this brief |
| 2 | structure | 4-leg iron condor: short call + short put, long call + long put wings; net credit | SOURCE-VERBATIM | §1.1: "(1) sells a monthly … SPX Put option (delta ≈ - 0.20) and a monthly … SPX Call option (delta ≈ 0.20), (2) buys a monthly OTM SPX Put option (delta ≈ - 0.05) and a monthly OTM SPX Call option (delta ≈ 0.05)" |
| 3 | short_call_delta | +0.20 | SOURCE-VERBATIM | §2.1 table: "Option with delta closest to 0.20." |
| 4 | short_put_delta | −0.20 | SOURCE-VERBATIM | §2.1 table: "Option with delta closest to -0.20." |
| 5 | long_call_delta | +0.05 | SOURCE-VERBATIM | §2.1 table: "Option with delta closest to 0.05." |
| 6 | long_put_delta | −0.05 | SOURCE-VERBATIM | §2.1 table: "Option with delta closest to -0.05." |
| 7 | strike_selection_rule | closest-to-target delta, per leg | SOURCE-VERBATIM | §2.1 table: "Option with delta closest to …" (all four legs) |
| 8 | strike_tiebreak | UNKNOWN | UNKNOWN | Methodology silent on equidistant-delta ties. Shadow must pick a deterministic rule and log it as a local convention, not a published one |
| 9 | delta_model | Black formula; inputs = last available values before 11:00 a.m. ET | SOURCE-VERBATIM | §2.1: "All inputs used in the delta calculation using the Black formula should be the last available values before 11:00 a.m. ET." |
| 10 | delta_iv_input | UNKNOWN | UNKNOWN | Source names the Black formula but never specifies the IV/surface input |
| 11 | delta_source_shadow | Tradier chain greeks at the entry snapshot | ADAPTED | We cannot reproduce Cboe's unspecified Black-formula inputs; broker greeks approximate the same 20Δ/5Δ targets |
| 12 | roll_date | third Friday of each month; if exchange holiday, preceding business day | SOURCE-VERBATIM | §2.3: "The third Friday of each month. Should the third Friday fall on an exchange holiday, the roll date is the preceding Business Day." |
| 13 | entry_dte | next standard monthly expiration ("1 month", ~28–35 calendar days) | SOURCE-VERBATIM | §2.1 table, Option expiration column: "1 month"; §1.1: "roll on a monthly basis" |
| 14 | expiry_type | standard monthlies only (third-Friday cycle); never weeklies | SOURCE-VERBATIM | §1.1: "All SPX options involved are AM-settled and roll on a monthly basis." (ETF monthlies are the PM-settled analog - see row 17) |
| 15 | entry_time | strikes fixed before 11:00 a.m. ET on roll date; position deemed entered at 11:00 a.m. ET | SOURCE-VERBATIM | §2.1: "The strike prices of the option positions are selected before 11 a.m. ET on roll dates."; §3.2: "deemed purchased and sold (11:00 a.m. ET)" |
| 16 | entry_fill_price | mid: average of last bid-ask before 11:00 a.m. ET, per leg | SOURCE-VERBATIM | §2.2: "At the average of the last bid-ask quote of the applicable option before 11:00 a.m. ET." |
| 17 | settlement_style | published: European AM cash-settle at SPX SOQ → ours: intrinsic vs. official 4 p.m. close on expiration Friday, cash-settled in shadow, no stock legs | ADAPTED | §2.2: "Against the Special Opening Quotation (SOQ) of the SPX Index." ETF/single-name options are American/PM/physical - adaptation documented in §2 of this brief |
| 18 | exit_rule | HOLD TO EXPIRATION - no intra-month exit of any kind (overrides platform exit doctrine) | SOURCE-VERBATIM | §2: "On subsequent roll dates, the old options settles and a new option position is entered." No other exit appears in the document |
| 19 | profit_target | NONE | SOURCE-VERBATIM | No profit-taking rule anywhere in the methodology; independent confirmation (Options Jive 2024): "no adjustments, no management, mechanical monthly roll" |
| 20 | stop_loss | NONE (loss bounded only by wings) | SOURCE-VERBATIM | No stop/adjustment rule in the methodology; worst payoff §2.1: "Max (KCall_P5 - KCall_P20, KPut_N20 - KPut_N5)." |
| 21 | iv_regime_gate | NONE - enter every roll date unconditionally | SOURCE-VERBATIM | No VIX/IV/trend/event condition appears anywhere in the methodology; §2.3 rebalance is unconditional monthly |
| 22 | event_gate | NONE published; mega-cap-tier holds spanning earnings are flagged (not skipped) so the tiers can be graded separately | PLATFORM-POLICY | Source has no event gate (see row 21); flagging is our bookkeeping, entry remains unconditional to preserve the published form |
| 23 | position_size | 1 unit per leg (one condor) | SOURCE-VERBATIM | §1.1: "All option positions are one unit." |
| 24 | collateral_convention (context only) | T-bill account = 10 × worst payoff; max loss ≈ 10% of account | SOURCE-VERBATIM | §2.1: "initial cash that equals ten times the maximum possible loss of the new option positions"; "maximum possible loss … is approximately 10% of the total value of the account." Shadow is account-blind, 1 lot |
| 25 | mark_price | daily mid: average of last bid-ask before 4:00 p.m. ET, per leg | SOURCE-VERBATIM | §3.1: "the average of the last bid-ask quote of the -20 delta Put option reported before 4:00 p.m. ET on the current trading day" (same wording for all four legs) |
| 26 | liquidity_gates | inherit the platform's existing contract-selection gates (quote present, spread, OI) on all four legs; a leg failing the gate vetoes the whole condor for that symbol-month | PLATFORM-POLICY | Ours by policy; the index assumes frictionless SPX liquidity and publishes no gate |
| 27 | car_basis | capital-at-risk = max(call-spread width, put-spread width) × 100 − net credit received | ADAPTED | Derived from the published worst-payoff formula §2.1: "Max (KCall_P5 - KCall_P20, KPut_N20 - KPut_N5)." (per-spread form of it, net of premium; the index instead holds 10× this in T-bills) |

## 9. DATA REQUIREMENTS

- **Tradier chains:** required. DTE band ~25–40 calendar days on roll morning (must contain the next standard monthly/third-Friday expiration for all 9 symbols); need greeks (delta) and NBBO bid/ask snapshot at ~10:45–11:00 a.m. ET on each roll date. All four legs need live quotes.
- **Expiration calendar:** third-Friday dates + exchange-holiday adjustments (row 12).
- **Earnings calendar (date + bmo/amc):** required only for the mega-cap tier - to FLAG (not gate) condor-months containing an earnings date (row 22).
- **FOMC/CPI dates:** not required by the source (no gate). Optional diagnostic tagging only.
- **VIX regime:** not required by the source. Record VIX at entry as a covariate for later attribution - no gating.
- **IV rank:** not required (source has no IV condition). No need to touch the cold IV archive; VIX-percentile fallback unnecessary for this strategy.
- **Daily history:** required - daily 4 p.m. mid marks per leg (row 25) for the mark series and drawdown accounting; underlying daily closes for settlement (row 17).
- **1-min bars:** NOT required. Entry is one 11:00 a.m. snapshot; marks are daily; settlement is the official close. (Optional: expiration-day closing print for the underlying, which daily history already covers.)
- **Ex-dividend dates** (SPY/IWM quarterly, single names): to flag short-ITM-call-through-ex-div months (§7 structural risk).

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** 1 condor per symbol per monthly cycle = **9/month** with the full universe (3 core ETF + 6 mega-cap), **3/month** if only the core ETF tier runs. Each condor = 4 legs but ONE graded trade. At N≥25 per lane: full universe reaches pooled N=25 in ~3 monthly cycles, but per-tier verdicts (the ones that matter, per §2) need ~9 cycles for the ETF tier alone. This is a slow-grading strategy by construction - one decision point per symbol per month.
- **Mark cadence:** daily EOD mid (4 p.m. ET, per leg, matching row 25) is the published convention and is sufficient; plus the 11:00 a.m. entry snapshot on roll dates and the settlement mark at expiration close. Intraday marks between those are optional platform telemetry, never a trigger - nothing in this strategy reacts intra-month (row 18).
- **Multi-leg shape:** 4-leg net-credit iron condor; symmetric delta targets, asymmetric dollar widths (put wing is typically wider in strike terms because of skew - this is expected, not a bug; the published worst-payoff formula max(call width, put width) anticipates it).
- **Capital-at-risk basis:** width-credit - CaR = max(call width, put width) × 100 − net credit (row 27). Do NOT use the index's 10× T-bill convention for CaR; that is a return-damping collateral choice, not risk.
- **1-lot account-blind distortions:** (a) our per-condor P&L is the raw spread P&L - roughly **10× more volatile in % terms** than the CNDR index series (which drowns the same P&L in a 10× T-bill account and adds T-bill yield); never compare our percentage returns to published index returns without de-damping; (b) we hold no T-bill account, so the risk-free carry component of the published total return is absent from our shadow - our expectation should be compared to the index's *option-P&L component*, not its headline CAGR; (c) premium "reinvestment" (§2) is meaningless at 1 lot - we simply book credit and settlement per condor.
- **Roll-gap fidelity:** old condor settles at expiration (morning SOQ in source; our close-settle adaptation shifts this to Thursday-close→Friday-close exposure differences), new condor opens 11:00 a.m. the same Friday (for us: same third Friday the old one expires - enter the new condor at 11:00 a.m., old one still open until the close under PM settlement; log both; this same-day overlap of a few hours is an unavoidable artifact of the AM→PM adaptation and should be noted on every roll).
- **Failure-hunting prior (from §6/§7):** the honest base case is that this strategy has been ~flat since 2010 on SPX. The shadow's job is to measure whether the mapped ETF/mega-cap version collects enough credit to survive its capped-loss months, not to assume the 1987–2010 CAGR is recoverable.

## 11. VERIFICATION

- **Verdict: CORRECTED** (adversarial fresh-context verification, 2026-07-19).
- **What was checked:** The primary methodology PDF (https://cdn.cboe.com/api/global/us_indices/governance/CNDR_Methodology.pdf) was downloaded and its full text extracted (10 pages, v4.1, Last Revised December 12, 2025 - matching §1 of this brief). Every SOURCE-VERBATIM constant and quote in sections 3, 4, 5, and 8 was located verbatim in the extracted text: the §1.1 structure/delta sentence, all four "Option with delta closest to …" table entries, the Black-formula 11:00 a.m. inputs sentence, "1 month" expiration, the worst-payoff formula Max(KCall_P5 − KCall_P20, KPut_N20 − KPut_N5), the 10× T-bill collateral language, §2.2 SOQ settlement and mid-quote premium determination, §2.3 third-Friday/preceding-business-day roll rule, §3.1 4:00 p.m. mark wording and USB4WTA rate source, §3.2 settlement payoffs and "deemed purchased and sold (11:00 a.m. ET)", §3.3 no-intraday-dissemination on roll dates, §5 base date 1986-06-20 / launch 2015-08-03 / base value 100, and the back-testing disclosure. Confirmed by absence (whole document searched): no profit target, no stop/adjustment, no IV/VIX/trend/event gate, no strike tiebreak rule, no IV-surface input spec - the brief's NONE and UNKNOWN entries are accurate. All four ADAPTED rows (1, 11, 17, 27) carry genuine adaptation rationales and none are presented as published. Both secondary sources were fetched live: Options Jive (2024-06-08) confirms +9.11% (1987–2010), ≈−0.72% and 770→~784 (2010–2024), 5.28% 37-year CAGR, and ~10.5% S&P 500 comparison; Cboe Insights (2021-07-26) confirms the −19% vs −51% worst peak-to-trough monthly drawdown, the "59% of the time … between 0% and 2%" distribution, and the 11-months->10% statement; the Benchmark Indexes fact sheet v1.9 (© 2020) confirms −13.7% for CNDR as the least severe drawdown on the 2006–2019 chart. No invented constants found.
- **Correction applied:** section 4's hold-to-expiry locator read "(§2.2 / §1.2)"; §1.2 is "Supporting Documentation" and contains nothing about holding. Corrected to "(§2 / §3.3)", which is where the supporting language actually lives. This was the only defect.
- **Residual doubts:** (a) §3.2 of the methodology literally says "the new SPX Put options are deemed purchased and sold (11:00 a.m. ET)" - an apparent Cboe typo (calls too); the brief's generalization to "new positions" is reasonable but noted. (b) The §1 characterization of the Options Jive article ("a monthly SPX iron condor; …") was verified in substance and for all numeric constants, but the exact prefix wording inside that quotation was not independently re-located word-for-word. (c) Episode-level P&L items in §7 are already flagged unverified in the brief itself and remain so. (d) The 2021 Cboe Insights drawdown (−19%) and the 2020 fact-sheet drawdown (−13.7%) cover different windows (since-1986 vs 2006–2019) - the brief keeps them separate, correctly.

### 11.b Independent re-verification (fresh-context adversarial pass, 2026-07-19)

- **Verdict: CORRECTED.** NOTE: the verification record above (11 through "Residual doubts") was ALREADY PRESENT in the file when this fresh-context pass began. It was treated as an untrusted claim and NOT relied on; everything below was re-derived from the sources directly.
- **Primary source:** the methodology PDF was re-downloaded from https://cdn.cboe.com/api/global/us_indices/governance/CNDR_Methodology.pdf (10 pages, v4.1, Last Revised Date December 12, 2025) and full text extracted. Every SOURCE-VERBATIM quote in §§3, 4, 5, 8 was located verbatim: §1.1 objective sentence with the ≈±0.20 short / ≈±0.05 long deltas and "All option positions are one unit" and "All SPX options involved are AM-settled and roll on a monthly basis"; §2 "total return index" / "functionally reinvested" / "On subsequent roll dates, the old options settles and a new option position is entered"; §2.1 "selected before 11 a.m. ET on roll dates", worst-payoff formula Max(K_Call_P5 − K_Call_P20, K_Put_N20 − K_Put_N5), "ten times the maximum possible loss" / "approximately 10% of the total value of the account", Black-formula-inputs-before-11:00 a.m. sentence, and all four "Option with delta closest to 0.20 / −0.20 / 0.05 / −0.05." table cells with "1 month" expiration; §2.2 SOQ settlement and "At the average of the last bid-ask quote of the applicable option before 11:00 a.m. ET."; §2.3 "performed with monthly frequency" and the third-Friday/preceding-Business-Day roll rule; §3.1 USB4WTA Treasury-website rate and the before-4:00 p.m. ET mark wording (row 25); §3.2 Max(0, K_Put_N20_old − SOQ_t) settlement payoffs, "deemed purchased and sold (11:00 a.m. ET)", M_new = Max(widths) × 10, and the no-roll-day-interest note; §3.3 no-intraday-dissemination on roll dates; §5 Base Date June 20, 1986 / Launch Date August 3, 2015 / Base Value 100 / USD; and the back-testing disclosure in the Disclosures section. Confirmed by absence over the full extracted text: no profit target, no stop/adjustment rule, no VIX/IV/trend/event gate, no strike tiebreak, no IV-surface input spec - every NONE and UNKNOWN entry is accurate. All ADAPTED rows (1, 11, 17, 27) carry real adaptation rationales and none masquerade as published; PLATFORM-POLICY rows (22, 26) are honestly labeled.
- **Secondary sources, fetched live:** Options Jive article (published June 8, 2024) confirms verbatim: CAGR "+9.11%" (1987–2010), "770 to approximately 784 – essentially flat for 14 years" with "approximately -0.72%", full 37-year CAGR "5.28%", S&P 500 "approximately 10.5% annualized", and the "no adjustments, no management, mechanical monthly roll" description - including the §1 quote prefix, now located word-for-word (clearing prior residual doubt (b)). Cboe Insights (July 26, 2021) confirms: "worst peak-to-trough monthly drawdown losses were 19% for the CNDR Index … compared to 51% for the S&P 500 Index" over "the past 35 years"; "59% of the time, the CNDR Index had returns between 0% and 2%"; and the 11-months->10% statement for CNDR and BFLY. Benchmark Indexes fact sheet (© 2020, v1.9) confirms −13.7% for CNDR on the "Most Severe Drawdowns Since 2006 (From 2006 through 2019)" chart, the least severe of the 13 bars shown (range −80.9% to −13.7%). No invented constants found anywhere in §§3, 4, 6, or 8.
- **Correction applied this pass:** §1 secondary-source title was wrong - the brief called the article "Iron Condor Options Strategy: How to Actually Profit With It"; the live page's actual title is "Never Trade Iron Condors Blindly: Here's How to Actually Profit With This Strategy". Fixed in §1 (URL was correct and unchanged). This, plus the prior pass's §4 locator fix (already in place: "(§2 / §3.3)" verified correct against the extracted text), are the only defects found across both passes.
- **Residual doubts after this pass:** (a) the §7 episode-level P&L attributions (1987/2018/2020/2024) remain unverified, as the brief itself already flags; (b) the −19% drawdown's attribution to the 1987 window remains unverified (the Insights article gives the number, not the date); (c) the earlier pass's §11 record above is consistent with this pass's findings except that it missed the §1 title error and understated what could be verified in doubt (b) - treat this 11.b entry as the authoritative verification record.
