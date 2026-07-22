"""Day-briefing compiler tests (2026-07-09) - pure logic only, everything injected, zero
network/disk. Covers the calendar-structure flags against known 2026 dates, half-day session
shape via an injected days mapping, earnings enrichment via a fake earnings_fn, hunt-list
shape tolerance (candidates / symbols / bare-list / garbage), the scorecard digest, and the
never-raises guarantee with all-None inputs."""

from datetime import date

from atlas.options.events import build_events
from scripts.build_day_briefing import (
    build_briefing,
    is_month_end,
    is_opex,
    is_quarter_end,
    is_witching,
    normalize_hunt_rows,
    scorecard_digest,
)

D = date(2026, 7, 10)  # a plain Friday (2nd Friday of July - NOT opex)


# --------------------------------------------------------------------------- #
# Calendar structure: opex / witching / month_end / quarter_end.
# --------------------------------------------------------------------------- #

def test_opex_and_witching_known_2026_dates():
    assert is_opex(date(2026, 7, 17))            # July's 3rd Friday
    assert not is_witching(date(2026, 7, 17))    # July is not a witching month
    assert is_opex(date(2026, 9, 18))            # September's 3rd Friday
    assert is_witching(date(2026, 9, 18))        # ... and a witching month
    assert not is_opex(date(2026, 7, 10))        # 2nd Friday - not opex
    assert not is_opex(date(2026, 7, 16))        # Thursday of opex week - not opex
    assert not is_witching(date(2026, 7, 10))


def test_opex_flags_flow_into_briefing():
    b = build_briefing(date(2026, 9, 18))
    assert b["opex"] is True and b["witching"] is True
    b2 = build_briefing(D)
    assert b2["opex"] is False and b2["witching"] is False


def test_month_end_and_quarter_end():
    assert is_month_end(date(2026, 7, 31))       # Friday, last day of July
    assert not is_quarter_end(date(2026, 7, 31))
    assert not is_month_end(date(2026, 7, 30))
    assert is_month_end(date(2026, 9, 30))       # Wednesday, last day of September
    assert is_quarter_end(date(2026, 9, 30))
    # Weekend month-end rolls back to the preceding weekday: 2026-05-31 is a Sunday.
    assert not is_month_end(date(2026, 5, 31))
    assert is_month_end(date(2026, 5, 29))       # the Friday before


# --------------------------------------------------------------------------- #
# Session shape via injected days.
# --------------------------------------------------------------------------- #

def test_half_day_2026_11_27_injected_days():
    days = {"2026-11-27": {"status": "open", "close_min": 780}}
    b = build_briefing(date(2026, 11, 27), days=days)
    assert b["trading_day"] is True
    assert b["session_close_min"] == 780
    assert b["half_day"] is True


def test_normal_day_and_injected_holiday():
    b = build_briefing(D, days={})
    assert b["trading_day"] is True
    assert b["session_close_min"] == 960
    assert b["half_day"] is False
    closed = build_briefing(D, days={"2026-07-10": {"status": "closed"}})
    assert closed["trading_day"] is False
    weekend = build_briefing(date(2026, 7, 11), days={})   # Saturday
    assert weekend["trading_day"] is False


# --------------------------------------------------------------------------- #
# Events: today's kinds + the 7-day horizon.
# --------------------------------------------------------------------------- #

EVENTS = build_events(cpi_dates=["2026-07-14"], nfp_dates=["2026-08-07"],
                      fomc_decision_days=[date(2026, 7, 29)])


def test_events_today_and_next_events_horizon():
    on_print_day = build_briefing(date(2026, 7, 14), events=EVENTS)
    assert on_print_day["events_today"] == ["cpi"]

    b = build_briefing(D, events=EVENTS)                   # 07-10: CPI is 4 days out
    assert b["events_today"] == []
    kinds = [e["kind"] for e in b["next_events"]]
    assert kinds == ["cpi"]
    assert b["next_events"][0]["ts_et_iso"].startswith("2026-07-14T08:30")

    far = build_briefing(date(2026, 7, 1), events=EVENTS)  # 07-01 + 7d < 07-14
    assert far["next_events"] == []

    near_fomc = build_briefing(date(2026, 7, 27), events=EVENTS)
    assert [e["kind"] for e in near_fomc["next_events"]] == ["fomc", "fomc"]  # decision+presser


# --------------------------------------------------------------------------- #
# Hunt list: tolerant shapes + earnings enrichment.
# --------------------------------------------------------------------------- #

def test_normalize_hunt_rows_candidates_shape():
    raw = {"schema": 1, "candidates": [
        {"symbol": "abc", "catalyst_kind": "earnings", "confidence": 0.8},
        {"symbol": "XYZ", "gap_pct": "4.5", "catalyst": True},
        {"symbol": "abc"},                                  # duplicate -> dropped
        {"no_symbol": True},                                # unusable -> dropped
    ]}
    rows = normalize_hunt_rows(raw)
    assert [r["symbol"] for r in rows] == ["ABC", "XYZ"]
    assert rows[0]["catalyst"] == "earnings"
    assert rows[1]["gap_pct"] == 4.5 and rows[1]["catalyst"] is True


def test_normalize_hunt_rows_symbols_and_bare_list_shapes():
    assert [r["symbol"] for r in normalize_hunt_rows({"symbols": ["spy", "QQQ"]})] == ["SPY", "QQQ"]
    rows = normalize_hunt_rows(["IWM", {"symbol": "TSLA", "gap_pct": 6.1}])
    assert [r["symbol"] for r in rows] == ["IWM", "TSLA"]
    assert "gap_pct" not in rows[0] and rows[1]["gap_pct"] == 6.1


def test_normalize_hunt_rows_garbage_shapes():
    assert normalize_hunt_rows(None) == []
    assert normalize_hunt_rows(42) == []
    assert normalize_hunt_rows({"nope": 1}) == []
    assert normalize_hunt_rows({"candidates": "not-a-list"}) == []
    assert normalize_hunt_rows([{"symbol": ""}, 3.14]) == []


def test_earnings_flags_via_fake_earnings_fn():
    table = {"AAA": 0, "BBB": -1, "CCC": 5, "DDD": None}
    rows = normalize_hunt_rows(["AAA", "BBB", "CCC", "DDD", "EEE"])

    def boom_or_lookup(sym):
        if sym == "EEE":
            raise RuntimeError("provider down")            # one bad lookup never drops a row
        return table[sym]

    b = build_briefing(D, hunt_rows=rows, earnings_fn=boom_or_lookup)
    got = {r["symbol"]: (r["earnings_days"], r["earnings_flag"]) for r in b["hunt_list"]}
    assert got == {"AAA": (0, True), "BBB": (-1, True), "CCC": (5, False),
                   "DDD": (None, False), "EEE": (None, False)}


def test_hunt_list_without_earnings_fn_all_none():
    rows = normalize_hunt_rows({"candidates": [{"symbol": "GME", "catalyst_kind": "fda"}]})
    b = build_briefing(D, hunt_rows=rows)
    (row,) = b["hunt_list"]
    assert row["symbol"] == "GME" and row["catalyst"] == "fda"
    assert row["earnings_days"] is None and row["earnings_flag"] is False


# --------------------------------------------------------------------------- #
# Scorecard digest.
# --------------------------------------------------------------------------- #

def test_scorecard_digest_injected_dict():
    card = {"exits_total": 7, "entries_total": 9, "lanes": {
        "IndexTrend": {"verdict": "ACCUMULATING", "n": 3, "net_worst_mean": -0.5,
                       "exit_rule_mix": {"r1": 3}},
        "Last30": {"verdict": "PASS", "n": 25, "net_worst_mean": 1.2},
    }}
    b = build_briefing(D, scorecard=card)
    assert b["prior_scorecard"] == {
        "exits_total": 7,
        "lanes": {"IndexTrend": {"verdict": "ACCUMULATING", "n": 3, "net_worst_mean": -0.5},
                  "Last30": {"verdict": "PASS", "n": 25, "net_worst_mean": 1.2}},
    }
    assert scorecard_digest(None) is None
    assert scorecard_digest("junk") is None
    assert scorecard_digest({}) == {"lanes": {}, "exits_total": None}


# --------------------------------------------------------------------------- #
# The never-raises guarantee + stable schema.
# --------------------------------------------------------------------------- #

def test_build_briefing_all_none_inputs_never_raises():
    import json
    b = build_briefing(D)                                   # everything defaulted
    assert b["schema"] == 1
    assert b["date"] == "2026-07-10"
    assert b["events_today"] == [] and b["next_events"] == []
    assert b["hunt_list"] == []
    assert b["prior_scorecard"] is None
    assert b["vix"] is None
    assert b["notes"] == []
    assert isinstance(b["trading_day"], bool)
    assert isinstance(b["session_close_min"], int)
    json.dumps(b)                                           # fully serializable
