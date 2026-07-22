#!/usr/bin/env python
"""ATLAS Runtime Watcher -- a read-only monitoring "hub".

A separate, STDLIB-ONLY process (does NOT import `atlas`, does NOT use the GPU, only READS the
append-only/atomic artifacts under runtime/) that serves a self-refreshing local HTML dashboard:
what the scans return, what reaches the two reasoning models, the models' pass/reject reasoning,
and account/risk/positions/pool state.

    .venv\\Scripts\\python.exe scripts\\watch_hub.py            # then open http://127.0.0.1:8770/

Read-only + decoupled by design: it cannot race or interfere with the live trader (append-only
logs are safe to tail; the state JSONs are written atomically via os.replace). Bound to 127.0.0.1;
serves data, accepts no commands.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter, deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001
    ET = None

# Authoritative scan_id -> (label, archetype, setup_type). Source of truth: config/scanner.yaml.
SCAN_LABELS = {
    "00000000-0000-4000-8000-00000000000a": ("A", "continuation", "momentum_continuation"),
    "00000000-0000-4000-8000-00000000000c": ("B", "breakout", "breakout_with_volume"),
    "00000000-0000-4000-8000-00000000000e": ("C", "pullback", "pullback_in_uptrend"),
    "00000000-0000-4000-8000-000000000010": ("D", "in-play", "breakout_with_volume"),   # 2026-07-03
    # Morning variants (pre-11:00 ET; pace-scaled RVOL bands - 2026-07-01):
    "00000000-0000-4000-8000-00000000000b": ("A", "continuation-am", "momentum_continuation"),
    "00000000-0000-4000-8000-00000000000d": ("B", "breakout-am", "breakout_with_volume"),
    "00000000-0000-4000-8000-000000000011": ("D", "in-play-am", "breakout_with_volume"),  # 2026-07-03
    "00000000-0000-4000-8000-00000000000f": ("C", "pullback-am", "pullback_in_uptrend"),
}
TRADE_EVENTS = {"proposal", "rejected_proposal", "order_submitted", "fill", "exit"}
MAX_DECISIONS = 400
MAX_FEED = 250
MAX_TREND = 40
MAX_RECENT = 30   # rolling 'recently surfaced' survivor list (the scan log persists across rotations)
RH_TAIL_BYTES = 2_000_000


# ------------------------------------------------------------------ helpers ---
def _f(x):
    if x is None:
        return None
    try:
        v = float(str(x).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None
    return v if v == v else None  # drop NaN


def local_today() -> str:
    # The decision journal stamps ts in ET (the trading day), so "today" is the ET calendar date.
    now = datetime.now(ET) if ET is not None else datetime.now().astimezone()
    return now.date().isoformat()


def read_new_lines(path: Path, cur: dict, init_tail: int | None = None) -> list[str]:
    """Incremental byte-offset tail. Returns new COMPLETE lines (raw). A partial trailing line is
    held in cur['carry'] until the next read. Shrink/truncation resets the cursor."""
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if "offset" not in cur:
        cur["offset"] = max(0, size - init_tail) if init_tail else 0
        cur["carry"] = ""
    if size < cur["offset"]:          # rotated / truncated / restarted
        cur["offset"] = 0
        cur["carry"] = ""
    if size <= cur["offset"]:
        return []
    try:
        with path.open("rb") as fh:
            fh.seek(cur["offset"])
            chunk = fh.read()
    except OSError:
        return []
    cur["offset"] += len(chunk)
    text = cur["carry"] + chunk.decode("utf-8", "replace")
    parts = text.split("\n")
    cur["carry"] = parts.pop()        # last element is the (possibly partial) trailing line
    return [p for p in (x.strip() for x in parts) if p]


def load_json(path: Path, cache: dict):
    """Atomic-write-safe read; returns last-good cached value on a torn/absent read."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            val = json.load(fh)
        cache[str(path)] = val
        return val
    except (OSError, json.JSONDecodeError):
        return cache.get(str(path), {})


def market_open():
    if ET is None:
        return None
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= t < 16 * 60


# ------------------------------------------------------------- watcher state ---
class State:
    def __init__(self) -> None:
        self.cursors: dict[str, dict] = {}
        self.json_cache: dict[str, object] = {}
        self.today = local_today()
        self.decisions: dict[str, dict] = {}      # decision_id -> merged decision row
        self.feed: deque = deque(maxlen=MAX_FEED)
        self.scans: dict[str, dict] = {}          # scan_id -> live scan view
        self.recent_survivors: dict[str, dict] = {}   # rolling ticker -> survivor row (persistent scan log)
        self.account: dict = {}
        self.positions_rh: list = []
        self.cycle_lines: deque = deque(maxlen=60)


# ------------------------------------------------------------- journal parse ---
def _verdict(d: dict, et: str):
    rr = d.get("reject_reason", "") or ""
    if et == "fill":
        o = d.get("outcome") or {}
        return "fill", f"{o.get('qty')} @ {o.get('price')}"
    if et == "order_submitted":
        return "order", "order submitted"
    if et == "exit":
        o = d.get("outcome") or {}
        return "exit", f"{o.get('exit_reason')} {o.get('realized_return_pct')}%"
    if et == "rejected_proposal":
        if rr == "analyst_pass":
            return "analyst pass", "analyst declined (action=pass)"
        if rr == "low_confidence":
            return "consensus fail", "below confidence floor"
        if rr.startswith("analyst_error"):
            return "analyst error", rr
        if rr == "already_holding":
            return "held", "already holding"
        return "vetoed", rr or "rejected"
    if et == "proposal":
        c = d.get("consensus") or {}
        return "proposal", f"support {c.get('support')} / conf {c.get('confidence')}"
    return et, ""


def _merge_decision(decisions: dict, rec: dict) -> None:
    did = rec.get("decision_id") or ""
    d = decisions.get(did)
    if d is None:
        d = {"id": did, "symbol": rec.get("symbol", ""), "setup_type": rec.get("setup_type", ""),
             "scores": {}, "bull": "", "bear": "", "uncertainty": "", "risk_flags": [],
             "consensus": None, "escalated": False, "ordered": False, "action": "", "reject_reason": "",
             "outcome": None, "seq": -1, "ts": rec.get("ts", ""), "event_type": rec.get("event_type", "")}
        decisions[did] = d
    lp = rec.get("llm_proposal") or {}
    if lp:
        sc = lp.get("scores") or {}
        d["scores"] = {"technical": sc.get("technical"), "market": sc.get("market"),
                       "news": sc.get("news"), "risk_score": sc.get("risk_score")}
        d["bull"] = lp.get("bull_case") or d["bull"]
        d["bear"] = lp.get("bear_case") or d["bear"]
        d["uncertainty"] = lp.get("uncertainty") or d["uncertainty"]
        if lp.get("risk_flags"):
            d["risk_flags"] = lp["risk_flags"]
        rc = lp.get("recommendation") or {}
        d["action"] = rc.get("action") or d["action"]
        if sc.get("risk_score") is not None or lp.get("risk_flags"):
            d["escalated"] = True
    if rec.get("consensus"):
        d["consensus"] = rec["consensus"]
        d["escalated"] = True
    if rec.get("setup_type"):
        d["setup_type"] = rec["setup_type"]
    rd = rec.get("risk_decision") or {}
    if rd.get("reject_reason"):
        d["reject_reason"] = rd["reject_reason"]
    if rec.get("outcome"):
        d["outcome"] = rec["outcome"]
    d["seq"] = max(d["seq"], int(rec.get("seq", -1)))
    d["ts"] = rec.get("ts", d["ts"])
    if rec.get("event_type") in ("order_submitted", "fill"):
        d["ordered"] = True          # durable: the funnel 'orders' count must survive the later 'exit'
    d["event_type"] = rec.get("event_type", d["event_type"])   # latest event wins for the verdict
    d["verdict"], d["reason_short"] = _verdict(d, d["event_type"])


def _feed_item(rec: dict) -> dict:
    et = rec.get("event_type", "")
    o = rec.get("outcome") or {}
    rd = rec.get("risk_decision") or {}
    # detail-carried events (2026-07-03: the new service events all journal their story in `detail`)
    if et in ("regime_change", "halt", "catalyst_event", "catalyst_triggered", "revisit_set",
              "revisit_triggered", "state_overridden", "equity_flow", "guardian_ack"):
        summ = rec.get("detail", "")
    elif et == "fill":
        summ = f"{o.get('qty')} @ {o.get('price')}"
    elif et == "exit":
        summ = f"{o.get('exit_reason')} {o.get('realized_return_pct')}%"
    elif et == "order_submitted":
        summ = f"{rd.get('sized_units')} sh @ {rd.get('entry_limit')}"
    elif et == "rejected_proposal":
        summ = rd.get("reject_reason", "")
    elif et == "proposal":
        c = rec.get("consensus") or {}
        summ = f"conf {c.get('confidence')}"
    else:
        summ = ""
    return {"ts": rec.get("ts", ""), "symbol": rec.get("symbol", ""), "et": et, "summary": str(summ)}


def parse_journal(state: State, root: Path) -> None:
    path = root / "decision_journal.jsonl"
    td = local_today()
    if td != state.today:                       # new trading day -> reset
        state.today = td
        state.decisions.clear()
        state.feed.clear()
        state.cursors.pop(str(path), None)
    cur = state.cursors.setdefault(str(path), {})
    for line in read_new_lines(path, cur):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (rec.get("ts", "")[:10]) != td:      # journal ts is local-offset -> ts[:10] is local date
            continue
        state.feed.append(_feed_item(rec))
        if rec.get("event_type") in TRADE_EVENTS and rec.get("decision_id"):
            _merge_decision(state.decisions, rec)


def _scan_row(row: dict) -> dict:
    cols = row.get("columns") or {}
    last, vol = _f(cols.get("Last")), _f(cols.get("Volume"))
    return {"ticker": (row.get("ticker") or cols.get("Symbol") or "").upper(),
            "last": last, "pct": _f(cols.get("% Change")),
            "rvol": _f(cols.get("Relative volume")), "mktcap": _f(cols.get("Market cap")),
            "dollar_vol": (last * vol) if (last and vol) else None}


def _scan_survivors(rows: list) -> list:
    survs = [_scan_row(row) for row in (rows or [])[:40]]
    survs.sort(key=lambda s: s["dollar_vol"] or 0.0, reverse=True)
    return survs[:15]


def _remember_survivors(state: State, label: str, survivors: list, ts: str) -> None:
    """Accumulate survivors into a ROLLING, deduped (by ticker), newest-last list so the dashboard shows a
    stable 'recently surfaced' log - instead of the per-scan view that collapses to empty as the 3 scans
    rotate (most individual scans find 0 names at any instant). Capped at MAX_RECENT."""
    for row in survivors or []:
        tk = row.get("ticker")
        if not tk:
            continue
        state.recent_survivors.pop(tk, None)                  # re-insert at the end = newest
        state.recent_survivors[tk] = {**row, "scan": label, "last_seen": ts}
    while len(state.recent_survivors) > MAX_RECENT:           # drop the oldest
        state.recent_survivors.pop(next(iter(state.recent_survivors)))


def _salvage_rows(line: str) -> list:
    """Pull the COMPLETE row objects out of a TRUNCATED run_scan results array (brace-depth scan, string-
    aware so braces inside names don't fool it). The final cut-off row is skipped -> real survivors from an
    oversized log line."""
    i = line.find('"results"')
    i = line.find('[', i) if i >= 0 else -1
    if i < 0:
        return []
    rows, depth, start, in_str, esc = [], 0, -1, False, False
    for j in range(i + 1, len(line)):
        ch = line[j]
        if esc:
            esc = False
        elif ch == '\\':
            esc = True
        elif ch == '"':
            in_str = not in_str
        elif in_str:
            pass
        elif ch == '{':
            if depth == 0:
                start = j
            depth += 1
        elif ch == '}' and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    rows.append(json.loads(line[start:j + 1]))
                except json.JSONDecodeError:
                    pass
                start = -1
    return rows


def _salvage_scan_ts(state: State, line: str) -> None:
    """A run_scan line whose payload was TRUNCATED in the log still carries ts/scan_id/total_items at the
    FRONT and the COMPLETE rows before the cut. Recover them so the panel stays CURRENT (fresh ts + count +
    the survivors we can parse) instead of silently freezing. See rh_mcp_client's line cap."""
    import re
    if '"run_scan"' not in line:
        return
    sid = re.search(r'"scan_id":\s*"([0-9a-fA-F-]{8,})"', line)
    ts = re.search(r'"ts":\s*"([^"]+)"', line)
    if not (sid and ts):
        return
    s = sid.group(1)
    label, arche, setup = SCAN_LABELS.get(s, ("?", "other:" + s[:8], ""))
    sc = state.scans.setdefault(s, {"trend": deque(maxlen=MAX_TREND)})
    sc.update(id=s, label=label, archetype=arche, setup=setup, ts=ts.group(1), truncated=True)
    rows = _salvage_rows(line)
    if rows:
        sc["survivors"] = _scan_survivors(rows)
        _remember_survivors(state, label, sc["survivors"], ts.group(1))
    tot = re.search(r'"total_items":\s*(\d+)', line)
    if tot:
        sc["total_items"] = int(tot.group(1))
        sc["trend"].append(int(tot.group(1)))


def parse_rh_mcp(state: State, root: Path) -> None:
    path = root / "rh_mcp.log"
    cur = state.cursors.setdefault(str(path), {})
    for line in read_new_lines(path, cur, init_tail=RH_TAIL_BYTES):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            _salvage_scan_ts(state, line)   # oversized/truncated run_scan -> keep its ts + count fresh
            continue
        tool = rec.get("tool", "")
        data = ((rec.get("result") or {}).get("data") or {})
        ts = rec.get("ts", "")
        if tool == "run_scan":                  # branch on parsed tool (the result guide names other tools)
            r = data.get("result") or {}
            sid = (rec.get("args") or {}).get("scan_id", "")
            label, arche, setup = SCAN_LABELS.get(sid, ("?", "other:" + sid[:8], ""))
            sc = state.scans.setdefault(sid, {"trend": deque(maxlen=MAX_TREND)})
            survs = _scan_survivors(r.get("results"))
            sc.update(id=sid, label=label, archetype=arche, setup=setup, truncated=False,
                      total_items=r.get("total_items"), ts=ts, survivors=survs)
            _remember_survivors(state, label, survs, ts)
            if r.get("total_items") is not None:
                sc["trend"].append(r["total_items"])
        elif tool == "get_portfolio":
            bp = data.get("buying_power")
            state.account = {"value": _f(data.get("total_value")), "cash": _f(data.get("cash")),
                             "buying_power": _f(bp.get("buying_power")) if isinstance(bp, dict) else _f(bp),
                             "ts": ts}
        elif tool == "get_equity_positions":
            state.positions_rh = data.get("positions") or []


def parse_cycle_log(state: State, root: Path) -> None:
    # Tail the NEWEST session log (restart rotation writes live_day.restartN.out.log); per-path
    # cursors mean switching files after a restart picks up the new one from its start.
    try:
        logs = sorted(root.glob("live_day*.out.log"), key=lambda p: p.stat().st_mtime)
    except OSError:
        logs = []
    target = logs[-1] if logs else (root / "live_day.out.log")
    cur = state.cursors.setdefault(str(target), {})
    for line in read_new_lines(target, cur):
        if line.startswith("[cycle "):
            state.cycle_lines.append(line)


def _newest_app_log_age_sec(root: Path) -> "float | None":
    """Age of the NEWEST live_day*.out.log - the launcher's crash-restart rotates to
    live_day.restartN.out.log, so the original name alone would read stale after any restart."""
    try:
        logs = sorted(root.glob("live_day*.out.log"), key=lambda p: p.stat().st_mtime)
        return _file_age_sec(logs[-1]) if logs else None
    except OSError:
        return None


def _file_age_sec(path: Path) -> "float | None":
    try:
        import os as _os
        return round(max(0.0, time.time() - _os.stat(path).st_mtime), 1)
    except OSError:
        return None


def _guardian_view(root: Path) -> dict:
    """Read-only Guardian card: heartbeat age, what it watches, and the published stop levels - 
    the sole supervisor of every lot was previously invisible to the dashboard."""
    hb = load_json_nocache(root / "guardian_heartbeat.json") or {}
    stops = load_json_nocache(root / "synthetic_stops.json") or {}
    age = None
    try:
        age = round(max(0.0, time.time() - float(hb.get("ts_epoch"))), 1)
    except (TypeError, ValueError):
        pass
    return {"hb_age_sec": age, "watching": hb.get("watching_count"),
            "positions": stops.get("positions") or {}}


def load_json_nocache(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _catalyst_view(root: Path) -> dict:
    """Read-only catalyst-pipeline card (2026-07-03): live event book + armed watches + the
    pipeline's own service snapshot (mode, per-feed breaker errors). Sources:
    runtime/catalyst_state.json + runtime/catalyst_watches.json (both atomic single-writer)."""
    state = load_json_nocache(root / "catalyst_state.json") or {}
    watches = load_json_nocache(root / "catalyst_watches.json") or {}
    snap = state.get("snapshot") or {}
    events = []
    for rec in (state.get("events") or {}).values():
        e = rec.get("event") or {}
        events.append({"symbol": e.get("symbol"), "kind": e.get("kind"),
                       "magnitude": e.get("magnitude"), "status": rec.get("status"),
                       "source_ts": (e.get("source_ts_iso") or "")[:16],
                       "headline": (e.get("headline") or "")[:160]})
    events.sort(key=lambda x: x.get("source_ts") or "", reverse=True)
    return {"events": events[:20], "event_count": len(events),
            "mode": snap.get("mode"), "feeds": snap.get("feeds") or [],
            "dropped_unverified": snap.get("dropped_unverified"),
            "watches": [{"symbol": w.get("symbol"), "level": w.get("level"),
                         "rvol_min": w.get("rvol_min"), "note": (w.get("note") or "")[:60]}
                        for w in (watches.get("watches") or [])][:20]}


def _news_intel_view(root: Path) -> dict:
    """Read-only C6 news-flag card (2026-07-11, opts-svc-news-flag-tap-v1): tap heartbeat age +
    today's newest classified flags. Stage-0 evidence - gates nothing. Missing files =>
    empty-but-safe (the hub must render before the tap's first write)."""
    hb = load_json_nocache(root / "news_flags_heartbeat.json") or {}
    age = None
    try:
        ts = float(hb.get("ts_epoch") or 0.0)
        age = round(time.time() - ts, 1) if ts > 0 else None
    except (TypeError, ValueError):
        age = None
    flags: list = []
    try:
        lines = (root / "news_flags.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines()[-200:]
        today = datetime.now().astimezone().date().isoformat()
        for ln in lines:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if str(r.get("headline_ts") or "").startswith(today):
                flags.append({k: r.get(k) for k in
                              ("headline_ts", "symbol", "kind", "shock",
                               "direction", "materiality", "engine")})
    except OSError:
        pass
    return {"heartbeat_age_sec": age, "flags_today": len(flags),
            "groq_fail_streak": hb.get("groq_fail_streak"),
            "flags": flags[-12:][::-1]}


_OPS_CACHE: dict = {"ts": 0.0, "data": None}


def _ops_view(root: Path) -> dict:
    """Ops-schedule card (2026-07-11 task cutover): every ATLAS-* scheduled task (state + next
    fire), llama-swap health + resident model, and per-service heartbeat ages. Strictly
    read-only. The schtasks query + :8080 probes are cached ~60s so the 2s poll loop stays
    cheap; heartbeat ages are fresh every snapshot (they ARE the liveness signal)."""
    now = time.time()
    cached = _OPS_CACHE["data"]
    if cached is not None and now - _OPS_CACHE["ts"] < 60.0:
        data = dict(cached)
    else:
        tasks: list = []
        try:
            proc = subprocess.run(["schtasks", "/query", "/fo", "CSV", "/nh"],
                                  capture_output=True, text=True, timeout=10)
            for row in csv.reader((proc.stdout or "").splitlines()):
                if len(row) >= 3 and row[0].startswith("\\ATLAS-"):
                    tasks.append({"name": row[0].lstrip("\\"),
                                  "next_run": row[1].strip(), "status": row[2].strip()})
        except Exception:  # noqa: BLE001 - a schtasks hiccup must never break the dashboard
            tasks = []
        tasks.sort(key=lambda t: t["name"])
        seen: set = set()   # multi-trigger tasks can emit one CSV row per trigger
        tasks = [t for t in tasks if not (t["name"] in seen or seen.add(t["name"]))]
        llama: dict = {"up": False, "resident": None}
        try:  # /running names the resident model (llama-swap API)
            with urllib.request.urlopen("http://127.0.0.1:8080/running", timeout=1.5) as resp:
                running = (json.loads(resp.read().decode("utf-8")) or {}).get("running") or []
                llama = {"up": True,
                         "resident": running[0].get("model") if running else None}
        except Exception:  # noqa: BLE001 - older builds: fall back to plain health
            try:
                with urllib.request.urlopen("http://127.0.0.1:8080/v1/models",
                                            timeout=1.5) as resp:
                    llama = {"up": resp.status == 200, "resident": None}
            except Exception:  # noqa: BLE001
                llama = {"up": False, "resident": None}
        data = {"tasks": tasks, "llama": llama}
        _OPS_CACHE["ts"] = now
        _OPS_CACHE["data"] = dict(data)
    beats = []
    for service, fname in (("shadow", "options_shadow_heartbeat.json"),
                           ("news_tap", "news_tap_heartbeat.json"),
                           ("news_sources", "news_sources_heartbeat.json"),
                           ("flag_tap", "news_flags_heartbeat.json"),
                           ("mention_tap", "mention_tap_heartbeat.json"),
                           ("lab", "overnight_lab_heartbeat.json")):
        hb = load_json_nocache(root / fname) or {}
        age = None
        try:
            raw_ts = hb.get("ts_epoch") or hb.get("ts") or 0.0
            ts = (datetime.fromisoformat(str(raw_ts)).timestamp()
                  if isinstance(raw_ts, str) else float(raw_ts))   # news_tap writes ISO ET
            if ts > 0:
                age = round(max(0.0, time.time() - ts), 1)
        except (TypeError, ValueError):
            age = None
        beats.append({"service": service, "age_sec": age})
    data["heartbeats"] = beats
    return data


def _symbol_state_view(root: Path) -> dict:
    """Read-only symbol-state card (2026-07-04): active halts / SEC-suspension denylist / SSR
    flags + per-feed breaker health from runtime/symbol_state.json. Missing file => empty-but-safe
    (the hub must render before the first live poll)."""
    st = load_json_nocache(root / "symbol_state.json")
    st = st if isinstance(st, dict) else {}
    age = None
    try:
        age = round(max(0.0, time.time() - float(st.get("generated_epoch"))), 1)
    except (TypeError, ValueError):
        pass
    # isinstance guards: a valid-JSON-but-WRONG-SHAPE artifact (halts as a string/list) must not
    # AttributeError and freeze the whole dashboard on one bad file (the "frozen dashboard" false
    # alarm). Non-dict rows/maps degrade to empty, the rest of the card still renders.
    def _d(x):
        return x if isinstance(x, dict) else {}
    halts_map = _d(st.get("halts"))
    susp_map = _d(st.get("suspensions"))
    ssr_map = _d(st.get("ssr"))
    halts = [{"symbol": s, "code": _d(h).get("code"), "name": (_d(h).get("name") or "")[:40],
              "halt_date": _d(h).get("halt_date")}
             for s, h in sorted(halts_map.items())][:20]
    susp = [{"symbol": s, "released": _d(v).get("released"),
             "name": (_d(v).get("name") or "")[:40]}
            for s, v in sorted(susp_map.items())][:20]
    feeds = st.get("feeds")
    return {"age_sec": age, "halts": halts, "halt_count": len(halts_map),
            "suspensions": susp, "ssr": sorted(ssr_map.keys())[:20],
            "feeds": feeds if isinstance(feeds, list) else [],
            "unresolved": st.get("unresolved_count")}


def _short_context_view(root: Path) -> dict:
    """Read-only FINRA short-context card (2026-07-04): which day's file is loaded + coverage.
    Per-symbol features surface in the LLM prompt, not here (12k rows)."""
    st = load_json_nocache(root / "short_context.json")
    st = st if isinstance(st, dict) else {}
    by_sym = st.get("by_symbol")
    return {"data_date": st.get("data_date") or "",
            "symbols": len(by_sym) if isinstance(by_sym, dict) else 0}


def _services_view(root: Path, framework_root: Path) -> dict:
    """One card per ADDED SERVICE (2026-07-03 user request): what each source found today + its
    health. Strictly read-only: runtime artifacts + config file PRESENCE (never secret values)."""
    out: dict = {"catalysts": _catalyst_view(root)}
    out["symbol_state"] = _symbol_state_view(root)
    out["short_context"] = _short_context_view(root)
    # RS-leader sleeve: the pre-market 12-1 table is its whole input - show today's top leaders.
    rs = load_json_nocache(root / "rs_table.json")
    if isinstance(rs, dict) and rs:
        top = sorted(rs.items(), key=lambda kv: -float(kv[1]))[:8]
        out["rs_sleeve"] = {"table_size": len(rs),
                            "leaders": [{"symbol": k, "pct": round(float(v), 1)} for k, v in top],
                            "table_age_sec": _file_age_sec(root / "rs_table.json")}
    else:
        out["rs_sleeve"] = {"table_size": 0, "leaders": [],
                            "table_age_sec": _file_age_sec(root / "rs_table.json")}
    # Revisit queue: pending analyst re-look watches.
    rv = load_json_nocache(root / "revisit_state.json") or {}
    out["revisit"] = {"watches": [{"symbol": w.get("symbol"), "kind": w.get("kind"),
                                   "level": w.get("level"), "direction": w.get("direction")}
                                  for w in (rv.get("watches") or [])][:20]}
    # Tradier data path: config presence (existence only - the hub never reads the token). Probe the
    # shadow's DEDICATED token file FIRST, then the equity fallback - mirrors run_options_shadow's
    # own order (opts-fix-hub-tradier-token-v1), so a shadow on tradier_shadow.local.yaml with no
    # equity tradier.local.yaml no longer renders a false "absent".
    tconf = ((framework_root / "config" / "tradier_shadow.local.yaml").exists()
             or (framework_root / "config" / "tradier.local.yaml").exists())
    tline = ""
    try:
        for ln in (root / "guardian.log").read_text("utf-8").splitlines()[::-1]:
            if "quote source" in ln:
                tline = ln[-140:]
                break
    except OSError:
        pass
    out["tradier"] = {"configured": tconf, "guardian_line": tline}
    # Slippage telemetry (own-fill cost curve) lives beside these services too.
    out["slippage"] = _slippage_view(root)
    return out


def _slippage_view(root: Path) -> dict:
    """Aggregate runtime/slippage_telemetry.jsonl (one row per first entry fill, written by the
    orchestrator) into per-price-tier effective-spread stats - the OWN-DATA cost curve that will
    replace the literature-calibrated backtest model. Read-only tail; tolerant of a missing file."""
    path = root / "slippage_telemetry.jsonl"
    tiers = {"<=10": [], "10-20": [], ">20": []}
    n = 0
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()[-2000:]
    except OSError:
        return {"n": 0, "tiers": {}}
    for ln in lines:
        try:
            r = json.loads(ln)
            px, eff = float(r["fill_price"]), float(r["eff_half_spread_bps"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        n += 1
        key = "<=10" if px <= 10.0 else ("10-20" if px <= 20.0 else ">20")
        tiers[key].append(eff)
    out = {}
    for k, v in tiers.items():
        if v:
            sv = sorted(v)
            out[k] = {"n": len(v), "mean_bps": round(sum(v) / len(v), 1),
                      "median_bps": round(sv[len(sv) // 2], 1)}
    return {"n": n, "tiers": out}


# ----------------------------------------------------------- snapshot build ---
def build_snapshot(state: State, root: Path) -> dict:
    rs = load_json(root / "risk_state.runtime.json", state.json_cache) or {}
    org = load_json(root / "organizer_state.json", state.json_cache) or {}
    exe = load_json(root / "execution_state.json", state.json_cache) or {}
    rs_tab = load_json(root / "rs_table.json", state.json_cache) or {}

    for sc in state.scans.values():             # enrich survivors with RS percentile
        for s in sc.get("survivors", []):
            s["rs_pct"] = rs_tab.get(s.get("ticker", "")) if isinstance(rs_tab, dict) else None
    for s in state.recent_survivors.values():   # same RS enrichment for the rolling 'recently surfaced' list
        s["rs_pct"] = rs_tab.get(s.get("ticker", "")) if isinstance(rs_tab, dict) else None
    recent = list(state.recent_survivors.values())[::-1]   # newest first

    decisions = sorted(state.decisions.values(), key=lambda d: d["seq"], reverse=True)[:MAX_DECISIONS]
    scans = sorted((_scan_view(sc) for sc in state.scans.values()),
                   key=lambda s: ({"A": 0, "B": 1, "C": 2, "D": 3}.get(s["label"], 9), s["id"]))

    scan_survivors = sum((sc.get("total_items") or 0) for sc in state.scans.values() if sc.get("id") in SCAN_LABELS)
    reached = len(state.decisions)
    proposals = sum(1 for d in state.decisions.values() if d["escalated"])
    orders = sum(1 for d in state.decisions.values() if d.get("ordered"))
    reject_breakdown = Counter(d["reject_reason"] for d in state.decisions.values() if d["reject_reason"])

    pending = exe.get("pending")
    n_pending = len(pending) if isinstance(pending, (list, dict)) else 0
    positions_exe = exe.get("positions") or {}

    header = {
        "cycle_seq": org.get("cycle_seq"),
        "trading_state": rs.get("trading_state"),
        "tier": rs.get("tier"),
        "account": state.account,
        "day_dd": rs.get("day_drawdown_pct"), "week_dd": rs.get("week_drawdown_pct"),
        "trades_used": rs.get("trades_used_today"),
        "deployed_today": rs.get("deployed_today"),
        "day_start_spendable": rs.get("day_start_spendable"),
        "account_regime": (load_json_nocache(root / "account_regime.json") or {}).get("effective"),
        "consec_losses": rs.get("consecutive_losses"), "consec_wins": rs.get("consecutive_wins"),
        "size_multiplier": rs.get("size_multiplier"),
        "n_positions": len(positions_exe), "n_pending": n_pending,
        "regime_risk_off": rs.get("regime_risk_off"), "regime_gate_off": rs.get("regime_gate_off"),
        "cooldown_until": rs.get("cooldown_until"),
        "market_open": market_open(),
        "latest_cycle": state.cycle_lines[-1] if state.cycle_lines else None,
        "cycle_log_state": "live" if state.cycle_lines else "empty",
        # TRADER liveness (2026-07-01 audit: a crashed trader used to render as a green dashboard - 
        # the freshness dot only measured browser->hub fetch age). The app prints every cycle, so the
        # session log's write age IS the app's pulse; the Guardian heartbeat file is the Guardian's.
        "app_log_age_sec": _newest_app_log_age_sec(root),
        "guardian": _guardian_view(root),
    }
    return {
        "meta": {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                 "today": state.today, "errors": []},
        "header": header,
        "scans": scans,
        "recent_survivors": recent,
        "decisions": decisions,
        "funnel": {"scan_survivors": scan_survivors, "reached_models": reached,
                   "proposals": proposals, "orders": orders},
        "reject_breakdown": dict(reject_breakdown.most_common()),
        "positions": {"exe": positions_exe, "rh": state.positions_rh, "pending": pending,
                      "cooldown": org.get("cooldown") or {}},
        "slippage": _slippage_view(root),
        "catalysts": _catalyst_view(root),
        "news_intel": _news_intel_view(root),
        "options": _options_view(root),
        "ops": _ops_view(root),
        "services": _services_view(root, Path(__file__).resolve().parents[1]),
        "pool": org.get("pool") or [],
        "feed": list(state.feed)[::-1],
        "cycle_lines": list(state.cycle_lines)[::-1][:30],
    }


def _options_view(root: Path) -> dict:
    """Read-only OPTIONS-SHADOW surface (opts-hub-options-rebuild-v1): per-lane grader verdicts +
    N-progress from options_shadow_scorecard.json, the falsification quarantines, entry/exit counts,
    and recent lane fires / reval-triggers / no-picks from the journal - the shadow's own decision
    output, which the hub previously never read (audit finding #3). Fail-open to empty."""
    card = load_json_nocache(root / "options_shadow_scorecard.json") or {}
    lanes = {}
    for lane, s in (card.get("lanes") or {}).items():
        if isinstance(s, dict):
            lanes[lane] = {"verdict": s.get("verdict"), "n": s.get("n"), "n_today": s.get("n_today"),
                           "net_worst_mean": s.get("net_worst_mean"),
                           "profit_factor_worst": s.get("profit_factor_worst"),
                           "exit_rule_mix": s.get("exit_rule_mix")}

    def _count(fname: str) -> int:
        try:
            return sum(1 for ln in (root / fname).read_text("utf-8", errors="replace").splitlines()
                       if ln.strip())
        except OSError:
            return 0

    recent: list = []
    try:
        lines = (root / "options_shadow_journal.jsonl").read_text("utf-8", errors="replace").splitlines()
        for ln in lines[-500:]:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("event") in ("reval_trigger", "no_pick", "signal_blackout_skip", "lane_error"):
                recent.append({"event": r.get("event"), "kind": r.get("kind"),
                               "underlying": r.get("underlying") or r.get("symbol"),
                               "underlying_state": r.get("underlying_state")})
    except OSError:
        pass
    return {"lanes": lanes,
            "entries_total": _count("options_shadow_entries.jsonl"),
            "exits_total": _count("options_shadow_exits.jsonl"),
            "malformed_exits": card.get("malformed_exits"),
            "halted_underlying_exits": card.get("halted_underlying_exits"),
            "recent_journal": recent[-15:]}


def _scan_view(sc: dict) -> dict:
    return {"id": sc.get("id", ""), "label": sc.get("label", "?"), "archetype": sc.get("archetype", ""),
            "setup": sc.get("setup", ""), "total_items": sc.get("total_items"), "ts": sc.get("ts"),
            "survivors": sc.get("survivors", []), "trend": list(sc.get("trend", []))}


# ------------------------------------------------------------------- server ---
class SnapshotStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snap: dict = {"meta": {"errors": ["initializing"], "today": local_today()},
                            "header": {}, "scans": [], "recent_survivors": [], "decisions": [], "funnel": {},
                            "reject_breakdown": {}, "positions": {}, "pool": [], "feed": [], "cycle_lines": []}

    def set(self, snap: dict) -> None:
        with self._lock:
            self._snap = snap

    def get_bytes(self) -> bytes:
        with self._lock:
            return json.dumps(self._snap, default=str).encode("utf-8")


def poller(state: State, root: Path, store: SnapshotStore, interval: float) -> None:
    while True:
        errors = []
        for fn in (parse_journal, parse_rh_mcp, parse_cycle_log):
            try:
                fn(state, root)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{fn.__name__}: {type(exc).__name__}: {exc}")
        try:
            snap = build_snapshot(state, root)
            snap["meta"]["errors"] = errors
            store.set(snap)
        except Exception as exc:  # noqa: BLE001
            cur = json.loads(store.get_bytes())
            cur.setdefault("meta", {})["errors"] = errors + [f"build_snapshot: {exc}"]
            store.set(cur)
        time.sleep(interval)


class Handler(BaseHTTPRequestHandler):
    store: SnapshotStore | None = None

    def log_message(self, *a):  # silence default request logging
        return

    def do_GET(self):  # noqa: N802
        route = self.path.split("?")[0]
        if route == "/":
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        elif route == "/data.json":
            self._send(200, "application/json", self.store.get_bytes(), no_store=True)
        elif route == "/healthz":
            self._send(200, "application/json", b'{"ok":true}')
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def _send(self, code, ctype, body, no_store=False):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if no_store:
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="ATLAS read-only runtime watcher (monitoring hub).")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--root", default=None, help="runtime dir (default: <repo>/runtime)")
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parents[1] / "runtime"
    state, store = State(), SnapshotStore()
    Handler.store = store
    threading.Thread(target=poller, args=(state, root, store, args.interval), daemon=True).start()

    try:
        httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print(f"[watch_hub] cannot bind {args.host}:{args.port} -- {exc}. Try --port <other>.")
        return 2
    print(f"[watch_hub] ATLAS monitoring hub -> http://{args.host}:{args.port}/   (root={root})")
    print("[watch_hub] read-only; Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[watch_hub] stopping...")
        httpd.shutdown()
        httpd.server_close()
    return 0


# ----------------------------------------------------------------- the page ---
PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>ATLAS hub</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b0f17;--pan:#111826;--line:#1f2a3c;--ink:#e7eef7;--mut:#8aa0bb;--faint:#5b6e88;
 --grn:#34d399;--red:#f87171;--gold:#f6c560;--teal:#2dd4bf;--blu:#60a5fa;--vio:#a78bfa;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:13px/1.4 'Segoe UI',system-ui,Arial,sans-serif}
.mono{font-family:'Cascadia Mono',Consolas,monospace}
header{position:sticky;top:0;z-index:5;background:linear-gradient(180deg,#0d1422,#0b0f17);
 border-bottom:1px solid var(--line);padding:8px 14px}
.hrow{display:flex;flex-wrap:wrap;align-items:center;gap:7px 16px}
.brand{font-weight:800;letter-spacing:.16em;color:var(--teal);font-size:13px;margin-right:4px}
.stat{font-size:12px;color:var(--mut)} .stat b{color:var(--ink);font-weight:700}
.pill{font-size:10.5px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);background:#0e1626}
.pill.on{color:var(--grn);border-color:#1e5b46} .pill.off{color:var(--faint)}
.pill.red{color:var(--red);border-color:#5b2230} .pill.amber{color:var(--gold);border-color:#5b4a1e}
.fresh{margin-left:auto;font-size:11px;color:var(--faint)} .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--grn);margin-right:5px}
.dot.stale{background:var(--gold)} .dot.dead{background:var(--red)}
.cyc{width:100%;color:var(--faint);font-size:11px;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav{display:flex;gap:4px;padding:8px 14px 0}
.tab{padding:6px 13px;border:1px solid var(--line);border-bottom:none;border-radius:7px 7px 0 0;
 background:#0e1626;color:var(--mut);cursor:pointer;font-size:12.5px}
.tab.active{background:var(--pan);color:var(--ink);font-weight:700}
.tab .n{color:var(--faint);font-weight:400}
#content{background:var(--pan);border:1px solid var(--line);margin:0 14px 14px;border-radius:0 8px 8px 8px;
 padding:10px 12px;min-height:62vh;max-height:calc(100vh - 130px);overflow:auto}
table.t{width:100%;border-collapse:collapse;font-size:12.3px}
table.t th{text-align:left;color:var(--faint);font-weight:600;border-bottom:1px solid var(--line);padding:5px 8px;position:sticky;top:0;background:var(--pan)}
table.t td{padding:5px 8px;border-bottom:1px solid #16202f;vertical-align:top}
tr.row{cursor:pointer} tr.row:hover{background:#0e1828} tr.row.open{background:#0e1a2c}
.sym{font-weight:800} .mut{color:var(--mut)} .reason{color:var(--mut)}
.chip{font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:6px;white-space:nowrap}
.c-pass{background:#1d2433;color:var(--mut)} .c-cons{background:#3a2d12;color:var(--gold)}
.c-err{background:#3a1d22;color:var(--red)} .c-veto{background:#3a1d22;color:var(--red)}
.c-prop{background:#15324a;color:var(--blu)} .c-order{background:#13324a;color:var(--teal)}
.c-fill{background:#143524;color:var(--grn)} .c-exit{background:#2a3142;color:var(--ink)}
.c-held{background:#1d2433;color:var(--faint)} .c-halt{background:#3a1d22;color:var(--red)} .c-regime{background:#2a2342;color:var(--vio)}
.esc{color:var(--gold);font-size:12px} .sc{font-family:Consolas,monospace;font-size:11.5px;color:var(--mut)}
.sc b{color:var(--ink)}
.det td{background:#0a1018;padding:12px 14px} .det h4{margin:0 0 4px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--teal)}
.det .blk{margin-bottom:10px} .det p{margin:0;color:#cdd9e8;font-size:12.4px;line-height:1.5}
.det .bear h4{color:var(--red)} .det .unc h4{color:var(--gold)} .det .aud h4{color:var(--vio)}
.flag{display:inline-block;font-size:10.5px;background:#2a1822;color:var(--red);border:1px solid #5b2230;border-radius:5px;padding:1px 7px;margin:2px 4px 0 0}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.card{flex:1;min-width:230px;background:#0d1626;border:1px solid var(--line);border-radius:9px;padding:11px 13px}
.card h3{margin:0 0 7px;font-size:13px}.card .big{font-size:24px;font-weight:800}
.spark{font-family:monospace;font-size:11px;color:var(--teal);letter-spacing:1px}
.empty{color:var(--faint);padding:26px;text-align:center}
.funnel{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:6px 0 14px}
.fstep{background:#0d1626;border:1px solid var(--line);border-radius:9px;padding:12px 16px;text-align:center;min-width:120px}
.fstep .big{font-size:26px;font-weight:800;color:var(--teal)} .fstep .lbl{font-size:11px;color:var(--faint);margin-top:3px}
.farrow{color:var(--faint);font-size:20px} .note{color:var(--faint);font-size:11.5px;line-height:1.5;border-left:2px solid var(--line);padding-left:10px;margin-top:8px}
.kv{display:inline-block;margin:2px 14px 2px 0;font-size:12px;color:var(--mut)} .kv b{color:var(--ink)}
.feeditem{font-size:12px;padding:3px 0;border-bottom:1px solid #16202f;color:var(--mut)}
.up{color:var(--grn)} .down{color:var(--red)}
/* 2026-07-03 scans/services density rework: merged two-line cells + tighter tables so the widest
   view is <=5 columns and never needs a horizontal scroll. */
table.t.compact th,table.t.compact td{padding:4px 6px;font-size:11.8px}
td.c2 .sub,.sym .sub{display:block;font-size:10.5px;color:var(--faint);font-weight:400;margin-top:1px}
table.t{max-width:100%} #content{overflow-x:auto}
</style></head><body>
<header>
  <div class="hrow" id="hdr"><span class="brand">ATLAS &middot; HUB</span><span class="stat">connecting...</span>
    <span class="fresh" id="fresh"><span class="dot dead"></span>--</span></div>
  <div class="cyc mono" id="cyc"></div>
</header>
<nav id="nav"></nav>
<div id="content"><div class="empty">Loading...</div></div>
<script>
const TABS=[['decisions','Decisions'],['scans','Scans'],['funnel','Funnel'],['positions','Positions'],['services','Services'],['activity','Activity'],['risk','Risk']];
let D=null, activeTab='decisions', lastOk=0;
const expanded=new Set();

function esc(s){return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function hh(ts){try{const d=new Date(ts);return d.toLocaleTimeString('en-GB');}catch(e){return (ts||'').slice(11,19);}}
function ago(iso){if(!iso)return '--';const s=Math.max(0,(Date.now()-new Date(iso).getTime())/1000);return s<90?Math.round(s)+'s':Math.round(s/60)+'m';}
function money(v){if(v==null)return '--';return '$'+Number(v).toLocaleString(undefined,{maximumFractionDigits:2});}
function cap(v){if(v==null)return '--';const a=Math.abs(v);if(a>=1e9)return '$'+(v/1e9).toFixed(1)+'B';if(a>=1e6)return '$'+(v/1e6).toFixed(0)+'M';return '$'+Math.round(v);}
function pct(v){if(v==null)return '--';const p=v*100;return (p>=0?'+':'')+p.toFixed(2)+'%';}
function num(v,d){return v==null?'--':Number(v).toFixed(d==null?2:d);}
function shortSetup(s){return (s||'').replace('_with_volume','').replace('_to_vwap_uptrend','').replace('momentum_','');}
const CHIP={'analyst pass':'c-pass','consensus fail':'c-cons','analyst error':'c-err','vetoed':'c-veto','proposal':'c-prop','order':'c-order','fill':'c-fill','exit':'c-exit','held':'c-held','halt':'c-halt','regime':'c-regime'};
function chip(v){return '<span class="chip '+(CHIP[v]||'c-pass')+'">'+esc(v)+'</span>';}
function scoreCell(s){if(!s)return '<span class="sc">--</span>';const r=s.risk_score!=null?' <span style="color:#a78bfa">R'+s.risk_score+'</span>':'';
  return '<span class="sc"><b>'+(s.technical??'-')+'</b>/'+(s.market??'-')+'/'+(s.news??'-')+r+'</span>';}

function toggle(id){if(expanded.has(id))expanded.delete(id);else expanded.add(id);render();}
window.toggle=toggle;

function viewDecisions(rows){
  if(!rows||!rows.length)return '<div class="empty">No candidates have reached the reasoning models today yet.</div>';
  let h='<table class="t"><thead><tr><th>time</th><th>symbol</th><th>setup</th><th>T/M/N</th><th>verdict</th><th>reason</th></tr></thead><tbody>';
  for(const d of rows){const op=expanded.has(d.id);
    h+='<tr class="row'+(op?' open':'')+'" onclick="toggle(\''+d.id+'\')"><td class="mut mono">'+hh(d.ts)+'</td>'+
       '<td class="sym">'+esc(d.symbol)+'</td><td class="mut">'+esc(shortSetup(d.setup_type))+'</td>'+
       '<td>'+scoreCell(d.scores)+'</td><td>'+chip(d.verdict)+(d.escalated?' <span class="esc" title="auditor ran">⚖</span>':'')+'</td>'+
       '<td class="reason">'+esc(d.reason_short||'')+'</td></tr>';
    if(op)h+='<tr class="det"><td colspan="6">'+detail(d)+'</td></tr>';}
  return h+'</tbody></table>';}

function detail(d){
  let h='<div class="blk"><h4>Bull</h4><p>'+esc(d.bull||'(none)')+'</p></div>'+
        '<div class="blk bear"><h4>Bear</h4><p>'+esc(d.bear||'(none)')+'</p></div>'+
        '<div class="blk unc"><h4>Uncertainty</h4><p>'+esc(d.uncertainty||'(none)')+'</p></div>';
  if(d.escalated){h+='<div class="blk aud"><h4>Auditor</h4><p>risk_score '+(d.scores&&d.scores.risk_score!=null?d.scores.risk_score:'--')+
     ' &middot; flags: '+((d.risk_flags&&d.risk_flags.length)?d.risk_flags.map(f=>'<span class="flag">'+esc(f)+'</span>').join(''):'<span class="mut">none</span>')+'</p></div>';}
  if(d.consensus)h+='<div class="blk"><h4>Consensus</h4><p>support '+num(d.consensus.support)+' &middot; confidence '+num(d.consensus.confidence)+'</p></div>';
  h+='<p class="mut" style="font-size:11px">decision '+esc(d.id)+' &middot; action '+esc(d.action||'--')+(d.reject_reason?' &middot; reject: '+esc(d.reject_reason):'')+'</p>';
  return h;}

// Scans page (2026-07-03 UI rework, user request: no horizontal scrolling). Columns are MERGED
// into stacked two-line cells (price+%chg, cap+$vol, RVOL+RS) so the widest table is 5 columns and
// always fits the viewport; .compact shrinks padding/font a notch on these dense tables.
function cell2(top,bot){return '<td class="mono c2">'+top+'<span class="sub">'+bot+'</span></td>';}
function scanRow(r,withScan){
  let h='<tr><td class="sym">'+esc(r.ticker)+(withScan?'<span class="sub mut">'+esc(r.scan||'')+(r.last_seen?' &middot; '+hh(r.last_seen):'')+'</span>':'')+'</td>';
  h+=cell2(num(r.last),'<span class="'+((r.pct||0)>=0?'up':'down')+'">'+pct(r.pct)+'</span>');
  h+=cell2('RV '+num(r.rvol,1),'RS '+(r.rs_pct!=null?Math.round(r.rs_pct):'--'));
  h+=cell2(cap(r.mktcap),esc(cap(r.dollar_vol))+' $vol');
  return h+'</tr>';}
function viewScans(scans, recent){
  if(!scans||!scans.length)return '<div class="empty">No scan results yet (waiting on the live scanner poll).</div>';
  let h='<div class="cards">';
  for(const s of scans){const sp=(s.trend||[]).slice(-32).map(v=>'▁▂▃▅▆▇'[Math.min(5,Math.floor((v||0)/2))]).join('');
    h+='<div class="card"><h3>'+esc(s.label)+' &middot; '+esc(s.archetype)+'</h3>'+
       '<div class="big">'+(s.total_items??'--')+'<span class="mut" style="font-size:12px"> matches</span></div>'+
       '<div class="spark">'+sp+'</div><div class="mut" style="font-size:11px;margin-top:4px">'+(s.ts?hh(s.ts):'')+'</div></div>';}
  h+='</div>';
  if(recent&&recent.length){
    h+='<h4 style="color:#8aa0bb;margin:10px 0 4px">recently surfaced &middot; '+recent.length+' (rolling, newest first)</h4>'+
       '<table class="t compact"><thead><tr><th>ticker &middot; scan</th><th>last / %chg</th><th>RVOL / RS</th><th>cap / $vol</th></tr></thead><tbody>';
    for(const r of recent)h+=scanRow(r,true);
    h+='</tbody></table>';
  }
  for(const s of scans){if(!s.survivors||!s.survivors.length)continue;
    h+='<h4 style="color:#8aa0bb;margin:10px 0 4px">'+esc(s.label)+' survivors</h4>'+
       '<table class="t compact"><thead><tr><th>ticker</th><th>last / %chg</th><th>RVOL / RS</th><th>cap / $vol</th></tr></thead><tbody>';
    for(const r of s.survivors)h+=scanRow(r,false);
    h+='</tbody></table>';}
  return h;}

function viewServices(d){const sv=d.services||{};let h='';
  const ct=sv.catalysts||{};
  h+='<h4 style="color:#8aa0bb;margin:0 0 6px">catalyst pipeline &middot; mode <b>'+esc(ct.mode||'no snapshot yet (writes on the first live cycle)')+'</b>'
    +(ct.dropped_unverified?' &middot; <span class="mut">'+ct.dropped_unverified+' unverifiable tickers dropped</span>':'')+'</h4>';
  const feeds=ct.feeds||[];
  if(feeds.length){h+='<div style="margin-bottom:6px">';
    for(const f of feeds)h+='<span class="kv">'+esc(f.name)+' <b class="'+(f.breaker_error?'down':'up')+'">'+(f.breaker_error?'ERROR':'ok')+'</b>'+(f.breaker_error?' <span class="mut" style="font-size:10.5px">'+esc(f.breaker_error.slice(0,80))+'</span>':'')+'</span>';
    h+='</div>';}
  const cev=ct.events||[];
  if(cev.length){h+='<table class="t compact"><thead><tr><th>symbol</th><th>finding</th><th>mag</th><th>status</th></tr></thead><tbody>';
    for(const e of cev)h+='<tr><td class="sym">'+esc(e.symbol||'')+'<span class="sub mut">'+esc(e.source_ts||'')+'</span></td><td style="max-width:520px">'+esc(e.headline||e.kind||'')+'</td><td class="mono">'+num(e.magnitude,0)+'</td><td class="mono mut">'+esc(e.status||'')+'</td></tr>';
    h+='</tbody></table>';}
  else h+='<div class="empty" style="padding:10px">No catalyst events in the book (events appear here when a feed finds one; context-only mode shows them to the models but never trades them).</div>';
  const cw=ct.watches||[];
  if(cw.length){h+='<div class="kv" style="margin-top:4px">armed tape-confirmation watches: '+cw.map(w=>esc(w.symbol||'')+' (lvl '+num(w.level)+' / rvol '+num(w.rvol_min,1)+')').join(', ')+'</div>';}
  const ss=sv.symbol_state||{};
  h+='<h4 style="color:#8aa0bb;margin:14px 0 6px">symbol state &middot; halts <b>'+(ss.halt_count||0)+'</b> &middot; suspensions <b>'+((ss.suspensions||[]).length)+'</b> &middot; SSR <b>'+((ss.ssr||[]).length)+'</b>'
    +(ss.age_sec!=null?' <span class="mut">(polled '+Math.round(ss.age_sec)+'s ago)</span>':'')+'</h4>';
  const ssf=ss.feeds||[];
  if(ssf.length){h+='<div style="margin-bottom:6px">';
    for(const f of ssf)h+='<span class="kv">'+esc(f.name)+' <b class="'+(f.breaker_error?'down':'up')+'">'+(f.breaker_error?'ERROR':'ok')+'</b>'+(f.breaker_error?' <span class="mut" style="font-size:10.5px">'+esc(f.breaker_error.slice(0,80))+'</span>':'')+'</span>';
    h+='</div>';}
  if((ss.halts||[]).length){h+='<table class="t compact"><thead><tr><th>halted</th><th>code</th><th>since</th><th>name</th></tr></thead><tbody>';
    for(const x of ss.halts)h+='<tr><td class="sym">'+esc(x.symbol||'')+'</td><td class="mono">'+esc(x.code||'')+'</td><td class="mono">'+esc(x.halt_date||'')+'</td><td class="mut">'+esc(x.name||'')+'</td></tr>';
    h+='</tbody></table>';}
  if((ss.suspensions||[]).length){h+='<div class="kv" style="margin-top:4px">SEC-suspended (denylist): '+ss.suspensions.map(x=>esc(x.symbol)+' (to '+esc(x.released||'?')+')').join(', ')+'</div>';}
  if((ss.ssr||[]).length){h+='<div class="kv" style="margin-top:4px">SSR active (context only - long book unaffected): '+ss.ssr.map(esc).join(', ')+'</div>';}
  if(!(ss.halts||[]).length&&!(ss.suspensions||[]).length&&!(ss.ssr||[]).length)
    h+='<div class="empty" style="padding:10px">No active halts / suspensions / SSR flags in the snapshot. A FRESH halt vetoes discovery + blocks the order guard; stale data fails OPEN (never blocks).</div>';
  const sctx=sv.short_context||{};
  h+='<h4 style="color:#8aa0bb;margin:14px 0 6px">FINRA short context &middot; '+(sctx.symbols?('file '+esc(sctx.data_date)+' &middot; '+sctx.symbols+' symbols'):'no file loaded yet')+'</h4>';
  h+='<div class="note">Context features only (short_vol_ratio / percentile in the LLM prompt); short-horizon predictive value refuted - never a gate.</div>';
  const rs=sv.rs_sleeve||{};
  h+='<h4 style="color:#8aa0bb;margin:14px 0 6px">RS-leader sleeve &middot; 12-1 table: '+(rs.table_size||0)+' names'
    +(rs.table_age_sec!=null?' <span class="mut">(built '+Math.round(rs.table_age_sec/3600)+'h ago)</span>':'')+'</h4>';
  if((rs.leaders||[]).length){h+='<div>';for(const l of rs.leaders)h+='<span class="kv"><b>'+esc(l.symbol)+'</b> '+num(l.pct,1)+'</span>';h+='</div>';
    h+='<div class="note">Top-decile names are injected through the full gate set every ~30 min in scanner mode (setup relative_strength_leader, 21-session trailing leash).</div>';}
  else h+='<div class="empty" style="padding:10px">No RS table (pre-market build did not run - the sleeve is dormant today; -BuildRsTable builds it).</div>';
  const rv=sv.revisit||{};const rvw=rv.watches||[];
  h+='<h4 style="color:#8aa0bb;margin:14px 0 6px">revisit queue &middot; '+rvw.length+' pending re-looks</h4>';
  if(rvw.length){h+='<div>';for(const w of rvw)h+='<span class="kv"><b>'+esc(w.symbol)+'</b> '+esc(w.kind)+(w.level!=null?' '+esc(w.direction||'')+' '+num(w.level):'')+'</span>';h+='</div>';}
  const td=sv.tradier||{};
  h+='<h4 style="color:#8aa0bb;margin:14px 0 6px">tradier data path &middot; <b class="'+(td.configured?'up':'down')+'">'+(td.configured?'configured':'absent')+'</b></h4>';
  h+=td.guardian_line?('<div class="kv mono" style="font-size:11px">'+esc(td.guardian_line)+'</div>')
    :'<div class="mut" style="font-size:11.5px">guardian.log has not declared a quote source yet this session (appears at Guardian startup).</div>';
  const sl=sv.slippage||{};const slt=sl.tiers||{};const slk=Object.keys(slt);
  h+='<h4 style="color:#8aa0bb;margin:14px 0 6px">realized entry slippage &middot; '+(sl.n||0)+' fills recorded</h4>';
  if(slk.length){h+='<table class="t compact"><thead><tr><th>price tier</th><th>fills</th><th>mean bps</th><th>median bps</th></tr></thead><tbody>';
    for(const k of slk){const v=slt[k];h+='<tr><td class="mono">'+esc(k)+'</td><td class="mono">'+v.n+'</td><td class="mono">'+num(v.mean_bps,1)+'</td><td class="mono">'+num(v.median_bps,1)+'</td></tr>';}
    h+='</tbody></table><div class="note">x2 &asymp; round-trip; the backtest cost curve assumes 19/17/9 bps per side by tier - this table is the own-data replacement being accumulated.</div>';}
  return h;}

function viewFunnel(d){const f=d.funnel||{};const steps=[['scan_survivors','scanner survivors'],['reached_models','reached models'],['proposals','to auditor'],['orders','orders']];
  let h='<div class="funnel">';
  steps.forEach((s,i)=>{h+='<div class="fstep"><div class="big">'+(f[s[0]]??0)+'</div><div class="lbl">'+s[1]+'</div></div>';if(i<3)h+='<div class="farrow">→</div>';});
  h+='</div>';
  const rb=d.reject_breakdown||{};const keys=Object.keys(rb);
  if(keys.length){h+='<h4 style="color:#8aa0bb;margin:14px 0 6px">rejections by reason</h4>';
    for(const k of keys)h+='<div class="kv">'+esc(k)+' <b>'+rb[k]+'</b></div>';}
  h+='<div class="note">The first arrow (scanner survivors &rarr; reached models) is a <b>count gap</b> only: per-survivor pre-cascade drop reasons (price&gt;200-SMA, liquidity floor, earnings, 52wk-proximity, cooldown, dedupe) happen inside discovery and are not journaled, so the hub can show how many were dropped but not why each one died.</div>';
  return h;}

function viewPositions(d){const p=d.positions||{};const exe=p.exe||{};const rh=p.rh||[];const pend=p.pending;const cd=p.cooldown||{};
  let h='';
  const exk=Object.keys(exe);
  if(exk.length){h+='<h4 style="color:#8aa0bb;margin:0 0 6px">open positions</h4><table class="t"><thead><tr><th>symbol</th><th>qty</th><th>entry</th><th>stop</th><th>target</th></tr></thead><tbody>';
    for(const k of exk){const m=exe[k]||{};h+='<tr><td class="sym">'+esc(k)+'</td><td class="mono">'+num(m.qty,4)+'</td><td class="mono">'+num(m.entry_price)+'</td><td class="mono">'+num(m.stop)+'</td><td class="mono">'+num(m.target)+'</td></tr>';}
    h+='</tbody></table>';}else h+='<div class="empty" style="padding:14px">No open positions.</div>';
  const pn=Array.isArray(pend)?pend.length:(pend?Object.keys(pend).length:0);
  if(pn)h+='<div class="kv" style="margin-top:8px">in-flight orders <b>'+pn+'</b></div>';
  const poolN=(d.pool||[]).length; h+='<div class="kv" style="margin-top:8px">organizer pool <b>'+poolN+'</b></div>';
  const cdk=Object.keys(cd);if(cdk.length){h+='<h4 style="color:#8aa0bb;margin:12px 0 6px">cooldowns</h4>';for(const k of cdk)h+='<div class="kv mono">'+esc(k)+'</div>';}
  const ct=d.catalysts||{};const cev=ct.events||[];const cw=ct.watches||[];
  if(cev.length||cw.length){h+='<h4 style="color:#8aa0bb;margin:12px 0 6px">catalysts (context for the models; never a ranking input)</h4>';
    if(cev.length){h+='<table class="t"><thead><tr><th>symbol</th><th>kind</th><th>mag</th><th>status</th></tr></thead><tbody>';
      for(const e of cev)h+='<tr><td class="sym">'+esc(e.symbol||'')+'</td><td class="mono">'+esc(e.kind||'')+'</td><td class="mono">'+num(e.magnitude,0)+'</td><td class="mono">'+esc(e.status||'')+'</td></tr>';
      h+='</tbody></table>';}
    if(cw.length){h+='<div class="kv" style="margin-top:4px">armed watches: '+cw.map(w=>esc(w.symbol||'')).join(', ')+'</div>';}}
  const ni=d.news_intel||{};const nif=ni.flags||[];
  if(ni.heartbeat_age_sec!=null||nif.length){h+='<h4 style="color:#8aa0bb;margin:12px 0 6px">news flags (C6 classifier &mdash; stage-0 evidence; gates nothing)</h4>';
    h+='<div class="kv">tap '+(ni.heartbeat_age_sec==null?'<b>offline</b>':'beat '+num(ni.heartbeat_age_sec,0)+'s ago')+' &middot; flags today <b>'+(ni.flags_today||0)+'</b>'+(ni.groq_fail_streak?' &middot; groq fails '+ni.groq_fail_streak:'')+'</div>';
    if(nif.length){h+='<table class="t"><thead><tr><th>ts</th><th>symbol</th><th>kind</th><th>dir</th><th>mat</th><th>engine</th></tr></thead><tbody>';
      for(const f of nif)h+='<tr><td class="mono">'+esc(String(f.headline_ts||'').slice(11,16))+'</td><td class="sym">'+esc(f.symbol||'')+'</td><td class="mono">'+esc(f.kind||'')+(f.shock?' &#9889;':'')+'</td><td class="mono">'+esc(f.direction||'')+'</td><td class="mono">'+num(f.materiality,2)+'</td><td class="mono">'+esc(f.engine||'')+'</td></tr>';
      h+='</tbody></table>';}}
  const ops=d.ops||{};const opt=ops.tasks||[];const oh=(ops.heartbeats||[]).filter(x=>x.age_sec!=null);
  if(opt.length||ops.llama){h+='<h4 style="color:#8aa0bb;margin:12px 0 6px">ops schedule (2026-07-11 cutover &mdash; LiveDay retired; OptionsDay drives weekdays 07:30 CT)</h4>';
    const ll=ops.llama||{};h+='<div class="kv">llama-swap '+(ll.up?'<b style="color:var(--grn)">up</b>'+(ll.resident?' &middot; resident '+esc(ll.resident):' &middot; idle (no model resident)'):'<b style="color:var(--red)">down</b> &middot; start_llama_swap.cmd (auto: logon + weekdays 15:22)')+'</div>';
    if(oh.length){h+='<div class="kv" style="margin-top:4px">heartbeats: '+oh.map(x=>esc(x.service)+' <b>'+num(x.age_sec,0)+'s</b>').join(' &middot; ')+'</div>';}
    if(opt.length){h+='<table class="t"><thead><tr><th>task</th><th>state</th><th>next run</th></tr></thead><tbody>';
      for(const t of opt)h+='<tr><td class="mono">'+esc(t.name)+'</td><td class="mono">'+esc(t.status||'')+(t.name==='ATLAS-LiveDay'?' (retired)':'')+'</td><td class="mono">'+esc(t.next_run||'')+'</td></tr>';
      h+='</tbody></table>';}}
  const sl=d.slippage||{};const slt=sl.tiers||{};const slk=Object.keys(slt);
  if(slk.length){h+='<h4 style="color:#8aa0bb;margin:12px 0 6px">realized entry slippage (eff. half-spread, own fills)</h4>'
    +'<table class="t"><thead><tr><th>price tier</th><th>fills</th><th>mean bps</th><th>median bps</th></tr></thead><tbody>';
    for(const k of slk){const v=slt[k];h+='<tr><td class="mono">'+esc(k)+'</td><td class="mono">'+v.n+'</td><td class="mono">'+num(v.mean_bps,1)+'</td><td class="mono">'+num(v.median_bps,1)+'</td></tr>';}
    h+='</tbody></table><div class="kv mut" style="margin-top:4px">x2 &asymp; round-trip; compare vs backtest cost curve 19/17/9 bps per side</div>';}
  return h||'<div class="empty">--</div>';}

function viewActivity(feed,cyc){let h='';
  if(cyc&&cyc.length){h+='<h4 style="color:#8aa0bb;margin:0 0 6px">cycle log</h4>';for(const l of cyc.slice(0,12))h+='<div class="feeditem mono">'+esc(l)+'</div>';}
  h+='<h4 style="color:#8aa0bb;margin:12px 0 6px">events</h4>';
  if(!feed||!feed.length)return h+'<div class="empty" style="padding:14px">No events today.</div>';
  for(const e of feed)h+='<div class="feeditem"><span class="mono mut">'+hh(e.ts)+'</span> &middot; <b>'+esc(e.symbol)+'</b> &middot; '+esc(e.et)+(e.summary?' &middot; <span class="mut">'+esc(e.summary)+'</span>':'')+'</div>';
  return h;}

function renderHeader(hd,meta){const a=hd.account||{};
  const ts=hd.trading_state||'--';const tsCls=ts==='ACTIVE'?'on':(ts==='REDUCING'?'amber':'red');
  let pills='<span class="pill '+tsCls+'">'+esc(ts)+'</span>';
  pills+='<span class="pill '+(hd.market_open?'on':'off')+'">'+(hd.market_open==null?'mkt ?':(hd.market_open?'market open':'market closed'))+'</span>';
  if(hd.regime_gate_off)pills+='<span class="pill amber">regime risk-off</span>';
  // TRADER pulse (2026-07-01): the freshness dot below only proves the HUB is alive; these prove the
  // TRADER and the GUARDIAN are. App log silent >120s in market hours = the orchestrator is dead/hung.
  if(hd.market_open&&hd.app_log_age_sec!=null&&hd.app_log_age_sec>120)
    pills+='<span class="pill red">APP SILENT '+Math.round(hd.app_log_age_sec/60)+'m</span>';
  const g=hd.guardian||{};
  if(hd.market_open){
    if(g.hb_age_sec==null)pills+='<span class="pill red">GUARDIAN ?</span>';
    else if(g.hb_age_sec>30)pills+='<span class="pill red">GUARDIAN STALE '+Math.round(g.hb_age_sec)+'s</span>';
    else pills+='<span class="pill on">guardian '+(g.watching??0)+' watch</span>';
  }
  if(ts!=='ACTIVE'&&ts!=='--')pills+='<span class="pill red">TRADING BLOCKED</span>';
  if(hd.account_regime)pills+='<span class="pill '+(hd.account_regime==='CASH'?'on':'amber')+'">'+esc(hd.account_regime)+'</span>';
  const items=[
    ['cycle','#'+(hd.cycle_seq??'--')],['value',money(a.value)],['cash',money(a.cash)],
    ['deployed',(hd.deployed_today!=null?money(hd.deployed_today):'--')],
    ['day DD',(hd.day_dd!=null?hd.day_dd.toFixed(2)+'%':'--')],['wk DD',(hd.week_dd!=null?hd.week_dd.toFixed(2)+'%':'--')],
    ['trades',(hd.trades_used??'--')],['pos',(hd.n_positions??0)],['pending',(hd.n_pending??0)]];
  let s='<span class="brand">ATLAS &middot; HUB</span>'+pills;
  for(const [k,v] of items)s+='<span class="stat">'+k+' <b>'+v+'</b></span>';
  const errs=(meta&&meta.errors||[]).filter(e=>e&&e!=='initializing');
  if(errs.length)s+='<span class="pill red" title="'+esc(errs.join(' | '))+'">'+errs.length+' parse err</span>';
  const since=(Date.now()-lastOk)/1000;const dcls=since>10?'dead':(since>6?'stale':'');
  s+='<span class="fresh"><span class="dot '+dcls+'"></span>updated '+(lastOk?Math.round(since)+'s ago':'--')+'</span>';
  document.getElementById('hdr').innerHTML=s;
  const cyc=document.getElementById('cyc');
  cyc.textContent=hd.latest_cycle||(hd.cycle_log_state==='empty'?'(cycle line streams after the next launch picks up python -u)':'');}

function renderNav(){let h='';for(const [id,lbl] of TABS){const n=id==='decisions'&&D?(' <span class="n">'+(D.decisions||[]).length+'</span>'):
   (id==='activity'&&D?(' <span class="n">'+(D.feed||[]).length+'</span>'):'');
   h+='<div class="tab'+(activeTab===id?' active':'')+'" onclick="setTab(\''+id+'\')">'+lbl+n+'</div>';}
  document.getElementById('nav').innerHTML=h;}
function setTab(t){activeTab=t;render();} window.setTab=setTab;

function viewRisk(){
  // The risk controls live in the write-capable control plane on :8771 (clamped to survival rails +
  // audited). We EMBED it here so the hub gains a Risk tab without the read-only hub itself ever taking
  // a write path. Built ONCE and preserved across polls (see render) so the iframe doesn't reload/lose
  // form state every ~2s.
  return '<div style="margin-bottom:8px;color:#8aa0bb;font-size:12px">Risk &amp; control settings &middot; '
    +'changes apply on the <b>next launch</b> (clamped to survival rails &amp; audited; persisted in '
    +'runtime/control_overlay.json). Served by the control plane on :8771 &mdash; if this panel is blank, '
    +'it isn\'t running (start via launch_live_day.ps1 or open_hub.ps1).</div>'
    +'<iframe id="riskframe" src="http://127.0.0.1:8771/" title="Risk controls" '
    +'style="width:100%;height:78vh;border:1px solid #2a3344;border-radius:8px;background:#fff"></iframe>';}

function render(){if(!D)return;renderHeader(D.header||{},D.meta||{});renderNav();
  const el=document.getElementById('content');
  if(activeTab==='risk'){if(!document.getElementById('riskframe'))el.innerHTML=viewRisk();return;}
  const sy=el.scrollTop;let h='';
  if(activeTab==='decisions')h=viewDecisions(D.decisions);
  else if(activeTab==='scans')h=viewScans(D.scans, D.recent_survivors||[]);
  else if(activeTab==='funnel')h=viewFunnel(D);
  else if(activeTab==='positions')h=viewPositions(D);
  else if(activeTab==='services')h=viewServices(D);
  else h=viewActivity(D.feed,D.cycle_lines);
  el.innerHTML=h;el.scrollTop=sy;}

async function poll(){try{const r=await fetch('/data.json',{cache:'no-store'});D=await r.json();lastOk=Date.now();render();}
  catch(e){if(D)renderHeader(D.header||{},D.meta||{});}}
poll();setInterval(poll,2000);
</script></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
