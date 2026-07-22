"""Load + validate the config/*.yaml files into frozen, typed config objects.

Principle (docs/01 §1.4, docs/03): the YAML files are the authoritative source of the
deterministic rules. This loader fails fast on a missing/garbled file or an internally
inconsistent value (e.g. consensus weights that do not sum to 1). The deterministic
engine reads these objects; the LLMs never do.

M1 types the sections the deterministic spine needs now (consensus + the numbers used by
the risk engine and sizing). Other files are parsed and exposed as read-only dicts via
`.raw_*`; they get promoted to typed dataclasses as their engine module is built.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = FRAMEWORK_ROOT / "config"

_REQUIRED_FILES = (
    "risk_limits.yaml",
    "position_sizing.yaml",
    "consensus.yaml",
    "signal_params.yaml",
    "universe.yaml",
    "system.yaml",
)


class ConfigError(RuntimeError):
    """Raised when configuration is missing, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class ConsensusConfig:
    """config/consensus.yaml - the fixed scoring formula + drift guards."""

    w_tech: float
    w_market: float
    w_news: float
    risk_weight: float
    risk_veto_threshold: int
    never_carry_forward: bool
    external_recalibration: bool
    calibration_lookback_trades: int
    calibration_discount_max: float
    anonymize_arguments_for_judge: bool
    risk_is_subtractive_only: bool
    drift_tolerance_pct: float

    def __post_init__(self) -> None:
        total = self.w_tech + self.w_market + self.w_news
        if abs(total - 1.0) > 1e-6:
            raise ConfigError(
                f"consensus weights must sum to 1.0 (got {total:.6f}: "
                f"tech={self.w_tech}, market={self.w_market}, news={self.w_news})"
            )
        for name in ("w_tech", "w_market", "w_news", "risk_weight"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ConfigError(f"consensus.{name} must be in [0,1] (got {v})")
        if not 0 <= self.risk_veto_threshold <= 100:
            raise ConfigError(
                f"risk_veto_threshold must be in [0,100] (got {self.risk_veto_threshold})"
            )
        if not 0.0 <= self.calibration_discount_max <= 1.0:
            raise ConfigError("calibration_discount_max must be in [0,1]")


@dataclass(frozen=True)
class AtlasConfig:
    """Aggregate of all config files. `consensus` is typed; the rest are read-only dicts."""

    consensus: ConsensusConfig
    raw_risk_limits: Mapping[str, Any]
    raw_position_sizing: Mapping[str, Any]
    raw_signal_params: Mapping[str, Any]
    raw_universe: Mapping[str, Any]
    raw_system: Mapping[str, Any]
    config_dir: Path


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"required config file missing: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via malformed-file tests
        raise ConfigError(f"could not parse {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must be a YAML mapping at the top level")
    return data


def _freeze(d: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(d))


def _build_consensus(raw: Mapping[str, Any]) -> ConsensusConfig:
    try:
        w = raw["weights"]
        guards = raw["confidence_drift_guards"]
        calib = raw["calibration"]
        return ConsensusConfig(
            w_tech=float(w["w_tech"]),
            w_market=float(w["w_market"]),
            w_news=float(w["w_news"]),
            risk_weight=float(w["risk_weight"]),
            risk_veto_threshold=int(w["risk_veto_threshold"]),
            never_carry_forward=bool(guards["never_carry_forward"]),
            external_recalibration=bool(guards["external_recalibration"]),
            calibration_lookback_trades=int(guards["calibration_lookback_trades"]),
            calibration_discount_max=float(guards["calibration_discount_max"]),
            anonymize_arguments_for_judge=bool(guards["anonymize_arguments_for_judge"]),
            risk_is_subtractive_only=bool(guards["risk_is_subtractive_only"]),
            drift_tolerance_pct=float(calib["drift_tolerance_pct"]),
        )
    except KeyError as exc:
        raise ConfigError(f"consensus.yaml missing key: {exc}") from exc


def load_config(config_dir: Path | str = DEFAULT_CONFIG_DIR) -> AtlasConfig:
    """Load and validate all config files. Raises ConfigError on any problem."""
    config_dir = Path(config_dir)
    files = {name: _load_yaml(config_dir / name) for name in _REQUIRED_FILES}
    return AtlasConfig(
        consensus=_build_consensus(files["consensus.yaml"]),
        raw_risk_limits=_freeze(files["risk_limits.yaml"]),
        raw_position_sizing=_freeze(files["position_sizing.yaml"]),
        raw_signal_params=_freeze(files["signal_params.yaml"]),
        raw_universe=_freeze(files["universe.yaml"]),
        raw_system=_freeze(files["system.yaml"]),
        config_dir=config_dir,
    )
