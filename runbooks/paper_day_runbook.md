# Unattended Live-Data Paper Shakeout - Runbook (2026-06-22)

**Goal:** run one full market day to prove the system is *operationally sound* against the live
Alpaca data API - "it does not blow up" - while the user is AFK. This is NOT about making money.

## What is running and why it's safe
- Command: `.venv\Scripts\python.exe -m atlas.app --data alpaca --broker sim --interval 1800`
- **`--broker sim`** = SimBroker shadow fills. **NO real orders are sent to Alpaca.** It cannot lose
  money, get rejected, or move the account. The SimBroker has the full bracket/trailing/exit logic.
- **`--data alpaca`** = real Alpaca IEX daily bars (free tier, ~15-min delayed - fine for a daily
  strategy). One batched bars call per cycle.
- **No `--force-session`** → the clock gate skips out-of-session cycles. Started pre-market, it
  idles (`skip=out_of_session`) until 09:30 ET, runs real cycles during the session, idles after 16:00 ET.
- Safety nets already in place: HTTP timeout 180s on model calls (no infinite hang); the dual-model
  analyzer fail-closes on any model error (no-trade); risk kill-switches (daily 4% / weekly 9% /
  loss-streak); hash-chained journal; `app.py` refuses `mode: live`.

## Why NOT `--broker alpaca_paper` (verified 2026-06-22)
The paper account equity is **$250**, so every position is fractional, and **Alpaca rejects
bracket/stop orders on fractional shares** - every order would be rejected. The Alpaca adapter also
lacks exit-sync (server-side bracket exits would trip the reconcile→DISABLED_REVIEW halt) and a
`step()` that reports fills. Real paper orders need a larger paper balance (whole-share brackets) or
a fractional entry + managed-exit rewrite. Until then, `--broker sim --data alpaca` is the faithful,
safe venue. **Do not switch to alpaca_paper for this unattended run.**

## Per-wake procedures (cron fires these in CT; market is ET = CT+1h)

### Pre-market (~07:45 CT / 08:45 ET)
1. Model server: `GET http://localhost:8080/v1/models`. If down, start `scripts/serve_models.ps1`
   (background) and wait until both `glm-4.7-flash` and `qwen3.6-27b` respond.
2. `.venv\Scripts\python.exe scripts\preflight.py` → proceed only on **GO**. Fix any FAIL first.
3. Start the run in the background, logging to `runtime\paper_day.log`:
   `.venv\Scripts\python.exe -m atlas.app --data alpaca --broker sim --interval 1800`
4. Arm a Monitor on `runtime\paper_day.log` filtered to cycle/order/exit/error/halt lines.
5. Confirm cycle 1 printed (`[cycle 1] ... skip=out_of_session` pre-open is correct) and report.

### Midday checks (~10:05 and ~12:35 CT)
- Tail `runtime\paper_day.log`: cycles advancing? After 09:30 ET, `skip=None` cycles with
  cand/prop/orders. Before, `skip=out_of_session` is expected.
- Scan for red flags: `Traceback`, `Error`, `DISABLED_REVIEW`, `reconciliation_divergence`,
  `hash` break, or cycles that **stopped advancing** (hang).
- Check `runtime\decision_journal.jsonl` for any proposals/orders/exits, and
  `runtime\risk_state.runtime.json` for the trading_state.
- Verify the model server still responds.
- One-paragraph status. Intervene only on a red flag (see below).

### Post-close (~15:10 CT / 16:10 ET)
1. `TaskStop` the bot + the Monitor.
2. Summarize from the log + journal: cycles, candidates, proposals, shadow orders/fills, exits,
   halts/errors, final SimBroker equity + P&L, model-server stability.
3. Verify the journal hash chain (`DecisionJournal(...).verify_chain()`).
4. Write the outcome to memory; give the user a full end-of-day report incl. a clear
   "did / did not blow up" verdict and any fixes needed.

## Red flags → interventions
- **Bot process exited** (you get an auto-notification): read the tail, diagnose. If a transient
  model/network error, restart the run. If a real bug, STOP, capture the traceback, do not restart
  blindly - report it.
- **Cycles stopped advancing (hang)**: `TaskStop` the bot and restart it; note the last good cycle.
- **Model server unresponsive**: restart `serve_models.ps1`; the analyzer will have been skipping
  cycles safely meanwhile.
- **DISABLED_REVIEW / hash-chain break**: this is the system halting *safely*. Do NOT clear it.
  Record what tripped it and report - it's a finding, not a fire.
- Anything that would place a REAL order or touch real money: impossible here (sim), but if observed,
  STOP immediately.

## "Did not blow up" = success criteria
Ran the session without an unhandled crash; cycles advanced cleanly for hours; state + hash chain
intact; decisions were sensible (mostly passes given the known-thin edge); model server stable; no
runaway behavior. Profit is irrelevant for this test.
