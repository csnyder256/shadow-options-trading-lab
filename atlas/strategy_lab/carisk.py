"""Capital-at-risk (CaR) rules - the grading denominators, FROZEN AT ENTRY (pure).

Why this exists: the main grader's e-process assumes returns bounded below by -1 ("by
construction of a long option"). Short-premium combos break that bound, so every lab trade
grades on a per-family denominator computed here, stamped into the entry record, and
re-derived by the grader as a falsification gate (denominator_mismatches must be []).

Bases (registered under lab-strategy-runtime-v1):
  debit - all-debit structures: denominator = net debit paid (USD). R floor -1 by construction.
  max_loss - defined-risk credit (verticals/condors/flies/jade lizard): denominator =
              expiry max loss from payoff_analysis. R floor -1 by construction.
  car - undefined-risk (naked short call exposure) OR multi-expiry structures whose
              expiry payoff is undefined: denominator = reg_t_v1 margin proxy. R is UNBOUNDED
              below; the grader's FOR-process uses no loss floor (annihilation is honest) and
              true-loss-beyond-CaR is logged as tail_excess.

reg_t_v1 (standard broker naked-short requirement, documented approximation - NOT a broker
quote): per naked short unit
    call: max(0.20*S - OTM_amount, 0.10*S) * 100 + premium*100
    put:  max(0.20*S - OTM_amount, 0.10*K) * 100 + premium*100
Strangle/straddle rule: the greater single-side requirement + the OTHER side's premium.
"""

from __future__ import annotations

from .model import LegSpec, payoff_analysis

BASIS_DEBIT = "debit"
BASIS_MAX_LOSS = "max_loss"
BASIS_CAR = "car"
CAR_RULE_V1 = "reg_t_v1"
MIN_DENOM_USD = 1.0     # a degenerate zero denominator never enters the ledger silently


def reg_t_short_option(S: float, strike: float, opt_type: str, premium: float,
                       qty: int = 1) -> float:
    """Reg-T-style naked short requirement in USD for `qty` short contracts."""
    S, strike = max(0.0, float(S)), max(0.0, float(strike))
    otm = max(0.0, strike - S) if opt_type == "call" else max(0.0, S - strike)
    floor = 0.10 * (S if opt_type == "call" else strike)
    req = max(0.20 * S - otm, floor) * 100.0
    return (req + max(0.0, premium) * 100.0) * qty


def _short_side_premium(legs_with_mid: list[tuple[LegSpec, float]], opt_type: str) -> float:
    return sum(mid * l.qty for l, mid in legs_with_mid if l.side < 0 and l.opt_type == opt_type)


def car_reg_t_v1(legs_with_mid: list[tuple[LegSpec, float]], S: float) -> dict:
    """CaR for a combo with naked short exposure. Uses the strangle rule when both sides carry
    naked shorts: max(call-side req, put-side req) + other side's premium. Long legs at the
    same expiry can cap a short (that's what payoff_analysis is for) - this proxy deliberately
    ignores capping and stays conservative; it is a MARGIN model, not a max-loss claim."""
    call_reqs = [reg_t_short_option(S, l.strike, "call", mid, l.qty)
                 for l, mid in legs_with_mid if l.side < 0 and l.opt_type == "call"]
    put_reqs = [reg_t_short_option(S, l.strike, "put", mid, l.qty)
                for l, mid in legs_with_mid if l.side < 0 and l.opt_type == "put"]
    call_req, put_req = sum(call_reqs), sum(put_reqs)
    if call_req and put_req:
        if call_req >= put_req:
            denom = call_req + _short_side_premium(legs_with_mid, "put") * 100.0
        else:
            denom = put_req + _short_side_premium(legs_with_mid, "call") * 100.0
    else:
        denom = call_req + put_req
    return {"denom_usd": round(max(MIN_DENOM_USD, denom), 2),
            "inputs": {"S": round(S, 4), "call_req": round(call_req, 2),
                       "put_req": round(put_req, 2)}}


def _shorts_covered_multi_expiry(specs: list[LegSpec]) -> bool:
    """True when every SHORT leg is covered by a LONG leg of the same type, same-or-later
    expiry, equal-or-better strike (call: long K <= short K; put: long K >= short K) and
    sufficient qty - the long-calendar/diagonal shape whose max loss is bounded by the debit.
    Conservative: any uncovered short -> False (CaR rules)."""
    longs = [l for l in specs if l.side > 0]
    for s in specs:
        if s.side > 0:
            continue
        need = s.qty
        for l in longs:
            if (l.opt_type == s.opt_type and l.expiry >= s.expiry
                    and ((l.strike <= s.strike) if s.opt_type == "call"
                         else (l.strike >= s.strike))):
                need -= l.qty
        if need > 0:
            return False
    return True


def grading_block(*, legs_with_mid: list[tuple[LegSpec, float]], net_open_worst: float,
                  S: float, declared_basis: str, contracts: int = 1) -> dict:
    """Compute the FROZEN grading block for an entry. `net_open_worst` = signed per-share net
    open fill on the WORST ledger (positive = debit). The basis is DERIVED from structure
    (payoff analysis), compared against the strategy's declared basis, and the DERIVED basis
    rules - a mismatch is flagged, never silently adopted (basis_mismatch feeds risk_flags).
    Multi-expiry combos (calendars/diagonals): expiry payoff is undefined, but when every
    short is covered (same type, later-or-equal expiry, equal-or-better strike) the max loss
    is bounded by the net debit -> DEBIT basis; anything else falls to the CaR proxy.
    """
    specs = [l for l, _ in legs_with_mid]
    net_debit_usd = net_open_worst * 100.0 * contracts
    pa = payoff_analysis(specs, net_debit_usd)

    if not pa["analyzable"]:
        derived = (BASIS_DEBIT if (net_debit_usd > 0 and _shorts_covered_multi_expiry(specs))
                   else BASIS_CAR)
    elif pa["unbounded_up"]:
        derived = BASIS_CAR
    elif net_debit_usd > 0:
        derived = BASIS_DEBIT
    else:
        derived = BASIS_MAX_LOSS

    if derived == BASIS_DEBIT:
        denom = max(MIN_DENOM_USD, net_debit_usd)
        car_rule, car_inputs = None, None
    elif derived == BASIS_MAX_LOSS:
        denom = max(MIN_DENOM_USD, float(pa["max_loss_usd"] or 0.0))
        car_rule, car_inputs = None, None
    else:
        car = car_reg_t_v1(legs_with_mid, S)
        denom, car_rule, car_inputs = car["denom_usd"], CAR_RULE_V1, car["inputs"]

    return {"basis": derived, "declared_basis": declared_basis,
            "basis_mismatch": bool(declared_basis and declared_basis != derived),
            "denom_usd": round(denom, 2),
            "max_loss_usd": pa["max_loss_usd"], "max_gain_usd": pa["max_gain_usd"],
            "unbounded_up": pa["unbounded_up"], "payoff_note": pa["note"],
            "net_debit_usd": round(net_debit_usd, 2),
            "car_rule": car_rule, "car_inputs": car_inputs, "contracts": int(contracts)}
