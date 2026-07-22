"""Exit engine v2 (opts-rework-exit-core-v1): the corrected first-match matrix - every rule
fired in isolation, precedence, the mu_eff live-reassessment blend, the continuous P(regain)
profit rule (i*), the d2* cost-basis backstop, breach carry-forward, variant_would_hold, and
the ANTI-HALLUCINATION pins (no premium threshold may ever force a sell).

The frozen v1 baseline is pinned separately in test_options_exit_engine_legacy.py.
"""

from __future__ import annotations

from datetime import date, datetime

from atlas.options.exit_engine import (HOLD, SELL, ExitParams, PositionView, decide_exit)
from atlas.options.selector import SelectorParams
from atlas.options.trajectory import mu_blend

TODAY = date(2026, 7, 14)                       # Tuesday
TOMORROW = date(2026, 7, 15)
FRIDAY_DT = datetime(2026, 7, 17, 15, 50)


def pv(**kw) -> PositionView:
    base = dict(occ="X", underlying="XYZ", opt_type="call", strike=100.0, expiry=TOMORROW,
                entry_mid=2.0, peak_mid=2.0, lane="lane1", target_underlying=102.0,
                mu_thesis=2.0, thesis_valid=True, entry_ts_min=9 * 60 + 50,
                S=100.0, bid=1.95, ask=2.05, solved_iv=0.30, iv_trend_per_hour=0.0)
    base.update(kw)
    return PositionView(**base)


def at(h, m):
    return datetime(2026, 7, 14, h, m)


# --------------------------------------------------------------------- clocks + hard rules
def test_a_zero_dte_clock_and_deep_itm_extension():
    d = decide_exit(pv(expiry=TODAY, strike=100.0), at(15, 5))
    assert d.action == SELL and d.rule == "a_zero_dte_clock"
    # deep ITM (delta >= 0.80): strike far below spot -> extension to 15:30
    deep = pv(expiry=TODAY, strike=90.0, bid=10.0, ask=10.2, entry_mid=9.0, peak_mid=10.1)
    d2 = decide_exit(deep, at(15, 5))
    assert d2.rule != "a_zero_dte_clock"
    d3 = decide_exit(deep, at(15, 35))
    assert d3.action == SELL and d3.rule == "a_zero_dte_clock"


def test_b_thesis_invalid_sells_even_winners():
    d = decide_exit(pv(thesis_valid=False, bid=3.90, ask=4.10, peak_mid=4.0), at(11, 0))
    assert d.action == SELL and d.rule == "b_thesis_invalid"


def test_c_premium_stop_inert_by_default():
    # owner 2026-07-10 (opts-tweak-disable-premium-stop-v1): never exit just because the premium
    # is lower now - a -52% mid must NOT trip a price stop...
    d0 = decide_exit(pv(bid=0.93, ask=0.99), at(11, 0))
    assert d0.rule != "c_premium_stop"
    # ...but the rule stays functional when a stop is explicitly set (the replay-variant knob)
    d = decide_exit(pv(bid=0.93, ask=0.99), at(11, 0), ExitParams(stop_frac=-0.50))
    assert d.action == SELL and d.rule == "c_premium_stop"


# --------------------------------------------------------------------- ANTI-HALLUCINATION pins
def test_no_premium_threshold_ever_forces_a_sell():
    """THE incident pin (owner 2026-07-10): the v1 engine force-sold at +100% premium - an
    unregistered author interpolation. In v2 NO rule may fire merely because the return
    crossed a level: a +150% winner with a live thesis, healthy EV and a reachable regain
    level HOLDS. (Fixture is model-consistent: mid == BSM(S,K,iv,T) so the solved IV the
    runner would produce matches the quote.)"""
    won = pv(strike=98.0, bid=2.30, ask=2.34, entry_mid=0.93, peak_mid=2.34,
             mu_thesis=8.0, target_underlying=104.0)
    d = decide_exit(won, at(11, 0))
    assert d.action == HOLD, (d.rule, d.state)
    assert d.rule == "j_hold"
    assert d.state["ret_frac"] > 1.4          # the +100% level is far behind us and nothing fired


def test_removed_v1_rules_never_fire():
    """d_take_profit / d_trail_giveback / d_trailing_hold / d2_breakeven_backstop /
    i_regain_unreachable / i_regain_gone are v1 rule ids - they must be unreachable across a
    sweep of provocative states (huge winners, deep losers, sagged peaks, morning recheck)."""
    dead = {"d_take_profit", "d_trail_giveback", "d_trailing_hold",
            "d2_breakeven_backstop", "i_regain_unreachable", "i_regain_gone"}
    probes = [
        (pv(bid=4.00, ask=4.10, peak_mid=4.1), at(11, 0)),                 # +100% winner
        (pv(bid=6.00, ask=6.10, peak_mid=6.1), at(11, 0)),                 # +200% winner
        (pv(bid=2.75, ask=2.85, peak_mid=6.0), at(11, 0)),                 # sagged off peak
        (pv(bid=0.55, ask=0.61, strike=105.0, entry_mid=0.9, peak_mid=0.95,
            target_underlying=106.0, mu_thesis=15.0), at(9, 36)),          # v1 recheck window
        (pv(bid=1.98, ask=2.02, peak_mid=3.6), at(11, 0)),                 # v1 d2 shape
    ]
    for view, when in probes:
        d = decide_exit(view, when)
        assert d.rule not in dead, (d.rule, view.bid, view.peak_mid)


# --------------------------------------------------------------------- d2* cost-basis backstop
def test_d2_costbasis_backstop_arm_and_fire():
    # ADDITION opts-rule-d2-costbasis-v1 (rules 17/23) - observed costs only:
    # armed: peak_bid (3.50) cleared entry_ask (2.05); fired: bid (1.98) <= entry_ask
    d = decide_exit(pv(bid=1.98, ask=2.02, peak_mid=3.6, entry_ask=2.05, peak_bid=3.50),
                    at(11, 0))
    assert d.action == SELL and d.rule == "d2_costbasis_backstop"
    # NOT armed: the trade never cleared its round-trip cost (peak_bid <= entry_ask)
    d2 = decide_exit(pv(bid=1.98, ask=2.02, peak_mid=2.1, entry_ask=2.05, peak_bid=2.00),
                     at(11, 0))
    assert d2.rule != "d2_costbasis_backstop"
    # armed but still realizably profitable (bid > entry_ask): no fire
    d3 = decide_exit(pv(bid=2.40, ask=2.50, peak_mid=3.6, entry_ask=2.05, peak_bid=3.50),
                     at(11, 0))
    assert d3.rule != "d2_costbasis_backstop"
    # no cost basis recorded (entry_ask 0, e.g. degenerate entry quote): never armed
    d4 = decide_exit(pv(bid=1.98, ask=2.02, peak_mid=3.6, entry_ask=0.0, peak_bid=3.50),
                     at(11, 0))
    assert d4.rule != "d2_costbasis_backstop"


# --------------------------------------------------------------------- live reassessment (mu_eff)
def test_mu_eff_blend_no_view_equals_scaled_thesis():
    """v3 (audit 2026-07-16 Wave 2.15, opts-audit-wave2-exitv3-v1): the prior is
    ENTRY-CONSISTENT - mu_prior = p_thesis * mu_thesis (the entry priced the thesis at
    p_thesis=0.5; the old full-weight prior was one of the five unreconciled probabilities)."""
    d = decide_exit(pv(mu_thesis=4.0, target_underlying=101.0), at(11, 0))
    assert abs(d.state["mu_eff"] - 2.0) < 1e-9                       # 0.5 * 4.0
    assert abs(d.state["mu_prior"] - 2.0) < 1e-9
    d15 = decide_exit(pv(mu_thesis=4.0, p_thesis=0.25, target_underlying=101.0), at(11, 0))
    assert abs(d15.state["mu_eff"] - 1.0) < 1e-9                     # 0.25 * 4.0
    # thesis invalidated -> prior collapses to 0 (rule (b) fires, state still logs the blend)
    d2 = decide_exit(pv(mu_thesis=4.0, thesis_valid=False), at(11, 0))
    assert d2.rule == "b_thesis_invalid" and abs(d2.state["mu_eff"]) < 1e-9
    # evidence_stale (Wave 2.16): a frozen/halted tape drops the prior to 0 too - a halt must
    # never read as "thesis fully intact"
    d3 = decide_exit(pv(mu_thesis=4.0, evidence_stale=True, target_underlying=101.0), at(11, 0))
    assert abs(d3.state["mu_prior"]) < 1e-9 and d3.state["evidence_stale"] is True


def test_mu_eff_blend_weights_match_registered_formula():
    """v3 blend = variance-scaled shrinkage (TRAJECTORY-1, 4/4 refuters upheld the noise-clock
    finding against the old w=t^2/(1+t^2)): w = tau^2/(tau^2+SE^2), SE = |mu_hat/t|,
    tau = |mu_thesis|. The legacy mu_blend stays importable for replay of pre-fix paths."""
    assert abs(mu_blend(-6.0, 1.0, 2.0) - (-2.0)) < 1e-9             # legacy formula unchanged
    assert mu_blend(None, 5.0, 2.0) == 2.0
    # engine: mu_hat=-6 t=1 -> SE=6; tau=|mu_thesis|=2 -> w=4/40=0.1;
    # mu_prior=0.5*2=1.0 -> mu_eff = 0.1*(-6) + 0.9*1.0 = +0.3
    d = decide_exit(pv(mu_thesis=2.0, mu_hat=-6.0, mu_t_stat=1.0,
                       target_underlying=101.0), at(11, 0))
    assert abs(d.state["mu_eff"] - 0.3) < 1e-9
    # the noise-clock cure: the SAME |t|=1 evidence at a 20-min-noise scale (SE huge) barely
    # moves the prior - a 1-sigma wiggle can no longer take 50% weight
    d2 = decide_exit(pv(mu_thesis=2.0, mu_hat=-14.0, mu_t_stat=1.0,
                        target_underlying=101.0), at(11, 0))
    w = (2.0 ** 2) / (2.0 ** 2 + 14.0 ** 2)
    assert abs(d2.state["mu_eff"] - (w * -14.0 + (1 - w) * 1.0)) < 1e-9
    assert d2.state["mu_eff"] > 0.4                                  # prior still governs


def test_adverse_live_evidence_kills_the_hold_after_persistence():
    """the owner's IWM pattern in miniature, v3: a profitable position whose underlying shows strong
    OPPOSING drift exits via the EV math - but only after the breach has PERSISTED
    ev_persist_min (Wave 2.14; the un-debounced rule was the confirmed noise clock). First
    breach mark arms the clock and HOLDs; the same state 20 minutes later sells."""
    base = dict(strike=98.0, bid=2.30, ask=2.34, entry_mid=0.93, peak_mid=2.34,
                mu_thesis=8.0, target_underlying=104.0)
    calm = decide_exit(pv(**base), at(11, 0))
    assert calm.action == HOLD and calm.h_breach_since_min is None
    storm = dict(base, mu_hat=-15.0, mu_t_stat=3.0)                  # strong, persistent fade
    first = decide_exit(pv(**storm), at(11, 0))
    assert first.action == HOLD and first.rule == "j_hold"           # clock armed, not fired
    assert first.h_breach_since_min == 11 * 60
    assert first.state["ev_hold"] < first.state["ev_sell"]
    later = decide_exit(pv(**storm, h_breach_since_min=first.h_breach_since_min), at(11, 20))
    assert later.action == SELL and later.rule == "h_ev_hold_below_sell", (later.rule, later.state)
    assert later.state["mu_eff"] < -4.0
    # a clean mark in between RESETS the clock (the breach must be continuous)
    clean = decide_exit(pv(**base, h_breach_since_min=11 * 60), at(11, 10))
    assert clean.h_breach_since_min is None


# --------------------------------------------------------------------- (i*) continuous P(regain)
def test_i_regain_low_mechanics_and_ordering():
    """(i*) is deliberately NARROW at the default p_regain_min=0.25: any drift adverse enough
    to crush P(regain) usually crushes EV_hold too, so (h) fires first - (i*) is the safety
    catch for the value-gone (regain_move=None) and skew corners. v3 (Wave 2.14): it fires only
    after the breach persists ev_persist_min - the first breach mark arms the clock and HOLDs."""
    # model-consistent profitable 0DTE hold: p_regain ~0.75 -> breaches when the knob is above it
    won = pv(expiry=TODAY, strike=100.0, bid=0.33, ask=0.37, entry_mid=0.12, peak_mid=0.37,
             solved_iv=0.25, mu_thesis=1.0, target_underlying=101.5)
    hold = decide_exit(won, at(14, 0))
    assert hold.action == HOLD and hold.rule == "j_hold"          # default 0.25: no breach at all
    assert hold.i_breach_since_min is None
    # knob set just above the MEASURED p_regain (the MATH-CORE-1 fix raised the level - 
    # the mechanics under test are the persistence clock + ordering, not the calibration)
    knob = min(1.0, hold.state["p_regain"] + 0.01)
    first = decide_exit(won, at(14, 0), ExitParams(p_regain_min=knob))
    assert first.action == HOLD and first.i_breach_since_min == 14 * 60   # armed, not fired
    d = decide_exit(PositionView(**{**won.__dict__, "i_breach_since_min": 14 * 60}),
                    at(14, 20), ExitParams(p_regain_min=knob))
    assert d.action == SELL and d.rule == "i_regain_low", (d.rule, d.state)
    assert d.state["profit_present"] is True and d.state["p_regain"] < knob


def test_i_regain_never_fires_on_losers():
    # owner directive: losers exit via thesis/theta/EV/clocks, NEVER via a value-gone test - 
    # the profit_present gate makes (i*) a profit-taking rule only
    stuck = pv(strike=105.0, bid=0.55, ask=0.61, entry_mid=0.9, peak_mid=0.95,
               target_underlying=106.0, mu_thesis=15.0, expiry=TOMORROW)
    for when in (at(9, 36), at(11, 0), at(14, 0)):
        d = decide_exit(stuck, when)
        assert d.rule != "i_regain_low"


def test_i_regain_never_sells_a_winner_on_degenerate_inputs():
    # W2 refute (2026-07-10): a DIRECT caller with S=0 or a NaN drift estimate must never trip
    # (i*) on a fictional p_regain=0 - the runner filters these, a replay caller might not
    won = dict(strike=100.0, bid=1.48, ask=1.52, entry_mid=0.5, peak_mid=1.55,
               solved_iv=0.25, mu_thesis=1.0, target_underlying=101.5)
    d0 = decide_exit(pv(**won, S=0.0), at(11, 0))
    assert d0.rule != "i_regain_low"
    d1 = decide_exit(pv(**won, mu_hat=float("nan"), mu_t_stat=1.0), at(11, 0))
    assert d1.rule != "i_regain_low"
    d2 = decide_exit(pv(**won, mu_hat=1.0, mu_t_stat=float("inf")), at(11, 0))
    assert d2.rule != "i_regain_low"


def test_i_regain_respects_stale_iv_sentinel():
    # a degraded IV solve (sentinel 1e-4) must never sell a winner on fictional math
    won = pv(expiry=TODAY, strike=100.0, bid=1.48, ask=1.52, entry_mid=0.5, peak_mid=1.55,
             solved_iv=1e-4, mu_thesis=0.5, target_underlying=101.0)
    d = decide_exit(won, at(14, 0))
    assert d.rule != "i_regain_low"


def test_i_regain_holds_when_value_is_repeatable():
    # a small profit with plenty of life left: P(regain) is high -> no profit-taking
    mild = pv(bid=2.08, ask=2.12, entry_mid=2.0, peak_mid=2.12,
              mu_thesis=4.0, target_underlying=102.0)
    d = decide_exit(mild, at(11, 0))
    assert d.rule != "i_regain_low"
    assert d.state["p_regain"] >= 0.25


# --------------------------------------------------------------------- events + EV rules
def test_e_event_straddle_always_out_at_tminus1():
    d = decide_exit(pv(is_event_straddle=True, event_tminus1_close=True,
                       bid=2.40, ask=2.50, peak_mid=2.45), at(15, 30))
    assert d.action == SELL and d.rule == "e_event_straddle_tminus1"


def test_f_post_print_forced_decision():
    dying = pv(minutes_since_print=20, mu_thesis=0.0, iv_trend_per_hour=-0.04,
               target_underlying=101.0)
    d = decide_exit(dying, at(10, 5))
    assert d.action == SELL and d.rule == "f_post_print_no_edge"


def test_g_theta_dominance_needs_two_cycles_and_weak_target():
    otm = pv(expiry=TODAY, strike=101.0, bid=0.14, ask=0.16, entry_mid=0.20, peak_mid=0.22,
             target_underlying=115.0, mu_thesis=0.0)
    d1 = decide_exit(otm, at(14, 30))
    assert d1.theta_share_breaches >= 1
    d2 = decide_exit(PositionView(**{**otm.__dict__, "theta_share_breaches": d1.theta_share_breaches}),
                     at(14, 32))
    assert d2.action == SELL and d2.rule == "g_theta_dominates"


def test_h_optimal_stopping_ignores_entry_price():
    # v3: the h breach must have persisted ev_persist_min (carried clock) before it may fire
    dying = pv(mu_thesis=0.0, iv_trend_per_hour=-0.04, target_underlying=101.0,
               h_breach_since_min=10 * 60 + 40)
    d = decide_exit(dying, at(11, 0))
    assert d.action == SELL and d.rule == "h_ev_hold_below_sell"
    # identical mark, wildly different entry -> IDENTICAL EV + regain + mu inputs (only the
    # explicitly cost-relative fields may differ)
    d2 = decide_exit(PositionView(**{**dying.__dict__, "entry_mid": 0.5, "peak_mid": 4.0}), at(11, 0))
    for key in ("ev_hold", "ev_sell", "p_regain", "mu_eff", "p_target_eff"):
        assert d2.state[key] == d.state[key], key
    assert d2.action == SELL


def test_j_healthy_hold_logs_full_state():
    d = decide_exit(pv(mu_thesis=4.0, target_underlying=101.0), at(11, 0))
    assert d.action == HOLD and d.rule == "j_hold"
    for key in ("p_target_mu0", "p_target_thesis", "p_target_eff", "theta_share",
                "ev_hold", "ev_hold_thesis", "ev_hold_mu0", "ev_sell", "p_regain",
                "regain_pct", "mu_hat", "mu_t_stat", "mu_eff", "profit_present",
                "d2_armed", "opposing_defense", "iv_trend_hr", "vehicle_mismatch"):
        assert key in d.state, key


def test_first_match_precedence():
    mess = pv(expiry=TODAY, thesis_valid=False, bid=0.40, ask=0.44)
    d = decide_exit(mess, at(15, 10))
    assert d.rule == "a_zero_dte_clock"


# --------------------------------------------------------------------- policy clocks
def test_winner_still_flat_at_eod_checkpoint():
    winner = pv(bid=4.00, ask=4.10, peak_mid=4.1, target_underlying=100.6)
    d = decide_exit(winner, at(15, 50))
    assert d.action == SELL and d.rule == "overnight_evidence_rule"


def test_overnight_evidence_rule_and_variant_flag():
    # variant_would_hold reflects the CURRENT engine's EV view: give it live favorable drift
    # (mu_hat 15 @ t=3, tau=5 -> mu_eff ~ 8.75) so ev_hold > ev_sell at the checkpoint
    d = decide_exit(pv(expiry=TOMORROW, mu_thesis=5.0, mu_hat=15.0, mu_t_stat=3.0), at(15, 50))
    assert d.action == SELL and d.rule == "overnight_evidence_rule"
    assert d.variant_would_hold is True
    assert d.variant_would_hold == (d.state["ev_hold"] > d.state["ev_sell"])
    okpv = pv(expiry=date(2026, 7, 17), strike=94.0, bid=6.4, ask=6.6, entry_mid=6.0,
              peak_mid=6.5, named_catalyst_tomorrow=True, mu_thesis=5.0)
    d2 = decide_exit(okpv, at(15, 50))
    assert d2.rule != "overnight_evidence_rule"
    fripv = pv(expiry=date(2026, 7, 22), strike=94.0, bid=6.4, ask=6.6, entry_mid=6.0,
               peak_mid=6.5, named_catalyst_tomorrow=True, is_friday=True, mu_thesis=5.0)
    d3 = decide_exit(fripv, FRIDAY_DT)
    assert d3.action == SELL and d3.rule == "overnight_evidence_rule"


def test_print_window_flat_never_holds_through_a_print():
    d = decide_exit(pv(minutes_to_next_print=7, mu_thesis=4.0, target_underlying=101.0),
                    at(13, 52))
    assert d.action == SELL and d.rule == "print_window_flat"
    d2 = decide_exit(pv(minutes_to_next_print=45, mu_thesis=4.0, target_underlying=101.0),
                     at(13, 15))
    assert d2.rule != "print_window_flat"
    # a big winner carrying maximum premium into the print is exactly the one that must flatten
    d3 = decide_exit(pv(bid=5.60, ask=5.70, peak_mid=6.0, target_underlying=100.6,
                        minutes_to_next_print=7), at(13, 52))
    assert d3.action == SELL and d3.rule == "print_window_flat"


def test_planned_exit_defers_checkpoint_then_flattens():
    healthy = pv(mu_thesis=4.0, target_underlying=101.0, planned_exit_minute=955)
    d = decide_exit(healthy, at(15, 50))
    assert d.rule not in ("overnight_evidence_rule", "planned_exit_flat")
    d2 = decide_exit(healthy, at(15, 56))
    assert d2.action == SELL and d2.rule == "planned_exit_flat"
    d4 = decide_exit(pv(mu_thesis=4.0, target_underlying=101.0), at(15, 50))
    assert d4.action == SELL and d4.rule == "overnight_evidence_rule"


# --------------------------------------------------------------------- late-close mode
def test_for_close_byte_identity_and_half_day_derivation():
    assert ExitParams.for_close(960) == ExitParams()
    assert SelectorParams.for_close(960) == SelectorParams()
    h = ExitParams.for_close(780)
    assert (h.zero_dte_sell_min, h.zero_dte_deep_itm_ext_min, h.eod_flat_min,
            h.planned_exit_cap_min) == (720, 750, 765, 779)
    assert h.session_close_min == 780 and h.late_close_flat_min == 790
    sh = SelectorParams.for_close(780)
    assert sh.no_0dte_after_min == 660 and sh.session_close_min == 780


def test_after_hours_restricted_ladder():
    base = dict(after_hours=True)
    # (c) premium stop: inert at the None default, fires after hours when explicitly set
    d0 = decide_exit(pv(bid=0.93, ask=0.99, **base), at(16, 2))
    assert d0.action == HOLD and d0.rule == "ah_hold"
    d = decide_exit(pv(bid=0.93, ask=0.99, **base), at(16, 2), ExitParams(stop_frac=-0.50))
    assert d.action == SELL and d.rule == "c_premium_stop"
    # a +100% winner does NOT take profit after hours (no take exists; EV states are stale)
    d3 = decide_exit(pv(bid=4.00, ask=4.10, peak_mid=4.1, target_underlying=100.6, **base),
                     at(16, 2))
    assert d3.action == HOLD and d3.rule == "ah_hold" and d3.state.get("after_hours") is True
    # thesis invalidation is fiction on frozen bars - (b) must NOT fire
    d4 = decide_exit(pv(thesis_valid=False, **base), at(16, 2))
    assert d4.rule == "ah_hold"
    # d2* cost-basis backstop still protects on live NBBO
    d5 = decide_exit(pv(bid=1.98, ask=2.02, peak_mid=3.6, entry_ask=2.05, peak_bid=3.50, **base),
                     at(16, 2))
    assert d5.action == SELL and d5.rule == "d2_costbasis_backstop"
    # 0DTE somehow alive after the close: no a_zero_dte_clock on stale state
    d6 = decide_exit(pv(expiry=TODAY, **base), at(16, 2))
    assert d6.rule in ("ah_hold",)


def test_late_close_flat_cap_normal_and_half_day():
    d = decide_exit(pv(after_hours=True), at(16, 10))
    assert d.action == SELL and d.rule == "late_close_flat"
    d2 = decide_exit(pv(after_hours=True), at(16, 9))
    assert d2.action == HOLD and d2.rule == "ah_hold"
    half = ExitParams.for_close(780)
    d3 = decide_exit(pv(after_hours=True), at(13, 10), half)
    assert d3.action == SELL and d3.rule == "late_close_flat"
    d4 = decide_exit(pv(after_hours=True), at(13, 9), half)
    assert d4.rule == "ah_hold"
    d5 = decide_exit(pv(after_hours=True, planned_exit_minute=955), at(16, 2))
    assert d5.action == SELL and d5.rule == "planned_exit_flat"


def test_after_hours_overnight_grant_outrides_late_close_flat():
    ok = pv(expiry=date(2026, 7, 17), strike=94.0, bid=6.4, ask=6.6, entry_mid=6.0,
            peak_mid=6.5, named_catalyst_tomorrow=True, after_hours=True)
    d = decide_exit(ok, at(16, 12))
    assert d.action == HOLD and d.rule == "overnight_grant_hold"
    fri = pv(expiry=date(2026, 7, 22), strike=94.0, bid=6.4, ask=6.6, entry_mid=6.0,
             peak_mid=6.5, named_catalyst_tomorrow=True, is_friday=True, after_hours=True)
    d2 = decide_exit(fri, FRIDAY_DT.replace(hour=16, minute=12))
    assert d2.action == SELL and d2.rule == "late_close_flat"
    otm = pv(expiry=date(2026, 7, 17), strike=110.0, bid=0.2, ask=0.3, entry_mid=0.5,
             peak_mid=0.5, named_catalyst_tomorrow=True, after_hours=True)
    d3 = decide_exit(otm, at(16, 12))
    assert d3.action == SELL and d3.rule == "late_close_flat"


def test_after_hours_tolerates_zero_S():
    d = decide_exit(pv(after_hours=True, S=0.0), at(16, 5))
    assert d.action == HOLD and d.rule == "ah_hold"
