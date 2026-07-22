# 06 · Portfolio Scaling Logic

Requested output **#7**. Machine values in [`config/position_sizing.yaml`](../config/position_sizing.yaml).

## 6.1 Principle: the account gets *harder to damage* as it grows

The defining property of the scaling logic is **monotonic de-risking**: every step up in equity
makes the system more conservative, never more aggressive. The only place the system is
*permitted* to be fragile is the very first tier ($250–$1,000), and only because that money is
pre-designated as an experiment you have agreed to lose. Above that, capital preservation
tightens automatically and irreversibly (absent a human editing the config).

## 6.2 The tier ladder

| Tier | Equity | Mode | Max position | Min cash reserve | Per-trade risk | Options |
|-----:|--------|------|-------------:|-----------------:|---------------:|---------|
| 1 | $250 – $1,000 | aggressive-experimental | 22% | 50% | 2.0% | **paper-only** (< $2k) |
| 2 | $1,000 – $5,000 | normal | 14% | 40% | 1.5% | enabled at $2k if broker supports |
| 3 | $5,000 – $10,000 | conservative | 9% | 35% | 1.0% | enabled |
| 4 | $10,000+ | capital-preservation | 4% | 30% | 0.75% | enabled |

Notes:
- **Position size** = capital deployed. **Per-trade risk** = how much of equity the stop can
  lose; it is the *binding* survival number and it steps *down* every tier.
- The cash reserve relaxes slightly as the account grows (you can afford more positions when a
  position is a smaller fraction), but never below 30% in this design.
- `options_live_min_equity` ($2,000) sits inside Tier 2, so options can only ever go live once
  the granularity wall (doc 03 §3.3) has been cleared *and* the broker enables them.

## 6.3 Tier transitions (hysteresis to avoid thrashing)

Tier is evaluated on **end-of-day settled equity**, with **hysteresis**: you move *up* a tier
only after closing **above** the threshold for `tier_promote_days` consecutive sessions
(default 5), and you move *down* immediately if equity closes **below** the lower band. This
prevents a single good or bad day from fl-flopping the entire risk posture mid-session. Tier is
re-evaluated **between** sessions, never inside one, so sizing is stable within a day.

## 6.4 Scaling is opt-in and gated, never automatic-to-the-moon

Crossing into a higher *capital* tier loosens nothing the operator hasn't pre-approved in
`config/`. There is **no mechanism by which good performance increases aggression.** A winning
streak does the opposite of what a martingale gambler does: it banks the gain into a higher
equity base that is then governed by *stricter* tier rules. Compounding happens through a larger,
better-protected base - not through bigger bets.

## 6.5 Profit-banking (optional, recommended)

An optional rule (`position_sizing.yaml: profit_bank`) sweeps a fraction of realized gains above
a high-water mark into a non-traded reserve once the account clears a milestone (e.g. above
$1,000, bank 25% of gains beyond the prior high-water mark). This makes drawdowns measure
against a *protected* floor and structurally prevents "round-tripping" a doubled account back to
the start. Off by default in Tier 1 (too small to matter), recommended from Tier 2.

## 6.6 What never scales

- The **separation of powers** (doc 01 §1.2) - the LLM never gains execution authority at any
  account size.
- The **kill switches** - drawdown/streak halts apply at every tier (the percentages may
  tighten, never loosen).
- The **defined-risk-only** rule for options - no naked exposure is ever unlocked by size.
- The **audit/journal discipline** - larger accounts get *more* logging and review, not less.
