"""THE INCIDENT REGRESSION (2026-07-10) - REPINNED TO EXIT-ENGINE v3 (2026-07-17,
opts-audit-wave2-exitv3-v1).

The real trade: IWM 298P 0DTE, entered ~09:40 ET @ ~$1.95 on the 2026-07-10 lane-1 put signal.
By 10:30 IWM hit its session low and the put marked ~+71%; from ~10:35 IWM reclaimed and the
put faded. The ORIGINAL pin (v2) required a SELL inside [10:35, 10:55] on the reclaim - but
the 2026-07-16 audit proved (TRAJECTORY-1, 4/4 independent refuters, Monte Carlo through the
real decide_exit) that the mechanism behind that fast exit was a NOISE CLOCK: the reclaim's
20-minute drift evidence is ~1 sigma - statistically indistinguishable from the wiggles that
forced random sales within ~30 minutes of ANY entry. The rules file that made the fast-exit
process authoritative (OWNER_RULES.md) was retracted the same day (docs/OWNER_RULES_RETRACTED.md).

v3 pins (each registered):
  1. UNCHANGED - the engine HOLDS through the entire run-up: no premium threshold may ever
     force a take. THE anti-hallucination pin survives every rework.
  2. NEW - a ~1-sigma reclaim is NOISE: the variance-scaled blend keeps mu_eff pinned to the
     entry-consistent prior (w = tau^2/(tau^2+SE^2) with SE ~ 21/yr vs tau ~ 1.35), and the
     statistical exits (h/i*) require a 20-minute persistent breach. v3 deliberately HOLDS
     where v2 noise-sold.
  3. NEW - the engine still harvests/protects at the CLOCK scale: on the extended real-shaped
     path (fade through the afternoon) it exits via the registered clock/backstop family by
     the 0DTE 15:00 sell clock at the latest.
  4. The frozen v1 engine still runs the identical path through ITS rules (trail family) - 
     the v1-vs-v3 divergence is measured by the repaired paired-replay lab on real quote
     paths, not asserted as dominance here (the old "v2 strictly dominates" pin was an
     artifact of pinning the noise clock as truth).
"""

from __future__ import annotations

from datetime import date, datetime

from atlas.options import exit_engine as v2
from atlas.options import exit_engine_legacy as v1
from atlas.options.trajectory import underlying_state
from atlas.options.vendor.blackscholes import implied_vol
from atlas.options.vendor.models import OptionType

DAY = date(2026, 7, 10)          # the real Friday (0DTE expiry)
STRIKE = 298.0
ENTRY_MID = 1.95
ENTRY_ASK = 1.97

# (minute-of-day ET, S, put bid, put ask) - 5-minute marks distilled from the real session
PATH = [
    (585, 296.30, 1.93, 1.97),   # 09:45 (first mark after the 09:40 entry)
    (590, 296.57, 1.66, 1.74),   # 09:50 pop against the put
    (595, 296.29, 1.85, 1.93),
    (600, 296.06, 2.04, 2.12),   # 10:00
    (605, 295.55, 2.13, 2.21),
    (610, 295.05, 2.59, 2.67),   # 10:10
    (615, 294.55, 2.50, 2.58),
    (620, 294.20, 2.75, 2.83),   # 10:20
    (625, 293.90, 3.02, 3.12),
    (630, 293.75, 3.28, 3.40),   # 10:30 - session low zone; ~+71% on the mid
    (635, 294.30, 2.56, 2.64),   # reclaim bar 1 (strength at 294.5-295 building)
    (640, 294.70, 2.38, 2.46),   # reclaim bar 2
    (645, 294.90, 2.28, 2.36),
    (650, 295.15, 2.10, 2.18),   # 10:50 - the level held; uptrend likely
    (655, 295.30, 2.02, 2.10),
    # v3 extension: the afternoon fade at the real day's shape - the put decays toward
    # intrinsic as IWM stabilizes above the strike zone; the 0DTE clock closes the trade
    (700, 295.60, 1.96, 2.04),   # 11:40
    (780, 295.90, 1.90, 1.98),   # 13:00
    (840, 296.10, 1.86, 1.94),   # 14:00
    (895, 296.20, 1.84, 1.92),   # 14:55
    (900, 296.25, 1.83, 1.91),   # 15:00 - base 0DTE clock (deep-ITM extends to 15:30)
    (930, 296.30, 1.80, 1.88),   # 15:30 - the deep-ITM extension boundary
    (935, 296.32, 1.79, 1.87),   # guard mark just past the extension
]
MU_THESIS = -1.349               # the real lane-1 signal's mu (journal, 2026-07-10)


def _minute_series(upto_idx: int) -> tuple[list, list]:
    """1-min interpolated closes through PATH[upto_idx] for the trajectory estimator. The
    backdrop carries the REAL 09:30-09:40 decline (open 297.71 -> 296.11) - that down-drift is
    the evidence that fired the put in the first place, and the early marks' trailing windows
    must see it exactly as the live builder would have."""
    anchors = [(570, 297.71), (572, 297.30), (575, 296.90), (578, 296.45), (580, 296.11)]
    anchors += [(m, s) for m, s, _, _ in PATH[: upto_idx + 1]]
    mins, closes = [anchors[0][0]], [anchors[0][1]]
    for (m0, s0), (m1, s1) in zip(anchors, anchors[1:]):
        steps = m1 - m0
        for k in range(1, steps + 1):
            mins.append(m0 + k)
            closes.append(s0 + (s1 - s0) * k / steps)
    return mins, closes


def _views(engine_module):
    """Yield (minute, mid, decision) running the path through the given engine - carrying the
    engine's own state exactly like the runner (breach cycles, v3 persistence clocks, the v1
    trail latch)."""
    params = engine_module.ExitParams()
    breaches = 0
    trailing = False
    h_since = i_since = None
    peak_mid = ENTRY_MID
    peak_bid = 0.0
    for idx, (minute, S, bid, ask) in enumerate(PATH):
        mid = (bid + ask) / 2.0
        peak_mid = max(peak_mid, mid)
        peak_bid = max(peak_bid, bid)
        T = max((960 - minute) / 390.0 / 252.0, 1e-7)
        try:
            iv = implied_vol(mid, S, STRIKE, 0.04, 0.0, T, OptionType.PUT) or 0.30
        except Exception:
            iv = 0.30
        mins, closes = _minute_series(idx)
        under = underlying_state(mins, closes, iv=iv, window_min=20)
        kw = dict(occ="IWM   260710P00298000", underlying="IWM", opt_type="put",
                  strike=STRIKE, expiry=DAY, entry_mid=ENTRY_MID, peak_mid=peak_mid,
                  lane="index_trend", target_underlying=294.74,   # the real signal's target
                  mu_thesis=MU_THESIS, thesis_valid=True, entry_ts_min=580,
                  S=S, bid=bid, ask=ask, solved_iv=iv, iv_trend_per_hour=0.0,
                  theta_share_breaches=breaches)
        if engine_module is v2:
            kw.update(entry_ask=ENTRY_ASK, peak_bid=peak_bid,
                      mu_hat=under.mu_hat, mu_t_stat=under.t_stat,
                      h_breach_since_min=h_since, i_breach_since_min=i_since)
        else:
            kw.update(trailing=trailing)
        pv = engine_module.PositionView(**kw)
        now = datetime(2026, 7, 10, minute // 60, minute % 60)
        d = engine_module.decide_exit(pv, now, params)
        breaches = d.theta_share_breaches
        h_since = getattr(d, "h_breach_since_min", None)
        i_since = getattr(d, "i_breach_since_min", None)
        if engine_module is v1:
            trailing = bool(trailing or getattr(d, "trailing", False))
        yield minute, mid, d
        if d.action == "SELL":
            return


def test_v3_holds_runup_ignores_noise_reclaim_and_exits_on_the_clock():
    """v3 pins 1-3 (see module docstring): no forced take on the run-up; a ~1-sigma reclaim is
    noise (mu_eff stays prior-pinned, h/i* need 20-min persistence); the trade still closes
    via the registered clock/backstop family by the 0DTE sell clock."""
    sells = []
    last_hold_state = None
    for minute, mid, d in _views(v2):
        if minute <= 630:
            assert d.action == "HOLD", (minute, d.rule, d.state)   # no forced take, ever
        if 635 <= minute <= 655:
            # THE REPIN: v2 noise-sold here; v3 holds - the reclaim's 20-min evidence is ~1
            # sigma and the variance-scaled blend refuses to flip the drift on it
            assert d.action == "HOLD", (minute, d.rule, d.state)
            assert abs(d.state["mu_eff"] - d.state["mu_prior"]) < 0.35, d.state
        if d.action == "HOLD":
            last_hold_state = d.state
        else:
            sells.append((minute, mid, d))
    assert sells, "the engine must still close a 0DTE by its sell clock"
    minute, mid, d = sells[0]
    assert d.rule in ("a_zero_dte_clock", "d2_costbasis_backstop", "g_theta_dominates",
                      "h_ev_hold_below_sell", "i_regain_low"), (minute, d.rule)
    assert minute <= 930, (minute, d.rule)     # never past the deep-ITM-extended 0DTE clock
    assert last_hold_state is not None and last_hold_state["evidence_stale"] is False


def test_legacy_engine_still_replays_the_same_path_through_v1_rules():
    """The frozen v1 baseline keeps replaying the identical path through ITS rule set (the
    trail family) - the lab measures the v1-vs-v3 divergence on real stored paths; this test
    only pins that both engines complete the path deterministically with their own rules."""
    v3_exit = None
    for minute, mid, d in _views(v2):
        if d.action == "SELL":
            v3_exit = (minute, mid, d.rule)
    v1_exit = None
    for minute, mid, d in _views(v1):
        if d.action == "SELL":
            v1_exit = (minute, mid, d.rule)
    assert v3_exit is not None
    assert v1_exit is not None, "the v1 trail family exits this fade by construction"
    v1_rules = {"d_take_profit", "d_trail_giveback", "d2_breakeven_backstop",
                "a_zero_dte_clock", "h_ev_hold_below_sell", "i_regain_unreachable",
                "i_regain_gone", "g_theta_dominates", "overnight_evidence_rule"}
    assert v1_exit[2] in v1_rules, v1_exit
    # the registered divergence exists and is visible (rules differ or timing differs)
    assert (v1_exit[0], v1_exit[2]) != (v3_exit[0], v3_exit[2]), (v1_exit, v3_exit)
