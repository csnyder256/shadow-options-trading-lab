"""Robinhood Agentic MCP client - the orchestrator's own connection to
`https://agent.robinhood.com/mcp/trading`.

This is the piece that lets the deterministic Python orchestrator (NOT Claude, NOT the LLMs) place and
manage orders on the live agentic account. It speaks the Model Context Protocol directly via the official
`mcp` SDK over streamable-HTTP, authenticating with the SDK's OAuth client provider.

Why a background thread:
    `BrokerAdapter` is a SYNCHRONOUS interface and `atlas.app` already runs the cycle loop inside
    `asyncio.run(...)`. The MCP SDK is async. So this client owns its OWN event loop on a dedicated
    daemon thread, keeps the `ClientSession` open for the process lifetime, and exposes a blocking
    `call_tool()` that bridges in via `run_coroutine_threadsafe(...).result()`. A separate loop on a
    separate thread sidesteps "this event loop is already running".

Auth model (verified against RH's live OAuth discovery 2026-06-23):
    Dynamic Client Registration (RFC 7591) + PKCE (S256) + authorization_code + refresh_token, public
    client (`token_endpoint_auth_method=none`), scope `internal`. The SDK runs DCR + the browser auth
    once; the refresh token (persisted to disk by `FileTokenStorage`) keeps the session alive headless
    across restarts - no re-login each day. The one-time browser authorization is the user logging into
    Robinhood themselves; this client only opens the URL and catches the loopback redirect.

The `mcp` SDK is imported lazily (inside the methods) so this module imports without it, mirroring the
lazy-import convention of `alpaca_paper_adapter` - unit tests use a FAKE client, never this one.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from atlas.execution.rate_gate import RateGate, RHThrottled, classify_priority

RH_MCP_URL = "https://agent.robinhood.com/mcp/trading"


class RHToolError(RuntimeError):
    """An MCP tool returned an error result (isError=True)."""


class RHConnectError(RuntimeError):
    """The MCP session could not be established (auth/transport)."""


class RHReadError(RuntimeError):
    """A READ tool returned an unreadable/garbled envelope (no 'data' dict, or a key with the wrong
    shape). Callers must FAIL CLOSED on this - never coerce it to an empty/zero value that triggers an
    action (a phantom exit, an oversized buy, a duplicate stop)."""


class FileTokenStorage:
    """Persist the DCR client registration + OAuth tokens to a gitignored JSON file so the refresh
    token survives restarts (unattended re-auth). Duck-typed to the SDK's `TokenStorage` protocol - 
    we don't subclass it, to keep this module importable without `mcp`."""

    def __init__(self, path: Path | str):
        self._path = Path(path)

    def _read(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic: a concurrent reader (or a crash mid-write) must never see a half-written/empty token
        # file and be forced into a hanging browser re-auth.
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self._path)
        try:  # best-effort tighten perms (no-op semantics on Windows)
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    async def get_tokens(self):
        from mcp.shared.auth import OAuthToken
        d = self._read()
        return OAuthToken.model_validate(d["tokens"]) if d.get("tokens") else None

    async def set_tokens(self, tokens) -> None:
        d = self._read()
        d["tokens"] = tokens.model_dump(mode="json")
        self._write(d)

    async def get_client_info(self):
        from mcp.shared.auth import OAuthClientInformationFull
        d = self._read()
        return OAuthClientInformationFull.model_validate(d["client_info"]) if d.get("client_info") else None

    async def set_client_info(self, client_info) -> None:
        d = self._read()
        d["client_info"] = client_info.model_dump(mode="json")
        self._write(d)


class _CallbackCatcher:
    """A tiny loopback HTTP server that captures the OAuth `code`/`state` from the browser redirect,
    so the user never has to copy-paste a URL. Runs in its own thread; resolves an asyncio.Future on
    the client's loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop, port: int):
        self._loop = loop
        self._port = port
        self._future: asyncio.Future = loop.create_future()
        self._server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        catcher = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                qs = parse_qs(urlparse(self.path).query)
                code = (qs.get("code") or [None])[0]
                state = (qs.get("state") or [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                ok = b"<h2>ATLAS \xe2\x86\x94 Robinhood authorized.</h2><p>You can close this tab.</p>"
                bad = b"<h2>No authorization code received.</h2>"
                self.wfile.write(ok if code else bad)
                if code and not catcher._future.done():
                    catcher._loop.call_soon_threadsafe(catcher._future.set_result, (code, state))

            def log_message(self, *_args):  # silence the default stderr logging
                return

        self._server = ThreadingHTTPServer(("localhost", self._port), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def make_callback_handler(self):
        async def handler() -> tuple[str, str | None]:
            return await self._future
        return handler

    def reset(self) -> None:
        """Fresh single-use future for a NEW auth attempt - so a reconnect that needs re-authorization is
        never handed the previous attempt's already-resolved code. The loopback server stays bound."""
        if not self._future.done():
            self._future.cancel()
        self._future = self._loop.create_future()

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass


def _parse_result(result: Any) -> dict:
    """Normalize an MCP CallToolResult to the RH JSON dict (the `{"data": ..., "guide": ...}` shape)."""
    if getattr(result, "isError", False):
        raise RHToolError(_first_text(result) or "tool returned isError")
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict) and sc:
        return sc
    text = _first_text(result)
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_text": text}
    return {}


def _first_text(result: Any) -> str | None:
    for block in getattr(result, "content", None) or []:
        t = getattr(block, "text", None)
        if t:
            return t
    return None


class RobinhoodMCPClient:
    """Lifetime-managed MCP connection to the RH agentic server. `start()` blocks until the session is
    live (running the one-time OAuth flow if needed); `call_tool()` is a blocking, thread-safe bridge;
    `stop()` tears the background loop down."""

    def __init__(self, server_url: str = RH_MCP_URL, token_path: Path | str | None = None, *,
                 redirect_port: int = 8765, call_timeout: float = 60.0, connect_timeout: float = 300.0,
                 client_name: str = "ATLAS Trading Orchestrator", verbose: bool = True,
                 call_log_path: Path | str | None = None,
                 rate_capacity: float = 8.0, rate_refill_per_sec: float = 2.0):
        self._server_url = server_url
        self._token_path = Path(token_path) if token_path else Path("rh_token.local.json")
        self._redirect_port = redirect_port
        self._call_timeout = call_timeout
        self._connect_timeout = connect_timeout
        self._client_name = client_name
        self._verbose = verbose
        # Durable JSONL log of EVERY tool call + raw parsed result (gitignored). This is how we stay in
        # the loop on an UNATTENDED run: the first real place/get/portfolio response SHAPES are captured
        # here for after-the-fact confirmation - no human needed at the moment of the trade.
        if call_log_path is not None:
            self._call_log_path: Path | None = Path(call_log_path)
        else:
            self._call_log_path = self._token_path.resolve().parent.parent / "runtime" / "rh_mcp.log"

        # Shared per-user rate gate: orders never blocked, scan polling yields (see rate_gate.py).
        self._gate = RateGate(rate_capacity, rate_refill_per_sec)

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session = None
        self._ready = threading.Event()
        self._stop_event: asyncio.Event | None = None
        self._start_error: BaseException | None = None

    # ---- lifecycle -------------------------------------------------------------------------------
    def start(self) -> "RobinhoodMCPClient":
        self._thread = threading.Thread(target=self._thread_main, name="rh-mcp", daemon=True)
        self._thread.start()
        if not self._ready.wait(self._connect_timeout + 30):
            raise RHConnectError("RH MCP client did not become ready in time")
        if self._start_error is not None:
            raise RHConnectError(f"RH MCP connect failed: {self._start_error!r}") from self._start_error
        return self

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except BaseException as exc:  # noqa: BLE001 - surface to start()
            self._start_error = exc
            self._ready.set()
        finally:
            # Cancel any task the streamable-HTTP transport left dangling (the long-lived SSE reader),
            # then close - otherwise teardown logs a benign "Task was destroyed but it is pending".
            try:
                pending = [t for t in asyncio.all_tasks(self._loop) if not t.done()]
                for t in pending:
                    t.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            try:
                self._loop.close()
            except Exception:
                pass

    async def _serve(self) -> None:
        from pydantic import AnyUrl

        from mcp import ClientSession
        from mcp.client.auth import OAuthClientProvider
        from mcp.client.streamable_http import streamablehttp_client
        from mcp.shared.auth import OAuthClientMetadata

        self._stop_event = asyncio.Event()
        catcher = _CallbackCatcher(asyncio.get_running_loop(), self._redirect_port)
        catcher.start()

        oauth = OAuthClientProvider(
            server_url=self._server_url,
            client_metadata=OAuthClientMetadata(
                client_name=self._client_name,
                redirect_uris=[AnyUrl(f"http://localhost:{self._redirect_port}/callback")],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                scope="internal",
                token_endpoint_auth_method="none",
            ),
            storage=FileTokenStorage(self._token_path),
            redirect_handler=self._redirect_handler,
            callback_handler=catcher.make_callback_handler(),
            timeout=self._connect_timeout,
        )

        # AUTO-RECONNECT (2026-06-30): one long-lived loop that RE-establishes the session when the
        # transport drops, instead of letting _serve exit (which closed the event loop -> every later
        # call_tool raised "Event loop is closed" and a protector went silently blind until the next
        # relaunch - the 2026-06-30 babysitter+app outage). The FIRST connect keeps the old contract
        # (success -> _ready; failure -> surfaced to start()); only AFTER a first success do we retry,
        # with capped backoff, until stop() is called.
        backoff = 2.0
        connected_once = False
        try:
            while not self._stop_event.is_set():
                catcher.reset()   # fresh single-use OAuth-callback future for this attempt (re-auth safe)
                try:
                    # terminate_on_close=False: RH 400s the SDK's session-DELETE on close (it doesn't
                    # support explicit session termination). Harmless; suppress the noisy teardown error.
                    async with streamablehttp_client(self._server_url, auth=oauth,
                                                     terminate_on_close=False) as (read, write, _get_sid):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            self._session = session
                            backoff = 2.0
                            if not connected_once:
                                connected_once = True
                                self._ready.set()
                            else:
                                self._log_reconnect("RH MCP session re-established")
                            await self._stop_event.wait()
                    break   # clean exit of the context = stop() was requested
                except (KeyboardInterrupt, SystemExit):
                    raise
                except BaseException as exc:  # transport drop / CancelledError / connection error
                    self._session = None
                    if self._stop_event.is_set():
                        break
                    if not connected_once:
                        self._start_error = exc   # initial connect failed -> old behavior: start() raises
                        self._ready.set()
                        return
                    self._log_reconnect(f"RH MCP connection lost ({exc!r}); reconnecting in {backoff:.0f}s")
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                    except asyncio.TimeoutError:
                        pass
                    backoff = min(backoff * 2.0, 30.0)
        finally:
            self._session = None
            catcher.stop()

    async def _redirect_handler(self, url: str) -> None:
        # A browser authorization is needed (first login, or the refresh token expired). Push a phone
        # alert so the user knows to approve the "authorize ATLAS" page, THEN open it. Fire the (blocking)
        # push in a thread so it never stalls the event loop / the auth flow.
        threading.Thread(target=self._notify_reauth, daemon=True).start()
        if self._verbose:
            print(f"\n[RH OAuth] Opening your browser to authorize ATLAS on Robinhood.\n"
                  f"If it does not open, paste this URL into a browser:\n{url}\n", flush=True)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _notify_reauth(self) -> None:
        """Best-effort ntfy phone push when ATLAS needs the user to approve the Robinhood authorize page.
        Reuses config/alerts.json's verified topic. NEVER raises (re-auth must not depend on a push)."""
        try:
            import urllib.request
            cfg_path = self._token_path.resolve().parent.parent / "config" / "alerts.json"
            cfg = json.loads(cfg_path.read_text("utf-8")) if cfg_path.exists() else {}
            n = cfg.get("ntfy") or {}
            topic = (n.get("topic") or "").strip()
            if not n.get("enabled", True) or not topic or "CHANGE-ME" in topic:
                return
            base = (n.get("base_url") or "https://ntfy.sh").rstrip("/")
            body = ("Robinhood wants ATLAS to re-authorize. Approve the 'authorize' page that just opened "
                    "on the trading PC so the platform can reconnect.").encode("utf-8")
            req = urllib.request.Request(
                f"{base}/{topic}", data=body, method="POST",
                headers={"Title": "ATLAS: let me back in please", "Priority": "urgent", "Tags": "lock"})
            urllib.request.urlopen(req, timeout=10).close()
        except Exception:
            pass

    def _log_reconnect(self, msg: str) -> None:
        """Surface a reconnect/drop event to the console AND the durable call log (so the hub + diagnostics
        record the drop and recovery). Never raises."""
        try:
            print(f"[RH MCP] {msg}", flush=True)
        except Exception:
            pass
        self._log_call("_reconnect", {}, {"_note": msg})

    def stop(self) -> None:
        if self._loop is not None and self._stop_event is not None:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=15)

    # ---- calls -----------------------------------------------------------------------------------
    def call_tool(self, name: str, arguments: dict | None = None, *, priority: str | None = None) -> dict:
        if self._session is None or self._loop is None:
            raise RHConnectError("RH MCP client not started")
        # Rate gate: orders (high) are never blocked; run_scan polling (low) is dropped if the budget is
        # tight so a poll can never starve an order. priority overrides the by-name classification.
        prio = priority or classify_priority(name)
        if not self._gate.acquire(priority=prio, timeout=(2.0 if prio == "low" else 15.0)):
            self._log_call(name, arguments or {}, {"_throttled": prio})
            raise RHThrottled(f"rate-gated ({prio}) tool {name}")
        fut = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments or {}), self._loop)
        try:
            result = _parse_result(fut.result(timeout=self._call_timeout))
        except Exception as exc:
            self._log_call(name, arguments or {}, {"_error": repr(exc)})
            raise
        self._log_call(name, arguments or {}, result)
        return result

    def _log_call(self, name: str, args: dict, result: dict) -> None:
        """Append a RH tool call + its raw parsed result to the durable JSONL log. Never raises - logging
        must not break trading. Truncates a huge payload (e.g. a multi-thousand-symbol quote dump)."""
        if not self._call_log_path:
            return
        try:
            import datetime as _dt
            self._call_log_path.parent.mkdir(parents=True, exist_ok=True)
            rec = {"ts": _dt.datetime.now(_dt.timezone.utc).isoformat(), "tool": name,
                   "args": args, "result": result}
            line = json.dumps(rec, default=str, ensure_ascii=False)
            if len(line) > 200_000:   # pathological payload only (e.g. a multi-thousand-symbol quote dump).
                # Keep ts/tool/args but drop the bulky result as VALID json so log consumers (the hub) can
                # still PARSE the line. The old 20k cap sliced mid-string -> invalid json -> the hub silently
                # skipped large run_scan results (a ~37-row scan is ~20k) and froze that scan's panel.
                line = json.dumps({"ts": rec["ts"], "tool": name, "args": args,
                                   "result": {"_truncated": True, "_orig_chars": len(line)}},
                                  default=str, ensure_ascii=False)
            with self._call_log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass

    def list_tools(self) -> list[str]:
        if self._session is None or self._loop is None:
            raise RHConnectError("RH MCP client not started")
        fut = asyncio.run_coroutine_threadsafe(self._session.list_tools(), self._loop)
        res = fut.result(timeout=self._call_timeout)
        return [t.name for t in res.tools]

    # context-manager sugar
    def __enter__(self) -> "RobinhoodMCPClient":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()
