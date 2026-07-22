"""Session calendar for the OPTIONS SHADOW TRADER (2026-07-09, late-close mode foundation).

The repo previously hardcoded a 16:00 ET close everywhere; nothing knew about half days
(13:00 equity / 13:15 index-ETF-options close - 2026-11-27, 2026-12-24) or NYSE holidays.
This module is the ONE source for "when does today's session end":

  * session_close_minute(d)         -> RTH close, minutes-of-day ET (960 normal, 780 half day)
  * options_close_minute(d, sym)    -> close + 15 for the late-close index ETFs
                                       (SPY/QQQ/IWM/DIA options trade to 16:15 / 13:15 - 
                                       EVERY day, which is what makes the post-close
                                       option-NBBO marking mode a daily feature)
  * is_trading_day(d)               -> False on weekends + full-holiday closures

DESIGN mirrors events.py exactly: pure query functions with an injectable `days` mapping
(tests never touch the network); fetch + cache is the only I/O and fails open at every layer - 
fresh cache (< 7 days) -> Tradier /v1/markets/calendar via an INJECTED client (the shadow's
own TradierData; ~12 calls/year) -> hardcoded 2026 fallback tables. A date missing from `days`
falls back to weekday-open-at-960 / weekend-closed, so the fetch is an UPGRADE, never a
dependency.

`days` mapping shape: {"YYYY-MM-DD": {"status": "open"|"closed", "close_min": int}} - 
exactly what atlas.collect.tradier_data.parse_calendar produces.
"""

from __future__ import annotations

import json
import time as _time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from atlas.config_loader import FRAMEWORK_ROOT
from atlas.fsutil import atomic_replace

ET = ZoneInfo("America/New_York")

OPEN_MIN = 9 * 60 + 30
CLOSE_MIN_DEFAULT = 16 * 60
HALF_DAY_CLOSE_MIN = 13 * 60
LATE_CLOSE_EXTRA_MIN = 15                 # SPY/QQQ/IWM/DIA options trade to equity close + 15

CACHE_PATH = FRAMEWORK_ROOT / "runtime" / "market_calendar.json"
CACHE_MAX_AGE_DAYS = 7.0

# NYSE published 2026 calendar (mirrored 2026-07-09). Full closures + 13:00 early closes.
# KEPT as the pinned reference the algorithmic generator below is unit-tested against.
HOLIDAYS_2026_FALLBACK: tuple[str, ...] = (
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
)
HALF_DAYS_2026_FALLBACK: dict[str, int] = {
    "2026-11-27": HALF_DAY_CLOSE_MIN,     # day after Thanksgiving
    "2026-12-24": HALF_DAY_CLOSE_MIN,     # Christmas Eve
}


# --------------------------------------------------------------------------- #
# Algorithmic NYSE calendar - ANY year (audit 2026-07-16 EVENTS-CALENDAR-1,
# opts-audit-wave3-calendar-v1): the 2026-only tables silently turned every future
# New-Year's-Day into a "trading day" at rollover. The standard NYSE rules are stable and
# computable; the generator reproduces the published 2026 tables exactly (unit-tested).
# --------------------------------------------------------------------------- #

def _easter_sunday(year: int) -> date:
    """Anonymous Gregorian computus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7          # noqa: E741 - the traditional variable name
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    off = (weekday - d.weekday()) % 7
    return date(year, month, 1 + off + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
    d = date(d.year, d.month, 1)
    from datetime import timedelta as _td
    d = d - _td(days=1)
    return d - _td(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date | None:
    """NYSE observation: Sunday -> Monday, Saturday -> preceding Friday; EXCEPT a Saturday
    New Year's Day is NOT observed (the prior Friday stays open, per NYSE rule)."""
    from datetime import timedelta as _td
    if d.weekday() == 6:
        return d + _td(days=1)
    if d.weekday() == 5:
        if d.month == 1 and d.day == 1:
            return None
        return d - _td(days=1)
    return d


def nyse_holidays(year: int) -> set[str]:
    """Full-closure dates (ISO strings) for any year under the standing NYSE rules."""
    outs: list[date | None] = [
        _observed(date(year, 1, 1)),                    # New Year's Day
        _nth_weekday(year, 1, 0, 3),                    # MLK - 3rd Monday Jan
        _nth_weekday(year, 2, 0, 3),                    # Washington's Birthday - 3rd Monday Feb
        _easter_sunday(year) - __import__("datetime").timedelta(days=2),   # Good Friday
        _last_weekday(year, 5, 0),                      # Memorial Day - last Monday May
        _observed(date(year, 6, 19)),                   # Juneteenth
        _observed(date(year, 7, 4)),                    # Independence Day
        _nth_weekday(year, 9, 0, 1),                    # Labor Day - 1st Monday Sep
        _nth_weekday(year, 11, 3, 4),                   # Thanksgiving - 4th Thursday Nov
        _observed(date(year, 12, 25)),                  # Christmas
    ]
    return {d.isoformat() for d in outs if d is not None}


def nyse_half_days(year: int) -> dict[str, int]:
    """13:00 early closes: July 3 (weekday, not itself the observed-July-4 closure), the day
    after Thanksgiving, and Christmas Eve (weekday, not itself the observed-Christmas closure)."""
    from datetime import timedelta as _td
    hols = nyse_holidays(year)
    out: dict[str, int] = {}
    j3 = date(year, 7, 3)
    if j3.weekday() < 5 and j3.isoformat() not in hols:
        out[j3.isoformat()] = HALF_DAY_CLOSE_MIN
    tgiving = _nth_weekday(year, 11, 3, 4)
    out[(tgiving + _td(days=1)).isoformat()] = HALF_DAY_CLOSE_MIN
    c24 = date(year, 12, 24)
    if c24.weekday() < 5 and c24.isoformat() not in hols:
        out[c24.isoformat()] = HALF_DAY_CLOSE_MIN
    return out


def _late_close_underlyings() -> frozenset:
    # selector owns the index-tier set; import lazily to keep this module import-light
    from atlas.options.selector import INDEX_UNDERLYINGS
    return frozenset(INDEX_UNDERLYINGS)


# --------------------------------------------------------------------------- #
# Pure queries - no I/O when `days` is injected.
# --------------------------------------------------------------------------- #

def _day_row(d: date, days: Mapping[str, Any] | None) -> dict | None:
    src = load_days() if days is None else days
    row = src.get(d.isoformat()) if src else None
    return row if isinstance(row, dict) else None


def is_trading_day(d: date, *, days: Mapping[str, Any] | None = None) -> bool:
    row = _day_row(d, days)
    if row is not None:
        return str(row.get("status", "")).lower() == "open"
    if d.weekday() >= 5:
        return False
    return d.isoformat() not in nyse_holidays(d.year)   # any-year (EVENTS-CALENDAR-1 fix)


def session_close_minute(d: date, *, days: Mapping[str, Any] | None = None) -> int:
    """RTH close for date `d` in minutes-of-day ET. Unknown open weekday -> 960 (the fetch is
    an upgrade, never a dependency); a fetched/fallback half day -> its early close."""
    row = _day_row(d, days)
    if row is not None and str(row.get("status", "")).lower() == "open":
        cm = row.get("close_min")
        try:
            cm = int(cm)
        except (TypeError, ValueError):
            cm = 0
        if OPEN_MIN < cm <= CLOSE_MIN_DEFAULT:
            return cm
        return CLOSE_MIN_DEFAULT
    return nyse_half_days(d.year).get(d.isoformat(), CLOSE_MIN_DEFAULT)


def options_close_minute(d: date, underlying: str, *, days: Mapping[str, Any] | None = None) -> int:
    """When the OPTIONS stop quoting: equity close + 15 for the late-close index ETFs
    (16:15 normal / 13:15 half days), equity close for everything else."""
    close = session_close_minute(d, days=days)
    if str(underlying or "").upper() in _late_close_underlyings():
        return close + LATE_CLOSE_EXTRA_MIN
    return close


# --------------------------------------------------------------------------- #
# Fetch + cache (the only I/O). Fail-open: no client / fetch error -> fallback tables.
# --------------------------------------------------------------------------- #

def _read_cache(path: Path = CACHE_PATH) -> dict | None:
    try:
        data = json.loads(path.read_text("utf-8"))
        if isinstance(data.get("days"), dict) and data.get("fetched_at"):
            return data
    except (OSError, ValueError):
        pass
    return None


def _write_cache_atomic(data: dict, path: Path = CACHE_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp.{int(_time.time() * 1000)}")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        atomic_replace(tmp, path)
    except OSError:
        pass  # cache is an optimization, never a failure


def _fallback_days(year: int) -> dict[str, dict]:
    """Algorithmic for ANY year (audit EVENTS-CALENDAR-1: the 2026-only mirror returned {} for
    2027, classifying New Year's Day as a trading session)."""
    out: dict[str, dict] = {}
    for iso in nyse_holidays(year):
        out[iso] = {"status": "closed"}
    for iso, cm in nyse_half_days(year).items():
        out[iso] = {"status": "open", "close_min": cm}
    return out


def refresh_calendar(client=None, force: bool = False, *, cache_path: Path = CACHE_PATH,
                     year: int | None = None) -> dict:
    """Return {"days": {...}, "source": ..., "fetched_at": ...}.

    Order: fresh cache (< CACHE_MAX_AGE_DAYS) -> Tradier fetch across the year's 12 months
    (client injected - the shadow passes its own TradierData; a fetch failure or absent client
    degrades to the hardcoded fallback tables). Cached atomically either way."""
    yr = year or datetime.now(ET).year
    cached = _read_cache(cache_path)
    if cached and not force:
        try:
            age = datetime.now(ET) - datetime.fromisoformat(cached["fetched_at"])
            if age.total_seconds() < CACHE_MAX_AGE_DAYS * 86400:
                return cached
        except (ValueError, TypeError, KeyError):
            pass
    if client is not None:
        try:
            days: dict[str, dict] = {}
            for month in range(1, 13):
                days.update(client.get_calendar(month, yr))
            if days:
                data = {"days": days, "source": "tradier",
                        "fetched_at": datetime.now(ET).isoformat()}
                _write_cache_atomic(data, cache_path)
                return data
        except Exception:  # noqa: BLE001 - fail open to the fallback tables
            pass
    data = {"days": _fallback_days(yr), "source": "fallback_nyse_2026",
            "fetched_at": datetime.now(ET).isoformat()}
    _write_cache_atomic(data, cache_path)
    return data


_DAYS_CACHE: dict | None = None


def load_days(client=None, force: bool = False) -> dict:
    """Default `days` source for the query API, memoized per process (refreshed weekly via the
    cache's own staleness rule; a restart or force=True re-reads)."""
    global _DAYS_CACHE
    if _DAYS_CACHE is None or force:
        _DAYS_CACHE = (refresh_calendar(client=client, force=force) or {}).get("days") or {}
    return _DAYS_CACHE
