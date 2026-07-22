"""Thin adapters for FREE cloud LLM APIs used by the overnight research crew.

Plain HTTPS via the stdlib (urllib), mirroring atlas/collect/finnhub_feed.py - no new
package dependency. Every provider exposes one method:

    complete(prompt: str, *, system: str, timeout: int) -> str | None

and returns None on ANY failure (missing key, 4xx/5xx, 429, timeout, bad JSON, empty
reply). The crew degrades gracefully: a dead provider just means one fewer vote in the
consensus - never a crash, never a retry storm against a free tier.

Keys live in gitignored config/credentials.local.yaml under a `crew:` section (shape
documented in docs/HUNTER_API_KEYS.md). The whole section - or the whole file - may be
absent; `load_crew_providers()` then returns an empty dict and the batch job still exits 0.

Rate limits: these are FREE tiers and the crew is a batch job where latency is free, so
each provider self-throttles with a conservative minimum interval between its own calls
(sleep-before-call). The crew normally makes exactly ONE call per provider per morning,
so the throttle is a seatbelt, not a cost.

ToS hygiene (enforced at the fan-out call site in scripts/research_crew.py): prompts may
contain ONLY public-market data - symbols, headlines, calendar events, prior-day
price/volume stats. Never account state, positions, orders, P&L, sizing, or strategy
internals. Free tiers may train on inputs; treat every byte sent as public.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from atlas.config_loader import FRAMEWORK_ROOT

_CREDS_PATH = FRAMEWORK_ROOT / "config" / "credentials.local.yaml"

# Conservative floors between calls to the SAME provider (seconds). Free-tier RPM limits
# as of mid-2026: Gemini flash ~10 RPM, OpenRouter :free ~20 RPM, Groq ~30 RPM,
# Cerebras ~5 RPM, Z.ai flash ~comparable. We stay well under all of them.
_MIN_INTERVAL_S = {
    "gemini": 10.0,
    "openrouter": 6.0,
    "groq": 3.0,
    "cerebras": 15.0,
    "zai": 6.0,
}

# Default models - all free-tier, live-verified 2026-07-10 against each provider's /models
# endpoint. Each is overridable per provider via `crew: {<name>_model: "..."}` in
# credentials.local.yaml because free pools churn (the original deepseek:free slug left the
# OpenRouter free pool, and gemini-2.5-flash closed to new API users - both found dead on the
# first live probe).
_DEFAULT_MODELS = {
    # openrouter :free pools share upstream capacity - gpt-oss-120b/llama-3.3-70b/qwen3-next
    # all probed 429-saturated 2026-07-10 01:40 ET while nemotron answered; a 429 costs one
    # consensus vote, never a crash
    "openrouter": "nvidia/nemotron-3-super-120b-a12b:free",
    "groq": "llama-3.3-70b-versatile",
    "cerebras": "zai-glm-4.7",
    "gemini": "gemini-flash-latest",
    "zai": "glm-4.7-flash",
}


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    """POST JSON over stdlib urllib (the finnhub_feed pattern). Raises on any problem - 
    callers catch broadly and degrade to None."""
    from urllib.request import Request, urlopen

    body = json.dumps(payload).encode("utf-8")
    # a real User-Agent is REQUIRED: Cloudflare-fronted providers (Groq, Cerebras) hard-block
    # urllib's default "Python-urllib/x.y" signature with error 1010 (found on the first
    # live key probe, 2026-07-10)
    req = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "atlas-research-crew/1.0", **headers},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise OSError(f"HTTP {resp.status}")
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("non-object JSON response")
    return data


class CrewProvider:
    """Base adapter: self-throttle + fail-to-None wrapper around a subclass `_complete`."""

    name = "?"

    def __init__(self, api_key: str, *, model: str, min_interval_s: float):
        self._key = api_key
        self.model = model
        self._min_interval_s = float(min_interval_s)
        self._last_call = 0.0

    # -- rate limiting -------------------------------------------------------------
    def _throttle(self) -> None:
        wait = self._min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    # -- public API ----------------------------------------------------------------
    def complete(self, prompt: str, *, system: str, timeout: int = 90,
                 max_tokens: int | None = None) -> str | None:
        """One chat completion. None on ANY failure - the crew treats None as 'no vote'.
        `max_tokens` None preserves each family's historical default (2048 OpenAI-compat /
        8192 Gemini); short-output callers (the news-flag classifier) pass a small cap."""
        if not self._key:
            return None
        try:
            self._throttle()
            text = self._complete(prompt, system=system, timeout=float(timeout),
                                  max_tokens=max_tokens)
        except Exception:
            return None
        text = (text or "").strip()
        return text or None

    def _complete(self, prompt: str, *, system: str, timeout: float,
                  max_tokens: int | None = None) -> str | None:
        raise NotImplementedError


class OpenAICompatProvider(CrewProvider):
    """Covers every provider speaking the OpenAI chat/completions dialect
    (OpenRouter, Groq, Cerebras, Z.ai)."""

    url = "?"
    extra_headers: dict = {}

    def _complete(self, prompt: str, *, system: str, timeout: float,
                  max_tokens: int | None = None) -> str | None:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": int(max_tokens) if max_tokens else 2048,
        }
        headers = {"Authorization": f"Bearer {self._key}", **self.extra_headers}
        data = _post_json(self.url, payload, headers, timeout)
        choices = data.get("choices") or []
        if not choices:
            return None
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content")
        return content if isinstance(content, str) else None


class OpenRouterProvider(OpenAICompatProvider):
    name = "openrouter"
    url = "https://openrouter.ai/api/v1/chat/completions"
    # Optional attribution headers OpenRouter asks nicely for (not required, never secret).
    extra_headers = {"X-Title": "atlas-research-crew"}


class GroqProvider(OpenAICompatProvider):
    name = "groq"
    url = "https://api.groq.com/openai/v1/chat/completions"


class CerebrasProvider(OpenAICompatProvider):
    name = "cerebras"
    url = "https://api.cerebras.ai/v1/chat/completions"


class ZaiProvider(OpenAICompatProvider):
    name = "zai"
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


class GeminiProvider(CrewProvider):
    """Google Gemini REST (generativelanguage.googleapis.com). Key travels in the
    x-goog-api-key header, never in the URL (keeps it out of any proxy/error logs)."""

    name = "gemini"

    def _complete(self, prompt: str, *, system: str, timeout: float,
                  max_tokens: int | None = None) -> str | None:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            # gemini-flash-latest is a THINKING model: thoughts bill against maxOutputTokens,
            # and 2048 starved longer replies to empty parts (live probe 2026-07-10; the full
            # crew packet can starve 4096 too) - 8192 leaves room for thinking + the JSON.
            # A caller-supplied max_tokens is honored but never below the thinking floor.
            "generationConfig": {"temperature": 0.2,
                                 "maxOutputTokens": max(int(max_tokens), 8192) if max_tokens else 8192},
        }
        data = _post_json(url, payload, {"x-goog-api-key": self._key}, timeout)
        candidates = data.get("candidates") or []
        if not candidates:
            return None
        parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        return text or None


_PROVIDER_CLASSES: dict[str, type[CrewProvider]] = {
    "openrouter": OpenRouterProvider,
    "groq": GroqProvider,
    "cerebras": CerebrasProvider,
    "gemini": GeminiProvider,
    "zai": ZaiProvider,
}


def _load_crew_section(creds_path: Path) -> dict:
    """The `crew:` mapping from credentials.local.yaml. Missing file, unparseable YAML, or
    absent/malformed section all degrade to {} - zero providers, never a crash."""
    try:
        import yaml

        raw = yaml.safe_load(creds_path.read_text("utf-8")) or {}
    except Exception:
        return {}
    section = raw.get("crew") if isinstance(raw, dict) else None
    return section if isinstance(section, dict) else {}


def load_crew_providers(creds_path: Path | str | None = None) -> dict[str, CrewProvider]:
    """Build one adapter per provider that has a non-empty `<name>_api_key` in the crew
    section. Returns {} when nothing is configured - the caller must treat that as a
    normal (empty hunt list) outcome, not an error."""
    section = _load_crew_section(Path(creds_path) if creds_path else _CREDS_PATH)
    providers: dict[str, CrewProvider] = {}
    for name, cls in _PROVIDER_CLASSES.items():
        key = section.get(f"{name}_api_key")
        if not key or not str(key).strip():
            continue
        model = str(section.get(f"{name}_model") or _DEFAULT_MODELS[name])
        providers[name] = cls(
            str(key).strip(), model=model, min_interval_s=_MIN_INTERVAL_S[name]
        )
    return providers
