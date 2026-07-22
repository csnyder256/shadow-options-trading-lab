"""RobinhoodMCPClient - the durable call log (how we stay in the loop on an UNATTENDED run) + the
tolerant result parser. No network/session needed for these (they exercise the pure/side-effect bits)."""

import json
from pathlib import Path

from atlas.execution.rh_mcp_client import RobinhoodMCPClient, _parse_result


def test_call_log_writes_jsonl(tmp_path):
    log = tmp_path / "rh_mcp.log"
    c = RobinhoodMCPClient(token_path=tmp_path / "tok.json", call_log_path=log)
    c._log_call("get_portfolio", {"account_number": "X"}, {"data": {"cash": "100.00"}})
    c._log_call("place_equity_order", {"symbol": "F", "type": "stop_market"}, {"data": {"id": "o1"}})
    lines = log.read_text("utf-8").strip().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert rec["tool"] == "get_portfolio" and rec["result"]["data"]["cash"] == "100.00"
    assert json.loads(lines[1])["result"]["data"]["id"] == "o1"


def test_call_log_default_path_is_runtime_sibling_of_config(tmp_path):
    # token at <repo>/config/x.json  ->  log at <repo>/runtime/rh_mcp.log
    repo = tmp_path
    (repo / "config").mkdir()
    c = RobinhoodMCPClient(token_path=repo / "config" / "rh_token.local.json")
    assert c._call_log_path == (repo / "runtime" / "rh_mcp.log")


def test_call_log_never_raises_on_bad_path():
    # a non-writable/odd path must not break trading - _log_call swallows errors
    c = RobinhoodMCPClient(token_path="tok.json", call_log_path="\0:/nope/rh.log")
    c._log_call("get_accounts", {}, {"data": {}})   # should not raise


class _Block:
    def __init__(self, text):
        self.text = text


class _Result:
    def __init__(self, content=None, structured=None, is_error=False):
        self.content = content or []
        self.structuredContent = structured
        self.isError = is_error


def test_parse_result_prefers_structured_then_text():
    assert _parse_result(_Result(structured={"data": {"a": 1}})) == {"data": {"a": 1}}
    assert _parse_result(_Result(content=[_Block('{"data": {"b": 2}}')])) == {"data": {"b": 2}}


def test_parse_result_unparseable_text_returns_text_sentinel():
    out = _parse_result(_Result(content=[_Block("not json")]))
    assert out == {"_text": "not json"}
