"""LIVE UNDERLYING-TRAJECTORY REASSESSMENT (opts-rework-exit-core-v1, 2026-07-10).

owner rule 1 ("Underlying stock's current estimated trajectory") + rule 11 ("Base exit decisions
on updated probabilities using the latest available information"): the exit engine must not run
on a drift frozen at entry time. This module estimates the CURRENT drift from the trailing
minutes of committed 1-min closes, with an evidence strength that lets the engine blend it
against the entry thesis WITHOUT any cliff threshold (rules 20/21 - confidence continuously
shrinks or grants room).

The estimator, per mark:

    T_K    = span_minutes / (390 * 252)          window length in trading years
    r_K    = ln(close_now / close_back)          window log return
    mu_hat = r_K / T_K                           raw annualized drift
    s_K    = iv * sqrt(T_K)                      1-sigma window move under the option's OWN
                                                 solved IV (internally consistent with the
                                                 pricing model - no invented vol constant)
    t_stat = r_K / s_K                           evidence strength in sigmas

The blend (applied in exit_engine.decide_exit, logged in every mark's state):

    w      = t_stat^2 / (1 + t_stat^2)           evidence-gated shrinkage weight - 
                                                 CALIBRATION-class HEURISTIC (registered:
                                                 opts-rework-exit-core-v1 names the formula;
                                                 weight family replay-swept under
                                                 opts-calib-mu-blend-weight-v1)
    mu_eff = w * mu_hat + (1 - w) * mu_prior     mu_prior = mu_thesis while thesis holds,
                                                 else 0 (no view)

LABEL CORRECTION (2026-07-10 external-audit triage): this weight was previously mislabeled
"DERIVED - inverse-variance with prior variance = observation variance". That derivation in
fact yields a CONSTANT w = 1/2 for every t; producing w = t^2/(1+t^2) from inverse-variance
weighting would require a data-dependent prior variance equal to mu_hat^2 - circular, not a
prior. The formula is a reasonable monotone evidence gate - no evidence (t≈0) → the lane
thesis governs; 1σ of observed drift → 50/50; 2σ → 80% live - but it is a calibration
choice, not a theorem. Alternatives (w = t^2/(c+t^2) for c in {0.5, 2}; a window-length
conjugate weight) are paired-replay columns only; the live formula changes only on
N-evidence. `mu_window_min` (default 20) is a CALIBRATION parameter (sweep_ledger
opts-calib-mu-window-v1, replay-swept 10/20/30) - an author-proposed value, NOT a owner number.

Pure: sequences in, dataclass out. No IO, no clock reads. Causal by construction - callers
feed only COMMITTED bars (LiveBarBuilder never exposes the forming minute).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

TRADING_MINUTES_PER_YEAR = 390.0 * 252.0


@dataclass(frozen=True)
class UnderlyingState:
    """Live trajectory evidence as of one committed bar (all fields logged per mark)."""
    mu_hat: float | None          # raw annualized drift over the window; None = no view
    t_stat: float                 # r_K / (iv * sqrt(T_K)); 0.0 when mu_hat is None
    er: float                     # efficiency ratio over the window (diagnostic, logged)
    window_min: int               # requested window
    n_bars: int                   # bars actually available/used
    # Structure overlay (state-only in v1 - sweep_ledger opts-calib-defense-params-v1 /
    # opts-variant-defense-exit-v1; populated once atlas/options/structure.py lands):
    opposing_defense: bool = False
    defense_zone_score: float = 0.0


def mu_blend(mu_hat: float | None, t_stat: float, mu_prior: float) -> float:
    """Evidence-gated shrinkage blend (module docstring - CALIBRATION-class heuristic, not a
    derivation; label corrected 2026-07-10). Pure + total: mu_hat None -> the prior governs
    untouched.

    SUPERSEDED for live decisions by mu_blend_shrink (audit 2026-07-16 TRAJECTORY-1, Wave 2.15):
    at t=1sigma this weight put 50% on a drift estimate whose sampling SE is ~14 annualized units
 - the "noise clock" that force-sold winners within ~30-50 min under pure noise (4/4 refuters
    upheld the Monte Carlo through the real decide_exit). Kept verbatim for replay of pre-fix
    stored paths."""
    if mu_hat is None:
        return float(mu_prior)
    w = (t_stat * t_stat) / (1.0 + t_stat * t_stat)
    return w * float(mu_hat) + (1.0 - w) * float(mu_prior)


def mu_blend_shrink(mu_hat: float | None, t_stat: float, mu_prior: float, tau: float) -> float:
    """VARIANCE-SCALED shrinkage (audit 2026-07-16 §6 Wave 2.15 - the normal-normal posterior
    mean): w = tau^2 / (tau^2 + SE^2), where SE is the sampling SE of mu_hat and tau the prior
    scale of plausible true drifts. SE is recovered exactly from the estimator's own outputs:
    t = r/(iv*sqrt(T)) and mu_hat = r/T give SE = iv/sqrt(T) = |mu_hat / t| - no new plumbing.

    tau is supplied by the caller (the engine passes the |thesis drift| scale - CALIBRATION,
    registered in the audit changeset; see exit_engine.decide_exit). With iv~0.20 over a 20-min
    window SE~14/yr, so any plausible tau (<~10/yr) keeps w small - the estimator only moves the
    decision when its evidence actually resolves drift at the thesis scale, which is the audit's
    prescribed cure for the noise clock. Pure + total: mu_hat None or zero-evidence -> prior."""
    if mu_hat is None:
        return float(mu_prior)
    if abs(t_stat) <= 1e-12 or tau <= 0.0:
        return float(mu_prior)
    se = abs(float(mu_hat) / float(t_stat))
    if se <= 0.0 or not math.isfinite(se):
        return float(mu_prior)
    w = (tau * tau) / (tau * tau + se * se)
    return w * float(mu_hat) + (1.0 - w) * float(mu_prior)


def underlying_state(mins: Sequence[int], closes: Sequence[float], *,
                     iv: float, window_min: int = 20) -> UnderlyingState:
    """Estimate the current trajectory from trailing committed 1-min closes.

    `mins` are minute-of-day keys aligned with `closes` (ascending; gaps allowed - the
    ACTUAL span in minutes is what enters T_K). `iv` is the position's solved IV (annual).
    Fails toward NO VIEW (mu_hat=None, t=0) when: fewer than max(3, window_min//2) bars in
    the window, a non-positive close, a degenerate IV (<= 1e-3, the runner's stale-IV
    sentinel guard), or a zero span."""
    k = int(window_min)
    no_view = UnderlyingState(mu_hat=None, t_stat=0.0, er=0.0,
                              window_min=k, n_bars=0)
    if not mins or not closes or len(mins) != len(closes) or k <= 0:
        return no_view

    # trailing window: bars whose minute is within [last_minute - k, last_minute]
    last_min = int(mins[-1])
    lo = last_min - k
    idx0 = 0
    for i in range(len(mins) - 1, -1, -1):
        if int(mins[i]) < lo:
            idx0 = i + 1
            break
    w_mins = [int(m) for m in mins[idx0:]]
    w_closes = [float(c) for c in closes[idx0:]]
    n = len(w_closes)
    if n < max(3, k // 2):
        return no_view
    # ROBUST ENDPOINTS (audit 2026-07-16 Wave 2.15, shipped with the variance-scaled blend):
    # a two-point r_K let a single anomalous print at either end own the whole drift estimate;
    # median-of-3 endpoint closes bound any one print's influence without changing the window.
    # er (the efficiency-ratio DIAGNOSTIC) keeps the raw endpoints - path efficiency describes
    # the whole window, and robustifying it would understate perfect trends by construction.
    c0 = sorted(w_closes[:3])[1]
    c1 = sorted(w_closes[-3:])[1]
    c0_raw, c1_raw = w_closes[0], w_closes[-1]
    span = w_mins[-1] - w_mins[0]
    if c0 <= 0.0 or c1 <= 0.0 or span <= 0 or not (iv and iv > 1e-3):
        return UnderlyingState(mu_hat=None, t_stat=0.0, er=0.0,
                               window_min=k, n_bars=n)

    t_years = span / TRADING_MINUTES_PER_YEAR
    r = math.log(c1 / c0)
    mu_hat = r / t_years
    s = float(iv) * math.sqrt(t_years)
    t_stat = r / s if s > 0 else 0.0

    path = sum(abs(w_closes[i] - w_closes[i - 1]) for i in range(1, n))
    er_num = abs(c1_raw - c0_raw) if (c0_raw > 0 and c1_raw > 0) else abs(c1 - c0)
    er = er_num / path if path > 0 else 0.0

    return UnderlyingState(mu_hat=mu_hat, t_stat=t_stat, er=er,
                           window_min=k, n_bars=n)
