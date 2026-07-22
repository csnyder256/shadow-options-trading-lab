"""Overnight research crew (Floor Hunter P0e) - FREE cloud LLM fan-out for the pre-market
hunt list.

This package is OFFLINE-ONLY tooling for the ~06:15 ET batch job (scripts/research_crew.py).
It never runs inside the live trading loop, never touches llama-swap, and its output
(runtime/hunt_list.json) is a LOOK-trigger only: untrusted DATA that every candidate must
still earn its way through the platform's full gated cascade.

Modules
-------
providers - thin HTTPS adapters for free cloud LLM APIs; every failure degrades to None.
consensus - pure functions: packet building, tolerant JSON extraction, cross-model
             agreement scoring, and the HARD allowlist/schema gate.
"""

from atlas.crew.consensus import (
    CATALYST_KINDS,
    build_packet,
    merge_consensus,
    parse_candidates,
    validate_allowlist,
)
from atlas.crew.providers import load_crew_providers

__all__ = [
    "CATALYST_KINDS",
    "build_packet",
    "merge_consensus",
    "parse_candidates",
    "validate_allowlist",
    "load_crew_providers",
]
