"""Crew probe: the pure pieces (JSON-array extraction + report shaping) - offline."""

from __future__ import annotations

from scripts.probe_crew import _first_json_array, summarize


def test_first_json_array_tolerant():
    assert _first_json_array('noise [ {"a": 1} ] trailing') == [{"a": 1}]
    assert _first_json_array('[[1, 2], 3]') == [[1, 2], 3]
    assert _first_json_array("no array here") is None
    assert _first_json_array('{"just": "an object"}') is None
    assert _first_json_array(None) is None
    # a broken first candidate does not stop the scan
    assert _first_json_array('[oops] then ["ok"]') == ["ok"]


def test_summarize_shapes_report():
    rows = [
        {"provider": "gemini", "task": "crew_fanout", "seconds": 3.2, "answered": True,
         "throttled": False},
        {"provider": "gemini", "task": "headline_classify", "seconds": 11.0, "answered": True,
         "throttled": True},
        {"provider": "groq", "task": "crew_fanout", "seconds": 1.1, "answered": True,
         "throttled": False},
        {"provider": "zai", "task": "crew_fanout", "seconds": 90.0, "answered": False,
         "throttled": False},
    ]
    rep = summarize(rows)
    assert rep["providers_configured"] == ["gemini", "groq", "zai"]
    assert rep["providers_answered"] == ["gemini", "groq"]
    assert rep["providers_failed"] == ["zai"]
    # throttled second calls never contaminate the first-call latency stats
    assert rep["fastest_first_call"] == {"provider": "groq", "seconds": 1.1}
    assert rep["slowest_first_call"] == {"provider": "gemini", "seconds": 3.2}
    empty = summarize([])
    assert empty["providers_configured"] == [] and empty["fastest_first_call"] is None
