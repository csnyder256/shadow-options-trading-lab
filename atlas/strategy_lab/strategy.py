"""Strategy abstraction - the contract every lab strategy implements (pure interfaces).

Each strategy owns its OWN published entry/exit rules (authority: docs/strategies/briefs/<id>.md,
adversarially verified). The runner enforces exactly TWO global rails on top, both journaled as
rails and never as strategy decisions:
    1. expiry-day backstop (combos with settle_at_expiry=False are closed close_min-10)
    2. quarantine (5 exceptions/day disarms the strategy for the day)
Event blackouts are PER-STRATEGY policy (EventPolicy) - several strategies trade INTO events.
The symbol_state halt gate applies to everyone (data validity, not doctrine).

Cohorts: config_hash() = sha256[:12] of {strategy_id, version, params}. Any params/version
change forks the cohort (e-process wealth restarts at 1.0) - same law as the main shadow.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from enum import Enum

from .model import ComboPosition


class EventPolicy(str, Enum):
    BLACKOUT = "blackout"                # runner suppresses scan() during macro blackouts
    TRADE_THROUGH = "trade_through"      # scanned regardless (systematic premium harvest)
    REQUIRES_EVENT = "requires_event"    # scanned ONLY when the strategy's event is upcoming


class GradingBasis(str, Enum):
    DEBIT = "debit"
    MAX_LOSS = "max_loss"
    CAR = "car"


@dataclass(frozen=True)
class StrategyMeta:
    """Class-level declaration; hashed into the cohort via version+params, displayed in the
    registry. `defining_mechanism` is the un-tunable core the prune bar checks against - 
    declared at BIRTH so 'the loss driver IS the strategy' is checkable, not arguable."""
    strategy_id: str
    version: int
    name: str
    universe: tuple                       # tuple[str, ...]
    dte_range: tuple                      # (min_dte, max_dte) for chain requests
    max_concurrent: int
    event_policy: EventPolicy
    grading_basis: GradingBasis           # DECLARED basis (derived basis rules; mismatch flagged)
    defining_mechanism: str               # e.g. "short_vol_carry", "momentum_convexity"
    settle_at_expiry: bool = False        # True: ride to intrinsic settlement at day-roll
    scan_interval_s: float = 60.0
    mark_interval_s: float = 120.0
    expected_fires_per_20_sessions: float = 4.0   # funnel-health floor (STARVED below 0.3x)


@dataclass
class ProposedCombo:
    """What scan() returns: the legs the strategy wants, with the market snapshot it used.
    Each leg dict: {occ, underlying, opt_type, strike, expiry, side, qty, nbbo:{bid,ask},
    iv, delta, gamma, vega, theta_day} - fills are computed by the runner via model.py."""
    kind: str
    underlying: str
    legs: list
    signal: dict                          # strategy's own payload (thresholds hit, context)
    contracts: int = 1
    risk_flags: list = field(default_factory=list)


@dataclass
class ExitAction:
    """What manage() returns when the strategy wants out (or None to hold)."""
    action: str                           # "close" | "roll"
    rule: str                             # strategy-local rule id, e.g. "profit_50pct"
    state: dict = field(default_factory=dict)
    roll_proposal: object = None          # ProposedCombo when action == "roll"


@dataclass
class StrategyContext:
    """Everything a strategy may read on a scan/manage call. Runner-built; strategies never
    do IO. `hub` exposes read-only market data (chains/quotes/bars/vol_regime/earnings)."""
    now_ts: float
    dt_et: datetime
    day: str
    minute: int                           # minutes since midnight ET
    session_close_min: int
    hub: object
    events: list = field(default_factory=list)     # upcoming EconEvents (7d horizon)
    in_blackout: str = ""                          # non-empty = blackout reason
    earnings: dict = field(default_factory=dict)   # {symbol: {date, hour}} for the universe
    journal: object = None                         # callable(dict) -> None, strategy-scoped
    open_positions: list = field(default_factory=list)   # THIS strategy's open ComboPositions


class Strategy(ABC):
    """One published strategy. Subclasses set META and a frozen params dataclass, and
    implement scan()/manage(). All constants in params carry provenance in the class
    docstring citing the brief (tests/strategy_lab provenance test enforces coverage)."""

    META: StrategyMeta
    params: object = None                 # frozen dataclass of tunables (may be None)

    def config_hash(self) -> str:
        payload = {"strategy_id": self.META.strategy_id, "version": self.META.version,
                   "params": asdict(self.params) if is_dataclass(self.params) else None}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]

    @abstractmethod
    def scan(self, ctx: StrategyContext) -> list:
        """Return [ProposedCombo] (usually 0 or 1). Called every META.scan_interval_s while
        armed and under max_concurrent. Must be pure given ctx."""

    @abstractmethod
    def manage(self, pos: ComboPosition, ctx: StrategyContext) -> ExitAction | None:
        """The strategy's OWN published exit logic. None = hold. Called every
        META.mark_interval_s per open combo."""

    def rebuild(self, pos: ComboPosition, marks: list) -> None:
        """Re-prime carried state from the position's mark history after a restart.
        Default: carry the last mark's state dict."""
        if marks:
            pos.carried = dict(marks[-1].get("state") or {})

    # -- identity helpers -------------------------------------------------
    @property
    def strategy_id(self) -> str:
        return self.META.strategy_id

    def next_position_id(self, underlying: str, day: str, minute: int, seq: int) -> str:
        return f"{self.META.strategy_id}:{underlying}:{day}:{minute}:{seq}"


def expiry_backstop_due(pos: ComboPosition, *, today: date, minute: int,
                        session_close_min: int, lead_min: int = 10) -> bool:
    """Global rail 1: a combo whose NEAREST leg expires today and whose strategy does not
    settle-at-expiry must be closed by close-lead_min. Pure; runner applies it."""
    return pos.nearest_expiry <= today and minute >= session_close_min - lead_min
