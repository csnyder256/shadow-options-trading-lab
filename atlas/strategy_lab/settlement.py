"""Expiry settlement + early-assignment heuristic (pure).

Expiry is a FIRST-CLASS lifecycle event in the lab (unlike the main shadow's
expired_unexited anomaly journal): the day-roll settles every combo whose nearest leg
expired at intrinsic against the session close, writing a real lab_exit with
rule="expiry_settlement". Settlement has no spread - the intrinsic fill is identical
across all three ledgers by construction (fills_override in build_combo_exit_record).

Early assignment (v1 approximation, flagged not modeled): an American short leg trading
at near-zero extrinsic with deep-ITM delta is at assignment risk; we have no equity book
to hold post-assignment stock, so the honest shadow approximation is a forced combo close
with rule="early_assignment_risk" - the grader counts how often this fires and what it
cost. Known limitation (recorded): no dividend calendar, so dividend-driven call
assignment is under-detected; the extrinsic test is the catch-all.
"""

from __future__ import annotations

from datetime import date

from .model import ComboPosition, intrinsic

PIN_BAND_FRAC = 0.002          # |S-K| < 0.2% of S at the close -> pin_risk flag
EA_EXTRINSIC_MAX = 0.03        # short leg extrinsic below 3 cents ...
EA_DELTA_MIN = 0.95            # ... with |delta| >= 0.95 -> assignment-risk fire


def settlement_fills(pos: ComboPosition, S_close: float) -> dict:
    """{occ: intrinsic settle price} for every leg (per share). Identical across ledgers."""
    return {ls.spec.occ: round(intrinsic(ls.spec.opt_type, ls.spec.strike, S_close), 4)
            for ls in pos.legs}


def pin_risk_flags(pos: ComboPosition, S_close: float, today: date) -> list:
    """['pin_risk:<occ>'] for legs expiring today whose strike sits inside the pin band."""
    out = []
    if S_close <= 0:
        return out
    for ls in pos.legs:
        if ls.spec.expiry <= today and abs(S_close - ls.spec.strike) < PIN_BAND_FRAC * S_close:
            out.append(f"pin_risk:{ls.spec.occ}")
    return sorted(out)


def expired_legs(pos: ComboPosition, today: date) -> list:
    """LegStates whose expiry has passed (settle at the day-roll)."""
    return [ls for ls in pos.legs if ls.spec.expiry <= today]


def early_assignment_risk(pos: ComboPosition, quotes: dict, S: float,
                          deltas: dict | None = None) -> list:
    """OCCs of SHORT legs at assignment risk. `quotes` = {occ: (bid, ask)};
    `deltas` = {occ: signed_delta} (live self-computed; falls back to entry delta)."""
    out = []
    for ls in pos.legs:
        if ls.spec.side >= 0:
            continue
        q = quotes.get(ls.spec.occ)
        if not q:
            continue
        bid, ask = max(0.0, float(q[0])), max(0.0, float(q[1]))
        if bid <= 0 and ask <= 0:
            continue
        mid = (bid + ask) / 2.0
        ext = mid - intrinsic(ls.spec.opt_type, ls.spec.strike, S)
        delta = (deltas or {}).get(ls.spec.occ, ls.entry_delta)
        if ext < EA_EXTRINSIC_MAX and abs(float(delta)) >= EA_DELTA_MIN:
            out.append(ls.spec.occ)
    return sorted(out)
