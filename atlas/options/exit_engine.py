"""EXIT ENGINE (v2, 2026-07-10 - opts-rework-exit-core-v1) - a pure, first-match decision loop
implementing the owner's exit framework as a RISK-NEUTRAL EV-MAXIMIZER with continuous underlying
reassessment.

THE GOVERNING STANDARD (owner, 2026-07-10, verbatim): "the aforementioned ~26 rules are not law.
Law = mathematically + philosophically correct stances to maximize profit taking. You are still
allowed to get creative; just not allowed to say 'sell at a specific price point.' There are
thousands of variables to account for - do your best to ensure our system balances everything
correctly with a viewpoint of 'slightly casino, but educated.'"

Hard consequences enforced by this module:
- NO rule fires at a premium threshold. The entry price is read in exactly THREE places - the
  inert rule-(c) knob (a directive-disabled parameter), the d2* cost-basis backstop (a
  winner-protection rule whose conditions are OBSERVED COSTS, not chosen numbers), and the
  (i*) profit_present APPLICABILITY gate (which can only prevent a sale of a loser, never
  cause one) - and NOWHERE in any hold/sell EV or probability computation.
- Every constant is (a) owner-verbatim, (b) mathematically derived (derivation cited inline), or
  (c) CALIBRATION with a sweep_ledger registration id cited inline. No constant may be
  attributed to the owner without a verbatim quote. NOTE 2026-07-16: docs/OWNER_RULES.md (the former
  canonical rules text) was RETRACTED AND DELETED by owner directive - see
  docs/OWNER_RULES_RETRACTED.md. The rule numbers below cite the retracted file's numbering as
  historical mapping only; every behavior now stands on its own EV/evidence merits.
- The 2026-07-09 v1 engine (which contained a +100% forced take and a trail latch that
  bypassed the EV rules - both unregistered author interpolations) is frozen VERBATIM in
  exit_engine_legacy.py as the paired-replay A/B baseline. Nothing imports it at runtime.

OWNER'S 26 CONSIDERATIONS → implementation (source text retracted; see OWNER_RULES_RETRACTED.md):
 1  current estimated trajectory        -> mu_hat/t_stat live estimate (trajectory.py) blended
                                           into mu_eff by the evidence-gated shrinkage weight
                                           w = t^2/(1+t^2) [CALIBRATION - registered in
                                           opts-rework-exit-core-v1; family replay-swept under
                                           opts-calib-mu-blend-weight-v1; see trajectory.py's
                                           LABEL CORRECTION - the old "DERIVED" claim was
                                           false]; prior = mu_thesis while the thesis holds,
                                           else 0
 2  "today the contract is worth X ... tomorrow the underlying will need to move N% for the
    contract to reach X value again"    -> p_regain (math.py): regain_move solved at the
                                           horizon END + first-passage p_touch under mu_eff - 
                                           the continuous rule (i*)
 3  always sell 0DTE same-day, never solely because of the clock
                                        -> rule (a) is the ONLY expiry clock (15:00; delta>=0.80
                                           extends to 15:30 - clock times are POLICY, from the
                                           registered plan, not the 26)
 4  P(underlying reaches target) over unrealized P/L
                                        -> p_touch (exact first-passage); unrealized P&L absent
                                           from every EV comparison
 5  expected remaining upside vs remaining theta decay
                                        -> ev_hold (Gauss-Hermite BSM reprice) + theta_share
 6  volatility events                   -> rules (e)/(f) + print_window_flat policy clock;
                                           IV-crush enters EV via iv_change
 7  IV rising/falling independently     -> iv_trend_per_hour -> EV iv_change
 8  delta vs required move              -> greeks state + regain_move
 9  gamma near expiry                   -> 0DTE theta multiplier (empirical afternoon ramp)
10  every additional day a new decision -> EVERY MARK is a full re-decision; the once-daily
                                           09:35 gate is GONE (v1's rule-i gating was an
                                           author restriction, removed)
11  updated probabilities, latest info  -> every cycle recomputes ALL states from fresh marks
                                           under mu_eff
12  thesis still valid / played out     -> thesis_valid -> rule (b)
13  "stock can still go higher" vs "option still the best expression"
                                        -> vehicle_mismatch flag + rule (g)
14  EV of holding vs realizing now      -> rule (h): ev_hold(mu_eff) < ev_sell
15  prefer selling when remaining gain is small vs remaining risk
                                        -> (h) is the expectation rule; (i*) is the SKEW rule - 
                                           it catches the fat-right-tail hold where most paths
                                           never see today's value again
16  highest %-gains come before the final portion of a move
                                        -> when the final portion arrives, P(regain today's
                                           value) collapses -> (i*) sells while the profit is
                                           still realizable. NO take-profit threshold exists.
                                           p_regain_min is CALIBRATION
                                           (opts-calib-p-regain-min-v1)
17  never hold because it was worth more earlier
                                        -> no peak anchor in any EV/probability input; peak_bid
                                           is used ONLY by the d2* winner-protection backstop
18  ignore anchoring to previous highs  -> (i*)'s reference is TODAY'S value (current mid),
                                           never the high-water mark
19  never hold to avoid a smaller-than-hoped profit
                                        -> (h) fires regardless of profit size
20  confidence down -> reduce exposure even if profitable
                                        -> continuously through mu_eff (adverse evidence drags
                                           the drift); lane invalidation (b) is the hard form
21  confidence up + manageable decay -> allow more room
                                        -> continuously through mu_eff (favorable evidence
                                           raises the drift; no trail, no cliff)
22  scale out of winners               -> ADDITION opts-variant-scaleout-v1: a paired-replay
                                           column (2-lot split), default OFF - the owner specified no
                                           trigger/split; inventing them live would repeat the
                                           interpolation failure mode. Promotion = the owner's call.
23  never let a profitable trade become a losing trade through indecision
                                        -> d2* cost-basis backstop - ADDITION
                                           opts-rule-d2-costbasis-v1 with DERIVED conditions:
                                           arm when peak_bid > entry_ask (the round trip was
                                           realizably profitable at worst-ledger fills); fire
                                           when bid <= entry_ask (that gain is gone)
24  recognize when decay dominates      -> theta_share > 0.50 - DERIVED-BY-DEFINITION
                                           ("dominant" = majority share); the 2-cycle debounce
                                           + 0.30 P_target floor are CALIBRATION
                                           (opts-calib-theta-cycles-v1 / p-target-floor-v1)
25  recalculate after every meaningful change
                                        -> C5 shock-triggered marks + full recompute per cycle
26  wasting assets; every minute justified by positive expected return
                                        -> (h) is the default-deny: hold only while
                                           EV_hold > EV_sell

POLICY CLOCKS (provenance = the owner's explicit dated directives, not the 26): 0DTE same-day
(rule 3 + registered clocks), print_window_flat (never hold long premium through a print),
the 15:45 overnight evidence rule + DTE>=3/delta>=0.7/named-catalyst/not-Friday grant (fork
answer 2026-07-09), planned lane exits (opts-tweak-planned-exit-v1), late-close mode
(opts-tweak-late-close-mode-v1).

OVERNIGHT POLICY (owner's fork answer 2026-07-09): the EVIDENCE rule grades - 0-2 DTE always
closed same-day (15:45), DTE>=3 may ride only with delta>=0.7 + a named next-morning catalyst
+ not Friday. When the evidence rule forces a sell the unrestricted arm would have held,
variant_would_hold=True and the nightly paired replay grades both arms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from atlas.options import math as om
from atlas.options.trajectory import mu_blend_shrink
from atlas.options.vendor.blackscholes import greeks
from atlas.options.vendor.models import OptionType

HOLD, SELL = "HOLD", "SELL"


@dataclass(frozen=True)
class ExitParams:
    zero_dte_sell_min: int = 15 * 60                 # rule (a): close - 60 (policy clock)
    zero_dte_deep_itm_ext_min: int = 15 * 60 + 30    # delta >= 0.80 extension: close - 30
    zero_dte_deep_itm_delta: float = 0.80
    print_flat_lead_min: int = 10                    # never hold through a print: flat this many min before
    # None = rule (c) INERT (owner, 2026-07-10; sweep_ledger opts-tweak-disable-premium-stop-v1):
    # never exit just because the premium is lower now - losses exit via thesis (b), theta (g),
    # the no-anchoring EV stop (h), or the clocks. Set a fraction to re-arm the price stop; the
    # old -0.50 behavior stays measurable as the opts-variant-evidence-exits-v1 replay column.
    stop_frac: float | None = None                   # rule (c)
    post_print_decision_min: int = 15                # rule (f) window - CALIBRATION (plan-era)
    theta_share_max: float = 0.50                    # rule 24: "dominant" = majority (derived)
    theta_share_cycles: int = 2                      # CALIBRATION opts-calib-theta-cycles-v1
    p_target_floor: float = 0.30                     # CALIBRATION opts-calib-p-target-floor-v1
    p_regain_min: float = 0.25                       # rule (i*) - CALIBRATION
    #                                                  opts-calib-p-regain-min-v1 (swept .15/.25/.35)
    # TIME-BASED persistence for the statistical exits (h)/(i*) - audit 2026-07-16 Wave 2.14
    # (TIMESCALE-STACK-2): one non-overlapping mu-estimation window (= mu_window_min default),
    # so the exit cadence can change without changing exit behavior (count-debounce is NOT
    # cadence-invariant; time-based is). The condition must hold CONTINUOUSLY this many minutes
    # before it may sell. Clocks/thesis/backstop rules are exempt by design.
    ev_persist_min: int = 20
    eod_flat_min: int = 15 * 60 + 45                 # evidence overnight checkpoint: close - 15
    planned_exit_cap_min: int = 15 * 60 + 59         # planned same-day exits may run to close - 1
    session_close_min: int = 16 * 60                 # today's RTH close (960 normal, 780 half day)
    late_close_flat_min: int = 16 * 60 + 10          # after-hours hard flat: close + 10
    overnight_min_dte: int = 3
    overnight_min_delta: float = 0.70
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
    entry_mid: float                  # measurement anchor (profit_present gate only; fills live in ledgers)
    peak_mid: float                   # high-water of the mid since entry (logged; NOT a decision input)
    lane: str
    target_underlying: float          # H - the thesis target price
    mu_thesis: float                  # annualized drift implied by the lane's thesis AT ENTRY
    thesis_valid: bool
    entry_ts_min: int                 # minutes-of-day at entry
    # cost basis (d2* backstop - worst-ledger realizability, opts-rule-d2-costbasis-v1):
    entry_ask: float = 0.0            # what the worst ledger PAID at entry
    peak_bid: float = 0.0             # best realizable sell seen since entry (runner-persisted)
    # fresh mark:
    S: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    solved_iv: float = 0.0
    iv_trend_per_hour: float = 0.0    # OLS slope of solved IV, trailing 45 min
    # live trajectory evidence (trajectory.py; None/0 = no view -> thesis governs):
    mu_hat: float | None = None
    mu_t_stat: float = 0.0
    opposing_defense: bool = False    # structure overlay (state-only v1; opts-variant-defense-exit-v1)
    defense_zone_score: float = 0.0
    # event context:
    is_event_straddle: bool = False
    minutes_since_print: int | None = None
    minutes_to_next_print: int | None = None  # minutes until TODAY's next macro release (None = none)
    planned_exit_minute: int | None = None    # lane-designed same-day exit (e.g. last30/macro 15:55)
    event_tminus1_close: bool = False # T-1 close window for an event straddle
    named_catalyst_tomorrow: bool = False
    is_friday: bool = False
    theta_share_breaches: int = 0     # consecutive cycles with theta_share > max (carried state)
    after_hours: bool = False         # equity close passed; S frozen; option NBBO still live
    # ---- audit 2026-07-16 Wave 2 additions (all defaulted: legacy replay rows stay valid) ----
    p_thesis: float = 0.5             # the lane's entry-time thesis probability - the ENTRY-
    #                                   consistent prior is mu_prior = p_thesis * mu_thesis
    #                                   (Wave 2.15; the old prior held the thesis at 100%
    #                                   while the selector priced it at 50%)
    horizon_T: float = 0.0            # the lane's planned hold (TRADING years) at entry - for
    #                                   the horizon-consistent p_target instrumentation (Wave 0.3)
    evidence_stale: bool = False      # tape staleness bound (Wave 2.16): a halted/frozen feed
    #                                   must not read as "thesis fully intact" - prior drops to 0
    h_breach_since_min: int | None = None  # first minute rule (h) held continuously (carried)
    i_breach_since_min: int | None = None  # first minute rule (i*) held continuously (carried)


@dataclass(frozen=True)
class ExitDecision:
    action: str                       # HOLD | SELL
    rule: str                         # which line fired (a, b, c, d2, e, f, g, h, i*, j, clocks)
    state: dict = field(default_factory=dict)
    variant_would_hold: bool = False  # the owner's unrestricted-overnight arm diverges here
    theta_share_breaches: int = 0     # carry-forward for the caller
    h_breach_since_min: int | None = None  # carry-forward: rule (h) persistence clock (Wave 2.14)
    i_breach_since_min: int | None = None  # carry-forward: rule (i*) persistence clock


def decide_exit(pv: PositionView, now_et: datetime, p: ExitParams = ExitParams()) -> ExitDecision:
    """One pure decision. First match wins; every SELL names its rule; HOLD logs the full state."""
    minute = now_et.hour * 60 + now_et.minute
    dte = (pv.expiry - now_et.date()).days
    mid = (pv.bid + pv.ask) / 2.0 if (pv.bid > 0 and pv.ask > 0) else max(pv.bid, 0.0)
    ot = OptionType.CALL if pv.opt_type == "call" else OptionType.PUT
    T = om.trading_T(now_et, pv.expiry, close_minute=p.session_close_min)
    iv = max(pv.solved_iv, 1e-4)
    iv_fresh = pv.solved_iv > 1e-3            # degraded-IV sentinel: a data failure never sells a winner
    g = greeks(pv.S, pv.strike, p.r, p.q, iv, T, ot) if pv.S > 0 else None
    adelta = abs(g.delta) if g else 0.0
    # theta in TRADING-day units (opts-fix-math-audit-20260710): the vendored greeks() theta is
    # per CALENDAR day (annual/365) while every consumer here compares against trading-day moves
    # (iv/16 daily vol) - scale ×365/252. The old extra 0DTE afternoon multiplier is REMOVED:
    # live-T BSM theta already carries its own 1/√T acceleration (the empirical ramp was
    # double-counting; it survives only inside zero_dte_effective_T where it REPLACES the model
    # clock for the p_regain barrier).
    theta_day = (g.theta if g else 0.0) * (365.0 / 252.0)

    # ---- live-reassessed drift (rules 1/11/20/21) - audit 2026-07-16 Wave 2.15 changeset -------
    # ENTRY-CONSISTENT prior: mu_prior = p_thesis * mu_thesis (the entry priced the thesis at
    # p_thesis; the old prior held it at 100% - one of the five unreconciled probabilities the
    # coherency seam flagged). STALENESS BOUND (Wave 2.16): a frozen/halted tape means the
    # thesis frame is unobservable - prior drops to 0 (no view), it does NOT stay "fully intact".
    mu_prior = (pv.p_thesis * pv.mu_thesis) if (pv.thesis_valid and not pv.evidence_stale) else 0.0
    # VARIANCE-SCALED blend (Wave 2.15, shipped together with the prior fix per TRAJECTORY-6):
    # tau = |mu_thesis| is the scale of drifts the thesis distinguishes - CALIBRATION, registered
    # in the audit changeset (docs/AUDIT_2026-07-16_options_platform.md §6.15); iv is the
    # fallback scale for a zero-drift thesis (defensive: no live lane emits one).
    tau = abs(pv.mu_thesis) if abs(pv.mu_thesis) > 1e-9 else iv
    mu_eff = mu_blend_shrink(pv.mu_hat, pv.mu_t_stat, mu_prior, tau)

    p_tgt_0 = om.p_touch(pv.S, pv.target_underlying, iv, T, mu=0.0) if pv.S > 0 else 0.0
    p_tgt_thesis = om.p_touch(pv.S, pv.target_underlying, iv, T, mu=pv.mu_thesis) if pv.S > 0 else 0.0
    p_tgt_eff = om.p_touch(pv.S, pv.target_underlying, iv, T, mu=mu_eff) if pv.S > 0 else 0.0
    # dt capped at the remaining life in trading days (audit fix: dt_days=1.0 on a 0DTE
    # afternoon extrapolated decay a full day past expiry)
    tshare = (om.theta_share(theta_day, adelta, pv.S, iv, dt_days=min(1.0, T * 252.0))
              if pv.S > 0 else 0.0)
    breaches = pv.theta_share_breaches + 1 if tshare > p.theta_share_max else 0

    # EV of holding to the NEXT decision horizon (rest of day for 0DTE, one day otherwise),
    # sunk costs excluded; IV path = observed trend, capped at +/-5 vol points per day.
    # The DECISION input is mu_eff; the mu_thesis and mu=0 columns are logged for divergence
    # evidence (rule-1 upgrade audit trail). S <= 0 (worst-case after-hours restart with no
    # backfill): BS states are meaningless - zero them; the after-hours ladder is S-free.
    dt_T = min(T, (max(0, p.session_close_min - minute) / 390.0) / 252.0 if dte == 0
               else 1.0 / 252.0)
    iv_chg = max(-0.05, min(0.05, pv.iv_trend_per_hour * (dt_T * 252.0 * 6.5)))
    if pv.S > 0:
        ev_h = om.ev_hold(pv.S, pv.strike, ot, p.r, p.q, iv, T, dt_T, mid,
                          mu=mu_eff, iv_change=iv_chg, n_grid=p.n_grid)
        ev_h_thesis = om.ev_hold(pv.S, pv.strike, ot, p.r, p.q, iv, T, dt_T, mid,
                                 mu=pv.mu_thesis, iv_change=iv_chg, n_grid=p.n_grid)["ev"]
        ev_h_mu0 = om.ev_hold(pv.S, pv.strike, ot, p.r, p.q, iv, T, dt_T, mid,
                              mu=0.0, iv_change=iv_chg, n_grid=p.n_grid)["ev"]
    else:
        ev_h, ev_h_thesis, ev_h_mu0 = {"ev": 0.0, "p_profit": 0.0}, 0.0, 0.0
    ev_sell = pv.bid - mid                                     # realize now = pay the half-spread

    # ---- P(regain today's value) - rule 2 verbatim, continuous (rule i*) ------------------------
    # 0DTE horizon = the engine's own rule-(a) forced-sale clock (incl. the deep-ITM extension).
    sell_clock = (p.zero_dte_deep_itm_ext_min if adelta >= p.zero_dte_deep_itm_delta
                  else p.zero_dte_sell_min)
    pr = (om.p_regain(mid, pv.S, pv.strike, ot, p.r, p.q, iv, T,
                      minute=minute, dte=dte, sell_clock_min=sell_clock, mu=mu_eff)
          if (pv.S > 0 and mid > 0) else {"p": 0.0, "move": None, "dt_h": 0.0})

    profit_present = pv.entry_mid > 0 and mid > pv.entry_mid   # (i*) applicability gate ONLY
    # d2* cost-basis backstop (rules 17/23 - ADDITION opts-rule-d2-costbasis-v1, derived):
    d2_armed = pv.entry_ask > 0 and pv.peak_bid > pv.entry_ask

    ret_frac = (mid / pv.entry_mid - 1.0) if pv.entry_mid > 0 else 0.0

    # ---- horizon-consistent p_target (audit Wave 0.3): P(touch the ORIGINAL thesis target
    #      within the REMAINING thesis horizon) - pairs with the entry-side p_touch_target/p_mkt
    #      logs so entry and exit finally measure the same quantity. Same-day elapsed
    #      approximation for overnight holds (documented; grants tend to be re-decided at 09:35).
    import math as _math
    elapsed_T = max(0, minute - pv.entry_ts_min) / (390.0 * 252.0)
    rem_h_T = min(T, max(pv.horizon_T - elapsed_T, 0.0))
    p_tgt_horizon = (om.p_touch(pv.S, pv.target_underlying, iv, rem_h_T, mu=mu_eff)
                     if (pv.S > 0 and rem_h_T > 0) else 0.0)

    # ---- time-based persistence clocks for the statistical exits (audit Wave 2.14) -------------
    # A breach minute is recorded the FIRST mark the condition holds and carried while it keeps
    # holding; any clean mark resets the clock. The rules fire only after the breach has held
    # continuously for ev_persist_min (~one non-overlapping mu window -> cadence-invariant).
    # evidence_stale (Wave 2.16) blocks BOTH: statistical exits never run on a frozen tape.
    cond_h = ev_h["ev"] < ev_sell and not pv.evidence_stale
    h_since = ((pv.h_breach_since_min if pv.h_breach_since_min is not None else minute)
               if cond_h else None)
    cond_i = (profit_present and iv_fresh and pv.S > 0 and _math.isfinite(mu_eff)
              and pr["p"] < p.p_regain_min and not pv.evidence_stale)
    i_since = ((pv.i_breach_since_min if pv.i_breach_since_min is not None else minute)
               if cond_i else None)

    state = {"mid": round(mid, 4), "dte": dte, "T": round(T, 6), "iv": round(iv, 4),
             "delta": round(adelta, 3), "theta_day": round(theta_day, 4),
             "mu_hat": round(pv.mu_hat, 4) if pv.mu_hat is not None else None,
             "mu_t_stat": round(pv.mu_t_stat, 3), "mu_eff": round(mu_eff, 4),
             "mu_prior": round(mu_prior, 4), "p_thesis": round(pv.p_thesis, 3),
             "evidence_stale": bool(pv.evidence_stale),
             "h_breach_since_min": h_since, "i_breach_since_min": i_since,
             "p_target_mu0": round(p_tgt_0, 3), "p_target_thesis": round(p_tgt_thesis, 3),
             "p_target_eff": round(p_tgt_eff, 3),
             "p_target_horizon": round(p_tgt_horizon, 3),
             "theta_share": round(tshare, 3),
             "ev_hold": round(ev_h["ev"], 4), "ev_hold_thesis": round(ev_h_thesis, 4),
             "ev_hold_mu0": round(ev_h_mu0, 4), "ev_sell": round(ev_sell, 4),
             "p_profit": round(ev_h.get("p_profit", 0.0), 3),
             "p_regain": round(pr["p"], 3),
             "regain_pct": round(pr["move"], 4) if pr["move"] is not None else None,
             "profit_present": bool(profit_present), "d2_armed": bool(d2_armed),
             "opposing_defense": bool(pv.opposing_defense),
             "defense_zone_score": round(pv.defense_zone_score, 2),
             "iv_trend_hr": round(pv.iv_trend_per_hour, 4), "ret_frac": round(ret_frac, 3),
             "vehicle_mismatch": bool(tshare > p.theta_share_max and p_tgt_thesis >= p.p_target_floor)}

    def _sell(rule: str, variant_hold: bool = False) -> ExitDecision:
        return ExitDecision(SELL, rule, state, variant_hold, breaches, h_since, i_since)

    # ---- AFTER-HOURS restricted ladder (late-close mode; owner 2026-07-09 "don't cut off early")
    # The equity close has passed: S is frozen, so every BS-state rule (a/g/h/i*, P_target, EV,
    # regain, mu_hat) and the lane thesis (b) would run on fiction - only PREMIUM/COST-anchored
    # rules and the hard clock survive. peak_bid keeps updating on live after-hours NBBO
    # (truthful - the option market trades to close+15).
    if pv.after_hours:
        state["after_hours"] = True
        # the overnight evidence-rule EXCEPTION (fork answer: DTE>=3 + delta>=0.7 + named
        # catalyst tomorrow + not Friday) outrides even the late-close flat - a granted ride
        # holds through every after-hours mark and carries to tomorrow via the ledger rebuild
        if (dte >= p.overnight_min_dte and adelta >= p.overnight_min_delta
                and pv.named_catalyst_tomorrow and not pv.is_friday):
            return ExitDecision(HOLD, "overnight_grant_hold", state, False,
                                pv.theta_share_breaches, h_since, i_since)
        if minute >= p.late_close_flat_min:              # close+10: nothing ELSE outrides this
            return _sell("late_close_flat")
        if pv.planned_exit_minute is not None and \
                minute >= min(int(pv.planned_exit_minute), p.planned_exit_cap_min):
            return _sell("planned_exit_flat")
        if p.stop_frac is not None and pv.entry_mid > 0 and ret_frac <= p.stop_frac:
            return _sell("c_premium_stop")
        if d2_armed and pv.bid <= pv.entry_ask:
            return _sell("d2_costbasis_backstop")
        return ExitDecision(HOLD, "ah_hold", state, False, pv.theta_share_breaches,
                            h_since, i_since)

    def _policy_clocks() -> ExitDecision | None:
        """The survival clocks NO branch may bypass:
        (1) never hold long premium through a print - SELL inside the pre-release lead window;
        (2) the 15:45 overnight evidence rule for non-0DTE (fork answer) - planned lane exits
        supersede the checkpoint (opts-tweak-planned-exit-v1), capped at close-1."""
        if (pv.minutes_to_next_print is not None
                and 0 <= pv.minutes_to_next_print <= p.print_flat_lead_min):
            return _sell("print_window_flat")
        if dte >= 1 and pv.planned_exit_minute is not None:
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
    if dte == 0 and minute >= sell_clock:
        return _sell("a_zero_dte_clock")
    # ---- (b) thesis invalid: sell winners too (rules 12, 20) -----------------------------------
    if not pv.thesis_valid:
        return _sell("b_thesis_invalid")
    # ---- (c) premium stop (INERT at default stop_frac=None - owner 2026-07-10) --------------------
    if p.stop_frac is not None and pv.entry_mid > 0 and ret_frac <= p.stop_frac:
        return _sell("c_premium_stop")
    # ---- (d2*) cost-basis backstop (rules 17/23 - ADDITION opts-rule-d2-costbasis-v1): the trade
    #      was realizably profitable through the round trip at worst-ledger fills (peak_bid >
    #      entry_ask) and that realizable gain is now gone (bid <= entry_ask). Observed costs
    #      only - no chosen numbers. (The v1 trail family and its +100% arm are REMOVED; the
    #      25%-trail survives only as replay columns.)
    #      Audit 2026-07-16 EXIT-ENGINE-3 / Wave 2.16: standalone, this armed on ~0.17 sigma of
    #      spread noise (P~0.99/day on a martingale) and scratched winners at ~$0 - the exact
    #      opposite skew of the casino posture. It now CO-REQUIRES the EV verdict
    #      (ev_hold < ev_sell) in the RTH ladder; the S-free after-hours ladder keeps the plain
    #      form (no EV exists there and the hard clocks bound the exposure).
    if d2_armed and pv.bid <= pv.entry_ask and ev_h["ev"] < ev_sell:
        return _sell("d2_costbasis_backstop")
    # ---- (e) event straddles always sold at T-1 close (Lane 4) ----------------------------------
    if pv.is_event_straddle and pv.event_tminus1_close:
        return _sell("e_event_straddle_tminus1")
    # ---- (f) post-print forced decision (rule 6) -------------------------------------------------
    if pv.minutes_since_print is not None and pv.minutes_since_print >= p.post_print_decision_min:
        if ev_h["ev"] <= ev_sell:
            return _sell("f_post_print_no_edge")
    # ---- policy clocks: print-window flat + the 15:45 overnight evidence rule --------------------
    clk = _policy_clocks()
    if clk is not None:
        return clk
    # ---- (g) theta dominance (rules 13, 24; P_target input = mu_eff per rule 11) ----------------
    if breaches >= p.theta_share_cycles and p_tgt_eff < p.p_target_floor:
        return _sell("g_theta_dominates")
    # ---- (h) optimal stopping under the LIVE drift: entry price appears NOWHERE here
    #      (rules 4, 5, 14, 15, 19, 26). Audit 2026-07-16 Wave 2.14: fires only after the EV
    #      breach has held CONTINUOUSLY for ev_persist_min (the persistence clock above) - the
    #      un-debounced form was the confirmed noise clock (TRAJECTORY-1, 4/4 refuters). --------
    if cond_h and (minute - h_since) >= p.ev_persist_min:
        return _sell("h_ev_hold_below_sell")
    # ---- (i*) continuous P(regain) profit-taking (rules 2, 4, 11, 14, 15, 16, 18, 25):
    #      profit is present AND the math says we will not see this contract value again within
    #      the actionable horizon -> take it while it is realizable. profit_present is an
    #      APPLICABILITY gate (this is a profit-taking rule; losers exit via b/g/h/clocks - 
    #      never exit just because the number is lower now). iv_fresh guards the degraded-IV
    #      sentinel, and the S/mu finiteness guards keep a DIRECT caller with degenerate inputs
    #      (S=0, NaN drift) from selling a winner on a fictional p_regain=0 (W2 refute,
    #      2026-07-10). Same Wave-2.14 persistence clock as (h). ---------------------------------
    if cond_i and (minute - i_since) >= p.ev_persist_min:
        return _sell("i_regain_low")
    # ---- (j) hold + full state log (persistence clocks carried so breaches accumulate) ----------
    return ExitDecision(HOLD, "j_hold", state, False, breaches, h_since, i_since)
