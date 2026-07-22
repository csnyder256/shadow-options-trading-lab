"""Minimal model shim for the vendored options math (2026-07-09).

VENDORED from the owner's options project (C:/path/to/options-project, app/models.py) - 
only the three shapes blackscholes.py / volatility.py import. Kept byte-compatible with the
originals so vendored math and its ported tests run unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


@dataclass
class Greeks:
    delta: float
    gamma: float
    theta: float  # per calendar day
    vega: float   # per 1 percentage-point (1%) change in IV
    rho: float    # per 1 percentage-point (1%) change in rate
    d1: float
    d2: float


@dataclass
class OHLC:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
