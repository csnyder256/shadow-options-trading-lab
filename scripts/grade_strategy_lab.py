"""STRATEGY LAB grader - per-strategy falsification gates, e-process wealth (FOR + AGAINST),
mechanism attribution, funnel health, verdicts, cross-strategy exposure -> scorecard.json.

    PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\grade_strategy_lab.py [--day YYYY-MM-DD]
        [--strategy <sid>] [--validate] [--runtime-dir <dir>]

The MAIN grader (scripts/grade_options_shadow.py, cohort a5ce85415e5a) is untouched; the
shared math contract is pinned by a parity test (tests/strategy_lab/test_lab_grading.py:
lab wealth on a bounded-basis fixture reproduces eprocess_wealth bit-for-bit).

Falsification gates per strategy (ALL must be [] before that strategy is graded; a broken
strategy is verdict BROKEN and never blinds the other 20): malformed_exits, duplicate_exits
(dedupe by position_id, first-by-time), ledger_identity_violations (net worst <= base <=
optimistic), denominator_mismatches (recomputed vs frozen, tol 1%), pid_collisions
(lab-wide), foreign_strategy_rows, floor_breaches (CaR FOR-floor), unusable_returns.

--validate = Tier-1 truth validation for /eodreport Phase 3: per-trade re-derivation of
every fill from its recorded NBBO + identity + denominator + return_pct recompute, emitted
per trade so the skill can print it. Scripted, so 60 trades cost nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.config_loader import FRAMEWORK_ROOT  # noqa: E402
from atlas.fsutil import atomic_replace  # noqa: E402
from atlas.strategy_lab.carisk import grading_block  # noqa: E402
from atlas.strategy_lab.grading import (AGAINST_FLAG, AGAINST_PRUNE, N_VERDICT_MIN, R_CAP,  # noqa: E402
                                        WEALTH_LIVE, WEALTH_PILOT, attribute, lambdas_for,
                                        loss_shares, r_return, wealth_against, wealth_for)
from atlas.strategy_lab.ledger import LabLedger, read_jsonl  # noqa: E402
from atlas.strategy_lab.model import (LEDGER_NAMES, LegSpec, combo_net_open,  # noqa: E402
                                      leg_open_fills)
from atlas.strategy_lab.registry import build_all, load_state  # noqa: E402
from atlas.strategy_lab.verdicts import verdict_for  # noqa: E402

DENOM_TOL = 0.01               # 1% recompute tolerance before a denominator_mismatch fires
STARVED_FRac = 0.3


# ------------------------------------------------------------------ gates + stats per strategy
def _dedupe_exits(exits: list) -> tuple[list, list]:
    seen, out, dups = {}, [], []
    for rec in sorted(exits, key=lambda r: float(r.get("ts_epoch") or 0.0)):
        pid = rec.get("position_id")
        if pid in seen:
            dups.append(pid)
            continue
        seen[pid] = True
        out.append(rec)
    return out, dups


def _identity_violation(rec: dict) -> bool:
    try:
        nets = [float(rec["ledgers"][n]["net_pnl_usd"]) for n in LEDGER_NAMES]
        return not (nets[0] <= nets[1] + 1e-6 <= nets[2] + 2e-6)
    except (KeyError, TypeError, ValueError):
        return True


def _recompute_denom(entry: dict) -> float | None:
    try:
        legs, mids = [], []
        for l in entry["legs"]:
            spec = LegSpec(occ=l["occ"], underlying=l["underlying"], opt_type=l["opt_type"],
                           strike=float(l["strike"]),
                           expiry=__import__("datetime").date.fromisoformat(str(l["expiry"])),
                           side=int(l["side"]), qty=int(l.get("qty", 1)))
            legs.append((spec, (float(l["nbbo"]["bid"]) + float(l["nbbo"]["ask"])) / 2.0))
        net_worst = float(entry["net_fills"]["worst"])
        g = grading_block(legs_with_mid=legs, net_open_worst=net_worst,
                          S=float(entry["S"]),
                          declared_basis=str(entry["grading"].get("declared_basis") or ""),
                          contracts=int(entry.get("contracts") or 1))
        return float(g["denom_usd"])
    except (KeyError, TypeError, ValueError):
        return None


def grade_strategy(sid: str, ledger: LabLedger, meta, *, day: str | None,
                   lab_sessions_elapsed: int | None = None) -> dict:
    s = ledger.strategy(sid)
    entries = [r for r in read_jsonl(s.entries_path) if r.get("event") == "lab_entry"]
    exits_raw = [r for r in read_jsonl(s.exits_path) if r.get("event") == "lab_exit"]
    exits, dups = _dedupe_exits(exits_raw)
    entry_by_pid = {r.get("position_id"): r for r in entries}

    gates = {"malformed_exits": [], "duplicate_exits": dups, "ledger_identity_violations": [],
             "denominator_mismatches": [], "foreign_strategy_rows": [], "floor_breaches": [],
             "unusable_returns": []}
    for rec in exits:
        pid = rec.get("position_id")
        if rec.get("strategy_id") != sid:
            gates["foreign_strategy_rows"].append(pid)
            continue
        if not isinstance(rec.get("ledgers"), dict) or "grading" not in rec:
            gates["malformed_exits"].append(pid)
            continue
        if _identity_violation(rec):
            gates["ledger_identity_violations"].append(pid)
        ent = entry_by_pid.get(pid)
        if ent is not None:
            rd = _recompute_denom(ent)
            frozen = float((rec.get("grading") or {}).get("denom_usd") or 0.0)
            if rd is not None and frozen > 0 and abs(rd - frozen) / frozen > DENOM_TOL:
                gates["denominator_mismatches"].append(
                    {"position_id": pid, "frozen": frozen, "recomputed": round(rd, 2)})

    graded = [r for r in exits
              if r.get("position_id") not in set(gates["malformed_exits"])
              and r.get("strategy_id") == sid]
    # per-cohort evidence (wealth restarts at 1.0 per cohort - same law as the main grader)
    by_cohort = defaultdict(list)
    for rec in graded:
        by_cohort[str(rec.get("strategy_config_hash") or "?")].append(rec)
    live_cohort = meta["cohort"] if meta else None
    evidence = {}
    for cohort, recs in sorted(by_cohort.items()):
        rs, skipped = [], 0
        basis0 = None
        for rec in recs:
            r = r_return(rec)
            basis0 = basis0 or (rec.get("grading") or {}).get("basis")
            if r is None:
                skipped += 1
                gates["unusable_returns"].append(rec.get("position_id"))
                continue
            rs.append(r)
        wf = wealth_for(rs, basis0 or "debit")
        gates["floor_breaches"].extend(
            recs[i].get("position_id") for i in wf["floor_breaches"])
        evidence[cohort] = {"n": len(rs), "skipped": skipped, "basis": basis0,
                            "lambda_grid": list(lambdas_for(basis0 or "debit")),
                            "wealth_for": round(wf["wealth"], 4),
                            "wealth_against": round(wealth_against(rs, basis0 or "debit"), 4),
                            "mean_r": (round(wf["mean_r"], 5) if wf["mean_r"] is not None else None)}

    nets = [float(r["ledgers"]["worst"]["net_pnl_usd"]) for r in graded
            if isinstance(r.get("ledgers"), dict)]
    attribs = [attribute(r, entry_by_pid.get(r.get("position_id")) or {}) for r in graded]
    attr = loss_shares(attribs, nets) if graded else None

    today = [r for r in graded if day and r.get("day") == day]
    day_net = round(sum(float(r["ledgers"]["worst"]["net_pnl_usd"]) for r in today), 2)

    # funnel: entries per trailing 20 sessions vs META expectation
    days_with_entries = sorted({r.get("day") for r in entries})
    expected = float(meta["expected_fires_per_20"]) if meta else 4.0
    recent = [d for d in days_with_entries][-40:]
    fires_recent = len([r for r in entries if r.get("day") in set(recent[-20:])])
    # Warmup guard (lab-funnel-warmup-guard-v1): the trailing-20 funnel metric compares a
    # window of fires against a FULL-20-session expectation. Before ~20 sessions have elapsed
    # that is unfair: a low-frequency strategy (wput=weekly, tsmom=monthly) can't reach its
    # target, and an ON-PACE strategy (overnight_1dte fires ~3/session -> 60/20) looks starved
    # because a couple sessions of fires is naturally < 0.3*full. Fix: pro-rate the expectation
    # by the elapsed lab window for BOTH the STARVED threshold and the DEAD/WARMUP cut.
    #   * expected_over_elapsed < 1  -> not enough sessions to expect even one fire -> WARMUP
    #     (not assessable, no defect).
    #   * else compare fires_recent against 0.3 * (fires expected over the elapsed window).
    # Frequency-aware: a daily strategy that expects >=1 fire is still flagged if it's silent.
    # Byte-identical once >=20 sessions elapse (min(.,20)/20 == 1). None => guard disengaged
    # (legacy full-window behaviour preserved for any non-main caller).
    # LIMITATION: uniform-cadence only; a day-of-week-concentrated strategy (wput fires Fridays)
    # can still read DEAD across non-trigger sessions. That self-resolves once a trigger day
    # elapses; a persistent post-trigger zero IS a real defect. Cadence-aware warmup is a
    # future refinement (needs per-strategy trigger predicates in the registry).
    expected_over_elapsed = (None if lab_sessions_elapsed is None
                             else expected * min(int(lab_sessions_elapsed), 20) / 20.0)
    starved_target = expected if expected_over_elapsed is None else expected_over_elapsed
    if not entries:
        base = "DEAD" if (meta and meta.get("armed")) else "NO-DATA"
    elif fires_recent < STARVED_FRac * starved_target:
        base = "STARVED"
    else:
        base = "OK"
    # Override only a NEGATIVE health, and ONLY while genuinely in warmup: the trailing-20
    # window must still be unfull (elapsed < 20) AND the pro-rated expectation < 1 fire. The
    # elapsed<20 bound is load-bearing: without it, a strategy whose expected_fires_per_20 is
    # intrinsically < 1 (a rare-event / quarterly cadence, e.g. an honestly-declared pre-FOMC
    # at ~0.63) would satisfy expected_over_elapsed<1 at EVERY elapsed count and be silenced
    # forever - conflating "warmup not over" with "low-frequency target". Once >=20 sessions
    # elapse the window is full and the guard is a complete no-op (byte-identical to legacy).
    # A positive (OK) health from an actively-firing strategy always stands. None => disengaged.
    warming = (lab_sessions_elapsed is not None and lab_sessions_elapsed < 20
               and expected_over_elapsed is not None and expected_over_elapsed < 1.0)
    if base in ("STARVED", "DEAD") and warming:
        health = "WARMUP"
    else:
        health = base

    gates_clean = all(not v for v in gates.values())
    live_ev = evidence.get(live_cohort) or (list(evidence.values())[-1] if evidence else None)
    v = verdict_for(gates_clean=gates_clean,
                    n=(live_ev or {}).get("n", 0),
                    wealth_for=(live_ev or {}).get("wealth_for", 1.0),
                    wealth_against=(live_ev or {}).get("wealth_against", 1.0),
                    mean_net_usd=(sum(nets) / len(nets)) if nets else None,
                    attribution=attr, funnel_health=health)

    return {"gates": gates, "n_exits": len(graded), "n_entries": len(entries),
            "n_today": len(today), "day_net_worst_usd": day_net,
            "net_worst_sum_usd": round(sum(nets), 2),
            "winrate_worst": (round(sum(1 for x in nets if x > 0) / len(nets), 3) if nets else None),
            "evidence": evidence, "live_cohort": live_cohort,
            "attribution": attr, "funnel": {"health": health, "fires_recent20": fires_recent,
                                            "expected_per_20": expected,
                                            "sessions_with_entries": len(days_with_entries),
                                            "lab_sessions_elapsed": lab_sessions_elapsed,
                                            "expected_over_elapsed": (
                                                None if expected_over_elapsed is None
                                                else round(expected_over_elapsed, 3))},
            **v}


# ------------------------------------------------------------------ tier-1 validation
def validate_trades(sid: str, ledger: LabLedger, day: str | None) -> list:
    """Per-trade re-derivation (Tier-1): recompute every leg open fill from its recorded NBBO,
    the net fills, the denominator, and return_pct. Any mismatch is listed."""
    s = ledger.strategy(sid)
    out = []
    entries = {r.get("position_id"): r for r in read_jsonl(s.entries_path)
               if r.get("event") == "lab_entry"}
    for rec in read_jsonl(s.exits_path):
        if rec.get("event") != "lab_exit" or (day and rec.get("day") != day):
            continue
        pid = rec.get("position_id")
        ent = entries.get(pid)
        problems = []
        if ent is None:
            problems.append("no matching entry record")
        else:
            for l in ent["legs"]:
                expect = leg_open_fills(int(l["side"]), float(l["nbbo"]["bid"]),
                                        float(l["nbbo"]["ask"]))
                if any(abs(expect[k] - float(l["fills"][k])) > 1e-6 for k in expect):
                    problems.append(f"leg {l['occ']}: recorded open fills != recomputed")
            pairs = []
            for l in ent["legs"]:
                spec = LegSpec(occ=l["occ"], underlying=l["underlying"], opt_type=l["opt_type"],
                               strike=float(l["strike"]),
                               expiry=__import__("datetime").date.fromisoformat(str(l["expiry"])),
                               side=int(l["side"]), qty=int(l.get("qty", 1)))
                pairs.append((spec, l["fills"]))
            net = combo_net_open(pairs)
            if any(abs(net[k] - float(ent["net_fills"][k])) > 1e-6 for k in net):
                problems.append("net_fills != recomputed")
            rd = _recompute_denom(ent)
            frozen = float((rec.get("grading") or {}).get("denom_usd") or 0.0)
            if rd is not None and frozen > 0 and abs(rd - frozen) / frozen > DENOM_TOL:
                problems.append(f"denominator drift frozen={frozen} recomputed={rd:.2f}")
            r = r_return(rec)
            led = rec["ledgers"]["worst"]
            if r is not None and frozen > 0:
                if abs(r - float(led["net_pnl_usd"]) / frozen) > 1e-9:
                    problems.append("return_pct != net/denom")
        if _identity_violation(rec):
            problems.append("ledger identity violated")
        out.append({"position_id": pid, "strategy_id": sid, "day": rec.get("day"),
                    "rule": rec.get("rule"), "net_worst": rec["ledgers"]["worst"]["net_pnl_usd"]
                    if isinstance(rec.get("ledgers"), dict) else None,
                    "tier1": "PASS" if not problems else "FAIL", "problems": problems})
    return out


# ------------------------------------------------------------------ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Grade the strategy lab")
    ap.add_argument("--day", default=None)
    ap.add_argument("--strategy", default=None)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--runtime-dir", default=str(FRAMEWORK_ROOT / "runtime"))
    args = ap.parse_args(argv)

    runtime = Path(args.runtime_dir)
    ledger = LabLedger(runtime)
    try:
        strategies = build_all()
        state = load_state()
    except Exception as exc:  # noqa: BLE001 - registry failure must still produce a scorecard
        strategies, state = {}, {}
        print(f"REGISTRY-ERROR {exc}", file=sys.stderr)

    sids = sorted(set(ledger.known_strategy_dirs()) | set(strategies))
    if args.strategy:
        sids = [s for s in sids if s == args.strategy]

    if args.validate:
        rows = []
        for sid in sids:
            rows.extend(validate_trades(sid, ledger, args.day))
        print(json.dumps({"validate": rows, "day": args.day}, indent=1))
        return 0 if all(r["tier1"] == "PASS" for r in rows) else 1

    # lab-wide pid collision gate + elapsed-session count (for the funnel warmup guard):
    # distinct days on which the lab placed ANY entry = a conservative lower bound on the
    # number of sessions the lab has operated (never over-counts, so the guard can only be
    # more conservative, never falsely un-suppress a real starvation).
    pid_owner: dict[str, str] = {}
    collisions = []
    lab_days: set = set()
    for sid in sids:
        for rec in read_jsonl(ledger.strategy(sid).entries_path):
            pid = rec.get("position_id")
            if rec.get("day"):
                lab_days.add(rec.get("day"))
            if pid and pid in pid_owner and pid_owner[pid] != sid:
                collisions.append(pid)
            elif pid:
                pid_owner[pid] = sid
    lab_sessions_elapsed = len(lab_days)

    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "day_requested": args.day,
           "thresholds": {"pilot": WEALTH_PILOT, "sized_live": WEALTH_LIVE,
                          "against_flag": AGAINST_FLAG, "against_prune": AGAINST_PRUNE,
                          "n_verdict_min": N_VERDICT_MIN, "r_cap": R_CAP},
           "multiplicity_note": (f"{len(sids)} strategies watched; at the PILOT bar expect "
                                 f"~1 false flag per 5 null strategies - PILOT is a discussion "
                                 f"trigger, arming is a per-strategy registration"),
           "pid_collisions": collisions, "strategies": {}, "summary_table": []}

    for sid in sids:
        strat = strategies.get(sid)
        meta = None
        if strat is not None:
            meta = {"cohort": strat.config_hash(),
                    "expected_fires_per_20": strat.META.expected_fires_per_20_sessions,
                    "armed": state.get(sid, {}).get("state") == "armed",
                    "defining_mechanism": strat.META.defining_mechanism,
                    "basis_declared": strat.META.grading_basis.value}
        blk = grade_strategy(sid, ledger, meta, day=args.day,
                             lab_sessions_elapsed=lab_sessions_elapsed)
        if collisions:
            blk["gates"]["pid_collisions"] = collisions
        blk["state"] = state.get(sid, {}).get("state") or "unregistered"
        blk["meta"] = meta
        out["strategies"][sid] = blk
        ev = blk["evidence"].get(blk.get("live_cohort") or "", None) \
            or (list(blk["evidence"].values())[-1] if blk["evidence"] else {})
        out["summary_table"].append(
            [sid, blk["state"], (blk.get("live_cohort") or "?")[:12], ev.get("n", 0),
             blk["day_net_worst_usd"], ev.get("wealth_for", 1.0), ev.get("wealth_against", 1.0),
             blk["funnel"]["health"], blk["verdict"], blk["action"]])

    # daily-return append for the correlation block (one row per strategy per graded day)
    if args.day:
        for sid in sids:
            blk = out["strategies"][sid]
            if blk["n_today"]:
                from atlas.options.shadow import append_jsonl
                append_jsonl(ledger.root / "daily_returns.jsonl",
                             {"day": args.day, "strategy_id": sid,
                              "net_worst_usd": blk["day_net_worst_usd"],
                              "n": blk["n_today"]})

    # cross-strategy exposure + correlation (Phase-8 block; opts-lab-exposure-wire-v1) - the
    # aggregate Greek book over ALL open combos ("N strategies short SPY vega = ONE bet") + the
    # pairwise-correlation / effective_n once daily_returns accrues. Per-strategy stats never
    # read this. Open positions rebuilt fail-closed; entry_S is the spot fallback for an EOD snap.
    from atlas.strategy_lab.exposure import aggregate as _agg, correlation_block as _corr
    from atlas.strategy_lab.ledger import LedgerUnreadable as _LU
    try:
        open_by = ledger.open_positions_all(sids)
        exposure = _agg(open_by)
    except _LU as exc:
        exposure = {"error": f"ledger unreadable: {exc}"}
    daily_ret: dict = {}
    dr_path = ledger.root / "daily_returns.jsonl"
    for r in read_jsonl(dr_path):
        sid, day = r.get("strategy_id"), r.get("day")
        denom = 0.0
        # normalize the day P&L by that strategy's frozen-denominator sum is out of scope here;
        # use net_worst_usd directly as the daily series (correlation is scale-invariant).
        if sid and day:
            daily_ret.setdefault(sid, {})[day] = float(r.get("net_worst_usd") or 0.0)
    out["cross"] = {"exposure": exposure, "correlation": _corr(daily_ret)}

    tmp = ledger.root / "scorecard.json.tmp"
    ledger.root.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    atomic_replace(tmp, ledger.root / "scorecard.json")
    print(json.dumps({"summary_table": out["summary_table"],
                      "pid_collisions": collisions}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
