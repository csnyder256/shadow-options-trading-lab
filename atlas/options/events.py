"""Macro event calendar for the OPTIONS SHADOW TRADER (2026-07-09, O1).

FOMC decision datetimes are hardcoded from the Fed's published 2026 meeting calendar (decision
statement 14:00 ET on day 2, press conference 14:30 ET). CPI and Employment Situation (NFP)
release dates come from the FRED release/dates JSON API (release_id 10 = CPI, 50 = Employment
Situation) when a FRED key exists at config/credentials.local.yaml -> fred: api_key; otherwise
a hardcoded 2026 fallback table (BLS published schedule, mirrored 2026-07-09 - see the table
comments) is used. All releases at 08:30 ET. Fetched dates are cached to
runtime/econ_calendar.json (atomic write, weekly staleness refresh).

DESIGN: pure logic is separated from fetch. Every query function (`upcoming_events`,
`in_blackout`, `is_event_day`, `macro_release_active`) takes an optional injected `events`
list so tests never touch the network; only `load_events()` (the default source) does I/O,
and even that fails open to the hardcoded tables.

Blackout semantics (plan "Event layer" + hard rules):
  * [release-5min, release+15min]  -> the event kind ("cpi" / "fomc" / "nfp") - never enter.
  * [release-60min, release)       -> "pre_print" - never enter pre-print (checked after the
                                      hard window so the hard window always wins).
This module finally gives atlas.risk.blackouts' dormant `macro_release_active` flag a truthful
producer - callers pass `macro_release_active(now)` into their own BlackoutContext; nothing in
atlas/risk/* is modified here.
"""

from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from atlas.config_loader import FRAMEWORK_ROOT
from atlas.fsutil import atomic_replace

ET = ZoneInfo("America/New_York")

# --------------------------------------------------------------------------- #
# Hardcoded schedules.
# --------------------------------------------------------------------------- #

# FOMC 2026 meetings (Federal Reserve published calendar): Jan 27-28, Mar 17-18, Apr 28-29,
# Jun 16-17, Jul 28-29, Sep 15-16, Oct 27-28, Dec 8-9. Decision = 14:00 ET on day 2,
# post-meeting press conference = 14:30 ET.
FOMC_DECISION_DAYS_2026: tuple[date, ...] = (
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
)
FOMC_DECISION_TIME = time(14, 0)
FOMC_PRESSER_TIME = time(14, 30)

# BLS release-time convention: 08:30 ET for both CPI and the Employment Situation.
BLS_RELEASE_TIME = time(8, 30)

# Fallback tables - BLS published 2026 schedules, mirrored 2026-07-09.
# Source: https://www.bls.gov/schedule/news_release/cpi.htm and
# https://www.bls.gov/schedule/news_release/empsit.htm (BLS 403-blocks automated fetchers;
# cross-verified 2026-07-09 against https://www.financecalendar.com/us-cpi-report/,
# https://macroornoise.com/cpi-release-dates-2026/ and
# https://www.financecalendar.com/us-jobs-report/, which mirror the BLS tables, plus BLS's own
# empsit archive stamps empsit_05082026/empsit_06052026 and the Jul 2 / Aug 7 schedule notes).
CPI_2026_FALLBACK: tuple[str, ...] = (
    "2026-01-13", "2026-02-13", "2026-03-11", "2026-04-10", "2026-05-12", "2026-06-10",
    "2026-07-14", "2026-08-12", "2026-09-11", "2026-10-14", "2026-11-10", "2026-12-10",
)
NFP_2026_FALLBACK: tuple[str, ...] = (
    "2026-01-09", "2026-02-11", "2026-03-06", "2026-04-03", "2026-05-08", "2026-06-05",
    "2026-07-02", "2026-08-07", "2026-09-04", "2026-10-02", "2026-11-06", "2026-12-04",
)

# FRED release ids: 10 = Consumer Price Index, 50 = Employment Situation.
FRED_RELEASE_CPI = 10
FRED_RELEASE_EMPSIT = 50
FRED_DATES_URL = "https://api.stlouisfed.org/fred/release/dates"

CACHE_PATH = FRAMEWORK_ROOT / "runtime" / "econ_calendar.json"
CACHE_MAX_AGE_DAYS = 7.0

# Blackout window shape (minutes relative to the release instant).
HARD_BEFORE_MIN = 5
HARD_AFTER_MIN = 15
PRE_PRINT_BEFORE_MIN = 60


@dataclass(frozen=True)
class EconEvent:
    kind: str           # "cpi" | "nfp" | "fomc"
    ts_et: datetime     # tz-aware, America/New_York
    label: str = ""     # "decision" / "presser" for FOMC; "" for prints


# --------------------------------------------------------------------------- #
# Pure logic - no I/O anywhere below until the "fetch + cache" section.
# --------------------------------------------------------------------------- #

def build_events(cpi_dates: Iterable[str], nfp_dates: Iterable[str],
                 fomc_decision_days: Iterable[date] = FOMC_DECISION_DAYS_2026,
                 ) -> list[EconEvent]:
    """Assemble the full event list from plain date inputs (pure; test-injectable)."""
    events: list[EconEvent] = []
    for d in cpi_dates:
        events.append(EconEvent("cpi", datetime.combine(date.fromisoformat(str(d)),
                                                        BLS_RELEASE_TIME, tzinfo=ET)))
    for d in nfp_dates:
        events.append(EconEvent("nfp", datetime.combine(date.fromisoformat(str(d)),
                                                        BLS_RELEASE_TIME, tzinfo=ET)))
    for d in fomc_decision_days:
        events.append(EconEvent("fomc", datetime.combine(d, FOMC_DECISION_TIME, tzinfo=ET),
                                label="decision"))
        events.append(EconEvent("fomc", datetime.combine(d, FOMC_PRESSER_TIME, tzinfo=ET),
                                label="presser"))
    events.sort(key=lambda e: e.ts_et)
    return events


def _as_et(now: datetime) -> datetime:
    """Naive datetimes are taken as ET (the platform's market-local convention); aware ones
    are converted."""
    if now.tzinfo is None:
        return now.replace(tzinfo=ET)
    return now.astimezone(ET)


def upcoming_events(now: datetime, horizon_days: int = 7,
                    *, events: Sequence[EconEvent] | None = None) -> list[EconEvent]:
    """Events with ts_et in [now, now + horizon_days], soonest first."""
    ev = load_events() if events is None else events
    t = _as_et(now)
    end = t + timedelta(days=horizon_days)
    return sorted((e for e in ev if t <= e.ts_et <= end), key=lambda e: e.ts_et)


def in_blackout(now: datetime, *, events: Sequence[EconEvent] | None = None) -> str | None:
    """The event kind inside [release-5m, release+15m], else "pre_print" inside
    [release-60m, release), else None. Hard windows are checked across ALL events first so a
    decision's hard window is never masked by the presser's pre-window."""
    ev = load_events() if events is None else events
    t = _as_et(now)
    for e in ev:
        if e.ts_et - timedelta(minutes=HARD_BEFORE_MIN) <= t \
                <= e.ts_et + timedelta(minutes=HARD_AFTER_MIN):
            return e.kind
    for e in ev:
        if e.ts_et - timedelta(minutes=PRE_PRINT_BEFORE_MIN) <= t < e.ts_et:
            return "pre_print"
    return None


def is_event_day(d: date, *, events: Sequence[EconEvent] | None = None) -> list[str]:
    """Unique event kinds occurring on ET-date `d`, in chronological order."""
    ev = load_events() if events is None else events
    kinds: list[str] = []
    for e in sorted(ev, key=lambda x: x.ts_et):
        if e.ts_et.date() == d and e.kind not in kinds:
            kinds.append(e.kind)
    return kinds


def macro_release_active(now: datetime, *, events: Sequence[EconEvent] | None = None) -> bool:
    """True inside any blackout window (incl. pre_print) - the truthful producer for
    atlas.risk.blackouts.BlackoutContext.macro_release_active."""
    return in_blackout(now, events=events) is not None


# --------------------------------------------------------------------------- #
# Fetch + cache (the only I/O). Fail-open: FRED unreachable / key absent -> fallback tables.
# --------------------------------------------------------------------------- #

def _read_fred_key(creds_path: Path | None = None) -> str | None:
    """Tolerant read of config/credentials.local.yaml -> fred: api_key (absent -> None)."""
    p = creds_path or (FRAMEWORK_ROOT / "config" / "credentials.local.yaml")
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text("utf-8")) or {}
        key = str(((cfg.get("fred") or {}).get("api_key")) or "").strip()
        return key or None
    except Exception:
        return None


def _fetch_fred_release_dates(api_key: str, release_id: int, year: int) -> list[str]:
    """One FRED release/dates call -> ISO date strings for `year` (raises on transport/shape
    errors - the caller fails open)."""
    import httpx
    resp = httpx.get(FRED_DATES_URL, params={
        "release_id": release_id, "api_key": api_key, "file_type": "json",
        "include_release_dates_with_no_data": "true",
        "realtime_start": f"{year}-01-01", "realtime_end": f"{year}-12-31",
        "sort_order": "asc", "limit": 500,
    }, timeout=10.0)
    resp.raise_for_status()
    rows = resp.json().get("release_dates") or []
    out = sorted({str(r.get("date")) for r in rows
                  if str(r.get("date", "")).startswith(str(year))})
    if not out:
        raise ValueError(f"FRED release {release_id}: no {year} dates in response")
    return out


def _read_cache(path: Path = CACHE_PATH) -> dict | None:
    try:
        data = json.loads(path.read_text("utf-8"))
        if data.get("cpi") and data.get("nfp") and data.get("fetched_at"):
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


def refresh_calendar(force: bool = False, *, cache_path: Path = CACHE_PATH,
                     year: int | None = None) -> dict:
    """Return {"cpi": [...], "nfp": [...], "source": ..., "fetched_at": ...}.

    Order: fresh cache (< CACHE_MAX_AGE_DAYS) -> FRED fetch (key present) -> fallback tables.
    A fetch failure or an absent key degrades to the hardcoded BLS tables; the result is
    cached atomically either way (a "fallback" cache is refreshed weekly, so the first week
    with a key present upgrades it automatically)."""
    yr = year or datetime.now(ET).year
    cached = _read_cache(cache_path)
    if cached and not force:
        try:
            age = datetime.now(ET) - datetime.fromisoformat(cached["fetched_at"])
            if age.total_seconds() < CACHE_MAX_AGE_DAYS * 86400:
                return cached
        except (ValueError, TypeError, KeyError):
            pass
    key = _read_fred_key()
    if key:
        try:
            data = {"cpi": _fetch_fred_release_dates(key, FRED_RELEASE_CPI, yr),
                    "nfp": _fetch_fred_release_dates(key, FRED_RELEASE_EMPSIT, yr),
                    "source": "fred",
                    "fetched_at": datetime.now(ET).isoformat()}
            _write_cache_atomic(data, cache_path)
            return data
        except Exception:
            pass  # fail open to the fallback tables below
    data = {"cpi": list(CPI_2026_FALLBACK), "nfp": list(NFP_2026_FALLBACK),
            "source": "fallback_bls_2026", "fetched_at": datetime.now(ET).isoformat()}
    _write_cache_atomic(data, cache_path)
    return data


_EVENTS_CACHE: list[EconEvent] | None = None


def load_events(force: bool = False) -> list[EconEvent]:
    """Default event source for the query API: refresh_calendar() + hardcoded FOMC, memoized
    per process (the calendar changes ~monthly; a process restart or force=True re-reads)."""
    global _EVENTS_CACHE
    if _EVENTS_CACHE is None or force:
        cal = refresh_calendar(force=force)
        _EVENTS_CACHE = build_events(cal.get("cpi") or CPI_2026_FALLBACK,
                                     cal.get("nfp") or NFP_2026_FALLBACK)
    return _EVENTS_CACHE
