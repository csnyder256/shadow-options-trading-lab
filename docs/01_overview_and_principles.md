# 01 · Overview & Design Principles

## 1.1 Prime directive

> Preserve capital first. Generate consistent, auditable, recoverable decisions second.
> Make money third - and only as a *byproduct* of the first two.

Every other rule in this framework descends from that ordering. When two rules conflict, the
one closer to "preserve capital" wins. When the model is uncertain whether an action is
allowed, the answer is **no**.

## 1.2 The separation of powers (the most important architectural decision)

The system is deliberately built like a constitutional government with separated, mutually
limiting powers. No single component - least of all the LLM - can both *want* a trade and
*cause* a trade.

| Power | Held by | Can it place an order? | Can it change a risk limit? |
|-------|---------|------------------------|------------------------------|
| **Propose** (generate hypotheses, arguments, confidence) | GLM-4.7-Flash analyst + Qwen3.6-27B auditor | **No** | **No** |
| **Decide** (combine scores, apply rules) | Deterministic Consensus + Risk Engine | Only within hard limits | **No** |
| **Veto** (block anything unsafe) | Risk Engine | n/a (it only blocks) | **No** |
| **Execute** (place/cancel orders, manage state) | Execution Layer | Yes, but *only* pre-validated orders | **No** |
| **Amend the rules** | **The human operator**, via versioned `config/` files + redeploy | n/a | **Yes** |

The LLM is an **untrusted proposal generator**. This is not an insult to the model; it is the
only safe way to use *any* probabilistic component to influence real money. The Knight Capital
failure (~$460M lost in 45 minutes in 2012) happened precisely because a component that should
have been *limited* was instead *trusted*. We do not repeat that.

## 1.3 The "rotating analyst after compaction" problem - stated plainly

You are right to be worried. Here is the failure mode in precise terms:

Each model runs continuously. Its context window has finite size. As the session accumulates
observations, the runtime will **compact, summarize, or truncate** older context to make room.
After such an event, the model has effectively *forgotten* the earlier parts of its own
reasoning. In a chat assistant this is a minor annoyance. In a 24/7 autonomous trader it is a
**solvency risk**, because the post-compaction model:

- forgets *why* an open position was entered (its original thesis, stop, and target);
- re-proposes a setup it already tried and lost on last week ("amnesia loop");
- loses its own confidence calibration and drifts toward over-confidence;
- contradicts decisions its earlier self made an hour ago;
- behaves like a **different analyst rotating into the seat every few hours** - inconsistent,
  un-accountable, and prone to repeating mistakes.

This is documented in the agent-research literature as **"agent drift"**: the context fills
with stale or summarized information that dilutes signal and degrades decision quality over
long horizons.

### The solution, in one sentence

**Stop relying on the context window for anything that matters.**

We treat the LLM as **stateless between cycles by design.** Every decision cycle, a
deterministic orchestrator *reconstructs* the model's entire relevant world from durable
on-disk storage and serves it fresh:

- a **Core Memory Block** (positions, theses, rules, budget, recent lessons) regenerated from
  ground-truth files and re-injected *verbatim every cycle*;
- a **Decision Journal** (append-only, P&L-keyed) that is the real long-term memory;
- a **retrieval step** that pulls the most relevant past entries by recency × relevance ×
  importance and injects only those.

Because the orchestrator rebuilds context from disk on every cycle, **compaction of the
in-flight context is irrelevant** - there is nothing important in there to lose. The analyst's
*identity* is defined by static, version-controlled role constitutions (`ANALYST_CONSTITUTION.md` + `AUDITOR_CONSTITUTION.md`, archived with the equity system and not shipped here),
re-served every cycle, not by accumulated chat history. The seat never rotates because the
occupant is reconstituted identically each time.

Full mechanism: [`docs/05_memory_and_rotating_analyst.md`](05_memory_and_rotating_analyst.md).
This is the centerpiece of the framework.

## 1.4 Determinism is a feature, not a limitation

Anywhere a number can be computed by plain code, it **must** be - not asked of the LLM.
The LLM may *argue about* RSI being overbought; it may not *report the RSI value*. The value
comes from the deterministic Signal Engine. This gives us three things money depends on:

- **Reproducibility:** the same inputs always produce the same signals and the same risk
  decision, so we can backtest and audit them.
- **Hallucination immunity:** a fabricated price or ticker cannot enter the decision because
  every number is re-checked against the feed and every signal is re-derived in code.
- **A clean blame boundary:** if a trade was bad, we can tell whether the *data*, the
  *signal*, the *argument*, or the *rule* failed - because each is logged separately.

## 1.5 What this system is NOT

- **Not high-frequency / low-latency.** Decision cadence is minutes, not microseconds. We
  never compete on speed. If a trade requires being fast, we don't take it.
- **Not an unrestricted autonomous AI.** The AI's authority is bounded to *argument and
  scoring*. It has no tools that move money.
- **Not a profit maximizer.** See §1.1.
- **Not a black box.** Every decision is reconstructable from the journal months later.
- **Not "set and forget."** It runs autonomously but is *supervised*: a human reviews the
  journal, holds the only keys to the risk config, and can kill it instantly.

## 1.6 The six optimization targets (in priority order)

1. **Survival** - never take a loss that ends the experiment or the account.
2. **Consistency** - same situation → same behavior, cycle after cycle, across restarts.
3. **Auditability** - every decision fully reconstructable from durable logs.
4. **Recoverability** - any crash/restart resumes to a correct, reconciled state.
5. **Long-term scaling** - the path from $250 to larger capital is built in and makes the
   system *progressively harder to damage*.
6. **Catastrophic-error prevention** - fat-finger, runaway loop, duplicate order, and
   hallucinated-trade classes are structurally impossible, not merely unlikely.

Hold these six in mind reading every other document. They are the acceptance criteria for the
whole system.
