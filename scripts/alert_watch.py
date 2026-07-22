#!/usr/bin/env python3
"""alert_watch.py - standalone READ-ONLY model-server stall detector + alerter for ATLAS.

WHY: on 2026-06-25 the local analyst (GLM via llama-swap) stalled in the last ~25 min of the session and
every cascade attempt timed out, silently. Trades are fail-closed (a timeout -> skip -> no position -> no
risk), so capital was never in danger -- but the failure was INVISIBLE until reviewed after the close.
This watcher makes a *suspected server-down* condition LOUD so the operator can intervene immediately.

WHAT (deliberately mirrors the hub/babysitter philosophy):
  * separate process, stdlib-only, NO `atlas` import, NO GPU, NO Robinhood calls.
  * READ-only on the trading artifacts (decision_journal.jsonl). It writes ONLY its own files
    (runtime/analyst_incident_*.txt, runtime/alert_state.json) -- nothing the trader reads -> cannot
    interfere with the live loop.
  * TRIGGER = "suspected server-down" (user's choice): >=N consecutive cascade cycles where every
    candidate timed out, OR the model server (:8080) failing K consecutive health probes during market
    hours. A lone transient timeout stays silent.
  * ON TRIGGER: write a timestamped incident snapshot (llama_swap_*.err.log tail + nvidia-smi + the
    failing cycle's journal rows + :8080 health) and notify via ntfy (phone push) + email.
  * de-duped: ONE alert per outage; a single "recovered" note when the analyst responds again. State is
    reset per trading-day so a prior day's outage never leaks into the next.

RUN:
  .venv\\Scripts\\python.exe scripts\\alert_watch.py                # daemon (the launcher starts this)
  .venv\\Scripts\\python.exe scripts\\alert_watch.py --self-test    # detect against today's journal, print
                                                                    # the would-be incident; sends NOTHING
  .venv\\Scripts\\python.exe scripts\\alert_watch.py --test         # send a real test alert + write a real
                                                                    # incident (verify channels end-to-end)
  .venv\\Scripts\\python.exe scripts\\alert_watch.py --once         # one evaluation pass then exit
Config: config/alerts.json (see that file's _note keys). Email/ntfy must be set up there first.
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, time as dtime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
RUNTIME = REPO / "runtime"
JOURNAL = RUNTIME / "decision_journal.jsonl"
STATE_FILE = RUNTIME / "alert_state.json"
CONFIG_FILE = REPO / "config" / "alerts.json"
MODELS_URL = "http://127.0.0.1:8080/v1/models"
RISK_STATE_FILE = RUNTIME / "risk_state.runtime.json"
APP_LOG = RUNTIME / "live_day.out.log"

DEFAULTS = {
    "enabled": True,
    "poll_interval_sec": 5,
    "trigger": {
        "consecutive_timeout_cycles": 2,
        "health_probe_fails": 3,
        "health_probe_interval_sec": 20,
        "startup_grace_sec": 180,
        "market_hours_only": True,
        "market_open_local": "08:30",   # local (machine = Central) -- 9:30 ET
        "market_close_local": "15:05",   # matches launch_live_day UntilTime
    },
    "ntfy": {"enabled": True, "base_url": "https://ntfy.sh", "topic": ""},
    "email": {
        "enabled": True, "to": "", "via_ntfy": False,
        "smtp_host": "", "smtp_port": 587, "smtp_user": "", "from": "",
        "smtp_pass_env": "ATLAS_ALERT_SMTP_PASS",
    },
    "guardian": {
        "enabled": False,                 # True (or pass --guardian) when running fractional (run_guardian.py)
        "heartbeat_file": "guardian_heartbeat.json",
        "stale_threshold_sec": 30,        # heartbeat older than this in market hours -> DOWN (urgent)
        "quote_stale_threshold_sec": 90,  # Guardian alive but its quote reads wedged -> DOWN
    },
    "telegram": {
        "enabled": False,                 # True (or pass --telegram) when the failsafe bot (telegram_bot.py) runs
        "heartbeat_file": "telegram_heartbeat.json",
        "stale_threshold_sec": 120,       # beacon older than this in market hours -> bot DOWN (can't remote-halt).
                                          # bot beats every ~25-35s (long-poll), so 120s = ~4 missed polls.
    },
    "options_shadow": {
        "enabled": False,                 # True (or pass --options-shadow) when run_options_shadow.py runs
        "heartbeat_file": "options_shadow_heartbeat.json",
        "stale_threshold_sec": 180,       # shadow loops ~10s; 180s = wedged/dead. MEDIUM severity:
                                          # zero capital at risk - the loss is a day of shadow EVIDENCE.
        "tick_stale_threshold_sec": 120,  # OPS constant (2026-07-10, audit find #7): poll cadence is
                                          # 10s and feed.poll fails OPEN to {} - the process heartbeat
                                          # stays fresh while the DATA PLANE is dead. 120s = 12 straight
                                          # quiet polls, > one full Tradier 429 backoff (~60s), < the
                                          # 180s process threshold. NOT a trading constant.
    },
    "news_flags": {
        "enabled": False,                 # armed by --options-only alongside the shadow watch
        "heartbeat_file": "news_flags_heartbeat.json",
        "stale_threshold_sec": 300,       # tap ticks ~2s; 300s = wedged/dead. LOW-MEDIUM severity:
                                          # the loss is stage-0 headline-flag EVIDENCE - the shadow
                                          # trades unaffected (opts-svc-news-flag-tap-v1).
    },
}


# ---------------------------------------------------------------- config / state
def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    try:
        # utf-8-sig: PowerShell edits love to prepend a BOM, and a BOM'd file
        # must degrade the pager to defaults (empty topic = cannot page at all)
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        cfg = _merge(cfg, raw)
    except FileNotFoundError:
        print(f"[alert_watch] no {CONFIG_FILE.name}; using built-in defaults (channels likely unset).", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[alert_watch] WARN: bad {CONFIG_FILE.name} ({exc}); using defaults.", flush=True)
    return cfg


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"date": None, "down": False}


def save_state(st: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(st, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"[alert_watch] WARN: could not write state: {exc}", flush=True)


# ---------------------------------------------------------------- journal parsing
def local_today() -> str:
    return datetime.now().date().isoformat()


def load_today_records() -> list[dict]:
    today = local_today()
    recs: list[dict] = []
    if not JOURNAL.exists():
        return recs
    try:
        with open(JOURNAL, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # journal ts is offset-aware (ET); during a session its date == the local date.
                if str(r.get("ts", ""))[:10] != today:
                    continue
                recs.append(r)
    except Exception as exc:  # noqa: BLE001
        print(f"[alert_watch] WARN: journal read failed: {exc}", flush=True)
    return recs


def _cycle_of(decision_id: str):
    head = str(decision_id).split("-", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def analyze_cycles(recs: list[dict]) -> list[tuple[int, dict]]:
    """Group today's records by cycle. Each cycle dict: reasons[], symbols[], responded(bool), ts."""
    cyc: dict[int, dict] = {}
    for r in recs:
        c = _cycle_of(r.get("decision_id", ""))
        if c is None:
            continue
        d = cyc.setdefault(c, {"reasons": [], "symbols": [], "responded": False, "ts": r.get("ts", "")})
        et = r.get("event_type", "")
        reason = (r.get("risk_decision") or {}).get("reject_reason", "")
        sym = r.get("symbol", "")
        if et == "rejected_proposal" and reason:
            d["reasons"].append(reason)
            if sym:
                d["symbols"].append(sym)
            # any non-error reason (analyst_pass, low_confidence, vetoed) == the model RESPONDED.
            if not reason.startswith("analyst_error"):
                d["responded"] = True
        if et in ("proposal", "order_submitted", "fill", "exit"):
            d["responded"] = True
    # Order by TIMESTAMP, not cycle id: an intraday relaunch resets cycle numbers, so id-order would put
    # the morning run at the tail and a genuine afternoon stall would never register as "trailing".
    return sorted(cyc.items(), key=lambda kv: str(kv[1].get("ts", "")))


def _fully_timed_out(d: dict) -> bool:
    rs = d["reasons"]
    return bool(rs) and not d["responded"] and all(r == "analyst_error:TimeoutError" for r in rs)


def trailing_timeout(ordered: list[tuple[int, dict]]) -> dict:
    """Trailing run of consecutive fully-timed-out cycles (the recent outage)."""
    cycles, symbols = [], []
    for c, d in reversed(ordered):
        if _fully_timed_out(d):
            cycles.append(c)
            symbols.extend(d["symbols"])
        else:
            break
    cycles.reverse()
    return {"count": len(cycles), "cycles": cycles, "symbols": symbols}


# ---------------------------------------------------------------- probes / incident
def probe_8080(timeout: float = 5.0) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(MODELS_URL, timeout=timeout) as resp:
            body = resp.read(2000).decode("utf-8", "replace")
            return resp.status == 200, f"HTTP {resp.status}: {body[:200]}"
    except urllib.error.URLError as exc:
        return False, f"URLError: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _run(cmd: list[str], timeout: float = 10.0) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "").strip()
        if p.stderr:
            out += f"\n[stderr] {p.stderr.strip()}"
        return out or "(no output)"
    except FileNotFoundError:
        return f"({cmd[0]} not found on PATH)"
    except Exception as exc:  # noqa: BLE001
        return f"(failed to run {cmd[0]}: {exc})"


def _tail_llama_swap(nbytes: int = 8000) -> str:
    logs = sorted(RUNTIME.glob("llama_swap_*.err.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        return "(no runtime/llama_swap_*.err.log yet -- serve_models server-logging lands on the NEXT model-server start)"
    p = logs[-1]
    data = p.read_bytes()
    return f"[{p.name}, last {min(nbytes, len(data))} of {len(data)} bytes]\n" + data[-nbytes:].decode("utf-8", "replace")


def _journal_error_rows(recs: list[dict]) -> str:
    rows = [r for r in recs if str((r.get("risk_decision") or {}).get("reject_reason", "")).startswith("analyst_error")]
    if not rows:
        return "(no analyst_error rows in today's journal)"
    return "\n".join(
        f"  cycle {_cycle_of(r.get('decision_id',''))}  {str(r.get('ts',''))[11:19]}  {r.get('symbol','?'):6} "
        f"{(r.get('risk_decision') or {}).get('reject_reason','')}"
        for r in rows
    )


def build_incident_text(reason: str, recs: list[dict], trail: dict) -> str:
    healthy, health_txt = probe_8080()
    return "\n".join([
        "===================== ATLAS analyst-stall incident =====================",
        f"generated : {datetime.now().isoformat()} (local)",
        f"trigger   : {reason}",
        f"outage    : {trail['count']} consecutive fully-timed-out cycle(s) {trail['cycles']} "
        f"-> {sorted(set(trail['symbols']))}",
        "",
        f"== model server :8080 /v1/models == (healthy={healthy})",
        f"  {health_txt}",
        "",
        "== nvidia-smi (is a model resident? GPU busy?) ==",
        _run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu", "--format=csv"]),
        "",
        "== latest runtime/llama_swap_*.err.log (tail) ==",
        _tail_llama_swap(),
        "",
        "== today's analyst_error journal rows ==",
        _journal_error_rows(recs),
        "",
        "NOTE: trades are fail-closed on a stall (skip -> no position -> no risk); capital is safe. This is a",
        "reliability alert. Review this file and verify against broker truth before acting.",
        "========================================================================",
    ])


def write_incident(reason: str, recs: list[dict], trail: dict) -> Path:
    RUNTIME.mkdir(exist_ok=True)
    path = RUNTIME / f"analyst_incident_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    path.write_text(build_incident_text(reason, recs, trail), encoding="utf-8")
    return path


# ---------------------------------------------------------------- guardian heartbeat
def guardian_status(now: float, cfg: dict):
    """Read runtime/guardian_heartbeat.json -> {age, quote_age, watching, raw}, or None if missing/unreadable.
    The Guardian is the SOLE protector of fractional lots, so a stale heartbeat is the HIGHEST-severity alert
    (unlike a model stall, where trades fail closed and capital is safe)."""
    g = cfg.get("guardian", {})
    path = RUNTIME / g.get("heartbeat_file", "guardian_heartbeat.json")
    try:
        hb = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    ts = hb.get("ts_epoch")
    lq = hb.get("last_quote_epoch") or 0
    wc = int(hb.get("watching_count") or 0)
    age = (now - float(ts)) if ts else None
    quote_age = (now - float(lq)) if (lq and wc > 0) else None    # quotes only matter while watching a lot
    return {"age": age, "quote_age": quote_age, "watching": wc, "raw": hb}


def _tail_file(path: Path, nbytes: int = 4000) -> str:
    try:
        data = path.read_bytes()
    except Exception:  # noqa: BLE001
        return f"({path.name} not found)"
    return (f"[{path.name}, last {min(nbytes, len(data))} of {len(data)} bytes]\n"
            + data[-nbytes:].decode("utf-8", "replace"))


def write_guardian_incident(reason: str, status) -> Path:
    RUNTIME.mkdir(exist_ok=True)
    path = RUNTIME / f"guardian_incident_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    body = "\n".join([
        "===================== ATLAS GUARDIAN-DOWN incident =====================",
        f"generated : {datetime.now().isoformat()} (local)",
        f"trigger   : {reason}",
        "SEVERITY  : HIGH - the Guardian is the SOLE protector of fractional lots; a dead Guardian means a",
        "            real position may be UNPROTECTED. The orchestrator also flattens + halts on this, but",
        "            verify against broker truth and restart the Guardian (scripts/run_guardian.py) NOW.",
        "",
        f"== heartbeat == {status['raw'] if status else 'MISSING / unreadable'}",
        "",
        "== synthetic_stops.json (orchestrator-published levels = what SHOULD be watched) ==",
        _tail_file(RUNTIME / "synthetic_stops.json"),
        "",
        "== runtime/guardian.log (tail) ==",
        _tail_file(RUNTIME / "guardian.log"),
        "",
        "== runtime/guardian_ALERTS.txt (tail) ==",
        _tail_file(RUNTIME / "guardian_ALERTS.txt"),
        "========================================================================",
    ])
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------- telegram failsafe-bot heartbeat
def telegram_status(now: float, cfg: dict):
    """Read runtime/telegram_heartbeat.json -> {age, raw}, or None if missing/unreadable. A stale beacon =
    the remote /halt failsafe is unreachable (bot process dead OR Telegram unreachable). MEDIUM severity:
    the Guardian still protects open positions; only the ability to remotely STOP NEW buys is lost."""
    t = cfg.get("telegram", {})
    path = RUNTIME / t.get("heartbeat_file", "telegram_heartbeat.json")
    try:
        hb = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    ts = hb.get("ts_epoch")
    age = (now - float(ts)) if ts else None
    return {"age": age, "raw": hb}


def write_telegram_incident(reason: str, status) -> Path:
    RUNTIME.mkdir(exist_ok=True)
    path = RUNTIME / f"telegram_incident_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    body = "\n".join([
        "===================== ATLAS TELEGRAM-BOT-DOWN incident =====================",
        f"generated : {datetime.now().isoformat()} (local)",
        f"trigger   : {reason}",
        "SEVERITY  : MEDIUM - the remote /halt failsafe is offline (bot process dead or Telegram",
        "            unreachable). Open positions are STILL Guardian-protected; you have lost the ability",
        "            to remotely STOP NEW purchases. Restart scripts/telegram_bot.py.",
        "",
        f"== heartbeat == {status['raw'] if status else 'MISSING / unreadable'}",
        "",
        "== runtime/telegram_bot.err.log (tail) ==",
        _tail_file(RUNTIME / "telegram_bot.err.log"),
        "",
        "== runtime/telegram_bot.out.log (tail) ==",
        _tail_file(RUNTIME / "telegram_bot.out.log"),
        "========================================================================",
    ])
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------- senders
def send_ntfy(cfg: dict, title: str, body: str) -> tuple[str, str]:
    n = cfg["ntfy"]
    if not n.get("enabled"):
        return ("ntfy", "disabled")
    topic = (n.get("topic") or "").strip()
    if not topic or "CHANGE-ME" in topic:
        return ("ntfy", "NO TOPIC set in config/alerts.json")
    url = f"{n.get('base_url', 'https://ntfy.sh').rstrip('/')}/{topic}"
    headers = {"Title": title, "Priority": "urgent", "Tags": "rotating_light"}
    em = cfg["email"]
    if em.get("enabled") and em.get("via_ntfy") and em.get("to") and not em.get("smtp_host"):
        headers["Email"] = em["to"]  # ntfy forwards to email (no SMTP creds needed)
    req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return ("ntfy", f"ok {resp.status}" + (" (+email via ntfy)" if "Email" in headers else ""))
    except Exception as exc:  # noqa: BLE001
        return ("ntfy", f"FAIL {type(exc).__name__}: {exc}")


def send_email(cfg: dict, subject: str, body: str) -> tuple[str, str]:
    e = cfg["email"]
    if not e.get("enabled"):
        return ("email", "disabled")
    if not e.get("smtp_host"):
        return ("email", "via ntfy Email header" if e.get("via_ntfy") else "no smtp_host configured")
    pw = os.environ.get(e.get("smtp_pass_env", "ATLAS_ALERT_SMTP_PASS"), "")
    if not pw:
        return ("email", f"skipped: env {e.get('smtp_pass_env')} not set")
    msg = EmailMessage()
    msg["From"] = e.get("from") or e.get("smtp_user", "")
    msg["To"] = e.get("to", "")
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(e["smtp_host"], int(e.get("smtp_port", 587)), timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(e.get("smtp_user", ""), pw)
            s.send_message(msg)
        return ("email", "ok (smtp)")
    except Exception as exc:  # noqa: BLE001
        return ("email", f"FAIL {type(exc).__name__}: {exc}")


def notify(cfg: dict, title: str, body: str) -> list[tuple[str, str]]:
    return [send_ntfy(cfg, title, body), send_email(cfg, title, body)]


# ---------------------------------------------------------------- market hours
def _hhmm(s: str) -> dtime:
    h, m = (s or "0:0").split(":")
    return dtime(int(h), int(m))


def in_market_hours(cfg: dict) -> bool:
    if not cfg["trigger"].get("market_hours_only", True):
        return True
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    return _hhmm(cfg["trigger"]["market_open_local"]) <= now.time() <= _hhmm(cfg["trigger"]["market_close_local"])


def options_shadow_data_reason(raw, now: float, osw: dict, et_minute: int):
    """Reason string when the shadow PROCESS is alive but its DATA PLANE is dead; None = healthy.

    Pure + stdlib-only (unit-tested in tests/test_alert_watch.py). Schema-tolerant: heartbeats
    below schema 2 (old process version) never page. The process-staleness branch owns
    missing/stale heartbeats - this never double-pages that case. Tick staleness is bounded by
    the heartbeat's OWN session_close_min: the shadow's tick gate stops polling at the equity
    close by design (after-hours freeze), so late-close-window silence is healthy - and half
    days are handled for free."""
    if not isinstance(raw, dict):
        return None
    try:
        ts = float(raw.get("ts_epoch") or 0.0)
    except (TypeError, ValueError):
        return None
    if now - ts > float(osw.get("stale_threshold_sec", 180)):
        return None                          # process-down check owns this case
    try:
        schema = int(raw.get("schema") or 1)
    except (TypeError, ValueError):
        schema = 1
    if schema < 2 or "client_present" not in raw:
        return None                          # old heartbeat shape - tolerance, never page
    if raw.get("client_present") is False:
        return ("options-shadow running WITHOUT a Tradier client (degraded heartbeat-only: "
                "no fills recorded, open positions UNMANAGED)")
    try:
        close_min = int(raw.get("session_close_min") or 960)
    except (TypeError, ValueError):
        close_min = 960
    if et_minute >= close_min or et_minute < 9 * 60 + 32:
        return None                          # after-hours freeze / pre-open settle window
    try:
        last_tick = float(raw.get("last_tick_epoch") or 0.0)
    except (TypeError, ValueError):
        return None
    tick_age = now - last_tick
    if tick_age > float(osw.get("tick_stale_threshold_sec", 120)):
        ctx = [f"open_positions={raw.get('open_positions', '?')}"]
        for k in ("last_mark_epoch", "last_bar_epoch"):
            try:
                v = float(raw.get(k) or 0.0)
                ctx.append(f"{k.replace('_epoch', '')} {now - v:.0f}s ago" if v > 0
                           else f"{k.replace('_epoch', '')} never")
            except (TypeError, ValueError):
                pass
        since = ("NO tick since process start" if last_tick <= 0.0
                 else f"{tick_age:.0f}s since last tick")
        return (f"options-shadow quotes STALE ({since}; client present, "
                f"process alive) [{', '.join(ctx)}]")
    return None


def options_shadow_tick_fresh(raw, now: float, osw: dict) -> bool:
    """True only when a schema>=2 heartbeat shows a genuinely fresh tick - the recovery-
    notification gate: a data-plane outage whose reason merely evaporates (session close
    bound reached, or the process itself died and the staleness branch took ownership) must
    clear the latch SILENTLY, never announce "quotes flowing again"."""
    if not isinstance(raw, dict):
        return False
    try:
        if int(raw.get("schema") or 1) < 2:
            return False
        last_tick = float(raw.get("last_tick_epoch") or 0.0)
    except (TypeError, ValueError):
        return False
    return last_tick > 0.0 and (now - last_tick) <= float(osw.get("tick_stale_threshold_sec", 120))


def _age_seconds(ts_str: str) -> float:
    """Seconds since an offset-aware journal ts (1e9 if unparseable). Lets us ignore STALE stalls."""
    try:
        dt = datetime.fromisoformat(str(ts_str))
        ref = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        return (ref - dt).total_seconds()
    except Exception:  # noqa: BLE001
        return 1e9


# ---------------------------------------------------------------- evaluation
def evaluate(cfg: dict, st: dict, rt: dict) -> None:
    now = time.time()
    recs = load_today_records()
    today = local_today()
    if st.get("date") != today:  # new trading day -> reset outage state
        st.clear()
        st.update({"date": today, "down": False})
        save_state(st)

    recent_window = cfg["trigger"].get("recent_stall_window_sec", 600)
    # --options-only (2026-07-10 pivot): the equity analyst/model-server/halt/broker/app watches
    # are DISABLED - no llama-swap or orchestrator runs, so the :8080 probe and journal checks
    # would false-page every session. Heartbeat watches (options-shadow etc.) stay active.
    if cfg.get("analyst_watch", True):
        ordered = analyze_cycles(recs)
        trail = trailing_timeout(ordered)
        thr = cfg["trigger"]["consecutive_timeout_cycles"]
        # Only a CURRENT stall counts: a trailing-timeout run whose MOST RECENT cycle is recent. Without this a
        # fresh start alerts on hours-old stalls still in today's journal (e.g. an afternoon outage read at a
        # 10pm manual launch). A stale tail clears state silently rather than paging.
        latest_stall_age = _age_seconds(ordered[-1][1]["ts"]) if (ordered and trail["count"] > 0) else 1e9
        journal_down = trail["count"] >= thr and latest_stall_age <= recent_window
        fresh_recovery = bool(ordered and ordered[-1][1].get("responded")
                              and _age_seconds(ordered[-1][1]["ts"]) <= recent_window)

        health_down = False
        if now >= rt["next_probe"]:
            rt["next_probe"] = now + cfg["trigger"]["health_probe_interval_sec"]
            if in_market_hours(cfg) and now >= rt["grace_until"]:
                ok, _ = probe_8080()
                rt["health_fail"] = 0 if ok else rt["health_fail"] + 1
            else:
                rt["health_fail"] = 0
        if rt["health_fail"] >= cfg["trigger"]["health_probe_fails"]:
            health_down = True

        suspected = journal_down or health_down
        if suspected and not st.get("down"):
            if journal_down:
                reason = (f"{trail['count']} consecutive cascade cycles fully TIMED OUT "
                          f"(cycles {trail['cycles']}, {sorted(set(trail['symbols']))})")
            else:
                reason = f"model server :8080 failed {rt['health_fail']} consecutive health probes"
            inc = write_incident(reason, recs, trail)
            when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            body = (f"{reason}\n"
                    f"time: {when} (local)\n"
                    f"incident: runtime/{inc.name}\n"
                    f"action: open the hub http://127.0.0.1:8770/ and read runtime/{inc.name}\n"
                    f"note: trades are fail-closed on a stall -- capital is safe; this is a reliability alert.")
            results = notify(cfg, "ATLAS: model server stall", body)
            st.update({"down": True, "trigger": "journal" if journal_down else "health",
                       "incident": inc.name, "fired_local": when})
            save_state(st)
            print(f"[alert_watch] *** ALERT *** {reason} | {inc.name} | {results}", flush=True)
        elif st.get("down") and not suspected:
            rt["health_fail"] = 0
            # Notify "recovered" ONLY on a FRESH successful cascade -- not when an old stall merely ages out of
            # the freshness window (that would be a spurious recovery ping at night or on restart).
            if fresh_recovery:
                body = (f"analyst responding again (cycle {ordered[-1][0] if ordered else '?'}); "
                        f"earlier incident: runtime/{st.get('incident', '?')}")
                results = notify(cfg, "ATLAS: model server recovered", body)
                print(f"[alert_watch] recovered | {results}", flush=True)
            else:
                print("[alert_watch] prior stall no longer current; clearing state silently", flush=True)
            st.update({"down": False})
            save_state(st)

    # --- Guardian (synthetic-stop) heartbeat: HIGHEST severity - a dead Guardian = a real UNPROTECTED
    # fractional lot (unlike a model stall, where capital is safe). Separate latch; market-hours + grace gated.
    g = cfg.get("guardian", {})
    if g.get("enabled") and in_market_hours(cfg) and now >= rt["grace_until"]:
        status = guardian_status(now, cfg)
        stale = (status is None) or (status["age"] is None) or (status["age"] > g.get("stale_threshold_sec", 30))
        qstale = bool(status and status.get("quote_age") is not None
                      and status["quote_age"] > g.get("quote_stale_threshold_sec", 90))
        guardian_down = stale or qstale
        if guardian_down and not st.get("guardian_down"):
            if status is None or status["age"] is None:
                reason = "Guardian heartbeat MISSING (process not running?)"
            elif stale:
                reason = f"Guardian heartbeat STALE ({status['age']:.0f}s old)"
            else:
                reason = f"Guardian quotes STALE ({status['quote_age']:.0f}s) - MCP reads wedged"
            inc = write_guardian_incident(reason, status)
            when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            body = (f"GUARDIAN DOWN - fractional lots may be UNPROTECTED.\n{reason}\n"
                    f"time: {when} (local)\nincident: runtime/{inc.name}\n"
                    f"action: restart scripts/run_guardian.py and verify positions at Robinhood NOW.")
            results = notify(cfg, "ATLAS: GUARDIAN DOWN (positions unprotected)", body)
            st.update({"guardian_down": True, "guardian_incident": inc.name, "guardian_fired_local": when})
            save_state(st)
            print(f"[alert_watch] *** GUARDIAN ALERT *** {reason} | {inc.name} | {results}", flush=True)
        elif st.get("guardian_down") and not guardian_down:
            results = notify(cfg, "ATLAS: Guardian recovered",
                             f"Guardian heartbeat fresh again (watching {status['watching'] if status else '?'}).")
            st.update({"guardian_down": False})
            save_state(st)
            print(f"[alert_watch] guardian recovered | {results}", flush=True)

    # --- Telegram failsafe-bot heartbeat: MEDIUM severity - a stale beacon means the remote /halt button
    # is unreachable (bot process dead OR Telegram down). Open positions stay Guardian-protected; the loss
    # is the ability to remotely STOP NEW buys. Separate latch; market-hours + grace gated.
    tg = cfg.get("telegram", {})
    if tg.get("enabled") and in_market_hours(cfg) and now >= rt["grace_until"]:
        status = telegram_status(now, cfg)
        stale = (status is None) or (status["age"] is None) or (status["age"] > tg.get("stale_threshold_sec", 120))
        if stale and not st.get("telegram_down"):
            reason = ("Telegram bot heartbeat MISSING (process not running?)"
                      if (status is None or status["age"] is None)
                      else f"Telegram bot heartbeat STALE ({status['age']:.0f}s old)")
            inc = write_telegram_incident(reason, status)
            when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            body = (f"REMOTE /halt FAILSAFE OFFLINE - {reason}\n"
                    f"time: {when} (local)\n"
                    f"note: open positions are STILL protected by the Guardian; you have lost the ability to "
                    f"remotely STOP NEW purchases.\n"
                    f"action: restart scripts/telegram_bot.py (or relaunch). incident: runtime/{inc.name}")
            results = notify(cfg, "ATLAS: Telegram failsafe OFFLINE (can't remote-halt)", body)
            st.update({"telegram_down": True, "telegram_incident": inc.name, "telegram_fired_local": when})
            save_state(st)
            print(f"[alert_watch] *** TELEGRAM ALERT *** {reason} | {inc.name} | {results}", flush=True)
        elif st.get("telegram_down") and not stale:
            lc = status["raw"].get("linked_chat") if status else "?"
            results = notify(cfg, "ATLAS: Telegram failsafe back online",
                             f"Telegram bot heartbeat fresh again (linked_chat={lc}).")
            st.update({"telegram_down": False})
            save_state(st)
            print(f"[alert_watch] telegram bot recovered | {results}", flush=True)

    # --- Options-shadow heartbeat (2026-07-09): MEDIUM severity - no capital at risk; a stale beacon
    # means the day's shadow EVIDENCE stops accumulating. Same latch pattern as the bot.
    osw = cfg.get("options_shadow", {})
    if osw.get("enabled") and in_market_hours(cfg) and now >= rt["grace_until"]:
        hb_path = RUNTIME / osw.get("heartbeat_file", "options_shadow_heartbeat.json")
        try:
            raw = json.loads(hb_path.read_text(encoding="utf-8"))
            age = now - float(raw.get("ts_epoch") or 0.0)
        except (OSError, ValueError, json.JSONDecodeError):
            raw, age = None, None
        stale = age is None or age > osw.get("stale_threshold_sec", 180)
        if stale and not st.get("options_shadow_down"):
            reason = ("options-shadow heartbeat MISSING (process not running?)" if age is None
                      else f"options-shadow heartbeat STALE ({age:.0f}s old)")
            results = notify(cfg, "ATLAS: options shadow OFFLINE (evidence gap)",
                             f"{reason}\nnote: ZERO capital at risk - the shadow ledger is simply not "
                             f"recording. action: restart scripts/run_options_shadow.py")
            st.update({"options_shadow_down": True})
            save_state(st)
            print(f"[alert_watch] *** OPTIONS-SHADOW ALERT *** {reason} | {results}", flush=True)
        elif st.get("options_shadow_down") and not stale:
            results = notify(cfg, "ATLAS: options shadow back online",
                             "options-shadow heartbeat fresh again.")
            st.update({"options_shadow_down": False})
            save_state(st)
            print(f"[alert_watch] options shadow recovered | {results}", flush=True)
        # data-plane zombie check (2026-07-10 audit find #7): process alive + heartbeating while
        # the FEED is dead (mid-day token death; feed.poll fails open to {}) - open positions sit
        # UNMANAGED and nothing above catches it. Separate latch so process- and data-plane pages
        # never mask each other; daily state reset clears both.
        _et = datetime.now(ZoneInfo("America/New_York"))
        data_reason = options_shadow_data_reason(raw, now, osw, _et.hour * 60 + _et.minute)
        if data_reason and not st.get("options_shadow_data_down"):
            results = notify(cfg, "ATLAS: options shadow DATA-PLANE DEAD (process alive)",
                             f"{data_reason}\nnote: ZERO capital at risk, but exits/evidence are "
                             f"NOT being recorded and open positions are unmanaged. "
                             f"action: check the Tradier token, restart the shadow")
            st.update({"options_shadow_data_down": True})
            save_state(st)
            print(f"[alert_watch] *** OPTIONS-SHADOW DATA ALERT *** {data_reason} | {results}", flush=True)
        elif st.get("options_shadow_data_down") and data_reason is None:
            st.update({"options_shadow_data_down": False})
            save_state(st)
            if options_shadow_tick_fresh(raw, now, osw):
                results = notify(cfg, "ATLAS: options shadow data plane recovered",
                                 "quotes flowing again.")
                print(f"[alert_watch] options shadow data plane recovered | {results}", flush=True)
            else:
                # reason evaporated without proof of flow (close boundary / process death):
                # clear the latch silently - never claim recovery that never happened
                print("[alert_watch] options shadow data-plane latch cleared silently "
                      "(no fresh tick to confirm recovery)", flush=True)

    # --- News-flag tap heartbeat (2026-07-11, opts-svc-news-flag-tap-v1): stage-0 enrichment
    # service (C6 headline classifier). A dead tap costs headline-flag EVIDENCE only - the
    # shadow's marks/entries are unaffected. Same latch pattern, own key.
    nfw = cfg.get("news_flags", {})
    if nfw.get("enabled") and in_market_hours(cfg) and now >= rt["grace_until"]:
        nf_path = RUNTIME / nfw.get("heartbeat_file", "news_flags_heartbeat.json")
        try:
            raw_nf = json.loads(nf_path.read_text(encoding="utf-8"))
            age_nf = now - float(raw_nf.get("ts_epoch") or 0.0)
        except (OSError, ValueError, json.JSONDecodeError):
            raw_nf, age_nf = None, None
        stale_nf = age_nf is None or age_nf > nfw.get("stale_threshold_sec", 300)
        if stale_nf and not st.get("news_flags_down"):
            reason = ("news-flag tap heartbeat MISSING (process not running?)" if age_nf is None
                      else f"news-flag tap heartbeat STALE ({age_nf:.0f}s old)")
            results = notify(cfg, "ATLAS: news-flag tap OFFLINE (enrichment gap)",
                             f"{reason}\nnote: headline classification stopped - stage-0 flag "
                             f"evidence only; the shadow trades unaffected. "
                             f"action: restart scripts/news_flag_tap.py")
            st.update({"news_flags_down": True})
            save_state(st)
            print(f"[alert_watch] *** NEWS-FLAG ALERT *** {reason} | {results}", flush=True)
        elif st.get("news_flags_down") and not stale_nf:
            results = notify(cfg, "ATLAS: news-flag tap back online",
                             "news-flag heartbeat fresh again.")
            st.update({"news_flags_down": False})
            save_state(st)
            print(f"[alert_watch] news-flag tap recovered | {results}", flush=True)

    # --- Trading-state halt: the kill switch is the system's most severe action, and until 2026-07-01 it
    # fired in TOTAL SILENCE (the 06-30 phantom DISABLED_REVIEW buzzed nobody). Two complementary checks:
    # (a) a fresh 'halt' journal event -> urgent push with its detail; (b) the persisted trading_state is
    # halted during market hours (catches a halt that happened while this daemon was down). One latch per
    # day per state value.
    if cfg.get("analyst_watch", True) and cfg["trigger"].get("halt_alerts", True):
        halts = [r for r in recs if r.get("event_type") == "halt"]
        fresh_halt = next((r for r in reversed(halts)
                           if _age_seconds(str(r.get("ts", ""))) <= max(recent_window, 3600)), None)
        halted_state = None
        try:
            ts_state = json.loads(RISK_STATE_FILE.read_text(encoding="utf-8")).get("trading_state")
            if ts_state in ("HALTED_DAY", "DISABLED_REVIEW") and in_market_hours(cfg):
                halted_state = ts_state
        except Exception:  # noqa: BLE001 - unreadable state file is the app's problem, not ours
            pass
        key = None
        if fresh_halt is not None:
            key = f"halt:{fresh_halt.get('ts', '')}"
        elif halted_state:
            key = f"halted_state:{halted_state}:{today}"
        if key and st.get("halt_alerted") != key:
            detail = (fresh_halt or {}).get("detail") or f"trading_state={halted_state}"
            when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            body = (f"TRADING HALTED - {detail}\n"
                    f"time: {when} (local)\n"
                    f"action: open http://127.0.0.1:8770/ ; if this is a false positive (e.g. a cash "
                    f"withdrawal), review runtime/risk_state.runtime.json before re-enabling.\n"
                    f"note: no NEW entries will be taken until this clears; existing stops stay live.")
            results = notify(cfg, "ATLAS: TRADING HALTED", body)
            st.update({"halt_alerted": key})
            save_state(st)
            print(f"[alert_watch] *** HALT ALERT *** {detail} | {results}", flush=True)

    # --- Broker order rejections (2026-07-02: Robinhood silently 400-rejected EVERY order all day - 
    # investor-profile questionnaire required - and nothing buzzed). Two or more same-day API-error
    # rejects -> one urgent push per day, with the broker's own message so the user knows what to fix.
    api_rejects = [r for r in recs if r.get("event_type") == "rejected_proposal"
                   and str((r.get("risk_decision") or {}).get("reject_reason", "")).startswith("API error")]
    if cfg.get("analyst_watch", True) and len(api_rejects) >= 2 and st.get("broker_reject_alerted") != today:
        last_reason = str((api_rejects[-1].get("risk_decision") or {}).get("reject_reason", ""))[:280]
        when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        body = (f"{len(api_rejects)} orders REJECTED by Robinhood today - the funnel is approving trades "
                f"but the BROKER is refusing them.\n"
                f"last reason: {last_reason}\n"
                f"time: {when} (local)\n"
                f"action: open the Robinhood APP on the Agentic account and complete whatever it asks "
                f"(e.g. investor-profile questions). No push notification comes from RH for this - it is "
                f"an in-app prompt. Orders resume as soon as it's done.")
        results = notify(cfg, "ATLAS: broker REJECTING orders (action needed)", body)
        st.update({"broker_reject_alerted": today})
        save_state(st)
        print(f"[alert_watch] *** BROKER-REJECT ALERT *** x{len(api_rejects)} | {results}", flush=True)

    # --- App liveness: the orchestrator prints every cycle (even idle ones sleep <=25s), so a session log
    # that was written today and then goes quiet for minutes during market hours = the app is dead or hung
    # (the 06-30 and 07-01 crashes were 27-33 min of exactly this, with zero notification because the
    # launcher also killed this alerter - fixed in launch_live_day.ps1 the same day).
    silent_min = float(cfg["trigger"].get("app_log_silent_min", 10))
    if cfg.get("analyst_watch", True) and silent_min > 0 and in_market_hours(cfg) and now >= rt["grace_until"]:
        app_dead = False
        try:
            # NEWEST session log: the launcher's crash-restart writes live_day.restartN.out.log, so
            # pinning the original name would page a false APP-SILENT ~10 min after every restart.
            logs = sorted(RUNTIME.glob("live_day*.out.log"), key=lambda p: p.stat().st_mtime)
            mtime = logs[-1].stat().st_mtime if logs else 0.0
            wrote_today = bool(logs) and datetime.fromtimestamp(mtime).date().isoformat() == today
            app_dead = wrote_today and (now - mtime) > silent_min * 60
        except OSError:
            pass                                        # no log at all -> launcher never ran; stay quiet
        if app_dead and not st.get("app_silent"):
            age_min = (now - mtime) / 60.0
            when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            body = (f"APP SILENT - live_day.out.log last written {age_min:.0f} min ago during market hours.\n"
                    f"time: {when} (local)\n"
                    f"action: the orchestrator likely crashed. Check runtime/live_day.err.log, then relaunch "
                    f"scripts/launch_live_day.ps1. If fractional lots are open, verify the Guardian is up NOW.")
            results = notify(cfg, "ATLAS: app appears DOWN", body)
            st.update({"app_silent": True})
            save_state(st)
            print(f"[alert_watch] *** APP-SILENT ALERT *** ({age_min:.0f}m) | {results}", flush=True)
        elif st.get("app_silent") and not app_dead:
            st.update({"app_silent": False})
            save_state(st)
            print("[alert_watch] app log fresh again", flush=True)


# ---------------------------------------------------------------- modes
def run_daemon(cfg: dict) -> int:
    if not cfg.get("enabled", True):
        print("[alert_watch] disabled in config; exiting.", flush=True)
        return 0
    st = load_state()
    rt = {"health_fail": 0, "next_probe": 0.0, "grace_until": time.time() + cfg["trigger"]["startup_grace_sec"]}
    print(f"[alert_watch] up. trigger={cfg['trigger']['consecutive_timeout_cycles']} timeout-cycles "
          f"OR {cfg['trigger']['health_probe_fails']} health-fails | "
          f"ntfy={'on:'+(cfg['ntfy'].get('topic','') or 'UNSET') if cfg['ntfy'].get('enabled') else 'off'} "
          f"email={'on->'+(cfg['email'].get('to','') or 'UNSET') if cfg['email'].get('enabled') else 'off'}",
          flush=True)
    while True:
        try:
            evaluate(cfg, st, rt)
        except Exception as exc:  # noqa: BLE001
            print(f"[alert_watch] poll error: {type(exc).__name__}: {exc}", flush=True)
        time.sleep(cfg["poll_interval_sec"])


def run_self_test(cfg: dict) -> int:
    recs = load_today_records()
    ordered = analyze_cycles(recs)
    trail = trailing_timeout(ordered)
    thr = cfg["trigger"]["consecutive_timeout_cycles"]
    print(f"[self-test] today={local_today()}  cycles-reaching-analyst={len(ordered)}")
    for c, d in ordered:
        tag = "TIMEOUT-ALL" if _fully_timed_out(d) else ("responded" if d["responded"] else "?")
        print(f"   cycle {c}: {tag:12} reasons={d['reasons']} symbols={sorted(set(d['symbols']))}")
    recent_window = cfg["trigger"].get("recent_stall_window_sec", 600)
    age = _age_seconds(ordered[-1][1]["ts"]) if (ordered and trail["count"] > 0) else 1e9
    fired = trail["count"] >= thr and age <= recent_window
    print(f"[self-test] trailing fully-timed-out run = {trail['count']} (threshold {thr}); "
          f"latest-stall age {age:.0f}s (freshness window {recent_window}s) "
          f"-> WOULD {'FIRE' if fired else 'stay silent'}")
    print(f"[self-test] ntfy topic set: {bool((cfg['ntfy'].get('topic') or '').strip()) and 'CHANGE-ME' not in cfg['ntfy'].get('topic','')}; "
          f"email to: {cfg['email'].get('to') or 'UNSET'}")
    print("\n----- incident snapshot that WOULD be written (nothing sent) -----")
    print(build_incident_text("SELF-TEST (no alert sent)", recs, trail))
    return 0


def run_test(cfg: dict) -> int:
    recs = load_today_records()
    trail = trailing_timeout(analyze_cycles(recs))
    inc = write_incident("MANUAL --test (channel verification, not a real outage)", recs, trail)
    body = (f"This is a TEST alert from ATLAS alert_watch.\n"
            f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (local)\n"
            f"incident: runtime/{inc.name}\n"
            f"If you got this on your phone (ntfy) and/or email, the channels work.")
    results = notify(cfg, "ATLAS: TEST alert", body)
    print(f"[test] wrote runtime/{inc.name}")
    for ch, res in results:
        print(f"[test] {ch}: {res}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="ATLAS model-server stall detector + alerter (read-only).")
    ap.add_argument("--self-test", action="store_true", help="detect against today's journal + print the incident; send nothing")
    ap.add_argument("--test", action="store_true", help="send a real test alert + write a real incident (verify channels)")
    ap.add_argument("--once", action="store_true", help="one evaluation pass then exit")
    ap.add_argument("--guardian", action="store_true",
                    help="also watch the synthetic-stop Guardian heartbeat (use when fractional is armed)")
    ap.add_argument("--telegram", action="store_true",
                    help="also watch the Telegram failsafe-bot heartbeat (use when telegram_bot.py is running)")
    ap.add_argument("--options-shadow", action="store_true",
                    help="also watch the options-shadow heartbeat (use when run_options_shadow.py is running)")
    ap.add_argument("--options-only", action="store_true",
                    help="ALL-IN OPTIONS mode (2026-07-10 pivot): disable the equity analyst/"
                         "model-server/halt/broker/app watches (no llama-swap or orchestrator "
                         "runs - the :8080 probe would false-page) and watch the options-shadow "
                         "heartbeat. Equivalent to --options-shadow plus analyst_watch=off.")
    args = ap.parse_args(argv)
    cfg = load_config()
    if args.options_only:
        cfg["analyst_watch"] = False
        cfg.setdefault("options_shadow", {})["enabled"] = True
        cfg.setdefault("news_flags", {})["enabled"] = True
    if args.guardian:
        cfg.setdefault("guardian", {})["enabled"] = True
    if args.telegram:
        cfg.setdefault("telegram", {})["enabled"] = True
    if args.options_shadow:
        cfg.setdefault("options_shadow", {})["enabled"] = True
    if args.self_test:
        return run_self_test(cfg)
    if args.test:
        return run_test(cfg)
    if args.once:
        st = load_state()
        rt = {"health_fail": 0, "next_probe": 0.0, "grace_until": 0.0}
        evaluate(cfg, st, rt)
        return 0
    return run_daemon(cfg)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\n[alert_watch] stopped.", flush=True)
        sys.exit(0)
