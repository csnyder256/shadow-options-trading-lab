"""HttpLLMClient transient-retry policy (the analyst/auditor cold-start fix).

The first constrained request right after a VRAM swap can transiently fail (connection blip / 5xx /
empty body) even though SwapManager.load() already warmed the model - which used to surface as
`analyst_error:LLMRequestError` and silently waste the candidate. complete_json now retries TRANSIENT
failures with a bounded budget, but NEVER retries deterministic ones (a 4xx, a read timeout, or
non-empty-but-unparseable output at temp 0 - re-sending the identical prompt just repeats it).

These tests monkeypatch urllib so they need no live server; backoff is 0 so they don't sleep.
"""

import json
import urllib.error
import urllib.request

import pytest

from atlas.models.http_client import HttpLLMClient, LLMRequestError

SCHEMA = {"title": "t", "type": "object"}


class _FakeResp:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode("utf-8")
        self.status = 200

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _payload(content='{"ok": true}', finish="stop"):
    return {"model": "glm", "choices": [{"message": {"content": content}, "finish_reason": finish}]}


def _http_error(code):
    return urllib.error.HTTPError("http://x/v1/chat/completions", code, "err", None, None)


def _seq_urlopen(behaviors):
    """Return (fake_urlopen, calls) where each call yields the next behavior (raise it if an Exception,
    else return it). The last behavior repeats if calls exceed the list."""
    calls = {"n": 0}

    def fake(req, timeout=None):
        b = behaviors[min(calls["n"], len(behaviors) - 1)]
        calls["n"] += 1
        if isinstance(b, Exception):
            raise b
        return b

    return fake, calls


def _client(max_retries=2):
    return HttpLLMClient("http://x", max_retries=max_retries, retry_backoff_seconds=0.0)


def _call(client):
    return client.complete_json(model="glm", system="s", user="u", schema=SCHEMA)


def test_success_on_first_try_makes_one_call(monkeypatch):
    fake, calls = _seq_urlopen([_FakeResp(_payload())])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == {"ok": True}
    assert calls["n"] == 1


def test_retries_transient_url_error_then_succeeds(monkeypatch):
    fake, calls = _seq_urlopen([
        urllib.error.URLError("connection refused"),
        urllib.error.URLError("connection reset"),
        _FakeResp(_payload()),
    ])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == {"ok": True}
    assert calls["n"] == 3  # 1 initial + 2 retries


def test_retries_server_5xx_then_succeeds(monkeypatch):
    fake, calls = _seq_urlopen([_http_error(503), _FakeResp(_payload())])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == {"ok": True}
    assert calls["n"] == 2


def test_retries_empty_content_then_succeeds(monkeypatch):
    # A 200 with empty content (only a stripped <think>) = model not producing yet -> transient.
    fake, calls = _seq_urlopen([
        _FakeResp(_payload(content="<think>warming up</think>")),
        _FakeResp(_payload()),
    ])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == {"ok": True}
    assert calls["n"] == 2


def test_retries_unexpected_shape_then_succeeds(monkeypatch):
    # An error body in place of a completion (no choices) is treated as transient.
    fake, calls = _seq_urlopen([_FakeResp({"error": "loading"}), _FakeResp(_payload())])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == {"ok": True}
    assert calls["n"] == 2


def test_does_not_retry_client_4xx(monkeypatch):
    fake, calls = _seq_urlopen([_http_error(400), _FakeResp(_payload())])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(LLMRequestError):
        _call(_client())
    assert calls["n"] == 1  # deterministic -> no retry (the would-be success is never reached)


def test_does_not_retry_read_timeout(monkeypatch):
    # The model was warmed before this call, so a read timeout is slow inference, not a cold start.
    fake, calls = _seq_urlopen([urllib.error.URLError(TimeoutError("timed out")), _FakeResp(_payload())])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(LLMRequestError):
        _call(_client())
    assert calls["n"] == 1


def test_does_not_retry_nonempty_unparseable_output(monkeypatch):
    # Truncated/garbled but non-empty output is deterministic at temp 0 -> retrying repeats it.
    fake, calls = _seq_urlopen([_FakeResp(_payload(content="not json at all", finish="length")),
                                _FakeResp(_payload())])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(LLMRequestError):
        _call(_client())
    assert calls["n"] == 1


def test_gives_up_after_max_retries(monkeypatch):
    fake, calls = _seq_urlopen([urllib.error.URLError("connection refused")])  # always fails
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(LLMRequestError):
        _call(_client(max_retries=2))
    assert calls["n"] == 3  # 1 initial + 2 retries, then give up


def test_zero_retries_means_one_attempt(monkeypatch):
    fake, calls = _seq_urlopen([urllib.error.URLError("connection refused")])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(LLMRequestError):
        _call(_client(max_retries=0))
    assert calls["n"] == 1


def test_strips_think_and_code_fences_on_success(monkeypatch):
    content = '<think>chain of thought</think>```json\n{"ok": true}\n```'
    fake, calls = _seq_urlopen([_FakeResp(_payload(content=content))])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == {"ok": True}
    assert calls["n"] == 1


# ---- tolerant parse of UNCONSTRAINED output (llama.cpp #20345: grammar not enforced with thinking) ----
def test_recovers_trailing_comma(monkeypatch):
    fake, calls = _seq_urlopen([_FakeResp(_payload(content='{"risk_score": 40, "ok": true,}'))])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == {"risk_score": 40, "ok": True}
    assert calls["n"] == 1                               # repaired in-place, no retry


def test_recovers_unescaped_control_chars_in_string(monkeypatch):
    # a raw newline inside a string is invalid STRICT json but common in free-text notes; strict=False keeps it
    fake, calls = _seq_urlopen([_FakeResp(_payload(content='{"note": "line1\nline2"}'))])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == {"note": "line1\nline2"}


def test_recovers_prose_wrapped_fenced_json(monkeypatch):
    content = 'Sure - here is the verdict:\n```json\n{"risk_score": 40}\n```\nThat is my answer.'
    fake, calls = _seq_urlopen([_FakeResp(_payload(content=content))])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == {"risk_score": 40}


def test_genuine_garbage_still_fails_closed(monkeypatch):
    # repair is value-preserving; unrecoverable output deterministically fails -> no trade (fail-closed)
    fake, calls = _seq_urlopen([_FakeResp(_payload(content="not json at all {[")), _FakeResp(_payload())])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(LLMRequestError):
        _call(_client())
    assert calls["n"] == 1                               # deterministic -> not retried


# ---- thinking-budget exhaustion + extra_body (diagnosed live 2026-07-11: GLM-4.7-Flash burned
# ---- the whole max_tokens in reasoning_content and every tagger batch came back empty) ----
def _thinking_payload():
    return {"model": "glm", "choices": [{
        "message": {"content": "", "reasoning_content": "step 1... step 2..."},
        "finish_reason": "length"}]}


def test_thinking_budget_exhaustion_is_not_retried(monkeypatch):
    # Empty content + finish_reason=length + non-empty reasoning = the budget went to thoughts.
    # Deterministic at temp 0: a retry re-buys the same thoughts -> exactly one attempt.
    fake, calls = _seq_urlopen([_FakeResp(_thinking_payload()), _FakeResp(_payload())])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    with pytest.raises(LLMRequestError, match="thinking consumed"):
        _call(_client())
    assert calls["n"] == 1


def test_empty_without_reasoning_stays_transient(monkeypatch):
    # The pre-existing swap-blip shape (empty content, no reasoning channel) must KEEP retrying.
    p = {"model": "glm", "choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}
    fake, calls = _seq_urlopen([_FakeResp(p), _FakeResp(_payload())])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == {"ok": True}
    assert calls["n"] == 2


def test_extracts_top_level_array_reply(monkeypatch):
    # The tagger requests a JSON ARRAY; the object-only extractor used to return just the
    # array's first element (live 2026-07-11: every batch parsed to 0 tags).
    content = '[{"i": 0, "kind": "earnings"}, {"i": 1, "kind": "other"}]'
    fake, calls = _seq_urlopen([_FakeResp(_payload(content=content))])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == [{"i": 0, "kind": "earnings"}, {"i": 1, "kind": "other"}]


def test_extracts_fenced_array_with_prose(monkeypatch):
    content = 'Here you go:\n```json\n[{"i": 0, "kind": "fda"}]\n```'
    fake, calls = _seq_urlopen([_FakeResp(_payload(content=content))])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert _call(_client()) == [{"i": 0, "kind": "fda"}]


def test_extra_body_is_merged_into_request(monkeypatch):
    seen = {}

    def fake(req, timeout=None):
        seen.update(json.loads(req.data.decode("utf-8")))
        return _FakeResp(_payload())

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    client = HttpLLMClient("http://x", retry_backoff_seconds=0.0,
                           extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    assert client.complete_json(model="glm", system="s", user="u", schema=SCHEMA) == {"ok": True}
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["model"] == "glm" and "response_format" in seen   # defaults survive the merge
