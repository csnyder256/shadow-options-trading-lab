# Floor Hunter research crew - free API key checklist (owner)

The overnight research crew (`scripts/research_crew.py`, ~06:15 ET) fans one public-data
packet out to free cloud LLMs and merges their votes into `runtime/hunt_list.json`.
**Every key below is optional** - the crew degrades gracefully: a missing/dead key just
means one fewer vote (zero keys = valid empty hunt list, exit 0). More providers = better
cross-model consensus; aim for at least 3.

**ToS note (applies to ALL of these):** the crew sends ONLY public-market data - symbols,
headlines, calendar events, prior-day price/volume stats. It never sends account state,
positions, orders, P&L, sizing, or ATLAS strategy internals (enforced in code at the
fan-out site). Assume **free tiers may train on inputs**; treat every byte sent as public.

Free-tier numbers below are as of **mid-2026** and drift constantly - treat them as
ballpark, and check the provider's limits page when a key suddenly starts 429ing.

---

## 1. Google Gemini (AI Studio) - RECOMMENDED (strongest free flash model)

- Sign up / create key: https://aistudio.google.com/ → "Get API key" → *Create API key*
  (any Google account; no card needed).
- Model used: `gemini-2.5-flash` (override with `gemini_model:`).
- Free tier (mid-2026): roughly **20–50 requests/day** on flash via API, ~10 RPM.
  ⚠ The old "1,500/day" figure floating around is **stale** - don't plan around it.
  The crew makes ~1 call/day, so even the reduced tier is plenty.
- YAML key: `gemini_api_key`.

## 2. OpenRouter - RECOMMENDED (one key, many `:free` models)

- Sign up / create key: https://openrouter.ai/ → sign in → https://openrouter.ai/settings/keys
  → *Create Key*.
- Model used: `deepseek/deepseek-chat-v3.1:free` by default - any `:free` variant works
  (DeepSeek / GLM / Qwen); override with `openrouter_model:` since the free pool churns.
- Free tier (mid-2026): **50 requests/day** on `:free` models; a one-time **$10 credit
  purchase** raises that to **1,000/day** - OPTIONAL, not needed for 1 call/day.
- YAML key: `openrouter_api_key`.

## 3. Groq - RECOMMENDED (fast, generous, clean tier)

- Sign up / create key: https://console.groq.com/ → *API Keys* → *Create API Key*.
- Model used: `llama-3.1-8b-instant` (override with `groq_model:`).
- Free tier (mid-2026): ~**30 RPM / 14,400 requests/day** on the instant model.
- YAML key: `groq_api_key`.

## 4. Cerebras - RECOMMENDED (big models, clean tier)

- Sign up / create key: https://cloud.cerebras.ai/ → *API Keys* → *Generate*.
- Model used: `zai-glm-4.7` (alternative: `gpt-oss-120b`; override with `cerebras_model:`).
- Free tier (mid-2026): ~**5 RPM / 1M tokens/day** - tight RPM, huge daily token budget.
  The crew's adapter self-throttles to stay under it.
- YAML key: `cerebras_api_key`.

## 5. Z.ai (Zhipu / bigmodel.cn) - OPTIONAL (GLM flash, free)

- Sign up / create key: https://open.bigmodel.cn/ → register → *API Keys* (控制台 → API 密钥)
  → create key. English UI available; phone/email signup.
- Model used: `glm-4.7-flash` (or the current free flash variant; override with `zai_model:`).
- Free tier (mid-2026): the flash-tier model is free with modest RPM; limits are posted
  on the pricing page and move around - the crew's 1 call/day is far inside any of them.
- Data note: mainland-China-hosted endpoint. Same rule as everywhere: public data only.
- YAML key: `zai_api_key`.

---

## Where the keys go

Paste into **`config/credentials.local.yaml`** (gitignored - never commit) under a new
top-level `crew:` section. Only add the lines for keys you actually created; the code
tolerates the whole section (or any key) being absent. The `*_model` overrides are
optional.

```yaml
crew:
  gemini_api_key: "AIza..."
  openrouter_api_key: "sk-or-v1-..."
  groq_api_key: "gsk_..."
  cerebras_api_key: "csk-..."
  zai_api_key: "..."
  # optional model overrides (defaults live in atlas/crew/providers.py):
  # gemini_model: "gemini-2.5-flash"
  # openrouter_model: "deepseek/deepseek-chat-v3.1:free"
  # groq_model: "llama-3.1-8b-instant"
  # cerebras_model: "zai-glm-4.7"
  # zai_model: "glm-4.7-flash"
```

## Smoke test (no market impact - writes only runtime/hunt_list.json, or nothing with --dry-run)

```powershell
$env:PYTHONPATH='.'; .venv\Scripts\python.exe scripts\research_crew.py --offline --dry-run
```

`--offline` uses a canned packet (no market-data gathering); drop it for a real run.
Each configured provider prints one line (`N candidates parsed` or `FAILED (no vote)`),
so a bad key is immediately visible.
