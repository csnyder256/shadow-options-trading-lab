"""Verdict machine + prune bar (pure; registered lab-strategy-runtime-v1).

Deterministic ordering, first match wins:
  BROKEN    any falsification gate non-empty -> grading suspended for THIS strategy only;
            the fix is the day's work item.
  WINNING   wealth_for >= 5 at n >= 25 (current cohort)   -> PILOT-ELIGIBLE
            wealth_for >= 20                              -> SIZED-LIVE-DISCUSSION
  LOSING    wealth_against >= 5 at n >= 25, OR mean net < 0 at n >= 25 (gross-negative rule)
  UNPROVEN  everything else (n >= 10 allows a labeled non-binding interim read)

The mandatory computed "why": every WINNING/LOSING verdict carries the attribution line
(loss/win driver + shares + coverage) and the funnel line. Coverage < 0.6 FORBIDS a
mechanism claim - the why becomes UNRELIABLE-ATTRIBUTION and the action INVESTIGATE.

Prune bar (DEFINITE LOSER = "no small tweak can save it") = (a) AND (b):
  (a) statistical: wealth_against >= 20 at n >= 25 in the current cohort
      (a-lite: wealth_against >= 5 AND mean net < 0 at n >= 25 -> PRUNE-CANDIDATE early).
      Anti-fork-immortality: >= 3 cohort forks each reaching wealth_against >= 5 counts as (a).
  (b) mechanistic: loss_driver maps onto the registry's defining_mechanism (declared at
      birth) AND the registered tweak-sweep found NO surviving grid cell (mean R > 0 and
      PF >= 1.0). The sweep can only KILL, never validate.
PRUNE-CANDIDATE is flagged to the owner (who confirms); AUTO-DISABLED needs no confirmation:
      any FOR-floor breach (single CaR trade r < -1/lambda_max), falsification gates broken
      2 consecutive sessions, or a single-day loss > KILL_DAY_LOSS_X * denom median.
"""

from __future__ import annotations

from .grading import (AGAINST_FLAG, AGAINST_PRUNE, ATTRIB_COVERAGE_MIN, N_INTERIM,
                      N_VERDICT_MIN, WEALTH_LIVE, WEALTH_PILOT)

KILL_DAY_LOSS_X = 3.0            # one-day strategy loss beyond 3x its median denom -> disable
GATE_BREAK_SESSIONS = 2
FORK_IMMORTALITY_N = 3

# Which attribution components count as expressions of which defining mechanisms.
# A LOSING strategy is prune-track only when its loss_driver is one of its mechanism's own
# components - spread_tax and residual are never mechanism components (they route to
# TWEAK-QUEUE / INVESTIGATE instead).
MECHANISM_COMPONENTS = {
    "short_vol_carry": ("vol", "direction"),
    "long_vol_convexity": ("vol", "theta"),
    "directional_momentum": ("direction",),
    "directional_mean_reversion": ("direction",),
    "event_premium": ("vol", "direction"),
    "time_decay_capture": ("theta", "vol"),
    "term_structure": ("vol", "theta"),
    "overnight_premium": ("vol", "direction"),
    "pinning": ("direction",),
    "drift_capture": ("direction", "theta"),
}


def verdict_for(*, gates_clean: bool, n: int, wealth_for: float, wealth_against: float,
                mean_net_usd: float | None, attribution: dict | None,
                funnel_health: str) -> dict:
    """The per-strategy verdict block. Pure - everything observable is an argument."""
    why: list[str] = []
    if not gates_clean:
        return {"verdict": "BROKEN", "action": "FIX-GATES",
                "why": ["falsification gate(s) non-empty - grading suspended for this strategy"]}

    attr_ok = bool(attribution and attribution.get("coverage", 0.0) >= ATTRIB_COVERAGE_MIN)
    attr_line = None
    if attribution:
        attr_line = (f"losses: driver={attribution.get('loss_driver')} "
                     f"shares={attribution.get('loss_shares')} "
                     f"coverage={attribution.get('coverage')}")

    if n >= N_VERDICT_MIN and wealth_for >= WEALTH_PILOT:
        action = "SIZED-LIVE-DISCUSSION" if wealth_for >= WEALTH_LIVE else "PILOT-ELIGIBLE"
        why.append(f"wealth_for={wealth_for:.2f} at n={n}")
        why.append((f"wins: driver={attribution.get('win_driver')}" if attr_ok else
                    f"UNRELIABLE-ATTRIBUTION (coverage {attribution.get('coverage') if attribution else 'n/a'}) - instrument before concluding"))
        return {"verdict": "WINNING", "action": action, "why": why}

    losing_stat = n >= N_VERDICT_MIN and wealth_against >= AGAINST_FLAG
    losing_gross = n >= N_VERDICT_MIN and mean_net_usd is not None and mean_net_usd < 0
    if losing_stat or losing_gross:
        why.append(f"wealth_against={wealth_against:.2f}, mean_net=${mean_net_usd:.2f} at n={n}"
                   if mean_net_usd is not None else f"wealth_against={wealth_against:.2f} at n={n}")
        if not attr_ok:
            why.append(f"UNRELIABLE-ATTRIBUTION (coverage "
                       f"{attribution.get('coverage') if attribution else 'n/a'}) - instrument before concluding")
            return {"verdict": "LOSING", "action": "INVESTIGATE", "why": why}
        why.append(attr_line)
        driver = attribution.get("loss_driver")
        if driver in ("spread_tax", "residual"):
            return {"verdict": "LOSING", "action": "TWEAK-QUEUE", "why": why
                    + [f"loss driver {driver} is tunable (structure/filters), not the thesis"]}
        return {"verdict": "LOSING", "action": "PRUNE-TRACK", "why": why}

    why.append(f"n={n} - no verdict below n={N_VERDICT_MIN}")
    if n >= N_INTERIM:
        why.append(f"interim (non-binding): wealth_for={wealth_for:.2f}, "
                   f"wealth_against={wealth_against:.2f}")
    if funnel_health in ("STARVED", "DEAD"):
        why.append(f"funnel {funnel_health} - a strategy that never fires is a defect")
        return {"verdict": "UNPROVEN", "action": "INVESTIGATE-FUNNEL", "why": why}
    if funnel_health == "WARMUP":
        why.append("funnel WARMUP - <1 expected fire over elapsed lab sessions; "
                   "not yet assessable (no defect)")
    return {"verdict": "UNPROVEN", "action": "NONE", "why": why}


def prune_assessment(*, wealth_against: float, n: int, mean_net_usd: float | None,
                     loss_driver: str | None, coverage: float, defining_mechanism: str,
                     sweep_survivors: int | None, cohort_forks_against: int = 0) -> dict:
    """The two-part prune bar. sweep_survivors: grid cells with mean R > 0 and PF >= 1.0 from
    the registered tweak-sweep (None = sweep not run yet)."""
    stat_full = n >= N_VERDICT_MIN and wealth_against >= AGAINST_PRUNE
    stat_forks = cohort_forks_against >= FORK_IMMORTALITY_N
    stat_lite = (n >= N_VERDICT_MIN and wealth_against >= AGAINST_FLAG
                 and mean_net_usd is not None and mean_net_usd < 0)
    mech_driver = (coverage >= ATTRIB_COVERAGE_MIN and loss_driver is not None
                   and loss_driver in MECHANISM_COMPONENTS.get(defining_mechanism, ()))
    mech_sweep = sweep_survivors == 0
    met_a = stat_full or stat_forks
    met_b = mech_driver and mech_sweep
    if met_a and met_b:
        state = "PRUNE-CANDIDATE"
    elif (met_a or stat_lite) and (mech_driver or mech_sweep is True):
        state = "PRUNE-EVIDENCE-PARTIAL"
    elif stat_lite:
        state = "EARLY-FLAG"
    else:
        state = "NOT-MET"
    return {"state": state, "stat_full": stat_full, "stat_lite": stat_lite,
            "stat_forks": stat_forks, "mech_driver_match": mech_driver,
            "sweep_survivors": sweep_survivors,
            "note": "the owner confirms every PRUNE-CANDIDATE; ledgers archive, never delete"}


def auto_disable_check(*, floor_breaches: int, gate_broken_today: bool,
                       gate_broken_streak: int, day_net_usd: float,
                       median_denom_usd: float) -> dict:
    """Immediate no-confirmation disable triggers (demotion is free)."""
    reasons = []
    if floor_breaches > 0:
        reasons.append(f"FOR-floor breach x{floor_breaches} (single trade beyond -1/lambda_max CaR)")
    streak = gate_broken_streak + 1 if gate_broken_today else 0
    if streak >= GATE_BREAK_SESSIONS:
        reasons.append(f"falsification gates broken {streak} consecutive sessions")
    if median_denom_usd > 0 and day_net_usd < -KILL_DAY_LOSS_X * median_denom_usd:
        reasons.append(f"day loss ${day_net_usd:.0f} beyond {KILL_DAY_LOSS_X}x median denom")
    return {"disable": bool(reasons), "reasons": reasons, "gate_broken_streak": streak}
