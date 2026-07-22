"""Shared data models (pydantic v2) mirroring the JSON schemas.

These are the in-process contracts. `AnalystView` and `AuditorView` are what the two
models emit (constrained-decoded to schemas/analyst_view + auditor_view). `TradeProposal`
is the immutable merged contract (schemas/trade_proposal) the deterministic pipeline
consumes. `extra='forbid'` mirrors `additionalProperties: false`.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "0.1"


class SetupType(str, Enum):
    breakout_with_volume = "breakout_with_volume"
    pullback_in_uptrend = "pullback_in_uptrend"
    range_reversion = "range_reversion"
    momentum_continuation = "momentum_continuation"
    relative_strength_leader = "relative_strength_leader"


class RiskFlag(str, Enum):
    earnings_risk = "earnings_risk"
    low_liquidity = "low_liquidity"
    unusual_volatility = "unusual_volatility"
    weak_signal = "weak_signal"
    contradictory_indicators = "contradictory_indicators"
    market_weakness = "market_weakness"
    sector_weakness = "sector_weakness"
    overexposure = "overexposure"
    concentration = "concentration"
    news_risk = "news_risk"
    gap_risk = "gap_risk"
    over_confidence = "over_confidence"
    repeated_failed_pattern = "repeated_failed_pattern"
    prompt_injection_suspected = "prompt_injection_suspected"


class Action(str, Enum):
    enter = "enter"
    pass_ = "pass"


class Direction(str, Enum):
    long = "long"
    short = "short"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class CitedNumber(_Strict):
    name: str
    value: float


class AnalystScores(_Strict):
    technical: int = Field(ge=0, le=100)
    market: int = Field(ge=0, le=100)
    news: int = Field(ge=0, le=100)


class Recommendation(_Strict):
    action: Action
    direction: Direction | None = None


class AnalystView(_Strict):
    """Output of GLM-4.7-Flash (analyst). No risk_flags / risk_score by construction."""

    schema_version: str = SCHEMA_VERSION
    symbol: str = Field(pattern=r"^[A-Z.]{1,6}$")
    setup_type: SetupType
    bull_case: str = Field(min_length=20, max_length=1200)
    bear_case: str = Field(min_length=20, max_length=1200)
    uncertainty: str = Field(min_length=20, max_length=1200)
    scores: AnalystScores
    recommendation: Recommendation
    cited_numbers: list[CitedNumber] = Field(default_factory=list)
    # Optional re-look condition emitted on a PASS where the setup is sound but the entry is extended
    # (e.g. {"price": 31.5, "dir": "below"} = "re-look on a pullback to ~31.5"). LENIENT dict, NOT a
    # strict submodel: the thinking-model grammar is not server-enforced, so a malformed `revisit` must
    # be silently ignored by the deterministic RevisitQueue (atlas/revisit.add_price), never raise here
    # and discard the whole candidate. All validation happens downstream, in code.
    revisit: dict | None = None


class AuditorView(_Strict):
    """Output of Qwen3.6-27B (auditor). Owns only risk_flags + risk_score."""

    schema_version: str = SCHEMA_VERSION
    symbol: str = Field(pattern=r"^[A-Z.]{1,6}$")
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    risk_score: int = Field(ge=0, le=100)
    adversarial_notes: str | None = Field(default=None, max_length=1200)


class ProposalScores(_Strict):
    technical: int = Field(ge=0, le=100)
    market: int = Field(ge=0, le=100)
    news: int = Field(ge=0, le=100)
    risk_score: int = Field(ge=0, le=100)


class TradeProposal(_Strict):
    """The immutable merged contract (schemas/trade_proposal.schema.json)."""

    schema_version: str = SCHEMA_VERSION
    symbol: str = Field(pattern=r"^[A-Z.]{1,6}$")
    setup_type: SetupType
    bull_case: str = Field(min_length=20, max_length=1200)
    bear_case: str = Field(min_length=20, max_length=1200)
    uncertainty: str = Field(min_length=20, max_length=1200)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    scores: ProposalScores
    recommendation: Recommendation
    cited_numbers: list[CitedNumber] = Field(default_factory=list)
