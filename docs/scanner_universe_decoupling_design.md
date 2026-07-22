# Scanner universe decoupling - design (2026-06-29)

Status: **BUILT + ENABLED 2026-06-29** (`config/robinhood.local.yaml: decoupled_universe: true`). On-demand
survivor bars (`AlpacaDataFeed.allow_on_demand`) + membership = universe ∪ scanner-surfaced (orchestrator
`_surfaced_allow` + `risk_engine.universe`). 493 tests green. The design below documents the approach.

## Problem (verified 2026-06-29)
In `--scanner` mode, a survivor outside the static `dynamic_screen` universe (`universe.yaml`,
`min_price 5 / max_price 100`) cannot trade:
1. **No bars.** `ScannerDiscovery.discover()` calls `MarketCollector.collect(symbols)` →
   `feed.get_bars(symbol)`. The collector is symbol-agnostic, but the live discovery **feed is seeded
   to the universe**, so `get_bars(<a >$100 non-universe name>)` returns `None` → the survivor is
   dropped (`if b is None: continue`).
2. **Membership reject.** Even with bars, `orchestrator.py:772` and `risk_engine.py:142` reject
   `not_in_universe`.

Net: every >$100 scanner hit (CRWD $743, SIMO $329, ASR $308, DLTR $122) dies before the analyst.
The server scans having "no price ceiling" (set 2026-06-28) is therefore moot - this universe cap is
the true blocker. (Predicted as a deferred follow-up in memory `rh-scanner-realtime-2026-06-24`.)

## Goal
In scanner mode, the tradable set = **whatever the scanner surfaced this session ∪ current holdings**,
with bars fetched on demand, while EVERY protective gate still runs (liquidity $-vol floor, spread,
leveraged/inverse exclusion, earnings, price>SMA200, 12mo-TSMOM, 52wk-proximity, don't-chase, fractional
sizing, the Guardian synthetic stop, concentration caps). Affordability for >$100 names is already solved
by fractional + Guardian (2026-06-28). Flag-gated, default OFF (byte-identical to today when off).

## Changes
1. **On-demand survivor bars.** Verify the scanner path's `DataFeed.get_bars`. If it only serves
   universe-seeded symbols, make survivor-bar fetch on demand:
   - Preferred: Alpaca daily-bar API fetches *any* US equity by symbol (daily bars are fine for the slow
     SMA/52wk/RS context the gates use). Confirm the feed isn't hard-pinned to a preloaded universe set.
   - Fallback (cleaner on the live RH path): pull survivor bars from RH `get_equity_historicals`.
   - Keep the staleness gate; cache per session to respect the ~15-burst MCP rate limit.
2. **Membership = universe ∪ scanner_surfaced ∪ holdings.** Maintain a per-session `scanner_surfaced`
   set (every ticker `discover()` returns - each carries a real RH `instrument_id`, so the
   hallucinated-ticker guard is preserved: the LLM can still only act on real, scanner-verified names).
   In scanner mode, the two membership guards accept `symbol ∈ (universe ∪ scanner_surfaced ∪
   open_holdings)`. A never-surfaced symbol still rejects `not_in_universe`.
3. **Sizing / sector.** Fractional sizing already handles >$100 (a $743 name → small fractional notional,
   Guardian-protected). `sector_map.get(symbol, "unknown")` already defaults unknown sectors gracefully →
   concentration tracked under an "unknown" bucket (works; caveat: many unknowns share one bucket - fine
   initially, revisit if it binds).
4. **RS table.** >$100 names aren't in the universe-built 12-1 RS table → neutral-RS fallback (already
   graceful). Optional follow-up: widen the RS build universe so they rank on merit.
5. **Flag.** `scanner_decoupled_universe: true` (config, default OFF) threaded app.py → orchestrator +
   discovery. OFF = today's behavior exactly.

## Tests
- discovery returns a >$100 surfaced name → not dropped (on-demand bars present).
- risk_engine accepts a surfaced >$100 symbol with fractional sizing; still rejects a never-surfaced one.
- unknown-sector symbol → concentration under "unknown", no crash.
- flag OFF → all existing tests unchanged/green.

## Rollout
Default OFF → unit + integration tests → ONE supervised min-size validation day (watch a >$100 fractional
lot: fill → Guardian ACK → trail/exit on the hub) → only then enable unattended.

## Open questions for review
- Survivor-bar source: Alpaca on-demand vs RH historicals (verify Alpaca can fetch arbitrary symbols on
  the live path; if not, use RH historicals).
- RS-table breadth: neutral-fallback initially vs widen the build now.
- Concentration "unknown" bucket: acceptable, or map sectors on the fly for surfaced names?
