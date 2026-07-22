"""PAIRED decide_exit REPLAY (opts-rework-exit-core-v1 §replay) - pure functions that re-run a
FULL exit engine (v2 or the frozen v1 baseline in exit_engine_legacy.py) over a position's
stored schema-2 quote-path rows and report where each variant would have sold. This is the
engine-level companion to the overnight lab's premium-threshold exit_grid_replay (stage 1,
run_overnight_lab.py) - that stage stays; this one answers the question the grid cannot:
"would the OTHER engine / OTHER calibration have exited this exact stored path differently?"

PURITY CONTRACT: no IO, no clock, no network - callers pass entry records and quote rows
already read from the ledgers. The engines themselves are passed IN (module objects), never
imported here, so this module stays inert: importing it can never wake the legacy engine.

REPLAY FIDELITY (must mirror scripts/run_options_shadow.py _reval_positions per mark):
  - the position rebuilds from the entry record via shadow.position_from_entry (peak_mid /
    peak_bid start at entry mid / entry bid, exactly like a fresh live position);
  - peak_mid/peak_bid update BEFORE the decision, from the row's own NBBO;
  - theta_share_breaches carries FROM each decision into the next PositionView (rule (g)'s
    two-cycle memory); the legacy trail latch carries the same way when the target engine's
    PositionView has a `trailing` field (introspected - v1 and v2 have different views);
  - engine-input context (solved_iv, iv trend, mu_hat/t_stat, thesis_valid, print/planned
    clocks, after_hours, minute) comes from the row's `ext` dict - the snapshot the runner
    persisted at decision time (shadow.build_quote_record schema 2). Rows WITHOUT ext cannot
    feed a decide_exit replay (the engine inputs were never stored): they are counted and
    skipped; a position with zero ext rows is unreplayable -> None.
  - an engine exception on a row = HOLD with unchanged carried state (the runner journals
    exit_engine_error and keeps the position; the replay counts it instead).

Fill convention: sell at the SELL row's bid vs the entry record's WORST fill (buy at ask) - 
the three-ledger worst column (shadow.entry_fills/exit_fills), same as the grid stage.
"""

from __future__ import annotations

from dataclasses import fields as dc_fields
from datetime import date, datetime, timedelta

from atlas.options.shadow import exit_fills, position_from_entry

CONTRACT_MULT = 100.0


def _now_et(entry_day: date, entry_ts: float, entry_minute: int, row_ts: float,
            minute: int) -> datetime:
    """Naive ET datetime for a stored row: the entry record's day + the row's ext minute.
    Overnight-grant rows live in LATER day files: the whole-day offset is recovered from the
    ts_epoch delta minus the intraday minute delta (both were produced from the same clock by
    the runner, so the remainder is days*86400 +/- one DST hour - round() absorbs it). No
    timezone import needed; the replay stays pure and deterministic."""
    day_off = 0
    if row_ts > 0 and entry_ts > 0:
        day_off = max(0, round((row_ts - entry_ts - (minute - entry_minute) * 60.0) / 86400.0))
    base = datetime(entry_day.year, entry_day.month, entry_day.day)
    return base + timedelta(days=day_off, minutes=minute)


def replay_decide_exit(entry_rec: dict, quote_rows: list, *, engine, params,
                       day_close_min: int = 960) -> dict | None:
    """Walk one position's stored quote rows through `engine.decide_exit(...)` chronologically
    and sell at the FIRST SELL decision. `engine` is an exit-engine MODULE (atlas.options.
    exit_engine or .exit_engine_legacy); `params` its matching ExitParams. `day_close_min` is
    used ONLY as the after-hours fallback inference for a row whose ext lacks the flag (the
    runner always writes it; tolerance is for hand-built fixtures).

    Returns None when the entry record is malformed or NO ext-carrying rows exist for the
    position (nothing decide_exit-replayable). Otherwise a dict:
      exit_minute/rule/sell_bid/net_worst - the first SELL (rule "unexited" + None fills when
                                             the path ends without one, same as a still-open
                                             live position)
      marks_replayed/skipped_no_ext/engine_errors/peak_mid/peak_bid - path accounting.
    """
    pos = position_from_entry(entry_rec)
    if pos is None:
        return None
    rows = [r for r in quote_rows
            if str(r.get("position_id") or "") == pos.position_id]
    usable = [r for r in rows if isinstance(r.get("ext"), dict)]
    skipped_no_ext = len(rows) - len(usable)
    if not usable:
        return None
    usable = sorted(usable, key=lambda r: float(r.get("ts_epoch") or 0.0))

    try:
        entry_day = date.fromisoformat(pos.entry_day)
    except ValueError:
        return None
    # engine-shape introspection (v1 vs v2 PositionView): `mu_hat` marks the v2 live-trajectory
    # fields + d2* cost-basis inputs; `trailing` marks the v1 runner-persisted trail latch
    field_names = {f.name for f in dc_fields(engine.PositionView)}
    has_v2_fields = "mu_hat" in field_names
    has_v3_fields = "p_thesis" in field_names                # audit 2026-07-16 exit-engine v3
    has_trail_latch = "trailing" in field_names
    sell = getattr(engine, "SELL", "SELL")
    contracts = int(entry_rec.get("contracts") or 1)

    peak_mid, peak_bid = pos.peak_mid, pos.peak_bid          # entry mid / entry bid
    breaches = int(pos.theta_share_breaches)
    h_since = pos.h_breach_since_min                         # v3 persistence clocks, carried
    i_since = pos.i_breach_since_min                         # like breaches (variant-evolved,
    trailing = False                                         # never read back from ext)
    marks_replayed = 0
    engine_errors = 0

    for r in usable:
        ext = r["ext"]
        bid = max(0.0, float(r.get("bid") or 0.0))
        ask = max(0.0, float(r.get("ask") or 0.0))
        mid = (bid + ask) / 2.0 if ask > 0 else bid          # one-sided books price (RUNNER-10)
        minute = int(ext.get("minute") or 0)
        now_et = _now_et(entry_day, pos.entry_ts, pos.entry_minute,
                         float(r.get("ts_epoch") or 0.0), minute)
        # peaks update BEFORE the decision - exactly the runner's order, so the d2* backstop
        # (and the v1 trail giveback) see the same high-water the live engine saw
        peak_mid = max(peak_mid, mid)
        if bid > 0:
            peak_bid = max(peak_bid, bid)
        siv = float(ext.get("solved_iv") or 0.0)
        kw = dict(
            occ=pos.occ, underlying=pos.underlying, opt_type=pos.opt_type,
            strike=pos.strike, expiry=pos.expiry, entry_mid=pos.entry_mid,
            peak_mid=peak_mid, lane=",".join(pos.lanes),
            target_underlying=pos.target_underlying, mu_thesis=pos.mu_thesis,
            thesis_valid=bool(ext.get("thesis_valid", True)),
            entry_ts_min=pos.entry_minute,
            S=float(r.get("S") or 0.0), bid=bid, ask=ask,
            solved_iv=siv if siv > 0 else 1e-4,              # runner's degraded-IV sentinel
            iv_trend_per_hour=float(ext.get("iv_trend_per_hour") or 0.0),
            is_event_straddle=False,                         # runner hardcodes both (no lane 4 yet)
            event_tminus1_close=False,
            minutes_since_print=(int(ext["minutes_since_print"])
                                 if ext.get("minutes_since_print") is not None else None),
            minutes_to_next_print=(int(ext["minutes_to_next_print"])
                                   if ext.get("minutes_to_next_print") is not None else None),
            planned_exit_minute=(int(ext["planned_exit_minute"])
                                 if ext.get("planned_exit_minute") is not None else None),
            named_catalyst_tomorrow=bool(ext.get("named_catalyst_tomorrow", False)),
            is_friday=bool(ext.get("is_friday", False)),
            theta_share_breaches=breaches,
            after_hours=bool(ext.get("after_hours", minute >= int(day_close_min))))
        if has_v2_fields:
            mu_hat = ext.get("mu_hat")
            kw.update(entry_ask=pos.entry_ask, peak_bid=peak_bid,
                      mu_hat=float(mu_hat) if mu_hat is not None else None,
                      mu_t_stat=float(ext.get("mu_t_stat") or 0.0),
                      opposing_defense=bool(ext.get("opposing_defense", False)),
                      defense_zone_score=float(ext.get("defense_zone_score") or 0.0))
        if has_v3_fields:
            kw.update(p_thesis=float(ext.get("p_thesis", pos.p_thesis or 0.5)),
                      horizon_T=float(ext.get("horizon_T", pos.horizon_T or 0.0)),
                      evidence_stale=bool(ext.get("evidence_stale", False)),
                      h_breach_since_min=h_since, i_breach_since_min=i_since)
        if has_trail_latch:
            kw["trailing"] = trailing
        marks_replayed += 1
        try:
            decision = engine.decide_exit(engine.PositionView(**kw), now_et, params)
        except Exception:  # noqa: BLE001 - the runner journals + HOLDs; the replay counts
            engine_errors += 1
            continue
        breaches = int(decision.theta_share_breaches)
        h_since = getattr(decision, "h_breach_since_min", h_since)
        i_since = getattr(decision, "i_breach_since_min", i_since)
        trailing = bool(getattr(decision, "trailing", trailing))
        if decision.action == sell:
            net = (exit_fills(bid, ask)["worst"] - pos.entry_fills["worst"]) \
                * CONTRACT_MULT * contracts
            return {"exit_minute": minute, "rule": decision.rule,
                    "sell_bid": round(bid, 4), "net_worst": round(net, 2),
                    "marks_replayed": marks_replayed, "skipped_no_ext": skipped_no_ext,
                    "engine_errors": engine_errors,
                    "peak_mid": round(peak_mid, 4), "peak_bid": round(peak_bid, 4)}
    return {"exit_minute": None, "rule": "unexited", "sell_bid": None, "net_worst": None,
            "marks_replayed": marks_replayed, "skipped_no_ext": skipped_no_ext,
            "engine_errors": engine_errors,
            "peak_mid": round(peak_mid, 4), "peak_bid": round(peak_bid, 4)}


def exit_engine_ab(entries: list, quotes_by_pid: dict, variants: list) -> dict:
    """Run EVERY entry through EVERY (name, engine_module, params) variant on its stored quote
    path. PAIRED by construction: all variants replay the identical rows, and a position that
    is unreplayable (malformed entry / zero ext rows) is excluded from ALL variants, so the
    per-variant aggregates stay comparable. Deterministic: entries sort by (day, position_id),
    variants keep their given (pre-registered) order, rule_mix keys sort.

    Returns {"variants": {name: {n, net_worst_sum, rule_mix, unexited}}, "per_position": [...],
    ...counts}. net_worst_sum/rule_mix cover SELL-decided replays only; "unexited" counts paths
    that ended still-open (their dollars are not yet realizable - same as a live open position,
    they contribute n but no P&L)."""
    ents = [e for e in entries
            if e.get("event", "shadow_entry") == "shadow_entry" and not e.get("merged_into")]
    ents.sort(key=lambda e: (str(e.get("day") or ""), str(e.get("position_id") or "")))
    agg = {name: {"n": 0, "net_worst_sum": 0.0, "rule_mix": {}, "unexited": 0}
           for name, _engine, _params in variants}
    per_position = []
    n_unreplayable = 0
    for e in ents:
        pid = str(e.get("position_id") or "")
        rows = quotes_by_pid.get(pid) or []
        row_out = {"position_id": pid}
        replayed = False
        for name, eng, prm in variants:
            res = replay_decide_exit(e, rows, engine=eng, params=prm)
            if res is None:
                continue                     # variant-independent: entry/rows decide, not params
            replayed = True
            a = agg[name]
            a["n"] += 1
            if res["rule"] == "unexited":
                a["unexited"] += 1
            else:
                a["net_worst_sum"] += float(res["net_worst"])
                a["rule_mix"][res["rule"]] = a["rule_mix"].get(res["rule"], 0) + 1
            row_out[name] = {"rule": res["rule"], "exit_minute": res["exit_minute"],
                             "net_worst": res["net_worst"]}
        if replayed:
            per_position.append(row_out)
        else:
            n_unreplayable += 1
    for a in agg.values():
        a["net_worst_sum"] = round(a["net_worst_sum"], 2)
        a["rule_mix"] = {k: a["rule_mix"][k] for k in sorted(a["rule_mix"])}
    n_ext_rows = sum(1 for rows in quotes_by_pid.values() for r in rows
                     if isinstance(r.get("ext"), dict))
    out = {"variants": agg, "per_position": per_position, "n_entries": len(ents),
           "n_unreplayable_no_ext_or_malformed": n_unreplayable,
           "n_ext_rows_total": n_ext_rows}
    if n_ext_rows == 0:
        # day-1 state: schema-2 ext rows only exist from the first post-rework live session - 
        # an empty A/B is expected tonight, not a defect
        out["note"] = ("no ext-carrying (schema-2) quote rows stored yet; the decide_exit A/B "
                       "starts accumulating with the first live session after "
                       "opts-rework-exit-core-v1 shipped")
    return out
