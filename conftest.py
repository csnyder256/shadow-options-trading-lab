"""Ensure the framework root is importable as the `atlas` package root under pytest."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------------------------
# 2026-07-09: daily_deployment_pct is an OPERATOR throttle (0 live = old-engine buying OFF while
# the options shadow accumulates evidence). The suite tests orchestrator/risk MECHANICS, which
# need a working budget - so pytest pins the canonical 95 at the config loader, exactly once,
# here. A test that deliberately wants the LIVE operator value must read config/risk_limits.yaml
# directly (none do today). Remove this shim if/when equity buying is re-armed at 95.
import atlas.config_loader as _cfg_loader  # noqa: E402

_real_load_config = _cfg_loader.load_config


def _load_config_with_pinned_operator_knobs(*args, **kwargs):
    cfg = _real_load_config(*args, **kwargs)
    try:
        cfg.raw_risk_limits["frequency"]["daily_deployment_pct"] = 95.0
    except (KeyError, TypeError, AttributeError):
        pass
    return cfg


_cfg_loader.load_config = _load_config_with_pinned_operator_knobs
