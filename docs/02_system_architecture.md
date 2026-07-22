# 02 · System Architecture, Roles & Runtime Loop

This covers requested outputs **#1 (system architecture)** and **#2 (roles & responsibilities)**.

## 2.1 Architectural shape

The system is a **deterministic orchestrator** that calls a **stateless LLM** as one step in a
fixed pipeline. It is *not* an "agent that decides what to do next." The control flow is owned
by code; the LLM only fills in the "analysis" slot when asked.

```
                         ┌──────────────────────────────────────────────┐
                         │              ORCHESTRATOR (code)               │
                         │   fixed loop · owns control flow · owns state  │
                         └──────────────────────────────────────────────┘
   (1) collect      (2) signals       (3) build context    (4) ANALYZE (LLM)
┌───────────────┐ ┌───────────────┐ ┌──────────────────┐ ┌────────────────────┐
│   Market      │ │   Signal      │ │  reconstruct     │ │  GLM-4.7-Flash     │
│   Collector   │→│   Engine      │→│  Core Memory +   │→│  bull / bear /     │
│ (data, code)  │ │ (TA, code)    │ │  retrieve memory │ │  uncertainty /     │
└───────────────┘ └───────────────┘ └──────────────────┘ │  confidence (text) │
                                                          └─────────┬──────────┘
                                                                    │ JSON proposal
                                                                    ▼
   (7) journal      (6) execute       (5) DECIDE (code) - LLM CANNOT REACH THIS
┌───────────────┐ ┌───────────────┐ ┌──────────────────────────────────────────┐
│  Decision     │ │  Execution    │ │  Validate schema → re-check every number   │
│  Journal      │←│  Layer        │←│  vs feed → re-derive signal → Consensus     │
│ (append-only) │ │ (limit only)  │ │  → RISK ENGINE (veto + size) → order or no  │
└───────────────┘ └───────────────┘ └──────────────────────────────────────────┘
        ▲                                                   │
        └───────────── durable state on disk ───────────────┘
              (read at step 3, written at step 7, survives any restart)
```

The arrow that does **not** exist is the important one: there is **no path from GLM (step 4)
to the Execution Layer (step 6).** GLM's output is data that step 5 *inspects*. GLM has no
order-placing tool, no broker credentials, and no ability to set or read the risk state except
as text the orchestrator chose to show it.

## 2.2 The runtime loop (canonical cycle)

Each cycle is deterministic top-to-bottom. A cycle runs on a timer (e.g. every 1–5 minutes
during the trading session; see `config/system.yaml`).

1. **Health & state gate.** Confirm: data feed fresh, broker connected, clock inside session,
   trading state is `ACTIVE`. If any check fails → **skip the cycle** (do nothing) and log why.
   Halts/blackouts are evaluated here, *before* any analysis spend.
2. **Collect** (Market Collector). Pull prices, volume, news, earnings calendar, macro events,
   sector/breadth, volatility. Stamp freshness on every datum.
3. **Reconcile.** Diff local journal state against broker positions/orders. Resolve any
   divergence *before* proposing anything new (see lifecycle doc).
4. **Signals** (Signal Engine). Compute all indicators in code over the collected data.
   Produce candidate setups with fully numeric, reproducible features.
5. **Pre-filter** (Risk Engine, cheap pass). Drop candidates that already violate a hard rule
   (earnings blackout, illiquid, over-concentration, no budget left). Never spend LLM tokens
   on a candidate the risk engine will reject anyway.
6. **Build context.** Reconstruct the **Core Memory Block** from disk; **retrieve** top-K
   relevant past journal entries for each surviving candidate. Assemble the decision prompt =
   `ANALYST_CONSTITUTION.md` (or `AUDITOR_CONSTITUTION.md` for the auditor pass) + Core Memory Block + retrieved memory + current signals.
7. **Analyze** (LLM). For each candidate, GLM returns a structured **trade proposal**:
   bull case, bear case, uncertainty analysis, technical/market/news sub-scores, and a
   confidence - conforming to [`schemas/trade_proposal.schema.json`](../schemas/trade_proposal.schema.json).
8. **Validate the proposal** (code). Reject if: schema-invalid; ticker not in universe; any
   cited number disagrees with the feed beyond tolerance; the claimed signal cannot be
   re-derived deterministically. A rejected proposal is journaled and discarded.
9. **Consensus** (code). Combine sub-scores into one confidence via the fixed formula in
   `config/consensus.yaml`. Apply the risk-score veto.
10. **Risk Engine** (code, final authority). Apply every hard constraint; compute the *only*
    legal position size; convert to a concrete bracket order (entry limit, hard stop, take
    profit). If anything fails → **no trade**.
11. **Execute** (Execution Layer). Place the bracket as **limit orders only**, with an
    idempotency key generated and journaled *before* the send.
12. **Journal** (Memory Layer). Append the full record: inputs, signals, arguments, scores,
    decision, order IDs. Later cycles append the realized outcome + a reflection.

If the loop dies anywhere, the next process start resumes at step 1 and *reconciles* (step 3)
 - there is never lost or duplicated work, because durable state, not memory, is the source of
truth.

External NON-PRICE information (catalyst events, the symbol-state defense layer, defensive FDA/
dilution flags, context feeds) rides alongside this loop under one rule - events decide WHEN we
look, gates + models decide WHETHER we trade - documented in
[doc 10](10_edge_sources.md) (2026-07-04).

## 2.3 Roles & responsibilities

Roles map to either **code** (deterministic, trusted) or **LLM** (probabilistic, untrusted).
The trust boundary is absolute.

### Market Collector - *code*
Collects and timestamps: price, volume, news, earnings calendar, macro/economic events, sector
movement, volatility metrics (ATR, realized vol, VIX level), market breadth (advance/decline,
% above MA). Tags every datum with a source and an age. **Stale data (older than
`max_data_age_seconds`) is treated as missing** and blocks trading on the affected symbol.

### Signal Engine - *code*
Deterministically computes candidate signals: support/resistance, moving averages, VWAP, RSI,
volume anomalies (rolling z-score), gap detection, trend strength (ADX), volatility (ATR,
Bollinger), momentum, relative strength vs benchmark. Output is fully numeric and
reproducible. **No LLM involvement.** Detail: [`04_signal_engine.md`](04_signal_engine.md).

### Technical Analyst Model - *LLM (GLM-4.7-Flash)*
Given the deterministic signals and retrieved memory, produces, as **text/JSON only**:
a bullish argument, a bearish argument, an explicit uncertainty analysis ("what would make
this wrong"), and sub-scores (technical/market/news, 0–100) with a confidence. **It explains;
it does not decide, and it does not report raw numbers** - those come from the Signal Engine.

### Risk Auditor Model - *LLM (Qwen3.6-27B), adversarial role - a DIFFERENT model family from the analyst, run sequentially via a single VRAM hot-swap*
A second, deliberately adversarial pass whose only job is to **invalidate** the trade. It
searches for: earnings risk, low liquidity, unusual volatility, weak signal quality,
contradictory indicators, market-wide weakness, sector weakness, overexposure, concentration
risk, news risk, gap risk, over-confidence, and **repeated failed patterns** (surfaced from
the journal). It outputs a `risk_score` (0–100, higher = more dangerous) and named risk flags.
Its *arguments* inform the human and the journal; its *score* feeds a deterministic veto. The
Risk Auditor's opinion never *raises* position size - only the deterministic Risk Engine sizes,
and only ever downward from the cap.

### Consensus Layer - *code*
Combines the LLM sub-scores into a single confidence using the fixed weighting in
`config/consensus.yaml`, applies the risk veto, and enforces anti-confidence-drift rules
(confidence is recomputed each cycle, never carried forward; cross-checked against realized
hit-rate). Detail: [`05_memory_and_rotating_analyst.md`](05_memory_and_rotating_analyst.md) §consensus.

### Risk Engine - *code · highest authority*
Hard constraints; position sizing; daily/weekly/streak kill switches; blackouts; concentration
caps; PDT/settlement enforcement. **No AI component can override it.** It is the last gate
before execution and it can only ever say "no" or "yes, at *this* size, with *this* stop."
Detail: [`03_risk_engine.md`](03_risk_engine.md).

### Execution Layer - *code*
Places **limit orders only** (never market). Always attaches a hard stop and a take-profit
(bracket). Generates and journals an **idempotency / client-order-id before every send** to
make duplicate orders impossible on retry. Maintains the order state machine and logs.
Detail: [`07_failure_and_lifecycle.md`](07_failure_and_lifecycle.md).

### Memory Layer - *code + files*
Stores completed trades, active trades, outcomes, mistakes, recurring patterns, and strategy
performance. **Active-trade state is never compressed or summarized** - it is ground truth.
Historical records may be summarized into lessons, but the raw append-only journal is retained.
Detail: [`05_memory_and_rotating_analyst.md`](05_memory_and_rotating_analyst.md).

## 2.4 The technology stack (summary; rationale in doc 08)

| Layer | Choice | Why |
|-------|--------|-----|
| Execution / backtest engine | **NautilusTrader** (Python, event-driven) | Same strategy code runs in backtest *and* live → kills backtest-vs-live drift; IB adapter; deterministic. Escalate to **QuantConnect LEAN** only if options modeling becomes central. |
| Technical indicators | **TA-Lib** core + **`ta` (bukosabino)** for VWAP | C-fast, deterministic, permissive license, now pip-installable. |
| Sizing / Kelly math | **keeks** | Fractional-Kelly, drawdown-adjusted Kelly, fixed-fraction, CPPI as a never-exceed ceiling. |
| Risk reporting | **QuantStats** | Risk-of-ruin, VaR/CVaR, max drawdown, Ulcer index. |
| Overfitting control | **skfolio** (CombinatorialPurgedCV, WalkForward) | Only free, sklearn-compatible purged CV with embargo. |
| LLM output safety | **Instructor** / **Outlines** | Constrained decoding → proposals valid by construction; auto-retry on schema violation. |
| Live broker (equities) | **Robinhood Agentic MCP** (`agent.robinhood.com/mcp/trading`) | Official, OAuth-scoped, isolated sub-account, MCP-native (fits a local LLM). **Equities-only at beta.** |
| Paper broker + options validation + data | **Alpaca** (`alpaca-py`, paper=True) | First-class paper trading, L3 multi-leg options, OPRA data; same surface as live. |
| Market data | Alpaca (primary) + Finnhub (news, earnings calendar) + Polygon (optional options history) | Reliable, ToS-clean. **Avoid yfinance in the live hot path.** |

## 2.5 Broker abstraction (the seam that keeps validation == live)

All brokers sit behind **one interface**, so the exact same strategy and risk code runs against
a simulator, against Alpaca paper, and against Robinhood live - only the adapter binding
changes.

```
BrokerAdapter (interface)
├── SimBrokerAdapter - shadow/sim: models fills/slippage/partial-fills/assignment vs LIVE data
├── AlpacaPaperAdapter - paper=True; full L3 multi-leg options; OPRA data  (validation of options)
└── RobinhoodAgenticAdapter - OAuth, isolated account; capabilities() = equities-only until RH enables options
```

Interface verbs: `get_account()`, `get_positions()`, `get_quote()`, `get_option_chain()`,
`place_order(OrderRequest)`, `cancel_order()`, `get_order()`, `poll_activities()` (assignment /
non-trade events), and **`capabilities()`** (which asset classes / options level / paper?).

`OrderRequest` carries a `legs[]` array from day one (single-leg = one leg), so a defined-risk
spread is always submitted as **one atomic multi-leg order** - never as sequential legs that
could leave a naked position on a partial fill. The strategy queries `capabilities()` and
routes: options-bearing proposals go to Alpaca paper (validation) and are **blocked from the
Robinhood live adapter** until `capabilities().options == true`.
