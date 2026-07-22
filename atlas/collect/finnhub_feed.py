"""FinnhubNewsFeed - real company news behind the NewsFeed interface (docs/02 §2.3-2.4).

Free Finnhub tier: `/company-news` is available (the pre-scored `/news-sentiment` endpoint is
premium-only / 403, so the ANALYST scores sentiment from the headlines itself - which is the
intended design: the LLM judges, the deterministic engine never trusts the score). We poll on
demand each cycle for the handful of candidate symbols only (<= max_proposals_per_cycle), well
inside the free 60-calls/min budget. No webhook is needed - this is pull, not push.

Fail-safe: ANY error (timeout, non-200, bad JSON, missing key) returns an empty *unfetched*
bundle, so a flaky news provider degrades the `news` signal to neutral (~50) and can never block
or crash a cycle. News is a soft input, never a hard gate.

Uses only the stdlib (urllib) so no new dependency is added. The bundle is cached per
(cycle-timestamp, symbol) so the analyst pass and the later auditor pass share one fetch.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from atlas.collect.feeds import EarningsFeed, NewsBundle, NewsFeed, NewsItem

_BASE = "https://finnhub.io/api/v1/company-news"
_EARNINGS = "https://finnhub.io/api/v1/calendar/earnings"


def _clip(text: str | None, n: int) -> str:
    t = (text or "").strip().replace("\r", " ").replace("\n", " ")
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


class FinnhubNewsFeed(NewsFeed):
    def __init__(
        self,
        api_key: str,
        *,
        lookback_days: int = 7,
        max_items: int = 6,
        summary_chars: int = 240,
        timeout: float = 10.0,
    ):
        self._key = api_key
        self._lookback_days = lookback_days
        self._max_items = max_items
        self._summary_chars = summary_chars
        self._timeout = timeout
        self._cache_key: str | None = None
        self._cache: dict[str, NewsBundle] = {}

    def _fetch_raw(self, symbol: str) -> list[dict]:
        import json
        from urllib.parse import urlencode
        from urllib.request import urlopen

        today = datetime.now(timezone.utc).date()
        params = urlencode({
            "symbol": symbol,
            "from": (today - timedelta(days=self._lookback_days)).isoformat(),
            "to": today.isoformat(),
            "token": self._key,
        })
        with urlopen(f"{_BASE}?{params}", timeout=self._timeout) as resp:
            if resp.status != 200:
                raise OSError(f"finnhub HTTP {resp.status}")
            data = json.loads(resp.read().decode("utf-8"))
        return data if isinstance(data, list) else []

    def get_news(self, symbol: str, now_iso: str) -> NewsBundle:
        if self._cache_key != now_iso:        # new cycle -> drop the prior cycle's cache
            self._cache_key = now_iso
            self._cache = {}
        if symbol in self._cache:
            return self._cache[symbol]

        try:
            raw = self._fetch_raw(symbol)
        except Exception:                      # any provider failure -> degrade to neutral, never crash
            bundle = NewsBundle(symbol, (), now_iso, fetched=False)
            self._cache[symbol] = bundle
            return bundle

        rows = [r for r in raw if r.get("headline")]
        rows.sort(key=lambda r: r.get("datetime", 0), reverse=True)
        items = []
        for r in rows[: self._max_items]:
            ts = r.get("datetime", 0)
            iso = (datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                   if isinstance(ts, (int, float)) and ts > 0 else "?")
            items.append(NewsItem(
                datetime_iso=iso,
                headline=_clip(r.get("headline"), 200),
                summary=_clip(r.get("summary"), self._summary_chars),
                source=_clip(r.get("source"), 40),
                url=str(r.get("url", "")),
            ))
        bundle = NewsBundle(symbol, tuple(items), now_iso, fetched=True)
        self._cache[symbol] = bundle
        return bundle


class FinnhubEarningsFeed(EarningsFeed):
    """Nearest earnings date per symbol via the free `/calendar/earnings` endpoint, so the (until
    now inert) earnings blackout in risk_limits.yaml can actually fire. Same fail-safe + per-cycle
    cache philosophy as the news feed: any error -> None (no constraint), never a crash."""

    def __init__(
        self,
        api_key: str,
        *,
        lookback_days: int = 4,      # enough to still see an earnings that JUST happened (post-earnings vol)
        lookahead_days: int = 120,   # one quarter+, so the next report is always in range
        timeout: float = 10.0,
    ):
        self._key = api_key
        self._lookback_days = lookback_days
        self._lookahead_days = lookahead_days
        self._timeout = timeout
        self._cache_key: str | None = None
        self._cache: dict[str, int | None] = {}

    def _fetch_dates(self, symbol: str, today) -> list:
        import json
        from urllib.parse import urlencode
        from urllib.request import urlopen

        params = urlencode({
            "from": (today - timedelta(days=self._lookback_days)).isoformat(),
            "to": (today + timedelta(days=self._lookahead_days)).isoformat(),
            "symbol": symbol,
            "token": self._key,
        })
        with urlopen(f"{_EARNINGS}?{params}", timeout=self._timeout) as resp:
            if resp.status != 200:
                raise OSError(f"finnhub HTTP {resp.status}")
            data = json.loads(resp.read().decode("utf-8"))
        return (data or {}).get("earningsCalendar", []) if isinstance(data, dict) else []

    def days_to_earnings(self, symbol: str, now_iso: str) -> int | None:
        if self._cache_key != now_iso:
            self._cache_key = now_iso
            self._cache = {}
        if symbol in self._cache:
            return self._cache[symbol]

        today = datetime.now(timezone.utc).date()
        try:
            rows = self._fetch_dates(symbol, today)
            signed = []
            for r in rows:
                d = r.get("date")
                if not d:
                    continue
                signed.append((datetime.strptime(d, "%Y-%m-%d").date() - today).days)
            result = min(signed, key=abs) if signed else None
        except Exception:           # provider/parse failure -> no constraint (fail-open, like before)
            result = None
        self._cache[symbol] = result
        return result
