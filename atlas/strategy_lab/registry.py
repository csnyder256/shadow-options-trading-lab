"""Strategy registry - code declares strategies, YAML holds roster STATE (pure + one read).

Constants live in code (provenance-tested, cohort-hashed); config/strategy_lab.yaml holds
only the operational state machine per strategy:

    strategies:
      <strategy_id>:
        state: armed | parked | auto_disabled | pruned
        cohort_pin: <12hex>        # must equal the live config_hash (drift = finding)
        note: <why the state>

A strategy runs ONLY when (a) its factory is registered in atlas/strategy_lab/strategies/,
(b) its YAML state is `armed`, and (c) its sweep-ledger row lab-strat-<id>-v1 exists - 
the third check lives in tests/strategy_lab provenance, not here (no ledger IO here).

This module is the single source the runner, the grader, the heartbeat assertion, and
scripts/print_armed_roster.py all import - the /eodreport roster check compares heartbeats
against THIS, never against a hardcoded list.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from atlas.config_loader import FRAMEWORK_ROOT

from .strategy import Strategy

STATE_PATH = FRAMEWORK_ROOT / "config" / "strategy_lab.yaml"
VALID_STATES = ("armed", "parked", "auto_disabled", "pruned")


def load_state(path: Path | str = STATE_PATH) -> dict:
    """{strategy_id: {state, cohort_pin, note}} from YAML (utf-8-sig tolerant). Absent file ->
    {} (nothing armed - the lab runs empty rather than guessing)."""
    p = Path(path)
    if not p.exists():
        return {}
    cfg = yaml.safe_load(p.read_text(encoding="utf-8-sig")) or {}
    out = {}
    for sid, block in (cfg.get("strategies") or {}).items():
        block = block or {}
        state = str(block.get("state") or "parked")
        if state not in VALID_STATES:
            raise ValueError(f"strategy_lab.yaml: {sid}: invalid state {state!r}")
        out[str(sid)] = {"state": state,
                         "cohort_pin": str(block.get("cohort_pin") or ""),
                         "note": str(block.get("note") or "")}
    return out


def build_all() -> dict:
    """{strategy_id: Strategy instance} for every registered factory. Import is deferred so
    a broken strategy module surfaces here (once, loudly) and not at package import."""
    from .strategies import STRATEGY_FACTORIES
    out: dict[str, Strategy] = {}
    for sid, factory in STRATEGY_FACTORIES.items():
        strat = factory()
        if strat.META.strategy_id != sid:
            raise ValueError(f"registry key {sid!r} != META.strategy_id "
                             f"{strat.META.strategy_id!r}")
        out[sid] = strat
    return out


def validate(strategies: dict, state: dict) -> list:
    """Registry coherence violations (grader gate + unit test): duplicate/missing declarations,
    armed-without-factory, cohort-pin drift."""
    problems = []
    for sid, block in state.items():
        if block["state"] == "armed" and sid not in strategies:
            problems.append(f"{sid}: armed in YAML but no factory registered")
    for sid, strat in strategies.items():
        pin = state.get(sid, {}).get("cohort_pin") or ""
        if pin and pin != strat.config_hash():
            problems.append(f"{sid}: cohort_pin {pin} != live config_hash {strat.config_hash()}")
        m = strat.META
        if not (1 <= m.max_concurrent <= 20):
            problems.append(f"{sid}: max_concurrent {m.max_concurrent} outside [1,20]")
        if not (0 <= m.dte_range[0] <= m.dte_range[1]):
            problems.append(f"{sid}: bad dte_range {m.dte_range}")
    return problems


def armed_roster(strategies: dict | None = None, state: dict | None = None) -> list:
    """Sorted strategy_ids that are registered AND armed - THE roster everyone asserts on."""
    strategies = strategies if strategies is not None else build_all()
    state = state if state is not None else load_state()
    return sorted(sid for sid in strategies
                  if state.get(sid, {}).get("state") == "armed")
