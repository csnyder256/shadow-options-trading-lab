"""Deterministic pre-LLM quality score (signal_params.yaml: quality_score).

Candidates below `min_quality_score` are discarded WITHOUT spending LLM tokens
(deterministic-gate-first pattern, docs/02 step 5). Each component is 0-100; the composite
is their config-weighted sum, clamped to 0-100.
"""

from __future__ import annotations

from typing import Mapping

QUALITY_COMPONENTS = ("trend_alignment", "location", "confirmation", "reward_risk")


def quality_score(components: Mapping[str, float], weights: Mapping[str, float]) -> float:
    total = 0.0
    for name in QUALITY_COMPONENTS:
        total += float(weights[name]) * float(components.get(name, 0.0))
    return max(0.0, min(100.0, total))
