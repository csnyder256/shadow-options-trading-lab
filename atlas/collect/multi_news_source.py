"""Multi-source LIVE news adapters + cross-source dedup for the options news tap
(mission 20260712 news-sources-and-dead-code-audit, design E3).

The Benzinga tap (scripts/news_tap.py -> benzinga_news.NewsTap) is macro-BLIND: its only feed is
the Alpaca-bundled Benzinga single-name corporate wire. This module ADDS Finnhub (general market /
world + per-symbol company) and GDELT (global / geopolitical) WITHOUT modifying NewsTap: NewsTap
already accepts a `fetch` callable (benzinga_news.NewsTap.__init__ fetch=...), so `build_multi_fetch`
returns a `MultiNewsFetcher` whose __call__ matches `fetch(symbols, start, end, *, limit)`. NewsTap
inherits cursor / overlap / fingerprint dedup / single-writer append / heartbeat / caps unchanged.

Design rules (ledger E3):
- FAIL-OPEN per source: any error -> [] for THAT source; never raises, never starves siblings.
- Provider-prefixed ids for the NEW sources only ("finnhub:<id>", "gdelt:<sha>") so
  NewsItem.fingerprint (sha256(id)) can't collide across providers. Benzinga ids/fingerprints are
  LEFT UNCHANGED (no schema break, no test break, no data discontinuity).
- MACRO = a ticker-less item carries symbols == [] (NO sentinel ticker). The consumer routes
  empty-symbol rows to its own macro sink; they never enter the per-symbol classifier. Observe-first.
- CROSS-source content dedup (normalized lede + 5-min ts bucket) drops the SAME story reported by a
  DIFFERENT provider; it NEVER drops a distinct same-source item (so the Benzinga path is unharmed).
- Per-source cadence + 429 backoff + a sidecar heartbeat (runtime/news_sources_heartbeat.json) so a
  silently-zero source is VISIBLE (the 2026-07-12 silent-feed incident).
- Untrusted external text: length-capped via _clip, never format-strung, only json.dumps'd
  (inherited from benzinga_news._to_record / _append_jsonl).
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from atlas.collect.benzinga_news import (
    ET,
    HEADLINE_MAX,
    MAX_SYMBOLS_PER_ITEM,
    SUMMARY_MAX,
    SYMBOL_MAX,
    URL_MAX,
    NewsItem,
    _clip,
    fetch_news,
)
from atlas.fsutil import atomic_replace

UA = "atlas-news-tap/1.0 (research collector; contact via repo owner)"

FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"           # ?category=general -> macro/world
FINNHUB_COMPANY_URL = "https://finnhub.io/api/v1/company-news"  # ?symbol=&from=&to=

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
# Versioned macro/geopolitical query (tunable constant, reviewed against per-source counts).
# GDELT DOC has NO "give me everything" mode - a non-empty query is required.
DEFAULT_GDELT_QUERY = (
    '(war OR sanctions OR tariff OR OPEC OR "interest rate" OR "central bank" OR inflation '
    'OR "Federal Reserve" OR geopolitical OR "oil price" OR conflict OR "strait of hormuz" '
    'OR "supply chain" OR recession)'
)

# Per-source poll cadence (Benzinga is polled every NewsTap tick ~10s; the others are throttled
# here because they are rate-limited - GDELT 429s a cold single request, Finnhub free tier 60/min).
FINNHUB_EVERY_S = 60.0
GDELT_EVERY_S = 90.0
SOURCE_OVERLAP_S = 120.0           # per-source window overlap; cross-source dedup absorbs repeats
BACKOFF_MAX = 8                    # cap on the consecutive-failure exponent

_KNOWN_SOURCES = ("benzinga", "finnhub", "gdelt")


# --------------------------------------------------------------------------- #
# HTTP (stdlib only - no new dependency; mirrors finnhub_feed._fetch_raw idiom)
# --------------------------------------------------------------------------- #

def _fetch_json(url: str, timeout: float = 12.0) -> tuple[int | None, Any, str | None]:
    """GET -> (http_status, parsed_json_or_None, error_or_None). NEVER raises (fail-open)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            body = resp.read().decode("utf-8", errors="replace")
        return status, json.loads(body), None
    except urllib.error.HTTPError as exc:                     # 4xx/5xx incl. 429
        return int(exc.code), None, f"http {exc.code}"
    except Exception as exc:                                   # noqa: BLE001 - timeout/DNS/bad JSON
        return None, None, repr(exc)


# --------------------------------------------------------------------------- #
# Parsers (pure; tested offline via a monkeypatched _fetch_json)
# --------------------------------------------------------------------------- #

def _finnhub_item(raw: dict, symbols: list[str]) -> NewsItem | None:
    """One Finnhub article dict -> NewsItem, or None if it isn't a dict / lacks an id/timestamp.
    The isinstance guard MUST come first: a list element that is null/int/str would otherwise make
    `raw.get(...)` raise and (per the fail-open contract) it must not - it must drop that one row."""
    if not isinstance(raw, dict):
        return None
    art_id = raw.get("id")
    if art_id in (None, ""):
        return None
    ts = raw.get("datetime")
    if not isinstance(ts, (int, float)) or ts <= 0:
        return None
    dt = datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone(ET)
    syms = [_clip(s, SYMBOL_MAX) for s in symbols if s][:MAX_SYMBOLS_PER_ITEM]
    return NewsItem(
        id=f"finnhub:{art_id}",                               # provider-prefixed -> no cross-source collision
        ts=dt.isoformat(),
        headline=_clip(raw.get("headline"), HEADLINE_MAX),
        summary=_clip(raw.get("summary"), SUMMARY_MAX),
        symbols=syms,
        source="finnhub",
        url=_clip(raw.get("url"), URL_MAX),
    )


def _parse_gdelt_ts(value: Any) -> datetime | None:
    """GDELT seendate 'YYYYMMDDTHHMMSSZ' (UTC) -> ET-aware datetime; None when unparseable."""
    s = str(value or "").strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).astimezone(ET)
        except ValueError:
            continue
    return None


def _gdelt_item(raw: dict) -> NewsItem | None:
    """One GDELT ArtList article dict -> macro NewsItem (symbols == []), or None."""
    if not isinstance(raw, dict):
        return None
    url = str(raw.get("url") or "").strip()
    if not url:
        return None                                           # url is GDELT's only stable unique key
    dt = _parse_gdelt_ts(raw.get("seendate"))
    if dt is None:
        return None
    art_id = "gdelt:" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    return NewsItem(
        id=art_id,
        ts=dt.isoformat(),
        headline=_clip(raw.get("title"), HEADLINE_MAX),
        summary="",                                           # GDELT ArtList carries no body
        symbols=[],                                           # MACRO: ticker-less by construction
        source="gdelt",
        url=_clip(url, URL_MAX),
    )


# --------------------------------------------------------------------------- #
# Adapters - each returns (items, http_status, error); each is FAIL-OPEN.
# --------------------------------------------------------------------------- #

def fetch_finnhub_general(api_key: str, *, limit: int = 100, timeout: float = 12.0):
    """Finnhub /news?category=general -> macro/world headlines (symbols == [])."""
    if not api_key:
        return [], None, "no_key"
    url = f"{FINNHUB_NEWS_URL}?" + urlencode({"category": "general", "token": api_key})
    status, data, err = _fetch_json(url, timeout)
    if data is None:
        return [], status, err
    rows = data if isinstance(data, list) else []
    items = [it for it in (_finnhub_item(r, []) for r in rows[:limit]) if it is not None]
    return items, status, None


def fetch_finnhub_company(api_key: str, symbols: list[str], since: datetime, until: datetime,
                          *, per_symbol_limit: int = 50, timeout: float = 12.0):
    """Finnhub /company-news for each symbol -> per-symbol NewsItems (symbols == [SYM])."""
    if not api_key or not symbols:
        return [], None, ("no_key" if not api_key else None)
    frm = since.astimezone(timezone.utc).date().isoformat()
    to = until.astimezone(timezone.utc).date().isoformat()
    out: list[NewsItem] = []
    last_status: int | None = None
    first_err: str | None = None
    for sym in symbols:
        url = f"{FINNHUB_COMPANY_URL}?" + urlencode(
            {"symbol": sym, "from": frm, "to": to, "token": api_key})
        status, data, err = _fetch_json(url, timeout)
        last_status = status if status is not None else last_status
        if err and first_err is None:
            first_err = err
        rows = data if isinstance(data, list) else []
        for r in rows[:per_symbol_limit]:
            it = _finnhub_item(r, [sym])
            if it is not None:
                out.append(it)
    return out, last_status, first_err


def fetch_gdelt(query: str, since: datetime, until: datetime,
                *, limit: int = 75, timeout: float = 15.0):
    """GDELT DOC 2.1 ArtList over [since, until] -> macro NewsItems (symbols == [])."""
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "sort": "DateDesc",
        "maxrecords": int(limit),
        "startdatetime": since.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "enddatetime": until.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S"),
    }
    url = f"{GDELT_URL}?" + urlencode(params)
    status, data, err = _fetch_json(url, timeout)
    if not isinstance(data, dict):
        return [], status, (err or "non_dict_response")
    arts = data.get("articles", []) if isinstance(data.get("articles"), list) else []
    items = [it for it in (_gdelt_item(a) for a in arts) if it is not None]
    return items, status, None


# --------------------------------------------------------------------------- #
# Cross-source content dedup
# --------------------------------------------------------------------------- #

def _normalize_headline(headline: Any, words: int = 8) -> str:
    """Lowercase, strip non-alphanumerics to spaces, keep the first `words` tokens (the wire lede
    most syndicated stories front-load). Deterministic; no I/O."""
    s = str(headline or "").lower()
    toks = "".join(c if c.isalnum() else " " for c in s).split()
    return " ".join(toks[:words])


def _ts_epoch(ts_iso: Any) -> float:
    try:
        return datetime.fromisoformat(str(ts_iso)).timestamp()
    except (ValueError, TypeError):
        return 0.0


class CrossSourceDedup:
    """Drops the SAME story reported by a DIFFERENT provider, keyed on (5-min ts bucket, normalized
    lede, symbol-set). Deliberately NEVER drops a distinct SAME-source item that merely shares a lede
    (templated corporate wires do this constantly) - so the proven Benzinga path is never suppressed.
    Bounded FIFO, mirroring benzinga_news.NewsTap._seen_order eviction."""

    def __init__(self, maxlen: int = 8000):
        self._owner: dict[str, str] = {}      # content_key -> first source that reported it
        self._order: deque[str] = deque()
        self._max = int(maxlen)

    def _key(self, item: NewsItem) -> str:
        bucket = int(_ts_epoch(item.ts) // 300)
        syms = ",".join(sorted(item.symbols)) if item.symbols else "__macro__"
        return f"{bucket}|{_normalize_headline(item.headline)}|{syms}"

    def admit(self, item: NewsItem) -> bool:
        key = self._key(item)
        owner = self._owner.get(key)
        if owner is not None:
            return owner == item.source       # same-source repeat -> admit; other source -> drop
        self._owner[key] = item.source
        self._order.append(key)
        while len(self._order) > self._max:
            self._owner.pop(self._order.popleft(), None)
        return True


# --------------------------------------------------------------------------- #
# The fetch seam NewsTap consumes
# --------------------------------------------------------------------------- #

class MultiNewsFetcher:
    """Callable matching benzinga_news.NewsTap's `fetch(symbols, start, end, *, limit)` seam.
    Merges the enabled sources (Benzinga every tick; Finnhub/GDELT on their own cadence with
    backoff), applies cross-source dedup, records per-source health, and writes a sidecar heartbeat.
    NewsTap still owns the canonical single-writer append + its own fingerprint dedup + cursor."""

    def __init__(self, *, sources, api_key: str | None = None, company_symbols=(),
                 gdelt_query: str = DEFAULT_GDELT_QUERY,
                 finnhub_every_s: float = FINNHUB_EVERY_S, gdelt_every_s: float = GDELT_EVERY_S,
                 benzinga_fetch: Callable[..., list[NewsItem]] | None = None,
                 heartbeat_path: str | Path | None = None,
                 now_fn: Callable[[], datetime] | None = None):
        self.sources = {s.strip().lower() for s in sources if s and s.strip()}
        self._api_key = api_key or ""
        self._company = [str(s).strip().upper() for s in company_symbols if str(s).strip()]
        self._gdelt_query = gdelt_query
        self._every = {"finnhub": float(finnhub_every_s), "gdelt": float(gdelt_every_s)}
        self._benzinga = benzinga_fetch or fetch_news
        self._hb = Path(heartbeat_path) if heartbeat_path else None
        self._now = now_fn or (lambda: datetime.now(ET))
        self._dedup = CrossSourceDedup()
        start = self._now()
        self._last_poll = {"finnhub": 0.0, "gdelt": 0.0}
        self._cursor = {"finnhub": start - timedelta(hours=1),
                        "gdelt": start - timedelta(hours=1)}
        self._fail = {s: 0 for s in self.sources}      # every enabled source (incl. benzinga)
        self._health: dict[str, dict] = {}

    def _due(self, src: str, now: datetime) -> bool:
        """Cadence gate with exponential backoff on consecutive failures."""
        base = self._every[src]
        wait = base * (2 ** min(self._fail[src], BACKOFF_MAX)) if self._fail[src] else base
        return (now.timestamp() - self._last_poll[src]) >= wait

    def _record(self, src: str, items, status, err, now: datetime) -> None:
        prior = self._health.get(src, {})
        zero = int(prior.get("consecutive_zero", 0))
        zero = 0 if items else zero + 1
        if err is None:
            self._fail[src] = 0
            last_ok = round(now.timestamp(), 3)
        else:
            self._fail[src] += 1
            last_ok = prior.get("last_ok_epoch")
        self._health[src] = {
            "items_last_poll": len(items),
            "consecutive_zero": zero,
            "consecutive_failures": self._fail[src],
            "http_status": status,
            "last_error": err,
            "last_ok_epoch": last_ok,
            "cursor": self._cursor.get(src).isoformat() if src in self._cursor else None,
        }

    def _run_windowed(self, src: str, fetch: Callable[[datetime, datetime], tuple], now: datetime):
        """Run a since-cursor'd source; advance its OWN cursor only on success."""
        since = self._cursor[src] - timedelta(seconds=SOURCE_OVERLAP_S)
        try:
            items, status, err = fetch(since, now)
        except Exception as exc:                              # noqa: BLE001 - isolate wrapper bugs too
            items, status, err = [], None, repr(exc)
        self._last_poll[src] = now.timestamp()
        if err is None:
            self._cursor[src] = now
        self._record(src, items, status, err, now)
        return items

    def __call__(self, symbols, start, end, *, limit: int = 200) -> list[NewsItem]:
        now = self._now()
        merged: list[NewsItem] = []

        if "benzinga" in self.sources:
            try:
                bz = self._benzinga(None, start, end, limit=limit)
                bz_err = None
            except Exception as exc:                          # noqa: BLE001 - never let one source kill the tick
                bz, bz_err = [], repr(exc)
            # http_status stays None (the alpaca SDK doesn't expose it) - honest "unknown" beats a fake 200
            self._record("benzinga", bz, None, bz_err, now)
            merged.extend(bz)

        if "finnhub" in self.sources and self._due("finnhub", now):
            def _fh(since, until):
                gen_items, gstatus, gerr = fetch_finnhub_general(self._api_key, limit=limit)
                co_items, cstatus, cerr = fetch_finnhub_company(
                    self._api_key, self._company, since, until, per_symbol_limit=50)
                return gen_items + co_items, (cstatus or gstatus), (gerr or cerr)
            merged.extend(self._run_windowed("finnhub", _fh, now))

        if "gdelt" in self.sources and self._due("gdelt", now):
            merged.extend(self._run_windowed(
                "gdelt", lambda since, until: fetch_gdelt(self._gdelt_query, since, until), now))

        out = [it for it in merged if self._dedup.admit(it)]
        self._write_heartbeat(now)
        return out

    def _write_heartbeat(self, now: datetime) -> None:
        if self._hb is None:
            return
        payload = {
            "schema": 2,
            "ts_epoch": round(now.timestamp(), 3),
            "sources": self._health,
            "enabled": sorted(self.sources),
        }
        try:
            self._hb.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._hb.with_name(self._hb.name + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            atomic_replace(tmp, self._hb)
        except OSError:
            pass


def build_multi_fetch(sources, **kwargs) -> Callable[..., list[NewsItem]]:
    """Return the `fetch` callable for NewsTap. If sources is exactly ['benzinga'] the live
    Benzinga path is returned BYTE-IDENTICAL to today (fetch_news itself) - the regression gate."""
    srcs = [s.strip().lower() for s in sources if s and s.strip()]
    if srcs == ["benzinga"]:
        return fetch_news
    return MultiNewsFetcher(sources=srcs, **kwargs)
