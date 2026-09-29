"""Invented XYZ paths on an archived date. These are not market data or performance."""
from datetime import datetime
from zoneinfo import ZoneInfo
from atlas.options.shadow import build_entry_record, build_quote_record


def demo_history():
    day, expiry = "2026-07-14", "2026-07-15"
    midnight = datetime(2026, 7, 14, tzinfo=ZoneInfo("America/New_York")).timestamp()
    entries, quotes = [], []
    for pid, strike, bid, ask, target, mu, marks in [
        ("winner", 98, .91, .95, .04, 8, [(660, 2.30, 2.34), (800, 2.05, 2.09), (950, 2.30, 2.34)]),
        ("steady", 100, 1.95, 2.05, .01, 4, [(620, 1.92, 2.02), (660, 1.95, 2.05), (800, 1.90, 2.00), (950, 1.95, 2.05)]),
        ("still-open", 100, 1.95, 2.05, .01, 4, [(620, 1.92, 2.02)]),
        ("missing-context", 100, 1.95, 2.05, .01, 4, [(660, 1.95, 2.05)]),
    ]:
        occ = f"XYZ260715C{strike * 1000:08d}"
        entry = build_entry_record(ts=midnight+590*60, day=day, entry_minute=590,
            position_id=pid, lanes=["index_trend"], config_hash="fictional-demo",
            signal={"lane":"index_trend","underlying":"XYZ","direction":"call",
                    "target_move":target,"mu_thesis":mu,"p_thesis":.6,
                    "horizon_T":1/252,"expires_minute":700,"notes":{}},
            pick={"occ":occ,"underlying":"XYZ","opt_type":"call","strike":strike,
                  "expiry":expiry,"S":100,"theta_day":-.05},
            runner_up_occs=[], nbbo={"bid":bid,"ask":ask}, risk_flags=["fictional_data"])
        entries.append(entry)
        for minute, qb, qa in marks:
            ext = {"solved_iv":.3,"iv_trend_per_hour":0,"mu_hat":None,"mu_t_stat":0,
                   "thesis_valid":True,"opposing_defense":False,"defense_zone_score":0,
                   "minutes_to_next_print":None,"minutes_since_print":None,
                   "planned_exit_minute":None,"named_catalyst_tomorrow":False,
                   "is_friday":False,"after_hours":False,"theta_share_breaches":0,
                   "minute":minute}
            quotes.append(build_quote_record(ts=midnight+minute*60, occ=occ, bid=qb, ask=qa,
                S=100, position_id=pid, ext=ext if pid!="missing-context" else None))
    return entries, quotes
