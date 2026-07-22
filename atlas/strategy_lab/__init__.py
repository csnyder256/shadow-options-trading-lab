"""STRATEGY LAB - 20 published options strategies running shadow-only beside the main
options shadow trader (mission 20260719-strategy-lab; registration lab-strategy-runtime-v1).

HARD BOUNDARIES (each is load-bearing):
  * SHADOW ONLY. Nothing in this package (or anything it imports) can place an order.
    The package's entire side-effect surface is runtime/strategy_lab/ JSONL ledgers.
  * The MAIN shadow (cohort a5ce85415e5a) is untouched: this package IMPORTS
    atlas.options.shadow's pure fill math and ledger IO, it never modifies atlas/options/.
  * Each strategy is deterministic code with its OWN published entry/exit rules
    (docs/strategies/briefs/<id>.md is the authority) and its OWN config-hash cohort.
    The main system's exit ladder / selector doctrine deliberately does NOT apply here
    (owner directive 2026-07-19: these are NEW stances).
  * Namespace is `strategy_lab` everywhere - runtime/lab/ belongs to the OVERNIGHT lab.
"""
