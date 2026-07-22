"""Cross-strategy exposure + correlation (pure; registered lab-strategy-runtime-v1).

"20 strategies long SPY delta is ONE bet, not 20" - this module makes that a computed line:
aggregate Greeks over every open lab combo, per-underlying same-sign counts, CONCENTRATED
flags, and (once history accrues) pairwise correlation of per-strategy daily returns with
the eigenvalue-based effective_n = (sum w_i)^2 / sum w_i^2 - the honest count of independent
bets the lab actually holds. Per-strategy statistics NEVER read this block (independence of
grading); it exists for the EOD report's integrity phase.
"""

from __future__ import annotations

import math

CONC_NET_GROSS = 0.6         # |net delta$| / gross delta$ >= 0.6 -> one directional bet
CONC_TOP_UNDERLYING = 0.5    # one underlying carries >= 50% of gross delta$
CONC_SAME_SIGN_N = 8         # >= 8 strategies same-sign delta in one underlying
CORR_FLAG = 0.7
CORR_MIN_OVERLAP = 15


def combo_greeks(pos, S: float | None = None) -> dict:
    """Entry-greek aggregate for one combo (USD-ish units; entry deltas are the v1 basis)."""
    S = S if S is not None else pos.entry_S
    units = pos.contracts
    d_sh = sum(ls.spec.side * ls.spec.qty * ls.entry_delta for ls in pos.legs) * 100.0 * units
    return {"delta_dollars": d_sh * S,
            "vega": sum(ls.spec.side * ls.spec.qty * ls.entry_vega for ls in pos.legs) * 100.0 * units,
            "theta_day": sum(ls.spec.side * ls.spec.qty * ls.entry_theta_day
                             for ls in pos.legs) * 100.0 * units}


def aggregate(positions_by_strategy: dict, spots: dict | None = None) -> dict:
    """positions_by_strategy: {sid: [ComboPosition]}; spots: {underlying: S} (entry_S fallback).
    Returns the exposures block for the scorecard + exposures.jsonl."""
    net_d = gross_d = net_v = net_t = 0.0
    per_u: dict[str, dict] = {}
    for sid, poss in positions_by_strategy.items():
        for pos in poss:
            S = (spots or {}).get(pos.underlying, pos.entry_S)
            g = combo_greeks(pos, S)
            net_d += g["delta_dollars"]
            gross_d += abs(g["delta_dollars"])
            net_v += g["vega"]
            net_t += g["theta_day"]
            u = per_u.setdefault(pos.underlying,
                                 {"net_delta_dollars": 0.0, "gross_delta_dollars": 0.0,
                                  "strategies_long": set(), "strategies_short": set()})
            u["net_delta_dollars"] += g["delta_dollars"]
            u["gross_delta_dollars"] += abs(g["delta_dollars"])
            (u["strategies_long"] if g["delta_dollars"] >= 0 else u["strategies_short"]).add(sid)

    flags = []
    if gross_d > 0 and abs(net_d) / gross_d >= CONC_NET_GROSS:
        flags.append(f"CONCENTRATED: |net|/gross delta$ = {abs(net_d) / gross_d:.2f} >= {CONC_NET_GROSS}")
    for u, blk in per_u.items():
        if gross_d > 0 and blk["gross_delta_dollars"] / gross_d >= CONC_TOP_UNDERLYING and len(per_u) > 1:
            flags.append(f"CONCENTRATED: {u} carries {blk['gross_delta_dollars'] / gross_d:.0%} of gross delta$")
        for side, key in (("long", "strategies_long"), ("short", "strategies_short")):
            if len(blk[key]) >= CONC_SAME_SIGN_N:
                flags.append(f"CONCENTRATED: {len(blk[key])} strategies {side} {u} delta - one bet, not {len(blk[key])}")
    return {"net_delta_dollars": round(net_d, 0), "gross_delta_dollars": round(gross_d, 0),
            "net_vega": round(net_v, 0), "net_theta_day": round(net_t, 0),
            "per_underlying": {u: {"net_delta_dollars": round(b["net_delta_dollars"], 0),
                                   "gross_delta_dollars": round(b["gross_delta_dollars"], 0),
                                   "n_long": len(b["strategies_long"]),
                                   "n_short": len(b["strategies_short"])}
                               for u, b in sorted(per_u.items())},
            "flags": flags}


def correlation_block(daily_returns: dict) -> dict:
    """daily_returns: {sid: {day: r}}. Pairwise Pearson on >= CORR_MIN_OVERLAP overlapping
    days; clusters over CORR_FLAG; effective_n from the correlation matrix's eigenvalues."""
    sids = sorted(sid for sid, d in daily_returns.items() if len(d) >= CORR_MIN_OVERLAP)
    pairs = []
    corr: dict[tuple, float] = {}
    for i, a in enumerate(sids):
        for b in sids[i + 1:]:
            days = sorted(set(daily_returns[a]) & set(daily_returns[b]))
            if len(days) < CORR_MIN_OVERLAP:
                continue
            xa = [daily_returns[a][d] for d in days]
            xb = [daily_returns[b][d] for d in days]
            r = _pearson(xa, xb)
            if r is None:
                continue
            corr[(a, b)] = r
            if abs(r) >= CORR_FLAG:
                pairs.append({"a": a, "b": b, "rho": round(r, 3), "n_days": len(days)})
    eff = _effective_n(sids, corr)
    return {"n_series": len(sids), "flagged_pairs": sorted(pairs, key=lambda p: -abs(p["rho"])),
            "effective_n": round(eff, 2) if eff is not None else None}


def _pearson(x: list, y: list) -> float | None:
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if sx <= 0 or sy <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def _effective_n(sids: list, corr: dict) -> float | None:
    """effective_n = (sum lam)^2 / sum lam^2 over eigenvalues of the correlation matrix
    (power-iteration-free: exact via numpy when available, else the Frobenius bound
    n^2 / ||R||_F^2 which equals the same expression when eigenvalues are spread)."""
    n = len(sids)
    if n == 0:
        return None
    if n == 1:
        return 1.0
    try:
        import numpy as np
        m = np.eye(n)
        idx = {s: i for i, s in enumerate(sids)}
        for (a, b), r in corr.items():
            m[idx[a], idx[b]] = m[idx[b], idx[a]] = r
        lam = np.linalg.eigvalsh(m)
        lam = np.clip(lam, 0.0, None)
        s1, s2 = float(lam.sum()), float((lam ** 2).sum())
        return (s1 * s1 / s2) if s2 > 0 else None
    except Exception:  # noqa: BLE001 - numpy absent: Frobenius fallback
        fro2 = n + 2.0 * sum(r * r for r in corr.values())
        return (n * n) / fro2 if fro2 > 0 else None
