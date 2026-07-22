# 04 · Signal Engine

Requested output **#4**. Thresholds live in [`config/signal_params.yaml`](../config/signal_params.yaml).

## 4.1 Purpose and the trust rule

The Signal Engine is **deterministic code** that turns raw market data into numeric, named,
reproducible features and candidate setups. It is the *only* legitimate source of indicator
values in the system.

> **Trust rule:** every number the LLM is allowed to reason about comes from here. The LLM may
> argue "RSI is overbought and divergent from price"; it may **not** state the RSI number. If a
> proposal cites a value, step 8 of the runtime loop re-derives that value here and rejects the
> proposal on mismatch. This makes hallucinated indicators structurally unable to drive a trade.

## 4.2 Indicator catalog (all required by the spec)

Implemented with **TA-Lib** (C-backed, deterministic) plus **`ta` (bukosabino)** for VWAP and
volume indicators TA-Lib lacks. A handful are not provided by any library and are implemented
as small, **unit-tested deterministic functions** - which is *ideal*, because it keeps them
reproducible and auditable.

| Feature | Source | Notes |
|---------|--------|-------|
| Moving averages (SMA/EMA) | TA-Lib | trend context, MA cross |
| VWAP | `ta` (or manual) | intraday fair-value anchor |
| RSI | TA-Lib | overbought/oversold + divergence |
| Trend strength (ADX) | TA-Lib | filter chop vs trend |
| Volatility (ATR, Bollinger) | TA-Lib | stop distance + regime |
| Momentum (MOM/ROC/MACD) | TA-Lib | impulse |
| OBV / volume | TA-Lib | confirmation |
| **Support / resistance** | custom | rolling pivots / swing highs-lows + clustering |
| **Gap detection** | custom | prior close vs today open, gap % + fill state |
| **Volume anomaly** | custom | rolling z-score of volume vs N-day mean/std |
| **Relative strength** | custom | symbol return ÷ benchmark (SPY) return over window |

All custom functions take a price/volume frame and return scalars + booleans, with no hidden
state, so a backtest and a live cycle compute them identically.

## 4.3 Candidate setup contract

The engine emits zero or more **candidate setups**, each a plain record:

```yaml
candidate:
  symbol: AAPL
  asof: 2026-06-19T14:32:00Z          # data timestamp (freshness-checked)
  setup_type: pullback_in_uptrend # named, enumerable
  direction: long
  features:                            # ALL numeric, reproducible
    rsi_14: 41.2
    adx_14: 27.8
    atr_14: 1.83
    dist_to_vwap_pct: -0.4
    vol_zscore_20: 2.1
    rel_strength_20: 1.06
    gap_pct: 0.0
  proposed_levels:                     # deterministic, from ATR/structure
    entry: 191.20
    hard_stop: 187.40
    take_profit: 197.10
    reward_risk: 1.55
  liquidity:
    avg_dollar_vol_20d: 8.9e9
    spread_bps: 1.2
  quality_score: 0.0-100               # deterministic composite (see 4.4)
```

The candidate is fully self-describing and reproducible. The LLM receives this record (plus
retrieved memory) and is asked to *argue about it*, not to invent it.

## 4.4 Deterministic quality score (pre-LLM filter)

Before any LLM spend, each candidate gets a **deterministic `quality_score`** from
`signal_params.yaml` weights - e.g. trend alignment (ADX over threshold), location (distance to
VWAP/structure), confirmation (volume z-score), and reward:risk. Candidates below
`min_quality_score` are discarded without analysis. This keeps token cost proportional to
opportunity and means the LLM only ever sees pre-vetted, capital-plausible setups - the same
"deterministic gate first, model second" pattern proven in `virattt/ai-hedge-fund`.

## 4.5 Setup taxonomy is fixed and enumerable

`setup_type` is drawn from a **closed list** in `signal_params.yaml` (e.g.
`breakout_with_volume`, `pullback_in_uptrend`, `range_reversion`, `momentum_continuation`).
This matters for memory: the Decision Journal keys reflections by `setup_type`, so the system
can detect "this *kind* of setup has lost the last 4 times" and the Risk Auditor can surface
**repeated failed patterns** (a named requirement). An open-ended, free-text setup label would
make that impossible.

## 4.6 What the Signal Engine must NOT do

- It must not call the LLM.
- It must not look ahead (no future bars; all features computed as-of the candidate timestamp - 
  enforced in backtest by the engine's event-driven time model).
- It must not emit a setup on stale or partial data; missing/old data → no candidate.
- It must not size positions or set risk - it *proposes* levels from structure/ATR; the Risk
  Engine owns the final, risk-clamped size.

## 4.7 Overfitting discipline (so signals survive contact with the future)

Signal parameters are not hand-tuned on the full history. They are selected under
**combinatorial purged cross-validation with embargo** (`skfolio`) and validated **walk-forward**
out-of-sample. A parameter set that only works in-sample is rejected. See
[`09_validation_and_production.md`](09_validation_and_production.md). The number of free
parameters is kept deliberately small to limit the degrees of freedom available to overfit.
