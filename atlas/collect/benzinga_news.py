"""Alpaca-Benzinga NEWS adapter (2026-07-09, floor-hunter overhaul).

The free Alpaca account includes the Benzinga real-time news feed. This module taps it two ways:

  * HISTORICAL pull (`fetch_news` / `overnight_news`) - which symbols had news since the most recent
    weekday close; feeds the research crew + catalyst tagging premarket.
  * LIVE tap (`NewsTap`) - a REST **poller** (NOT a websocket: the platform is polling-architecture
    throughout) that appends one JSON line per new headline to runtime/news_stream.jsonl so the
    in-play scanner can correlate headlines with volume spikes.

SDK decision (verified by import, not guessed): alpaca-py 0.43.4 in .venv ships
`alpaca.data.historical.news.NewsClient` (REST, paginates internally against
data.alpaca.markets/v1beta1/news) - we use it in raw mode and parse dicts defensively ourselves.
`alpaca.data.live.news.NewsDataStream` also exists but is deliberately unused in v1 (polling only).

Credentials mirror atlas/backtest/intraday_data.py `_client()`: config/credentials.local.yaml
under `alpaca:` (api_key / secret_key).

SECURITY: every headline/summary/symbol/url is UNTRUSTED EXTERNAL DATA. It is never eval'd,
exec'd, or used as a format string; stored text is length-capped and only ever serialized through
json.dumps (which escapes control characters, so the JSONL stays one physical line per record).

Fail-open contract: `fetch_news` returns [] on ANY error - news is a context feed, never a
dependency the trading loop can die on.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from atlas.fsutil import atomic_replace

ET = ZoneInfo("America/New_York")

# Storage caps for untrusted external text (applied at parse AND again at write time).
HEADLINE_MAX = 300
SUMMARY_MAX = 500
URL_MAX = 500
SOURCE_MAX = 40
SYMBOL_MAX = 12          # OCC-ish upper bound; anything longer is junk
MAX_SYMBOLS_PER_ITEM = 20
MAX_SEEN_FINGERPRINTS = 5000   # NewsTap dedup memory bound (FIFO eviction)


# --------------------------------------------------------------------------- #
# Model + pure parsers (no network) - tested offline.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class NewsItem:
    id: str
    ts: str                  # ET ISO-8601 (e.g. "2026-07-09T07:15:00-04:00")
    headline: str
    summary: str             # may be ""
    symbols: list[str]
    source: str
    url: str

    @property
    def fingerprint(self) -> str:
        """Stable dedup key: sha256 of the article id (NOT Python hash() - that's salted per run)."""
        return hashlib.sha256(str(self.id).encode("utf-8")).hexdigest()[:16]


def _clip(value: Any, max_len: int) -> str:
    """Cap untrusted text; normalize internal newlines/tabs to spaces (json would escape them
    anyway - this just keeps the stored fields grep-friendly)."""
    s = str(value if value is not None else "")
    for ch in ("\r", "\n", "\t"):
        s = s.replace(ch, " ")
    return s[:max_len]


def _parse_ts(value: Any) -> datetime | None:
    """RFC-3339/ISO timestamp -> ET-aware datetime; None when unparseable."""
    try:
        s = str(value).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ET)
    except Exception:
        return None


def _parse_article(raw: dict) -> NewsItem | None:
    """One raw v1beta1/news article dict -> NewsItem; None when it lacks an id or a usable
    timestamp (an item we can neither dedup nor cursor-track is dropped, not guessed at)."""
    try:
        art_id = raw.get("id")
        if art_id is None or str(art_id) == "":
            return None
        ts = _parse_ts(raw.get("updated_at") or raw.get("created_at"))
        if ts is None:
            return None
        syms: list[str] = []
        for s in (raw.get("symbols") or [])[:MAX_SYMBOLS_PER_ITEM]:
            if isinstance(s, str) and s.strip():
                syms.append(_clip(s.strip().upper(), SYMBOL_MAX))
        return NewsItem(
            id=str(art_id),
            ts=ts.isoformat(),
            headline=_clip(raw.get("headline"), HEADLINE_MAX),
            summary=_clip(raw.get("summary"), SUMMARY_MAX),
            symbols=syms,
            source=_clip(raw.get("source"), SOURCE_MAX),
            url=_clip(raw.get("url"), URL_MAX),
        )
    except Exception:
        return None


def _to_record(item: NewsItem) -> dict:
    """JSONL record for runtime/news_stream.jsonl. Caps re-applied at write time so the file
    invariant holds even if a NewsItem was constructed outside _parse_article."""
    return {
        "id": str(item.id),
        "ts": _clip(item.ts, 64),
        "headline": _clip(item.headline, HEADLINE_MAX),
        "summary": _clip(item.summary, SUMMARY_MAX),
        "symbols": [_clip(s, SYMBOL_MAX) for s in list(item.symbols)[:MAX_SYMBOLS_PER_ITEM]],
        "source": _clip(item.source, SOURCE_MAX),
        "url": _clip(item.url, URL_MAX),
        "fingerprint": item.fingerprint,
    }


def last_weekday_close(now_et: datetime) -> datetime:
    """Most recent weekday 16:00 ET strictly before `now_et`'s date: Tue 06:00 -> Mon 16:00,
    Mon 06:00 -> FRIDAY 16:00, Sat/Sun -> Friday 16:00 (walk back over the weekend)."""
    d = now_et.date() - timedelta(days=1)
    while d.weekday() >= 5:                     # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return datetime(d.year, d.month, d.day, 16, 0, tzinfo=ET)


# --------------------------------------------------------------------------- #
# REST pulls (SDK NewsClient in raw mode; SDK paginates internally).
# --------------------------------------------------------------------------- #

def _client():
    """Mirror of atlas/backtest/intraday_data._client, but for the news endpoint."""
    from alpaca.data.historical.news import NewsClient
    import yaml

    from atlas.config_loader import FRAMEWORK_ROOT
    creds = yaml.safe_load(
        (FRAMEWORK_ROOT / "config" / "credentials.local.yaml").read_text("utf-8"))["alpaca"]
    return NewsClient(creds["api_key"], creds["secret_key"], raw_data=True)


def _as_utc(dt: datetime) -> datetime:
    """Naive datetimes are treated as ET (platform convention), then sent as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(timezone.utc)


def fetch_news(symbols: list[str] | None, start: datetime, end: datetime, *,
               limit: int = 200) -> list[NewsItem]:
    """Historical Benzinga pull over [start, end], oldest-first, paginated by the SDK up to
    `limit` total items, deduped by fingerprint, sorted by ts. FAIL-OPEN: any error -> []."""
    try:
        from alpaca.data.requests import NewsRequest
        sym_param = None
        if symbols:
            sym_param = ",".join(s.strip().upper() for s in symbols if s and s.strip()) or None
        req = NewsRequest(
            start=_as_utc(start), end=_as_utc(end), symbols=sym_param,
            limit=int(limit), sort="asc",
        )
        raw = _client().get_news(req)
        articles = raw.get("news", []) if isinstance(raw, dict) else []
    except Exception:
        return []
    items: list[NewsItem] = []
    seen: set[str] = set()
    for a in articles:
        it = _parse_article(a) if isinstance(a, dict) else None
        if it is None or it.fingerprint in seen:
            continue
        seen.add(it.fingerprint)
        items.append(it)
    items.sort(key=lambda i: i.ts)
    return items


def overnight_news(now_et: datetime) -> list[NewsItem]:
    """All-symbols news from the most recent weekday close (16:00 ET, weekend-aware) to now.
    Deduped + ts-sorted. Feeds premarket research + catalyst tagging."""
    if now_et.tzinfo is None:
        now_et = now_et.replace(tzinfo=ET)
    start = last_weekday_close(now_et)
    items = fetch_news(None, start, now_et, limit=1000)
    out: list[NewsItem] = []
    seen: set[str] = set()
    for it in items:
        if it.fingerprint in seen:
            continue
        seen.add(it.fingerprint)
        out.append(it)
    out.sort(key=lambda i: i.ts)
    return out


# --------------------------------------------------------------------------- #
# LIVE tap - REST poller with a `since` cursor (v1; NewsDataStream deliberately unused).
# --------------------------------------------------------------------------- #

def _append_jsonl(items: list[NewsItem], path) -> int:
    """Append one JSON line per item (mirrors atlas/shadow/early_wave.append_records:
    single writer, plain append-mode, fsync'd)."""
    if not items:
        return 0
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(_to_record(it), separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return len(items)


def _write_heartbeat(path, payload: dict) -> None:
    """Best-effort atomic heartbeat (tmp + atomic_replace - Windows-safe vs. hub/watcher readers).
    The tap must never die on a heartbeat failure."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        atomic_replace(tmp, p)
    except Exception:
        pass


class NewsTap:
    """Polls the news REST endpoint every N seconds with a `since` cursor = last seen item ts.

    Cursor rules:
      * starts `since_hours` back from now;
      * each poll queries [cursor - overlap, now] (overlap guards equal-timestamp misses;
        fingerprint dedup absorbs the resulting repeats);
      * advances only on SEEN items - a failed poll (fetch_news fail-open -> []) never skips
        the window forward, and `sort=asc` + limit means a burst is caught up oldest-first
        across successive polls.
    """

    def __init__(self, *, since_hours: float = 1.0, poll_limit: int = 200,
                 overlap_seconds: float = 120.0,
                 fetch: Callable[..., list[NewsItem]] | None = None,
                 now_fn: Callable[[], datetime] | None = None):
        self._fetch = fetch or fetch_news
        self._now = now_fn or (lambda: datetime.now(ET))
        self.poll_limit = int(poll_limit)
        self.overlap = timedelta(seconds=max(0.0, float(overlap_seconds)))
        self.cursor: datetime = self._now() - timedelta(hours=max(0.0, float(since_hours)))
        self._seen: set[str] = set()
        self._seen_order: deque[str] = deque()
        self.polls = 0
        self.appended_total = 0

    def _remember(self, fp: str) -> None:
        if fp in self._seen:
            return
        self._seen.add(fp)
        self._seen_order.append(fp)
        while len(self._seen_order) > MAX_SEEN_FINGERPRINTS:
            self._seen.discard(self._seen_order.popleft())

    def poll_once(self, out_path, heartbeat_path=None) -> int:
        """One poll: fetch since cursor, append the unseen items as JSONL, advance the cursor,
        heartbeat. Returns the number of NEW items appended."""
        now = self._now()
        items = self._fetch(None, self.cursor - self.overlap, now, limit=self.poll_limit)
        fresh = [it for it in items if it.fingerprint not in self._seen]
        n = _append_jsonl(fresh, out_path)
        latest = self.cursor
        for it in fresh:
            self._remember(it.fingerprint)
            ts = _parse_ts(it.ts)
            if ts is not None and ts > latest:
                latest = ts
        self.cursor = latest
        self.polls += 1
        self.appended_total += n
        if heartbeat_path is not None:
            _write_heartbeat(heartbeat_path, {
                "ts": now.isoformat(), "cursor": self.cursor.isoformat(),
                "polls": self.polls, "new_items": n, "appended_total": self.appended_total,
            })
        return n

    def run_forever(self, out_path, poll_seconds: float = 30.0, heartbeat_path=None) -> None:
        """Poll until KeyboardInterrupt (clean exit). Per-loop errors are contained - a poller
        that dies silently is worse than one that logs and retries next tick."""
        try:
            while True:
                try:
                    self.poll_once(out_path, heartbeat_path=heartbeat_path)
                except Exception as exc:                      # noqa: BLE001 - poller survives
                    # repr() of the exception only - external text is never format-strung.
                    print("news_tap: poll error:", repr(exc))
                time.sleep(max(1.0, float(poll_seconds)))
        except KeyboardInterrupt:
            return
