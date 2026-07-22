"""SHADOW LEDGERS (O3) - the OPTIONS SHADOW TRADER's only output: fsync'd append-only JSONL
records (the early_wave/hunter single-writer idiom). NOTHING in this module (or any module it
imports) can place an order - the shadow's entire side-effect surface is these files:

    runtime/options_shadow_entries.jsonl   one record per hypothetical entry
    runtime/options_shadow_marks.jsonl     one record per reval cycle per open position
    runtime/options_shadow_exits.jsonl     one record per hypothetical exit
    runtime/options_shadow_quotes/YYYY-MM-DD.jsonl
                                           every reval-cycle NBBO (the paired-replay quote paths)

THREE FILL LEDGERS per trade (plan "Shadow mechanics"): the WORST ledger grades (buy at ask,
sell at bid), BASE models price improvement (mid +/- 0.35 x half-spread), OPTIMISTIC is the
mid-fill bound. Identities enforced by construction and unit-tested:
    entry:  optimistic <= base <= worst      (you never buy below mid, never above ask)
    exit:   worst <= base <= optimistic      (you never sell above mid, never below bid)
    =>      net P&L: worst <= base <= optimistic

Record builders are PURE functions (dict in/dict out, no clock, no IO) so the ledger schema is
testable without a process; ShadowLedger is the thin single-writer IO wrapper around them.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

SCHEMA = 1
BASE_FILL_FRAC = 0.35        # base ledger: mid + 0.35 x (ask - mid) buy / mid - 0.35 x (mid - bid) sell


# --------------------------------------------------------------------------- fill math (pure)
def entry_fills(bid: float, ask: float) -> dict:
    """Buy-side fills. worst=ask, base=mid+0.35*(ask-mid), optimistic=mid."""
    bid, ask = max(0.0, float(bid)), max(0.0, float(ask))
    if ask < bid:
        ask = bid
    mid = (bid + ask) / 2.0
    return {"worst": round(ask, 4),
            "base": round(mid + BASE_FILL_FRAC * (ask - mid), 4),
            "optimistic": round(mid, 4)}


def exit_fills(bid: float, ask: float) -> dict:
    """Sell-side fills. worst=bid, base=mid-0.35*(mid-bid), optimistic=mid."""
    bid, ask = max(0.0, float(bid)), max(0.0, float(ask))
    if ask < bid:
        ask = bid
    mid = (bid + ask) / 2.0
    return {"worst": round(bid, 4),
            "base": round(mid - BASE_FILL_FRAC * (mid - bid), 4),
            "optimistic": round(mid, 4)}


# --------------------------------------------------------------------------- open position
@dataclass
class ShadowPosition:
    """In-memory state of one open shadow position (rebuildable from the entry ledger)."""
    position_id: str
    occ: str
    underlying: str
    opt_type: str                 # "call" | "put"
    strike: float
    expiry: date
    lanes: list                   # lane tags (merged fires append here)
    direction: str                # == opt_type (kept for symmetry with LaneSignal)
    target_underlying: float
    mu_thesis: float
    p_thesis: float
    horizon_T: float
    entry_ts: float
    entry_minute: int
    entry_day: str
    entry_S: float
    entry_bid: float
    entry_ask: float
    entry_mid: float
    entry_fills: dict
    entry_theta_day: float = 0.0
    contracts: int = 1
    peak_mid: float = 0.0
    peak_bid: float = 0.0         # best realizable sell since entry (d2* cost-basis backstop - 
    #                               opts-rule-d2-costbasis-v1; the v1 trail latch is REMOVED)
    theta_share_breaches: int = 0
    # audit 2026-07-16 Wave 2.14/2.13 carried state (defaults keep old-entry rebuilds valid):
    h_breach_since_min: int | None = None   # rule (h) continuous-breach clock (engine-carried)
    i_breach_since_min: int | None = None   # rule (i*) continuous-breach clock
    thesis_invalid_streak: int = 0          # rule (b) needs 2 consecutive committed-close evals
    last_mark_ts: float = 0.0
    fav_max: float = 0.0          # max favorable underlying move (fraction, signed by direction)
    fav_min: float = 0.0          # max adverse underlying move (fraction, <= 0)
    print_minute: int | None = None   # lane 3: the release's market-reference minute
    notes: dict = field(default_factory=dict)

    def observe_underlying(self, S: float) -> None:
        if S <= 0 or self.entry_S <= 0:
            return
        sgn = 1.0 if self.opt_type == "call" else -1.0
        f = (S / self.entry_S - 1.0) * sgn
        self.fav_max = max(self.fav_max, f)
        self.fav_min = min(self.fav_min, f)


# --------------------------------------------------------------------------- record builders (pure)
def build_entry_record(*, ts: float, day: str, entry_minute: int, position_id: str, lanes: list,
                       config_hash: str, signal: dict, pick: dict, runner_up_occs: list,
                       nbbo: dict, risk_flags: list, iv_rank=None, hv20=None, vix=None,
                       merged_into: str | None = None, covariates: dict | None = None,
                       runner_up_snapshot: list | None = None) -> dict:
    """One hypothetical entry. `signal` = asdict(LaneSignal); `pick` = the chosen ScoredPick as a
    dict (occ + greeks + EV decomposition + flags); `nbbo` = {bid, ask} at decision time.
    `covariates` = day-1 regime context (graded at N, never a gate); `runner_up_snapshot` =
    quotes of the beaten candidates (the counterfactual-selector lab's input)."""
    fills = entry_fills(nbbo.get("bid", 0.0), nbbo.get("ask", 0.0))
    return {"schema": SCHEMA, "event": "shadow_entry", "ts_epoch": round(float(ts), 3),
            "day": day, "entry_minute": int(entry_minute),
            "position_id": position_id, "lanes": list(lanes),
            "config_hash": config_hash, "signal": dict(signal), "pick": dict(pick),
            "runner_up_occs": list(runner_up_occs),
            "nbbo": {"bid": round(float(nbbo.get("bid", 0.0)), 4),
                     "ask": round(float(nbbo.get("ask", 0.0)), 4)},
            "fills": fills, "contracts": 1,
            "risk_flags": sorted(set(str(f) for f in risk_flags)),
            "iv_rank": iv_rank, "hv20": hv20, "vix": vix,
            "covariates": dict(covariates) if covariates else None,
            "runner_up_snapshot": list(runner_up_snapshot) if runner_up_snapshot else None,
            "merged_into": merged_into}


def build_merge_record(*, ts: float, day: str, position_id: str, lane: str, signal: dict) -> dict:
    """A same-underlying same-direction multi-lane fire folded into an existing position: the
    position carries both lane tags (both graded); no second entry is booked."""
    return {"schema": SCHEMA, "event": "shadow_merge", "ts_epoch": round(float(ts), 3),
            "day": day, "position_id": position_id, "lane": lane, "signal": dict(signal)}


def build_mark_record(*, ts: float, position_id: str, occ: str, bid: float, ask: float,
                      solved_iv: float, S: float, decision_state: dict, action: str,
                      rule: str) -> dict:
    bid, ask = max(0.0, float(bid)), max(0.0, float(ask))
    mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else max(bid, 0.0)
    return {"schema": SCHEMA, "event": "shadow_mark", "ts_epoch": round(float(ts), 3),
            "position_id": position_id, "occ": occ,
            "bid": round(bid, 4), "ask": round(ask, 4), "mid": round(mid, 4),
            "solved_iv": round(float(solved_iv), 4), "S": round(float(S), 4),
            "state": dict(decision_state), "action": action, "rule": rule}


def build_quote_record(*, ts: float, occ: str, bid: float, ask: float, S: float,
                       position_id: str = "", ext: dict | None = None) -> dict:
    """The paired-replay quote path row - every reval cycle's NBBO, one file per day.
    `ext` (schema 2, opts-rework-exit-core-v1) carries the full engine-input snapshot
    (solved_iv, iv_trend, mu_hat/t_stat, thesis_valid, print/planned context, after_hours…)
    so a decide_exit-based replay can rebuild PositionView per stored step. Readers are
    tolerant: rows without ext replay premium-threshold variants only."""
    rec = {"schema": 2 if ext is not None else SCHEMA, "event": "shadow_quote",
           "ts_epoch": round(float(ts), 3),
           "occ": occ, "bid": round(max(0.0, float(bid)), 4),
           "ask": round(max(0.0, float(ask)), 4), "S": round(float(S), 4),
           "position_id": position_id}
    if ext is not None:
        rec["ext"] = dict(ext)
    return rec


def build_exit_record(*, ts: float, day: str, pos: ShadowPosition, rule: str,
                      bid: float, ask: float, solved_iv: float, S: float,
                      decision_state: dict, variant_would_hold: bool,
                      hold_trading_days: float) -> dict:
    """One hypothetical exit: three exit fills, per-ledger gross+net P&L, theta/spread
    decomposition, MFE/MAE of the underlying during the hold, and the rule that fired."""
    xf = exit_fills(bid, ask)
    exit_mid = xf["optimistic"]
    entry_mid = pos.entry_fills["optimistic"]
    mult = 100.0 * pos.contracts
    gross = (exit_mid - entry_mid) * mult                      # mid-to-mid, ledger-independent
    ledgers = {}
    for name in ("worst", "base", "optimistic"):
        ef, xfl = pos.entry_fills[name], xf[name]
        ledgers[name] = {"entry_fill": ef, "exit_fill": xfl,
                         "gross_pnl_usd": round(gross, 2),
                         "net_pnl_usd": round((xfl - ef) * mult, 2)}
    spread_paid = ((pos.entry_fills["worst"] - entry_mid) + (exit_mid - xf["worst"])) * mult
    theta_paid = pos.entry_theta_day * max(0.0, hold_trading_days) * mult
    return {"schema": SCHEMA, "event": "shadow_exit", "ts_epoch": round(float(ts), 3),
            "day": day, "position_id": pos.position_id, "occ": pos.occ,
            "underlying": pos.underlying, "opt_type": pos.opt_type, "lanes": list(pos.lanes),
            "rule": rule, "variant_would_hold": bool(variant_would_hold),
            "nbbo": {"bid": round(max(0.0, float(bid)), 4),
                     "ask": round(max(0.0, float(ask)), 4)},
            "solved_iv": round(float(solved_iv), 4), "S": round(float(S), 4),
            "fills": xf, "ledgers": ledgers,
            "decomposition": {"theta_paid_usd": round(theta_paid, 2),
                              "spread_paid_usd": round(spread_paid, 2)},
            "underlying_mfe": round(pos.fav_max, 6), "underlying_mae": round(pos.fav_min, 6),
            "hold_trading_days": round(float(hold_trading_days), 6),
            "entry_ts_epoch": round(pos.entry_ts, 3),
            "state": dict(decision_state)}


def position_from_entry(rec: dict) -> ShadowPosition | None:
    """Rebuild an open position from its entry record (restart safety). None on a malformed row - 
    a corrupt line never crashes the process."""
    try:
        sig = rec.get("signal") or {}
        pick = rec.get("pick") or {}
        nbbo = rec.get("nbbo") or {}
        expiry = date.fromisoformat(str(pick["expiry"]))
        entry_ts = float(rec["ts_epoch"])
        entry_mid = (float(nbbo["bid"]) + float(nbbo["ask"])) / 2.0
        entry_minute = int(rec.get("entry_minute") or 0)
        S0 = float(pick.get("S", 0.0))
        direction = str(pick["opt_type"])
        tgt = abs(float(sig.get("target_move", 0.0)))
        target_under = S0 * (1.0 + tgt) if direction == "call" else S0 * (1.0 - tgt)
        return ShadowPosition(
            position_id=str(rec["position_id"]), occ=str(pick["occ"]),
            underlying=str(pick.get("underlying") or sig.get("underlying", "")).upper(),
            opt_type=direction, strike=float(pick["strike"]), expiry=expiry,
            lanes=list(rec.get("lanes") or []), direction=direction,
            target_underlying=target_under, mu_thesis=float(sig.get("mu_thesis", 0.0)),
            p_thesis=float(sig.get("p_thesis", 0.5)),
            horizon_T=float(sig.get("horizon_T", 0.0)), entry_ts=entry_ts,
            entry_minute=entry_minute, entry_day=str(rec.get("day", "")),
            entry_S=S0, entry_bid=float(nbbo.get("bid", 0.0)),
            entry_ask=float(nbbo.get("ask", 0.0)), entry_mid=entry_mid,
            entry_fills=dict(rec.get("fills") or entry_fills(nbbo.get("bid", 0), nbbo.get("ask", 0))),
            entry_theta_day=float(pick.get("theta_day", 0.0)),
            peak_mid=entry_mid,
            peak_bid=float(nbbo.get("bid", 0.0)),
            print_minute=(int(sig["notes"]["print_minute"])
                          if isinstance(sig.get("notes"), dict) and "print_minute" in sig["notes"]
                          else None),
            notes=dict(sig.get("notes") or {}))
    except (KeyError, TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- IO (single writer)
class LedgerUnreadable(RuntimeError):
    """A ledger file EXISTS but could not be read (AV/backup lock, permission). Distinct from
    absent/empty: readers that fail open on this (returning []) resurrect exited positions and
    double-count exits - audit 2026-07-16 SHADOW-LEDGER-2 (4/4 refuters upheld)."""


def append_jsonl(path, rec: dict) -> None:
    """Append-only fsync'd JSONL - the Guardian/early_wave/hunter ledger idiom.
    Torn-tail guard (audit 2026-07-16 SHADOW-LEDGER-2): a crash between write() and fsync can
    leave a partial final line; appending straight after it would corrupt TWO rows. If the last
    byte is not a newline, terminate the torn line first - the reader already quarantines the
    torn fragment as a JSONDecodeError line."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    try:
        if p.exists() and p.stat().st_size > 0:
            with open(p, "rb") as rf:
                rf.seek(-1, os.SEEK_END)
                if rf.read(1) != b"\n":
                    prefix = "\n"
    except OSError:
        prefix = ""
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(prefix + json.dumps(rec, separators=(",", ":"), default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def read_jsonl(path, *, strict: bool = False) -> list:
    """Tolerant JSONL read: absent file -> []. `strict=True` raises LedgerUnreadable when the
    file EXISTS but cannot be read (fail-CLOSED for rebuild paths; the old silent [] is the
    mass-resurrection bug of SHADOW-LEDGER-2)."""
    p = Path(path)
    if not p.exists():
        return []
    out = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        if strict:
            raise LedgerUnreadable(f"{p}: {exc!r}") from exc
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


class ShadowLedger:
    """Thin single-writer wrapper. `root` = the runtime dir; every write is one fsync'd append."""

    def __init__(self, root: Path | str):
        root = Path(root)
        self.entries_path = root / "options_shadow_entries.jsonl"
        self.marks_path = root / "options_shadow_marks.jsonl"
        self.exits_path = root / "options_shadow_exits.jsonl"
        self.quotes_dir = root / "options_shadow_quotes"
        self.journal_path = root / "options_shadow_journal.jsonl"

    def write_entry(self, rec: dict) -> None:
        append_jsonl(self.entries_path, rec)

    def write_merge(self, rec: dict) -> None:
        append_jsonl(self.entries_path, rec)     # merges live with entries (same grading stream)

    def write_mark(self, rec: dict) -> None:
        append_jsonl(self.marks_path, rec)

    def write_exit(self, rec: dict) -> None:
        append_jsonl(self.exits_path, rec)

    def write_quote(self, day: str, rec: dict) -> None:
        append_jsonl(self.quotes_dir / f"{day}.jsonl", rec)

    def journal(self, rec: dict) -> None:
        rec.setdefault("schema", SCHEMA)
        append_jsonl(self.journal_path, rec)

    # ---- loaders for the grader (O4) -------------------------------------------------------
    def load_entries(self, day: str | None = None) -> list:
        rows = [r for r in read_jsonl(self.entries_path) if r.get("event") == "shadow_entry"]
        return [r for r in rows if day is None or r.get("day") == day]

    def load_merges(self, day: str | None = None) -> list:
        rows = [r for r in read_jsonl(self.entries_path) if r.get("event") == "shadow_merge"]
        return [r for r in rows if day is None or r.get("day") == day]

    def load_marks(self, position_id: str | None = None) -> list:
        rows = read_jsonl(self.marks_path)
        return [r for r in rows if position_id is None or r.get("position_id") == position_id]

    def load_exits(self, day: str | None = None) -> list:
        rows = [r for r in read_jsonl(self.exits_path) if r.get("event") == "shadow_exit"]
        return [r for r in rows if day is None or r.get("day") == day]

    def open_positions_for_day(self, day: str) -> list:
        """Restart safety: today's entries without a matching exit -> rebuilt ShadowPositions
        (peak_mid/peak_bid/mfe/mae/breach-count re-primed from the stored marks)."""
        return self._open_positions(day)

    def open_positions_all(self) -> list:
        """ALL unexited entries regardless of day - the day-roll rebuild path. Without this an
        overnight hold (the DTE>=3 catalyst exception) would be orphaned at the next day roll:
        never marked, never exited, invisible to the 09:35 re-decision."""
        return self._open_positions(None)

    def _open_positions(self, day: str | None) -> list:
        # lazy import: the breach re-prime must count with the ENGINE's threshold, not a copy - 
        # a registered tweak to theta_share_max would otherwise desync restart memory
        from atlas.options.exit_engine import ExitParams
        theta_share_max = ExitParams().theta_share_max
        # FAIL-CLOSED (audit SHADOW-LEDGER-2): an unreadable exits file must ABORT the rebuild
        # (caller journals + retries), never read as "no exits" - that resurrected every
        # unexpired historical position and double-counted their re-exits.
        exited_rows = read_jsonl(self.exits_path, strict=True)
        exited = {r.get("position_id") for r in exited_rows if r.get("event") == "shadow_exit"}
        out = []
        for rec in self.load_entries(day):
            if rec.get("position_id") in exited or rec.get("merged_into"):
                continue
            pos = position_from_entry(rec)
            if pos is None:
                continue
            for m in self.load_merges(day=None):
                if m.get("position_id") == pos.position_id:
                    lane = str(m.get("lane") or "")
                    if lane and lane not in pos.lanes:
                        pos.lanes.append(lane)
            breaches = 0
            h_since: int | None = None
            i_since: int | None = None
            for mk in self.load_marks(pos.position_id):
                mid = float(mk.get("mid") or 0.0)
                pos.peak_mid = max(pos.peak_mid, mid)
                pos.peak_bid = max(pos.peak_bid, float(mk.get("bid") or 0.0))
                s = float(mk.get("S") or 0.0)
                if s > 0:
                    pos.observe_underlying(s)
                pos.last_mark_ts = max(pos.last_mark_ts, float(mk.get("ts_epoch") or 0.0))
                st = mk.get("state") if isinstance(mk.get("state"), dict) else {}
                # rule (g)'s two-consecutive-cycle memory must survive a restart - else every
                # respawn grants a theta-dominated position a grace cycle. (The v1 trail-latch
                # re-prime died with the trail: opts-rework-exit-core-v1.)
                breaches = (breaches + 1
                            if float(st.get("theta_share") or 0.0) > theta_share_max else 0)
                # Wave 2.14: the h/i* persistence clocks survive a restart the same way - 
                # a respawn must not hand a persistently-breaching position a fresh clock.
                h_since = st.get("h_breach_since_min") if "h_breach_since_min" in st else h_since
                i_since = st.get("i_breach_since_min") if "i_breach_since_min" in st else i_since
            pos.theta_share_breaches = breaches
            pos.h_breach_since_min = int(h_since) if isinstance(h_since, (int, float)) else None
            pos.i_breach_since_min = int(i_since) if isinstance(i_since, (int, float)) else None
            out.append(pos)
        return out
