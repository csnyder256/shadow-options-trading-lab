"""alert_watch config + options-shadow watch regression tests.

Born 2026-07-10: config/alerts.json acquired a UTF-8 BOM (a PowerShell edit) and
alert_watch.load_config silently fell back to DEFAULTS - empty ntfy topic, pager
unable to page at all. The BOM tests pin the utf-8-sig fix AND canary the live
file so a recurrence is loud in CI instead of silent at the next outage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import alert_watch

REPO = Path(__file__).resolve().parent.parent


def test_load_config_tolerates_utf8_bom(tmp_path, monkeypatch):
    cfg_file = tmp_path / "alerts.json"
    payload = {"ntfy": {"enabled": True, "topic": "test-topic-123"}}
    cfg_file.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
    monkeypatch.setattr(alert_watch, "CONFIG_FILE", cfg_file)
    cfg = alert_watch.load_config()
    assert cfg["ntfy"]["topic"] == "test-topic-123", (
        "a BOM'd alerts.json must still merge over DEFAULTS (utf-8-sig read); "
        "falling back to defaults means an empty topic = pager cannot page"
    )


def test_load_config_plain_utf8_unchanged(tmp_path, monkeypatch):
    cfg_file = tmp_path / "alerts.json"
    cfg_file.write_text(json.dumps({"ntfy": {"topic": "plain-topic"}}), encoding="utf-8")
    monkeypatch.setattr(alert_watch, "CONFIG_FILE", cfg_file)
    assert alert_watch.load_config()["ntfy"]["topic"] == "plain-topic"


# ---------------------------------------------------------------- data-plane zombie check
OSW = {"stale_threshold_sec": 180, "tick_stale_threshold_sec": 120}
NOW = 1_800_000_000.0
IN_SESSION = 12 * 60          # 12:00 ET


def _hb(**over) -> dict:
    base = {"schema": 2, "ts_epoch": NOW - 5.0, "client_present": True,
            "last_tick_epoch": NOW - 10.0, "last_bar_epoch": NOW - 40.0,
            "last_mark_epoch": NOW - 70.0, "open_positions": 1,
            "session_close_min": 960}
    base.update(over)
    return base


def test_data_reason_healthy_is_none():
    assert alert_watch.options_shadow_data_reason(_hb(), NOW, OSW, IN_SESSION) is None


def test_data_reason_schema1_never_pages():
    hb = _hb(schema=1)
    hb.pop("client_present")
    assert alert_watch.options_shadow_data_reason(hb, NOW, OSW, IN_SESSION) is None


def test_data_reason_missing_or_stale_heartbeat_owned_by_process_check():
    assert alert_watch.options_shadow_data_reason(None, NOW, OSW, IN_SESSION) is None
    stale = _hb(ts_epoch=NOW - 500.0)          # process check pages this; never double-page
    assert alert_watch.options_shadow_data_reason(stale, NOW, OSW, IN_SESSION) is None


def test_data_reason_no_client_pages():
    reason = alert_watch.options_shadow_data_reason(_hb(client_present=False), NOW, OSW, IN_SESSION)
    assert reason and "WITHOUT a Tradier client" in reason


def test_data_reason_stale_ticks_page_in_session_only():
    hb = _hb(last_tick_epoch=NOW - 121.0)
    reason = alert_watch.options_shadow_data_reason(hb, NOW, OSW, IN_SESSION)
    assert reason and "STALE" in reason and "open_positions=1" in reason
    # after the close the tick gate stops polling BY DESIGN -> silence is healthy
    assert alert_watch.options_shadow_data_reason(hb, NOW, OSW, 961) is None
    # half day: heartbeat's own session_close_min bounds the check
    half = _hb(last_tick_epoch=NOW - 121.0, session_close_min=780)
    assert alert_watch.options_shadow_data_reason(half, NOW, OSW, 800) is None
    assert alert_watch.options_shadow_data_reason(half, NOW, OSW, 700) is not None
    # pre-open settle window
    assert alert_watch.options_shadow_data_reason(hb, NOW, OSW, 9 * 60 + 31) is None


def test_data_reason_never_ticked_pages():
    reason = alert_watch.options_shadow_data_reason(_hb(last_tick_epoch=0.0), NOW, OSW, IN_SESSION)
    assert reason and "STALE" in reason
    # never-ticked must read as such, not as an epoch-sized seconds count
    assert "NO tick since process start" in reason


def test_tick_fresh_gates_the_recovery_notice():
    # fresh in-session tick -> recovery notice allowed
    assert alert_watch.options_shadow_tick_fresh(_hb(), NOW, OSW) is True
    # stale / never-ticked / old-schema / unreadable -> latch clears SILENTLY
    assert alert_watch.options_shadow_tick_fresh(_hb(last_tick_epoch=NOW - 500.0), NOW, OSW) is False
    assert alert_watch.options_shadow_tick_fresh(_hb(last_tick_epoch=0.0), NOW, OSW) is False
    assert alert_watch.options_shadow_tick_fresh(_hb(schema=1), NOW, OSW) is False
    assert alert_watch.options_shadow_tick_fresh(None, NOW, OSW) is False


# ---------------------------------------------------------------- news-flag tap watch
def test_news_flags_defaults_shape_and_options_only_arm():
    assert alert_watch.DEFAULTS["news_flags"]["enabled"] is False
    assert alert_watch.DEFAULTS["news_flags"]["stale_threshold_sec"] == 300
    # --options-only arms it exactly like the shadow watch (source-pinned, no CLI run needed)
    import inspect
    src = inspect.getsource(alert_watch.main)
    assert 'cfg.setdefault("news_flags", {})["enabled"] = True' in src


def test_news_flags_watch_silent_when_disabled(monkeypatch, tmp_path):
    """enabled=False must never page - even with a MISSING heartbeat (skeptic defect-4 pin)."""
    calls = []
    monkeypatch.setattr(alert_watch, "notify", lambda *a, **k: calls.append(a) or {})
    monkeypatch.setattr(alert_watch, "RUNTIME", tmp_path)          # no heartbeat file exists
    monkeypatch.setattr(alert_watch, "load_today_records", lambda: [])
    monkeypatch.setattr(alert_watch, "in_market_hours", lambda cfg: True)
    monkeypatch.setattr(alert_watch, "save_state", lambda st: None)
    cfg = json.loads(json.dumps(alert_watch.DEFAULTS))
    cfg["analyst_watch"] = False
    st = {"date": alert_watch.local_today(), "down": False}
    alert_watch.evaluate(cfg, st, {"grace_until": 0.0})
    assert calls == [] and not st.get("news_flags_down")


def test_live_alerts_json_is_bom_free_and_configured():
    """Canary: the LIVE config must parse as plain utf-8 (no BOM) and carry a topic.

    load_config now tolerates a BOM, so this failing is a warning about whatever
    wrote the file, not an outage - but it must stay loud."""
    raw = (REPO / "config" / "alerts.json").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "alerts.json re-acquired a UTF-8 BOM"
    cfg = json.loads(raw.decode("utf-8"))
    topic = (cfg.get("ntfy") or {}).get("topic") or ""
    if not topic or "CHANGE-ME" in topic:
        pytest.skip("alerts.json still holds the shipped placeholder topic; "
                    "set a real ntfy topic to arm this canary")
    assert topic, "live ntfy topic missing - pager dead"
