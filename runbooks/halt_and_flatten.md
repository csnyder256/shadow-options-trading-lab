# Runbook: Halt & Flatten

Use when you need to stop the system and/or close everything immediately.

## Stop new entries (soft)
The risk engine blocks new entries whenever `runtime/risk_state.runtime.json` `trading_state` is
not `ACTIVE`. To halt new entries without touching open positions:

1. Edit `runtime/risk_state.runtime.json` → set `"trading_state": "HALTED_DAY"` (or `DISABLED_REVIEW`).
2. The next cycle reads it from disk and stops proposing. Broker-resident stops on open positions
   remain in force.

## Kill the loop
- `Ctrl+C` the `python -m atlas.app` process, or `Stop-Process -Name python` for the app process.
- Stop the model server: `Stop-Process -Name llama-swap` (also frees VRAM).

## Flatten all (close every position)
The SimBroker has no live money. For a live/paper venue:
1. Halt first (above).
2. Cancel resting orders and submit closing orders **manually in the broker UI** - per the
   project's standing rule, the agent never executes a flatten on your behalf.
3. After flattening, set `trading_state` to `DISABLED_REVIEW` and review the journal before
   re-enabling.

## After any halt
- `python -c "from atlas.memory import DecisionJournal; from pathlib import Path; print(DecisionJournal(Path('runtime/decision_journal.jsonl')).verify_chain())"`
  must print `(True, None)` - a broken chain means tampering/corruption; do not resume.
- Human-review the recent journal records before flipping `trading_state` back to `ACTIVE`.
