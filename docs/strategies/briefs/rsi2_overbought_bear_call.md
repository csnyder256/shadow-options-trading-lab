# Strategy Brief: rsi2_overbought_bear_call

Researched 2026-07-19. All quotes are short verbatim fragments from the cited sources, reproduced
solely for rule-auditability. Verification tags: [verified-primary] = read in the primary source
text (via full-text mirror), [verified-secondary] = read in a cited secondary source,
[unverified] = could not be confirmed by reading; treat as hearsay.

---

## 1. IDENTITY & PROVENANCE

- **Strategy id:** `rsi2_overbought_bear_call`
- **Provenance class:** practitioner (quantified-backtest practitioner literature; also in book form → practitioner/textbook hybrid)
- **PRIMARY citation:**
  - Larry Connors & Cesar Alvarez, *Short Term Trading Strategies That Work*, TradingMarkets Publishing Group, November 2008, ISBN 978-0981923901. **Chapter 9: "The 2-Period RSI - The Trader's Holy Grail of Indicators?"** (chapter title verified against full-text mirror). Supporting chapters: Chapter 12 ("The S&P Short Strategy" - source of the published short-cover exit) and the Exits chapter.
  - Full-text mirror read: https://epdf.pub/short-term-trading-strategies-that-work.html (also mirrored at https://studylib.net/doc/27785371/ - 429 at research time). Purchase page: https://www.amazon.com/Short-Term-Trading-Strategies-That/dp/0981923909
  - **Honest verification caveat:** the mirror extraction confirmed the chapter title, the test range ("the SPYs from the inception of their trading in mid-January 1993 through December 31, 2007"), the long-side rules/stats, the dynamic-exit doctrine, and the Chapter 12 short-cover rule. The chapter's *overbought-bucket tables* (RSI(2) > 90/95/98 forward returns) were NOT extractable from the mirror. The short-side entry formulation (RSI(2) > 95 below the 200-day SMA) is therefore verified through two independent secondary sources that attribute it to Connors' testing (below), not by direct page read of Chapter 9. This is flagged, not papered over.
- **Corroborating Connors primary:** Laurence Connors & Conor Sen, *How Markets Really Work* (1st ed. 2004; 2nd ed. Wiley 2012, data Jan 1989–Sep 2011) - overbought RSI(2) statistics for SPX/NDX; read via secondary review (below), so tagged [verified-secondary].
- **INDEPENDENT secondary sources:**
  1. StockCharts ChartSchool, "RSI(2)" - https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2 (verbatim markdown mirror read: .../rsi-2.md). Undated evergreen article; attributes the strategy to Larry Connors.
  2. MQL5 Articles #17636, "Day Trading Larry Connors RSI2 Mean-Reversion Strategies" - https://www.mql5.com/en/articles/17636 (cites *Short-Term Trading Strategies That Work* (2008); gives the exact long/short rule rendition).
  3. EasyLanguage Mastery, "Connors 2-Period RSI Update 2019" - https://easylanguagemastery.com/strategies/connors-2-period-rsi-update-2019/ (independent re-backtest; edge-attenuation evidence).
  4. Book review of *How Markets Really Work* - https://whatheheckaboom.wordpress.com/2012/10/26/book-review-of-how-markets-really-work-by-laurence-connors/
- **Publication dates:** book Nov 2008 (softcover reissue 2012); *How Markets Really Work* 2004/2012; ChartSchool undated (2010s, maintained); MQL5 article 2025; EasyLanguage Mastery update 2019.

## 2. PUBLISHED UNIVERSE & OUR MAPPING

- **What the source trades:** daily-bar mean reversion on the S&P 500 complex - book tests are on **SPY** ("the SPYs from the inception of their trading in mid-January 1993 through December 31, 2007" [verified-primary]); *How Markets Really Work* stats "Valid for both SPX and NDX" [verified-secondary]; ChartSchool applies it to index ETFs (DIA) and liquid single stocks (AAPL, GOOG examples) and reports Connors' testing spanned "hundreds of thousands of trades" across "stocks and stock indices" [verified-secondary]. The published instrument is the **underlying itself - a short stock/ETF sale**. No options anywhere in the published form.
- **Our mapping:** SPY / QQQ / IWM (directly congruent - SPY is the tested instrument, QQQ ≈ NDX which HMRW validates, IWM is an index-ETF sibling) plus the liquid mega-cap tier AAPL / NVDA / MSFT / TSLA / AMD / META (Connors' stock-universe tests and ChartSchool's single-stock examples cover liquid large caps).
- **ADAPTATION - LOUD:** the published trade is **short the underlying**. This platform is options-only: we express the signal as a **bear call spread** (short call + further-OTM long call, same expiry). Consequences, stated plainly:
  1. Every option-structure constant (strike, width, DTE, credit) is **ours, not Connors'** - tagged ADAPTED/PLATFORM-POLICY in section 8. The source publishes none of them.
  2. The long wing imposes a **structural max-loss cap the published strategy explicitly does not have** (Connors: no stops). This truncates the left tail the published stats include - our results are NOT a clean replication of the published expectancy, they are a defined-risk proxy of it.
  3. The spread adds theta/vega exposure absent from a stock short; near-ATM short strike keeps delta the dominant Greek so the option P&L tracks the published directional claim.
- **Why the mapping preserves the edge claim:** the claim is a 1–7 day downward drift after a 2-day RSI extreme within a downtrend, on exactly these index vehicles (and liquid large caps). An ATM-anchored bear call spread with expiry beyond the documented average holding period (≈3.6–3.7 trading days [verified-primary, long-side stats]) is a monotone-payoff proxy for that drift. Signals, timing, and exits stay exactly as published; only the expression vehicle changes.

## 3. EXACT ENTRY RULES

All entry logic is computed on **daily bars** (the entire published framework is daily: 200-day SMA, 5-day SMA, daily-close RSI).

1. **Trend filter (regime gate):** underlying's last close **below its 200-day SMA**.
   - ChartSchool: "The long-term trend is up when a security is above its 200-day SMA and down when a security is below its 200-day SMA." [verified-secondary]
   - MQL5 (rendition of the 2008 book): "Sell when: RSI2 > 95, last close price < 200-period moving average, and no current positions." [verified-secondary]
2. **Trigger:** **2-period RSI (Wilder RSI, daily closes) rises above 95**.
   - ChartSchool: "traders can look for short-selling opportunities when 2-period RSI moves above 90" and "returns were higher when selling short on an RSI surge above 95." [verified-secondary] → source gives a **range 90–95 with 95 documented as the better threshold**; we take 95.
   - Corroborating Connors stat (*How Markets Really Work* via review): "High RSI levels (above 95) have led to dead money as rallies have often stalled within a few days." (SPX/NDX, Jan 1989–Sep 2011) [verified-secondary]
3. **No pyramiding:** "and no current positions" [verified-secondary, MQL5 rendition] - one open position per symbol.
4. **Entry timing:** published signals are computed and executed **on the daily close** (EasyLanguage Mastery's rendition of "the original Connors model": "Buy on close when cumulative RSI(2) is below 5" [verified-secondary] - long-side wording; execution-at-close applied mirror-wise). Our shadow evaluates at **15:45–15:55 ET** using near-close values and enters then - ADAPTED (cannot trade the exact closing print and need time for contract selection).
5. **Strike selection / DTE / credit:** **NOT PUBLISHED - no options exist in the source.** Our choices (all ADAPTED, section 8): short call = nearest listed strike at/above signal-day underlying price; long call = smallest standard width ≥ 0.5% of spot above it; expiry = nearest listed with 10–17 calendar DTE.
6. **Published regime/IV gate:** the 200-day SMA is the only published gate. **No VIX, IV-rank, or event gate is published** for this strategy. (Chapter 6 of the book covers VIX stretches as a *separate* strategy; it is not part of the RSI(2) rules.)

## 4. EXACT EXIT RULES

These override all platform exit doctrine for this strategy.

1. **Primary signal exit:** cover when the underlying **closes below its 5-day SMA**.
   - Book, Chapter 12 (published short-cover doctrine): "Cover your short position when the SPY closes under its 5-period moving average." [verified-primary]
   - ChartSchool: "Connors advocates exiting ... short positions on a move below the 5-day SMA." [verified-secondary]
   - Shadow execution: when the condition is true at the 15:45–15:55 ET evaluation, buy the spread back at that day's closing mark.
2. **Secondary exit (regime flip):** cover if the underlying **closes above its 200-day SMA** - MQL5 rendition of the book: "Exit sell when: last close price < 5-period moving average, or last close price > 200-period moving average." [verified-secondary]
3. **No stop-loss:** "Connors does not advocate using stops"; his testing found stops "hurt" performance on stocks and stock indices. [verified-secondary, ChartSchool] → we add **no P&L stop** on the spread. The long wing's max-loss cap is a structural artifact of the options expression (ADAPTED), not a stop rule.
4. **No profit target:** exits are signal-driven only; the book advocates dynamic exits - "dynamic exits, like a moving average exit and an RSI exit, make the edges greater." [verified-primary] The book's alternate RSI exit is published for the long side only ("Exit when the 2-period RSI closes above 65" [verified-primary]); the short-side RSI-exit threshold is **UNKNOWN** (not published in anything read) and is NOT used.
5. **Time exit (ours, PLATFORM-POLICY):** the published strategy holds a stock short indefinitely until signal exit; a spread cannot. Force-close at the mark at **1 DTE** if neither signal exit has fired. Average published hold is ~3.6–3.7 trading days [verified-primary, long-side], so a 10–17 DTE entry makes this rare.
6. **No roll rules:** rolling does not exist in the source. We never roll - a forced close at 1 DTE ends the trade.

## 5. SIZING CONVENTION IN SOURCE

The book reports per-signal statistics (percent correct, points made, average % gain per trade) on a single-position basis with no capital-allocation scheme published in the chapter [verified-primary - stats are quoted per trade: "Total Signals: 50 ... Average Gain Per Trade: 1.26%"]. The EasyLanguage Mastery re-backtest used "1 contract per trade" on ES futures with $100,000 nominal equity [verified-secondary]. No %-of-buying-power or collateralization doctrine is published. **Our shadow: always 1 published unit = 1 bear call spread (1 lot), account-blind**, per platform convention.

## 6. DOCUMENTED PERFORMANCE

The published performance record is overwhelmingly **long-side**. Standalone short-side/overbought-fade performance numbers were **not verifiable** in anything read - recorded honestly below.

- **[verified-primary]** Book Ch. 9, SPY mid-Jan 1993 → Dec 31 2007, LONG side (Cumulative RSI(2) variants, buy above the 200-day MA, RSI-65 exit):
  - 2-day cumulative RSI < 35: "Total Signals: 50", "Percent of Signals Correct: 88%", "Total SPY Points Made: 65.53", "Average Gain Per Trade: 1.26%", "Average Hold Per Trade: 3.7 trading days".
  - 2-day cumulative RSI < 50: "Total Signals: 105", "Percent of Signals Correct: 85.47%", "Total SPY Points Made: 105.95", "Average Gain Per Trade: 1.05%", "Average Hold Per Trade: 3.57 trading days".
  - These are the LONG mirror - cited for hold-period/hit-rate shape only, NOT as evidence for the short side.
- **[verified-secondary]** *How Markets Really Work* (Jan 1989–Sep 2011, SPX & NDX, via review): overbought RSI(2) "above 95" readings "led to dead money as rallies have often stalled within a few days" - i.e., the documented short-side edge is **absence of upward drift, not strong negative drift**.
- **[verified-secondary]** QuantifiedStrategies (Substack, free tier), "RSI 2 Strategy Explained: Larry Connors' 2-Period RSI Trading Rules" - https://quantifiedstrategies.substack.com/p/rsi-2-strategy-explained-larry-connors - RSI-2 on SPY 1993–present, long side: "Average Gain per Trade: 0.9%", "Annual Returns (CAGR): 9%", "Maximum Drawdown: 34%", "Time Invested: 28%". Short-side breakdown not provided; trading-rules section paywalled.
- **[verified-secondary]** EasyLanguage Mastery 2019 re-backtest, ES futures 2000→2019, long-only original rules: "Net Profit $7,887", "Annual Rate of Return .041%" over 60 trades - and "starting around 2018 we entered another reduction, and the standard 2-period trading model ... has been in a drawdown." **The raw published edge has attenuated materially since 2008.**
- **[verified-secondary, long-side only]** The "76%" win-rate figure that circulates is EasyLanguage Mastery's reported Win Rate for the LONG-only original-rules ES backtest (2000→2019, 60 trades, Profit Factor 1.30). No win-rate number for the SHORT side was read on any cited page - do not treat short-side win rates as documented.
- **Methodology caveats:** book test window (1993–2007) ends before the GFC; results are frictionless (no commissions/slippage noted in extracts); overbought-side tables in Ch. 9 could not be extracted, so the short-side magnitude rests on HMRW's "dead money" characterization. Expect the options expression to differ further (spread pricing, capped tails).

## 7. KNOWN FAILURE MODES

- **Bear-market squeeze rallies (the defining risk):** the entry condition - sharp multi-day rally while below the 200-day SMA - is exactly the profile of violent bear-market rallies that keep running: Oct 2008 (+11% single days), Mar 2020 rebound legs, and the Jun–Aug 2022 rally (SPX +~17% while still below its 200-day SMA - a sequence of consecutive losing RSI(2)>95 shorts). Published form wears these unhedged (no stops); our long wing caps each instance at width − credit.
- **No-stop doctrine + overnight gaps:** published exits are close-based; an overnight gap up through both strikes realizes near-max loss before any exit can act. Single names (TSLA, NVDA, AMD) gap hardest.
- **Signal starvation in bull regimes:** below-200-day-SMA is a precondition; in sustained bull markets the strategy produces **zero** entries across the whole universe for months/years. Grading timelines must expect this (see §10).
- **Edge attenuation post-publication:** independent re-backtests show the standard RSI(2) model "has been in a drawdown" since ~2018 [verified-secondary]; the 1993–2007 stats should not be extrapolated at face value.
- **Earnings gap-through-strikes (single-name tier):** the source universe logic is index-era; a mega-cap earnings gap up while below its 200-day SMA (e.g., a beaten-down name beating estimates) blows through a 0.5%-wide call spread instantly. Platform earnings gate applied (ours, §8).
- **Early assignment through ex-div:** the short call is at/near ATM and goes ITM whenever the fade fails; an ITM short call held through an ex-dividend date (SPY/IWM/QQQ quarterly ex-divs; AAPL/MSFT/META dividends) invites early assignment when the dividend exceeds the call's remaining extrinsic. Shadow must model assignment risk or force-exit before ex-div (flagged for implementation).
- **Fighting the 2010s+ index updrift:** shorting index products has negative carry against the secular drift; HMRW documents "dead money" after overbought readings, not reliable declines - the short side is structurally the weaker half of the published RSI(2) pair.

## 8. PARAMETER TABLE

| # | name | value | tag | source quote / locator |
|---|------|-------|-----|------------------------|
| 1 | bar_interval | daily bars, daily closes | SOURCE-VERBATIM | entire framework daily: "200-day SMA", "5-day SMA" (ChartSchool); book tests on daily SPY closes (Ch. 9) |
| 2 | rsi_period | 2 (standard Wilder RSI on daily closes) | SOURCE-VERBATIM | "2-period RSI" (ChartSchool; book Ch. 9 title "The 2-Period RSI") |
| 3 | entry_rsi_threshold | > 95 (source range 90–95; 95 documented better) | SOURCE-RANGE | "short-selling opportunities when 2-period RSI moves above 90"; "returns were higher when selling short on an RSI surge above 95" (ChartSchool) |
| 4 | trend_filter_entry | last close < 200-day SMA | SOURCE-VERBATIM | "last close price < 200-period moving average" (MQL5 rendition of the 2008 book) |
| 5 | max_open_positions_per_symbol | 1 ("no current positions") | SOURCE-VERBATIM | "and no current positions" (MQL5 rendition) |
| 6 | entry_execution_timing | evaluate 15:45–15:55 ET with near-close values; enter at mark | ADAPTED | published execution is "on close" ("Buy on close…", EasyLanguage Mastery rendition, long side); we approximate the close print |
| 7 | exit_primary | underlying closes below its 5-day SMA → buy back spread at that close's mark | SOURCE-VERBATIM | "Cover your short position when the SPY closes under its 5-period moving average." (book, Ch. 12) |
| 8 | exit_secondary_regime_flip | underlying closes above its 200-day SMA → exit | SOURCE-VERBATIM | "Exit sell when: last close price < 5-period moving average, or last close price > 200-period moving average." (MQL5 rendition) |
| 9 | alternate_rsi_exit_threshold_short_side | UNKNOWN - not published; NOT used | UNKNOWN | long-side alternate is "Exit when the 2-period RSI closes above 65" (book, Ch. 9); no short-side mirror value published in anything read |
| 10 | stop_loss | NONE | SOURCE-VERBATIM | "Connors does not advocate using stops"; stops "hurt" performance (ChartSchool) |
| 11 | profit_target | NONE - signal-driven exits only | SOURCE-VERBATIM | "dynamic exits, like a moving average exit and an RSI exit, make the edges greater" (book) |
| 12 | option_structure | bear call spread: short call + long call, same expiry, 2 legs | ADAPTED | no options in source (published form = short the underlying); options-only platform |
| 13 | short_strike_selection | nearest listed strike at/above signal-day underlying price (≈ ATM) | ADAPTED | no published value; ATM keeps delta dominant so spread P&L tracks the published directional decline claim |
| 14 | spread_width | smallest standard listed width ≥ 0.5% of spot (floor $1) | ADAPTED | no published value; small width bounds CaR while preserving delta expression |
| 15 | dte_band | nearest expiry with 10 ≤ DTE ≤ 17 calendar days | ADAPTED | no published value; sized off published avg hold "3.7 trading days" / "3.57 trading days" (book, Ch. 9) plus buffer so exits stay signal-driven |
| 16 | force_close_dte | 1 DTE at mark if no signal exit has fired | PLATFORM-POLICY | spreads expire, stock shorts don't; keeps ledger free of expiry mechanics |
| 17 | min_credit_gate | reject entry if net credit < 30% of width | PLATFORM-POLICY | pricing-sanity gate (ATM verticals typically price well above this); ours, not published |
| 18 | liquidity_gate | both legs: bid > 0, (ask−bid)/mid ≤ 10%, OI ≥ 100 | PLATFORM-POLICY | platform standard liquidity policy; not published |
| 19 | earnings_gate_single_names | skip entry if earnings report falls on/before chosen expiry (mega-cap tier only) | PLATFORM-POLICY | source rules are index-era; gap-through-strikes control, ours |
| 20 | position_size | 1 spread (1 published unit), account-blind | PLATFORM-POLICY | shadow convention; source publishes per-signal stats with no sizing scheme (§5) |

## 9. DATA REQUIREMENTS

- **Daily history:** ≥ 210 trading days per symbol (200-day SMA + warmup) - REQUIRED. Drives RSI(2), 200-day SMA, 5-day SMA. This is the whole signal engine.
- **Tradier chains:** DTE band 7–21 (to select within the 10–17 target and price the 2 legs) - REQUIRED at entry and for daily marks.
- **1-min bars:** only for the 15:45–15:55 ET evaluation marks and exit fills - nice-to-have; daily close + chain quotes suffice.
- **Earnings calendar (date + bmo/amc):** REQUIRED for the mega-cap tier (row 19 gate). bmo/amc matters: an amc report on expiry day is still inside the window.
- **FOMC/CPI dates:** NOT required - no published event gate; log-only context if cheap.
- **VIX regime / IV rank:** NOT required - no published IV gate (200-day SMA is the only published regime filter). If a vol context tag is wanted for post-hoc analysis, use VIX-percentile fallback (our IV-rank archive is cold); tag only, never gate.

## 10. SHADOW-IMPLEMENTATION NOTES

- **Expected trades/month:** heavily regime-gated. Requires a symbol below its 200-day SMA *and* a sharp 2-day rally. In broad bull regimes: ~0/month across all 9 symbols (true starvation - this is expected behavior, not a funnel bug; do not "fix" it). In corrective/bear regimes: bursts of 5–15/month. Long-run planning number: **~2.5/month averaged across regimes**. Consequence: the N≥25 grading gate may take many months to fill and will fill in clusters; e-process wealth accrual will be lumpy and regime-correlated.
- **Mark cadence:** daily closing marks are the doctrinal minimum (all published rules are close-based). Platform's standard intraday mark cadence is fine but exits trigger only off the 15:45–15:55 ET evaluation (rows 6–8).
- **Multi-leg shape:** 2-leg vertical credit spread (short call nearer strike, long call higher strike, same expiry). Net credit at entry.
- **Capital-at-risk basis:** **width − credit** (defined-risk max loss). This is the per-family CaR basis; no Reg-T proxy needed.
- **1-lot account-blind distortions:** (a) the published record is an uncapped stock short - our capped spread truncates both tails, so per-trade P&L will NOT match published expectancy shape; grade against the spread's own ledger, not the book's stock stats. (b) Published stats are frictionless percent moves; a 1-lot spread pays proportionally large spread-crossing costs on entry+exit - the WORST-fill ledger will bite hardest here of the three. (c) "No stops" (row 10) means drawdowns within a trade are doctrinal - the exit engine must NOT cut this family on adverse marks; only rows 7, 8, 16 close a position. (d) Early-assignment risk on ITM short calls through ex-div is real in the live world but invisible to a shadow ledger - flag any trade holding an ITM short call across an ex-div date in the trade record so grading can note the fiction.
- **Sibling strategy:** long side of the same source = `rsi2_oversold_bull_put` (RSI(2) < 5/10 above the 200-day SMA). Same primary citation; keep constants consistent across the pair where the source is symmetric, and do not invent symmetry where it isn't (row 9).

## 11. VERIFICATION

### Pass 2 - independent adversarial re-verification (fresh context, 2026-07-19) - VERDICT: CONFIRMED

A second verifier with no shared context found the Pass 1 section below already present in the file, treated it as untrusted data, and re-fetched every cited source live (2026-07-19). Result: **every claim independently re-confirmed; zero invented constants; no edits to the brief body were needed.**

- **Primary (epdf.pub full-text mirror):** located verbatim - Ch. 9 title "The 2-period RSI - The Trader's Holy Grail of Indicators?"; "we ran the test results on the SPYs from the inception of their trading in mid-January 1993 through December 31, 2007"; "Cover your short position when the SPY closes under its 5-period moving average."; "Exit when the 2-period RSI closes above 65"; the dynamic-exits sentence (mirror OCR reads "dynamk exits" - obvious typo for "dynamic"); BOTH cumulative-RSI stat blocks digit-for-digit (50 / 88% / 65.53 / 1.26% / 3.7 and 105 / 85.47% / 105.95 / 1.05% / 3.57). Independently re-confirmed the two disclosed gaps: no overbought-bucket (RSI>90/95/98) tables extractable, and NO explicit "RSI(2)>95 below 200-SMA" short-entry rule in the extractable primary text - §1's caveat and the [verified-secondary] tagging of the short entry are exactly right.
- **ChartSchool RSI(2):** all quoted fragments located, including the full sentences behind the brief's ellipses ("returns were higher when selling short on an RSI surge above 95 than on a surge above 90"; "Connors advocates exiting long positions on a move above the 5-day SMA and short positions on a move below the 5-day SMA"); no-stops and stops-"hurt" wording confirmed; DIA/AAPL/GOOG examples and Connors attribution confirmed.
- **MQL5 #17636 (dated 3 April 2025):** sell rule and exit-sell rule located word-for-word; cites "Short-Term Trading Strategies That Work (2008)".
- **EasyLanguage Mastery 2019:** "Buy on close when cumulative RSI(2) is below 5"; ES 2000–2019, 60 trades, Net Profit $7,887, ARR 0.041%, Win Rate 76%, Profit Factor 1.30, $100,000 / 1 contract, confirmed **long-only** (so §6's long-side-only scoping of the 76% figure is correct); "Starting around 2018 we entered another reduction ... has been in a drawdown" confirmed.
- **whatheheckaboom HMRW review (2nd ed., Jan 1989–Sep 2011):** "High RSI levels (above 95) have led to dead money as rallies have often stalled within a few days" confirmed verbatim, and - critically - it sits under the heading "Two-Period RSI [Best Indicator]" with "Valid for both SPX and NDX" closing that section, so the brief's RSI(2)/SPX+NDX attribution is sound.
- **QuantifiedStrategies Substack:** 0.9% / 9% CAGR / 34% MDD / 28% time-invested confirmed verbatim; SPY 1993–present; no short-side breakdown; Trading Rules section paywalled - all as stated.
- **Tag audit re-run (§§3, 4, 8):** every SOURCE-VERBATIM and SOURCE-RANGE constant traced to its cited source; ADAPTED rows (6, 12–15) and PLATFORM-POLICY rows (16–20) all carry real rationales and none is presented as published; row 9 correctly UNKNOWN.
- **Residual doubts (Pass 2):** same three as Pass 1 - Ch. 9 overbought tables unread in primary; epdf.pub is an unauthorized mirror (content cross-checks against independent secondaries, pagination uncheckable); the documented short-side edge is "dead money", not strong negative drift - disclosed in §6/§7, a risk statement, not a verification failure. Additional note: Pass 1's provenance is unknown to Pass 2 (it predated Pass 2 in the file), but every checkable claim in it survived independent re-fetch.

### Pass 1 (as found in file; independently re-verified above)

- **Verdict: CORRECTED** (minor citation fixes only; no invented constants found). Adversarial verification pass, fresh context, 2026-07-19.
- **What was checked, source by source (all fetched live 2026-07-19):**
  - **Primary (book, full-text mirror at epdf.pub):** located verbatim - Ch. 9 title ("The 2-period RSI- The Trader's Holy Grail of Indicators?"); the SPY test-range sentence ("mid-January 1993 through December 31, 2007"); the Ch. 12 short-cover rule ("Cover your short position when the SPY closes under its 5-period moving average."); the RSI-65 long exit; the dynamic-exits sentence; BOTH cumulative-RSI stat blocks exactly as quoted in §6 (50/88%/65.53/1.26%/3.7 and 105/85.47%/105.95/1.05%/3.57). The mirror indeed does NOT surface the Ch. 9 overbought (RSI>90/95/98) tables - the brief's caveat in §1 is accurate, not papered over.
  - **ChartSchool RSI(2):** all quoted fragments located (200-day SMA trend definition; short entries "above 90"; "returns were higher when selling short on an RSI surge above 95"; 5-day-SMA short exit; "does not advocate using stops" / stops "hurt"; "hundreds of thousands of trades"; DIA/AAPL/GOOG examples). One elided quote in §3.1 restored to full verbatim form.
  - **MQL5 #17636:** sell rule and exit-sell rule located word-for-word; article does cite *Short-Term Trading Strategies That Work* (2008).
  - **EasyLanguage Mastery 2019:** original-rules wording, ES futures, 60 trades, "Net Profit $7,887", 0.041% ARR, $100,000 / 1-contract / no-stops sizing, and the "starting around 2018 ... in a drawdown" statement all located. Also surfaced: Win Rate 76%, Profit Factor 1.30 (long side) - §6's formerly-[unverified] 76% bullet upgraded and correctly scoped to long-side.
  - **whatheheckaboom HMRW review:** "dead money" sentence, "Valid for both SPX and NDX", and the Jan 1989–Sep 2011 window all located verbatim.
  - **QuantifiedStrategies:** the §6 stats had no URL in the original brief; located at quantifiedstrategies.substack.com/p/rsi-2-strategy-explained-larry-connors - all four numbers (0.9% / 9% CAGR / 34% MDD / 28% time invested) verbatim; URL added.
  - **Tag audit (§§3, 4, 8):** every SOURCE-VERBATIM and SOURCE-RANGE constant traced to its cited source. Every ADAPTED row (6, 12–15) and PLATFORM-POLICY row (16–20) carries a real rationale and none is presented as published; §2 flags the short-stock→bear-call-spread adaptation loudly. Row 9 (short-side RSI exit) correctly left UNKNOWN.
- **Corrections applied (all minor):** (1) restored full ChartSchool trend-definition quote in §3.1; (2) added the missing QuantifiedStrategies URL and clarified paywall scope in §6; (3) re-scoped the 76% win-rate bullet from [unverified] to [verified-secondary, long-side only].
- **Residual doubts:** (a) the Ch. 9 overbought-bucket tables remain unread in any primary text - the short-side magnitude still rests on HMRW's "dead money" characterization plus MQL5/ChartSchool renditions, exactly as the brief discloses; (b) the epdf.pub mirror is an unauthorized reproduction - quotes match across independent secondaries, but page-level pagination was not checkable; (c) the documented short-side edge is weak by the sources' own account ("dead money", not reliable decline) - the brief states this honestly in §6/§7, so it is a disclosed risk, not a verification failure.
