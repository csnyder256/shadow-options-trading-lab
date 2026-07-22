# 08 · Repository Recommendations & Integration Rationale

Requested output **#10**. This is not a link dump. Each entry says *why* it's in (or out) of the
design and *how* it integrates. Treat every repo as a **component or pattern, not a solution.**
Star counts / dates are as of mid-2026 and drift; re-verify license and maintenance at build.

---

## Tier S - adopt as core infrastructure

### NautilusTrader - execution + backtest engine
- **https://github.com/nautechsystems/nautilus_trader** · LGPL-3.0 · ~24k★ · very active.
- **Why it's core:** the *same strategy code runs in backtest and live* with a deterministic,
  event-driven time model. This directly attacks our #1 survival risk - backtest-vs-live
  divergence - and its determinism is exactly what a reproducible, LLM-fed signal pipeline
  needs. Ships an Interactive Brokers adapter; explicit options/`legs[]` order support.
- **Adopt:** the engine, its order state machine, its **live reconciliation** (OrderStatusReport
  / FillReport / PositionStatusReport, inflight-check timers), and its RiskEngine state pattern
  (`ACTIVE`/`REDUCING`/`HALTED`). Heed **issue #3176** - reconciliation reports need stable IDs.
- **Don't adopt:** its full complexity for early R&D; prototype signals elsewhere first.
- **Alternative:** **QuantConnect LEAN** (Apache-2.0, ~20k★) if equity-options modeling becomes
  central - it has the best first-class options support and unified backtest→paper→live, at the
  cost of a C#/Docker footprint.

### TA-Lib (+ `ta` by bukosabino) - indicators
- **https://github.com/TA-Lib/ta-lib-python** · BSD-2 · ~12k★ · active (prebuilt wheels now).
- **https://github.com/bukosabino/ta** · MIT · ~5k★ · maintained (has **VWAP** natively).
- **Why:** deterministic, C-fast, permissively licensed indicator math = trustworthy numbers the
  LLM is allowed to argue about. `ta` fills TA-Lib's VWAP/volume gaps without a C dependency.
- **Adopt:** TA-Lib as the authoritative compute core; `ta` for VWAP. Implement
  support/resistance, gaps, volume-anomaly, relative-strength as your own small unit-tested
  functions (better reproducibility than any library gives).
- **Avoid:** the **original `twopirllc/pandas-ta`** - repo was removed amid supply-chain
  concerns; use the maintained fork **`xgboosted/pandas-ta-classic`** (MIT) *only* as an
  ergonomic breadth layer, never as the authoritative compute. **`finta`** is archived (2022) - 
  avoid.

### Alpaca (`alpaca-py`) - paper broker + options validation + data
- **https://github.com/alpacahq/alpaca-py** · Apache-2.0 · active.
- **Why:** first-class **paper trading**, **L3 multi-leg options** enabled by default in paper,
  OPRA data, clean REST/websocket (no desktop gateway). Its surface mirrors the Robinhood
  agentic model, so it's the ideal place to validate options *today* while Robinhood is
  equities-only.
- **Adopt:** as the `AlpacaPaperAdapter` behind our broker interface, the primary market-data
  feed, and the options-validation venue. Model assignment via **REST activity polling** (Alpaca
  does not push assignment events).
- **Don't adopt:** as the live equities venue if you specifically want Robinhood - it's the
  *validation* and *data* backbone, not necessarily the live target.

---

## Tier A - adopt as patterns / libraries

### virattt/ai-hedge-fund - the deterministic-risk-gate pattern
- **https://github.com/virattt/ai-hedge-fund** · MIT · ~60k★ · very active.
- **Adopt the pattern, not the fleet:** its **Risk Manager is pure Python** and computes the
  *allowed actions and max sizes first*, then hands the LLM only capital-safe choices. This is
  the exact "deterministic gate → model chooses within it" model we use. Also adopt its tidy
  `{signal, confidence}` per-component schema and constrained JSON decision output.
- **Avoid:** its 14 investor-persona agents (cost/noise) and its **stateless** design - it has
  no memory across runs, which is precisely the gap we fill with doc 05.

### TauricResearch/TradingAgents - P&L-keyed reflection memory
- **https://github.com/TauricResearch/TradingAgents** · Apache-2.0 · ~87k★ · very active.
  Paper: arXiv:2412.20138.
- **Adopt the mechanism:** persist every decision + thesis; on the next look at a ticker, fetch
  the **realized return**, write a one-paragraph reflection, and **re-inject recent same-ticker
  decisions + lessons** into the prompt. This is the most directly reusable building block for
  our Decision Journal (doc 05 Layer 2) and the bull/bear/judge structure for the analyst split.
- **Avoid:** running its full 8+ agent pipeline on a $250 account - token cost dwarfs any edge.
  Don't trust its LLM "risk team" as real risk control; ours is deterministic.

### FinMem (pipiku915/FinMem-LLM-StockTrading) - layered memory + retrieval scoring
- **https://github.com/pipiku915/FinMem-LLM-StockTrading** · MIT · ~0.9k★ · 2024-era.
  Paper: arXiv:2311.13743.
- **Adopt:** the **layered memory + recency/relevance/importance retrieval score**, and the
  news→fast-decay / fundamentals+reflections→slow-decay routing (doc 05 Layer 3).
- **Avoid / invert:** its "risk-seeking when winning" rule. For a $250 survival-first account we
  **invert it** - de-risk after gains *and* losses. Single-agent with no adversarial check is
  also why we add the Risk Auditor split.

### keeks - position-sizing math
- **https://github.com/wdm0006/keeks** · adopt for `FractionalKellyCriterion`,
  `DrawdownAdjustedKelly`, `FixedFractionStrategy`, CPPI, and a `BankRoll` that enforces
  `max_draw_down` + `percent_bettable`. Use **fixed-fractional as the binding rule and Kelly
  only as a never-exceed ceiling** - never full Kelly (≈1-in-3 chance of a ~50% drawdown).

### QuantStats - risk reporting
- **https://github.com/ranaroussi/quantstats** · for `risk_of_ruin`, `kelly_criterion`,
  `value_at_risk`, `cvar`, `max_drawdown`, `ulcer_index` in backtest/paper reports. Reporting
  only - not in the execution hot path.

### skfolio - overfitting control
- **https://github.com/skfolio/skfolio** · BSD-3 · the only free, sklearn-compatible
  **CombinatorialPurgedCV + WalkForward** with purging/embargo. Adopt its CV machinery for
  signal-parameter selection. **Avoid `mlfinlab`** (now commercial / paywalled).

### Instructor / Outlines - LLM output safety
- **https://github.com/567-labs/instructor** (Pydantic `response_model` + auto-retry) and
  **https://github.com/dottxt-ai/outlines** (constrained decoding → valid by construction).
  Adopt to force GLM's output to satisfy
  [`schemas/trade_proposal.schema.json`](../schemas/trade_proposal.schema.json) - a malformed or
  out-of-universe proposal becomes structurally impossible, not merely caught later.

### MemGPT / Letta - core-memory pattern (optional dependency)
- **https://github.com/letta-ai/letta** · paper arXiv:2310.08560. Adopt the **editable
  always-in-context "core memory" block** idea (our doc 05 Layer 1). Use Letta off-the-shelf if
  you want managed memory tiers; otherwise replicate the core-memory block manually (recommended
 - fewer moving parts for a $250 system).

---

## Tier B - reference / fallback only

### robin-stocks (jmfernandes/robin_stocks)
- **https://github.com/jmfernandes/robin_stocks** · MIT · unofficial, **reverse-engineered**.
- **Role:** quarantined, *flagged-off* fallback live adapter only. Now that the **official
  Robinhood Agentic MCP** exists, prefer it. robin-stocks calls private endpoints with no API
  contract; auth (device-approval "sheriff challenge") breaks regularly; automating it risks ToS
  violation and account lockout; no paper environment. If ever used, store a TOTP seed and
  expect to babysit auth. **Never point validation/CI at it.**

### freqtrade / Hummingbot - robustness reference
- **freqtrade** (https://github.com/freqtrade/freqtrade) and **Hummingbot**
  (https://github.com/hummingbot/hummingbot): not adopted as engines (crypto-bot oriented), but
  **read their OMS/reconciliation code as references**: freqtrade's `PairLocks`/`StoplossGuard`/
  reload-on-restart and Hummingbot's `in_flight_order` id-mapping + kill-switch are battle-tested
  patterns we mirror in docs 03 and 07.

### vectorbt (OSS) - research-only screening
- **https://github.com/polakowo/vectorbt** · Apache-2.0 **+ Commons Clause** (not OSI).
  Adopt **only** as a throwaway screening layer to rank candidate signal variants fast, then
  re-validate survivors in NautilusTrader. **Never** the execution path (vectorized ≠ live;
  violates "no code divergence"). Watch the Commons Clause if you ever commercialize.

### yfinance - offline backfill only
- **https://github.com/ranaroussi/yfinance** · scrapes Yahoo's undocumented endpoints; 429s /
  IP blocks under sustained load; ToS-questionable for commercial use. **Keep out of the live
  loop**; acceptable for ad-hoc backfill and early backtests only.

---

## Tier X - explicitly rejected
- **Original `twopirllc/pandas-ta`** - removed / supply-chain concern. Use `pandas-ta-classic`.
- **`finta`** - archived 2022. Use TA-Lib + `ta`.
- **`mlfinlab`** - now commercial. Use `skfolio` for purged CV.
- **`vectorbtpro`** - paid, still vectorized (can't be the live engine). Not worth it at $250.
- **Any "give the LLM the order API" agent template** - violates the separation of powers
  (doc 01 §1.2). The LLM never holds execution authority, full stop.

---

## Integration map (what each adopted repo *does* in our system)

```
data        → Alpaca (+ Finnhub news/earnings)            → Market Collector
indicators  → TA-Lib + ta + custom funcs                  → Signal Engine
screening   → vectorbt (R&D only)                         → param search
CV/overfit  → skfolio (CPCV + walk-forward)               → param selection
LLM safety  → Instructor / Outlines                       → proposal schema enforcement
memory      → patterns from TradingAgents + FinMem + Letta→ Decision Journal + Core Memory + retrieval
risk gate   → pattern from ai-hedge-fund + keeks          → Risk Engine + sizing
OMS/recon   → NautilusTrader (+ freqtrade/Hummingbot refs)→ Execution Layer + reconciliation
engine      → NautilusTrader (LEAN if options-central)    → backtest == live
reporting   → QuantStats                                  → risk reports
live broker → Robinhood Agentic MCP (equities)            → live execution
             (robin-stocks = quarantined fallback)
```
