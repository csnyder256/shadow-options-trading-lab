"""LEGACY EXIT ENGINE - FROZEN 2026-07-10 (git tag pre-pivot-2026-07-10) as the paired-replay
A/B BASELINE for opts-rework-exit-core-v1. DO NOT EDIT and DO NOT WIRE INTO THE RUNNER: this is
the engine that contained the +100% forced take (an unregistered author interpolation the owner
ordered removed - its rule-16/21 attributions below are WRONG; see docs/OWNER_RULES_RETRACTED.md
 - the rules file itself was retracted and deleted 2026-07-16 by owner directive) and the
trail latch that bypassed the EV rules. It exists so the overnight lab can replay old-vs-new on
identical stored quote paths. For the original v1-with-stop flavor, replay with
ExitParams(stop_frac=-0.50); this freeze carries stop_frac=None (disabled 2026-07-10,
opts-tweak-disable-premium-stop-v1) and take_frac=1.0 (the disputed forced take, intact here
BY DESIGN for measurement).

Original (superseded) header follows:
EXIT ENGINE (O2) - the owner's 26-rule sell framework as a pure, first-match decision loop.
Zero anchoring by construction: the entry price appears in exactly TWO places (the -50% stop and
the winner-protection backstop) and NOWHERE in the hold/sell EV comparison.

OWNER'S RULES, VERBATIM (2026-07-09), each mapped to its implementation:
 1. "Underlying stock's current estimated trajectory"                -> mu_thesis input (lane-supplied), used in P_target + EV_hold
 2. "today the contract is worth X at Y underlying, tomorrow the underlying will need to move N%
    for the contract to reach X value again"                         -> regain_pct state + rule (i)
 3. "Always sell a 0DTE contract same-day, but do not force an early exit solely because of the
    clock"                                                           -> rule (a) is the only EXPIRY-clock exit (15:00; delta>=0.80 extends to 15:30); the
                                                                        15:45 overnight checkpoint and the print-window flat are POLICY clocks (survival rules), not P&L clocks
 4. "Estimate the probability that the underlying reaches our target before expiration rather
    than focusing on the option's unrealized P/L"                    -> P_target (exact first-passage, dual-mu) in rules (d)/(g); unrealized P&L absent from (h)
 5. "Continuously compare the expected remaining upside to the expected remaining theta decay"    -> EV_hold vs EV_sell (h) + theta_share (g)
 6. "Account for upcoming volatility events (earnings, CPI, FOMC...)"-> event states + rules (e)/(f) + the print-window flat (never hold long premium
                                                                        through a print: minutes_to_next_print <= lead -> SELL, rule "print_window_flat"); crush enters EV_hold's iv_change
 7. "Monitor whether implied volatility is rising or falling independently of the stock price"    -> iv_trend_per_hour state -> EV_hold iv_change
 8. "Evaluate delta to estimate how much additional stock movement is required"                   -> delta state + regain_pct
 9. "Monitor gamma as expiration approaches"                         -> gamma state; 0DTE theta multiplier steepens (g) into the afternoon
10. "Treat every additional day held as a new decision"              -> the 09:35 daily re-decision runs the FULL loop + rule (i); nothing is grandfathered
11. "Base exit decisions on updated probabilities using the latest available information"         -> every cycle recomputes all states from fresh marks
12. "Consider whether the original trade thesis is still valid or has already played out"         -> thesis_valid -> rule (b); played-out = target touched -> P_target re-aimed or (d)
13. "Differentiate between 'the stock can still go higher' and 'the option is still the best way
    to express that view'"                                           -> vehicle_mismatch flag: theta_share>0.5 while P_target(mu_thesis)>=0.30 = stock view alive, option dying -> (g) exits, flag logged
14. "Estimate expected value from holding versus realizing profits immediately"                   -> rule (h)
15. "Potentially prefer selling when the remaining expected gain is small relative to the
    remaining downside risk"                                         -> rule (h) (EV_sell wins) + rule (d)
16. "the highest percentage gains often occur before the final portion of a move"                 -> rule (d): default TAKE at +100% (trail only on strong P_target)
17. "Avoid holding solely because the contract was worth more earlier in the day"                 -> no peak anchor in (h)/(g); peak is used ONLY to protect gains (d2), never to wait for recovery
18. "Ignore anchoring to previous highs; the market owes us nothing"  -> rule (i)'s regain reference is TODAY'S value, never the high-water mark
19. "Never hold simply to avoid realizing a smaller profit than expected"                          -> rule (h) fires regardless of profit size
20. "If confidence in the underlying decreases, reduce exposure even if the option remains
    profitable"                                                      -> lane confidence downgrade sets thesis_valid=False -> rule (b) sells winners too
21. "If confidence materially increases while time decay remains manageable, allow more room"     -> rule (d) trail arm: P_target(mu=0)>0.35 converts TAKE into a 25%-off-peak trail;
                                                                        the trail LATCHES (PositionView.trailing, runner-persisted) so a sag below +100% never un-arms it
22. "Scale out of winners when appropriate"                          -> variant column (default OFF per evidence - partials measured in paired replay, never assumed)
23. "Avoid letting a profitable trade become a losing trade due to indecision"                    -> rule (d2): once peak >= +50%, a give-back to entry SELLS (breakeven backstop)
24. "Recognize when time decay has become the dominant force over directional exposure"           -> theta_share > 0.5 (g)
25. "Recalculate the required underlying move after every meaningful change in price or IV"        -> event-triggered re-runs (>0.5xATR5m move / IV jump >2pt) + regain_pct each cycle
26. "options are wasting assets; every minute held should be justified by a positive expected
    return"                                                          -> rule (h) is the default-deny: hold only while EV_hold > EV_sell

OVERNIGHT POLICY (owner's fork answer 2026-07-09): the EVIDENCE rule grades - 0-2 DTE always closed
same-day (15:45), DTE>=3 may ride only with delta>=0.7 + a named next-morning catalyst + not
Friday. the owner's unrestricted-overnight instinct is NOT silently dropped: when the evidence rule
forces a sell that the unrestricted variant would have held, the decision carries
variant_would_hold=True and the nightly paired replay grades both arms head-to-head.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from atlas.options import math as om
from atlas.options.vendor.blackscholes import greeks
from atlas.options.vendor.models import OptionType

HOLD, SELL = "HOLD", "SELL"


@dataclass(frozen=True)
class ExitParams:
    zero_dte_sell_min: int = 15 * 60                 # rule (a): close - 60
    zero_dte_deep_itm_ext_min: int = 15 * 60 + 30    # delta >= 0.80 extension: close - 30
    zero_dte_deep_itm_delta: float = 0.80
    print_flat_lead_min: int = 10                    # never hold through a print: flat this many min before
    # None = rule (c) INERT (owner, 2026-07-10; sweep_ledger opts-tweak-disable-premium-stop-v1):
    # never exit just because the premium is lower now - losses exit via thesis (b), theta (g),
    # the no-anchoring EV stop (h), or the clocks. Set a fraction to re-arm the price stop; the
    # old -0.50 behavior stays measurable as the opts-variant-evidence-exits-v1 replay column.
    stop_frac: float | None = None                   # rule (c)
    take_frac: float = 1.00                          # rule (d)
    trail_p_target_min: float = 0.35
    trail_giveback: float = 0.25                     # 25% off peak once trailing
    backstop_arm_frac: float = 0.50                  # rule (d2): peak >= +50% arms breakeven
    post_print_decision_min: int = 15                # rule (f)
    theta_share_max: float = 0.50                    # rule (g)
    theta_share_cycles: int = 2
    p_target_floor: float = 0.30
    regain_mult: float = 1.5                         # rule (i): vs daily expected move
    eod_flat_min: int = 15 * 60 + 45                 # evidence overnight checkpoint: close - 15
    planned_exit_cap_min: int = 15 * 60 + 59         # planned same-day exits may run to close - 1
    session_close_min: int = 16 * 60                 # today's RTH close (960 normal, 780 half day)
    late_close_flat_min: int = 16 * 60 + 10          # after-hours hard flat: close + 10
    overnight_min_dte: int = 3
    overnight_min_delta: float = 0.70
    daily_recheck_min: int = 9 * 60 + 35             # absolute - 09:35 exists on half days too
    r: float = 0.04
    q: float = 0.0
    n_grid: int = 11

    @classmethod
    def for_close(cls, close_min: int = 16 * 60) -> "ExitParams":
        """Per-day params with every close-anchored clock shifted by (close_min - 960).
        for_close(960) == ExitParams() field-for-field - the byte-identity pin for normal days;
        a 13:00 half day derives 12:00/12:30/12:45/12:59 clocks and a 13:10 hard flat."""
        d = int(close_min) - 16 * 60
        return cls(zero_dte_sell_min=15 * 60 + d,
                   zero_dte_deep_itm_ext_min=15 * 60 + 30 + d,
                   eod_flat_min=15 * 60 + 45 + d,
                   planned_exit_cap_min=15 * 60 + 59 + d,
                   session_close_min=int(close_min),
                   late_close_flat_min=int(close_min) + 10)


@dataclass
class PositionView:
    """Everything the engine needs about one open shadow position + the fresh mark."""
    occ: str
    underlying: str
    opt_type: str                     # "call" | "put"
    strike: float
    expiry: date
    entry_mid: float                  # measurement anchor for stop/take fracs (fills live in ledgers)
    peak_mid: float                   # high-water of the mid since entry (gain protection only)
    lane: str
    target_underlying: float          # H - the thesis target price
    mu_thesis: float                  # annualized drift implied by the lane's thesis
    thesis_valid: bool
    entry_ts_min: int                 # minutes-of-day at entry
    # fresh mark:
    S: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    solved_iv: float = 0.0
    iv_trend_per_hour: float = 0.0    # OLS slope of solved IV, trailing 45 min
    # event context:
    is_event_straddle: bool = False
    minutes_since_print: int | None = None
    minutes_to_next_print: int | None = None  # minutes until TODAY's next macro release (None = none)
    planned_exit_minute: int | None = None    # lane-designed same-day exit (e.g. last30/macro 15:55)
    event_tminus1_close: bool = False # T-1 close window for an event straddle
    named_catalyst_tomorrow: bool = False
    is_friday: bool = False
    theta_share_breaches: int = 0     # consecutive cycles with theta_share > max (carried state)
    trailing: bool = False            # rule (d) trail latch (carried state, runner-persisted)
    after_hours: bool = False         # equity close passed; S frozen; option NBBO still live


@dataclass(frozen=True)
class ExitDecision:
    action: str                       # HOLD | SELL
    rule: str                         # which line fired (a..j, d2, overnight, print_window_flat)
    state: dict = field(default_factory=dict)
    variant_would_hold: bool = False  # the owner's unrestricted-overnight arm diverges here
    theta_share_breaches: int = 0     # carry-forward for the caller
    trailing: bool = False            # trail-latch carry-forward for the caller


def decide_exit(pv: PositionView, now_et: datetime, p: ExitParams = ExitParams()) -> ExitDecision:
    """One pure decision. First match wins; every SELL names its rule; HOLD logs the full state."""
    minute = now_et.hour * 60 + now_et.minute
    dte = (pv.expiry - now_et.date()).days
    mid = (pv.bid + pv.ask) / 2.0 if (pv.bid > 0 and pv.ask > 0) else max(pv.bid, 0.0)
    ot = OptionType.CALL if pv.opt_type == "call" else OptionType.PUT
    T = om.trading_T(now_et, pv.expiry, close_minute=p.session_close_min)
    iv = max(pv.solved_iv, 1e-4)
    g = greeks(pv.S, pv.strike, p.r, p.q, iv, T, ot) if pv.S > 0 else None
    adelta = abs(g.delta) if g else 0.0
    theta_day = (g.theta if g else 0.0) * (om.zero_dte_theta_multiplier(minute) if dte == 0 else 1.0)

    p_tgt_0 = om.p_touch(pv.S, pv.target_underlying, iv, T, mu=0.0) if pv.S > 0 else 0.0
    p_tgt_thesis = om.p_touch(pv.S, pv.target_underlying, iv, T, mu=pv.mu_thesis) if pv.S > 0 else 0.0
    tshare = om.theta_share(theta_day, adelta, pv.S, iv, dt_days=1.0) if pv.S > 0 else 0.0
    breaches = pv.theta_share_breaches + 1 if tshare > p.theta_share_max else 0

    # EV of holding to the NEXT decision horizon (rest of day for 0DTE, one day otherwise),
    # sunk costs excluded; IV path = observed trend, capped at +/-5 vol points per day.
    # S <= 0 (worst-case after-hours restart with no backfill): BS states are meaningless - 
    # zero them; the after-hours ladder below is S-free by construction.
    dt_T = min(T, (max(0, p.session_close_min - minute) / 390.0) / 252.0 if dte == 0
               else 1.0 / 252.0)
    iv_chg = max(-0.05, min(0.05, pv.iv_trend_per_hour * (dt_T * 252.0 * 6.5)))
    ev_h = (om.ev_hold(pv.S, pv.strike, ot, p.r, p.q, iv, T, dt_T, mid,
                       mu=pv.mu_thesis, iv_change=iv_chg, n_grid=p.n_grid)
            if pv.S > 0 else {"ev": 0.0})
    ev_sell = pv.bid - mid                                     # realize now = pay the half-spread
    regain = (om.regain_move(mid, pv.S, pv.strike, ot, p.r, p.q, iv,
                             max(T - 1.0 / 252.0, om.MIN_T)) if pv.S > 0 else None)
    daily_em = iv / 16.0                                       # 1-sigma daily move, fractional

    ret_frac = (mid / pv.entry_mid - 1.0) if pv.entry_mid > 0 else 0.0
    peak_frac = (pv.peak_mid / pv.entry_mid - 1.0) if pv.entry_mid > 0 else 0.0

    state = {"mid": round(mid, 4), "dte": dte, "T": round(T, 6), "iv": round(iv, 4),
             "delta": round(adelta, 3), "theta_day": round(theta_day, 4),
             "p_target_mu0": round(p_tgt_0, 3), "p_target_thesis": round(p_tgt_thesis, 3),
             "theta_share": round(tshare, 3), "ev_hold": round(ev_h["ev"], 4),
             "ev_sell": round(ev_sell, 4),
             "regain_pct": round(regain, 4) if regain is not None else None,
             "iv_trend_hr": round(pv.iv_trend_per_hour, 4), "ret_frac": round(ret_frac, 3),
             "vehicle_mismatch": bool(tshare > p.theta_share_max and p_tgt_thesis >= p.p_target_floor)}

    def _sell(rule: str, variant_hold: bool = False, trail: bool = False) -> ExitDecision:
        return ExitDecision(SELL, rule, state, variant_hold, breaches, trail)

    # ---- AFTER-HOURS restricted ladder (late-close mode; owner 2026-07-09 "don't cut off early")
    # The equity close has passed: S is frozen, so every BS-state rule (a/g/h/i, P_target, EV,
    # regain) and the lane thesis (b) would run on fiction - only PREMIUM-anchored rules and the
    # hard clock survive. Peak keeps updating on live after-hours NBBO mids (truthful - the
    # option market trades to close+15); NEW trail arms are forbidden (P_target input is stale).
    if pv.after_hours:
        state["after_hours"] = True
        if pv.trailing:
            state["trailing"] = True
        # the overnight evidence-rule EXCEPTION (fork answer: DTE>=3 + delta>=0.7 + named
        # catalyst tomorrow + not Friday) outrides even the late-close flat - a granted ride
        # holds through every after-hours mark and carries to tomorrow via the ledger rebuild
        # (refute find 2026-07-10: without this the exception arm was end-to-end dead code)
        if (dte >= p.overnight_min_dte and adelta >= p.overnight_min_delta
                and pv.named_catalyst_tomorrow and not pv.is_friday):
            return ExitDecision(HOLD, "overnight_grant_hold", state, False,
                                pv.theta_share_breaches, pv.trailing)
        if minute >= p.late_close_flat_min:              # close+10: nothing ELSE outrides this
            return _sell("late_close_flat", trail=pv.trailing)
        if pv.planned_exit_minute is not None and \
                minute >= min(int(pv.planned_exit_minute), p.planned_exit_cap_min):
            return _sell("planned_exit_flat", trail=pv.trailing)
        if p.stop_frac is not None and pv.entry_mid > 0 and ret_frac <= p.stop_frac:
            return _sell("c_premium_stop")
        if pv.trailing and mid <= pv.peak_mid * (1.0 - p.trail_giveback):
            return _sell("d_trail_giveback", trail=True)
        if pv.entry_mid > 0 and peak_frac >= p.backstop_arm_frac and mid <= pv.entry_mid:
            return _sell("d2_breakeven_backstop")
        return ExitDecision(HOLD, "ah_hold", state, False, pv.theta_share_breaches, pv.trailing)

    def _policy_clocks() -> ExitDecision | None:
        """The two survival clocks NO branch may bypass (including the rule-(d) trail):
        (1) never hold long premium through a print - SELL inside the pre-release lead window;
        (2) the 15:45 overnight evidence rule for non-0DTE (fork answer) - a DTE 1-2 trailing
        winner must still go flat same-day."""
        if (pv.minutes_to_next_print is not None
                and 0 <= pv.minutes_to_next_print <= p.print_flat_lead_min):
            return _sell("print_window_flat")
        if dte >= 1 and pv.planned_exit_minute is not None:
            # a lane-designed same-day exit (last30/macro 15:55) supersedes the 15:45 checkpoint:
            # "don't cut off early, running later is better" (owner, 2026-07-09 night; sweep_ledger
            # opts-tweak-planned-exit-v1). EV rules below may still sell earlier on merit - 
            # only the CLOCK is deferred, capped at 15:59 for underlying-mark sanity.
            if minute >= min(int(pv.planned_exit_minute), p.planned_exit_cap_min):
                return _sell("planned_exit_flat")
            return None
        if dte >= 1 and minute >= p.eod_flat_min:
            exception = (dte >= p.overnight_min_dte and adelta >= p.overnight_min_delta
                         and pv.named_catalyst_tomorrow and not pv.is_friday)
            if not exception:
                variant_hold = ev_h["ev"] > ev_sell      # the unrestricted arm would keep it
                return _sell("overnight_evidence_rule", variant_hold)
        return None

    # ---- (a) 0DTE same-day, the only expiry-clock exit (rule 3) --------------------------------
    if dte == 0:
        cutoff = p.zero_dte_deep_itm_ext_min if adelta >= p.zero_dte_deep_itm_delta else p.zero_dte_sell_min
        if minute >= cutoff:
            return _sell("a_zero_dte_clock")
    # ---- (b) thesis invalid: sell winners too (rules 12, 20) -----------------------------------
    if not pv.thesis_valid:
        return _sell("b_thesis_invalid")
    # ---- (c) premium stop (INERT at default stop_frac=None - owner 2026-07-10) --------------------
    if p.stop_frac is not None and pv.entry_mid > 0 and ret_frac <= p.stop_frac:
        return _sell("c_premium_stop")
    # ---- (d) take at +100% unless conviction earns a trail (rules 16, 21). The trail LATCHES:
    #      once armed it governs the winner even when the current return sags below +100%
    #      (unlatched, the giveback level peak*(1-0.25) is unreachable for any peak < 2.667x
    #      entry because the ret>=+100% precondition dies first - the winner would bleed to the
    #      d2 breakeven backstop instead of losing 25% off peak).
    trail_armed = pv.trailing
    if pv.entry_mid > 0 and ret_frac >= p.take_frac and not trail_armed:
        if p_tgt_0 > p.trail_p_target_min:
            trail_armed = True                           # rule 21: conviction earned MORE ROOM
        else:
            return _sell("d_take_profit")
    if trail_armed:
        state["trailing"] = True
        if mid <= pv.peak_mid * (1.0 - p.trail_giveback):
            return _sell("d_trail_giveback", trail=True)
        clk = _policy_clocks()          # the trail bypasses EV/theta rules, NEVER the survival
        if clk is not None:             # clocks (print window + 15:45 checkpoint)
            return clk
        # the EV/theta rules below may not claw a latched winner back mid-trail
        return ExitDecision(HOLD, "d_trailing_hold", state, False, breaches, True)
    # ---- (d2) winner-protection backstop (rule 23) ----------------------------------------------
    if pv.entry_mid > 0 and peak_frac >= p.backstop_arm_frac and mid <= pv.entry_mid:
        return _sell("d2_breakeven_backstop")
    # ---- (e) event straddles always sold at T-1 close (Lane 4) ----------------------------------
    if pv.is_event_straddle and pv.event_tminus1_close:
        return _sell("e_event_straddle_tminus1")
    # ---- (f) post-print forced decision (rule 6) -------------------------------------------------
    if pv.minutes_since_print is not None and pv.minutes_since_print >= p.post_print_decision_min:
        if ev_h["ev"] <= ev_sell:
            return _sell("f_post_print_no_edge")
    # ---- policy clocks: print-window flat (plan hard rule; rule 6) + the 15:45 overnight
    #      evidence rule for non-0DTE (fork answer) ------------------------------------------------
    clk = _policy_clocks()
    if clk is not None:
        return clk
    # ---- (g) theta dominance (rules 13, 24) ------------------------------------------------------
    if breaches >= p.theta_share_cycles and p_tgt_thesis < p.p_target_floor:
        return _sell("g_theta_dominates")
    # ---- (h) optimal stopping: entry price appears NOWHERE here (rules 4, 14, 19, 26) -----------
    if ev_h["ev"] < ev_sell:
        return _sell("h_ev_hold_below_sell")
    # ---- (i) daily re-decision: the regain test (rules 2, 10, 18) --------------------------------
    if minute == p.daily_recheck_min or (p.daily_recheck_min <= minute < p.daily_recheck_min + 5):
        if regain is not None and abs(regain) > p.regain_mult * daily_em:
            return _sell("i_regain_unreachable")
        if regain is None:
            return _sell("i_regain_gone")
    # ---- (j) hold + full state log ---------------------------------------------------------------
    return ExitDecision(HOLD, "j_hold", state, False, breaches)
