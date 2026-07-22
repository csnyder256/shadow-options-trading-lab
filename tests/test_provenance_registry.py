"""Provenance enforcement - every tunable constant maps to a registration (machine-checked).

Born 2026-07-10 (external-audit triage, finding #22): the sweep-ledger discipline was a human
process, and the config-hash near-miss (6c1dc2a4e1a7 recorded only in a note field of a
mislabeled row) proved it leaks. This test makes the standing law from the +100% incident - 
every constant is owner-verbatim, DERIVED, POLICY (a dated directive / the registered plan), or
CALIBRATION with a sweep id - enforceable:

  * adding or renaming a field in ExitParams / SelectorParams / runner DEFAULTS without a
    registry entry here FAILS;
  * a registry entry citing a sweep id that is not in sweep_ledger.jsonl FAILS;
  * the LIVE runner config hash must be pinned in the ledger as a config_hash field.

The registry is deliberately in-test (not production code): it is the reviewed, human-readable
provenance map, and updating it is the moment the discipline fires.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from atlas.options.exit_engine import ExitParams
from atlas.options.selector import SelectorParams
from scripts.run_options_shadow import DEFAULTS, config_hash, load_shadow_config

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "runtime" / "backtest_out" / "sweep_ledger.jsonl"

# provenance strings: must name a class (owner-verbatim | derived | policy | calibration)
# and, for calibrations/tweaks, the sweep id(s). Ids are existence-checked below.
EXIT_PARAMS_PROVENANCE = {
    "zero_dte_sell_min": "policy clock (registered plan; rule 3 mapping) - opts-rework-exit-core-v1",
    "zero_dte_deep_itm_ext_min": "policy clock (registered plan) - opts-rework-exit-core-v1",
    "zero_dte_deep_itm_delta": "policy clock (registered plan) - opts-rework-exit-core-v1",
    "print_flat_lead_min": "calibration (plan-era) - opts-calib-plan-era-constants-v1",
    "stop_frac": "directive owner 2026-07-10 (inert None) - opts-tweak-disable-premium-stop-v1",
    "post_print_decision_min": "calibration (plan-era) - opts-calib-plan-era-constants-v1",
    "theta_share_max": "derived-by-definition (rule 24 'dominant' = majority share)",
    "theta_share_cycles": "calibration - opts-calib-theta-cycles-v1",
    "p_target_floor": "calibration - opts-calib-p-target-floor-v1",
    "p_regain_min": "calibration - opts-calib-p-regain-min-v1",
    "eod_flat_min": "policy (owner fork answer 2026-07-09, overnight evidence rule)",
    "planned_exit_cap_min": "directive - opts-tweak-planned-exit-v1",
    "session_close_min": "policy - opts-tweak-late-close-mode-v1 (per-day via for_close)",
    "late_close_flat_min": "directive - opts-tweak-late-close-mode-v1",
    "overnight_min_dte": "policy (owner fork answer 2026-07-09)",
    "overnight_min_delta": "policy (owner fork answer 2026-07-09)",
    "r": "calibration (plan-era rate assumption) - opts-calib-plan-era-constants-v2",
    "q": "calibration (plan-era zero-dividend approximation) - opts-calib-plan-era-constants-v2",
    "n_grid": "calibration (plan-era quadrature width) - opts-calib-plan-era-constants-v2",
    "ev_persist_min": "calibration (one non-overlapping mu window; cadence-invariant statistical "
                      "exits, audit 2026-07-16 Wave 2.14) - opts-audit-wave2-exitv3-v1",
}

SELECTOR_PARAMS_PROVENANCE = {
    "delta_gate": "calibration (plan-era; the owner's stated skew context) - opts-calib-plan-era-constants-v2",
    "delta_preferred": "policy (owner's stated 0.55-0.75 skew band); +5 bonus registered - opts-calib-plan-era-constants-v1",
    "delta_ban_below": "calibration (plan-era lotto ban) - opts-calib-plan-era-constants-v2",
    "spread_clean_pct": "calibration (plan-era) - opts-calib-plan-era-constants-v2",
    "spread_max_pct": "calibration (plan-era) - opts-calib-plan-era-constants-v2",
    "spread_abs_max_nonindex": "calibration (plan-era) - opts-calib-plan-era-constants-v2",
    "spread_abs_pct_of_mid": "calibration (premium-tiered non-index abs cap; audit "
                             "FUNNEL-THROUGHPUT-4) - opts-audit-wave1-funnel-v1",
    "oi_min": "calibration (plan-era) - opts-calib-plan-era-constants-v2",
    "oi_min_index": "calibration (plan-era) - opts-calib-plan-era-constants-v2",
    "volume_min": "calibration (plan-era; now time-scaled by elapsed session fraction - audit "
                  "SELECTOR-6) - opts-audit-wave1-funnel-v1",
    "volume_alt_index_dte1": "calibration (index DTE<=1 OI-or-live-volume gate; audit SELECTOR-6, "
                             "measured live: fresh ATM strike OI=0/vol 6255) - opts-audit-wave1-funnel-v1",
    "premium_min_mid": "calibration (microstructure research: sub-$0.50 premiums pay 3-6% "
                       "min-tick toll) - opts-audit-wave1-funnel-v1",
    "p_touch_min": "calibration (coherence gate; audit PROBABILITY-MEASURE-1/SELECTOR-3, "
                   "2/2 upheld) - opts-audit-wave1-funnel-v1",
    "premium_max_usd": "directive owner 2026-07-10 (None = cap removed) - opts-tweak-remove-premium-cap-v1",
    "lambda_band": "calibration (plan-era; floor + DTE>=2 cap) - opts-calib-plan-era-constants-v2",
    "lambda_cap_dte0": "calibration (lambda ~ 1/(sigma*sqrt(T)); flat 90 was a de-facto 0DTE "
                       "index ban, measured ATM lambda 107-271) - opts-audit-wave1-funnel-v1",
    "lambda_cap_dte1": "calibration (same basis) - opts-audit-wave1-funnel-v1",
    "lambda_floor_deep": "calibration (deep-delta stock-replacement contracts compute lambda "
                         "~10-12) - opts-audit-wave1-funnel-v1",
    "deep_delta": "calibration (deep-delta threshold for the reduced floor) - opts-audit-wave1-funnel-v1",
    "max_dte": "calibration (plan-era scan bound) - opts-calib-plan-era-constants-v2",
    "no_0dte_after_min": "policy (plan: no 0DTE entries in the last 2h) - opts-calib-plan-era-constants-v2",
    "session_close_min": "policy - opts-tweak-late-close-mode-v1 (per-day via for_close)",
    "overnight_min_dte": "calibration (plan-era) - opts-calib-plan-era-constants-v2",
    "hold_max_frac_of_life": "calibration (plan-era) - opts-calib-plan-era-constants-v2",
    "zero_dte_third_of_life_exempt": "directive owner 2026-07-09 night - opts-tweak-0dte-carveout-v1",
    "ev_pct_min": "calibration (expected NET return floor on the ask) - opts-calib-plan-era-constants-v2",
    "ev_vs_spread_mult": "calibration - opts-calib-plan-era-constants-v2",
    "p_profit_min": "calibration - opts-calib-plan-era-constants-v2",
    "r": "calibration (plan-era) - opts-calib-plan-era-constants-v2",
    "q": "calibration (plan-era) - opts-calib-plan-era-constants-v2",
    "n_grid": "calibration (plan-era) - opts-calib-plan-era-constants-v2",
}

DEFAULTS_PROVENANCE = {
    "watch": "runner config - opts-runner-defaults",
    "poll_seconds": "runner config - opts-runner-defaults",
    "max_concurrent": "runner config - opts-runner-defaults",
    "top_n": "runner config - opts-runner-defaults",
    "p_thesis": "runner config - opts-runner-defaults",
    "range_percentile_min": "runner config - opts-runner-defaults",
    "lane2_max_candidates": "runner config - opts-runner-defaults",
    "lane2_gap_min_pct": "runner config - opts-runner-defaults",
    "lane2_rvol_min": "runner config - opts-runner-defaults",
    "lane2_price_min": "runner config - opts-runner-defaults",
    "lane2_scan_symbols": "runner config - opts-runner-defaults",
    "max_chain_expirations": "runner config 3->6 (audit FUNNEL-THROUGHPUT-2: 3 truncated "
                             "daily-expiry indexes to DTE 0-2; hash cohort "
                             "opts-audit-cohort-hashpin-v1) - opts-audit-wave1-funnel-v1",
    "p_thesis_by_lane": "runner config (per-lane prior plumbing; values await the offline "
                        "calibration study) - opts-audit-wave3-priors-v1",
    "tradier_self_cap_per_min": "runner config - opts-runner-defaults",
    "noise_lookback_days": "runner config - opts-runner-defaults",
    "r": "runner config - opts-runner-defaults",
    "reval_shock_mult": "calibration - opts-tweak-reval-triggers-v1 (hash cohort opts-runner-defaults-v2)",
    "reval_shock_floor": "calibration - opts-tweak-reval-triggers-v1 (hash cohort opts-runner-defaults-v2)",
    "mu_window_min": "calibration - opts-calib-mu-window-v1 (hash cohort opts-runner-defaults-v3-hashpin)",
}


def _ledger_text() -> str:
    """Read the operator's sweep ledger, skipping the test when it is absent.

    The ledger lives under runtime/, which is machine-local operational state and is
    not part of the source tree. Tests that cross-check the registry against it are
    canaries for a running deployment, so on a fresh clone they skip rather than fail.
    """
    if not LEDGER.exists():
        pytest.skip(f"no sweep ledger at {LEDGER.relative_to(REPO)} (runtime state is machine-local)")
    return LEDGER.read_text(encoding="utf-8")


def _assert_registry_matches(registry: dict, names: set, what: str) -> None:
    missing = names - registry.keys()
    stale = registry.keys() - names
    assert not missing, (
        f"{what}: UNREGISTERED constant(s) {sorted(missing)} - the standing law (every constant "
        f"owner-verbatim / derived / policy / registered calibration) requires a sweep-ledger row "
        f"AND a registry entry here BEFORE first fire")
    assert not stale, f"{what}: registry names no longer in the code: {sorted(stale)}"


def test_exit_params_all_registered():
    _assert_registry_matches(EXIT_PARAMS_PROVENANCE,
                             {f.name for f in dataclasses.fields(ExitParams)}, "ExitParams")


def test_selector_params_all_registered():
    _assert_registry_matches(SELECTOR_PARAMS_PROVENANCE,
                             {f.name for f in dataclasses.fields(SelectorParams)}, "SelectorParams")


def test_runner_defaults_all_registered():
    _assert_registry_matches(DEFAULTS_PROVENANCE, set(DEFAULTS.keys()), "runner DEFAULTS")


def test_every_cited_sweep_id_exists_in_ledger():
    txt = _ledger_text()
    cited = set()
    for reg in (EXIT_PARAMS_PROVENANCE, SELECTOR_PARAMS_PROVENANCE, DEFAULTS_PROVENANCE):
        for v in reg.values():
            cited.update(re.findall(r"opts-[a-z0-9-]+", v))
    missing = sorted(i for i in cited if f'"config_id": "{i}"' not in txt)
    assert not missing, f"registry cites sweep id(s) with no ledger row: {missing}"


def test_live_config_hash_pinned_as_field():
    """The effective runner config's hash must be a machine-greppable config_hash FIELD in the
    ledger (the 2026-07-10 near-miss: 6c1dc2a4e1a7 lived only in a note string)."""
    h = config_hash(load_shadow_config())
    assert f'"config_hash": "{h}"' in _ledger_text(), (
        f"live config hash {h} has no ledger row with a config_hash field - a config change "
        f"started a new entry cohort without registration")
