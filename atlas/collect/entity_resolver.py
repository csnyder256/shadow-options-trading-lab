"""Company-name -> ticker resolver (2026-07-03, ATLAS-native port of Sentinel's matching tiers).

Government contract announcements name LEGAL ENTITIES ("Raytheon Co., Waltham, Massachusetts"),
not tickers. This resolver seeds from the SEC's free, no-auth company_tickers.json (every EDGAR
registrant with a listed ticker, refreshed daily by the SEC) and answers with HIGH-CONFIDENCE
matches only - an ambiguous or weak match returns None, because a WRONG-but-real ticker is the
worst failure mode (it would pass the downstream quote-verification gate and attach a catalyst to
an innocent stock). USER DIRECTIVE: don't depend on the Sentinel platform being up - this is the
lean in-process equivalent of its entity master (exact-normalized tier + alias overlay; no fuzzy).

Normalization: uppercase, strip punctuation, drop legal suffixes (CORP/INC/CO/LLC/LTD/PLC/LP/SA/AG/
NV/HOLDINGS/GROUP/COMPANY/TECHNOLOGIES/INTERNATIONAL...) iteratively from the tail, collapse
whitespace. Two different SEC entities normalizing to the same key = AMBIGUOUS = unresolvable
(dropped at build time; correctness over recall). The alias overlay (config/entity_aliases.yaml,
optional) wins over everything - the operator's curated truth for chronic misses ("GD" for
"GENERAL DYNAMICS LAND SYSTEMS" etc.).

The cache file (runtime/sec_company_tickers.json) is refreshed at most once per day; on any fetch
failure the last-good cache is used, and with no cache at all the resolver simply resolves nothing
(callers treat None as "no ticker" - fail-quiet, never fail-loud, per the CatalystFeed philosophy).
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

import yaml

SEC_URL = "https://www.sec.gov/files/company_tickers.json"
_UA = "ATLAS-research/1.0 (contact: you@example.com)"   # SEC fair-use requires a UA
_CACHE_TTL_SECONDS = 20 * 3600

# Legal/structural suffixes stripped ITERATIVELY from the tail of a normalized name.
_SUFFIXES = (
    "CORPORATION", "INCORPORATED", "COMPANY", "CORP", "INC", "LLC", "LTD", "PLC", "CO", "LP",
    "SA", "AG", "NV", "SE", "AB", "OYJ", "HOLDINGS", "HOLDING", "GROUP", "TECHNOLOGIES",
    "TECHNOLOGY", "INTERNATIONAL", "INDUSTRIES", "ENTERPRISES", "SYSTEMS", "SOLUTIONS",
    "SERVICES", "USA", "US",
)
_PUNCT = re.compile(r"[^A-Z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Uppercase, de-punctuate, iteratively strip trailing legal suffixes, collapse whitespace."""
    s = _WS.sub(" ", _PUNCT.sub(" ", (name or "").upper())).strip()
    changed = True
    while changed and s:
        changed = False
        for suf in _SUFFIXES:
            if s.endswith(" " + suf):
                s = s[: -len(suf) - 1].rstrip()
                changed = True
    return s


class EntityResolver:
    """name -> ticker, high-confidence only. Build once per session (seed + aliases), then resolve()."""

    def __init__(self, name_to_ticker: dict[str, str], aliases: dict[str, str]):
        self._map = dict(name_to_ticker)
        self._aliases = {normalize_name(k): v.upper() for k, v in (aliases or {}).items()}

    def resolve(self, company_name: str) -> str | None:
        """The ticker for a legal-entity name, or None (unknown OR ambiguous - never a guess)."""
        key = normalize_name(company_name)
        if not key:
            return None
        if key in self._aliases:
            return self._aliases[key]
        return self._map.get(key)

    def __len__(self) -> int:
        return len(self._map)

    # ---- construction -------------------------------------------------------
    @classmethod
    def from_seed(cls, seed: dict, aliases: dict[str, str] | None = None) -> "EntityResolver":
        """Build from the SEC company_tickers.json shape: {"0": {"cik_str":..., "ticker": "AAPL",
        "title": "Apple Inc."}, ...}. A normalized name claimed by 2+ DIFFERENT tickers is AMBIGUOUS
        and dropped (correctness over recall). Multi-class listings of the SAME company (GOOG/GOOGL
        share a title) keep the FIRST ticker - SEC orders by market cap, so the primary class wins."""
        name_to_ticker: dict[str, str] = {}
        ambiguous: set[str] = set()
        for row in (seed or {}).values():
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").upper()
            key = normalize_name(str(row.get("title") or ""))
            if not ticker or not key or key in ambiguous:
                continue
            existing = name_to_ticker.get(key)
            if existing is None:
                name_to_ticker[key] = ticker
            else:
                # Multi-class listings of one issuer (GOOG/GOOGL, BRK.A/BRK.B) share a root after
                # dropping a class suffix; if the roots don't nest, it's a genuine name collision.
                ra = re.sub(r"[.\-][A-Z]$", "", existing)
                rb = re.sub(r"[.\-][A-Z]$", "", ticker)
                if existing != ticker and not (ra.startswith(rb) or rb.startswith(ra)):
                    # Same normalized name, genuinely different issuers -> unresolvable.
                    ambiguous.add(key)
                    name_to_ticker.pop(key, None)
        return cls(name_to_ticker, aliases or {})

    @classmethod
    def from_cache_or_fetch(cls, *, cache_path: Path | str = "runtime/sec_company_tickers.json",
                            aliases_path: Path | str = "config/entity_aliases.yaml",
                            fetch: bool = True) -> "EntityResolver":
        """Daily-cached SEC seed + optional operator alias overlay. Any failure degrades to the
        last-good cache; no cache at all -> an EMPTY resolver (resolves nothing, raises nothing)."""
        cache = Path(cache_path)
        seed: dict = {}
        fresh = cache.exists() and (time.time() - cache.stat().st_mtime) < _CACHE_TTL_SECONDS
        if fetch and not fresh:
            try:
                req = urllib.request.Request(SEC_URL, headers={"User-Agent": _UA})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read()
                json.loads(raw)                      # validate before persisting
                cache.parent.mkdir(parents=True, exist_ok=True)
                tmp = cache.with_name(cache.name + ".tmp")
                tmp.write_bytes(raw)
                from atlas.fsutil import atomic_replace
                atomic_replace(tmp, cache)
            except Exception:  # noqa: BLE001 - fetch failure -> last-good cache below
                pass
        try:
            seed = json.loads(cache.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            seed = {}
        aliases: dict[str, str] = {}
        try:
            aliases = dict(yaml.safe_load(Path(aliases_path).read_text("utf-8")) or {})
        except OSError:
            pass
        return cls.from_seed(seed, aliases)
