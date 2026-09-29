"""Offline, traceable exit-engine replay. Importing this module performs no IO."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import platform
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from atlas.options.replay import replay_decide_exit
from atlas.options.shadow import entry_fills, position_from_entry

ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).with_name("replay_assets")
BOOL_FIELDS = ("thesis_valid", "opposing_defense", "named_catalyst_tomorrow",
               "is_friday", "after_hours")
NUMBER_FIELDS = ("solved_iv", "iv_trend_per_hour", "mu_t_stat", "defense_zone_score")
CLOCK_FIELDS = ("minutes_to_next_print", "minutes_since_print", "planned_exit_minute")
CONTEXT_FIELDS = BOOL_FIELDS + NUMBER_FIELDS + CLOCK_FIELDS + ("mu_hat", "minute", "theta_share_breaches")
SOURCE_FILES = ("VERSION", "requirements.txt", "atlas/options/replay.py",
                "atlas/options/replay_report.py", "atlas/options/replay_demo.py",
                "atlas/options/shadow.py", "atlas/options/exit_engine.py",
                "atlas/options/exit_engine_legacy.py", "atlas/options/math.py",
                "atlas/options/trajectory.py", "atlas/options/vendor/blackscholes.py",
                "atlas/options/vendor/models.py", "atlas/options/replay_assets/report.html",
                "atlas/options/replay_assets/report.css", "atlas/options/replay_assets/report.js")


def _number(value, name, low=-1e9, high=1e9):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(name + " must be numeric")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(name + " is outside the supported finite range")
    return float(value)


def _integer(value, name, low=0, high=1439):
    n = _number(value, name, low, high)
    if n != int(n):
        raise ValueError(name + " must be an integer")
    return int(n)


def _text(value, name, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(name + " must be a nonempty bounded string")
    if any(ord(c) < 32 for c in value):
        raise ValueError(name + " contains a control character")
    return value


def _jsonable(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _canonical(value):
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _book(row, name, entry=False):
    bid = _number(row.get("bid"), name + ".bid", 0)
    ask = _number(row.get("ask"), name + ".ask", 0)
    # The engine supports a one-sided quote with ask=0; entry needs an executable ask.
    if (entry and ask <= 0) or (ask > 0 and bid > ask):
        raise ValueError(name + " is crossed or lacks an entry ask")


def _clock(ts, minute, day=None):
    stamp = datetime.fromtimestamp(_number(ts, "ts_epoch", 1, 32503680000), ZoneInfo("America/New_York"))
    if stamp.hour * 60 + stamp.minute != minute or (day and stamp.date().isoformat() != day):
        raise ValueError("stored ET minute/day and timestamp disagree")


def validate_history(entries, quotes):
    if not isinstance(entries, list) or not isinstance(quotes, list):
        raise ValueError("entries and quotes must be arrays")
    if not entries or len(entries) > 10000 or len(quotes) > 100000:
        raise ValueError("history needs 1..10000 entries and at most 100000 quotes")
    by_id, paths, excluded = {}, {}, 0
    for e in entries:
        if not isinstance(e, dict):
            raise ValueError("entry must be an object")
        if e.get("event") != "shadow_entry" or e.get("merged_into"):
            excluded += 1
            continue
        pid = _text(e.get("position_id"), "position_id")
        if pid in by_id:
            raise ValueError("duplicate entry position_id")
        day = date.fromisoformat(_text(e.get("day"), "day"))
        pick, sig, nbbo = e.get("pick"), e.get("signal"), e.get("nbbo")
        if not all(isinstance(x, dict) for x in (pick, sig, nbbo)):
            raise ValueError("entry needs pick, signal and nbbo objects")
        _book(nbbo, "entry nbbo", entry=True)
        _text(pick.get("occ"), "occ")
        _text(pick.get("underlying"), "underlying", 32)
        if pick.get("opt_type") not in ("call", "put"):
            raise ValueError("opt_type must be call or put")
        if date.fromisoformat(_text(pick.get("expiry"), "expiry")) < day:
            raise ValueError("entry is after expiry")
        _number(pick.get("strike"), "strike", 1e-6)
        _number(pick.get("S"), "entry S", 1e-6)
        _number(pick.get("theta_day", 0), "entry theta_day")
        _number(sig.get("target_move", 0), "target_move", 0, 1)
        _number(sig.get("mu_thesis", 0), "mu_thesis")
        _number(sig.get("p_thesis", .5), "p_thesis", 0, 1)
        _number(sig.get("horizon_T", 0), "horizon_T", 0, 10)
        _integer(e.get("contracts", 1), "contracts", 1, 100000)
        minute = _integer(e.get("entry_minute"), "entry_minute")
        _clock(e.get("ts_epoch"), minute, day.isoformat())
        if not isinstance(e.get("lanes"), list) or not all(isinstance(x, str) and len(x) <= 100 for x in e["lanes"]):
            raise ValueError("lanes must be bounded strings")
        expected = entry_fills(nbbo["bid"], nbbo["ask"])
        if e.get("fills") and e["fills"] != expected:
            raise ValueError("stored entry fills disagree with NBBO")
        if position_from_entry(e) is None:
            raise ValueError("entry cannot rebuild a position")
        by_id[pid], paths[pid] = e, []
    if not by_id:
        raise ValueError("no independent shadow_entry records")
    seen = set()
    for q in quotes:
        if not isinstance(q, dict) or q.get("event") != "shadow_quote":
            raise ValueError("quote must be a shadow_quote object")
        pid = _text(q.get("position_id"), "quote position_id")
        if pid not in by_id or q.get("occ") != by_id[pid]["pick"]["occ"]:
            raise ValueError("quote does not match an entry and contract")
        ts = _number(q.get("ts_epoch"), "quote timestamp", 1, 32503680000)
        if ts < by_id[pid]["ts_epoch"] or (pid, ts) in seen:
            raise ValueError("pre-entry or duplicate quote timestamp")
        seen.add((pid, ts))
        _book(q, "quote")
        _number(q.get("S"), "quote S", 1e-6)
        ext = q.get("ext")
        if ext is not None:
            if not isinstance(ext, dict) or not all(k in ext for k in CONTEXT_FIELDS):
                raise ValueError("partial ext context cannot support a faithful replay")
            minute = _integer(ext["minute"], "quote minute")
            _clock(ts, minute)
            for k in BOOL_FIELDS + ("evidence_stale",):
                if k in ext and not isinstance(ext[k], bool):
                    raise ValueError(k + " must be boolean")
            for k in NUMBER_FIELDS:
                _number(ext[k], k)
            if ext["solved_iv"] < 0:
                raise ValueError("solved_iv cannot be negative")
            for k in CLOCK_FIELDS:
                if ext[k] is not None:
                    _integer(ext[k], k, 0, 100000)
            if ext["mu_hat"] is not None:
                _number(ext["mu_hat"], "mu_hat")
            _integer(ext["theta_share_breaches"], "theta_share_breaches", 0, 100000)
            for k, low, high in (("p_thesis", 0, 1), ("horizon_T", 0, 10)):
                if k in ext:
                    _number(ext[k], k, low, high)
        paths[pid].append(q)
    return by_id, {k: sorted(v, key=lambda q: q["ts_epoch"]) for k, v in paths.items()}, excluded


def build_report(entries, quotes, *, label, fictional=False, fee_per_contract=0.0, variants=None):
    """Run the actual engines on identical paths. Open positions have no realized P&L."""
    label = _text(label, "dataset label", 240)
    fee = _number(fee_per_contract, "fee_per_contract", 0, 1000)
    by_id, paths, excluded = validate_history(entries, quotes)
    if variants is None:
        # Explicit invocation only; module import never starts a runner or broker.
        from atlas.options import exit_engine, exit_engine_legacy
        variants = [("current", exit_engine, exit_engine.ExitParams()),
                    ("frozen_v1", exit_engine_legacy, exit_engine_legacy.ExitParams())]
    if not variants or len({name for name, _, _ in variants}) != len(variants):
        raise ValueError("variant names must be unique")
    summary, positions = {}, []
    for name, engine, params in variants:
        _text(name, "variant", 60)
        summary[name] = {"closed": 0, "open": 0, "unreplayable": 0, "engine_errors": 0,
                         "realized_net_sum": 0.0, "realized_net_mean": None,
                         "rules": {}, "parameters": asdict(params)}
    for pid, e in sorted(by_id.items(), key=lambda x: (x[1]["ts_epoch"], x[0])):
        p = {"position_id": pid, "day": e["day"], "occ": e["pick"]["occ"],
             "entry_ts": e["ts_epoch"], "entry_ask": e["nbbo"]["ask"],
             "contracts": e.get("contracts", 1), "entry_sha256": _digest(e),
             "quotes_sha256": _digest(paths[pid]), "quotes_available": len(paths[pid]),
             "bare_quotes": sum(not isinstance(q.get("ext"), dict) for q in paths[pid]),
             "variants": {}}
        for name, engine, params in variants:
            trace = []
            result = replay_decide_exit(e, paths[pid], engine=engine, params=params, trace=trace)
            a = summary[name]
            if result is None:
                status, net, exit_ts = "unreplayable", None, None
            elif result["net_worst"] is None:
                status, net, exit_ts = "open", None, None
            else:
                status = "closed"
                net = round(result["net_worst"] - 2 * fee * p["contracts"], 2)
                exit_ts = trace[-1]["ts_epoch"]
                a["realized_net_sum"] += net
                a["rules"][result["rule"]] = a["rules"].get(result["rule"], 0) + 1
            a[status] += 1
            a["engine_errors"] += result["engine_errors"] if result else 0
            p["variants"][name] = {"status": status, "result": result, "net_after_fees": net,
                                   "exit_ts": exit_ts, "trace": _jsonable(trace),
                                   "v3_context_from_entry": any("p_thesis" not in q.get("ext", {}) or
                                       "horizon_T" not in q.get("ext", {}) for q in paths[pid] if q.get("ext") is not None)}
        positions.append(p)
    for a in summary.values():
        a["realized_net_sum"] = round(a["realized_net_sum"], 2)
        if a["closed"]:
            a["realized_net_mean"] = round(a["realized_net_sum"] / a["closed"], 2)
    paired = []
    if len(variants) == 2:
        first, second = [v[0] for v in variants]
        for p in positions:
            a, b = p["variants"][first], p["variants"][second]
            if a["status"] == b["status"] == "closed":
                paired.append({"position_id": p["position_id"], "baseline": first, "variant": second,
                               "net_delta": round(b["net_after_fees"] - a["net_after_fees"], 2),
                               "exit_delay_minutes": round((b["exit_ts"] - a["exit_ts"])/60, 3)})
    sources = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest()
               for f in SOURCE_FILES}
    import numpy as np
    report = {"environment": {"python": platform.python_version(), "numpy": np.__version__}, "schema": "shadow-replay-report/1", "product_version": (ROOT / "VERSION").read_text().strip(), "dataset": {"label": label, "fictional": bool(fictional),
              "entries_sha256": _digest(entries), "quotes_sha256": _digest(quotes)},
              "source_sha256": sources, "configuration_sha256": _digest({n: asdict(p) for n, _, p in variants}),
              "assumptions": {"fill": "Buy at entry ask, sell at first SELL quote bid; 100 shares per contract.",
                              "fee_per_contract_per_side": fee,
                              "open_positions": "Null realized P&L; excluded from closed-only sums and paired dollars.",
                              "scope": "Exit-policy replay of selected entries. No entry selection, market impact, liquidity guarantee, assignment, dividends or portfolio return estimate.",
                              "context": "Schema-1 rows are skipped. V3 probability/horizon use entry context when absent in stored ext, matching existing replay.",
                              "non_finite_engine_metrics": "Undefined or infinite internal metrics render as null.",
                              "data": "Fictional examples" if fictional else "User-supplied quote history; provenance hashes identify inputs, not vendor authenticity."},
              "excluded_merged_or_other_entries": excluded, "summary": summary,
              "positions": positions, "paired_closed_comparisons": paired}
    report = _jsonable(report)
    report["report_sha256"] = _digest(report)
    return report


def report_csv(report):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["position_id", "day", "occ", "variant", "status", "entry_ask", "contracts",
                     "exit_ts", "exit_minute", "rule", "net_before_fees", "net_after_fees",
                     "marks_replayed", "skipped_no_ext", "engine_errors", "entry_sha256", "quotes_sha256"])
    for p in report["positions"]:
        for name, v in p["variants"].items():
            r = v["result"] or {}
            row = [p["position_id"], p["day"], p["occ"], name, v["status"], p["entry_ask"],
                   p["contracts"], v["exit_ts"], r.get("exit_minute"), r.get("rule"),
                   r.get("net_worst"), v["net_after_fees"], r.get("marks_replayed"),
                   p["bare_quotes"], r.get("engine_errors"), p["entry_sha256"], p["quotes_sha256"]]
            writer.writerow(["'" + x if isinstance(x, str) and x.lstrip().startswith(("=", "+", "-", "@")) else x for x in row])
    return output.getvalue()


def report_html(report):
    css = (ASSETS / "report.css").read_text(encoding="utf-8")
    js = (ASSETS / "report.js").read_text(encoding="utf-8")
    template = (ASSETS / "report.html").read_text(encoding="utf-8")
    data = _canonical(report).decode().replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    import base64
    sha = lambda s: base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()
    csp = "default-src 'none'; script-src 'sha256-" + sha(js) + "'; style-src 'sha256-" + sha(css) + "'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
    return template.replace("__CSP__", csp).replace("__CSS__", css).replace("__JS__", js).replace("__DATA__", data)


def write_report(report, output):
    # Assemble completely before creating a directory. Never overwrite another report.
    payloads = {"report.json": json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
                "positions.csv": report_csv(report), "index.html": report_html(report)}
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=False)
    for name, data in payloads.items():
        (folder / name).write_text(data, encoding="utf-8", newline="\n")
    manifest = {"report_sha256": report["report_sha256"],
                "files": {n: hashlib.sha256((folder / n).read_bytes()).hexdigest() for n in payloads}}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path):
    p = Path(path)
    if p.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("ledger exceeds 20 MiB")
    rows = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON"))))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline exit-policy replay with complete decision traces")
    parser.add_argument("--demo", action="store_true", help="use explicitly fictional archived-date XYZ fixtures")
    parser.add_argument("--entries", type=Path)
    parser.add_argument("--quotes", type=Path, action="append", help="repeat for multiple historical day ledgers")
    parser.add_argument("--label", default="User-supplied quote history")
    parser.add_argument("--fee-per-contract", type=float, default=0.0, help="per side, for closed positions")
    parser.add_argument("--output", type=Path, required=True, help="a new directory")
    args = parser.parse_args(argv)
    if args.demo and (args.entries or args.quotes):
        parser.error("--demo cannot be combined with ledgers")
    try:
        if args.demo:
            from atlas.options.replay_demo import demo_history
            entries, quotes = demo_history()
            label = "Fictional XYZ quote paths dated 2026-07-14"
        else:
            if not args.entries or not args.quotes:
                parser.error("provide --demo or --entries and --quotes")
            entries = read_jsonl(args.entries)
            quotes = [q for p in args.quotes for q in read_jsonl(p)]
            label = args.label
        report = build_report(entries, quotes, label=label, fictional=args.demo,
                              fee_per_contract=args.fee_per_contract)
        write_report(report, args.output)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error("Replay rejected: " + str(exc))
    print("Created offline replay report:", args.output / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
