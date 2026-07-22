# LEGACY PINS - frozen 2026-07-10 with exit_engine_legacy.py (the paired-replay A/B baseline).
# These tests protect the FROZEN v1 engine byte-for-byte, INCLUDING the +100% forced take that
# the owner ordered removed from the live engine (it exists here only so old-vs-new is measurable).
# Do not update these when the live engine changes - they pin the baseline, not the product.
"""Exit engine (O2): the first-match action matrix - every rule (a..j, d2, overnight) fired in
isolation, precedence when several match, the trail-hold carve-out, breach carry-forward, and
the variant_would_hold divergence flag for the owner's overnight arm.
"""

from __future__ import annotations

from datetime import date, datetime

from atlas.options.exit_engine_legacy import (HOLD, SELL, ExitParams, PositionView, decide_exit)
from atlas.options.selector import SelectorParams
from atlas.options.vendor.blackscholes import bs_price
from atlas.options.vendor.models import OptionType

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


def test_c_premium_stop():
    # INERT by default (opts-tweak-disable-premium-stop-v1, owner 2026-07-10: never exit just
    # because the premium is lower now) - a -52% mid must NOT trip a price stop...
    d0 = decide_exit(pv(bid=0.93, ask=0.99), at(11, 0))
    assert d0.rule != "c_premium_stop"
    # ...but the rule stays functional when a stop is explicitly set (the replay-variant knob)
    d = decide_exit(pv(bid=0.93, ask=0.99), at(11, 0), ExitParams(stop_frac=-0.50))
    assert d.action == SELL and d.rule == "c_premium_stop"


def test_d_take_trail_and_giveback():
    # +100% with target essentially unreachable -> TAKE
    won = pv(bid=4.00, ask=4.10, peak_mid=4.1, target_underlying=140.0)
    d = decide_exit(won, at(11, 0))
    assert d.action == SELL and d.rule == "d_take_profit"
    # +100% with target close (strong P_target) -> TRAIL-HOLD
    trailing = pv(bid=4.00, ask=4.10, peak_mid=4.1, target_underlying=100.6)
    d2 = decide_exit(trailing, at(11, 0))
    assert d2.action == HOLD and d2.rule == "d_trailing_hold" and d2.state.get("trailing")
    # trail give-back: peak 6.0, mid 4.05 -> more than 25% off peak -> SELL
    gave = pv(bid=4.00, ask=4.10, peak_mid=6.0, target_underlying=100.6)
    d3 = decide_exit(gave, at(11, 0))
    assert d3.action == SELL and d3.rule == "d_trail_giveback"


def test_d2_breakeven_backstop_protects_a_50pct_winner():
    # peaked at +80%, now back at entry -> rule 23: never let the winner become a loser
    d = decide_exit(pv(bid=1.98, ask=2.02, peak_mid=3.6), at(11, 0))
    assert d.action == SELL and d.rule == "d2_breakeven_backstop"


def test_e_event_straddle_always_out_at_tminus1():
    d = decide_exit(pv(is_event_straddle=True, event_tminus1_close=True,
                       bid=2.40, ask=2.50, peak_mid=2.45), at(15, 30))
    assert d.action == SELL and d.rule == "e_event_straddle_tminus1"


def test_overnight_evidence_rule_and_variant_flag():
    # DTE=1 at 15:50 -> evidence rule sells; strong thesis => the unrestricted arm would hold
    d = decide_exit(pv(expiry=TOMORROW, mu_thesis=5.0), at(15, 50))
    assert d.action == SELL and d.rule == "overnight_evidence_rule"
    assert d.variant_would_hold is True
    # exception path: DTE>=3, deep delta, named catalyst, not Friday -> allowed through
    okpv = pv(expiry=date(2026, 7, 17), strike=94.0, bid=6.4, ask=6.6, entry_mid=6.0,
              peak_mid=6.5, named_catalyst_tomorrow=True, mu_thesis=5.0)
    d2 = decide_exit(okpv, at(15, 50))
    assert d2.rule != "overnight_evidence_rule"
    # Friday kills the exception (never over a weekend)
    fripv = pv(expiry=date(2026, 7, 22), strike=94.0, bid=6.4, ask=6.6, entry_mid=6.0,
               peak_mid=6.5, named_catalyst_tomorrow=True, is_friday=True, mu_thesis=5.0)
    d3 = decide_exit(fripv, FRIDAY_DT)
    assert d3.action == SELL and d3.rule == "overnight_evidence_rule"


def test_g_theta_dominance_needs_two_cycles_and_weak_target():
    # slightly-OTM 0DTE at 14:30: the afternoon theta multiplier makes decay dominate direction,
    # and the target is hopeless -> rule (g) once the breach persists two cycles
    otm = pv(expiry=TODAY, strike=101.0, bid=0.14, ask=0.16, entry_mid=0.20, peak_mid=0.22,
             target_underlying=115.0, mu_thesis=0.0)
    d1 = decide_exit(otm, at(14, 30))
    assert d1.theta_share_breaches >= 1                        # first breach recorded
    d2 = decide_exit(PositionView(**{**otm.__dict__, "theta_share_breaches": d1.theta_share_breaches}),
                     at(14, 32))
    assert d2.action == SELL and d2.rule == "g_theta_dominates"


def test_h_optimal_stopping_ignores_entry_price():
    # dead thesis (mu 0), IV falling: EV_hold < EV_sell regardless of entry price
    dying = pv(mu_thesis=0.0, iv_trend_per_hour=-0.04, target_underlying=101.0)
    d = decide_exit(dying, at(11, 0))
    assert d.action == SELL and d.rule == "h_ev_hold_below_sell"
    # identical mark, wildly different entry -> IDENTICAL hold/sell EV inputs (rule h sees no
    # entry price; the stop/take/backstop rules are legitimately entry-relative and fire earlier)
    d2 = decide_exit(PositionView(**{**dying.__dict__, "entry_mid": 0.5, "peak_mid": 4.0}), at(11, 0))
    assert d2.state["ev_hold"] == d.state["ev_hold"]
    assert d2.state["ev_sell"] == d.state["ev_sell"]
    assert d2.action == SELL


def test_i_regain_rule_fires_at_daily_recheck_only():
    # decayed OTM: regaining today's value tomorrow needs a move >> 1.5x daily expected move
    # rule (i) is the anti-treadmill guard: it exists for the case rule (h) can NOT catch - a
    # thesis so aggressive that EV_hold stays above EV_sell, while merely staying FLAT by
    # tomorrow still demands a move >> 1.5x the daily expected move. Only the 09:35 re-decision
    # window may fire it.
    stuck = pv(strike=105.0, bid=0.55, ask=0.61, entry_mid=0.9, peak_mid=0.95,
               target_underlying=106.0, mu_thesis=15.0, expiry=TOMORROW)
    at_recheck = decide_exit(stuck, at(9, 36))
    midday = decide_exit(stuck, at(11, 0))
    assert at_recheck.action == SELL and at_recheck.rule.startswith("i_regain"), at_recheck.rule
    assert not midday.rule.startswith("i_regain")              # i_* exists only at the recheck


def test_j_healthy_hold_logs_full_state():
    d = decide_exit(pv(mu_thesis=4.0, target_underlying=101.0), at(11, 0))
    assert d.action == HOLD and d.rule == "j_hold"
    for key in ("p_target_mu0", "p_target_thesis", "theta_share", "ev_hold", "ev_sell",
                "regain_pct", "iv_trend_hr", "vehicle_mismatch"):
        assert key in d.state


def test_first_match_precedence():
    # 0DTE clock + invalid thesis + stop breach simultaneously -> rule (a) wins
    mess = pv(expiry=TODAY, thesis_valid=False, bid=0.40, ask=0.44)
    d = decide_exit(mess, at(15, 10))
    assert d.rule == "a_zero_dte_clock"


def test_d_trail_latch_survives_sag_below_take():
    # 2026-07-09 audit fix: unlatched, the giveback level peak*(0.75) was unreachable for any
    # peak < 2.667x entry because the ret>=+100% precondition died first - a trailing winner
    # would bleed from peak to breakeven (d2) instead of losing 25% off peak.
    # Armed earlier (runner-persisted latch), now sagged to +40%: the trail still governs.
    sagged = pv(bid=2.75, ask=2.85, peak_mid=6.0, target_underlying=100.6, trailing=True)
    d = decide_exit(sagged, at(11, 0))
    assert d.action == SELL and d.rule == "d_trail_giveback"
    # latched and above the giveback line -> the trail's HOLD, and the latch carries forward
    riding = pv(bid=5.60, ask=5.70, peak_mid=6.0, target_underlying=100.6, trailing=True)
    d2 = decide_exit(riding, at(11, 0))
    assert d2.action == HOLD and d2.rule == "d_trailing_hold" and d2.trailing is True


def test_trailing_winner_still_flat_at_eod_checkpoint():
    # 2026-07-09 audit fix: the trailing HOLD used to be returned before the 15:45 checkpoint,
    # so a DTE 1-2 trailing winner rode overnight (and over weekends) unrecorded.
    trailing = pv(bid=4.00, ask=4.10, peak_mid=4.1, target_underlying=100.6)
    d = decide_exit(trailing, at(15, 50))
    assert d.action == SELL and d.rule == "overnight_evidence_rule"


def test_trailing_winner_never_holds_through_a_print():
    # 2026-07-09 refute fix: the trailing branch honored the 15:45 checkpoint but returned its
    # HOLD before the print-window check - the position carrying the most premium into an
    # IV-crush event was exactly the one that rode through it. The trail bypasses EV/theta
    # rules, never the survival clocks.
    riding = pv(bid=5.60, ask=5.70, peak_mid=6.0, target_underlying=100.6,
                trailing=True, minutes_to_next_print=7)
    d = decide_exit(riding, at(13, 52))
    assert d.action == SELL and d.rule == "print_window_flat"


def test_print_window_flat_never_holds_through_a_print():
    # plan hard rule "never hold long premium through a print" - engine-enforced from the
    # runner's minutes_to_next_print input (2026-07-09 audit fix: it was a hardcoded stub)
    d = decide_exit(pv(minutes_to_next_print=7, mu_thesis=4.0, target_underlying=101.0),
                    at(13, 52))
    assert d.action == SELL and d.rule == "print_window_flat"
    d2 = decide_exit(pv(minutes_to_next_print=45, mu_thesis=4.0, target_underlying=101.0),
                     at(13, 15))
    assert d2.rule != "print_window_flat"


def test_planned_exit_defers_checkpoint_then_flattens():
    # owner 2026-07-09 night (opts-tweak-planned-exit-v1): a lane-designed same-day exit
    # (last30/macro 15:55) supersedes the 15:45 checkpoint - "don't cut off early, running
    # later is better". Only the CLOCK defers; EV rules may still sell earlier on merit.
    healthy = pv(mu_thesis=4.0, target_underlying=101.0, planned_exit_minute=955)
    d = decide_exit(healthy, at(15, 50))
    assert d.rule not in ("overnight_evidence_rule", "planned_exit_flat")
    d2 = decide_exit(healthy, at(15, 56))
    assert d2.action == SELL and d2.rule == "planned_exit_flat"
    # the trail latch cannot outride the planned exit either
    trail = pv(bid=5.60, ask=5.70, peak_mid=6.0, target_underlying=100.6,
               trailing=True, planned_exit_minute=955)
    d3 = decide_exit(trail, at(15, 56))
    assert d3.action == SELL and d3.rule == "planned_exit_flat"
    # without a planned exit the 15:45 evidence checkpoint governs exactly as before
    d4 = decide_exit(pv(mu_thesis=4.0, target_underlying=101.0), at(15, 50))
    assert d4.action == SELL and d4.rule == "overnight_evidence_rule"


def test_f_post_print_forced_decision():
    # rule (f): >= 15 min after the print with no remaining edge -> forced SELL, named rule
    dying = pv(minutes_since_print=20, mu_thesis=0.0, iv_trend_per_hour=-0.04,
               target_underlying=101.0)
    d = decide_exit(dying, at(10, 5))
    assert d.action == SELL and d.rule == "f_post_print_no_edge"


# --------------------------------------------------------------------------- late-close mode
def test_for_close_byte_identity_and_half_day_derivation():
    # the byte-identity pin: normal days derive EXACTLY the default params
    assert ExitParams.for_close(960) == ExitParams()
    assert SelectorParams.for_close(960) == SelectorParams()
    # a 13:00 half day shifts every close-anchored clock; absolutes stay absolute
    h = ExitParams.for_close(780)
    assert (h.zero_dte_sell_min, h.zero_dte_deep_itm_ext_min, h.eod_flat_min,
            h.planned_exit_cap_min) == (720, 750, 765, 779)
    assert h.session_close_min == 780 and h.late_close_flat_min == 790
    assert h.daily_recheck_min == ExitParams().daily_recheck_min          # 09:35 is absolute
    sh = SelectorParams.for_close(780)
    assert sh.no_0dte_after_min == 660 and sh.session_close_min == 780    # 11:00 cutoff


def test_after_hours_restricted_ladder():
    # 16:02, DTE 1, S frozen: only premium-anchored rules run
    base = dict(after_hours=True)
    # (c) premium stop: inert at the None default, fires after hours when explicitly set
    d0 = decide_exit(pv(bid=0.93, ask=0.99, **base), at(16, 2))
    assert d0.action == HOLD and d0.rule == "ah_hold"
    d = decide_exit(pv(bid=0.93, ask=0.99, **base), at(16, 2), ExitParams(stop_frac=-0.50))
    assert d.action == SELL and d.rule == "c_premium_stop"
    # a latched trail's giveback fires (peak keeps updating on live mids)
    d2 = decide_exit(pv(bid=2.75, ask=2.85, peak_mid=6.0, trailing=True, **base), at(16, 2))
    assert d2.action == SELL and d2.rule == "d_trail_giveback"
    # an UNLATCHED +100% winner does NOT take profit or arm a trail (P_target is stale)
    d3 = decide_exit(pv(bid=4.00, ask=4.10, peak_mid=4.1, target_underlying=100.6, **base),
                     at(16, 2))
    assert d3.action == HOLD and d3.rule == "ah_hold" and d3.state.get("after_hours") is True
    # thesis invalidation is fiction on frozen bars - (b) must NOT fire
    d4 = decide_exit(pv(thesis_valid=False, **base), at(16, 2))
    assert d4.rule == "ah_hold"
    # d2 breakeven backstop still protects on live NBBO
    d5 = decide_exit(pv(bid=1.98, ask=2.02, peak_mid=3.6, **base), at(16, 2))
    assert d5.action == SELL and d5.rule == "d2_breakeven_backstop"
    # 0DTE somehow alive after the close: no a_zero_dte_clock on stale state - ah ladder rules
    d6 = decide_exit(pv(expiry=TODAY, **base), at(16, 2))
    assert d6.rule in ("ah_hold",)                                        # dies at 16:10 instead


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
    # a stale planned exit is honored ahead of the cap
    d5 = decide_exit(pv(after_hours=True, planned_exit_minute=955), at(16, 2))
    assert d5.action == SELL and d5.rule == "planned_exit_flat"


def test_after_hours_overnight_grant_outrides_late_close_flat():
    # refute fix 2026-07-10: the evidence rule's DTE>=3 exception was end-to-end dead code - 
    # a granted ride now holds through every after-hours mark (even past close+10) and
    # carries to tomorrow via the ledger rebuild
    ok = pv(expiry=date(2026, 7, 17), strike=94.0, bid=6.4, ask=6.6, entry_mid=6.0,
            peak_mid=6.5, named_catalyst_tomorrow=True, after_hours=True)
    d = decide_exit(ok, at(16, 12))
    assert d.action == HOLD and d.rule == "overnight_grant_hold"
    # Friday kills the grant (never any long over a weekend) -> the flat governs
    fri = pv(expiry=date(2026, 7, 22), strike=94.0, bid=6.4, ask=6.6, entry_mid=6.0,
             peak_mid=6.5, named_catalyst_tomorrow=True, is_friday=True, after_hours=True)
    d2 = decide_exit(fri, FRIDAY_DT.replace(hour=16, minute=12))
    assert d2.action == SELL and d2.rule == "late_close_flat"
    # low delta -> no grant -> the flat governs
    otm = pv(expiry=date(2026, 7, 17), strike=110.0, bid=0.2, ask=0.3, entry_mid=0.5,
             peak_mid=0.5, named_catalyst_tomorrow=True, after_hours=True)
    d3 = decide_exit(otm, at(16, 12))
    assert d3.action == SELL and d3.rule == "late_close_flat"


def test_after_hours_tolerates_zero_S():
    # worst-case restart: no backfill, S=0 - the ladder is S-free and must not crash
    d = decide_exit(pv(after_hours=True, S=0.0), at(16, 5))
    assert d.action == HOLD and d.rule == "ah_hold"

