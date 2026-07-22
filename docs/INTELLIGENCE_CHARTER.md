# ATLAS INTELLIGENCE CHARTER - how AI serves the options platform

**Adopted 2026-07-11 (owner-approved plan, intelligence-layer Wave 0). Supersedes the equity-era
two-family posture: `ANALYST_CONSTITUTION.md` / `AUDITOR_CONSTITUTION.md` are RETIRED to
`attic/` - that framework was survival-first ("don't blow up") adversarial filtration of
survivors. The platform's posture is now casino-esque risk-neutral EV-max ("slightly casino,
but educated", owner 2026-07-10), and its decision core is deterministic math. AI's job changed
accordingly: from FILTERING trades to SENSING, REMEMBERING, and NARRATING.**

## The five laws

1. **Async enrichment, synchronous consumption.** AI runs *beside* the trading loop - 
   continuously, in its own processes - writing annotations to its own files. The deterministic
   runner reads them in O(1) at decision time. **No AI call ever blocks a tick.** "Fast vs
   smart" is a false fork: precomputation delivers both.

2. **AI never computes a number that gates; code computes, AI tags/narrates/suggests.**
   An LLM may classify a headline's kind, tag a catalyst, narrate an exit, propose a candidate.
   It may not produce the threshold, probability, or price that a decision consumes - those are
   computed by registered deterministic code from AI-tagged inputs. LLM direction hints are
   covariates, never trade direction: **the tape decides.**

3. **Every AI-derived signal walks the promotion ladder** (`docs/PROMOTION_LADDER.md`) - 
   side artifact → briefing → logged covariate → N-graded → replay column → live, one
   registered stage at a time. LLM output always enters at stage 0.

4. **Untrusted-data law.** All external text reaches models inside fenced UNTRUSTED-DATA
   blocks (reuse `atlas/crew/consensus.py` fencing); output passes drop-never-repair
   validation against closed enums; a classifier may never mint a ticker that was not in its
   input. **Public market data only to cloud models** (headlines, symbols, calendars,
   prior-day stats - never positions, P&L, sizing, or strategy internals). Anything touching
   positions/P&L runs on LOCAL models (127.0.0.1:8080), exclusively.

5. **Ops law.** AI side-processes write their OWN append-only files (the shadow's
   single-writer ledgers are untouchable); no second process shares a Tradier token; the exit
   ladder is untouchable by AI in any form (owner directive 2026-07-11 - the position-watcher
   stays deterministic; the only sanctioned touch is C5-style mark-cadence acceleration:
   "WHEN we mark, never WHAT we do"); every AI component pre-registers in
   `runtime/backtest_out/sweep_ledger.jsonl` before first effect.

## The two engines and their roles

| Engine | When | Role |
|---|---|---|
| **Cloud free tiers** (groq fast-lane; openrouter/cerebras/zai batch; gemini excluded from fast tasks) | premarket crew fan-out; intraday headline classification (groq); weekly peer-map batch | public-data sensing at near-zero latency/cost |
| **Local models** (GLM-4.7-Flash, Qwen3-30B-Thinking, scouts - the owner's 24/7 rig) | RTH: warm fallback for the headline classifier (GLM resident, scouts cold). Overnight: catalyst tagging, exit-quality narratives, anomaly answering, memory curation inputs | the sovereign engine - unlimited, private, allowed to see P&L |

## Standing rejections (do not re-propose without NEW evidence)

WSB/Reddit as a LONG signal (Bradley RFS 2024 - attention-*acceleration* as a direction-agnostic
in-play detector is the sanctioned framing); hold-through-print variants; 0DTE-specific flow
signals; 8-K Item 1.01 triggers; crypto→equity lead-lag; PRNewswire polling (ToS); paid vendors;
LLM chart-reading (≈chance, 2026-06-28 verdict); embeddings/vector stores where a closed enum +
SQLite suffices.

## Component registry (grows as the ladder is climbed)

| Component | Stage | Registration |
|---|---|---|
| Premarket crew → hunt_list | 1.5 (grandfathered look-trigger; every candidate walks all gates) | opts-fix-huntlist-candidates-key |
| C6 news classifier (news_flag_tap) | 0 → consumers registered separately | opts-svc-news-flag-tap-v1 |
| Mention-acceleration tap | 0 (baseline accruing) | opts-svc-mention-tap-v1 |
| Catalyst event archive | 0 (evidence factory) | opts-catalyst-archive-v1 |
| Catalyst memory store + recall | 0 → 1 (briefing) planned | opts-catmem-store-v1 |
| IV surface collector | 0 (evidence factory; unblocks IV-rank/skew/GEX covariates ~mid-Sep) | opts-iv-surface-v1 |
| Overnight lab jobs A–D | 0 (narration/tagging, feeds /eodreport) | opts-lab-jobs-v1 |
