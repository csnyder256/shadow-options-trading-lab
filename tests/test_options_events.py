"""Event-calendar tests (2026-07-09, O1) - pure logic only, events always injected, zero
network/disk. Covers window edges of the [release-5m, release+15m] hard blackout and the
[release-60m, release) pre_print band, FOMC decision+presser interplay, timezone handling,
horizon filtering, event-day lookup, and the fallback-table invariants."""

from datetime import date, datetime, timedelta, timezone

from atlas.options.events import (
    CPI_2026_FALLBACK,
    ET,
    FOMC_DECISION_DAYS_2026,
    NFP_2026_FALLBACK,
    EconEvent,
    build_events,
    in_blackout,
    is_event_day,
    macro_release_active,
    upcoming_events,
)

# A tiny deterministic calendar: one CPI print, one NFP print, one FOMC day.
EVENTS = build_events(cpi_dates=["2026-07-14"], nfp_dates=["2026-08-07"],
                      fomc_decision_days=[date(2026, 7, 29)])


def _et(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def test_build_events_shape_and_times():
    kinds = [(e.kind, e.label, e.ts_et.strftime("%Y-%m-%d %H:%M")) for e in EVENTS]
    assert kinds == [
        ("cpi", "", "2026-07-14 08:30"),
        ("fomc", "decision", "2026-07-29 14:00"),
        ("fomc", "presser", "2026-07-29 14:30"),
        ("nfp", "", "2026-08-07 08:30"),
    ]
    assert all(e.ts_et.tzinfo is not None for e in EVENTS)


def test_in_blackout_cpi_window_edges():
    # Hard window [08:25, 08:45] inclusive.
    assert in_blackout(_et(2026, 7, 14, 8, 25), events=EVENTS) == "cpi"
    assert in_blackout(_et(2026, 7, 14, 8, 30), events=EVENTS) == "cpi"
    assert in_blackout(_et(2026, 7, 14, 8, 45), events=EVENTS) == "cpi"
    assert in_blackout(_et(2026, 7, 14, 8, 46), events=EVENTS) is None
    # Pre-print [07:30, 08:25) - the hard window wins at its own left edge.
    assert in_blackout(_et(2026, 7, 14, 7, 30), events=EVENTS) == "pre_print"
    assert in_blackout(_et(2026, 7, 14, 8, 24), events=EVENTS) == "pre_print"
    assert in_blackout(_et(2026, 7, 14, 7, 29), events=EVENTS) is None
    # A plain day is clean.
    assert in_blackout(_et(2026, 7, 15, 8, 30), events=EVENTS) is None


def test_in_blackout_fomc_decision_and_presser_sequence():
    day = (2026, 7, 29)
    assert in_blackout(_et(*day, 13, 0), events=EVENTS) == "pre_print"    # decision pre-window
    assert in_blackout(_et(*day, 13, 55), events=EVENTS) == "fomc"        # hard opens
    assert in_blackout(_et(*day, 14, 15), events=EVENTS) == "fomc"        # hard closes
    # Between the decision's hard window and the presser's: presser pre_print, NOT clean - 
    # and the presser pre-window must never mask the decision hard window (checked above).
    assert in_blackout(_et(*day, 14, 20), events=EVENTS) == "pre_print"
    assert in_blackout(_et(*day, 14, 25), events=EVENTS) == "fomc"        # presser hard opens
    assert in_blackout(_et(*day, 14, 45), events=EVENTS) == "fomc"        # presser hard closes
    assert in_blackout(_et(*day, 14, 46), events=EVENTS) is None
    assert in_blackout(_et(*day, 12, 59), events=EVENTS) is None          # before any window


def test_timezone_handling_aware_and_naive():
    # July = EDT (UTC-4): 12:30Z == 08:30 ET -> inside the CPI hard window.
    assert in_blackout(datetime(2026, 7, 14, 12, 30, tzinfo=timezone.utc), events=EVENTS) == "cpi"
    # Naive datetimes are taken as ET (market-local convention).
    assert in_blackout(datetime(2026, 7, 14, 8, 30), events=EVENTS) == "cpi"


def test_upcoming_events_horizon_and_order():
    now = _et(2026, 7, 13, 9, 0)
    week = upcoming_events(now, horizon_days=7, events=EVENTS)
    assert [e.kind for e in week] == ["cpi"]                    # FOMC is 16 days out
    month = upcoming_events(now, horizon_days=30, events=EVENTS)
    assert [(e.kind, e.label) for e in month] == [("cpi", ""), ("fomc", "decision"),
                                                  ("fomc", "presser"), ("nfp", "")]
    assert month == sorted(month, key=lambda e: e.ts_et)
    # Past events never resurface.
    assert upcoming_events(_et(2026, 8, 8, 9, 0), horizon_days=90, events=EVENTS) == []


def test_is_event_day():
    assert is_event_day(date(2026, 7, 14), events=EVENTS) == ["cpi"]
    assert is_event_day(date(2026, 7, 29), events=EVENTS) == ["fomc"]     # deduped decision+presser
    assert is_event_day(date(2026, 8, 7), events=EVENTS) == ["nfp"]
    assert is_event_day(date(2026, 7, 15), events=EVENTS) == []


def test_macro_release_active_mirrors_in_blackout():
    assert macro_release_active(_et(2026, 7, 14, 8, 31), events=EVENTS) is True
    assert macro_release_active(_et(2026, 7, 14, 7, 35), events=EVENTS) is True   # pre_print counts
    assert macro_release_active(_et(2026, 7, 14, 11, 0), events=EVENTS) is False


def test_multi_kind_day_reports_all_kinds():
    ev = build_events(cpi_dates=["2026-07-29"], nfp_dates=[],
                      fomc_decision_days=[date(2026, 7, 29)])
    assert is_event_day(date(2026, 7, 29), events=ev) == ["cpi", "fomc"]
    # 08:30 CPI print dominates the morning; FOMC windows own the afternoon.
    assert in_blackout(_et(2026, 7, 29, 8, 40), events=ev) == "cpi"
    assert in_blackout(_et(2026, 7, 29, 14, 10), events=ev) == "fomc"


def test_fallback_tables_are_sane():
    # 12 monthly prints each, all ISO-parsable, all in 2026, strictly increasing.
    for table in (CPI_2026_FALLBACK, NFP_2026_FALLBACK):
        assert len(table) == 12
        days = [date.fromisoformat(d) for d in table]
        assert all(d.year == 2026 for d in days)
        assert days == sorted(days)
    assert len(FOMC_DECISION_DAYS_2026) == 8
    # The full default build yields 12 + 12 + 2*8 = 40 events with correct clock times.
    ev = build_events(CPI_2026_FALLBACK, NFP_2026_FALLBACK)
    assert len(ev) == 40
    assert all(e.ts_et.strftime("%H:%M") == "08:30" for e in ev if e.kind in ("cpi", "nfp"))
    assert all(e.ts_et.strftime("%H:%M") in ("14:00", "14:30") for e in ev if e.kind == "fomc")


def test_pure_api_never_touches_loader(monkeypatch):
    # With events injected, the query API must not call load_events (no disk, no network).
    import atlas.options.events as mod

    def boom(force=False):  # pragma: no cover - only fires on regression
        raise AssertionError("load_events called despite injected events")

    monkeypatch.setattr(mod, "load_events", boom)
    assert in_blackout(_et(2026, 7, 14, 8, 30), events=EVENTS) == "cpi"
    assert upcoming_events(_et(2026, 7, 13, 9, 0), events=EVENTS)
    assert is_event_day(date(2026, 7, 14), events=EVENTS) == ["cpi"]
    assert macro_release_active(_et(2026, 7, 14, 8, 30), events=EVENTS) is True


def test_events_are_frozen_records():
    e = EconEvent("cpi", _et(2026, 7, 14, 8, 30))
    try:
        e.kind = "nfp"
        raised = False
    except AttributeError:
        raised = True
    assert raised
