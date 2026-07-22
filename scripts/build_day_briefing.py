"""Premarket DAY BRIEFING compiler for the OPTIONS SHADOW TRADER (2026-07-09).

  PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\build_day_briefing.py [--out PATH]
                                                    [--date YYYY-MM-DD] [--skip-crew]

Runs premarket (after the overnight research crew, which it can invoke itself) and compiles
everything a shadow runner needs to READ at open into ONE deterministic artifact,
runtime/day_briefing.json (atomic write):

  * session shape - trading_day / session_close_min / half_day  [session_calendar]
  * macro events - events_today + next_events within 7 days   [options.events]
  * calendar structure - opex (3rd Friday), witching (3rd Friday of Mar/Jun/Sep/Dec),
                         month_end / quarter_end (last WEEKDAY of the month/quarter - 
                         weekday-based on purpose; a holiday landing on that weekday shifts
                         the true last trading day earlier and is tolerated)
  * hunt list - the crew's candidates enriched with signed days-to-earnings
                         (Finnhub, fail-open to None) + an abs(days)<=1 earnings_flag
  * prior scorecard - a per-lane digest of runtime/options_shadow_scorecard.json
  * vix - always null for now (enrichment lands later; the field exists so
                         consumers can bind to a stable schema today)

DESIGN mirrors events.py / session_calendar.py: `build_briefing()` is PURE - everything
(events, days, hunt rows, earnings lookup, scorecard) is injected so tests never touch the
network or disk, and every section fails open (null/[] + a "notes" entry naming the degraded
section) rather than raising. Only main() does I/O, each real source is wrapped fail-open,
and the process ALWAYS exits 0 - a missing key or empty runtime/ must never break a
premarket launch. The research crew subprocess (unless --skip-crew) is tolerated failing
silently for the same reason: it degrades by design without API keys.
"""

from __future__ import annotations

import argparse
import calendar
import json
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:                      # allow running without PYTHONPATH=.
    sys.path.insert(0, str(_ROOT))

from atlas.config_loader import FRAMEWORK_ROOT      # noqa: E402  (path bootstrap above)
from atlas.fsutil import atomic_replace             # noqa: E402
from atlas.options.events import ET, is_event_day, upcoming_events  # noqa: E402
from atlas.options.session_calendar import (        # noqa: E402
    is_trading_day,
    session_close_minute,
)

RUNTIME = FRAMEWORK_ROOT / "runtime"
DEFAULT_OUT = RUNTIME / "day_briefing.json"
HUNT_LIST_PATH = RUNTIME / "hunt_list.json"
SCORECARD_PATH = RUNTIME / "options_shadow_scorecard.json"
CREDS_PATH = FRAMEWORK_ROOT / "config" / "credentials.local.yaml"
CREW_SCRIPT = FRAMEWORK_ROOT / "scripts" / "research_crew.py"
# 300 -> 600 (audit 2026-07-16 PREMARKET-CREW-2, opts-audit-wave1-funnel-v1): the crew's
# worst case (gather ~135-150s + up to 5 SEQUENTIAL 90s provider calls ~= 585s) exceeded the
# old kill window - a timeout KILLS the child before its atomic hunt-list write, silently
# leaving YESTERDAY'S artifact for the whole session (the freshness contract now also makes
# that failure loud instead of silent).
CREW_TIMEOUT_S = 600.0

FULL_DAY_CLOSE_MIN = 960                            # 16:00 ET; anything earlier = half day
EARNINGS_FLAG_WINDOW_DAYS = 1                       # abs(days_to_earnings) <= 1 -> in play
NEXT_EVENTS_HORIZON_DAYS = 7


# --------------------------------------------------------------------------- #
# Pure calendar-structure helpers (no I/O, fully deterministic).
# --------------------------------------------------------------------------- #

def is_opex(d: date) -> bool:
    """Monthly options expiration: the 3rd Friday of the month (days 15-21)."""
    return d.weekday() == 4 and 15 <= d.day <= 21


def is_witching(d: date) -> bool:
    """Triple witching: the 3rd Friday of Mar/Jun/Sep/Dec."""
    return is_opex(d) and d.month in (3, 6, 9, 12)


def _last_weekday_of_month(d: date) -> date:
    last = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
    while last.weekday() >= 5:
        last -= timedelta(days=1)
    return last


def is_month_end(d: date) -> bool:
    """Last WEEKDAY of the calendar month. Deliberately holiday-blind: if that weekday is a
    full-closure holiday the true last trading day is one earlier - tolerated (the flag is a
    rebalance-pressure context bit, not a gate)."""
    return d == _last_weekday_of_month(d)


def is_quarter_end(d: date) -> bool:
    return is_month_end(d) and d.month in (3, 6, 9, 12)


# --------------------------------------------------------------------------- #
# Hunt-list normalization (pure) + tolerant file read.
# --------------------------------------------------------------------------- #

def normalize_hunt_rows(raw) -> list[dict]:
    """Tolerant normalization of the research crew's artifact into [{symbol, catalyst?,
    gap_pct?}]. Accepts {"candidates": [...]} (current crew schema), {"symbols": [...]}
    (legacy), or a bare list of dicts/strings. Unknown shapes / rows -> dropped, never a
    raise; duplicate symbols keep the first row."""
    if isinstance(raw, dict):
        rows = raw.get("candidates")
        if not isinstance(rows, list):
            rows = raw.get("symbols")
    else:
        rows = raw
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, str):
            row: dict = {"symbol": r.strip().upper()}
        elif isinstance(r, dict) and r.get("symbol"):
            row = {"symbol": str(r["symbol"]).strip().upper()}
            catalyst = r.get("catalyst", r.get("catalyst_kind"))
            if catalyst is not None:
                row["catalyst"] = catalyst
            if r.get("gap_pct") is not None:
                try:
                    row["gap_pct"] = float(r["gap_pct"])
                except (TypeError, ValueError):
                    pass
        else:
            continue
        if not row["symbol"] or row["symbol"] in seen:
            continue
        seen.add(row["symbol"])
        out.append(row)
    return out


def load_hunt_rows(path: Path = HUNT_LIST_PATH) -> list[dict]:
    """[] on any problem (absent file, bad JSON) - fail-open, like the shadow's own loader."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    return normalize_hunt_rows(raw)


# --------------------------------------------------------------------------- #
# Scorecard digest (pure).
# --------------------------------------------------------------------------- #

def scorecard_digest(card) -> dict | None:
    """Per-lane {verdict, n, net_worst_mean} + exits_total from a full scorecard dict
    (grade_options_shadow.py output). None when the scorecard is absent/unreadable."""
    if not isinstance(card, dict):
        return None
    lanes = {}
    for lane, s in (card.get("lanes") or {}).items():
        if isinstance(s, dict):
            lanes[str(lane)] = {"verdict": s.get("verdict"), "n": s.get("n"),
                                "net_worst_mean": s.get("net_worst_mean")}
    return {"lanes": lanes, "exits_total": card.get("exits_total")}


# --------------------------------------------------------------------------- #
# The pure briefing builder - everything injected, never raises.
# --------------------------------------------------------------------------- #

def build_briefing(d: date, *, events=None, days=None, hunt_rows=None, earnings_fn=None,
                   scorecard=None) -> dict:
    """Compile the briefing dict for ET-date `d` from injected sources only.

    events      : sequence[EconEvent] (None -> no events known, NOT load_events() - the pure
                  path must never do I/O)
    days        : session-calendar mapping (None -> {} = weekday + 2026 fallback tables)
    hunt_rows   : normalize_hunt_rows() output (None -> [])
    earnings_fn : callable(symbol) -> signed days-to-earnings int | None (None -> all None)
    scorecard   : full scorecard dict | None

    Every section fails open to null/[] and records itself in "notes" instead of raising.
    """
    notes: list[str] = []
    out: dict = {
        "schema": 1,
        "generated": datetime.now(ET).isoformat(timespec="seconds"),
        "date": d.isoformat(),
    }

    days_map = days if days is not None else {}
    try:
        close_min = int(session_close_minute(d, days=days_map))
        out["trading_day"] = bool(is_trading_day(d, days=days_map))
        out["session_close_min"] = close_min
        out["half_day"] = close_min < FULL_DAY_CLOSE_MIN
    except Exception:  # noqa: BLE001 - fail open, name the degraded section
        out["trading_day"] = None
        out["session_close_min"] = None
        out["half_day"] = None
        notes.append("session")

    try:
        ev = list(events) if events is not None else []
        out["events_today"] = list(is_event_day(d, events=ev))
        start = datetime.combine(d, time(0, 0), tzinfo=ET)
        out["next_events"] = [
            {"kind": e.kind, "ts_et_iso": e.ts_et.isoformat()}
            for e in upcoming_events(start, horizon_days=NEXT_EVENTS_HORIZON_DAYS, events=ev)
        ]
    except Exception:  # noqa: BLE001
        out["events_today"] = []
        out["next_events"] = []
        notes.append("events")

    # Calendar structure is pure date arithmetic - it cannot fail.
    out["opex"] = is_opex(d)
    out["witching"] = is_witching(d)
    out["month_end"] = is_month_end(d)
    out["quarter_end"] = is_quarter_end(d)

    try:
        hunt_out: list[dict] = []
        for r in hunt_rows or []:
            if not isinstance(r, dict):
                continue
            sym = str(r.get("symbol") or "").strip().upper()
            if not sym:
                continue
            row = dict(r)
            row["symbol"] = sym
            ed = None
            if earnings_fn is not None:
                try:
                    ed = earnings_fn(sym)
                except Exception:  # noqa: BLE001 - one bad lookup never drops the row
                    ed = None
            if isinstance(ed, bool) or not isinstance(ed, (int, float)):
                ed = None
            else:
                ed = int(ed)
            row["earnings_days"] = ed
            row["earnings_flag"] = ed is not None and abs(ed) <= EARNINGS_FLAG_WINDOW_DAYS
            hunt_out.append(row)
        out["hunt_list"] = hunt_out
    except Exception:  # noqa: BLE001
        out["hunt_list"] = []
        notes.append("hunt_list")

    try:
        out["prior_scorecard"] = scorecard_digest(scorecard)
    except Exception:  # noqa: BLE001
        out["prior_scorecard"] = None
        notes.append("scorecard")

    out["vix"] = None                    # enrichment lands later; keep the field stable now
    out["notes"] = notes
    return out


# --------------------------------------------------------------------------- #
# main() wiring - the ONLY I/O. Each source fail-opens; the process always exits 0.
# --------------------------------------------------------------------------- #

def _run_crew(timeout: float = CREW_TIMEOUT_S) -> str:
    """Invoke the overnight research crew as a subprocess. ANY failure (missing script,
    non-zero exit, timeout, spawn error) is tolerated silently - the crew degrades without
    API keys by design and must never break the briefing."""
    try:
        proc = subprocess.run([sys.executable, str(CREW_SCRIPT)], cwd=str(FRAMEWORK_ROOT),
                              capture_output=True, text=True, timeout=timeout)
        return "ok" if proc.returncode == 0 else f"rc={proc.returncode}"
    except Exception:  # noqa: BLE001 - never raises because of the crew
        return "failed"


def _run_side_script(script_name: str, timeout: float) -> str:
    """Best-effort premarket side-job (same contract as _run_crew): ANY failure - missing script,
    non-zero exit, timeout, spawn error - is tolerated silently and must NEVER break the briefing.
    Used to fold the catalyst-context writer + catmem enrichment into ATLAS-Premarket (no new task)."""
    try:
        proc = subprocess.run([sys.executable, str(FRAMEWORK_ROOT / "scripts" / script_name)],
                              cwd=str(FRAMEWORK_ROOT), capture_output=True, text=True, timeout=timeout)
        return "ok" if proc.returncode == 0 else f"rc={proc.returncode}"
    except Exception:  # noqa: BLE001
        return "failed"


def _make_earnings_fn():
    """Production earnings source: FinnhubEarningsFeed.days_to_earnings wrapped fail-open.
    Missing credentials file / key / import problem -> a lookup that returns None for every
    symbol (all rows get earnings_days=None, earnings_flag=False)."""
    try:
        import yaml
        creds = yaml.safe_load(CREDS_PATH.read_text("utf-8")) or {}
        key = str(((creds.get("finnhub") or {}).get("api_key")) or "").strip()
        if not key:
            return lambda symbol: None
        from atlas.collect.finnhub_feed import FinnhubEarningsFeed
        feed = FinnhubEarningsFeed(key)
        now_iso = datetime.now(ET).isoformat(timespec="seconds")

        def fn(symbol: str):
            try:
                return feed.days_to_earnings(symbol, now_iso)
            except Exception:  # noqa: BLE001 - the feed already fail-opens; belt and braces
                return None

        return fn
    except Exception:  # noqa: BLE001
        return lambda symbol: None


def _read_scorecard(path: Path = SCORECARD_PATH) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Compile the premarket day briefing (runtime/day_briefing.json)")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help="output path (default runtime/day_briefing.json)")
    ap.add_argument("--date", default=None, help="briefing date YYYY-MM-DD (default: today ET)")
    ap.add_argument("--skip-crew", action="store_true",
                    help="do not invoke scripts/research_crew.py first")
    args = ap.parse_args(argv)

    notes: list[str] = []

    crew_status = "skipped"
    if not args.skip_crew:
        # 1) refresh the catalyst context BEFORE the crew so it fans out with fresh 8-K/insider/FDA/
        #    dilution/PR/crowding context (opts-catalyst-context-writer-v1)
        cat_status = _run_side_script("build_catalyst_context.py", timeout=120.0)
        if cat_status != "ok":
            notes.append(f"catalyst_context:{cat_status}")
        # 2) the research crew builds runtime/hunt_list.json
        crew_status = _run_crew()
        if crew_status != "ok":
            notes.append(f"crew:{crew_status}")
        # 3) catmem enrichment AFTER the crew: recall() over the fresh hunt_list -> catalyst_context.json
        #    (the entry catmem covariates, opts-catmem-covariates-v1)
        enrich_status = _run_side_script("enrich_catalyst_context.py", timeout=60.0)
        if enrich_status != "ok":
            notes.append(f"catmem_enrich:{enrich_status}")

    try:
        d = date.fromisoformat(args.date) if args.date else datetime.now(ET).date()
    except (TypeError, ValueError):
        d = datetime.now(ET).date()
        notes.append("bad_date_arg")

    try:
        from atlas.options.events import load_events
        events = load_events()
    except Exception:  # noqa: BLE001
        events = []
        notes.append("events_load")

    try:
        from atlas.options.session_calendar import load_days
        days = load_days()
    except Exception:  # noqa: BLE001
        days = {}
        notes.append("calendar_load")

    try:
        hunt_rows = load_hunt_rows()
    except Exception:  # noqa: BLE001 - load_hunt_rows is fail-open already; belt and braces
        hunt_rows = []
        notes.append("hunt_list_load")

    earnings_fn = _make_earnings_fn()
    scorecard = _read_scorecard()

    briefing = build_briefing(d, events=events, days=days, hunt_rows=hunt_rows,
                              earnings_fn=earnings_fn, scorecard=scorecard)
    briefing["notes"] = notes + list(briefing.get("notes") or [])

    out = Path(args.out)
    wrote = str(out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(briefing, indent=1), encoding="utf-8")
        atomic_replace(tmp, out)
    except Exception as exc:  # noqa: BLE001 - a write failure must not break the launch
        wrote = f"WRITE FAILED ({type(exc).__name__}: {exc})"

    flagged = sum(1 for r in briefing["hunt_list"] if r.get("earnings_flag"))
    print(f"day-briefing {briefing['date']}: trading_day={briefing['trading_day']} "
          f"close={briefing['session_close_min']} half_day={briefing['half_day']} "
          f"events_today={briefing['events_today'] or []} opex={briefing['opex']} "
          f"witching={briefing['witching']} hunt={len(briefing['hunt_list'])} "
          f"({flagged} earnings-flagged) "
          f"scorecard={'present' if briefing['prior_scorecard'] else 'absent'} "
          f"crew={crew_status} notes={briefing['notes'] or []} -> {wrote}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
