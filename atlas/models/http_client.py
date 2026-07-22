"""Real LLM client - POSTs to the llama-swap OpenAI-compatible endpoint, temperature 0 / fixed seed,
strips the <think> channel, and parses the JSON.

We REQUEST a json_schema response_format, but llama.cpp does NOT actually enforce that grammar for a
thinking model (issue #20345: with thinking on, grammar enforcement is silently inactive; a
schema->GBNF conversion failure can also fail open, #19051). BOTH ATLAS models think, so the schema is
enforced CLIENT-SIDE: tolerant extraction + a value-preserving repair here, then STRICT Pydantic
validation by the caller (AnalystView / AuditorView). A malformed or out-of-schema verdict therefore
fails closed (no trade) - the grammar is best-effort, the client validation is the real guard.
Stdlib-only (urllib); unit tests use FakeLLMClient, so this needs the live server to exercise."""

from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from atlas.models.llm_client import LLMClient, strip_think


class LLMRequestError(RuntimeError):
    """A failed LLM request. `retryable` marks TRANSIENT failures (a connection blip / 5xx / a
    not-ready model right after a VRAM swap) that a bounded retry can absorb, vs DETERMINISTIC ones
    (4xx, or non-empty-but-unparseable output at temp 0) where re-sending the identical prompt is futile."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def extract_json_object(text: str) -> str:
    """Pull the first balanced JSON value - object OR array - out of model output (tolerant of
    ``` fences and any prose around it when the grammar isn't strictly applied). Keeps its
    original object-only name; arrays joined 2026-07-11 when the tagger's array replies came
    back as just their first element (live find: every batch 'tagged 0/20')."""
    text = text.strip()
    if text.startswith("```"):
        body = text[3:]
        if body[:4].lower() == "json":
            body = body[4:]
        text = body.split("```", 1)[0].strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return text
    start = min(starts)
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]  # unbalanced -> truncated output (raise more max_tokens)


def _repair_json(text: str) -> str:
    """Conservative, VALUE-PRESERVING repair for the unconstrained output llama.cpp returns when the
    schema grammar is inactive (#20345): drop trailing commas before a closing } or ]. String-aware, so
    a comma inside a value is untouched. Never changes a value -> a repaired-but-out-of-schema verdict
    still fails the caller's strict validation (fail-closed)."""
    out: list[str] = []
    in_str = esc = False
    for i, ch in enumerate(text):
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            continue
        if ch == ",":                                  # drop a comma whose next non-space is } or ]
            j = i + 1
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            if j < len(text) and text[j] in "}]":
                continue
        out.append(ch)
    return "".join(out)


def loads_tolerant(text: str) -> Any:
    """Parse model JSON, tolerating the cosmetic defects of UNCONSTRAINED output (#20345). `strict=False`
    allows literal control chars inside strings (e.g. a raw newline in free-text notes); on failure, ONE
    value-preserving repair pass (drop trailing commas) is retried. Raises JSONDecodeError if still
    unparseable -> the caller fails closed. NEVER alters values, so strict schema validation downstream
    still rejects a bad verdict."""
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        return json.loads(_repair_json(text), strict=False)


class HttpLLMClient(LLMClient):
    def __init__(
        self,
        base_url: str,
        *,
        temperature: float = 0.0,
        seed: int = 42,
        timeout: float = 180.0,
        max_tokens: int = 1536,
        max_retries: int = 2,
        retry_backoff_seconds: float = 1.0,
        extra_body: dict[str, Any] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.seed = seed
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        # Extra top-level request fields merged into every POST body. The motivating case
        # (diagnosed live 2026-07-11): {"chat_template_kwargs": {"enable_thinking": False}} - 
        # GLM-4.7-Flash is a HYBRID thinker and, left thinking, spends the entire max_tokens
        # budget in the separate reasoning_content channel and returns EMPTY content
        # (finish_reason=length) on batch-sized prompts.
        self.extra_body = dict(extra_body) if extra_body else {}
        self.last_model_fingerprint: str | None = None

    def complete_json(self, *, model, system, user, schema):
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "seed": self.seed,
            "max_tokens": self.max_tokens,
            # Request the schema grammar (best-effort: llama.cpp does NOT enforce it with thinking on
            # -> #20345; the client-side extract + strict Pydantic validation is the real guard).
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.get("title", "output"),
                    "schema": schema,
                    "strict": True,
                },
            },
        }
        if self.extra_body:
            body.update(self.extra_body)
        data = json.dumps(body).encode("utf-8")
        # Bounded retry for TRANSIENT failures only. The dominant one is the FIRST constrained request
        # right after a VRAM swap: the model is still settling, so the proxy can return a connection
        # blip / 5xx / empty body. Without this the candidate is silently wasted (analyst_error).
        # Deterministic failures (4xx, or non-empty unparseable output at temp 0) are NOT retried - the
        # identical prompt would just repeat. (The model is warmed by SwapManager.load() before we get
        # here, so a read timeout means slow inference, not a cold start -> also not retried.)
        for attempt in range(self.max_retries + 1):
            try:
                return self._post_once(data, model=model)
            except LLMRequestError as exc:
                if not exc.retryable or attempt >= self.max_retries:
                    raise
                print(f"[llm-retry] {model}: transient failure "
                      f"(attempt {attempt + 1}/{self.max_retries + 1}): {exc}", file=sys.stderr, flush=True)
                if self.retry_backoff_seconds:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
        raise AssertionError("unreachable")  # the loop always returns or raises

    def _post_once(self, data: bytes, *, model: str) -> dict[str, Any]:
        req = urllib.request.Request(
            self.base_url + "/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 5xx = server loading/overloaded (transient); 4xx = our request is malformed (deterministic).
            raise LLMRequestError(f"llama-swap HTTP {exc.code}: {exc}", retryable=exc.code >= 500) from exc
        except urllib.error.URLError as exc:
            # Connection refused/reset right at a model swap = transient. A READ timeout means the server
            # accepted the request but is slow (the model was warmed before this call), so retrying just
            # re-waits the full timeout -> not retryable.
            is_timeout = isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout))
            raise LLMRequestError(f"llama-swap request failed: {exc}", retryable=not is_timeout) from exc

        self.last_model_fingerprint = payload.get("model")
        try:
            msg = payload["choices"][0]["message"]
            content = msg.get("content") or ""
            # Some chat templates split reasoning into a separate field (reasoning_content);
            # it is never parsed as output, only measured for the budget-exhaustion diagnosis.
        except (KeyError, IndexError) as exc:
            # An error body in place of a completion (e.g. the proxy reporting a load in progress).
            raise LLMRequestError(f"unexpected completion shape: {payload}", retryable=True) from exc
        stripped = strip_think(content)
        if not stripped.strip():
            finish = payload["choices"][0].get("finish_reason")
            reasoning_len = len(msg.get("reasoning_content") or msg.get("reasoning") or "")
            if finish == "length" and reasoning_len:
                # The model spent the WHOLE max_tokens budget thinking (reasoning_content) and
                # never started the answer. Deterministic at temp 0 - a retry re-buys the same
                # thoughts. Fix at the caller: extra_body chat_template_kwargs
                # {"enable_thinking": false} (hybrid models) or a budget the thinking variant
                # can finish inside. Diagnosed live 2026-07-11 (GLM-4.7-Flash, tagger batches).
                raise LLMRequestError(
                    f"thinking consumed the whole max_tokens budget (finish_reason=length, "
                    f"reasoning_len={reasoning_len}) - disable thinking via extra_body "
                    f"chat_template_kwargs or raise max_tokens", retryable=False)
            # A 200 with empty content right after a swap = the model isn't producing yet -> transient.
            raise LLMRequestError("empty completion content (model not ready?)", retryable=True)
        cleaned = extract_json_object(stripped)
        try:
            return loads_tolerant(cleaned)
        except json.JSONDecodeError as exc:
            finish = payload["choices"][0].get("finish_reason")
            # Non-empty but unparseable even after repair = truncation / genuine garbage: deterministic
            # at temp 0 -> no retry, fail closed (the caller treats no verdict as no trade).
            raise LLMRequestError(
                f"model did not return parseable JSON (finish_reason={finish}, "
                f"len={len(content)}): {cleaned[:160]!r}", retryable=False
            ) from exc

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(self.base_url + "/v1/models", timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False
