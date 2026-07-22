"""Nightly post-close COMPUTE LAB for the OPTIONS SHADOW TRADER (O5) - deterministic pure-CPU
stages over the shadow's JSONL ledgers tonight, plus a gate/health-checked LLM stage stub.

Reads ONLY the shadow ledgers (atlas/options/shadow.py); writes ONLY
runtime/overnight_lab_report.json (+ its own lock/heartbeat). There is NO order path here and
NO import of atlas.execution or anything order-related. The lab NEVER starts, stops, or
restarts the llama-swap server: the LLM stage runs only when the lab's OWN market-hours
guard allows it (after-hours; rth_blocked mirrors 09:15-16:15 ET) AND the already-running
server answers health(); any other outcome is a silent skip recorded in the report. The lab
governs itself by RTH, NOT the shared localgate -- localgate now brackets 16:25 (15:40-17:10 ET)
to keep EXTERNAL local-model users out while the lab runs, so gating the lab on it too would
lock the lab out of its own slot (see _own_rth_allows).

Stages (pure functions over ledger data; no-op-safe on empty/missing ledgers):
  1. exit_grid_replay - PAIRED replay of a stop x take x trail exit-policy grid on each
     exited position's stored quote path (runtime/options_shadow_quotes/). A variant sells at
     the FIRST row whose mid return from entry-mid crosses its stop/take, at that row's BID
     (worst-ledger convention); an uncrossed variant exits at the ACTUAL exit row's bid, same
     as reality. Cohort = exited positions with >= 2 quote rows; the ACTUAL policy is
     aggregated over the SAME cohort so the comparison is paired.
  1b. exit_engine_ab - PAIRED decide_exit replay (opts-rework-exit-core-v1 §replay,
     atlas/options/replay.py): the pre-registered v1/v2 engine+param variants (AB_VARIANTS)
     re-decide every stored schema-2 quote row per position. BESIDE stage 1, not replacing
     it - the grid sweeps premium thresholds, this sweeps whole engines. Needs the `ext`
     engine-input snapshot on quote rows, so it reports a note (not an error) until the
     first post-rework live session writes some.
  2. exit_efficiency - per exit rule id: MFE-capture ratio
     (exit worst fill - entry worst fill) / (peak mark mid - entry worst fill), null when the
     marks never peaked above the entry fill.
  3. anomaly_questions - deterministic question generator from the day's journal rows + the
     scorecard (zero entries on a trading day; lane/chain/exit-engine error counts; a no_pick
     rejection code holding > 50% of all rejections; malformed exit rows).
  4. llm_stages - RTH-guard + health() gated LOCAL jobs (glm-4.7-flash): a temp-0
     smoke echo, then job A (exit-review narratives) + job C (catalyst-memory tags); jobs B/D
     report "pending". Skipped (silently, recorded) if the guard blocks or the server is down.

Guards at startup (journaled, never crash):
  - REFUSES to run 09:15-16:15 ET on weekdays (print + exit 3) - mirrors the machine's
    local-model gate; there is deliberately no override.
  - pid lock runtime/overnight_lab.lock (run_hunter/run_options_shadow idiom: dead-pid
    reclaim, live holder -> exit 6, never signals the holder).

Exit codes: 0 success (including the all-empty no-op), 3 RTH refusal, 6 a stage raised
(caught + reported in the JSON) or the lock is held by a live pid.

    PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\run_overnight_lab.py [--once] [--day YYYY-MM-DD]

--once is accepted for launcher symmetry with the other runners; the lab is a single-pass
batch job either way. --day scopes the questions stage (journal slice + scorecard day); the
exit grid and efficiency stages always run over the FULL ledger history - the whole point of
a nightly lab is cumulative evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.clock import NY  # noqa: E402
from atlas.config_loader import FRAMEWORK_ROOT  # noqa: E402
from atlas.fsutil import atomic_replace  # noqa: E402
from atlas.models.http_client import HttpLLMClient  # noqa: E402
from atlas.options import exit_engine as engine_v2  # noqa: E402
from atlas.options import exit_engine_legacy as engine_v1  # noqa: E402  (replay-only - the ONE sanctioned consumer)
from atlas.options.replay import exit_engine_ab  # noqa: E402
from atlas.options.shadow import ShadowLedger, read_jsonl  # noqa: E402
from scripts.grade_options_shadow import grade  # noqa: E402

RUNTIME = FRAMEWORK_ROOT / "runtime"
LOCK_PATH = RUNTIME / "overnight_lab.lock"
HEARTBEAT_PATH = RUNTIME / "overnight_lab_heartbeat.json"
REPORT_PATH = RUNTIME / "overnight_lab_report.json"
# Path to the shared local-model time gate. Override with the ATLAS_LOCALGATE env var;
# absent/unset -> the gate is treated as missing and the LLM stage fails CLOSED.
LOCALGATE = Path(os.environ.get("ATLAS_LOCALGATE", "localgate.py"))
LLM_BASE_URL = "http://127.0.0.1:8080"
LLM_SMOKE_MODEL = "glm-4.7-flash"

# exit-grid variant space (pre-registered; keep stable so nightly reports are comparable)
STOP_FRACS = (-0.25, -0.50, -0.75)
TAKE_FRACS = (0.5, 1.0, 2.0)
TRAIL_MODES = ("off", "trail25")          # trail25 = 25%-off-peak trail armed by the take
TRAIL_OFF_PEAK_FRAC = 0.25
CONTRACT_MULT = 100.0

# stage-1b decide_exit A/B variants (pre-registered, opts-rework-exit-core-v1 §replay; keep
# stable so nightly reports are comparable - adding a variant is a registration, not an edit):
# the frozen v1 baseline as it ran on 07-09 (stop already disabled), the ORIGINAL v1 flavor
# with its -50% stop re-armed, live v2, and the two registered p_regain_min sweep points
# (opts-calib-p-regain-min-v1: .15 / .25(default) / .35).
AB_VARIANTS = (
    ("legacy_v1", engine_v1, engine_v1.ExitParams()),
    ("legacy_v1_stop50", engine_v1, engine_v1.ExitParams(stop_frac=-0.50)),
    ("v2_default", engine_v2, engine_v2.ExitParams()),
    ("v2_pregain_15", engine_v2, engine_v2.ExitParams(p_regain_min=0.15)),
    ("v2_pregain_35", engine_v2, engine_v2.ExitParams(p_regain_min=0.35)),
)


# --------------------------------------------------------------------------- guards
def rth_blocked(dt: datetime) -> bool:
    """True inside 09:15-16:15 ET on a weekday. Pure - caller passes an ET-local datetime.
    Mirrors the spirit of the machine's local-model gate (weekends are open; the MVP has no
    holiday calendar, matching atlas.clock - a holiday refusal is a safe false positive)."""
    minute = dt.hour * 60 + dt.minute
    return dt.weekday() < 5 and (9 * 60 + 15) <= minute < (16 * 60 + 15)


def _venv_python() -> str:
    cand = FRAMEWORK_ROOT / ".venv" / "Scripts" / "python.exe"
    return str(cand) if cand.exists() else sys.executable


def localgate_allows() -> tuple[bool, str]:
    """(allowed, reason) from the localgate script named by $ATLAS_LOCALGATE (exit 0 = allowed,
    3 = blocked). ANY other outcome - missing file, crash, timeout, weird exit - is treated
    as blocked (fail-closed): the gate must positively say yes."""
    if not LOCALGATE.exists():
        return False, f"localgate missing at {LOCALGATE} (fail-closed)"
    try:
        proc = subprocess.run([_venv_python(), str(LOCALGATE)],
                              capture_output=True, text=True, timeout=60)
    except Exception as exc:  # noqa: BLE001 - a broken gate is a blocked gate
        return False, f"localgate invocation failed: {exc!r} (fail-closed)"
    if proc.returncode == 0:
        return True, "localgate: allowed"
    if proc.returncode == 3:
        return False, "localgate: blocked (trading window)"
    return False, f"localgate exit {proc.returncode} (fail-closed)"


def _own_rth_allows(now: datetime | None = None) -> tuple[bool, str]:
    """(allowed, reason) from the lab's OWN market-hours guard -- deliberately NOT the shared
    localgate. The lab is ATLAS's own post-close compute and must run its ~16:25 jobs
    regardless of the discord-SDK gate: localgate now brackets 16:25 (15:40-17:10 ET) to keep
    EXTERNAL local-model users OUT while the lab runs, so gating the lab on it too would lock
    the lab out of its own slot. rth_blocked mirrors the market session (09:15-16:15 ET) -- the
    lab's real 'don't compute now' constraint. (localgate_allows above is retained for
    reference/manual use; the lab no longer gates on it.)"""
    now = now or datetime.now(NY)
    if rth_blocked(now):
        return False, f"lab RTH guard: {now:%H:%M} ET inside 09:15-16:15 (no LLM during RTH)"
    return True, "lab RTH guard: after-hours (lab runs regardless of the external gate)"


# --------------------------------------------------------------------------- pid lock (idiom)
def _pid_alive(pid: int) -> bool:
    """Never signals/kills (run_hunter idiom): Windows OpenProcess probe, POSIX kill(pid, 0)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            handle = k32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return code.value == 259
            finally:
                k32.CloseHandle(handle)
        except Exception:  # noqa: BLE001 - probe failure = assume alive (refuse to start)
            return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock() -> bool:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    try:
        rec = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        old_pid = int(rec.get("pid", 0))
    except (OSError, ValueError):
        old_pid = 0
    if old_pid and old_pid != os.getpid() and _pid_alive(old_pid):
        print(f"another overnight-lab (pid {old_pid}) holds {LOCK_PATH} -- exiting")
        return False
    LOCK_PATH.write_text(json.dumps({"pid": os.getpid(), "ts": time.time()}), encoding="utf-8")
    return True


def release_lock() -> None:
    try:
        rec = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        if int(rec.get("pid", 0)) == os.getpid():
            LOCK_PATH.unlink()
    except (OSError, ValueError):
        pass


def _write_heartbeat(phase: str, day: str, exit_code: int | None = None) -> None:
    """Best-effort heartbeat (run_options_shadow idiom, batch flavor) - never crashes the lab."""
    try:
        obj = {"schema": 1, "pid": os.getpid(), "ts_epoch": round(time.time(), 3),
               "day": day, "mode": "overnight_lab", "phase": phase, "exit_code": exit_code}
        RUNTIME.mkdir(parents=True, exist_ok=True)
        tmp = HEARTBEAT_PATH.with_name(HEARTBEAT_PATH.name + ".tmp")
        tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
        atomic_replace(tmp, HEARTBEAT_PATH)
    except Exception:  # noqa: BLE001 - observability must never take the lab down
        pass


# --------------------------------------------------------------------------- stage 1: exit grid
def _variant_key(stop_frac: float, take_frac: float, trail: str) -> str:
    return f"stop{stop_frac}_take{take_frac}_{trail}"


def _quote_mid(bid: float, ask: float) -> float:
    return (bid + ask) / 2.0 if (bid > 0 and ask > 0) else max(bid, 0.0)


def _replay_variant(rows: list, entry_mid: float, stop_frac: float, take_frac: float,
                    trail: str, fallback_bid: float) -> float:
    """Walk one position's quote rows chronologically; return the variant's sell BID.

    Sells at the FIRST row whose mid return from entry-mid crosses the stop or the take, at
    that row's bid (worst-ledger convention). trail25: the take crossing ARMS a
    25%-off-peak-mid trail instead of selling; once armed the trail governs (mirrors the exit
    engine's rule-(d) latch). Never crossed -> the ACTUAL exit row's bid (same as reality)."""
    armed = False
    peak = 0.0
    for r in rows:
        bid = float(r.get("bid") or 0.0)
        ask = float(r.get("ask") or 0.0)
        mid = _quote_mid(bid, ask)
        if mid <= 0:
            continue                       # a dead row can't price a fill either way
        if armed:
            peak = max(peak, mid)
            if mid <= peak * (1.0 - TRAIL_OFF_PEAK_FRAC):
                return bid
            continue
        ret = mid / entry_mid - 1.0
        if ret <= stop_frac:
            return bid
        if ret >= take_frac:
            if trail == "off":
                return bid
            armed = True
            peak = mid
    return fallback_bid


def _agg(nets: list) -> dict:
    n = len(nets)
    s = float(sum(nets))
    return {"n": n, "net_worst_sum": round(s, 2),
            "net_worst_mean": round(s / n, 3) if n else None}


def exit_grid_replay(entries: list, exits: list, quotes_by_pid: dict) -> dict:
    """PAIRED replay of alternative exit policies on the stored quote paths.

    Cohort = every EXITED position whose entry record is present, whose worst-ledger numbers
    are readable, and which has >= 2 stored quote rows. Entry fill = the entry record's fills
    (worst for dollars, optimistic == mid for the return baseline). Per-variant and ACTUAL
    aggregates are computed over the SAME cohort. No-op-safe: empty inputs -> every variant
    n=0."""
    entry_by_pid = {str(e.get("position_id")): e for e in entries}
    cohort = []                     # (rows, entry_mid, entry_worst, actual_bid, actual_net, contracts)
    n_skipped = 0
    for x in exits:
        pid = str(x.get("position_id"))
        e = entry_by_pid.get(pid)
        rows = quotes_by_pid.get(pid) or []
        try:
            fills = (e or {}).get("fills") or {}
            entry_worst = float(fills["worst"])
            entry_mid = float(fills["optimistic"])
            actual_bid = float((x.get("nbbo") or {})["bid"])
            actual_net = float(x["ledgers"]["worst"]["net_pnl_usd"])
        except (KeyError, TypeError, ValueError):
            n_skipped += 1
            continue
        # >= 1 row (audit REPLAY-LAB-3, opts-audit-wave0-evidence-v1): the old >=2 gate excluded
        # every first-mark exit - precisely the hair-trigger cuts the lab exists to study - so
        # the grid had replayed 0% of all real trades. Mark-at-entry rows (runner) now guarantee
        # an entry-anchored path for every position.
        if e is None or len(rows) < 1 or entry_mid <= 0:
            n_skipped += 1
            continue
        contracts = int(e.get("contracts") or 1)
        rows = sorted(rows, key=lambda r: float(r.get("ts_epoch") or 0.0))
        cohort.append((rows, entry_mid, entry_worst, actual_bid, actual_net, contracts))

    variants: dict[str, dict] = {}
    for stop in STOP_FRACS:
        for take in TAKE_FRACS:
            for trail in TRAIL_MODES:
                nets = []
                for rows, entry_mid, entry_worst, actual_bid, _net, contracts in cohort:
                    sell_bid = _replay_variant(rows, entry_mid, stop, take, trail, actual_bid)
                    nets.append((sell_bid - entry_worst) * CONTRACT_MULT * contracts)
                variants[_variant_key(stop, take, trail)] = _agg(nets)
    actual = _agg([c[4] for c in cohort])
    live = [(k, v) for k, v in variants.items() if v["n"]]
    best = max(live, key=lambda kv: (kv[1]["net_worst_sum"], kv[0]))[0] if live else None
    return {"n_exited": len(exits), "n_replayed": len(cohort),
            "n_skipped_no_path_or_malformed": n_skipped,
            "actual": actual, "variants": variants, "best_variant": best}


# --------------------------------------------------------------------------- stage 2: efficiency
def exit_efficiency(marks: list, exits: list) -> dict:
    """Per exit rule id: MFE-capture = (exit worst fill - entry worst fill) /
    (peak mark mid - entry worst fill), only when the peak exceeded the entry fill (else that
    trade contributes n but no capture). No-op-safe on empty inputs."""
    peaks: dict[str, float] = {}
    for m in marks:
        pid = str(m.get("position_id") or "")
        if not pid:
            continue
        try:
            mid = float(m.get("mid") or 0.0)
        except (TypeError, ValueError):
            continue
        peaks[pid] = max(peaks.get(pid, 0.0), mid)
    per_rule: dict[str, dict] = {}
    for x in exits:
        rule = str(x.get("rule") or "?")
        led = (x.get("ledgers") or {}).get("worst") or {}
        try:
            entry_fill = float(led["entry_fill"])
            exit_fill = float(led["exit_fill"])
        except (KeyError, TypeError, ValueError):
            continue                       # unreadable row - the grader reports it, not us
        rec = per_rule.setdefault(rule, {"n": 0, "captures": []})
        rec["n"] += 1
        peak = peaks.get(str(x.get("position_id") or ""), 0.0)
        if peak > entry_fill > 0:
            rec["captures"].append((exit_fill - entry_fill) / (peak - entry_fill))
    rules = {}
    for rule, rec in sorted(per_rule.items()):
        caps = rec["captures"]
        rules[rule] = {"n": rec["n"], "n_with_peak": len(caps),
                       "mean_mfe_capture": round(sum(caps) / len(caps), 4) if caps else None}
    return {"n_exits": len(exits), "rules": rules}


# --------------------------------------------------------------------------- stage 3: questions
def journal_rows_for_day(rows: list, day: str) -> list:
    """Day slice of the shadow journal: match on the record's own `day` when present, else on
    the ET date of ts_epoch (lane_error/exit_engine_error rows carry only a timestamp)."""
    out = []
    for r in rows:
        rd = r.get("day")
        if rd is not None:
            if str(rd) == day:
                out.append(r)
            continue
        ts = r.get("ts_epoch")
        try:
            if ts is not None and \
                    datetime.fromtimestamp(float(ts), tz=NY).strftime("%Y-%m-%d") == day:
                out.append(r)
        except (TypeError, ValueError, OSError, OverflowError):
            continue
    return out


def anomaly_questions(journal_rows: list, scorecard: dict) -> list:
    """Deterministic questions for the next session's human/LLM review. Inputs: the DAY's
    journal rows and the scorecard dict (grade() output extended with `entries_on_day`).
    Pure and no-op-safe: clean inputs -> []."""
    questions: list[str] = []
    day = str(scorecard.get("day_requested") or "?")
    trading = any(r.get("event") == "session_calendar" and r.get("trading_day")
                  for r in journal_rows)
    if trading and int(scorecard.get("entries_on_day") or 0) == 0:
        questions.append(
            f"Zero shadow entries on trading day {day}: were the lanes armed, was the feed "
            f"up, and did any signal survive the selector? (check journal fire/skip events)")
    err_counts: dict[str, int] = {}
    for r in journal_rows:
        ev = r.get("event")
        if ev in ("lane_error", "chain_fetch_error", "exit_engine_error"):
            err_counts[ev] = err_counts.get(ev, 0) + 1
    for ev, n in sorted(err_counts.items()):
        questions.append(
            f"{n} {ev} event(s) on {day}: what raised, and is it deterministic "
            f"(same lane/underlying every time) or transient?")
    reasons: dict[str, int] = {}
    for r in journal_rows:
        if r.get("event") == "no_pick":
            for code, cnt in (r.get("rejections") or {}).items():
                try:
                    reasons[str(code)] = reasons.get(str(code), 0) + int(cnt)
                except (TypeError, ValueError):
                    continue
    total = sum(reasons.values())
    if total > 0:
        code, cnt = max(sorted(reasons.items()), key=lambda kv: kv[1])
        if cnt / total > 0.5:
            questions.append(
                f"no_pick rejections on {day} are {cnt}/{total} concentrated in '{code}': is "
                f"a selector threshold miscalibrated for the day's chains?")
    malformed = scorecard.get("malformed_exits") or []
    if malformed:
        questions.append(
            f"malformed_exits is nonempty ({malformed}): the exit schema drifted - fix it "
            f"before believing any scorecard number.")
    return questions


# --------------------------------------------------------------------------- stage 4 jobs
LAB_DIR = RUNTIME / "lab"
EXIT_TAG_ENUM = frozenset({"exited_into_strength", "ladder_saved_us", "theta_bleed",
                           "chased_entry", "thesis_never_confirmed", "spread_tax_dominated"})
_JOB_SYSTEM = (
    "You review options shadow-trade digests. Every NUMBER you may need is already in the "
    "digest - never compute or invent one. Reply ONLY with the JSON the user requests."
)


def _write_job_file(job: str, day: str, items: list, dropped: list) -> Path:
    out_dir = LAB_DIR / job
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day}.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"schema": 1, "day": day, "model": LLM_SMOKE_MODEL,
                               "items": items,
                               "validation": {"n_ok": len(items), "n_dropped": len(dropped),
                                              "drop_reasons": dropped[:20]}},
                              indent=1, sort_keys=True), encoding="utf-8")
    atomic_replace(tmp, path)
    return path


def _job_exit_reviews(client, ledger: ShadowLedger, day: str) -> dict:
    """Job A (opts-lab-jobs-v1): per closed position, CODE builds the digest (fills, peaks,
    left_on_table) and the LLM writes a narrative + closed-enum tags citing mark timestamps
    that must exist in the stored quote path - else the row is dropped."""
    exits = [x for x in ledger.load_exits(None) if str(x.get("day") or "") == day]
    if not exits:
        return {"n": 0, "note": "no exits for the day"}
    quotes = load_quotes_by_pid(ledger)
    items, dropped = [], []
    for x in exits:
        pid = str(x.get("position_id") or "")
        path_rows = quotes.get(pid, [])
        ts_set = {round(float(r.get("ts_epoch") or 0.0), 3) for r in path_rows}
        peak_bid, peak_ts = 0.0, None
        for r in path_rows:
            b = float(r.get("bid") or 0.0)
            if b > peak_bid:
                peak_bid, peak_ts = b, round(float(r.get("ts_epoch") or 0.0), 3)
        exit_bid = float(x.get("bid") or 0.0)
        ledgers = x.get("ledgers") or {}
        digest = {
            "position_id": pid, "occ": x.get("occ"), "rule": x.get("rule"),
            "net_worst_usd": (ledgers.get("worst") or {}).get("net_pnl_usd"),
            "gross_usd": (ledgers.get("worst") or {}).get("gross_pnl_usd"),
            "spread_paid_usd": (x.get("decomposition") or {}).get("spread_paid_usd"),
            "theta_paid_usd": (x.get("decomposition") or {}).get("theta_paid_usd"),
            "underlying_mfe": x.get("underlying_mfe"), "underlying_mae": x.get("underlying_mae"),
            "hold_trading_days": x.get("hold_trading_days"),
            "peak_bid": round(peak_bid, 4), "peak_ts": peak_ts, "exit_bid": exit_bid,
            "left_on_table_usd": round(max(0.0, (peak_bid - exit_bid)) * 100.0, 2),
            "n_marks": len(path_rows),
        }
        user = ("Digest of one closed shadow position (trusted internal data):\n"
                + json.dumps(digest, sort_keys=True)
                + '\nReply ONLY with {"narrative": "<=600 chars on what the exit ladder did '
                  'well/poorly on THIS path", "tags": [subset of '
                + json.dumps(sorted(EXIT_TAG_ENUM))
                + '], "cites": [ts_epoch values from the digest/quote path you relied on]}')
        try:
            raw = client.complete_json(model=LLM_SMOKE_MODEL, system=_JOB_SYSTEM, user=user,
                                       schema={"type": "object"})
        except Exception as exc:  # noqa: BLE001
            dropped.append(f"{pid}: llm {exc!r}")
            continue
        if not isinstance(raw, dict):
            dropped.append(f"{pid}: non-dict reply")
            continue
        narrative = str(raw.get("narrative") or "")[:600]
        tags = [t for t in (raw.get("tags") or []) if t in EXIT_TAG_ENUM]
        cites = []
        for c in raw.get("cites") or []:
            try:
                cv = round(float(c), 3)
            except (TypeError, ValueError):
                continue
            if cv in ts_set or cv == peak_ts:
                cites.append(cv)
        if not narrative:
            dropped.append(f"{pid}: empty narrative")
            continue
        if (raw.get("cites") or []) and not cites:
            dropped.append(f"{pid}: cited timestamps not in stored quote path")
            continue
        items.append({"position_id": pid, "digest": digest, "narrative": narrative,
                      "tags": sorted(set(tags)), "cites": cites})
    path = _write_job_file("exit_reviews", day, items, dropped)
    return {"n": len(items), "dropped": len(dropped), "path": str(path)}


def _job_catmem_append(client, ledger: ShadowLedger, day: str) -> dict:
    """Job C (opts-lab-jobs-v1): tag TODAY's headline-bearing names (hunt list + entered
    underlyings) with the crew enum and append story stubs to the catalyst memory (features
    null, fwd censored - the nightly builder heals them as daily bars accrue)."""
    from atlas.memory.catalyst_memory import MEM_DIR, STORIES_PATH
    from scripts.tag_catalyst_headlines import build_batch_prompt, parse_batch_reply
    # today's headlines by symbol (newest per symbol) from the news stream
    heads: dict[str, str] = {}
    for r in read_jsonl(RUNTIME / "news_stream.jsonl"):
        if str(r.get("ts") or "").startswith(day):
            for s in r.get("symbols") or []:
                s = str(s).upper()
                if s:
                    heads[s] = str(r.get("headline") or "")
    wanted: set = set()
    try:
        raw = json.loads((RUNTIME / "hunt_list.json").read_text(encoding="utf-8-sig"))
        rows = (raw.get("candidates") or raw.get("symbols")) if isinstance(raw, dict) else raw
        for r in rows if isinstance(rows, list) else []:
            sym = (r if isinstance(r, str) else (r or {}).get("symbol") or "")
            if sym:
                wanted.add(str(sym).upper())
    except Exception:  # noqa: BLE001
        pass
    for e in ledger.load_entries(None):
        if str(e.get("day") or "") == day:
            sym = str(((e.get("signal") or {}).get("underlying")) or "").upper()
            if sym:
                wanted.add(sym)
    items_in = [(f"{s}|{day}", s, heads[s]) for s in sorted(wanted & set(heads))]
    if not items_in:
        return {"n": 0, "note": "no headline-bearing names today"}
    # skip keys already in the story store
    existing: set = set()
    try:
        for line in STORIES_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                existing.add(json.loads(line)["key"])
            except (ValueError, KeyError):
                continue
    except OSError:
        pass
    items_in = [it for it in items_in if it[0] not in existing]
    if not items_in:
        return {"n": 0, "note": "all of today's names already in the store"}
    raw = client.complete_json(model=LLM_SMOKE_MODEL, system=_JOB_SYSTEM,
                               user=build_batch_prompt(items_in), schema={"type": "array"})
    tags = parse_batch_reply(raw, len(items_in))
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    appended = []
    with STORIES_PATH.open("a", encoding="utf-8") as fh:
        for idx, tag in sorted(tags.items()):
            key, sym, headline = items_in[idx]
            fh.write(json.dumps({
                "schema": 1, "key": key, "symbol": sym, "date": day,
                "catalyst_kind": tag["kind"], "name_specific": tag["name_specific"],
                "direction_hint": tag["direction_hint"], "gap_direction": None,
                "headline": headline[:300], "n_news": None,
                "gap_pct": None, "vol_mult": None, "range_pct": None, "dollar_vol20": None,
                "rank": None, "delisted": False,
                "fwd": {"gap_hold_d0": None, "ret_1d": None, "ret_2d": None, "ret_5d": None,
                        "censored": True},
                "tag_source": {"model": LLM_SMOKE_MODEL, "agree": False}, "ingest": "daily_v1",
            }, separators=(",", ":")) + "\n")
            appended.append(key)
        fh.flush()
        os.fsync(fh.fileno())
    path = _write_job_file("catmem_append", day,
                           [{"key": k} for k in appended],
                           [f"idx {i} untagged" for i in range(len(items_in))
                            if i not in tags])
    return {"n": len(appended), "path": str(path)}


# --------------------------------------------------------------------------- stage 4: LLM jobs
def llm_stages(*, gate_fn=None, client=None, ledger=None, day: str | None = None) -> dict:
    """Stage 4 (opts-lab-jobs-v1): RTH-guard + health() double-gated LOCAL-model jobs. Gate
    blocked or server down -> {"skipped": reason} (silent skip - the lab NEVER starts/stops
    llama-swap). Allowed -> the temp-0 smoke, then jobs A (exit-quality narratives) + C (daily
    catalyst-memory tags); B/D report "pending" until mid-week. gate_fn/client injectable
    (default gate = _own_rth_allows, the lab's OWN market-hours guard, NOT the shared localgate
 - the lab must run its 16:25 slot even though localgate now blocks 15:40-17:10 ET)."""
    gate_fn = gate_fn or _own_rth_allows
    try:
        allowed, why = gate_fn()
    except Exception as exc:  # noqa: BLE001 - a broken gate is a blocked gate
        allowed, why = False, f"gate check raised: {exc!r} (fail-closed)"
    if not allowed:
        return {"skipped": why}
    if client is None:
        # enable_thinking:false (2026-07-11): the smoke model (GLM) is a hybrid thinker - left
        # thinking it can spend the whole budget in reasoning_content and return EMPTY content.
        client = HttpLLMClient(LLM_BASE_URL, timeout=120.0, max_retries=1,
                               extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    try:
        healthy = bool(client.health())
    except Exception:  # noqa: BLE001
        healthy = False
    if not healthy:
        return {"skipped": "llama-swap health check failed (server down/unreachable) -- "
                           "skipping LLM stages; the lab never starts or stops the server"}
    try:
        out = client.complete_json(
            model=LLM_SMOKE_MODEL,
            system="You are a smoke test. Reply with EXACTLY the JSON object the user "
                   "requests and nothing else.",
            user='Reply with {"ok": true}',
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"]})
    except Exception as exc:  # noqa: BLE001 - a failed smoke is a report line, not a crash
        return {"smoke": f"failed: {exc!r}"}
    if isinstance(out, dict) and out.get("ok") is True:
        smoke = "ok"
    else:
        smoke = f"failed: unexpected payload {out!r}"
    result: dict = {"smoke": smoke}
    # ---- REAL jobs (opts-lab-jobs-v1, 2026-07-11): the stub grew up. Each job in its own
    # containment; the LLM narrates/tags - every number is code-computed; outputs are
    # validated JSON under runtime/lab/ (atomic, own files) consumed by /eodreport.
    # ToS: positions/P&L stay on 127.0.0.1:8080 - these jobs never touch cloud models.
    if ledger is not None and day and smoke == "ok":
        for name, fn in (("exit_reviews", lambda: _job_exit_reviews(client, ledger, day)),
                         ("catmem_append", lambda: _job_catmem_append(client, ledger, day))):
            try:
                result[name] = fn()
            except Exception as exc:  # noqa: BLE001 - one job never kills the stage
                result[name] = {"error": repr(exc)}
        result["anomaly_answers"] = {"pending": "job B lands mid-week (opts-lab-jobs-v1)"}
        result["runner_up_reviews"] = {"pending": "job D lands mid-week (opts-lab-jobs-v1)"}
    return result


# --------------------------------------------------------------------------- ledger loading
def load_quotes_by_pid(ledger: ShadowLedger) -> dict:
    """All stored quote-path rows grouped by position_id, each list ts-sorted. Missing dir or
    unreadable files -> {} / partial (read_jsonl is tolerant)."""
    out: dict[str, list] = {}
    qdir = Path(ledger.quotes_dir)
    if not qdir.exists():
        return out
    try:
        files = sorted(qdir.glob("*.jsonl"))
    except OSError:
        return out
    for p in files:
        for r in read_jsonl(p):
            pid = str(r.get("position_id") or "")
            if pid:
                out.setdefault(pid, []).append(r)
    for pid in out:
        out[pid].sort(key=lambda r: float(r.get("ts_epoch") or 0.0))
    return out


# --------------------------------------------------------------------------- orchestration
def run_lab(ledger: ShadowLedger, day: str, *, llm_fn=None, notes: list | None = None):
    """Main-equivalent, IO-light and test-friendly: run all four stages over `ledger`, each in
    its own containment (a raised stage becomes {"error": ...} and flips the exit code to 6,
    the rest still run). Returns (report_dict, exit_code); writes nothing."""
    notes = list(notes or [])
    stages: dict[str, object] = {}
    failed = False

    def _stage(name: str, fn) -> None:
        nonlocal failed
        try:
            stages[name] = fn()
        except Exception as exc:  # noqa: BLE001 - per-stage containment, exit 6 at the end
            failed = True
            stages[name] = {"error": repr(exc)}
            notes.append(f"stage {name} RAISED (caught): {exc!r}")

    def _grid():
        return exit_grid_replay(ledger.load_entries(None), ledger.load_exits(None),
                                load_quotes_by_pid(ledger))

    def _engine_ab():
        # full ledger history, like the grid - cumulative evidence is the lab's whole point;
        # replay.exit_engine_ab is pure and no-op-safe (note, not error, before any ext rows)
        return exit_engine_ab(ledger.load_entries(None), load_quotes_by_pid(ledger),
                              list(AB_VARIANTS))

    def _efficiency():
        return exit_efficiency(ledger.load_marks(None), ledger.load_exits(None))

    def _questions():
        card = grade(ledger, day)
        card["entries_on_day"] = len(ledger.load_entries(day))
        rows = journal_rows_for_day(read_jsonl(ledger.journal_path), day)
        return anomaly_questions(rows, card)

    _stage("exit_grid", _grid)
    _stage("exit_engine_ab", _engine_ab)
    _stage("exit_efficiency", _efficiency)
    _stage("questions", _questions)
    _stage("llm", llm_fn or (lambda: llm_stages(ledger=ledger, day=day)))

    report = {"generated": datetime.now(NY).isoformat(timespec="seconds"), "day": day,
              "stages": stages, "notes": notes}
    return report, (6 if failed else 0)


def _print_summary(report: dict, code: int) -> None:
    st = report.get("stages") or {}
    print("=" * 78)
    print(f"OVERNIGHT LAB  day={report.get('day')}  generated={report.get('generated')}  "
          f"exit={code}")
    grid = st.get("exit_grid")
    if isinstance(grid, dict) and "variants" in grid:
        actual = grid.get("actual") or {}
        line = (f"  exit_grid: replayed {grid.get('n_replayed', 0)}/{grid.get('n_exited', 0)} "
                f"exited positions  actual net(worst) sum={actual.get('net_worst_sum')}")
        best = grid.get("best_variant")
        if best:
            line += f"  best={best} sum={grid['variants'][best]['net_worst_sum']}"
        print(line)
    else:
        print(f"  exit_grid: {grid}")
    ab = st.get("exit_engine_ab")
    if isinstance(ab, dict) and "variants" in ab:
        print(f"  exit_engine_ab: {ab.get('n_entries', 0)} entr(ies), "
              f"{ab.get('n_ext_rows_total', 0)} ext row(s)"
              + (f"  [{ab['note']}]" if ab.get("note") else ""))
        for name, s in ab["variants"].items():
            print(f"    {name}: n={s['n']} net_worst_sum={s['net_worst_sum']} "
                  f"unexited={s['unexited']} rules={s['rule_mix']}")
    else:
        print(f"  exit_engine_ab: {ab}")
    eff = st.get("exit_efficiency")
    if isinstance(eff, dict) and "rules" in eff:
        print(f"  exit_efficiency: {len(eff['rules'])} rule(s) over {eff.get('n_exits', 0)} "
              f"exit(s)")
        for rule, s in eff["rules"].items():
            print(f"    {rule}: n={s['n']} mean_mfe_capture={s['mean_mfe_capture']}")
    else:
        print(f"  exit_efficiency: {eff}")
    qs = st.get("questions")
    if isinstance(qs, list):
        print(f"  questions ({len(qs)}):")
        for q in qs:
            print(f"    - {q}")
    else:
        print(f"  questions: {qs}")
    print(f"  llm: {st.get('llm')}")
    for n in report.get("notes") or []:
        print(f"  note: {n}")
    print(f"  -> {REPORT_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="ATLAS options-shadow overnight compute lab (ledger-only; NO order path, "
                    "never touches the llama-swap lifecycle)")
    ap.add_argument("--once", action="store_true",
                    help="accepted for launcher symmetry; the lab is single-pass either way")
    ap.add_argument("--day", default=None, help="report day YYYY-MM-DD (default: today ET)")
    args = ap.parse_args()

    now_et = datetime.now(NY)
    if rth_blocked(now_et):
        print(f"REFUSED: {now_et:%Y-%m-%d %H:%M} ET is inside the 09:15-16:15 weekday trading "
              f"window -- the overnight lab never runs during RTH (no override exists)")
        return 3

    notes: list[str] = [f"rth guard clear at {now_et:%Y-%m-%d %H:%M} ET"]
    day = None
    if args.day:
        try:
            day = date.fromisoformat(args.day).isoformat()
        except ValueError:
            notes.append(f"--day {args.day!r} malformed -> using today ET")
    if day is None:
        day = now_et.strftime("%Y-%m-%d")

    if not acquire_lock():
        return 6
    try:
        notes.append(f"lock acquired (pid {os.getpid()})")
        _write_heartbeat("start", day)
        report, code = run_lab(ShadowLedger(RUNTIME), day, notes=notes)
        try:
            RUNTIME.mkdir(parents=True, exist_ok=True)
            tmp = REPORT_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(report, indent=1), encoding="utf-8")
            atomic_replace(tmp, REPORT_PATH)
        except OSError as exc:
            code = 6
            report.setdefault("notes", []).append(f"report write FAILED: {exc!r}")
        _write_heartbeat("done", day, exit_code=code)
        _print_summary(report, code)
        return code
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
