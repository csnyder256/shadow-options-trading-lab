"""Phase 1 gating proof: connect the orchestrator's OWN MCP client to Robinhood and make READ-ONLY
calls. NO orders, zero money risk. This proves OAuth (DCR + PKCE + refresh) and the streamable-HTTP
transport work end-to-end from standalone Python, and that the live account matches expectations.

First run opens your browser ONCE to log into Robinhood and approve ATLAS; the refresh token is then
cached to config/rh_token.local.json so subsequent runs are silent.

    PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\rh_verify.py [account_number]
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.config_loader import FRAMEWORK_ROOT  # noqa: E402
from atlas.execution.rh_mcp_client import RH_MCP_URL, RobinhoodMCPClient  # noqa: E402


def _mask(s) -> str:
    s = str(s)
    return "*" * max(0, len(s) - 4) + s[-4:]


def main() -> int:
    cfg_path = FRAMEWORK_ROOT / "config" / "robinhood.local.yaml"
    rh = yaml.safe_load(cfg_path.read_text("utf-8")) if cfg_path.exists() else {}
    acct = sys.argv[1] if len(sys.argv) > 1 else rh.get("account_number")
    token_path = FRAMEWORK_ROOT / (rh.get("token_path") or "config/rh_token.local.json")
    url = rh.get("mcp_url") or RH_MCP_URL

    print(f"Connecting to {url}\n(token cache: {token_path})", flush=True)
    client = RobinhoodMCPClient(url, token_path)
    client.start()
    try:
        print("CONNECTED. Tool surface:", ", ".join(sorted(client.list_tools())), flush=True)

        accts = client.call_tool("get_accounts", {})
        for a in (accts.get("data", {}).get("accounts") or []):
            print(f"  account {_mask(a.get('account_number'))} type={a.get('type')} "
                  f"agentic_allowed={a.get('agentic_allowed')} nickname={a.get('nickname')}")

        if acct:
            port = client.call_tool("get_portfolio", {"account_number": acct})
            d = port.get("data", {})
            bp = (d.get("buying_power") or {}).get("buying_power")
            print(f"PORTFOLIO {_mask(acct)}: total={d.get('total_value')} "
                  f"cash={d.get('cash')} buying_power={bp}")
            pos = client.call_tool("get_equity_positions", {"account_number": acct})
            print("OPEN POSITIONS:", len(pos.get("data", {}).get("positions") or []))
            orders = client.call_tool("get_equity_orders", {"account_number": acct})
            print("RECENT/OPEN ORDERS:", len(orders.get("data", {}).get("orders") or []))
        else:
            print("No account_number configured; auth proof complete, skipped portfolio.")

        print("PHASE-1 OK")
        return 0
    finally:
        client.stop()


if __name__ == "__main__":
    raise SystemExit(main())
