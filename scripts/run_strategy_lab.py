"""STRATEGY LAB runner - 20 published strategies, shadow-only, ONE process beside the main
options shadow (registration lab-strategy-runtime-v1; mission 20260719-strategy-lab).

    PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\run_strategy_lab.py [--once] [--interval 10]

Separation from the main shadow (cohort a5ce85415e5a) is total: own pid lock
(runtime/strategy_lab.lock), own heartbeat (runtime/strategy_lab_heartbeat.json), own ledger
tree (runtime/strategy_lab/), own Tradier budget slice (LAB_CAP_PER_MIN=40 of the SHARED
single production token - M0 finding E3: both config files carry the SAME token; the main
self-caps 60/min, 60+40 leaves headroom under the documented ~120/min). Nothing in this
script or its import closure can place an order.

Fault containment: every strategy call is exception-wrapped; QUARANTINE_ERRORS_PER_DAY
exceptions from one strategy disarms it for the day (its positions still get the global
rails: expiry backstop + marks). One strategy's bug costs that strategy's day, nothing else.

Stop: runtime/STOP_DAY.flag (whole platform) or runtime/STOP_LAB.flag (lab only).
Side effects live under main() - tests/test_keep_imports.py spec-loads this file top-level.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.collect.symbol_state import state_reasons  # noqa: E402
from atlas.config_loader import FRAMEWORK_ROOT  # noqa: E402
from atlas.fsutil import atomic_replace  # noqa: E402
from atlas.options.events import in_blackout, upcoming_events  # noqa: E402
from atlas.options.session_calendar import (is_trading_day, options_close_minute,  # noqa: E402
                                            session_close_minute)
from atlas.strategy_lab.carisk import grading_block  # noqa: E402
from atlas.strategy_lab.hub import MarketHub  # noqa: E402
from atlas.strategy_lab.ledger import LabLedger, LedgerUnreadable  # noqa: E402
from atlas.strategy_lab.model import (LegSpec, build_combo_entry_record,  # noqa: E402
                                      build_combo_exit_record, build_combo_mark_record,
                                      combo_from_entry, combo_net_open, leg_open_fills)
from atlas.strategy_lab.registry import armed_roster, build_all, load_state, validate  # noqa: E402
from atlas.strategy_lab.settlement import expired_legs, pin_risk_flags, settlement_fills  # noqa: E402
from atlas.strategy_lab.strategy import EventPolicy, StrategyContext, expiry_backstop_due  # noqa: E402

NY = ZoneInfo("America/New_York")

# MODULE constants (not config-hashed; per-strategy cohorts live in each strategy's params).
LAB_CAP_PER_MIN = 40                 # PERMANENT shared-token slice - see module docstring
QUARANTINE_ERRORS_PER_DAY = 5
HEARTBEAT_SCHEMA = 2


def _paths(runtime_dir: Path) -> dict:
    return {"runtime": runtime_dir,
            "lock": runtime_dir / "strategy_lab.lock",
            "heartbeat": runtime_dir / "strategy_lab_heartbeat.json",
            "log": runtime_dir / "strategy_lab_run.log",
            "stop_day": runtime_dir / "STOP_DAY.flag",
            "stop_lab": runtime_dir / "STOP_LAB.flag"}


def _stamp() -> str:
    return datetime.now(NY).strftime("%Y-%m-%d %H:%M:%S %Z")


def make_log(log_file: Path):
    log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"[{_stamp()}] {msg}"
        print(line, flush=True)
        try:
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
    return log


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


def acquire_lock(lock_path: Path, log) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        rec = json.loads(lock_path.read_text(encoding="utf-8"))
        old_pid = int(rec.get("pid", 0))
    except (OSError, ValueError):
        old_pid = 0
    if old_pid and old_pid != os.getpid() and _pid_alive(old_pid):
        log(f"another strategy-lab (pid {old_pid}) holds {lock_path} - exiting")
        return False
    lock_path.write_text(json.dumps({"pid": os.getpid(), "ts": time.time()}), encoding="utf-8")
    return True


def release_lock(lock_path: Path) -> None:
    try:
        rec = json.loads(lock_path.read_text(encoding="utf-8"))
        if int(rec.get("pid", 0)) == os.getpid():
            lock_path.unlink()
    except (OSError, ValueError):
        pass


class StrategyLabCore:
    """The lab's tick loop: fail-closed rebuild -> settlement -> P0 quote poll + capture ->
    per-strategy manage/scan (exception-quarantined) -> heartbeat. `hub` and `now_fn` are
    injectable for offline tests; nothing here can place an order."""

    def __init__(self, *, runtime_dir: Path, log, hub: MarketHub | None = None, now_fn=None):
        self.paths = _paths(runtime_dir)
        self.log = log
        self.ledger = LabLedger(runtime_dir)
        self.hub = hub
        self.now_fn = now_fn or (lambda: datetime.now(NY))
        self.strategies = build_all()
        self.state = load_state()
        problems = validate(self.strategies, self.state)
        for p in problems:
            log(f"REGISTRY-PROBLEM {p}")
            self.ledger.journal({"event": "registry_problem", "ts_epoch": time.time(), "detail": p})
        self.armed = armed_roster(self.strategies, self.state)
        self.quarantined: dict[str, int] = {}
        self.positions: dict[str, list] = {}
        self._day = ""
        self._scan_ts: dict[str, float] = {}
        self._mark_ts: dict[str, float] = {}
        self._seq_today: dict[str, int] = {}
        self.log(f"lab core up: {len(self.strategies)} registered, "
                 f"{len(self.armed)} armed {self.armed}, cap {LAB_CAP_PER_MIN}/min")

    # -- day roll + settlement --------------------------------------------
    def _roll_day(self, day: str) -> None:
        try:
            self.positions = self.ledger.open_positions_all(
                sorted(set(self.armed) | set(self.ledger.known_strategy_dirs())))
        except LedgerUnreadable as exc:
            self.log(f"DAY-ROLL ABORTED (fail-closed): {exc}")
            self.ledger.journal({"event": "day_roll_aborted", "ts_epoch": time.time(),
                                 "detail": str(exc)})
            return
        self._settle_expired(day)
        self._day = day
        self.quarantined = {}
        self._seq_today = {}
        n_open = sum(len(v) for v in self.positions.values())
        self.ledger.journal({"event": "day_roll", "ts_epoch": time.time(), "day": day,
                             "open_combos": n_open, "armed": self.armed})
        self.log(f"day-roll {day}: {n_open} open combos across "
                 f"{sum(1 for v in self.positions.values() if v)} strategies")

    def _expiry_close_S(self, underlying: str, expiry_iso: str) -> float:
        if self.hub is None:
            return 0.0
        for bar in self.hub.daily_history(underlying, days=10):
            if str(bar.ts)[:10] == expiry_iso:
                return float(bar.close)
        return 0.0

    def _settle_expired(self, day: str) -> None:
        """Expiry is a first-class lifecycle event: combos whose nearest leg expired settle at
        intrinsic vs the expiry-day close (all three ledgers equal by construction)."""
        today = date.fromisoformat(day)
        for sid, poss in self.positions.items():
            for pos in list(poss):
                exp_legs = expired_legs(pos, today - timedelta(days=1))
                if not exp_legs:
                    continue
                exp = max(ls.spec.expiry for ls in exp_legs)
                S = self._expiry_close_S(pos.underlying, exp.isoformat())
                if S <= 0:
                    self.ledger.strategy(sid).journal(
                        {"event": "settlement_deferred", "ts_epoch": time.time(),
                         "position_id": pos.position_id, "detail": "no expiry close price yet"})
                    continue
                fills = settlement_fills(pos, S)
                rec = build_combo_exit_record(
                    ts=time.time(), day=day, pos=pos, rule="expiry_settlement",
                    legs_close=[{"occ": ls.spec.occ, "bid": 0.0, "ask": 0.0} for ls in pos.legs],
                    S=S, state={"settle_S": S, "expiry": exp.isoformat(),
                                "pin_risk": pin_risk_flags(pos, S, exp)},
                    hold_trading_days=self._hold_days(pos), fills_override=fills)
                self.ledger.strategy(sid).write_exit(rec)
                poss.remove(pos)
                self.log(f"settled {pos.position_id} at S={S} intrinsic")

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _hold_days(pos) -> float:
        return max(0.0, (time.time() - pos.entry_ts) / 86400.0) * (252.0 / 365.0)

    def _halted(self, symbol: str) -> list:
        try:
            snap = json.loads((self.paths["runtime"] / "symbol_state.json")
                              .read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return state_reasons(symbol, snap, time.time())

    def _wrap(self, sid: str, what: str, fn):
        """Per-strategy exception containment + quarantine (one bug costs one strategy's day)."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - containment is the point
            self.quarantined[sid] = self.quarantined.get(sid, 0) + 1
            self.ledger.strategy(sid).journal(
                {"event": "strategy_error", "ts_epoch": time.time(), "where": what,
                 "detail": f"{type(exc).__name__}: {exc}", "count": self.quarantined[sid]})
            if self.quarantined[sid] == QUARANTINE_ERRORS_PER_DAY:
                self.ledger.journal({"event": "strategy_quarantined", "ts_epoch": time.time(),
                                     "strategy_id": sid, "day": self._day})
                self.log(f"QUARANTINED {sid} for the day ({QUARANTINE_ERRORS_PER_DAY} errors)")
            return None

    def _S_of(self, quotes, underlying: str) -> float:
        q = quotes.get(underlying)
        if q is None:
            return 0.0
        last = float(getattr(q, "last", 0.0) or 0.0)
        if last > 0:
            return last
        bid, ask = float(q.bid or 0.0), float(q.ask or 0.0)
        return (bid + ask) / 2.0 if (bid > 0 and ask > 0) else 0.0

    # -- entries -----------------------------------------------------------
    def _enter(self, sid: str, strat, proposal, ctx, S: float) -> None:
        reasons = self._halted(proposal.underlying)
        if "halted" in reasons or "sec_suspended" in reasons:
            self.ledger.strategy(sid).journal(
                {"event": "entry_vetoed", "ts_epoch": time.time(),
                 "underlying": proposal.underlying, "reasons": reasons})
            return
        legs = []
        for l in proposal.legs:
            fills = leg_open_fills(int(l["side"]), float(l["nbbo"]["bid"]),
                                   float(l["nbbo"]["ask"]))
            legs.append({**l, "fills": fills})
        pairs, mids = [], []
        for l in legs:
            spec = LegSpec(occ=l["occ"], underlying=l["underlying"], opt_type=l["opt_type"],
                           strike=float(l["strike"]),
                           expiry=date.fromisoformat(str(l["expiry"])),
                           side=int(l["side"]), qty=int(l.get("qty", 1)))
            pairs.append((spec, l["fills"]))
            mids.append((spec, (float(l["nbbo"]["bid"]) + float(l["nbbo"]["ask"])) / 2.0))
        net = combo_net_open(pairs)
        grading = grading_block(legs_with_mid=mids, net_open_worst=net["worst"], S=S,
                                declared_basis=strat.META.grading_basis.value,
                                contracts=proposal.contracts)
        seq = self._seq_today.get(sid, 0)
        self._seq_today[sid] = seq + 1
        minute = ctx.minute
        pid = strat.next_position_id(proposal.underlying, self._day, minute, seq)
        greeks_net = {
            "delta_shares": round(sum(l["side"] * l.get("qty", 1) * float(l.get("delta") or 0.0)
                                      for l in legs) * 100.0 * proposal.contracts, 2),
            "vega": round(sum(l["side"] * l.get("qty", 1) * float(l.get("vega") or 0.0)
                              for l in legs) * 100.0 * proposal.contracts, 2),
            "theta_day": round(sum(l["side"] * l.get("qty", 1) * float(l.get("theta_day") or 0.0)
                                   for l in legs) * 100.0 * proposal.contracts, 2)}
        risk_flags = list(proposal.risk_flags)
        if grading["basis_mismatch"]:
            risk_flags.append("basis_mismatch")
        rec = build_combo_entry_record(
            ts=time.time(), day=self._day, entry_minute=minute, position_id=pid,
            strategy_id=sid, strategy_config_hash=strat.config_hash(), kind=proposal.kind,
            legs=legs, S=S, grading=grading, signal=proposal.signal, greeks_net=greeks_net,
            risk_flags=risk_flags, contracts=proposal.contracts)
        self.ledger.strategy(sid).write_entry(rec)
        pos = combo_from_entry(rec)
        if pos is not None:
            self.positions.setdefault(sid, []).append(pos)
            self.log(f"ENTER {pid} {proposal.kind} denom=${grading['denom_usd']:.0f} "
                     f"basis={grading['basis']}")

    # -- marks / manage ----------------------------------------------------
    def _leg_book(self, pos) -> list | None:
        book = []
        for ls in pos.legs:
            nb = self.hub.last_nbbo(ls.spec.occ) if self.hub else None
            if nb is None:
                return None
            book.append({"occ": ls.spec.occ, "bid": nb[0], "ask": nb[1], "age_s": nb[2]})
        return book

    def _close_position(self, sid: str, pos, rule: str, book: list, S: float,
                        state: dict) -> None:
        today = date.fromisoformat(self._day)
        legs_close = []
        for row in book:
            spec = next(ls.spec for ls in pos.legs if ls.spec.occ == row["occ"])
            mid = (row["bid"] + row["ask"]) / 2.0
            g = None
            if S > 0 and mid > 0:
                g = MarketHub.row_greeks(opt_type=spec.opt_type, strike=spec.strike, S=S,
                                         mid=mid, dte_days=max(0.5, (spec.expiry - today).days))
            legs_close.append({**row, "iv": (g or {}).get("iv", 0.0)})
        rec = build_combo_exit_record(ts=time.time(), day=self._day, pos=pos, rule=rule,
                                      legs_close=legs_close, S=S, state=state,
                                      hold_trading_days=self._hold_days(pos))
        self.ledger.strategy(sid).write_exit(rec)
        self.positions[sid].remove(pos)
        net = rec["ledgers"]["worst"]["net_pnl_usd"]
        self.log(f"EXIT {pos.position_id} rule={rule} worst=${net:.0f}")

    def _manage_positions(self, sid: str, strat, ctx, quotes) -> None:
        today = date.fromisoformat(self._day)
        for pos in list(self.positions.get(sid, [])):
            S = self._S_of(quotes, pos.underlying)
            if S > 0:
                pos.observe_underlying(S)
            book = self._leg_book(pos)
            if book is None:
                self.ledger.strategy(sid).journal(
                    {"event": "combo_mark_partial", "ts_epoch": time.time(),
                     "position_id": pos.position_id})
                continue
            self.ledger.strategy(sid).write_mark(build_combo_mark_record(
                ts=time.time(), position_id=pos.position_id, strategy_id=sid,
                legs_nbbo=book, S=S, state=dict(pos.carried), action="hold", rule=""))
            if (not strat.META.settle_at_expiry
                    and expiry_backstop_due(pos, today=today, minute=ctx.minute,
                                            session_close_min=ctx.session_close_min)):
                self._close_position(sid, pos, "expiry_backstop", book, S,
                                     {"rail": "global", "minute": ctx.minute})
                continue
            action = self._wrap(sid, "manage", lambda: strat.manage(pos, ctx))
            if action is not None and action.action == "close":
                self._close_position(sid, pos, action.rule, book, S, dict(action.state))
            pos.last_mark_ts = time.time()

    # -- main tick ---------------------------------------------------------
    def stop_requested(self) -> str:
        if self.paths["stop_day"].exists():
            return "STOP_DAY.flag"
        if self.paths["stop_lab"].exists():
            return "STOP_LAB.flag"
        return ""

    def write_heartbeat(self) -> None:
        rec = {"schema": HEARTBEAT_SCHEMA, "pid": os.getpid(), "ts_epoch": round(time.time(), 3),
               "day": self._day, "strategies_registered": sorted(self.strategies),
               "strategies_armed": self.armed,
               "quarantined": sorted(k for k, v in self.quarantined.items()
                                     if v >= QUARANTINE_ERRORS_PER_DAY),
               "open_combos": {k: len(v) for k, v in self.positions.items() if v},
               "cap_per_min": LAB_CAP_PER_MIN,
               "hub_used_per_min": self.hub.governor.used() if self.hub else None}
        try:
            tmp = self.paths["heartbeat"].with_suffix(".json.tmp")
            tmp.write_text(json.dumps(rec, separators=(",", ":")) + "\n", encoding="utf-8")
            atomic_replace(tmp, self.paths["heartbeat"])
        except OSError as exc:
            self.log(f"heartbeat write failed: {exc}")

    def tick(self) -> None:
        now_dt = self.now_fn()
        day = now_dt.date().isoformat()
        if day != self._day:
            self._roll_day(day)
        if self._day != day:                       # roll aborted fail-closed: heartbeat only
            self.write_heartbeat()
            return
        today = now_dt.date()
        minute = now_dt.hour * 60 + now_dt.minute
        if not is_trading_day(today) or self.hub is None:
            self.write_heartbeat()
            return
        close_min = session_close_minute(today)
        if minute < 570 or minute > close_min + 20:
            self.write_heartbeat()
            return

        underlyings = sorted({u for sid in self.armed
                              for u in self.strategies[sid].META.universe}
                             | {p.underlying for v in self.positions.values() for p in v})
        leg_occs = sorted({ls.spec.occ for v in self.positions.values()
                           for p in v for ls in p.legs})
        quotes = self.hub.poll_quotes(underlyings, leg_occs)
        for occ in leg_occs:                       # quote-capture rows (replay corpus)
            nb = self.hub.last_nbbo(occ)
            if nb is not None:
                self.ledger.write_quote(self._day, {"event": "lab_quote",
                                                    "ts_epoch": round(time.time(), 3),
                                                    "occ": occ, "bid": nb[0], "ask": nb[1]})
        events = upcoming_events(now_dt)
        blackout = in_blackout(now_dt, events=events) or ""
        now_mono = time.time()
        for sid in self.armed:
            if self.quarantined.get(sid, 0) >= QUARANTINE_ERRORS_PER_DAY:
                continue
            strat = self.strategies[sid]
            ctx = StrategyContext(now_ts=now_mono, dt_et=now_dt, day=self._day, minute=minute,
                                  session_close_min=options_close_minute(
                                      today, next(iter(strat.META.universe), "SPY")),
                                  hub=self.hub, events=events, in_blackout=blackout,
                                  earnings=self.hub.earnings_week(),
                                  journal=self.ledger.strategy(sid).journal,
                                  open_positions=list(self.positions.get(sid, [])))
            if now_mono - self._mark_ts.get(sid, 0.0) >= strat.META.mark_interval_s:
                self._mark_ts[sid] = now_mono
                self._manage_positions(sid, strat, ctx, quotes)
            room = strat.META.max_concurrent - len(self.positions.get(sid, []))
            if room <= 0 or now_mono - self._scan_ts.get(sid, 0.0) < strat.META.scan_interval_s:
                continue
            self._scan_ts[sid] = now_mono
            if strat.META.event_policy is EventPolicy.BLACKOUT and blackout:
                self.ledger.strategy(sid).journal({"event": "scan_blackout_skip",
                                                   "ts_epoch": now_mono, "reason": blackout})
                continue
            proposals = self._wrap(sid, "scan", lambda: strat.scan(ctx)) or []
            for proposal in proposals[:room]:
                S = self._S_of(quotes, proposal.underlying)
                if S <= 0:
                    self.ledger.strategy(sid).journal(
                        {"event": "entry_no_underlying_quote", "ts_epoch": now_mono,
                         "underlying": proposal.underlying})
                    continue
                self._wrap(sid, "enter", lambda p=proposal, s=S: self._enter(sid, strat, p, ctx, s))
        self.write_heartbeat()


def build_hub(runtime_dir: Path, log) -> MarketHub | None:
    """Real hub on the SHARED production token (config/tradier.local.yaml - the second FILE,
    same token; M0 E3). Tolerant of BOM + top-level-or-nested token; None = degraded lab
    (heartbeat-only), never a crash."""
    import yaml
    from atlas.collect.tradier_data import PRODUCTION_BASE, TradierData
    p = FRAMEWORK_ROOT / "config" / "tradier.local.yaml"
    try:
        cfg = yaml.safe_load(p.read_text(encoding="utf-8-sig")) or {}
        if isinstance(cfg.get("tradier"), dict):
            cfg = {**cfg, **cfg["tradier"]}
        token = str(cfg.get("token") or "").strip()
        if not token:
            log("no tradier token - lab runs heartbeat-only (degraded)")
            return None
        client = TradierData(token, base_url=PRODUCTION_BASE, max_per_minute=LAB_CAP_PER_MIN)
        return MarketHub(client, runtime_dir, cap_per_min=LAB_CAP_PER_MIN)
    except Exception as exc:  # noqa: BLE001 - feed fail-open
        log(f"hub build failed ({type(exc).__name__}: {exc}) - heartbeat-only")
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ATLAS strategy lab (shadow-only)")
    ap.add_argument("--once", action="store_true", help="single tick then exit")
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--runtime-dir", default=str(FRAMEWORK_ROOT / "runtime"),
                    help="override for tests only")
    ap.add_argument("--no-hub", action="store_true",
                    help="heartbeat-only mode (tests; no network)")
    args = ap.parse_args(argv)

    runtime_dir = Path(args.runtime_dir)
    paths = _paths(runtime_dir)
    log = make_log(paths["log"])
    if not acquire_lock(paths["lock"], log):
        return 6
    try:
        hub = None if args.no_hub else build_hub(runtime_dir, log)
        core = StrategyLabCore(runtime_dir=runtime_dir, log=log, hub=hub)
        while True:
            stop = core.stop_requested()
            if stop:
                log(f"stop flag {stop} - exiting cleanly")
                return 0
            core.tick()
            if args.once:
                return 0
            time.sleep(max(1.0, float(args.interval)))
    except KeyboardInterrupt:
        log("Ctrl-C - clean exit")
        return 0
    finally:
        release_lock(paths["lock"])


if __name__ == "__main__":
    raise SystemExit(main())
