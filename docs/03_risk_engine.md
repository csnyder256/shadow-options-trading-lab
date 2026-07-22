# 03 · Risk Engine - the Highest Authority

Requested output **#3**. The numbers here are mirrored, machine-readable, in
[`config/risk_limits.yaml`](../config/risk_limits.yaml) and
[`config/position_sizing.yaml`](../config/position_sizing.yaml). **The code reads the YAML.
This document explains the YAML.** If the two ever disagree, the YAML wins and the doc is a bug.

## 3.1 Status and powers

The Risk Engine is **deterministic code**. It is the final gate before execution. It has
exactly two outputs for any proposed trade:

- **REJECT** (with a named reason), or
- **APPROVE at a specific size, with a specific hard stop and take-profit.**

It can never be argued with. The LLM cannot read, set, or reason its way around it. The only
way to change a risk limit is for a **human to edit `config/` and redeploy** - a slow,
reviewable, version-controlled act, by design. The entity that can change a limit (human +
git) is organizationally separate from the entity being limited (the model) - the same
principle SEC Rule 15c3-5 requires of brokers.

## 3.2 The trading-state machine (halt authority lives here, not in the strategy)

The Risk Engine owns a single persisted variable, `trading_state`, written to disk
out-of-band. The strategy and the LLM have **read-only** visibility of it; neither can clear it.

| State | Meaning | What is allowed |
|-------|---------|-----------------|
| `ACTIVE` | normal | new entries, exits, everything |
| `REDUCING` | de-risking | **no exposure-increasing orders**; exits and cancels only |
| `HALTED_DAY` | day's risk budget spent | exits/cancels only; auto-clears next session |
| `DISABLED_REVIEW` | a protective limit tripped | **nothing** until a human reviews and re-enables |

Transitions are triggered by deterministic checks (below), never by the model. `DISABLED_REVIEW`
**requires human action to leave** - there is no automatic recovery from a serious breach.

## 3.3 Position sizing (and the $250 granularity wall)

### Equity-tiered caps (from `config/position_sizing.yaml`)

| Portfolio value | Max **position size** (% of equity) | Min cash reserve |
|-----------------|-------------------------------------|------------------|
| $250 – $1,000 | 33% (aggressive experimental) | 25% |
| $1,000 – $5,000 | 14% | 40% |
| $5,000 – $10,000 | 9% | 35% |
| $10,000+ | 4% | 30% |

These are **position-size** caps (how much capital is *deployed*). They are an upper bound, not
a target. The *risk* taken is much smaller because of the hard stop (next section).

### The single unified sizing formula

```
units = floor_to_tradable( (equity × per_trade_risk_pct) / per_unit_risk )

  per_unit_risk depends on instrument:
    equities (fractional ok):   per_unit_risk = entry_price − stop_price
    volatility-based stop:      per_unit_risk = atr_multiple × ATR(N)
    defined-risk options:       per_unit_risk = (spread_width − net_credit) × 100   # max loss/contract
```

`per_trade_risk_pct` default = **2.5%** of equity at tier1 (`position_sizing.yaml`, per-tier).
The result is then **clamped down** to whichever is smaller: the risk-based size, the
equity-tier position cap, the available *settled* cash, and the concentration caps. Size is only
ever reduced by additional constraints, **never increased** by confidence or by the model.

### The granularity wall - stated honestly and handled

At $250, `2.5% × $250 = $6.25` of acceptable risk per trade. The stop is ATR-based (≈3.5×ATR,
capped at an 8%-of-entry width), so the position sizes to risk that $6.25 - roughly a **31%
position** (~$78). Because the 35% single-stock cap and 33% tier cap sit just above this, the
**per-trade risk budget is what binds** - the account genuinely risks ~2.5%, not a token fraction.

- **Equities w/ fractional shares:** fractional shares make sub-$1-per-share allocations
  *possible*, so **sizing works for equities even at $250.** A whole-share floor would round a
  small allocation to zero (the granularity wall); fractional shares rescue it. This is why
  equities are the live vehicle in Phase 2.
- **Options:** the *cheapest* defined-risk spread risks ~$30–$95 per contract - **6–19× the
  entire risk budget.** You cannot buy a fractional option. Therefore one options trade would
  breach the per-trade risk limit by an order of magnitude.

**Resolution (hard rule):** options are **disabled in live** until
`equity ≥ options_live_min_equity` (default **$2,000**) *and* the live broker's
`capabilities().options == true`. Below that, options run **paper-only on Alpaca** for strategy
validation and are routed away from the live adapter automatically. This is not a preference;
it is enforced in `config/system.yaml: capability_gates` and re-checked by the Risk Engine on
every options proposal. The system will *log the wall explicitly* rather than silently shrink to
"one contract = 38% of the account."

## 3.4 Hard constraints (every one is a REJECT condition)

All values live in `config/risk_limits.yaml`. Defaults shown.

**Per-trade (trend-following profile, retuned 2026-06-21)**
- Per-trade risk ≤ **2.5%** of equity at tier1 (via the initial stop distance), stepping down
  with size in the higher tiers.
- **Volatility-based stop**, not a flat %. Initial stop = `entry − atr_multiple × ATR`
  (default **3.5×ATR**, retuned from the 2026-06-21 historical sweep - wider trails rode winners
  better out-of-sample), never *wider* than `hard_stop_pct` (**8%** of entry). No position may
  exist without a live stop.
- **Exit by setup type** (`risk_limits.yaml: setup_exits`):
  - *Momentum/trend* (`breakout_with_volume`, `momentum_continuation`, `relative_strength_leader`)
    → **Chandelier trailing stop**: as price makes new highs the stop ratchets up to
    `highest_high − 3.5×ATR`, never down - winners run, the trade exits when the trend turns
    down. A far **+25%** take-profit is only a backstop for a parabolic spike.
  - *Mean-reversion* (`range_reversion`, `pullback_in_uptrend`) → **fixed target** at
    `fixed_target_reward_risk` (**2×**) the initial stop distance; no trailing.
- Minimum reward:risk = **2:1** (structure that can't reach 2:1 is rejected before sizing; trend
  systems run ~30–45% win rates and profit from the high R:R, not from being right often).
- **Defined-risk options only.** No naked short options, ever. Max loss bounded *before* entry.

**Frequency & exposure**
- Max **2 trades/day**. Max **2 concurrent positions**.
- Max single-stock exposure **35%** (lets tier1's 33% position cap govern); single-sector
  **40%**; single correlated-thesis **40%**.
- **No averaging down. No pyramiding into a losing position. No martingale / doubling after a
  loss. No revenge trading** (enforced via the loss-streak throttle + cooldown, §3.6).

**Cash & settlement**
- Maintain a tiered cash reserve: **≥ 25%** at tier1 (down from 50% - half-idle is wasteful on
  $250 of pre-designated tuition), rising to 30–40% in the higher tiers.
- Cash account default: **buy only with settled cash** (T+1). Block selling a position bought
  with unsettled proceeds until it settles (prevents Good-Faith Violations). Never pay for a
  buy by selling that same security (prevents freeriding). Track rolling 12-month violation
  counters; 1 freeride or 3 GFVs → 90-day lockout, so the engine hard-blocks the *action that
  would cause* the violation.
- If run on margin under the **old PDT regime** (broker not yet migrated, equity < $25k):
  hard-cap at **3 day trades per rolling 5 business days**; block the 4th. Regime is a config
  flag (`OLD_PDT | INTRADAY_MARGIN | CASH`) because both regimes are live during the 2026–2027
  phase-in. **Default for $250 = `CASH`.**

## 3.5 Daily / weekly protection (drawdown kill switches)

Drawdown checks **include open-position unrealized P&L and fees**, so an adverse open position
can trip a halt *before* any trade closes. Each cycle the engine captures a **start-of-period
equity reference** (the marked-to-market account value at the day's / week's first cycle) and
measures drawdown as the % *loss from that reference* - a period **loss limit**, not a
peak-to-trough trailing drawdown. (Peak-to-trough would halt the whole account merely for an open
winner giving back unrealized gains, which fights a trend strategy that rides wide trailing stops.)
The reference resets at the new session/week; `HALTED_DAY` auto-clears the next session (§3.2),
while `DISABLED_REVIEW` never auto-clears.

- **Daily max drawdown = 4%** (configurable 3–5%). On breach → `trading_state = HALTED_DAY`:
  cancel working entries, keep protective stops, place no new entries until next session.
- **Weekly max drawdown = 9%** (configurable 8–10%). On breach → `trading_state =
  DISABLED_REVIEW`: live trading off, human review required.

## 3.6 Loss-streak protection (anti-revenge, anti-martingale)

- **3 consecutive losses** → position-size multiplier **× 0.5** and a cooldown
  (`cooldown_minutes`, default 60) blocking new entries.
- **5 consecutive losses** → `trading_state = DISABLED_REVIEW` (human review required).

"Consecutive" counts closed trades in order. The multiplier resets only after a winning trade,
not after the cooldown - the system de-risks after losses and **never** re-risks to "win it
back."

## 3.7 Confidence handling (confidence never buys risk)

Confidence is **untrusted metadata** from the LLM. It can only ever *lower* exposure or block a
trade - never raise size or bypass a limit.

| Consensus confidence | Effect |
|----------------------|--------|
| < 60 | **No trade.** |
| 60–74 | Eligible, **small** position (size multiplier 0.5). |
| 75–89 | Eligible, **normal** position (multiplier 1.0, still capped). |
| 90+ | Eligible, still **position-capped** - 90+ grants *nothing* beyond the tier cap. |

Crucially (anti-drift): confidence is **recomputed every cycle from scratch** and **never
carried forward** from a prior cycle. It is also cross-checked against the model's own realized
hit-rate stored in the journal; persistent over-confidence (stated ≫ realized) automatically
*discounts* future confidence. See [`05_memory_and_rotating_analyst.md`](05_memory_and_rotating_analyst.md) §6.

## 3.8 Market-condition restrictions (no-trade windows)

The Risk Engine blocks **all new entries** when any of these hold (`risk_limits.yaml:
market_blackouts`):

- Within **10 minutes of the open** (first 10 min - no new trades).
- Within **±N days of a position's earnings** (`earnings_blackout_days`, default 2).
- During a **major economic release** window (CPI, FOMC, NFP, etc., from the macro calendar).
- During an **abnormal volatility spike** (e.g. VIX > threshold, or symbol ATR z-score >
  threshold).
- During **detected market instability** (LULD/MWCB halt states, breadth collapse).
- During **extremely low liquidity** (symbol fails the universe liquidity filter, or
  pre/post-market).

A blocked window means the cycle does its analysis but the Risk Engine returns REJECT with the
specific blackout reason, which is journaled.

## 3.9 Capital-preservation scaling (harder to damage as it grows)

As equity rises, the engine automatically tightens: position caps shrink (table §3.3), cash
reserves... can relax slightly but stay conservative, and per-trade risk % may step down. The
*intent* encoded in `position_sizing.yaml` is monotone: **a larger account is always better
protected, never more aggressive.** The aggressive-experimental posture exists **only** in the
$250–$1,000 tier and is the one place the system is *allowed* to be fragile - because that money
is pre-designated as tuition. Full logic: [`06_portfolio_scaling.md`](06_portfolio_scaling.md).

## 3.10 The 10 non-negotiable hard constraints (engineering checklist)

A reviewer should be able to point at code for each of these:

1. The LLM can **never** place an order; it emits a schema-validated proposal only.
2. Daily max-loss kill switch (incl. unrealized P&L) → `HALTED_DAY`, cancel + flatten-to-stops.
3. Per-trade risk ≤ 2.5% of equity (tier1); defined-risk only; every position has a live ATR/trailing stop.
4. Idempotent client-order-id generated and journaled **before** every send.
5. Order-rate throttle + max-orders-per-decision + require ack/fill before the next order.
6. Max single-order notional + max aggregate exposure + pre-trade settled-cash/buying-power check.
7. Settled-cash/T+1 enforcement (cash account) or active PDT/IML regime (margin).
8. Price-collar sanity check; reject if ticker ∉ universe or any number ≠ live feed.
9. Consecutive-loss throttle + cooldown (anti-revenge).
10. Halt on market-state anomalies, stale data, or broker disconnect (heartbeat / dead-man's switch).
