# Strategy Lab - Source Viability Matrix (M0)

Executed 2026-07-19 (Saturday; markets closed - quotes are Friday-close snapshots, which is
sufficient for shape/depth checks; V1 greeks presence re-confirmed intraday on the M3 live probe).
Probe script: session scratchpad `m0_viability.py` (read-only; second Tradier token; no runtime
cache writes - FRED checked via the pure `_fetch_fred_release_dates` seam, not `refresh_calendar`).

| # | Check | Verdict | Evidence (2026-07-19) |
|---|-------|---------|------------------------|
| V1 | Tradier far-dated chains, 2nd token (`config/tradier.local.yaml`) | **PASS** | SPY: 33 expirations 2026-07-20 → 2028-12-15; 43-DTE chain (2026-08-31) 474 rows; two-sided NBBO **100%**, OI>0 91.8%, vol>0 58%, ORATS greeks iv 100% / delta 98.9%. Row fields: ask, bid, delta, expiration, gamma, iv, last, open_interest, option_type, strike, symbol, theta, vega, volume. |
| V2 | Budget burst under self-cap | **PASS** | 13 requests / 1.3 s: 3× expirations + 9 chains (SPY/QQQ/IWM × ~30/45/60 DTE, 184–640 rows each) + one 60-OCC batched quote POST → 60/60 returned, zero 429s at cap=40/min. |
| V3 | Finnhub `/calendar/earnings` shape | **PASS w/ CAVEAT** | 498 rows next 7d; fields {date, symbol, hour, epsEstimate, epsActual, quarter, revenueEstimate/Actual, year}; epsEstimate present 78.3%. **CAVEAT: `hour` empty on 39%** of ALL rows (bmo 131 / amc 171 / empty 196) - small caps dominate the empties. Mitigation: RH `get_earnings_calendar(filter='high_market_cap')` is the cross-check + fallback (see V9). |
| V4 | CBOE index CSVs (keyless) | **PASS** | All three HTTP 200: VIX_History 9,231 rows (~36 yr), VIX3M 4,232, VIX1D 1,047; header `DATE,OPEN,HIGH,LOW,CLOSE`; last row 07/17/2026 (current through Friday). VIX close 18.77, VIX3M 20.54 (contango), VIX1D 16.69. |
| V5 | FRED release dates (key in `credentials.local.yaml`) | **PASS** | Live fetch: CPI 12 dates 2026 (next 2026-08-12), NFP 12 dates (next 2026-08-07). `events.py` fallback tables therefore upgradeable to `source=fred` at runtime. |
| V6 | `runtime/options_iv.db` warm-up census | **PASS (cold, as expected)** | Tables iv_daily (4,509 rows) + iv_surface (26,462 rows). iv_daily is tenor-30 legacy seed at ~2 distinct days across thousands of symbols; per-DTE rows (1/8/15/17…) exist for ~1 day. **IV-rank is unusable for months → the pre-registered gate ladder is mandatory: iv_rank (≥60 sessions at tenor) → VIX 252d percentile (V4) → ungated + `gate_unavailable` log.** |
| V7 | RH MCP chains/instruments/quotes | **PASS** | SPY chain UUID c277b118…; 34 expirations to 2028-12-15; instrument lookup by (chain_id, expiration, type, strike) → UUID; quote returns bid/ask/size, mark, **live greeks (Δ 0.830, γ, θ, vega, rho), IV 0.2035, OI 3272, volume**, chance_of_profit, prior official close. Research-grade; NOT a runtime feed (agent-side only). |
| V8 | RH MCP option historicals depth | **PASS** | SPY 260831C00700000: daily OHLC bars from 2026-06-15 (23 bars, ≥1 month; docstring says ~1–3 months). No volume on bars. Good for research sanity-checks (e.g. verifying a researched credit level), not backtesting. |
| V9 | RH MCP earnings calendar | **PASS** | `filter=high_market_cap`, 7d: ~230 rows; `report.timing` (am/pm) present on ~97% incl. TSLA 07-22 pm, GOOGL 07-22 pm, INTC 07-23 pm; `verified` flag per row. **This is the primary timing source for strategies 19/20 at research time; Finnhub remains the runtime feed with RH cross-check during EOD truth-validation.** |
| V10 | Alpaca IEX minute bars, single names | **PASS** | AAPL + NVDA: 1,950 1-min RTH bars over 5 sessions each (o/h/l/c/volume), last ts 2026-07-17 15:59 ET. Cache extension to the ~10-name roster is feasible. |

## Consequences baked into the build

1. **All 20 slate strategies have their data needs met.** No blocking source asks. (owner declined optional Polygon/second-earnings-cal on 2026-07-19 - revisit only if V3's caveat bites a live earnings trade.)
2. Tradier second token serves far-dated chains with identical row shape to the main shadow's - `atlas/collect/tradier_data.py` needs **zero changes** for the lab.
3. **RISK-1 RESOLVED AT M0, adversely: there is NO second token.** `config/tradier.local.yaml` and `config/tradier_shadow.local.yaml` carry the IDENTICAL production token (sha256[:8] both `1e5c36a3`, verified 2026-07-19). The lab therefore shares the single ~120/min account budget with the main shadow (self-cap 60/min). **Lab self-cap is 40/min PERMANENTLY** (steady-state need ~18–20/min per V2; 60+40 ≤ 100 leaves headroom) - the plan's "raise to 80 after day-1 probe" is retired. M3's live probe now verifies non-interference at 40, not headroom for 80. A genuinely separate second Tradier token from the owner (free) would restore the original headroom - nice-to-have, not blocking.
4. IV-rank gates ship on the VIX-percentile fallback from day 1 (V6). Mapping constant (IVR>30 ≈ VIX pctile>30) is an ADAPTED constant and must be tagged as such in specs.
5. Earnings strategies: Finnhub `hour` is load-bearing and 39%-empty overall → universe screen for 19/20 must require `hour ∈ {bmo, amc}` (drop `dmh`/empty names) AND the name to appear in RH's high-market-cap calendar with `verified: true`.
