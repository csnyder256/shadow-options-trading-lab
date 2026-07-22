# 09 · Backtesting, Paper Trading & Production Readiness

Requested outputs **#11 (backtesting)**, **#12 (paper trading)**, **#13 (production-readiness)**.
These are **gates**. The system may not skip one. A human flips the phase in
[`config/system.yaml`](../config/system.yaml) only after the exit criteria are met.

---

## Part A - Backtesting Requirements (#11) - Phase 0

### 9.1 Non-negotiables
- **Same code path as live.** Backtests run in NautilusTrader so the strategy/risk/signal code
  is byte-for-byte what trades live. No separate "research" implementation that can diverge.
- **No look-ahead.** Event-driven time model; every feature computed strictly as-of its bar.
  Point-in-time data only - no survivorship bias, no restated fundamentals.
- **Realistic frictions.** Model commission, **slippage**, the **bid/ask spread** (dominant for
  small/illiquid names and *every* option), and **partial fills**. Optimistic fills are how
  backtests lie.
- **Options realism.** If testing options, model the spread, liquidity (min OI/volume), and
  assignment. A cheap-account options backtest that assumes mid-fills is worthless.

### 9.2 Overfitting discipline (the make-or-break)
- Select parameters under **Combinatorial Purged Cross-Validation with embargo** (`skfolio`),
  not on the full history.
- Confirm out-of-sample with **walk-forward** analysis.
- Keep **few free parameters** - every knob is a chance to overfit.
- Report the **deflated/》honest metrics**: hit-rate, average R, max drawdown, **risk-of-ruin**,
  Ulcer index, profit factor, and the in-sample-vs-out-of-sample gap (a large gap = overfit =
  reject). Use `QuantStats` for the report.

### 9.3 Exit criteria to leave Phase 0
- Positive, *stable* out-of-sample performance with a small IS/OOS gap.
- Modeled **risk-of-ruin acceptably low** at the intended per-trade risk and account size.
- The strategy survives stress windows (e.g. high-vol regimes) without breaching the kill
  switches more than the design expects.
- **Honest verdict allowed to be "no edge."** If the process has no demonstrable edge, the
  correct output of Phase 0 is *do not trade real money* - that is a successful outcome of the
  experiment, not a failure of the framework.

---

## Part B - Paper / Shadow Trading (#12) - Phase 1

You chose the **shadow / sim broker** approach: validate against **live market data** using the
**exact same code path** as live, with a simulated fill engine. This is the most faithful
forward test short of risking money.

### 9.4 Two parallel paper tracks
1. **`SimBrokerAdapter` (shadow):** in-process fill engine driven by the *live* Alpaca/Finnhub
   feed. Models slippage, spread, partial fills, and (for options) assignment-on-expiry, using
   the same order state machine and the same status enums as live. This is what CI and the
   continuous shadow run use.
2. **`AlpacaPaperAdapter`:** Alpaca's real paper API (`paper=True`) - real exchange matching,
   money-less. This is where **options strategies are validated** (full L3 multi-leg), since
   Robinhood live is equities-only and the account is below the options threshold anyway.

Both sit behind the identical `BrokerAdapter` interface, so **the code that passes paper is the
code that goes live** - only the adapter binding changes.

### 9.5 What Phase 1 must demonstrate
- **Behavioral parity with backtest** - live-data paper results land within the modeled
  distribution (no nasty surprise from real spreads/latency/news).
- **Zero risk-engine breaches** - across the whole window, not one hard constraint is violated;
  every halt that *should* fire *does* fire (deliberately inject test conditions to prove the
  kill switches, reconciliation, and dead-man's switch actually work).
- **The rotating-analyst defense works under real churn** - run long enough that compaction
  happens repeatedly; confirm decisions remain consistent across compaction events and restarts
  (replay the journal; the same inputs must reproduce the same decisions).
- **Confidence calibration is sane** - stated confidence tracks realized hit-rate; the
  calibration discount engages when it should.
- **Operational endurance** - runs 24/7 for ≥ the configured window (`system.yaml:
  paper_min_days`, default ≥ 20 trading sessions) without manual intervention, surviving feed
  hiccups, restarts, and weekends.

### 9.6 Exit criteria to leave Phase 1 → micro-live
- Met §9.5 in full, **plus** a human has read the journal end-to-end and agrees the decisions
  are *reasonable*, not just profitable.
- Reconciliation has been tested by deliberately killing the process mid-trade and confirming
  clean recovery.
- The operator has rehearsed the **kill switch** and the **halt-and-flatten runbook**.

---

## Part C - Production-Readiness Requirements (#13) - Phase 2+

Micro-live ($250) and beyond. None of this is optional.

### 9.7 Safety & control
- **Human kill switch** reachable in seconds (Robinhood's app pause/disconnect + your own
  flatten-all command). Tested before go-live.
- **Dead-man's switch / heartbeat:** loss of connectivity → no new entries, protective stops are
  broker-resident, cancel-on-disconnect where supported.
- **Capability + threshold gates enforced:** options blocked from live until `equity ≥
  options_live_min_equity` **and** `capabilities().options == true`. Cash account / T+1 / PDT
  regime enforced per `config`.
- **Account isolation:** trade only inside the dedicated Robinhood agentic sub-account, funded
  with exactly the experiment capital - the broker's own blast-radius limit, reinforced by ours.

### 9.8 Observability & audit
- **Every cycle journaled** (inputs, signals, arguments, scores, decision, order IDs, outcomes)
 - append-only, hash-chained, retained forever. The whole system must be reconstructable months
  later from the journal alone.
- **High-signal, paged alerts** for: any kill-switch fire, `DISABLED_REVIEW`, reconciliation
  divergence, repeated order rejects, feed outage, model-eval regression. (Knight Capital
  ignored 97 *informational* emails - alerts must be few, prioritized, and route to someone who
  can halt.)
- **Daily operator review** of the journal + a one-page risk report (drawdown, exposure,
  streaks, calibration).

### 9.9 Determinism & change control
- **Pin the exact GLM build**; temperature 0 + fixed seed; log model version/fingerprint every
  call. A model change is a *deploy* gated by the canary eval harness, not a silent repoint.
- **Config is version-controlled.** Every risk-limit change is a reviewed commit with a reason.
  No live edits.
- **Reviewed, repeatable deploys** with a post-deploy version assertion. **No dead code paths,
  no reused flags** (the Knight lessons). Runbook: **halt-and-flatten first, diagnose second.**

### 9.10 Recovery & continuity
- Crash/restart → startup reconciliation (doc 07 §7.5) before any new decision.
- State backed up: append-only journal + risk-state file are the recoverable source of truth.
- A documented procedure to bring the system from cold-start to reconciled-and-running, and from
  running to fully-flat-and-off.

### 9.11 Legal / regulatory posture (operator's responsibility)
- Robinhood explicitly **does not supervise or audit your agent** - *you* are fully responsible
  for its behavior, your positions, and the data you share with the model provider. This
  framework's audit trail exists partly so you can meet that responsibility.
- Respect cash-account settlement and the active PDT/IML regime (doc 03). These are enforced in
  code, but the operator owns the consequences.
- This is **not investment advice and not a guarantee of anything.** It is an engineering
  framework for *not blowing up* while you find out whether a process has edge.

### 9.12 The production-readiness checklist (binary, all must be ✅)
- ✅ Backtest gate passed with honest OOS metrics and low risk-of-ruin.
- ✅ Paper gate passed: parity, zero breaches, kill switches proven, recovery proven, ≥ window.
- ✅ Rotating-analyst defense verified under real compaction + restarts.
- ✅ Human kill switch + dead-man's switch tested.
- ✅ Idempotency, reconciliation, and overfill guards tested with fault injection.
- ✅ Capability/threshold/settlement gates enforced (options paper-only < $2k).
- ✅ Alerts paged, journal hash-chained, model pinned, config in git.
- ✅ Operator has rehearsed the halt-and-flatten runbook.
- ✅ Only the experiment capital is in the isolated account.

Until **every** box is ✅, `system.yaml: mode` stays `paper`. Going live is a deliberate human
act, never an automatic graduation.
