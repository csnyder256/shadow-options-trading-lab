"""LLM client interface (docs/02 §2.3).

Both models are reached through ONE interface so the orchestration logic is testable without a
GPU. The real client (added with the serving stack) POSTs to the llama-swap OpenAI-compatible
endpoint with constrained decoding (json_schema / GBNF) at temperature 0 / fixed seed, strips
the <think> reasoning channel, and logs model version + fingerprint. `FakeLLMClient` lets every
piece of analyst/auditor/merge logic be unit-tested deterministically.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Callable

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Remove a <think>...</think> reasoning channel before JSON parsing (both are thinking models)."""
    return _THINK_RE.sub("", text).strip()


class LLMClient(ABC):
    @abstractmethod
    def complete_json(
        self, *, model: str, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Return a parsed JSON object constrained to `schema` (valid by construction)."""


class FakeLLMClient(LLMClient):
    """Test double. `responder(model, system, user, schema) -> dict` supplies canned output."""

    def __init__(self, responder: Callable[[str, str, str, dict[str, Any]], dict[str, Any]]):
        self._responder = responder
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, model, system, user, schema):
        self.calls.append({"model": model, "system": system, "user": user})
        return self._responder(model, system, user, schema)
