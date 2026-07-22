"""OPTIONS SHADOW nightly scorecard (O4) - per-lane, three-ledger, falsification-checked.

  PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\grade_options_shadow.py [--day YYYY-MM-DD]

Reads runtime/options_shadow_{entries,marks,exits}.jsonl and prints + persists the scorecard the
plan mandates: per lane - n, three-ledger gross AND net P&L (WORST = the grading ledger), win
rate, profit factor, exit-rule mix, risk-flag decomposition (joined from the ENTRY record by
position_id - exit records don't carry flags), day-concentration; plus the FALSIFICATION checks
(the ledger must be able to SEE the known taxes):
  #1 cost_share_of_losses - spread paid as a share of total WORST-ledger losses;
  #2 worst<=base<=optimistic net-P&L identity on every trade;
  #3 schema visibility - every exit row must carry ledgers.{worst,base,optimistic}.net_pnl_usd
     and a rule id; malformed rows are EXCLUDED from stats and reported loudly (a scorecard that
     grades rows it can't read is worse than no scorecard).
Verdict per lane uses the pre-registered PASS bar; N-progress is reported against the 25
(HELP/HURT) and 50-100 (go-live talk) sample floors. Output:
runtime/options_shadow_scorecard.json + stdout table.

FIELD CONTRACT (pinned by tests/test_grade_options_shadow.py against the shadow.py builders):
exit rows are shadow.build_exit_record() output - "ledgers" {worst|base|optimistic:
{net_pnl_usd, gross_pnl_usd}}, "rule", "decomposition" {spread_paid_usd, theta_paid_usd},
"day", "lanes", "variant_would_hold", "position_id". Entry rows carry "risk_flags".
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from atlas.config_loader import FRAMEWORK_ROOT
from atlas.options.shadow import ShadowLedger, read_jsonl

PASS_N_MIN = 25
GO_LIVE_N = 50
LEDGER_NAMES = ("worst", "base", "optimistic")

# ---- anytime-valid evidence machine (audit 2026-07-16 EVIDENCE-MACHINE-1/2/3,
# opts-audit-wave0-evidence-v1). The legacy PASS bar (mean>0 + PF>=1.2 at N>=25) is a fixed-
# effect-size filter: ~33% false-PASS per lane at N=25 under a zero-edge null, ~69% under the
# nightly all-history re-grade (unbounded peeking), ~87% familywise across 5 lanes; and all-USD
# stats let one $2-3k contract carry ~94% of a lane's variance. Replacement: a betting
# e-process on %-OF-PREMIUM WORST returns R_i = net/(100*contracts*entry_fill), bounded below
# by -1 by construction of a long option. Wealth W_n = mean over the lambda grid of
# prod_i (1 + lambda * min(R_i, EPROCESS_R_CAP)); under H0 (E[R] <= 0) W is a supermartingale,
# so Ville's inequality makes the NIGHTLY re-grade legitimately anytime-valid:
# P(sup W >= 1/alpha | H0) <= alpha. Wealth >= 5 (P<=20% under null) unlocks a tuition-capped
# 1-lot PILOT; wealth >= 20 (P<=5%) unlocks sized live - graduated go-live, casino posture
# with bounded self-deception. Wealth is keyed by (scope, entry-cohort config_hash): a new
# cohort starts fresh at 1.0 (no selection-then-confirmation).
EPROCESS_LAMBDAS = (0.05, 0.10, 0.20)
EPROCESS_R_CAP = 2.0            # cap a single bet's win at +200% of premium (anti-fluke)
WEALTH_PILOT = 5.0              # >= 5:1 odds against the null -> 1-lot tuition-capped pilot
WEALTH_LIVE = 20.0              # >= 20:1 -> sized-live discussion
MDE_Z = 2.486                   # z_0.95 + z_0.80: one-sided 5% / 80% power


def _pf(nets: list[float]) -> float | None:
    wins = sum(x for x in nets if x > 0)
    losses = -sum(x for x in nets if x < 0)
    if losses <= 0:
        return None if wins <= 0 else float("inf")
    return wins / losses


def _r_premium(rec: dict) -> float | None:
    """Per-trade return in %-of-premium on the WORST ledger: net / (100*contracts*entry_fill).
    None when the entry fill is unusable (excluded from the e-process, listed loudly)."""
    led = (rec.get("ledgers") or {}).get("worst") or {}
    try:
        entry_fill = float(led.get("entry_fill", 0.0))
        contracts = float(rec.get("contracts") or 1)
        if entry_fill <= 0 or contracts <= 0:
            return None
        return float(led.get("net_pnl_usd", 0.0)) / (100.0 * contracts * entry_fill)
    except (TypeError, ValueError):
        return None


def eprocess_wealth(rs: list[float]) -> float:
    """Betting e-process wealth over exits in time order (mean over the lambda grid)."""
    if not rs:
        return 1.0
    wealth = []
    for lam in EPROCESS_LAMBDAS:
        w = 1.0
        for r in rs:
            w *= max(1e-12, 1.0 + lam * min(max(r, -1.0), EPROCESS_R_CAP))
        wealth.append(w)
    return sum(wealth) / len(wealth)


def _stale_fill(rec: dict) -> bool:
    """Forced exits that filled at a fallback NBBO (audit SHADOW-LEDGER-3 provenance): visible
    in state.nbbo_source; excluded from e-process wealth, listed loudly, kept in legacy stats."""
    st = rec.get("state") if isinstance(rec.get("state"), dict) else {}
    src = st.get("nbbo_source")
    return src not in (None, "fresh")


def _net(rec: dict, ledger: str) -> float:
    return float(((rec.get("ledgers") or {}).get(ledger) or {}).get("net_pnl_usd", 0.0))


def _gross(rec: dict) -> float:
    # gross is mid-to-mid and ledger-independent by construction; worst carries it
    return float(((rec.get("ledgers") or {}).get("worst") or {}).get("gross_pnl_usd", 0.0))


def _malformed(rec: dict) -> bool:
    """Falsification #3: an exit row the grader cannot actually read (schema drift guard - 
    the original 2026-07-09 grader read fields the builders never wrote and would have graded
    every lane as all-zero P&L without noticing). Audit GRADER-5: day/lanes/decomposition used
    to fail SOFT ('?'/epoch-strings/0.0) - the exact silent-drift class the gate exists for."""
    led = rec.get("ledgers")
    if not isinstance(led, dict):
        return True
    for name in LEDGER_NAMES:
        sub = led.get(name)
        if not isinstance(sub, dict) or "net_pnl_usd" not in sub or "gross_pnl_usd" not in sub:
            return True
    if not isinstance(rec.get("day"), str) or len(str(rec.get("day"))) != 10:
        return True
    if not isinstance(rec.get("lanes"), list) or not rec.get("lanes"):
        return True
    if not isinstance(rec.get("decomposition"), dict):
        return True
    return not rec.get("rule")


def grade(ledger: ShadowLedger, day: str | None) -> dict:
    all_exits = ledger.load_exits(day=None)           # all history; per-day slice reported inside
    entries = ledger.load_entries(day=None)
    flags_by_pid = {e.get("position_id"): list(e.get("risk_flags") or []) for e in entries}
    cohort_by_pid = {e.get("position_id"): str(e.get("config_hash") or "unknown")
                     for e in entries}

    malformed = [x.get("position_id") for x in all_exits if _malformed(x)]
    exits = [x for x in all_exits if not _malformed(x)]

    # duplicate-exit dedupe (audit GRADER-7/SHADOW-LEDGER-2, opts-audit-wave0-evidence-v1):
    # a duplicated exit row (resurrection re-exit, torn-tail replay) silently double-counted
    # into n/mean/PF. FIRST row by ts_epoch wins; duplicates are quarantined LOUDLY.
    exits.sort(key=lambda r: float(r.get("ts_epoch") or 0.0))
    duplicate_exits = []
    seen_pids: set = set()
    deduped = []
    for x in exits:
        pid = x.get("position_id")
        if pid in seen_pids:
            duplicate_exits.append(pid)
            continue
        seen_pids.add(pid)
        deduped.append(x)
    exits = deduped

    identity_violations = []
    halted_underlying = []
    stale_fill_exits = []
    pooled_rows: list[dict] = []                      # each REAL trade exactly once ("ALL" row)
    by_lane: dict[str, list[dict]] = defaultdict(list)
    for x in exits:
        if "underlying_halted" in flags_by_pid.get(x.get("position_id"), []):
            halted_underlying.append(x.get("position_id"))
            continue                       # falsification (opts-fix-grade-halt-quarantine-v1): a
            #                                position recorded on a HALTED / SEC-suspended underlying
            #                                is an un-fillable phantom - its fills are fiction; it
            #                                must not pool into lane means/PF/verdicts. Same class as
            #                                the malformed / identity-violation quarantines.
        w, b, o = _net(x, "worst"), _net(x, "base"), _net(x, "optimistic")
        if not (w <= b + 1e-9 and b <= o + 1e-9):
            identity_violations.append(x.get("position_id"))
            continue                       # QUARANTINED like malformed rows (audit fix
            #                                opts-fix-math-audit-20260710): a row whose fill
            #                                accounting is provably broken must not pool into
            #                                lane means/PF/verdicts it would silently poison
        if _stale_fill(x):
            stale_fill_exits.append(x.get("position_id"))   # visible; excluded from WEALTH only
        pooled_rows.append(x)                               # merged multi-lane trades count ONCE
        for lane in (x.get("lanes") or ["?"]):
            by_lane[lane].append(x)

    today = day or date.today().isoformat()

    # ---- e-process evidence per scope x cohort (audit EVIDENCE-MACHINE-1/2/7) ----------------
    def _evidence(rows: list[dict]) -> dict:
        by_cohort: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_cohort[cohort_by_pid.get(r.get("position_id"), "unknown")].append(r)
        out = {}
        for cohort, crows in sorted(by_cohort.items()):
            rs, skipped = [], 0
            for r in sorted(crows, key=lambda z: float(z.get("ts_epoch") or 0.0)):
                if _stale_fill(r):
                    skipped += 1
                    continue
                rp = _r_premium(r)
                if rp is None:
                    skipped += 1
                    continue
                rs.append(rp)
            w = eprocess_wealth(rs)
            out[cohort] = {
                "n": len(rs), "wealth": round(w, 4),
                "mean_r_premium": round(sum(rs) / len(rs), 4) if rs else None,
                "stale_or_unusable_skipped": skipped,
                "unlock": ("SIZED-LIVE" if w >= WEALTH_LIVE
                           else "PILOT" if w >= WEALTH_PILOT else None),
            }
        return out

    # honest minimum-detectable-edge line (audit EVIDENCE-MACHINE-2): what this machine can and
    # cannot see at the observed fire rate - nobody gets to misread ACCUMULATING as "soon"
    distinct_days = {str(r.get("day")) for r in pooled_rows}
    rs_all = [r for r in (_r_premium(x) for x in pooled_rows) if r is not None]
    if len(rs_all) >= 5:
        m = sum(rs_all) / len(rs_all)
        sd = (sum((r - m) ** 2 for r in rs_all) / (len(rs_all) - 1)) ** 0.5
    else:
        sd = 1.0                                       # research prior: ~100% of premium
    trades_per_year = (len(pooled_rows) / max(1, len(distinct_days))) * 252.0
    n_1yr = max(1.0, trades_per_year)
    mde = {
        "trades_per_year_at_current_rate": round(trades_per_year, 1),
        "per_trade_sd_r_premium": round(sd, 3),
        "mde_1yr_pct_of_premium": round(100.0 * MDE_Z * sd / (n_1yr ** 0.5), 1),
        "note": "one-sided alpha=5%, power=80%; the selector's own entry floor is 10% of ask - "
                "if MDE exceeds it, the machine cannot verify its own design target this year",
    }

    lanes_out = {}
    for lane, rows in sorted(by_lane.items()):
        nets_w = [_net(r, "worst") for r in rows]
        nets_b = [_net(r, "base") for r in rows]
        grosses = [_gross(r) for r in rows]
        days = defaultdict(float)
        rules = defaultdict(int)
        flags = defaultdict(lambda: [0, 0.0])
        spread_paid = theta_paid = 0.0
        overnight_divergences = 0
        n_today = 0
        net_today = 0.0
        for r, net_w in zip(rows, nets_w):
            r_day = str(r.get("day") or r.get("ts_epoch", ""))[:10]
            days[r_day] += net_w
            if r_day == today:
                n_today += 1
                net_today += net_w
            rules[str(r.get("rule") or "?")] += 1
            dec = r.get("decomposition") or {}
            spread_paid += float(dec.get("spread_paid_usd", 0.0))
            theta_paid += float(dec.get("theta_paid_usd", 0.0))
            overnight_divergences += 1 if r.get("variant_would_hold") else 0
            for fl in flags_by_pid.get(r.get("position_id"), []):
                flags[fl][0] += 1
                flags[fl][1] += net_w
        n = len(rows)
        net_sum_w = sum(nets_w)
        total_losses_w = -sum(x for x in nets_w if x < 0)
        # falsification #1: the ledger must SEE the cost tax - spread share of total losses
        cost_visibility = (spread_paid / total_losses_w) if total_losses_w > 0 else None
        top_day_share = (max(abs(v) for v in days.values()) / max(1e-9, sum(abs(v) for v in days.values()))
                         if days else None)
        passes = (n >= PASS_N_MIN and net_sum_w / max(n, 1) > 0 and sum(grosses) > 0
                  and (_pf(nets_w) or 0) >= 1.2 and (top_day_share or 1.0) < 0.5)
        lanes_out[lane] = {
            "n": n, "n_progress": f"{n}/{PASS_N_MIN} (go-live talk at {GO_LIVE_N})",
            "n_today": n_today, "net_worst_today": round(net_today, 2),
            "net_worst_sum": round(net_sum_w, 2), "net_worst_mean": round(net_sum_w / n, 3) if n else None,
            "net_base_mean": round(sum(nets_b) / n, 3) if n else None,
            "gross_sum": round(sum(grosses), 2),
            "winrate_worst": round(sum(1 for x in nets_w if x > 0) / n, 3) if n else None,
            # inf -> the STRING "inf" (audit fix): json.dumps would emit bare `Infinity`,
            # which is spec-invalid JSON and breaks jq/JS consumers of the scorecard
            "profit_factor_worst": (round(_pf(nets_w), 2)
                                    if n and _pf(nets_w) not in (None, float("inf"))
                                    else ("inf" if (n and _pf(nets_w) == float("inf")) else None)),
            "exit_rule_mix": dict(sorted(rules.items(), key=lambda kv: -kv[1])),
            "risk_flags": {k: {"n": v[0], "net": round(v[1], 2)} for k, v in sorted(flags.items())},
            "spread_paid_total": round(spread_paid, 2), "theta_paid_total": round(theta_paid, 2),
            "cost_share_of_losses": round(cost_visibility, 3) if cost_visibility is not None else None,
            "overnight_variant_divergences": overnight_divergences,
            "top_day_share": round(top_day_share, 3) if top_day_share is not None else None,
            # legacy fixed-threshold verdict RETAINED for display continuity; the e-process
            # wealth below is the PRIMARY evidence statistic (audit EVIDENCE-MACHINE-1)
            "verdict": ("PASS" if passes else ("ACCUMULATING" if n < PASS_N_MIN else "FAILING")),
            "evidence": _evidence(rows),
        }

    # expired-unexited entries (process gaps): kept visible with an OCC-reality terminal value
    # (auto-exercise at >= $0.01 ITM) estimated from the expiry day's quote path - never graded
    # at a stale NBBO, never silently dropped, never pooled into lane stats
    exited_ids = {x.get("position_id") for x in all_exits}
    try:
        today_d = date.fromisoformat(today)
    except (TypeError, ValueError):
        today_d = date.today()
    expired_unexited = []
    for e in entries:
        if e.get("position_id") in exited_ids or e.get("merged_into"):
            continue
        pick = e.get("pick") or {}
        try:
            expy = date.fromisoformat(str(pick.get("expiry")))
        except (TypeError, ValueError):
            continue
        # audit GRADER-6: on the nightly (post-close) run, an entry expiring TODAY with no exit
        # IS already a process gap - `expy >= today_d` hid the 0DTE common case on the one
        # night anyone looks. Same-day expiries count once the session is over (>= 16:00 local
        # is safely post-close in both CT and ET).
        still_live = expy > today_d or (expy == today_d and datetime.now().hour < 16)
        if still_live:
            continue                                   # still a live position, not a gap
        intrinsic = None
        rows = [r for r in read_jsonl(ledger.quotes_dir / f"{expy.isoformat()}.jsonl")
                if r.get("occ") == pick.get("occ")]
        if rows:
            s_term = float(rows[-1].get("S") or 0.0)
            k = float(pick.get("strike") or 0.0)
            if s_term > 0 and k > 0:
                val = max(0.0, s_term - k) if pick.get("opt_type") == "call" else max(0.0, k - s_term)
                intrinsic = round(val * 100.0, 2)
        expired_unexited.append({"position_id": e.get("position_id"), "occ": pick.get("occ"),
                                 "entry_day": e.get("day"), "expiry": str(pick.get("expiry")),
                                 "est_terminal_intrinsic_usd": intrinsic})

    # pooled ALL row (audit GRADER-2/EVIDENCE-MACHINE-2): the PRIMARY existence-of-edge verdict - 
    # every real trade exactly once (merged multi-lane trades deduped by position_id), so
    # portfolio-level evidence accrues at the full fire rate instead of fragmenting per lane
    pooled_evidence = _evidence(pooled_rows)
    pooled_nets = [_net(r, "worst") for r in pooled_rows]
    pooled = {
        "n": len(pooled_rows),
        "net_worst_sum": round(sum(pooled_nets), 2),
        "net_worst_mean": round(sum(pooled_nets) / len(pooled_nets), 3) if pooled_rows else None,
        "winrate_worst": (round(sum(1 for v in pooled_nets if v > 0) / len(pooled_nets), 3)
                          if pooled_rows else None),
        "evidence": pooled_evidence,
    }

    # entry-side context: fire counts + selector rejection visibility come from the journal
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "day_requested": today,
        "entries_total": len(entries),
        "exits_total": len(all_exits),
        "malformed_exits": malformed,                 # falsification #3 - MUST be empty
        "duplicate_exits": duplicate_exits,           # GRADER-7 dedupe - MUST be empty
        "ledger_identity_violations": identity_violations,   # falsification #2 - MUST be empty
        "halted_underlying_exits": halted_underlying,  # un-fillable phantoms on halted/suspended names
        "stale_fill_exits": stale_fill_exits,         # fallback-NBBO fills: excluded from wealth
        "expired_unexited": expired_unexited,         # process gaps, terminal-intrinsic estimated
        "pooled": pooled,                             # PRIMARY evidence scope (e-process wealth)
        "mde": mde,                                   # what the machine can/cannot see this year
        "wealth_thresholds": {"pilot": WEALTH_PILOT, "sized_live": WEALTH_LIVE,
                              "lambdas": list(EPROCESS_LAMBDAS), "r_cap": EPROCESS_R_CAP},
        "lanes": lanes_out,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Grade the options shadow ledgers")
    ap.add_argument("--day", default=None)
    args = ap.parse_args()
    ledger = ShadowLedger(FRAMEWORK_ROOT / "runtime")
    card = grade(ledger, args.day)
    out = FRAMEWORK_ROOT / "runtime" / "options_shadow_scorecard.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(card, indent=1), encoding="utf-8")
    from atlas.fsutil import atomic_replace
    atomic_replace(tmp, out)

    print("=" * 78)
    print(f"OPTIONS SHADOW SCORECARD  (generated {card['generated']}; "
          f"{card['entries_total']} entries / {card['exits_total']} exits all-time)")
    if card["malformed_exits"]:
        print(f"  !! MALFORMED EXIT ROWS (grader cannot read them; EXCLUDED from stats): "
              f"{card['malformed_exits']} - fix the schema before believing anything")
    if card["duplicate_exits"]:
        print(f"  !! DUPLICATE EXIT ROWS (same position_id; first-by-time kept, rest EXCLUDED): "
              f"{card['duplicate_exits']}")
    if card["stale_fill_exits"]:
        print(f"  !! STALE-FILL EXITS (fallback NBBO; excluded from e-process wealth): "
              f"{card['stale_fill_exits']}")
    pooled = card.get("pooled") or {}
    print(f"  [POOLED ALL] n={pooled.get('n')} net(worst) sum={pooled.get('net_worst_sum')} "
          f"mean={pooled.get('net_worst_mean')} wr={pooled.get('winrate_worst')}")
    for cohort, ev in (pooled.get("evidence") or {}).items():
        print(f"      cohort {cohort}: wealth={ev['wealth']} (n={ev['n']}, "
              f"mean R%={ev['mean_r_premium']}) "
              f"{'-> ' + ev['unlock'] + ' UNLOCK' if ev['unlock'] else ''}  "
              f"[pilot>={card['wealth_thresholds']['pilot']}, "
              f"live>={card['wealth_thresholds']['sized_live']}]")
    mde = card.get("mde") or {}
    print(f"  MDE: ~{mde.get('trades_per_year_at_current_rate')} trades/yr -> smallest "
          f"detectable edge this year ~{mde.get('mde_1yr_pct_of_premium')}% of premium "
          f"(sd {mde.get('per_trade_sd_r_premium')})")
    if card["ledger_identity_violations"]:
        print(f"  !! LEDGER IDENTITY VIOLATIONS (worst<=base<=optimistic broke): "
              f"{card['ledger_identity_violations']} - the accounting cannot be trusted")
    if card["halted_underlying_exits"]:
        print(f"  !! HALTED-UNDERLYING positions (recorded on a halted/suspended name; un-fillable, "
              f"EXCLUDED from stats): {card['halted_underlying_exits']}")
    if card["expired_unexited"]:
        print(f"  !! EXPIRED-UNEXITED positions (process gaps; graded at terminal intrinsic, "
              f"NOT pooled into lanes): {card['expired_unexited']}")
    for lane, s in card["lanes"].items():
        print(f"  [{lane}] {s['verdict']}  n={s['n']} (today {s['n_today']})  "
              f"net(worst) mean={s['net_worst_mean']} sum={s['net_worst_sum']}  "
              f"gross={s['gross_sum']}  wr={s['winrate_worst']} pf={s['profit_factor_worst']}")
        print(f"      exits {s['exit_rule_mix']} | costs/losses {s['cost_share_of_losses']} | "
              f"overnight-variant divergences {s['overnight_variant_divergences']}")
    if not card["lanes"]:
        print("  (no exits recorded yet - the shadow accumulates during market hours)")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
