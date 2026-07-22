"""Per-strategy grading math: return bases, FOR/AGAINST e-processes, mechanism attribution
(pure; registered lab-strategy-runtime-v1).

VALIDITY (the module's load-bearing argument, mirrored from scripts/grade_options_shadow.py
and extended to unbounded-loss families):

FOR-process (is the strategy making money?), H0: E[R] <= 0.
    W = mean over lambda of prod_i max(1e-12, 1 + lambda * r_i')
    bounded bases (debit/max_loss, R >= -1 by construction):
        r' = min(max(r, -1), R_CAP)          -- byte-parity with the main grader
    CaR basis (unbounded below):
        r' = min(r, R_CAP)                   -- cap WINS only. Capping wins is mean-REDUCING
        under H0 so W stays a supermartingale; an uncapped monster loss annihilates W to
        ~1e-12, which is the honest outcome of betting FOR a strategy that lost multiples of
        its capital-at-risk. NEVER floor losses here: flooring losses is mean-RAISING under
        H0 and destroys anytime-validity (the r->max(r,-4) clip considered in planning was
        rejected for exactly this reason).

AGAINST-process (powers the prune bar), H0': E[R] >= 0.
    W_against = mean over lambda of prod_i max(1e-12, 1 - lambda * max(r, -1))
    Flooring LOSSES at -1 is conservative for the against-bettor (mirror image of capping
    wins). A monster win annihilates the prune case. Both processes are supermartingales
    under their nulls, so Ville's inequality makes nightly re-grades anytime-valid.

Multiplicity: ~21 strategies watched at once -> at the PILOT bar (W>=5, alpha=20%) expect
~1 false flag per 5 null strategies. PILOT is a discussion trigger; arming is a per-strategy
registration. The scorecard prints this note.
"""

from __future__ import annotations

from .carisk import BASIS_CAR

R_CAP = 2.0                              # +200% of denominator per bet (anti-fluke; main parity)
LAMBDAS_BOUNDED = (0.05, 0.10, 0.20)     # byte-parity with grade_options_shadow.EPROCESS_LAMBDAS
LAMBDAS_CAR = (0.02, 0.05, 0.10)         # smaller bets: FOR-annihilation at -50x..-10x CaR
WEALTH_PILOT = 5.0
WEALTH_LIVE = 20.0
AGAINST_FLAG = 5.0                       # LOSING evidence bar (n >= N_VERDICT_MIN)
AGAINST_PRUNE = 20.0                     # statistical half of the prune bar
N_VERDICT_MIN = 25
N_INTERIM = 10
TAIL_R = -1.0                            # a CaR trade losing > 100% of CaR is a tail event
ATTRIB_COVERAGE_MIN = 0.6                # below this, mechanism claims are forbidden


def lambdas_for(basis: str) -> tuple:
    return LAMBDAS_CAR if basis == BASIS_CAR else LAMBDAS_BOUNDED


def r_return(exit_rec: dict) -> float | None:
    """Per-trade return on the WORST ledger against the FROZEN denominator. None on unusable
    rows (missing/invalid denom or pnl) - callers list skips loudly, never silently."""
    try:
        led = (exit_rec.get("ledgers") or {}).get("worst") or {}
        denom = float((exit_rec.get("grading") or {}).get("denom_usd") or 0.0)
        if denom <= 0:
            return None
        return float(led["net_pnl_usd"]) / denom
    except (KeyError, TypeError, ValueError):
        return None


def wealth_for(rs: list, basis: str, lambdas: tuple | None = None) -> dict:
    """FOR-process wealth. Returns {wealth, n, floor_breaches:[idx], mean_r}."""
    lams = lambdas or lambdas_for(basis)
    car = basis == BASIS_CAR
    breaches = []
    wealth = []
    for lam in lams:
        w = 1.0
        for i, r in enumerate(rs):
            rp = min(r, R_CAP) if car else min(max(r, -1.0), R_CAP)
            w *= max(1e-12, 1.0 + lam * rp)
        wealth.append(w)
    if car:
        lam_max = max(lams)
        breaches = [i for i, r in enumerate(rs) if r < -1.0 / lam_max]
    return {"wealth": sum(wealth) / len(wealth) if wealth else 1.0, "n": len(rs),
            "floor_breaches": breaches,
            "mean_r": (sum(rs) / len(rs)) if rs else None}


def wealth_against(rs: list, basis: str, lambdas: tuple | None = None) -> float:
    """Mirror bet AGAINST the strategy (loss floor -1 is conservative for the against-bettor)."""
    lams = lambdas or lambdas_for(basis)
    wealth = []
    for lam in lams:
        w = 1.0
        for r in rs:
            w *= max(1e-12, 1.0 - lam * max(r, -1.0))
        wealth.append(w)
    return sum(wealth) / len(wealth) if wealth else 1.0


# --------------------------------------------------------------------- attribution
def attribute(exit_rec: dict, entry_rec: dict) -> dict | None:
    """Decompose one exit's GROSS (mid-to-mid) P&L into computed components:

        direction_usd = net delta shares * (S_exit - S_entry)
        vol_usd       = sum(side*qty*vega * dIV_leg) * 100    (0 when exit leg IVs absent)
        theta_usd     = net theta_day * hold_trading_days * 100
        residual_usd  = gross - direction - vol - theta       (gamma/higher-order/unmodeled)
        spread_tax_usd (side info, WORST crossing cost, from the exit decomposition)

    coverage = 1 - |residual| / max(|gross|, $25) - mechanism claims require >= 0.6.
    Returns None when the pair is malformed."""
    try:
        legs_e = {l["occ"]: l for l in entry_rec["legs"]}
        S0, S1 = float(entry_rec["S"]), float(exit_rec["S"])
        gross = float(exit_rec["ledgers"]["worst"]["gross_pnl_usd"])
        units = float(entry_rec.get("contracts") or 1)
        hold = float(exit_rec.get("hold_trading_days") or 0.0)
        delta_sh = sum(l["side"] * l["qty"] * float(l.get("delta") or 0.0)
                       for l in legs_e.values()) * 100.0 * units
        direction = delta_sh * (S1 - S0)
        vol = 0.0
        for lc in exit_rec.get("legs_close") or []:
            le = legs_e.get(lc.get("occ"))
            iv1 = float(lc.get("iv") or 0.0)
            if le is None or iv1 <= 0 or float(le.get("iv") or 0.0) <= 0:
                continue
            vol += (le["side"] * le["qty"] * float(le.get("vega") or 0.0)
                    * (iv1 - float(le["iv"]))) * 100.0 * units
        theta_net = sum(l["side"] * l["qty"] * float(l.get("theta_day") or 0.0)
                        for l in legs_e.values()) * 100.0 * units
        theta = theta_net * max(0.0, hold)
        residual = gross - direction - vol - theta
        r = r_return(exit_rec)
        tail = bool(r is not None and r < TAIL_R)
        coverage = 1.0 - abs(residual) / max(abs(gross), 25.0)
        return {"gross_usd": round(gross, 2), "direction_usd": round(direction, 2),
                "vol_usd": round(vol, 2), "theta_usd": round(theta, 2),
                "residual_usd": round(residual, 2),
                "spread_tax_usd": round(float((exit_rec.get("decomposition") or {})
                                              .get("spread_paid_usd") or 0.0), 2),
                "tail_flag": tail, "coverage": round(max(0.0, coverage), 3)}
    except (KeyError, TypeError, ValueError):
        return None


def loss_shares(attribs: list, nets: list) -> dict:
    """Aggregate attribution over LOSING trades -> component shares of total loss magnitude +
    the argmax loss_driver (+ mirrored win_driver). Directional components contribute to a
    side's share only when they pushed that way (a positive theta on a losing trade is not a
    loss driver)."""
    comp_keys = ("direction", "vol", "theta", "spread_tax", "residual")
    losses = {k: 0.0 for k in comp_keys}
    wins = {k: 0.0 for k in comp_keys}
    n_loss = n_win = 0
    cov_sum = 0.0
    tails = 0
    for a, net in zip(attribs, nets):
        if a is None:
            continue
        cov_sum += a["coverage"]
        tails += 1 if a["tail_flag"] else 0
        bucket = losses if net < 0 else wins
        if net < 0:
            n_loss += 1
        else:
            n_win += 1
        for k in comp_keys:
            v = a.get(f"{k}_usd", 0.0)
            # spread tax is always a cost -> always a loss-side contributor
            if k == "spread_tax":
                losses[k] += abs(v)
                continue
            if net < 0 and v < 0:
                bucket[k] += -v
            elif net >= 0 and v > 0:
                bucket[k] += v
    def _norm(d):
        tot = sum(d.values())
        return ({k: round(v / tot, 3) for k, v in d.items()} if tot > 0
                else {k: 0.0 for k in d})
    n_all = max(1, n_loss + n_win)
    return {"loss_shares": _norm(losses), "win_shares": _norm(wins),
            "loss_driver": (max(losses, key=losses.get) if sum(losses.values()) > 0 else None),
            "win_driver": (max(wins, key=wins.get) if sum(wins.values()) > 0 else None),
            "coverage": round(cov_sum / n_all, 3), "tail_count": tails,
            "n_loss": n_loss, "n_win": n_win}
