"""Import-sweep tripwire for the all-in options pivot (attic\\ARCHIVE_MANIFEST.md).

Every module the OPTIONS platform + compute mesh depends on must import cleanly, and the
eight keep scripts must spec-load, with the equity systems gone to attic\\. This suite passes
trivially on the pre-move tree and becomes the post-move gate. It also pins the structural
no-order-path guarantee: no keep module may (transitively) import the archived order
machinery when loaded the way production loads it.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

KEEP_MODULES = [
    "atlas",
    "atlas.clock",
    "atlas.config_loader",
    "atlas.fsutil",
    "atlas.types",
    "atlas.collect",
    "atlas.collect.feeds",
    "atlas.collect.market_collector",
    "atlas.collect.tradier_data",
    "atlas.collect.finnhub_feed",
    "atlas.collect.benzinga_news",
    "atlas.collect.alpaca_feed",
    "atlas.crew",
    "atlas.crew.consensus",
    "atlas.crew.providers",
    "atlas.execution",                 # stripped shell: rate_gate only
    "atlas.execution.rate_gate",
    "atlas.hunter",
    "atlas.hunter.feed",
    "atlas.hunter.floors",
    "atlas.hunter.stalker",
    "atlas.models",                    # lazy shell: llm_client + http_client only
    "atlas.models.llm_client",
    "atlas.models.http_client",
    "atlas.options",
    "atlas.options.events",
    "atlas.options.exit_engine",
    "atlas.options.iv_archive",
    "atlas.options.lanes",
    "atlas.options.math",
    "atlas.options.replay",
    "atlas.options.selector",
    "atlas.options.session_calendar",
    "atlas.options.shadow",
    "atlas.options.vendor.blackscholes",
    "atlas.options.vendor.models",
    "atlas.options.vendor.volatility",
    "atlas.signals",
    "atlas.signals.features",
    "atlas.signals.price_action",
    # strategy lab (mission 20260719, lab-strategy-runtime-v1) - additive, shadow-only
    "atlas.strategy_lab",
    "atlas.strategy_lab.carisk",
    "atlas.strategy_lab.exposure",
    "atlas.strategy_lab.grading",
    "atlas.strategy_lab.hub",
    "atlas.strategy_lab.ledger",
    "atlas.strategy_lab.model",
    "atlas.strategy_lab.registry",
    "atlas.strategy_lab.settlement",
    "atlas.strategy_lab.strategy",
    "atlas.strategy_lab.strategies",
    "atlas.strategy_lab.verdicts",
]

KEEP_SCRIPTS = [
    "run_options_shadow.py",
    "grade_options_shadow.py",
    "build_day_briefing.py",
    "run_overnight_lab.py",
    "snapshot_iv.py",
    "news_tap.py",
    "probe_crew.py",
    "research_crew.py",
    # intelligence-layer Wave 0 (2026-07-11) - launcher/schtask-started services must gate here
    "news_flag_tap.py",
    "mention_tap.py",
    "archive_catalyst_events.py",
    "build_catalyst_memory.py",
    "tag_catalyst_headlines.py",
    "refresh_intraday_cache.py",
    # strategy lab (mission 20260719) - the lab must be structurally order-path-free too
    "run_strategy_lab.py",
    "grade_strategy_lab.py",
    "refresh_vix_history.py",
    "refresh_earnings_calendar.py",
]


@pytest.mark.parametrize("mod", KEEP_MODULES)
def test_keep_module_imports(mod):
    importlib.import_module(mod)


@pytest.mark.parametrize("script", KEEP_SCRIPTS)
def test_keep_script_spec_loads(script):
    path = REPO / "scripts" / script
    assert path.exists(), f"{script} missing from scripts/"
    name = f"_keepcheck_{script[:-3]}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # scripts import each other as `scripts.x`; make both spellings resolvable
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)


def test_no_broker_order_transport_ships():
    """No module in this tree may carry a broker order transport. The equity order
    machinery is archived and the Robinhood MCP client is excluded from this copy, so
    there is nothing here that can reach a venue - not disabled, absent."""
    assert not (REPO / "atlas" / "execution" / "rh_mcp_client.py").exists()
    needle = "agent.robinhood" + ".com"   # split so this file is not its own match
    offenders = []
    for path in REPO.rglob("*.py"):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle in text:
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"broker order transport present: {offenders}"


def test_no_order_machinery_reachable_from_options():
    """The options platform's import closure must not contain the archived order machinery.
    Runs in a CLEAN subprocess - the shared pytest process's sys.modules is polluted by
    whatever sibling tests imported first."""
    import subprocess

    probe = (
        "import importlib, sys\n"
        "for m in ('atlas.options.shadow', 'atlas.options.exit_engine',"
        " 'atlas.options.selector', 'atlas.options.lanes', 'atlas.hunter.feed',"
        " 'atlas.strategy_lab.ledger', 'atlas.strategy_lab.model',"
        " 'atlas.strategy_lab.strategies', 'atlas.strategy_lab.hub'):\n"
        "    importlib.import_module(m)\n"
        "banned = [b for b in ('atlas.execution.order_lifecycle',"
        " 'atlas.execution.broker_adapter', 'atlas.execution.guardian',"
        " 'atlas.execution.robinhood_adapter', 'atlas.execution.rh_mcp_client',"
        " 'atlas.orchestrator', 'atlas.app')"
        " if b in sys.modules]\n"
        "assert not banned, f'order machinery reachable: {banned}'\n"
    )
    res = subprocess.run([sys.executable, "-c", probe], cwd=str(REPO),
                         capture_output=True, text=True, timeout=120,
                         env={**__import__('os').environ, "PYTHONPATH": str(REPO)})
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"
