"""Run the OPTIONS SHADOW TRADER process (O3) - lanes fire on live 1-min bars, the selector
picks the contract we WOULD buy, and the exit engine manages the hypothetical position; the ONLY
outputs are the fsync'd JSONL ledgers (atlas/options/shadow.py). There is NO broker-order code
path anywhere in this module or its imports - structurally a shadow.

Process skeleton follows the equity-era hunter runner, archived out of this tree (pid lock
runtime/options_shadow.lock, heartbeat
runtime/options_shadow_heartbeat.json each loop, --once, per-loop exception containment, clean
Ctrl-C). Feeds: TradierData via config/tradier_shadow.local.yaml FIRST (the dedicated
options-project token = its own 120/min budget) falling back to config/tradier.local.yaml; the
token loader is tolerant of a UTF-8 BOM and of the token living either at the top level or under
a `tradier:` mapping (the shadow file uses the TOP-LEVEL shape). Underlying quotes are batched every
poll_seconds for the active watch (SPY/QQQ/IWM + up to lane2_max_candidates Lane-2 names);
LiveBarBuilder folds them into completed 1-min bars; today's bars are backfilled at startup via
timesales (stale backfill-era signals die on expires_minute - dedup state still arms).

Reval cadence per open position (plan): 5-min for DTE>=1; 0DTE 5-min before 14:00, 2-min after;
1-min inside the last 30 minutes before expiry. Every reval cycle's NBBO is persisted to
runtime/options_shadow_quotes/YYYY-MM-DD.jsonl (the paired exit-grid replay paths).

Config knobs: config/hunter.yaml top-level `options_shadow:` block, read tolerantly; absent
keys fall back to DEFAULTS in code (the block does not exist yet - defaults rule).

    PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\run_options_shadow.py [--once] [--interval 10]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import deque
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.clock import NY  # noqa: E402
from atlas.collect.tradier_data import PRODUCTION_BASE, SANDBOX_BASE, TradierData  # noqa: E402
from atlas.collect import symbol_state  # noqa: E402
from atlas.config_loader import FRAMEWORK_ROOT  # noqa: E402
from atlas.fsutil import atomic_replace  # noqa: E402
from atlas.hunter.feed import HunterFeed, LiveBarBuilder  # noqa: E402
from atlas.options import events as oevents  # noqa: E402
from atlas.options import lanes as olanes  # noqa: E402
from atlas.options import math as om  # noqa: E402
from atlas.options import session_calendar as scal  # noqa: E402
from atlas.options import shadow as oshadow  # noqa: E402
from atlas.options import trajectory as otraj  # noqa: E402
from atlas.options.exit_engine import HOLD, ExitParams, PositionView, decide_exit  # noqa: E402
from atlas.options.selector import (INDEX_UNDERLYINGS, ContractQuote, SelectorParams,  # noqa: E402
                                    select_contract)
from atlas.options.vendor.blackscholes import implied_vol  # noqa: E402
from atlas.options.vendor.models import OptionType  # noqa: E402

RUNTIME = FRAMEWORK_ROOT / "runtime"
LOCK_PATH = RUNTIME / "options_shadow.lock"
HEARTBEAT_PATH = RUNTIME / "options_shadow_heartbeat.json"
LOG_FILE = RUNTIME / "options_shadow.log"
HUNT_LIST = RUNTIME / "hunt_list.json"

DEFAULTS: dict = {
    "watch": ["SPY", "QQQ", "IWM"],
    "poll_seconds": 10.0,
    "max_concurrent": 3,
    "top_n": 3,
    "p_thesis": 0.5,
    "range_percentile_min": 50.0,
    "lane2_max_candidates": 10,
    "lane2_gap_min_pct": 4.0,
    "lane2_rvol_min": 5.0,
    "lane2_price_min": 5.0,
    "lane2_scan_symbols": [],
    # 3 -> 6 (audit 2026-07-16 Wave 1.5, opts-audit-wave1-funnel-v1): 3 truncated daily-expiry
    # indexes to DTE 0-2, colliding with the 1/3-of-life gate - morning index signals had ONE
    # marginal expiration to shop. 6 restores the selector's declared DTE 0-5 scan.
    "max_chain_expirations": 6,
    # per-lane p_thesis overrides (audit Wave 3.18 plumbing, opts-audit-wave3-priors-v1):
    # e.g. {"index_trend": 0.35}. Empty -> every lane uses the global p_thesis. Values come from
    # the offline lane-prior calibration study (pending); an unknown lane key is ignored.
    "p_thesis_by_lane": {},
    "tradier_self_cap_per_min": 60,
    "noise_lookback_days": 14,
    "r": 0.04,
    # C5 event-triggered re-vals (observability only - WHEN we mark, never WHAT we do):
    # a 1-min bar whose |move| exceeds max(floor, mult x trailing-20-bar mean |move|) marks
    # every open position on that underlying immediately instead of waiting out the cadence
    "reval_shock_mult": 3.0,
    "reval_shock_floor": 0.002,
    # live-trajectory window (opts-rework-exit-core-v1 / opts-calib-mu-window-v1): trailing
    # minutes of committed closes feeding mu_hat/t_stat (trajectory.py). CALIBRATION - 
    # replay-swept 10/20/30; in the config hash, so a change starts a new entry cohort.
    "mu_window_min": 20,
}


# Structural correctness (opts-fix-backfill-retry-v1): feed.backfill is FAIL-OPEN (returns [] on any
# transport/parse error). A symbol is marked backfilled ONLY after a non-empty fetch; a bar-less
# result is retried up to BACKFILL_MAX_ATTEMPTS before giving up for the day - so a transient morning
# feed failure no longer permanently starves a symbol of session context. MODULE constant, NOT in
# DEFAULTS -> not in the config hash, so this fix does not split the entry cohort.
BACKFILL_MAX_ATTEMPTS = 3


# --------------------------------------------------------------------------- logging / lock
def _stamp() -> str:
    return datetime.now(NY).strftime("%Y-%m-%d %H:%M:%S %Z")


def make_log():
    RUNTIME.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"[{_stamp()}] {msg}"
        print(line, flush=True)
        try:
            with LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
    return log


def _pid_alive(pid: int) -> bool:
    """Never signals/kills: Windows OpenProcess probe, POSIX kill(pid, 0)."""
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


def acquire_lock(log) -> bool:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    try:
        rec = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        old_pid = int(rec.get("pid", 0))
    except (OSError, ValueError):
        old_pid = 0
    if old_pid and old_pid != os.getpid() and _pid_alive(old_pid):
        log(f"another options-shadow (pid {old_pid}) holds {LOCK_PATH} - exiting")
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


# --------------------------------------------------------------------------- config / token
def load_shadow_config() -> dict:
    """DEFAULTS overlaid with config/hunter.yaml's top-level `options_shadow:` block (tolerant:
    absent file/block/keys are fine; wrong-typed values fall back per key)."""
    cfg = dict(DEFAULTS)
    try:
        raw = yaml.safe_load((FRAMEWORK_ROOT / "config" / "hunter.yaml").read_text("utf-8")) or {}
        block = raw.get("options_shadow")
        if isinstance(block, dict):
            for k, v in block.items():
                if k in cfg and v is not None:
                    cfg[k] = v
    except (OSError, yaml.YAMLError):
        pass
    return cfg


def config_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:12]


def tradier_from_yaml(path: Path) -> TradierData | None:
    """Tolerant client builder: utf-8-sig (a BOM must never kill the feed), token at top level
    (the shadow file's ACTUAL shape: `token:` + `env:`) OR nested under `tradier:` - 
    from_local_config handles neither."""
    try:
        cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig")) or {}
    except (OSError, yaml.YAMLError):
        return None
    if isinstance(cfg.get("tradier"), dict):
        cfg = {**cfg, **cfg["tradier"]}
    token = str(cfg.get("token") or "").strip()
    if not token:
        return None
    base = SANDBOX_BASE if str(cfg.get("env", "production")).lower() == "sandbox" else PRODUCTION_BASE
    try:
        return TradierData(token, base_url=base,
                           timeout=float(cfg.get("timeout_seconds", 5.0)),
                           max_per_minute=int(cfg.get("max_per_minute", 100)))
    except (TypeError, ValueError):
        return None


def build_tradier_client(log) -> TradierData | None:
    for name in ("tradier_shadow.local.yaml", "tradier.local.yaml"):
        p = FRAMEWORK_ROOT / "config" / name
        client = tradier_from_yaml(p)
        if client is not None:
            log(f"tradier client UP via config/{name}")
            return client
    log("no usable tradier token (config/tradier_shadow.local.yaml, config/tradier.local.yaml) "
        " - DEGRADED heartbeat-only loop")
    return None


# --------------------------------------------------------------------------- small helpers
def _et_dt(now: float) -> datetime:
    return datetime.fromtimestamp(now, tz=NY)


def _ols_slope_per_hour(series) -> float:
    """OLS slope of (ts_epoch, iv) pairs, per HOUR. 0 when degenerate (<3 points / no spread)."""
    pts = [(t, v) for t, v in series if v > 0]
    if len(pts) < 3:
        return 0.0
    n = float(len(pts))
    mt = sum(t for t, _ in pts) / n
    mv = sum(v for _, v in pts) / n
    var = sum((t - mt) ** 2 for t, _ in pts)
    if var <= 0:
        return 0.0
    cov = sum((t - mt) * (v - mv) for t, v in pts)
    return cov / var * 3600.0


def _trading_days_held(entry_day: str, entry_minute: int, now_day: str, now_minute: int) -> float:
    """Approximate trading days between entry and now (weekday count + RTH fractions;
    holidays ignored - same tolerance as om.trading_T)."""
    if entry_day == now_day:
        return max(0.0, now_minute - entry_minute) / 390.0
    try:
        d0, d1 = date.fromisoformat(entry_day), date.fromisoformat(now_day)
    except ValueError:
        return 0.0
    whole = sum(1 for i in range(1, max(0, (d1 - d0).days) + 1)
                if (d0 + timedelta(days=i)).weekday() < 5)
    frac_entry = max(0.0, 960 - entry_minute) / 390.0
    frac_now = min(390.0, max(0.0, now_minute - 570)) / 390.0
    return max(0.0, whole - 1 + frac_entry + frac_now)


def load_hunt_list(path: Path = HUNT_LIST) -> tuple[list, str | None]:
    """Tolerant read of the research crew's premarket artifact: accepts a list of dicts/strings,
    {"symbols": [...]}, or the crew's actual {"candidates": [...]} shape (2026-07-09 fix - the
    crew writes `candidates`; reading only `symbols` silently starved lane 2 of its hunt list).
    Returns (rows, session_date_str_or_None); ([], None) on any problem (fail-open). The CALLER
    enforces freshness (audit 2026-07-16 RUNNER-4/PREMARKET-CREW-1: a failed premarket used to
    silently arm lane 2 with YESTERDAY'S catalyst names)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], None
    session_date = str(raw.get("session_date")) if isinstance(raw, dict) and raw.get("session_date") else None
    rows = (raw.get("symbols") or raw.get("candidates")) if isinstance(raw, dict) else raw
    out = []
    for r in rows if isinstance(rows, list) else []:
        try:
            if isinstance(r, str):
                out.append({"symbol": r.upper(), "gap_pct": 0.0, "catalyst": True,
                            "catalyst_kind": None})
            elif isinstance(r, dict) and r.get("symbol"):
                # keep the existing bool `catalyst` (lane-2 gating reads it) AND retain the KIND
                # string for the stage-2 catalyst covariate (opts-catalyst-kind-covariate-v1)
                out.append({"symbol": str(r["symbol"]).upper(),
                            "gap_pct": float(r.get("gap_pct") or 0.0),
                            "catalyst": bool(r.get("catalyst", True)),
                            "catalyst_kind": r.get("catalyst_kind") or (
                                r.get("catalyst") if isinstance(r.get("catalyst"), str) else None)})
        except (TypeError, ValueError):
            continue        # machine-authored file: one malformed row never disarms the day
    return out, session_date


def _occ_expiry(occ: str) -> date | None:
    """Expiry parsed from an OCC symbol (ROOT + YYMMDD + C/P + 8-digit strike); None when
    unparseable (short test fakes pass through as None)."""
    try:
        if not occ or len(occ) < 15:
            return None
        ymd = occ[-15:-9]
        return date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    except (TypeError, ValueError):
        return None


def _read_cached_profile(symbol: str, lookback_days: int):
    """Noise profile from the intraday parquet cache - READ ONLY (never fetches at runtime;
    the O3 build step populated SPY/QQQ/IWM). None when absent/unreadable."""
    p = RUNTIME / "intraday_cache" / f"{symbol.upper()}_1min.parquet"
    if not p.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    return olanes.build_noise_profile(symbol, df, lookback_days=lookback_days)


def _avg_first5_from_cache(symbol: str) -> float:
    prof = _read_cached_profile(symbol, 14)
    return prof.avg_first5_volume if prof is not None else 0.0


# --------------------------------------------------------------------------- the core
class OptionsShadowCore:
    """One loop body per tick(); everything injected (client, feed, ledger, clock, config,
    events, profiles, lane-2 candidates) so it unit-tests with fakes - no network, no sleeps."""

    def __init__(self, *, client, feed: HunterFeed, ledger: oshadow.ShadowLedger,
                 clock_fn, cfg: dict, log,
                 events_list=None, profiles: dict | None = None,
                 lane2_candidates: list | None = None,
                 heartbeat_path: Path | None = None,
                 session_days: dict | None = None):
        self.heartbeat_path = Path(heartbeat_path) if heartbeat_path else HEARTBEAT_PATH
        self.client = client
        self.feed = feed
        self.ledger = ledger
        self.clock_fn = clock_fn
        self.cfg = dict(cfg)
        self.log = log
        self.events = events_list                    # None = load per day (IO); tests inject
        self._profiles_arg = profiles
        self._lane2_arg = lane2_candidates
        self._session_days = session_days            # None = session_calendar cache; tests inject
        self.cfg_hash = config_hash(self.cfg)
        # per-day session clocks (derived in _roll_day; normal-day defaults until then)
        self._close_min = 16 * 60
        self._late_close_flat_min = 16 * 60 + 10
        self._exit_params = ExitParams()
        self._selector_params = SelectorParams()

        self.builder = LiveBarBuilder()
        self.positions: dict[str, oshadow.ShadowPosition] = {}
        self.entries_today = 0
        self.lanes: list = []
        self._lane_by_name: dict = {}
        self._day: str | None = None
        self._events_today: list = []
        self._session_open: dict[str, float] = {}
        self._last_ticks: dict = {}
        self._last_ctx: dict[str, olanes.MinuteCtx] = {}
        self._iv_series: dict[str, deque] = {}
        self._backfilled: set = set()
        self._backfill_attempts: dict = {}        # sym -> consecutive empty-backfill count (bounded retry)
        self._s_freeze: dict[str, tuple] = {}     # underlying -> (S, since_ts, flagged)
        self._noquote_streak: dict[str, int] = {}  # position_id -> consecutive mark_no_quote
        self._bar_moves: dict[str, deque] = {}     # underlying -> trailing |1-min move| (C5)
        # audit 2026-07-16 additions (opts-audit-wave0/1/2 registrations):
        self._post_exit: dict = {}          # pid -> {occ, underlying, last_ts}: REPLAY-LAB-1 capture
        self._halted_flagged: set = set()   # underlyings journaled halted_while_held (once/stretch)
        self._rvol_retried = False          # lane-2 average_volume second fetch at ~09:25 (Wave 1.12)
        self._next_trading_day = None       # session-calendar next day (EVENTS-CALENDAR-5)
        self._retry_sleep_s = 2.0           # chain-fetch retry pause (tests set 0)
        # data-plane liveness (heartbeat schema 2 - observability ONLY, no decision input):
        # a token-less/dead feed keeps the process heartbeat fresh while positions sit
        # unmanaged; these let alert_watch page on that exact zombie mode (2026-07-10 audit #7)
        self._last_tick_epoch = 0.0    # last poll that returned >= 1 quote
        self._last_bar_epoch = 0.0     # last LIVE (non-backfill) completed RTH bar
        self._last_mark_epoch = 0.0    # last successful position reval (usable NBBO)
        self._iv_archive = None
        try:
            from atlas.options.iv_archive import IVArchive
            self._iv_archive = IVArchive()
        except Exception:  # noqa: BLE001 - iv_rank is nullable context, never a dependency
            self._iv_archive = None
        # WS4/WS5 news enrichment (opts-news-covariates-v1 / opts-news-shock-accel-v1): best-effort
        # O(1) cache over runtime/news_flags.jsonl; nullable context, never a dependency.
        self._news_cache = None
        try:
            from atlas.options.news_cache import NewsFlagsCache
            self._news_cache = NewsFlagsCache()
        except Exception:  # noqa: BLE001
            self._news_cache = None
        self._news_marked: dict[str, str] = {}    # position_id -> last news fingerprint that accel'd (dedupe)
        # WS4 catmem covariates (opts-catmem-covariates-v1): premarket recall() base rates keyed by
        # underlying, read O(1) at entry (construction-time one-shot; never re-read on the tick path).
        self._catalyst_ctx: dict = {}
        try:
            _cc = json.loads((RUNTIME / "catalyst_context.json").read_text("utf-8"))
            self._catalyst_ctx = _cc if isinstance(_cc, dict) else {}   # valid-JSON-wrong-type -> {}
        except Exception:  # noqa: BLE001 - nullable context, never a dependency
            self._catalyst_ctx = {}

    # ------------------------------------------------------------------ day / lanes
    def _load_events(self):
        if self.events is not None:
            return self.events
        try:
            return oevents.load_events()
        except Exception:  # noqa: BLE001
            return []

    def _blackout_at(self, dt: datetime) -> str | None:
        try:
            return oevents.in_blackout(dt, events=self._load_events())
        except Exception:  # noqa: BLE001
            return None

    def _roll_day(self, now: float) -> None:
        day = _et_dt(now).strftime("%Y-%m-%d")
        if day == self._day:
            return
        # FAIL-CLOSED rebuild (audit SHADOW-LEDGER-2 + RUNNER-9): the ledger rebuild runs FIRST
        # and self._day latches only after the whole roll succeeds - an unreadable exits file
        # (AV/backup lock) journals loudly and RETRIES next tick instead of resurrecting every
        # unexpired historical position under a half-initialized day.
        today_d = _et_dt(now).date()
        try:
            open_positions = self.ledger.open_positions_all()
        except oshadow.LedgerUnreadable as exc:
            self.ledger.journal({"event": "ledger_unreadable_roll_aborted", "day": day,
                                 "ts_epoch": round(now, 3), "error": repr(exc)})
            self.log(f"DAY ROLL ABORTED - exits ledger unreadable ({exc!r}); retrying next tick")
            return
        self.builder = LiveBarBuilder()
        self._session_open.clear()
        self._last_ctx.clear()
        self._backfilled.clear()
        self._backfill_attempts.clear()
        self._iv_series.clear()
        self._halted_flagged = set()
        self._rvol_retried = False
        # session clocks for the day (half days: 13:00 close -> every derived clock shifts)
        d = _et_dt(now).date()
        try:
            days = self._session_days if self._session_days is not None \
                else scal.load_days(client=self.client)
        except Exception:  # noqa: BLE001 - calendar is an upgrade, never a dependency
            days = {}
        self._close_min = scal.session_close_minute(d, days=days)
        self._late_close_flat_min = self._close_min + 10
        self._exit_params = ExitParams.for_close(self._close_min)
        self._selector_params = SelectorParams.for_close(self._close_min)
        self.ledger.journal({"event": "session_calendar", "day": day,
                             "close_min": self._close_min,
                             "trading_day": scal.is_trading_day(d, days=days)})
        # next trading day (session calendar, not weekday-skip - audit EVENTS-CALENDAR-5):
        # feeds the overnight grant's named-catalyst check in _reval_positions
        nd = d + timedelta(days=1)
        for _ in range(10):
            try:
                if scal.is_trading_day(nd, days=days):
                    break
            except Exception:  # noqa: BLE001
                if nd.weekday() < 5:
                    break
            nd = nd + timedelta(days=1)
        self._next_trading_day = nd
        evs = self._load_events()
        try:
            self._events_today = oevents.is_event_day(d, events=evs)
        except Exception:  # noqa: BLE001
            self._events_today = []
        # calendar coverage guard (audit EVENTS-CALENDAR-1, opts-audit-wave3-calendar-v1): the
        # 2026-only hardcoded tables silently disarm the whole macro layer at rollover - say so
        # LOUDLY once per day while there is still time to add next year's tables.
        try:
            max_ev = max((e.ts_et.date() for e in evs), default=None)
            if max_ev is None or (max_ev - d).days < 30:
                self.ledger.journal({"event": "event_calendar_coverage_low", "day": day,
                                     "max_event_date": max_ev.isoformat() if max_ev else None,
                                     "note": "macro-event tables run out within 30 days - "
                                             "blackouts/MacroReaction/overnight-catalyst checks "
                                             "will silently disarm (EVENTS-CALENDAR-1)"})
        except Exception:  # noqa: BLE001
            pass
        # MacroReaction FOMC arm PARKED (audit + external research, opts-audit-parks-v1): the
        # published post-2015 record shows no post-print continuation edge and a robust 14:30
        # presser REVERSAL - the lane as designed bets against the evidence. Re-arm condition:
        # re-registration as a reversal/fade lane.
        macro_kinds = [k for k in (self._events_today or []) if str(k).lower() != "fomc"]
        if len(macro_kinds) != len(self._events_today or []):
            self.ledger.journal({"event": "macro_fomc_parked", "day": day,
                                 "kinds_today": list(self._events_today),
                                 "note": "FOMC continuation arm parked (opts-audit-parks-v1); "
                                         "re-arm = presser-reversal re-founding"})
        profiles = self._profiles_arg
        if profiles is None:
            lb = int(self.cfg["noise_lookback_days"])
            profiles = {s: _read_cached_profile(s, lb) for s in self.cfg["watch"]}
        for sym, prof in (profiles or {}).items():
            if prof is None:
                self.log(f"{sym}: no noise profile (cache absent/thin) - lane1 stands down")
        cands = self._lane2_candidates(day)
        p_by_lane = self.cfg.get("p_thesis_by_lane") or {}

        def _p_for(lane: str) -> float:
            try:
                return float(p_by_lane.get(lane, self.cfg["p_thesis"]))
            except (TypeError, ValueError):
                return float(self.cfg["p_thesis"])

        # Last30Lane PARKED (audit LANES-4, 3/4 refuters upheld: its 15%-of-move target cannot
        # arithmetically clear the selector EV floor except on ~2-sigma days - 6/6 lifetime
        # EV-stage deaths). Code kept; re-arm condition = target re-derivation registered in
        # opts-audit-parks-v1.
        self.lanes = [
            olanes.IndexTrendLane(profiles, p_thesis=_p_for("index_trend"),
                                  range_percentile_min=float(self.cfg["range_percentile_min"]),
                                  close_min=self._close_min),
            olanes.InPlayORBLane(cands, rvol_min=float(self.cfg["lane2_rvol_min"]),
                                 price_min=float(self.cfg["lane2_price_min"]),
                                 p_thesis=_p_for("inplay_orb"),
                                 close_min=self._close_min),
            olanes.MacroReactionLane(macro_kinds, p_thesis=_p_for("macro_reaction"),
                                     close_min=self._close_min),
            olanes.PreEarningsStubLane(),
        ]
        self.ledger.journal({"event": "lane_parked", "day": day, "lane": "last30",
                             "registration": "opts-audit-parks-v1",
                             "re_arm": "target re-derivation clears the selector EV floor"})
        self._lane_by_name = {ln.LANE: ln for ln in self.lanes}
        # restart safety: ALL still-open shadow positions (any day - an overnight hold must
        # survive the day roll or it is orphaned: never marked, never exited) + entry count
        self.positions = {}
        already_flagged = {r.get("position_id")
                           for r in oshadow.read_jsonl(self.ledger.journal_path)
                           if r.get("event") == "expired_unexited_position"}
        for pos in open_positions:
            if pos.expiry < today_d:
                # held past expiry with no exit record (process gap) - exclude from live
                # tracking and say so loudly ONCE; the grader still sees the unexited entry
                if pos.position_id not in already_flagged:
                    self.ledger.journal({"event": "expired_unexited_position",
                                         "ts_epoch": round(now, 3), "day": day,
                                         "position_id": pos.position_id, "occ": pos.occ,
                                         "entry_day": pos.entry_day})
                    self.log(f"{pos.occ}: entry {pos.entry_day} expired UNEXITED (process gap) "
                             f" - journaled, not tracked")
                continue
            self.positions[pos.position_id] = pos
        self.entries_today = len(self.ledger.load_entries(day))
        # re-seed the 45-min IV series from stored marks so a restart doesn't blank the IV
        # trend (and a single failed solve doesn't collapse iv to 1e-4 mid-position)
        for pos in self.positions.values():
            dq = deque()
            for mk in self.ledger.load_marks(pos.position_id):
                ts, ivv = float(mk.get("ts_epoch") or 0.0), float(mk.get("solved_iv") or 0.0)
                if ivv > 0 and now - ts <= 45 * 60:
                    dq.append((ts, ivv))
            if dq:
                self._iv_series[pos.occ] = dq
        if self.positions:
            self.log(f"rebuilt {len(self.positions)} open shadow position(s) from the ledger")
        # post-exit quote capture (audit REPLAY-LAB-1, opts-audit-wave0-evidence-v1): exited but
        # UNEXPIRED contracts keep receiving NBBO quote rows (flagged post_exit) to the thesis
        # horizon - same-day to the late-close window, DTE>=1 through the next session's close - 
        # so hold-longer replay variants finally have prices to be graded against.
        self._post_exit = {}
        try:
            for r in self.ledger.load_exits(day=None):
                pid = str(r.get("position_id") or "")
                occ = str(r.get("occ") or "")
                exp = _occ_expiry(occ)
                if (pid and occ and exp is not None and exp >= today_d
                        and now - float(r.get("ts_epoch") or 0.0) <= 80 * 3600):
                    self._post_exit[pid] = {"occ": occ,
                                            "underlying": str(r.get("underlying") or ""),
                                            "last_ts": 0.0}
        except Exception:  # noqa: BLE001 - capture is an upgrade, never a roll dependency
            self._post_exit = {}
        if self._post_exit:
            self.log(f"post-exit capture armed for {len(self._post_exit)} contract(s)")
        self.log(f"day {day} armed - lanes={sorted(self._lane_by_name)} "
                 f"events_today={self._events_today or 'none'} (fomc parked) "
                 f"lane2_cands={len(cands)}")
        self._day = day     # latched LAST (RUNNER-9): a failed roll retries next tick whole

    def _lane2_candidates(self, day: str | None = None) -> list:
        day = day if day is not None else self._day
        if self._lane2_arg is not None:
            return list(self._lane2_arg)
        out: dict[str, olanes.InPlayCandidate] = {}
        rows, session_date = load_hunt_list()
        # freshness contract (audit RUNNER-4/PREMARKET-CREW-1, opts-audit-wave1-funnel-v1):
        # a hunt list generated for ANOTHER session never arms lane 2 - its catalysts are gone
        # and the day would silently hunt dead names. Loud journal; the day arms lane-2-empty.
        if rows and session_date and day and session_date != day:
            self.ledger.journal({"event": "hunt_list_stale", "day": day,
                                 "session_date": session_date, "rows_dropped": len(rows),
                                 "note": "premarket artifact is for another session - lane 2 "
                                         "arms EMPTY (fail-open, loud)"})
            rows = []
        for row in rows:
            sym = row["symbol"]
            out[sym] = olanes.InPlayCandidate(symbol=sym, gap_pct=row["gap_pct"],
                                              catalyst=row["catalyst"],
                                              catalyst_kind=row.get("catalyst_kind"),
                                              avg_first5_volume=_avg_first5_from_cache(sym))
        scan = [str(s).upper() for s in (self.cfg.get("lane2_scan_symbols") or [])]
        if scan and self.client is not None:
            try:
                quotes = self.client.get_quotes(scan)
                for sym, q in quotes.items():
                    if sym in out or q.prevclose <= 0:
                        continue
                    gap = (q.last - q.prevclose) / q.prevclose * 100.0
                    if abs(gap) >= float(self.cfg["lane2_gap_min_pct"]):
                        out[sym] = olanes.InPlayCandidate(
                            symbol=sym, gap_pct=round(gap, 2), catalyst=False,
                            avg_first5_volume=_avg_first5_from_cache(sym),
                            average_volume=q.average_volume)
            except Exception:  # noqa: BLE001 - the gap scan is best-effort
                pass
        # Tradier 90d average_volume IS the RVOL baseline for every name since
        # opts-fix-lane2-rvol-scale-v1 (the IEX cache's avg_first5_volume never gates - 
        # consolidated-vs-IEX was ~30-50x inflated); hunt-list names have no scan-quote pass
        # above, so it must be fetched here or InPlayORB silently stands down on them
        missing = [s for s, c in out.items() if c.average_volume <= 0]
        if missing and self.client is not None:
            try:
                for sym, q in self.client.get_quotes(missing).items():
                    c = out.get(sym)
                    if c is not None and q.average_volume > 0:
                        out[sym] = replace(c, average_volume=float(q.average_volume))
            except Exception:  # noqa: BLE001 - best-effort; the journal row below stays honest
                pass
        for sym, c in out.items():
            if c.average_volume <= 0:
                self.ledger.journal({"event": "lane2_rvol_baseline_missing", "symbol": sym,
                                     "day": day,
                                     "note": "no average_volume (the consolidated-scale RVOL "
                                             "baseline) - InPlayORB stands down for this name "
                                             "(a 09:25 retry will re-fetch it: Wave 1.12)"})
        cands = sorted(out.values(), key=lambda c: abs(c.gap_pct), reverse=True)
        return cands[: int(self.cfg["lane2_max_candidates"])]

    # ------------------------------------------------------------------ market data plumbing
    def _watch_symbols(self) -> list:
        syms = [str(s).upper() for s in self.cfg["watch"]]
        for ln in self.lanes:
            if isinstance(ln, olanes.InPlayORBLane):
                syms.extend(ln.cands)
        for pos in self.positions.values():
            syms.append(pos.underlying)
        return list(dict.fromkeys(syms))

    def _backfill(self, symbols: list, now: float) -> None:
        # pre-open there is nothing to backfill (timesales are RTH-only) - attempting anyway
        # burned all BACKFILL_MAX_ATTEMPTS before 09:30 every day (audit RUNNER-6)
        dt = _et_dt(now)
        if dt.hour * 60 + dt.minute < olanes.OPEN_MIN + 1:
            return
        for sym in symbols:
            if sym in self._backfilled:
                continue
            bars = self.feed.backfill(sym)              # FAIL-OPEN: [] on any transport/parse error
            if bars:
                for b in bars:
                    self.builder.seed_bar(sym, b)
                    self._on_completed_bar(sym, b, now, backfill=True)
                self._backfilled.add(sym)               # mark done ONLY after a successful fetch
                self.log(f"{sym}: backfilled {len(bars)} bars")
                continue
            # no bars: bounded retry (a transient feed failure must not permanently starve a symbol
            # of session context), then give up for the day (opts-fix-backfill-retry-v1)
            n = self._backfill_attempts.get(sym, 0) + 1
            self._backfill_attempts[sym] = n
            if n >= BACKFILL_MAX_ATTEMPTS:
                self._backfilled.add(sym)
                self.ledger.journal({"event": "backfill_gave_up", "symbol": sym, "attempts": n})

    def _ctx_for_bar(self, sym: str, bar, now: float) -> olanes.MinuteCtx:
        if sym not in self._session_open:
            self._session_open[sym] = float(bar.open)
        bi = self.builder.bar_input(sym, bar)
        close_dt = _et_dt(now).replace(hour=(bar.minute + 1) // 60, minute=(bar.minute + 1) % 60,
                                       second=0, microsecond=0)
        return olanes.MinuteCtx(symbol=sym, minute=bar.minute, open=bar.open, high=bar.high,
                                low=bar.low, close=bar.close, volume=bar.volume,
                                session_open=self._session_open[sym], svwap=bi.svwap,
                                blackout=self._blackout_at(close_dt))

    def _on_completed_bar(self, sym: str, bar, now: float, *, backfill: bool = False) -> None:
        if bar.minute < olanes.OPEN_MIN or bar.minute >= self._close_min:
            # pre-open AND post-close bars never reach lanes: the launcher starts the shadow
            # ~08:30 ET, and premarket bars were burning IndexTrendLane's one-per-side latch
            # and priming session_open off a premarket print (refute find, 2026-07-10)
            return
        if not backfill:
            self._last_bar_epoch = now         # liveness: backfill seeding must not count
        ctx = self._ctx_for_bar(sym, bar, now)
        self._last_ctx[sym] = ctx
        # C5 price-shock reval trigger (registered opts-tweak-reval-triggers-v1): a violent
        # 1-min close-to-close move on a HELD underlying marks its positions NOW - 
        # observability only (close-vs-PREV-close, not open-vs-close: sparse single-tick bars
        # carry the move BETWEEN bars, not inside them)
        if not backfill and bar.close > 0:
            hist = self._bar_moves.setdefault(sym, deque(maxlen=21))
            move = abs(bar.close / hist[-1][0] - 1.0) if hist else None
            if move is not None and len(hist) >= 6:
                base_moves = [m for _c, m in hist if m is not None]
                base = sum(base_moves) / len(base_moves) if base_moves else 0.0
                thresh = max(float(self.cfg["reval_shock_floor"]),
                             float(self.cfg["reval_shock_mult"]) * base)
                if move > thresh:
                    shocked = [p for p in self.positions.values() if p.underlying == sym]
                    for pos in shocked:
                        pos.last_mark_ts = 0.0
                    if shocked:
                        self.ledger.journal({"event": "reval_trigger", "kind": "price_shock",
                                             "ts_epoch": round(now, 3), "symbol": sym,
                                             "move": round(move, 6),
                                             "threshold": round(thresh, 6),
                                             "positions": [p.position_id for p in shocked]})
            hist.append((bar.close, move))
        for lane in self.lanes:
            try:
                sig = lane.update(ctx)
            except Exception as exc:  # noqa: BLE001 - one lane bug never kills the loop
                self.ledger.journal({"event": "lane_error", "lane": getattr(lane, "LANE", "?"),
                                     "ts_epoch": round(now, 3), "error": repr(exc)})
                continue
            if sig is not None:
                self._on_signal(sig, now, backfill=backfill)

    # ------------------------------------------------------------------ signal -> entry
    def _lane_confirm(self, sig: olanes.LaneSignal) -> None:
        """Latch-at-entry (Wave 1.11): a confirmed entry latches the (symbol, side) for the day."""
        lane = self._lane_by_name.get(sig.lane)
        if lane is not None and hasattr(lane, "confirm_entry"):
            lane.confirm_entry(sig.underlying, sig.direction)

    def _lane_release(self, sig: olanes.LaneSignal, minute: int) -> None:
        """Latch-at-entry (Wave 1.11): a fire that died downstream re-arms after the cooldown
        while the lane predicate still holds - a selector rejection no longer burns the day."""
        lane = self._lane_by_name.get(sig.lane)
        if lane is not None and hasattr(lane, "release"):
            lane.release(sig.underlying, sig.direction, minute)

    def _on_signal(self, sig: olanes.LaneSignal, now: float, *, backfill: bool = False) -> None:
        dt = _et_dt(now)
        minute_now = dt.hour * 60 + dt.minute
        base = {"ts_epoch": round(now, 3), "day": self._day, "lane": sig.lane,
                "underlying": sig.underlying, "direction": sig.direction,
                "signal": asdict(sig)}
        if minute_now > sig.expires_minute:
            self.ledger.journal({**base, "event": "signal_expired",
                                 "note": "stale (backfill-era or slow loop)"})
            return
        if not (9 * 60 + 30 <= minute_now < self._close_min) or dt.weekday() >= 5:
            self.ledger.journal({**base, "event": "signal_after_hours_skip"})
            return
        blackout = self._blackout_at(dt)
        if blackout is not None:
            self.ledger.journal({**base, "event": "signal_blackout_skip", "blackout": blackout})
            self.log(f"{sig.underlying} {sig.lane}: signal SKIPPED (blackout={blackout})")
            self._lane_release(sig, minute_now)
            return
        for pos in self.positions.values():
            if pos.underlying == sig.underlying and pos.opt_type == sig.direction:
                if sig.lane not in pos.lanes:
                    pos.lanes.append(sig.lane)
                    self.ledger.write_merge(oshadow.build_merge_record(
                        ts=now, day=self._day, position_id=pos.position_id,
                        lane=sig.lane, signal=asdict(sig)))
                    self.log(f"{sig.underlying} {sig.lane}: merged into {pos.position_id}")
                else:
                    self.ledger.journal({**base, "event": "signal_duplicate_lane_skip"})
                self._lane_confirm(sig)          # exposure exists - latch the side for the day
                return
        if len(self.positions) >= int(self.cfg["max_concurrent"]):
            self.ledger.journal({**base, "event": "signal_concurrency_skip",
                                 "open_positions": len(self.positions)})
            self._lane_release(sig, minute_now)
            return
        if self.client is None:
            self.ledger.journal({**base, "event": "signal_no_client_skip"})
            self._lane_release(sig, minute_now)
            return
        self._enter(sig, now, base, stale_bar=backfill)

    def _chain_rows(self, sig: olanes.LaneSignal, today: date) -> tuple[list, list]:
        """(ContractQuote rows, expirations used). DTE 0-5 expirations (lane 1b: the NEAREST
        expiration >= 1 calendar day = the next trading session, so Friday fires pick Monday - 
        a strict dte==1 match would kill the 15:30 lane every Friday), bounded to
        max_chain_expirations chain requests."""
        one_dte_only = bool(sig.notes.get("one_dte_only"))
        pool: list[tuple[int, str]] = []
        for e in self.client.get_option_expirations(sig.underlying):
            try:
                d = date.fromisoformat(e)
            except ValueError:
                continue
            dte = (d - today).days
            if 0 <= dte <= 5:
                pool.append((dte, e))
        if one_dte_only:
            fut = [t for t in pool if t[0] >= 1]
            exps = [min(fut)[1]] if fut else []
        else:
            exps = [e for _, e in pool]
        exps = exps[: int(self.cfg["max_chain_expirations"])]
        rows: list[ContractQuote] = []
        for e in exps:
            for o in self.client.get_option_chain(sig.underlying, e, greeks=True):
                try:
                    expiry = date.fromisoformat(o.expiration or e)
                except ValueError:
                    expiry = date.fromisoformat(e)
                rows.append(ContractQuote(occ=o.symbol, underlying=sig.underlying,
                                          opt_type=o.option_type, strike=o.strike,
                                          expiry=expiry, bid=o.bid, ask=o.ask, last=o.last,
                                          volume=o.volume, open_interest=o.open_interest,
                                          vendor_iv=o.iv))
        return rows, exps

    def _enter(self, sig: olanes.LaneSignal, now: float, base: dict,
               stale_bar: bool = False) -> None:
        dt = _et_dt(now)
        today = dt.date()
        minute_now = dt.hour * 60 + dt.minute
        # backfill-era signal inside its TTL (audit RUNNER-7): refresh S with one live poll so
        # the entry prices against the CURRENT tape, not a minutes-old backfill close
        if stale_bar and self.client is not None:
            try:
                for s2, tk2 in self.client.get_quotes([sig.underlying]).items():
                    self._last_ticks[s2] = tk2
            except Exception:  # noqa: BLE001 - refresh is best-effort
                pass
        tick = self._last_ticks.get(sig.underlying)
        ctx = self._last_ctx.get(sig.underlying)
        S = tick.last if tick is not None and tick.last > 0 else (ctx.close if ctx else 0.0)
        if S <= 0:
            self.ledger.journal({**base, "event": "signal_no_underlying_skip"})
            self._lane_release(sig, minute_now)
            return
        # one bounded retry on the chain fetch (audit TRADIER-FEED-1: a single transient blip
        # killed ~7 days of expected funnel output at the observed fire rate)
        rows, exps, last_exc = [], [], None
        for attempt in (0, 1):
            try:
                rows, exps = self._chain_rows(sig, today)
                last_exc = None
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                rows, exps = [], []
            if rows:
                break
            if attempt == 0 and self._retry_sleep_s > 0:
                time.sleep(self._retry_sleep_s)
        if last_exc is not None and not rows:
            self.ledger.journal({**base, "event": "chain_fetch_error", "error": repr(last_exc),
                                 "retried": True})
            self._lane_release(sig, minute_now)
            return
        if not rows:
            self.ledger.journal({**base, "event": "no_chain_rows", "expirations": exps})
            self._lane_release(sig, minute_now)
            return
        # 2-minute tolerance (audit RUNNER-5/TIMESCALE-STACK-7): a >=1-min bar-completion delay
        # used to silently flip an intraday signal to "overnight" and ban all DTE<2 contracts
        rest_of_day = max(0, self._close_min - minute_now) / 390.0 / 252.0
        may_overnight = sig.horizon_T > (rest_of_day + 2.0 / 390.0 / 252.0) * 1.001
        iv_rank = None
        if self._iv_archive is not None:
            try:
                iv_rank = self._iv_archive.iv_rank(sig.underlying, tenor_dte=2)
            except Exception:  # noqa: BLE001
                iv_rank = None
        # WS3 halt/suspension DATA-QUALITY guard (opts-ws3-halt-gate-v1): read the latest
        # symbol_state snapshot O(1) (fail-open) and, if this underlying is authoritatively HALTED
        # or SEC-SUSPENDED, thread that into the selector so every contract is rejected as
        # underlying_{state}. Entries are per-signal (not per-tick), so a small file read is fine;
        # state_reasons asserts a halt only on data fresh <=180s. NOT on the promotion ladder - a
        # validity filter, like no_quote. underlying_state MUST be None when clear so the gate is inert.
        try:
            _ss_snap = json.loads((RUNTIME / "symbol_state.json").read_text("utf-8"))
            _state_reasons = symbol_state.state_reasons(sig.underlying, _ss_snap, now)
        except Exception:  # noqa: BLE001 - a torn/wrong-shape symbol_state.json (incl. valid-JSON-
            _state_reasons = []            #   wrong-type) must never take a cycle down (fail-open)
        underlying_state = ("halted" if "halted" in _state_reasons
                            else "sec_suspended" if "sec_suspended" in _state_reasons else None)
        res = select_contract(rows, underlying=sig.underlying, S=S, direction=sig.direction,
                              target_move=sig.target_move, p_thesis=sig.p_thesis,
                              horizon_T=sig.horizon_T, now_et=dt.replace(tzinfo=None),
                              hv20=None, iv_rank=iv_rank, event_blackout=None,
                              underlying_state=underlying_state,
                              may_run_overnight=may_overnight,
                              params=self._selector_params, top_n=int(self.cfg["top_n"]))
        reasons: dict[str, int] = {}
        for _occ, code in res.rejections:
            reasons[code] = reasons.get(code, 0) + 1
        if not res.picks:
            self.ledger.journal({**base, "event": "no_pick", "rejections": reasons,
                                 "rows": len(rows), "underlying_state": underlying_state})
            self.log(f"{sig.underlying} {sig.lane}: NO PICK ({reasons})")
            self._lane_release(sig, minute_now)
            return
        pick = res.picks[0]
        cq = pick.quote
        # entries_today suffix keeps the id unique when the same occ exits and re-enters
        # within one minute (a reused id would read as already-exited on rebuild)
        position_id = f"{cq.occ}:{self._day}:{minute_now}:{self.entries_today}"
        pick_dict = {"occ": cq.occ, "underlying": cq.underlying, "opt_type": cq.opt_type,
                     "strike": cq.strike, "expiry": cq.expiry.isoformat(), "bid": cq.bid,
                     "ask": cq.ask, "S": S, "score": pick.score, "ev_usd": pick.ev_usd,
                     "ev_pct": pick.ev_pct, "p_profit": pick.p_profit,
                     "p_touch_target": pick.p_touch_target, "solved_iv": pick.solved_iv,
                     "delta": pick.delta, "gamma": pick.gamma, "theta_day": pick.theta_day,
                     "vega": pick.vega, "lam": pick.lam, "spread_pct": pick.spread_pct,
                     "dte": pick.dte, "flags": list(pick.flags),
                     "decomposition": dict(pick.decomposition),
                     "best_dte_outside_skew": res.best_dte_outside_skew}
        flags = list(pick.flags)
        if pick.dte == 0 and minute_now >= 12 * 60:
            flags.append("zero_dte_afternoon")
        if pick.spread_pct > 0.05:
            flags.append("spread_gt_5pct")
        if may_overnight:
            flags.append("overnight_exception")
        # C2 regime covariates (graded at N, never gates) + C3 runner-up snapshot (the
        # counterfactual-selector lab's input): both registered opts-covariates-v1
        idx_rets = []
        for isym in ("SPY", "QQQ", "IWM"):
            ictx = self._last_ctx.get(isym)
            if ictx is not None and ictx.session_open > 0 and ictx.close > 0:
                idx_rets.append(ictx.close / ictx.session_open - 1.0)
        uctx = self._last_ctx.get(sig.underlying)
        nc = self._news_cache
        if nc is not None:
            nc.update()                            # freshen the tail before reading (entries are rare)
        cc = self._catalyst_ctx.get(sig.underlying) or {}   # WS4 catmem base rates for this name ({} if none)
        covariates = {
            "idx_ret_disp": round(max(idx_rets) - min(idx_rets), 6) if len(idx_rets) >= 2 else None,
            "vwap_dist": (round((uctx.close - uctx.svwap) / uctx.close, 6)
                          if uctx is not None and uctx.close > 0 and uctx.svwap > 0 else None),
            "is_friday": dt.weekday() == 4,
            # WS3 observe-first (opts-ws3-halt-gate-v1): operational-state context for entries that
            # PROCEED (e.g. ssr_active). Halt/suspension entries never reach here - they no-pick above.
            "underlying_state": ",".join(_state_reasons) if _state_reasons else None,
            # WS4 catalyst covariate (opts-catalyst-kind-covariate-v1): the crew catalyst KIND behind
            # a lane-2 candidate (None for index lanes) - graded at N, gates nothing.
            "catalyst_kind": sig.notes.get("catalyst_kind"),
            # WS4 news covariates (opts-news-covariates-v1): from the C6 news_flags tail; all nullable
            "news_shock_15m": nc.news_shock_15m(sig.underlying, now) if nc else None,
            "news_kind_recent": nc.news_kind_recent(sig.underlying, now) if nc else None,
            "news_direction_align": (nc.news_direction_align(sig.underlying, sig.direction, now)
                                     if nc else None),
            "headline_age_min": nc.headline_age_min(sig.underlying, now) if nc else None,
            "news_count_60m": nc.news_count_60m(sig.underlying, now) if nc else None,
            # WS4 catmem covariates (opts-catmem-covariates-v1): historical forward-move base rates
            # for this name's catalyst kind (premarket recall); all nullable, graded at N.
            "kind_hist_n": cc.get("kind_hist_n"),
            "kind_hist_ret2d_med": cc.get("kind_hist_ret2d_med"),
            "kind_hist_p_pos2d": cc.get("kind_hist_p_pos2d"),
        }
        runner_up_snapshot = [{"occ": p.quote.occ, "bid": p.quote.bid, "ask": p.quote.ask,
                               "strike": p.quote.strike, "expiry": p.quote.expiry.isoformat(),
                               "dte": p.dte, "delta": p.delta, "score": p.score,
                               "ev_pct": p.ev_pct} for p in res.picks[1:]]
        rec = oshadow.build_entry_record(
            ts=now, day=self._day, entry_minute=minute_now, position_id=position_id,
            lanes=[sig.lane], config_hash=self.cfg_hash, signal=asdict(sig),
            pick=pick_dict, runner_up_occs=[p.quote.occ for p in res.picks[1:]],
            nbbo={"bid": cq.bid, "ask": cq.ask}, risk_flags=flags,
            iv_rank=iv_rank, hv20=None, vix=None,
            covariates=covariates, runner_up_snapshot=runner_up_snapshot)
        self.ledger.write_entry(rec)
        entry_mid = cq.mid
        tgt = abs(sig.target_move)
        target_under = S * (1.0 + tgt) if sig.direction == "call" else S * (1.0 - tgt)
        pos = oshadow.ShadowPosition(
            position_id=position_id, occ=cq.occ, underlying=sig.underlying,
            opt_type=sig.direction, strike=cq.strike, expiry=cq.expiry, lanes=[sig.lane],
            direction=sig.direction, target_underlying=target_under, mu_thesis=sig.mu_thesis,
            p_thesis=sig.p_thesis, horizon_T=sig.horizon_T, entry_ts=now,
            entry_minute=minute_now, entry_day=self._day, entry_S=S, entry_bid=cq.bid,
            entry_ask=cq.ask, entry_mid=entry_mid, entry_fills=rec["fills"],
            entry_theta_day=pick.theta_day, peak_mid=entry_mid, last_mark_ts=now,
            print_minute=(int(sig.notes["print_minute"]) if "print_minute" in sig.notes else None),
            notes=dict(sig.notes))
        self.positions[position_id] = pos
        self._iv_series[cq.occ] = deque()
        if pick.solved_iv > 0:
            self._iv_series[cq.occ].append((now, pick.solved_iv))
        self.entries_today += 1
        self._lane_confirm(sig)                       # latch the side for the day (Wave 1.11)
        # mark-at-entry quote row (audit REPLAY-LAB-3 root fix): every position gets an
        # entry-anchored quote-path row so first-mark exits are replayable
        self.ledger.write_quote(self._day, oshadow.build_quote_record(
            ts=now, occ=cq.occ, bid=cq.bid, ask=cq.ask, S=S, position_id=position_id,
            ext={"entry_row": True, "solved_iv": round(pick.solved_iv or 0.0, 4),
                 "p_thesis": sig.p_thesis, "horizon_T": sig.horizon_T,
                 "minute": minute_now}))
        self.log(f"SHADOW ENTRY {sig.underlying} {sig.direction} {cq.occ} "
                 f"lane={sig.lane} score={pick.score} ev%={pick.ev_pct} fills={rec['fills']}")

    # ------------------------------------------------------------------ reval / exits
    def _mark_interval_s(self, pos: oshadow.ShadowPosition, dt: datetime) -> float:
        minute = dt.hour * 60 + dt.minute
        if minute >= self._close_min:
            return 60.0                          # after-hours late-close window: tight marks
        dte = (pos.expiry - dt.date()).days
        if dte <= 0:
            if minute >= self._close_min - 30:
                return 60.0                      # last 30 min before expiry
            if minute >= self._close_min - 120:
                return 120.0                     # 0DTE afternoon
        return 300.0

    def _fresh_option_quote(self, pos: oshadow.ShadowPosition):
        """(bid, ask) via the batched quotes endpoint; chain-row fallback when the occ is
        missing from the response. None when nothing usable came back.
        Audit RUNNER-10/SHADOW-LEDGER-3: a ZERO bid with a live ask IS a usable book (the truth
        of a dying OTM contract) - requiring bid>0 made losers unmarkable, so rule (a)'s clock
        never fired and forced exits booked phantom stale-mark value on the grading ledger."""
        try:
            q = self.client.get_quotes([pos.occ]).get(pos.occ)
        except Exception:  # noqa: BLE001
            q = None
        if q is not None and q.ask > 0 and q.ask >= q.bid >= 0:
            return float(q.bid), float(q.ask)
        try:
            for o in self.client.get_option_chain(pos.underlying,
                                                  pos.expiry.isoformat(), greeks=False):
                if o.symbol == pos.occ and o.ask > 0 and o.ask >= o.bid >= 0:
                    return float(o.bid), float(o.ask)
        except Exception:  # noqa: BLE001
            pass
        return None

    def _thesis_valid(self, pos: oshadow.ShadowPosition, S: float, minute: int) -> bool:
        """Merged positions: invalid only when EVERY constituent lane says invalidated (each
        lane tag is an independent thesis for the same exposure).

        Audit 2026-07-16 Wave 2.13 (EXIT-ENGINE-1/RUNNER-2, the b_thesis_invalid hair-trigger
        that decided 2 of 3 lifetime trades): invalidation is now judged on the last COMMITTED
        bar close on the bar clock (never a raw 10-second tick on the wall clock), against the
        ENTRY-frozen band with hysteresis (lanes.py), and must persist for 2 consecutive
        evaluations on NEW bars before rule (b) may fire. Overnight grantees are exempt until
        their own frame is re-establishable (30 RTH minutes - RUNNER-3: judging yesterday's
        thesis in today's move-from-open frame cut every grantee at the open)."""
        if pos.entry_day != self._day and minute < olanes.OPEN_MIN + 30:
            pos.thesis_invalid_streak = 0
            return True
        ctx = self._last_ctx.get(pos.underlying)
        if ctx is None:
            return True                        # no committed context - never flip the thesis
        last_eval = getattr(pos, "_thesis_eval_minute", None)
        if last_eval == ctx.minute:            # no NEW bar since the last evaluation
            return pos.thesis_invalid_streak < 2
        pos._thesis_eval_minute = ctx.minute   # transient (not rebuilt across restarts - safe:
        #                                        a restart just re-evaluates on the next bar)
        frozen_band = 0.0
        try:
            frozen_band = float((pos.notes or {}).get("noise_width") or 0.0)
        except (TypeError, ValueError):
            frozen_band = 0.0
        pctx = olanes.PositionCtx(symbol=pos.underlying, direction=pos.opt_type,
                                  minute=ctx.minute, close=ctx.close,
                                  svwap=ctx.svwap if ctx else 0.0,
                                  session_open=ctx.session_open if ctx else 0.0,
                                  frozen_band=frozen_band)
        verdicts = []
        for tag in pos.lanes:
            lane = self._lane_by_name.get(tag)
            if lane is None:
                continue
            try:
                verdicts.append(bool(lane.invalidated(pctx)))
            except Exception:  # noqa: BLE001
                verdicts.append(False)
        raw_invalid = bool(verdicts) and all(verdicts)
        pos.thesis_invalid_streak = pos.thesis_invalid_streak + 1 if raw_invalid else 0
        return pos.thesis_invalid_streak < 2

    def _force_exit(self, pid: str, now: float, rule: str) -> None:
        """Runner-written structural exit (process anomaly / late-close hard flat): NBBO
        fallback chain fresh quote -> last stored mark -> entry NBBO, each degradation
        journaled. Distinct from engine decisions - decision_state says it was forced."""
        pos = self.positions.get(pid)
        if pos is None:
            return
        dt = _et_dt(now)
        minute = dt.hour * 60 + dt.minute
        quote = self._fresh_option_quote(pos)
        degraded = None
        if quote is not None:
            bid, ask = quote
        else:
            marks = self.ledger.load_marks(pid)
            if marks:
                bid, ask = float(marks[-1].get("bid") or 0.0), float(marks[-1].get("ask") or 0.0)
                degraded = "last_mark_nbbo"
            else:
                bid, ask = pos.entry_bid, pos.entry_ask
                degraded = "entry_nbbo"
        if degraded:
            self.ledger.journal({"event": "late_close_quote_degraded", "ts_epoch": round(now, 3),
                                 "position_id": pid, "occ": pos.occ, "fallback": degraded,
                                 "rule": rule})
        # fill provenance (audit SHADOW-LEDGER-3): the grading ledger must SEE that a forced
        # exit filled at a fallback NBBO - the grader flags/excludes stale-source fills
        if degraded == "last_mark_nbbo":
            marks = self.ledger.load_marks(pid)
            age_s = round(now - float(marks[-1].get("ts_epoch") or now), 1) if marks else None
        elif degraded == "entry_nbbo":
            age_s = round(now - pos.entry_ts, 1)
        else:
            age_s = 0.0
        tick = self._last_ticks.get(pos.underlying)
        S = tick.last if tick is not None and tick.last > 0 else pos.entry_S
        held = _trading_days_held(pos.entry_day, pos.entry_minute, self._day, minute)
        self.ledger.write_exit(oshadow.build_exit_record(
            ts=now, day=self._day, pos=pos, rule=rule, bid=bid, ask=ask,
            solved_iv=0.0, S=S,
            decision_state={"forced": True, "after_hours": True,
                            "nbbo_source": degraded or "fresh", "nbbo_age_s": age_s},
            variant_would_hold=False, hold_trading_days=held))
        del self.positions[pid]
        self._iv_series.pop(pos.occ, None)
        self._post_exit[pid] = {"occ": pos.occ, "underlying": pos.underlying, "last_ts": 0.0}
        self.log(f"SHADOW FORCED EXIT {pos.underlying} {pos.occ} rule={rule} "
                 f"bid={bid} ask={ask}{' (' + degraded + ')' if degraded else ''}")

    def _reval_positions(self, now: float) -> None:
        if self.client is None or not self.positions:
            return
        dt = _et_dt(now)
        minute = dt.hour * 60 + dt.minute
        # event context, computed ONCE per sweep from the real calendar (hardcoded-False stubs
        # here made the never-hold-through-a-print rule and the DTE>=3 overnight exception
        # unreachable dead code): minutes until TODAY's next macro release, and whether the
        # next TRADING day carries a named macro catalyst (the overnight exception's gate).
        evs = self._load_events()
        mins_to_print = None
        try:
            for e in oevents.upcoming_events(dt, horizon_days=1, events=evs):
                if e.ts_et.date() == dt.date():
                    mins_to_print = max(0, int((e.ts_et - dt).total_seconds() // 60))
                    break
        except Exception:  # noqa: BLE001 - event context is protective, never a crash source
            mins_to_print = None
        named_tomorrow = False
        try:
            # session-calendar next day computed at the roll (audit EVENTS-CALENDAR-5: the old
            # weekday-skip called a holiday "tomorrow" and mis-gated the overnight grant)
            nd = self._next_trading_day
            if nd is None:
                nd = dt.date() + timedelta(days=1)
                while nd.weekday() >= 5:
                    nd += timedelta(days=1)
            named_tomorrow = bool(oevents.is_event_day(nd, events=evs))
        except Exception:  # noqa: BLE001
            named_tomorrow = False
        after_hours = minute >= self._close_min
        if self._news_cache is not None:
            self._news_cache.update()              # freshen the news tail once per sweep (WS5)
        self._news_marked = {p: f for p, f in self._news_marked.items() if p in self.positions}
        # halted-underlying sweep (audit TRAJECTORY-8/DEAD-LAYERS-6): a halted tape must read as
        # DEGRADED EVIDENCE (statistical exits blocked, prior dropped), never "thesis intact"
        halted_now: set = set()
        if self.positions:
            try:
                _snap = json.loads((RUNTIME / "symbol_state.json").read_text("utf-8"))
                for _u in {p.underlying for p in self.positions.values()}:
                    if "halted" in symbol_state.state_reasons(_u, _snap, now):
                        halted_now.add(_u)
            except Exception:  # noqa: BLE001 - fail-open, like the entry-side gate
                halted_now = set()
            for _u in halted_now:
                if _u not in self._halted_flagged:
                    self._halted_flagged.add(_u)
                    self.ledger.journal({"event": "halted_while_held", "ts_epoch": round(now, 3),
                                         "symbol": _u, "day": self._day})
            self._halted_flagged &= halted_now     # clear on resume -> a NEW stretch journals again
        for pid in list(self.positions):
            pos = self.positions[pid]
            if after_hours and pos.underlying.upper() not in INDEX_UNDERLYINGS:
                # a non-late-close position open past the equity close is a process anomaly
                # (0DTE dies at rule (a), everything else at the eod/planned clocks) - force
                # it flat LOUDLY rather than mark it on a dead book. EXCEPTION: a plausible
                # overnight grantee (DTE>=3 + named catalyst tomorrow + not Friday - the
                # evidence rule's own exception arm) falls through to the mark path, where
                # the after-hours ladder re-checks with real delta and grants or flats.
                dte_pos = (pos.expiry - dt.date()).days
                if not (dte_pos >= 3 and named_tomorrow and dt.weekday() != 4):
                    self._force_exit(pid, now, "post_close_forced_flat")
                    continue
            # WS5 news-shock mark-accel (opts-news-shock-accel-v1): a fresh high-materiality shock on
            # this underlying forces an immediate re-mark (bypassing the cadence) - WHEN we mark, never
            # WHAT the exit engine decides. The SAME C5 idiom (sets last_mark_ts + journals only, never
            # reads/alters exit_engine); deduped once per shock fingerprint per position.
            if self._news_cache is not None:
                _shock = self._news_cache.fresh_shock(pos.underlying, now)
                if _shock is not None:
                    _fp = str(_shock.get("fingerprint") or _shock.get("news_id") or "")
                    if _fp and self._news_marked.get(pid) != _fp:
                        self._news_marked[pid] = _fp
                        pos.last_mark_ts = 0.0
                        self.ledger.journal({"event": "reval_trigger", "kind": "news_shock",
                                             "ts_epoch": round(now, 3), "position_id": pid,
                                             "occ": pos.occ, "underlying": pos.underlying,
                                             "news_kind": _shock.get("kind"),
                                             "materiality": _shock.get("materiality"),
                                             "fingerprint": _fp})
            if now - pos.last_mark_ts < self._mark_interval_s(pos, dt):
                continue
            quote = self._fresh_option_quote(pos)
            if quote is None:
                if after_hours and minute >= self._late_close_flat_min:
                    # NBBO gone before we flattened - exit at last stored mark, never ride
                    # into close+15 where the book truly dies
                    self._force_exit(pid, now, "late_close_flat")
                    continue
                self.ledger.journal({"event": "mark_no_quote", "ts_epoch": round(now, 3),
                                     "position_id": pid, "occ": pos.occ})
                self._noquote_streak[pid] = self._noquote_streak.get(pid, 0) + 1
                if self._noquote_streak[pid] == 3:
                    # a persistently unusable book is a data problem, not routine noise
                    self.ledger.journal({"event": "mark_no_quote_streak", "ts_epoch": round(now, 3),
                                         "position_id": pid, "occ": pos.occ, "streak": 3})
                pos.last_mark_ts = now
                continue
            self._noquote_streak.pop(pid, None)
            bid, ask = quote
            # one-sided (bid=0, live ask) books price at the half-ask mid - the truth of a dying
            # OTM contract (audit RUNNER-10; the old max(bid,0)=0 made the engine blind to them)
            mid = (bid + ask) / 2.0 if ask > 0 else max(bid, 0.0)
            tick = self._last_ticks.get(pos.underlying)
            ctx = self._last_ctx.get(pos.underlying)
            S = tick.last if tick is not None and tick.last > 0 else (ctx.close if ctx else 0.0)
            # evidence staleness (audit Wave 2.16 / TRAJECTORY-8): committed bars stopped
            # arriving (>3 min silence mid-session) or the underlying is exchange-halted - 
            # the statistical exits must not run on a frozen frame
            u_mins_all, _, _, _, _, _ = self.builder.session_arrays(pos.underlying)
            bar_stale = (not after_hours and bool(u_mins_all)
                         and (minute - int(u_mins_all[-1])) > 3)
            evidence_stale = bar_stale or (pos.underlying in halted_now)
            if S <= 0 and not after_hours:
                pos.last_mark_ts = now
                continue                # after-hours proceeds S-free (the ladder never reads S)
            if S > 0:
                pos.observe_underlying(S)
                if not after_hours and pos.underlying.upper() not in INDEX_UNDERLYINGS:
                    # frozen-tape observability (halt proxy): a held single name whose S has
                    # not printed for >= 10 min mid-session gets journaled ONCE per stretch
                    prev = self._s_freeze.get(pos.underlying)
                    if prev is None or prev[0] != S:
                        self._s_freeze[pos.underlying] = (S, now, False)
                    elif not prev[2] and now - prev[1] >= 600:
                        self._s_freeze[pos.underlying] = (S, prev[1], True)
                        self.ledger.journal({"event": "possible_halt", "ts_epoch": round(now, 3),
                                             "symbol": pos.underlying, "frozen_S": S,
                                             "frozen_for_s": round(now - prev[1], 1)})
            pos.peak_mid = max(pos.peak_mid, mid)
            if bid > 0:
                pos.peak_bid = max(pos.peak_bid, bid)   # d2* cost-basis high-water (realizable)
            T = om.trading_T(dt.replace(tzinfo=None), pos.expiry,
                             close_minute=self._close_min)
            ot = OptionType.CALL if pos.opt_type == "call" else OptionType.PUT
            series = self._iv_series.setdefault(pos.occ, deque())
            if after_hours:
                # frozen S: a solve would be fiction - carry the last good IV, don't extend
                # the trend series, and hand the engine a flat trend
                iv = series[-1][1] if series else 0.0
                iv_trend = 0.0
            else:
                iv = None
                if mid > 0:
                    try:
                        iv = implied_vol(mid, S, pos.strike, float(self.cfg["r"]), 0.0, T, ot)
                    except Exception:  # noqa: BLE001
                        iv = None
                if iv is None or iv <= 0:
                    iv = series[-1][1] if series else 0.0
                else:
                    series.append((now, iv))
                while series and now - series[0][0] > 45 * 60:
                    series.popleft()
                iv_trend = _ols_slope_per_hour(series)
            # live trajectory evidence (opts-rework-exit-core-v1): trailing committed closes
            # through the estimator; after-hours S is frozen -> no view (the ladder is S-free)
            thesis_ok = True if after_hours else self._thesis_valid(pos, S, minute)
            if after_hours:
                under = None
            else:
                u_mins, _, _, _, u_closes, _ = self.builder.session_arrays(pos.underlying)
                under = otraj.underlying_state(
                    u_mins, u_closes, iv=iv if iv and iv > 0 else 0.0,
                    window_min=int(self.cfg["mu_window_min"]))
            pv = PositionView(
                occ=pos.occ, underlying=pos.underlying, opt_type=pos.opt_type,
                strike=pos.strike, expiry=pos.expiry, entry_mid=pos.entry_mid,
                peak_mid=pos.peak_mid, lane=",".join(pos.lanes),
                target_underlying=pos.target_underlying, mu_thesis=pos.mu_thesis,
                thesis_valid=thesis_ok,
                entry_ts_min=pos.entry_minute,
                entry_ask=pos.entry_ask, peak_bid=pos.peak_bid,
                S=S, bid=bid, ask=ask, solved_iv=iv if iv and iv > 0 else 1e-4,
                iv_trend_per_hour=iv_trend,
                mu_hat=under.mu_hat if under else None,
                mu_t_stat=under.t_stat if under else 0.0,
                opposing_defense=under.opposing_defense if under else False,
                defense_zone_score=under.defense_zone_score if under else 0.0,
                is_event_straddle=False,
                minutes_since_print=(minute - pos.print_minute
                                     if pos.print_minute is not None else None),
                minutes_to_next_print=mins_to_print,
                planned_exit_minute=(int(pos.notes["planned_exit_minute"])
                                     if isinstance(pos.notes, dict)
                                     and pos.notes.get("planned_exit_minute") is not None
                                     else None),
                event_tminus1_close=False, named_catalyst_tomorrow=named_tomorrow,
                is_friday=dt.weekday() == 4,
                theta_share_breaches=pos.theta_share_breaches,
                after_hours=after_hours,
                # audit 2026-07-16 Wave 2 (exit-engine v3) inputs:
                p_thesis=pos.p_thesis, horizon_T=pos.horizon_T,
                evidence_stale=evidence_stale,
                h_breach_since_min=pos.h_breach_since_min,
                i_breach_since_min=pos.i_breach_since_min)
            try:
                decision = decide_exit(pv, dt.replace(tzinfo=None), self._exit_params)
            except Exception as exc:  # noqa: BLE001 - an engine error marks HOLD + journals
                self.ledger.journal({"event": "exit_engine_error", "ts_epoch": round(now, 3),
                                     "position_id": pid, "error": repr(exc)})
                pos.last_mark_ts = now
                continue
            # quote-path row (schema 2): the full engine-input snapshot so a decide_exit-based
            # paired replay can rebuild PositionView per stored step (opts-rework-exit-core-v1)
            _orb_lane = self._lane_by_name.get("inplay_orb")
            _or_rng = _orb_lane.or_range(pos.underlying) if _orb_lane is not None else None
            self.ledger.write_quote(self._day, oshadow.build_quote_record(
                ts=now, occ=pos.occ, bid=bid, ask=ask, S=S, position_id=pid,
                ext={"solved_iv": round(iv or 0.0, 4),
                     "iv_trend_per_hour": round(iv_trend, 4),
                     "mu_hat": (round(under.mu_hat, 4)
                                if under and under.mu_hat is not None else None),
                     "mu_t_stat": round(under.t_stat, 3) if under else 0.0,
                     "thesis_valid": bool(thesis_ok),
                     "opposing_defense": bool(under.opposing_defense) if under else False,
                     "defense_zone_score": round(under.defense_zone_score, 2) if under else 0.0,
                     "minutes_to_next_print": mins_to_print,
                     "minutes_since_print": (minute - pos.print_minute
                                             if pos.print_minute is not None else None),
                     "planned_exit_minute": pv.planned_exit_minute,
                     "named_catalyst_tomorrow": bool(named_tomorrow),
                     "is_friday": dt.weekday() == 4,
                     "after_hours": bool(after_hours),
                     "theta_share_breaches": int(pos.theta_share_breaches),
                     "minute": minute,
                     # audit Wave 0/2 replay-fidelity additions (REPLAY-LAB-2: variant thesis
                     # policies + the v3 persistence clocks must be rebuildable per stored step)
                     "p_thesis": round(pos.p_thesis, 4), "horizon_T": round(pos.horizon_T, 8),
                     "evidence_stale": bool(evidence_stale),
                     "thesis_streak": int(pos.thesis_invalid_streak),
                     "h_breach_since_min": pos.h_breach_since_min,
                     "i_breach_since_min": pos.i_breach_since_min,
                     "thesis_inputs": {
                         "bar_minute": (self._last_ctx[pos.underlying].minute
                                        if pos.underlying in self._last_ctx else None),
                         "bar_close": (self._last_ctx[pos.underlying].close
                                       if pos.underlying in self._last_ctx else None),
                         "svwap": (self._last_ctx[pos.underlying].svwap
                                   if pos.underlying in self._last_ctx else None),
                         "session_open": (self._last_ctx[pos.underlying].session_open
                                          if pos.underlying in self._last_ctx else None),
                         "frozen_band": (pos.notes or {}).get("noise_width"),
                         "or_range": list(_or_rng) if _or_rng else None}}))
            self._last_mark_epoch = now        # liveness: marked off a usable book
            pos.theta_share_breaches = decision.theta_share_breaches
            pos.h_breach_since_min = decision.h_breach_since_min     # Wave 2.14 persistence
            pos.i_breach_since_min = decision.i_breach_since_min     # clocks, engine-carried
            pos.last_mark_ts = now
            if decision.action == HOLD:
                self.ledger.write_mark(oshadow.build_mark_record(
                    ts=now, position_id=pid, occ=pos.occ, bid=bid, ask=ask,
                    solved_iv=iv or 0.0, S=S, decision_state=decision.state,
                    action=decision.action, rule=decision.rule))
            else:
                held = _trading_days_held(pos.entry_day, pos.entry_minute, self._day, minute)
                dstate = dict(decision.state)
                dstate.setdefault("nbbo_source", "fresh")
                dstate.setdefault("nbbo_age_s", 0.0)
                self.ledger.write_exit(oshadow.build_exit_record(
                    ts=now, day=self._day, pos=pos, rule=decision.rule, bid=bid, ask=ask,
                    solved_iv=iv or 0.0, S=S, decision_state=dstate,
                    variant_would_hold=decision.variant_would_hold, hold_trading_days=held))
                del self.positions[pid]
                self._iv_series.pop(pos.occ, None)
                # post-exit capture (REPLAY-LAB-1): keep quoting this contract to the horizon
                self._post_exit[pid] = {"occ": pos.occ, "underlying": pos.underlying,
                                        "last_ts": 0.0}
                self.log(f"SHADOW EXIT {pos.underlying} {pos.occ} rule={decision.rule} "
                         f"bid={bid} ask={ask}")

    def _mark_post_exit(self, now: float) -> None:
        """Post-exit quote capture (audit REPLAY-LAB-1, opts-audit-wave0-evidence-v1): exited
        contracts keep receiving NBBO quote rows at the slow cadence until the late-close
        window, so hold-longer replay variants finally have real prices to be graded against.
        Read-only market data; writes quote rows only; zero decision input."""
        if self.client is None or not self._post_exit:
            return
        dt = _et_dt(now)
        minute = dt.hour * 60 + dt.minute
        if minute >= self._late_close_flat_min or minute < olanes.OPEN_MIN:
            return
        due = [(pid, st) for pid, st in self._post_exit.items()
               if now - float(st.get("last_ts") or 0.0) >= 300.0]
        if not due:
            return
        try:
            quotes = self.client.get_quotes([st["occ"] for _pid, st in due])
        except Exception:  # noqa: BLE001 - capture is best-effort
            return
        for pid, st in due:
            st["last_ts"] = now
            q = quotes.get(st["occ"])
            if q is None or not (q.ask > 0 and q.ask >= q.bid >= 0):
                continue
            tick = self._last_ticks.get(st.get("underlying") or "")
            S = tick.last if tick is not None and tick.last > 0 else 0.0
            self.ledger.write_quote(self._day, oshadow.build_quote_record(
                ts=now, occ=st["occ"], bid=float(q.bid), ask=float(q.ask), S=S,
                position_id=pid, ext={"post_exit": True, "minute": minute}))

    def _rvol_baseline_retry(self, now: float) -> None:
        """Second average_volume fetch in the 09:25-09:35 window (audit Wave 1.12): a single
        transient quote failure at the 08:30 day roll used to stand ~40% of the lane-2 universe
        down for the whole day (21 lane2_rvol_baseline_missing journals in 3 sessions)."""
        if self._rvol_retried or self.client is None:
            return
        dt = _et_dt(now)
        minute = dt.hour * 60 + dt.minute
        if not (olanes.OPEN_MIN - 5 <= minute < olanes.OPEN_MIN + 5):
            return
        self._rvol_retried = True
        lane = self._lane_by_name.get("inplay_orb")
        if lane is None or not getattr(lane, "cands", None):
            return
        missing = [s for s, c in lane.cands.items() if c.average_volume <= 0]
        if not missing:
            return
        try:
            quotes = self.client.get_quotes(missing)
        except Exception:  # noqa: BLE001 - best-effort; the roll already journaled the misses
            return
        fixed = []
        for sym, q in quotes.items():
            c = lane.cands.get(sym)
            if c is not None and q.average_volume > 0:
                lane.cands[sym] = replace(c, average_volume=float(q.average_volume))
                fixed.append(sym)
        if fixed:
            self.ledger.journal({"event": "lane2_rvol_baseline_recovered", "day": self._day,
                                 "symbols": sorted(fixed), "ts_epoch": round(now, 3)})

    # ------------------------------------------------------------------ heartbeat + tick
    def _write_heartbeat(self, now: float) -> None:
        obj = {"schema": 2, "pid": os.getpid(), "ts_epoch": round(now, 3), "day": self._day,
               "lanes_armed": sorted(self._lane_by_name),
               "open_positions": len(self.positions), "entries_today": self.entries_today,
               "session_close_min": self._close_min, "mode": "shadow",
               # schema 2 (2026-07-10): data-plane liveness for alert_watch's zombie check
               "client_present": self.client is not None,
               "last_tick_epoch": round(self._last_tick_epoch, 3),
               "last_bar_epoch": round(self._last_bar_epoch, 3),
               "last_mark_epoch": round(self._last_mark_epoch, 3)}
        p = Path(self.heartbeat_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
        atomic_replace(tmp, p)

    def tick(self) -> dict:
        now = float(self.clock_fn())
        self._roll_day(now)
        watch = self._watch_symbols()
        self._backfill(watch, now)
        dt = _et_dt(now)
        ticks = {}
        minute_now = dt.hour * 60 + dt.minute
        if minute_now < self._close_min:
            # the tick gate IS the after-hours freeze: _last_ticks/_last_ctx stop updating at
            # the close (S freezes at the last in-session print with zero new state) and the
            # bar builder never forms post-close synthetic bars
            ticks = self.feed.poll(watch)
            if ticks:
                self._last_tick_epoch = now
            for sym, tk in ticks.items():
                self._last_ticks[sym] = tk
                # RTH gate (audit RUNNER-1/TIMESCALE-STACK-4): premarket ticks must never
                # commit bars - they contaminated session VWAP/HOD and the mu window with
                # prevclose-echo prints that both entry admission and the kill switch consume
                if minute_now >= olanes.OPEN_MIN:
                    for bar in self.builder.on_tick(tk):
                        self._on_completed_bar(sym, bar, now)
            self._rvol_baseline_retry(now)
        self._reval_positions(now)
        self._mark_post_exit(now)
        self._write_heartbeat(now)
        return {"ts": now, "symbols": len(watch), "quotes": len(ticks),
                "open": len(self.positions), "entries_today": self.entries_today}


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(
        description="ATLAS options shadow trader (journal-only; NO order path exists)")
    ap.add_argument("--once", action="store_true", help="run a single tick then exit")
    ap.add_argument("--interval", type=float, default=None,
                    help="seconds between ticks (default: options_shadow.poll_seconds)")
    args = ap.parse_args()

    log = make_log()
    if not acquire_lock(log):
        return 6
    try:
        cfg = load_shadow_config()
        client = build_tradier_client(log)
        feed = HunterFeed(client, clock_fn=time.time,
                          cap_per_min=int(cfg["tradier_self_cap_per_min"]))
        core = OptionsShadowCore(client=client, feed=feed,
                                 ledger=oshadow.ShadowLedger(RUNTIME),
                                 clock_fn=time.time, cfg=cfg, log=log)
        interval = args.interval if args.interval is not None else float(cfg["poll_seconds"])
        interval = max(1.0, interval)
        dt = datetime.now(NY)
        try:
            close_min_today = scal.session_close_minute(dt.date())
        except Exception:  # noqa: BLE001 - banner only
            close_min_today = 16 * 60
        in_session = (dt.weekday() < 5
                      and (9 * 60 + 30) <= (dt.hour * 60 + dt.minute) < close_min_today)
        log(f"options-shadow UP - mode=shadow interval={interval}s cfg_hash={core.cfg_hash} "
            f"tradier={'yes' if client else 'NO (degraded)'} "
            f"{'in-session' if in_session else 'market closed (heartbeat-only until open)'}")
        fails = 0
        try:
            while True:
                try:
                    summary = core.tick()
                    fails = 0
                    if summary.get("open") or summary.get("entries_today"):
                        log(f"tick: {summary}")
                except Exception as exc:  # noqa: BLE001 - one bad tick never kills the process
                    fails += 1
                    log(f"tick error ({fails}): {exc!r}")
                if args.once:
                    if not in_session:
                        log("--once complete: market closed / no signals expected - clean exit")
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            log("KeyboardInterrupt - clean exit")
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass
        return 0
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
