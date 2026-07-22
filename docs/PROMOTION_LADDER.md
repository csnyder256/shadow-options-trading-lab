# THE PROMOTION LADDER - how any signal earns its way into the decision path

**Canonical discipline (2026-07-11; formerly referenced from `docs/OWNER_RULES.md`, retracted
2026-07-16 - see `docs/OWNER_RULES_RETRACTED.md`; the ladder stands on its own). Applies to EVERY
signal - AI-derived or mechanical. This is what "slightly casino, but educated" means
operationally: creative bets enter freely at the bottom; nothing gates a trade until the
platform's own WORST-ledger evidence says it earns its keep.**

```
Stage 0   SIDE ARTIFACT     exists under runtime/, no live process reads it
Stage 1   BRIEFING / HUB    humans see it premarket / on :8770; gates nothing
Stage 2   ENTRY COVARIATE   logged on shadow_entry rows - "graded at N, never gates"
Stage 3   N-GRADED          /eodreport association analysis at N>=25 on the WORST ledger
Stage 4   REPLAY COLUMN     pre-registered paired-replay variant (its own sweep row)
Stage 5   LIVE GATE / LANE  only on a PASS-bar row (N>=25, WORST mean net>0, gross>0,
                            PF>=1.2, top-day share<0.5)
```

## Rules

1. **One stage per registration.** Each climb is its own sweep-ledger row, appended BEFORE the
   stage takes effect.
2. **No skipping.** A signal cannot jump from briefing to gate; stage 3 evidence is the toll
   for stage 4, and stage 4's replay verdict is the toll for stage 5.
3. **Demotion is free; promotion never is.** Anything can be switched off or pushed down a
   stage without ceremony; climbing always costs a registration + evidence.
4. **LLM output always enters at stage 0.** No exceptions - including Claude's.
5. **Numbers in any artifact are code-computed.** An LLM tag can label; only registered
   deterministic code turns labels into thresholds, probabilities, or prices.
6. **The exit ladder is above stage 5.** It is not on this ladder; no signal climbs into it.
   The only sanctioned contact is mark-cadence acceleration (C5/news-shock class:
   observability, "WHEN we mark, never WHAT we do").
7. **p_thesis and any EV input are decision core.** Signals touching them live at stage 4
   (replay columns) until a PASS-bar row promotes them - see
   `opts-variant-pthesis-catmem-v1` (reserved id, not yet built).

## Why this exists

The +100% take-profit incident (2026-07-10; recorded in the since-retracted `docs/OWNER_RULES.md`
 - see `docs/OWNER_RULES_RETRACTED.md`) proved that unregistered
interpolations corrupt the authority chain. The ladder generalizes the lesson: enthusiasm
enters at the bottom, evidence does the climbing. It also protects the casino posture itself - 
a "smart" signal that silently gates entries without N-evidence is indistinguishable from a
superstition with good marketing.
