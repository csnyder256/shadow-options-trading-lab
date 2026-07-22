"""pre_fomc_drift_call - Lucca-Moench pre-FOMC announcement drift as a long ATM SPY call.

AUTHORITY: docs/strategies/briefs/pre_fomc_drift_call.md (verified CORRECTED, second pass
CONFIRMED, 2026-07-19). Provenance: Lucca & Moench, FRBNY Staff Report 512 / JF 2015 (the
drift); Kurov, Wolfe & Gilbert, FRL 2021 (post-2015 attenuation). Every constant below cites
its brief §8 row.

LOUD (brief §2): the SOURCE trades the delta-one index (SPX spot / E-mini futures) - it is
NOT an options strategy in the literature. The long ATM call is entirely OUR options-only
adaptation (rows 10-12 ADAPTED, no published authority), and the pre-FOMC window is
documented LOW-realized-vol - the worst environment for paying ~24h of theta. This shadow
exists to measure exactly that adaptation cost against any post-2019 drift revival.

Doctrine (brief §3/§4 - overrides ALL platform exit doctrine for this cohort):
  * Signal = the scheduled FOMC statement release itself (row 1); entry is UNCONDITIONAL on
    every scheduled decision - no VIX gate, no MA8 gate (rows 16/17 are associations only).
    ctx.events (atlas/options/events.py EconEvent) provides kind="fomc", label="decision",
    ts_et=the 14:00 ET decision instant; the 14:30 presser row is NOT the signal.
  * Entry: window START = release - 24h15m (row 2 SOURCE-VERBATIM; = 13:45 ET on T-1 for the
    modern 14:00 ET release, row 3), accepted for entry_window_min minutes after that start
    (ADAPTED scan-cadence tolerance - never enters BEFORE the published window opens). Long
    1 ATM call: nearest listed strike to spot, equidistant tie -> lower strike (row 11
    ADAPTED, delta ~0.50). Expiry: nearest listed strictly AFTER the decision day inside
    META.dte_range (row 12 ADAPTED - the exit must always be a sale, never settlement).
    Re-anchoring is automatic: both clocks derive from the event's ts_et, so a non-14:00
    release shifts the whole window per §3.
  * Exit (the ONLY exit besides the global expiry backstop): HARD time exit at release - 15
    min (row 4 SOURCE-VERBATIM "selling fifteen minutes before the announcement" = 13:45 ET
    decision day). NEVER hold through the release; a late mark still exits on sight (graded
    a process failure per §10, but never held). No profit target (row 13), no stop (row 14,
    held through the -2.9% window), no roll (row 15). Purely clock-based: manage() reads no
    quotes, so a missing book can never postpone the gate. Anchor resolution order: decision
    ts stamped into the entry signal notes (survives restart via pos.notes) -> live
    ctx.events decision -> a held-full-window failsafe (entry_lead - exit_lead = 24h,
    derived from rows 2+4) covering §7's "release-time drift" failure mode.
  * Grading basis DEBIT: long single-leg premium, max loss = debit paid (brief §10).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..strategy import (EventPolicy, ExitAction, GradingBasis, ProposedCombo, Strategy,
                        StrategyMeta)

ET = ZoneInfo("America/New_York")


def _as_et(dt: datetime) -> datetime:
    """Naive datetimes are taken as ET (platform market-local convention); aware converted."""
    return dt.replace(tzinfo=ET) if dt.tzinfo is None else dt.astimezone(ET)


def _fomc_decisions(events) -> list[datetime]:
    """Sorted ET instants of scheduled FOMC DECISION releases in an events list (duck-typed
    EconEvent: kind == "fomc", label == "decision"). The presser row is never the signal."""
    out = []
    for e in events or []:
        if str(getattr(e, "kind", "")).lower() != "fomc":
            continue
        if str(getattr(e, "label", "")).lower() != "decision":
            continue
        ts = getattr(e, "ts_et", None)
        if isinstance(ts, datetime):
            out.append(_as_et(ts))
    return sorted(out)


def _parse_iso_et(raw) -> datetime | None:
    if not raw:
        return None
    try:
        return _as_et(datetime.fromisoformat(str(raw)))
    except ValueError:
        return None


@dataclass(frozen=True)
class PreFomcParams:
    """Tunables (the pre-registered tweak neighborhood; everything else is doctrine).
    entry_lead_min: brief row 2 SOURCE-VERBATIM - window start = announcement - 24h15m
    (1455 min); row 3 derives 13:45 ET on T-1 for the modern 14:00 ET release.
    entry_window_min: ADAPTED - minutes AFTER the derived start in which entry is accepted
    (scan-cadence tolerance; the source window is a point instant, and we never enter early).
    exit_lead_min: brief row 4 SOURCE-VERBATIM - "selling fifteen minutes before the
    announcement"; never hold through the release.
    strike_rule: brief row 11 ADAPTED - nearest listed strike to spot at entry (ATM,
    delta ~0.50); UNKNOWN in source (no options traded there)."""
    entry_lead_min: int = 1455            # release - 24h15m (row 2)
    entry_window_min: int = 10            # accept window after the derived start (ADAPTED)
    exit_lead_min: int = 15               # release - 15 min hard exit (row 4)
    strike_rule: str = "nearest_to_spot"  # row 11


class PreFomcDriftCall(Strategy):
    META = StrategyMeta(
        strategy_id="pre_fomc_drift_call", version=1,
        name="Lucca-Moench pre-FOMC drift, long ATM SPY call, hard pre-release time exit",
        universe=("SPY",),                            # row 9: SPY primary; singles excluded
        dte_range=(1, 10),                            # row 12 practical band + listing tolerance
        max_concurrent=1,                             # one ~24h window at a time (§5: one switch)
        event_policy=EventPolicy.REQUIRES_EVENT,      # row 1: the scheduled decision IS the signal
        grading_basis=GradingBasis.DEBIT,             # §10: long premium, max loss = debit
        defining_mechanism="drift_capture",
        settle_at_expiry=False,                       # §4: exit is always a sale, never settlement
        scan_interval_s=60.0, mark_interval_s=120.0,  # clock-critical window; §10 mark cadence
        expected_fires_per_20_sessions=1.0)           # 8 scheduled meetings/yr (§10 cadence)
    params = PreFomcParams()

    # -- entry helpers -----------------------------------------------------
    def _expiry_after_decision(self, ctx, sym: str, today: date,
                               decision_day: date) -> str | None:
        """Nearest listed expiry strictly AFTER the decision day inside META.dte_range
        (row 12); None = no qualifying listing."""
        lo, hi = self.META.dte_range
        best, best_dte = None, None
        for e in ctx.hub.expirations(sym):
            try:
                ed = date.fromisoformat(str(e))
            except ValueError:
                continue
            dte = (ed - today).days
            if ed <= decision_day or not (lo <= dte <= hi):
                continue
            if best_dte is None or dte < best_dte:
                best, best_dte = str(e), dte
        return best

    # -- scan (rows 1-3, 7, 9-12) ------------------------------------------
    def scan(self, ctx) -> list:
        p = self.params
        if p.strike_rule != "nearest_to_spot":
            raise ValueError(f"pre_fomc_drift_call: unknown strike_rule {p.strike_rule!r}")
        if ctx.open_positions:
            return []                                 # one window position at a time
        now_et = _as_et(ctx.dt_et)
        decision = next((t for t in _fomc_decisions(ctx.events) if t > now_et), None)
        if decision is None:
            return []                                 # REQUIRES_EVENT: no decision, no trade
        entry_start = decision - timedelta(minutes=p.entry_lead_min)
        if not (entry_start <= now_et < entry_start + timedelta(minutes=p.entry_window_min)):
            return []                                 # rows 2/3: [release-24h15m, +tolerance) only
        sym = self.META.universe[0]
        S_ref = ctx.hub.ref_price(sym)
        if S_ref <= 0:
            if ctx.journal:
                ctx.journal({"event": "prefomc_no_ref", "symbol": sym,
                             "day": now_et.date().isoformat()})
            return []
        today = now_et.date()
        exp = self._expiry_after_decision(ctx, sym, today, decision.date())
        if exp is None:
            if ctx.journal:
                ctx.journal({"event": "prefomc_no_expiry", "symbol": sym,
                             "decision_day": decision.date().isoformat()})
            return []
        rows = ctx.hub.chain(sym, exp)
        calls = [r for r in rows if r.option_type == "call"
                 and (r.bid or 0) > 0 and (r.ask or 0) > 0]
        if not calls:
            if ctx.journal:
                ctx.journal({"event": "prefomc_no_strike", "symbol": sym, "expiry": exp,
                             "S_ref": round(S_ref, 4)})
            return []
        row = min(calls, key=lambda r: (abs(r.strike - S_ref), r.strike))  # row 11: ATM, tie->lower
        mid = (row.bid + row.ask) / 2.0
        dte = max(1, (date.fromisoformat(exp) - today).days)
        g = ctx.hub.row_greeks(opt_type="call", strike=row.strike, S=S_ref, mid=mid,
                               dte_days=dte) or {}
        decision_iso = decision.isoformat()
        return [ProposedCombo(
            kind="long_call_pre_fomc", underlying=sym,
            legs=[{"occ": row.symbol, "underlying": sym, "opt_type": "call",
                   "strike": row.strike, "expiry": exp, "side": +1, "qty": 1,
                   "nbbo": {"bid": row.bid, "ask": row.ask},
                   "iv": g.get("iv", 0.0), "delta": g.get("delta", 0.0),
                   "gamma": g.get("gamma", 0.0), "vega": g.get("vega", 0.0),
                   "theta_day": g.get("theta_day", 0.0)}],
            signal={"S_ref": round(S_ref, 4), "strike": row.strike, "expiry": exp,
                    "dte_days": dte, "debit_ask": row.ask,
                    "debit_pct_of_S": round(100.0 * row.ask / S_ref, 3),
                    "decision_ts_et": decision_iso,
                    "entry_window_start_et": entry_start.isoformat(),
                    "minutes_to_release": int((decision - now_et).total_seconds() // 60),
                    # notes survive into pos.notes (combo_from_entry) - the exit anchor.
                    "notes": {"decision_ts_et": decision_iso,
                              "decision_day": decision.date().isoformat()}})]

    # -- manage (row 4; rows 13-15 absent by doctrine) ---------------------
    def manage(self, pos, ctx):
        """HARD time exit at release - exit_lead_min; the ONLY strategy exit. Purely
        clock-based - no quotes read, so nothing can postpone the gate; the runner supplies
        the closing book. A mark after the release still exits immediately (late, flagged)."""
        p = self.params
        now_et = _as_et(ctx.dt_et)
        decision = _parse_iso_et((getattr(pos, "notes", None) or {}).get("decision_ts_et"))
        anchor = "entry_notes"
        if decision is None:                          # notes lost: fall back to the live calendar
            decisions = _fomc_decisions(ctx.events)
            decision = decisions[0] if decisions else None
            anchor = "ctx_events"
        if decision is not None:
            gate = decision - timedelta(minutes=p.exit_lead_min)
            if now_et >= gate:
                return ExitAction(
                    action="close", rule="time_exit_pre_release",
                    state={"anchor": anchor, "decision_ts_et": decision.isoformat(),
                           "gate_et": gate.isoformat(),
                           "late_past_release": bool(now_et >= decision)})
        # Failsafe (§7 release-time drift): both anchors gone -> never exceed the full
        # published window length, entry_lead - exit_lead = 24h (derived from rows 2+4).
        max_hold_min = p.entry_lead_min - p.exit_lead_min
        held_min = (float(ctx.now_ts) - float(pos.entry_ts)) / 60.0
        if held_min >= max_hold_min:
            return ExitAction(action="close", rule="time_exit_failsafe",
                              state={"anchor": "held_full_window",
                                     "held_min": round(held_min, 1),
                                     "max_hold_min": max_hold_min})
        return None
