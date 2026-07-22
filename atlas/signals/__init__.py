"""Signal Engine (docs/04) - deterministic, reproducible technical features and candidate
setups. Pure numpy indicators (no TA-Lib C dependency, per docs/08); no LLM involvement."""

from atlas.signals.signal_engine import CandidateSetup, SignalEngine
from atlas.signals.quality_filter import quality_score

__all__ = ["CandidateSetup", "SignalEngine", "quality_score"]
