# Claude runbooks - the things the control panel CAN'T do

The control panel (`scripts/control_panel.py`, http://127.0.0.1:8771/) changes **deterministic config**:
risk %, stops, concentration, cash reserve, confidence floor, take-profit, Guardian knobs, the master
risk-appetite dial, etc. Those write `runtime/control_overlay.json` and apply on the next launch.

Some things live **outside** that config and need Claude (me) to act - server-side Robinhood scans, model
constitutions, code-level strategy/feature changes. For each, copy the **prompt** into a Claude Code session
in this repo. Each prompt is self-contained so a cold session can act. I will always confirm and show you
the change before committing anything that touches real money or the live account.

> Context every prompt assumes: repo at `C:\path\to\shadow-options-trading-lab`;
> live venue = Robinhood agentic CASH account `<ACCOUNT-NUMBER>`; the 3 live scans are
> A/B/C = the continuation / breakout / pullback saved scans, whose ids live in `config/scanner.yaml`
> (placeholder UUIDs in this public copy - substitute your own);
> the binding price/liquidity gate in `--scanner` mode is the **server-side** saved scan (run by UUID),
> NOT `config/scanner.yaml` (which is reference-only). Use the RH MCP `get_scans` / `update_scan_filters`
> / `create_scan`; `update_scan_filters` is REPLACE semantics (resend every filter).

---

## 1. Retune the scans for a risk appetite (the universe half of the dial)
The panel's risk-appetite dial moves the *client-side* risk params. The *candidate universe* (how strict
the scans are) is server-side. To match the scans to an appetite:

> **Prompt:** "Set my scan universe to risk appetite **N/10** (0 = blue chips, 10 = degen). Read the 3 live
> scans with `get_scans`, then `update_scan_filters` on each to scale: market-cap floor (blue chips ≥ $50B …
> degen ≥ $300M), price floor (keep ≥ $5; never a ceiling now we're fractional), RVOL and ADX/RSI bands
> (looser = more names). Keep each scan's setup identity (A=continuation, B=breakout, C=pullback). Show me
> the before/after filters and the new match counts before you finalize."

## 2. Narrow the scans back for a whole-share day
If you run a day with fractional OFF, the open universe wastes the cascade on >$100 names.

> **Prompt:** "Fractional is OFF today - put the 3 live scans back to the whole-share band: set
> `FILTER_TYPE_LAST` to `BETWEEN [5,100]` on scans A/B/C via `update_scan_filters` (keep all other filters
> as-is). Confirm with `get_scans`."

## 3. Add a brand-new scanner (a new discovery axis)
> **Prompt:** "Create a new RH scan for **<describe the setup, e.g. '52-week-high breakouts with RVOL>3'>**
> using `create_scan`, then add it to `config/scanner.yaml` (a new A/B/C-style entry with its UUID +
> setup_type) so the poller rotates it in. Cite each filter threshold to an established system and show me
> the live match count before wiring it."

## 4. Edit a model constitution (analyst / auditor reasoning)
The analyst/auditor are driven by `ANALYST_CONSTITUTION.md` / `AUDITOR_CONSTITUTION.md` (static prompts).
The panel's **LLM risk-posture** slider nudges them softly; a real behavior change is a constitution edit.

> **Prompt:** "In `ANALYST_CONSTITUTION.md`, change **<the rule>** - e.g. 'weight news/catalysts more for
> momentum setups' / 'be stricter on extended entries'. Keep the output schema and the don't-explode rules
> intact, show me a diff, and run the suite."

## 5. Add a new strategy / setup_type
> **Prompt:** "Add a new setup_type **<name>** end-to-end: scanner discovery (scan + `scanner.yaml`),
> `setup_exits` in `risk_limits.yaml` (trailing vs fixed-target), any signal features it needs, and tests.
> Research the edge first and tell me if it's worth it (cite evidence; reject if it's a coin-flip)."

## 6. Change the liquidity floor (currently code, not config)
The `dollar_vol_floor` (5M) lives in `atlas/scan/context.py` (`ContextParams`). To make it a panel slider,
or to change it now:

> **Prompt:** "Make `ContextParams.dollar_vol_floor` config-driven (read from `signal_params.yaml`) and add
> it to the control-plane registry (`atlas/control_plane.py`) as a slider; OR just set it to **$Xm** for now.
> It's a fill-quality / thin-name screen (plus the RH-buggy-volume `market_cap≥2B` proxy) - keep it sane."

## 7. Flip to the margin profile (post-FINRA-4210 world)
PDT is DEAD (FINRA 4210 amendments, effective 2026-06-04; Robinhood migrated day one) - there is no
day-trade counting anywhere, so OLD_PDT is a legacy no-op. The agentic account is CASH today, and RH
allows only ONE margin account per customer (the individual account holds that slot); whether the
agentic account type can ever be margin is undocumented. IF Robinhood someday lets the agentic
account read `type: margin`:

> **Prompt:** "The agentic account now shows type=margin at the broker. Set `account_regime:
> INTRADAY_MARGIN` (panel → System). Preflight already verifies the config against the broker's
> account type (NO-GO on mismatch) and the runtime forces CASH semantics fail-closed. Verify:
> (1) sizing spends buying_power, (2) the daily budget uses `margin_daily_deployment_pct` x
> `day_start_spendable` (the anchor prevents the proceeds-recycling ratchet), (3) one shadow day
> before trusting it."

Until then: the CASH regime already allows unlimited day trades on settled funds; the daily capital
budget (`daily_deployment_pct`) is the throttle, and T+1 recycling is the natural constraint.

## 8. Tune the ATR trailing multiple (do NOT eyeball it)
`atr_multiple` is 3.5 - picked by a 2026-06-21 OOS sweep (wider rode winners better). The panel slider
exists but warns. Don't change it on vibes:

> **Prompt:** "Re-run the ATR-multiple sweep on the trade ledger (and add synthetic-stop / continuous-
> trailing modeling to the backtester first, since the Guardian trails every ~5s vs the backtest's periodic
> model). Recommend a multiple with the OOS numbers; only then change it."

---

### Notes
- Anything touching the live account or real money: I confirm + show you first.
- Server-side scan edits take effect immediately (next `run_scan`); config/overlay edits take effect on the
  next launch.
- After any code change I run the test suite and report results.
