# 07 · Failure Handling & Trade Lifecycle

Requested outputs **#8 (failure modes)** and **#9 (trade lifecycle)**.

---

## Part A - Trade Lifecycle (#9)

### 7.1 Order state machine

Every order moves through an explicit, persisted state machine. The orchestrator and the
journal agree on this state at all times; on restart, state is rebuilt from the broker +
journal, not from memory.

```
INITIALIZED → SUBMITTED → ACCEPTED → PARTIALLY_FILLED → FILLED
                   │           │              │            │
                   └───────────┴──────────────┴────────────┴──→ CANCELED / REJECTED / EXPIRED
```

Each order carries two IDs: an internal **`client_order_id`** (our idempotency key, generated
and journaled **before** the network send) and the broker's **`venue_order_id`** (learned after
acceptance). Fills are applied **idempotently, keyed on the venue `trade_id`**, so a duplicated
execution report can never double-count. An **overfill guard** rejects any fill where
`filled_qty + last_qty > order_qty`.

### 7.2 Full lifecycle of one trade

1. **Candidate** produced by the Signal Engine (deterministic).
2. **Analysis** by GLM → schema-valid proposal (bull/bear/uncertainty/scores).
3. **Validation**: schema, ticker ∈ universe, every number re-checked vs feed, signal
   re-derived. Fail → journal + discard.
4. **Consensus** → single confidence; risk veto check.
5. **Risk Engine** → REJECT, or APPROVE with a concrete **bracket**: entry limit, hard stop,
   take-profit, and the risk-clamped size. Options → single atomic multi-leg order or nothing.
6. **Pre-send**: generate + journal `client_order_id`; pre-trade settled-cash / buying-power /
   rate-limit checks.
7. **Submit** as **limit orders only** (entry + protective stop + target as a bracket / OCO).
8. **Manage**: monitor fills; on entry fill, confirm the protective stop is live *immediately*
   (no position may exist without a stop). Handle partial fills (track `leaves_qty`).
9. **Exit**: stop hit, target hit, time-stop, or a deterministic exit rule. Cancel the sibling
   OCO leg on exit.
10. **Settle & reconcile**: update settled-cash calendar (T+1); reconcile against broker.
11. **Reflect**: amend the journal record with realized return (raw + vs SPY) and a written
    reflection; update `setup_type` calibration stats and any do-not-repeat flags.

### 7.3 Exit discipline

- Every position has a **live hard stop** at all times (doc 03). The stop is a *broker-resident*
  order where possible, not a "we'll sell when we notice" intention - so a crash or outage does
  not remove protection.
- Take-profit at the bracket target; minimum reward:risk 1.5 was enforced at entry.
- A **time stop** closes positions that have neither hit stop nor target within
  `max_holding_period` (avoids dead capital and overnight/earnings drift).
- Future (gated off until proven): trailing stops, volatility-adjusted exits, dynamic targets.
  Not enabled in Phase 1–2 - they add path-dependence that must be backtested first.

---

## Part B - Failure Modes (#8)

For each: **detection** → **mitigation**. All halts route through the Risk Engine's
`trading_state` (doc 03 §3.2). The guiding reflex everywhere is **fail safe = do nothing**.

### 7.4 Data & infrastructure

| Failure | Detection | Mitigation |
|---------|-----------|------------|
| **Stale market data** | datum age > `max_data_age_seconds` | treat symbol as no-data → no trades on it; if the whole feed is stale → `REDUCING`, manage exits only |
| **API / broker failure** | request error / timeout / non-200 | bounded retries with backoff + idempotency key; on persistent failure → `REDUCING`, alert |
| **Internet outage** | heartbeat to broker/data fails | **dead-man's switch**: protective stops are broker-resident so they persist; new entries blocked; on reconnect → reconcile before acting |
| **Partial fills** | `filled_qty < order_qty` after timeout | track `leaves_qty`; re-evaluate vs current risk; cancel remainder rather than chase |
| **Execution failure / rejected order** | broker reject code | journal reason; do **not** blindly resubmit; if a protective stop failed to place → emergency flatten the unprotected position |
| **Restart during an active trade** | process start with open positions | startup **reconciliation** (below) before any new decision |

### 7.5 Startup reconciliation (restart / crash recovery)

On every process start, **before** proposing anything:

1. Pull broker **open orders + positions + recent executions**.
2. Diff against the journal's last known state.
3. Resolve divergences: an order stuck `SUBMITTED` past threshold → query status, mark
   `REJECTED`/`FILLED` from the truth, never re-fire blindly. A position or order present at the
   broker but absent from the journal → tag **`EXTERNAL`** and surface for review; **do not
   fabricate a duplicate**. A journal trade with no broker counterpart → assume unfilled
   (conservative) and reconcile.
4. Rebuild the persisted `trading_state` and Core Memory Block from this reconciled truth.
5. Only then resume the loop. (Lesson from NautilusTrader issue #3176: reconciliation reports
   must carry **stable** IDs, or you manufacture duplicate orders on every restart.)

### 7.6 Catastrophic / runaway (the Knight Capital class)

| Failure | Detection | Mitigation |
|---------|-----------|------------|
| **Runaway trading loop** | orders/sec or orders-per-decision exceed cap | rate throttle + **max-orders-per-decision** + **require ack/fill before the next order** + max child orders per parent; breach → `HALTED_DAY` |
| **Duplicate orders** | resend without persisted `client_order_id` | id generated + journaled **before** send; broker dedupes on the id |
| **Fat-finger / unit error** | order notional/qty exceeds max or implausible vs ADV | max-order-notional + lot/share sanity + pre-trade buying-power check → REJECT |
| **Bad deploy / dead code path** | n/a (process) | remove dead/disabled execution paths; never reuse config flags; reviewed, repeatable deploys; post-deploy assertion that the version is what's expected; runbook = **halt-and-flatten first, diagnose second** |
| **Corrupted state** | journal hash/sequence break, or risk-state file unreadable/inconsistent | `DISABLED_REVIEW` immediately; never trade on uncertain state; restore from append-only journal |
| **Memory corruption** | Core Memory sources inconsistent | skip the cycle (fail-safe); rebuild from journal; if unrecoverable → `DISABLED_REVIEW` |

### 7.7 LLM-specific failure modes (the model is untrusted)

| Failure | Detection | Mitigation |
|---------|-----------|------------|
| **Hallucinated signal / ticker / number** | ticker ∉ universe; cited number ≠ live feed beyond tolerance; signal not re-derivable | hard REJECT; the engine, not the model, owns all numbers |
| **Fabricated reasoning** | a plausible story is not evidence | the **signal must be re-derived deterministically** before any order; the argument is for humans/journal, not for execution |
| **Confidence drift / inflation** | stated vs realized hit-rate gap per `setup_type` | calibration discount; no carry-forward; confidence may only *lower* exposure (doc 05 §5.11) |
| **Model drift / silent version repoint** | canary eval regression on a fixed prompt set; logged model version/fingerprint | pin the exact model build; temperature 0 + fixed seed; log every prompt + output; eval harness gates any model change |
| **Prompt injection via ingested news** | instruction-like content inside data | all ingested text is **data, never instructions**; delimited as untrusted; plan-then-decide separation; **the LLM has no order tool to hijack** - the strongest mitigation |
| **Malformed / out-of-schema output** | JSON-Schema validation fails | constrained decoding (Outlines/Instructor) + auto-retry; persistent failure → skip candidate |

### 7.8 The universal fail-safe

When in doubt - stale data, ambiguous state, failed check, unreachable broker, unreadable file - 
the system **does nothing new and protects what's open.** Inaction is always a legal, safe move.
The most expensive mistakes in autonomous trading come from a system that *acts* through
uncertainty; this one is built to *wait* through it.
