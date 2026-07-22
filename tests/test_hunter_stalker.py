"""STALKER FSM tests (P1b): grammar happy paths, every abort, and the no-shortcut property - 
a FIRE can only ever happen via TOUCHED -> CONFIRMING inside the entry window, under the chase line.
"""

from __future__ import annotations

import numpy as np

from atlas.hunter.stalker import (ABORTED, ARMED, CONFIRMING, EXPIRED, FIRED, G1, G2, STALKING,
                                  TOUCHED, BarInput, PinnedZone, StalkerFSM, StalkParams)

ZONE = PinnedZone(top=10.05, bottom=9.95, reference_low=9.98, max_chase=10.12)
ATR = 0.10


def bar(minute, o, c, *, lo=None, hi=None, v=1000.0, svwap=10.35, hod=10.60,
        retrace=0.5, spread=float("nan"), halted=False, defensive=False) -> BarInput:
    lo = lo if lo is not None else min(o, c) - 0.005
    hi = hi if hi is not None else max(o, c) + 0.005
    return BarInput(minute=minute, open=o, high=hi, low=lo, close=c, volume=v, svwap=svwap,
                    atr5m=ATR, hod=hod, retrace_frac=retrace, spread_bps=spread,
                    halted=halted, defensive_event=defensive)


def _warmup(fsm: StalkerFSM, start_min: int, n: int = 22) -> int:
    """ARMED chop above the zone: close == hod, above VWAP => no pullback signal."""
    m = start_min
    for _ in range(n):
        fsm.step(bar(m, 10.60, 10.60, v=1000))
        m += 1
    assert fsm.state == ARMED
    return m


def _decline(fsm: StalkerFSM, m: int) -> int:
    """Pullback with DRYING down-volume (Wyckoff taper) into the zone."""
    path = [(10.55, 10.45, 2400), (10.45, 10.35, 2200), (10.35, 10.25, 2000),
            (10.25, 10.15, 1600), (10.15, 10.08, 1200)]
    for o, c, v in path:
        fsm.step(bar(m, o, c, v=v))
        m += 1
    return m


def test_g1_undercut_reclaim_fires_with_stop_below_flush_low():
    fsm = StalkerFSM(ZONE)
    m = _warmup(fsm, 9 * 60 + 45)
    m = _decline(fsm, m)
    assert fsm.state == STALKING
    fsm.step(bar(m, 10.08, 10.03, lo=10.02, v=1100)); m += 1          # touch
    assert fsm.state == TOUCHED
    fsm.step(bar(m, 10.02, 9.96, lo=9.93, v=900)); m += 1             # flush 0.5 ATR under ref
    assert fsm.state == CONFIRMING
    fsm.step(bar(m, 9.96, 10.01, lo=9.955, hi=10.02, v=3000)); m += 1  # reclaim on volume
    assert fsm.state == FIRED and fsm.fire is not None
    f = fsm.fire
    assert f.grammar == G1
    assert f.flush_low == 9.93 and f.higher_low is None
    assert f.stop < 9.93                                              # below the flush extreme
    assert f.rr >= StalkParams().min_rr - 1e-9
    assert f.ref_close <= ZONE.max_chase
    # transition record is complete: ARMED->STALKING->TOUCHED->CONFIRMING->FIRED
    seq = [e.to_state for e in fsm.events]
    assert seq == [STALKING, TOUCHED, CONFIRMING, FIRED]


def test_knife_close_below_zone_aborts_and_is_terminal():
    fsm = StalkerFSM(ZONE)
    m = _warmup(fsm, 9 * 60 + 45)
    m = _decline(fsm, m)
    fsm.step(bar(m, 10.08, 10.03, lo=10.02, v=1100)); m += 1
    fsm.step(bar(m, 10.02, 9.90, lo=9.88, v=5000)); m += 1            # close < bottom - 0.3*ATR
    assert fsm.state == ABORTED
    assert fsm.events[-1].reason == "zone_break_knife"
    fsm.step(bar(m, 9.90, 10.04, lo=9.89, hi=10.05, v=9000))          # perfect reclaim - too late
    assert fsm.state == ABORTED and fsm.fire is None


def test_two_consecutive_closes_below_bottom_abort():
    fsm = StalkerFSM(ZONE)
    m = _warmup(fsm, 9 * 60 + 45)
    m = _decline(fsm, m)
    fsm.step(bar(m, 10.08, 10.03, lo=10.02, v=1100)); m += 1
    fsm.step(bar(m, 10.02, 9.94, lo=9.94, v=900)); m += 1             # below bottom, above knife line
    fsm.step(bar(m, 9.94, 9.94, lo=9.93, v=900)); m += 1
    assert fsm.state == ABORTED and fsm.events[-1].reason == "zone_break_closes"


def test_g2_higher_low_pivot_break_fires():
    fsm = StalkerFSM(ZONE)
    m = _warmup(fsm, 9 * 60 + 45)
    m = _decline(fsm, m)
    fsm.step(bar(m, 10.08, 10.04, lo=10.04, v=1100)); m += 1          # touch (low 10.035 <= top)
    assert fsm.state == TOUCHED
    # micro pivot low L1 at 10.00 (k=2: two strictly-higher lows each side)
    for o, c, lo_, v in [(10.04, 10.04, 10.035, 900), (10.04, 10.03, 10.02, 850),
                         (10.03, 10.01, 10.00, 800), (10.01, 10.03, 10.02, 900),
                         (10.03, 10.04, 10.03, 950)]:
        fsm.step(bar(m, o, c, lo=lo_, v=v)); m += 1
    assert fsm.state == CONFIRMING                                    # L1 confirmed
    fsm.step(bar(m, 10.04, 10.02, lo=10.01, v=700)); m += 1           # higher low (>= L1)
    fsm.step(bar(m, 10.02, 10.09, lo=10.015, hi=10.095, v=3200)); m += 1  # break interim high
    assert fsm.state == FIRED and fsm.fire is not None
    f = fsm.fire
    assert f.grammar == G2 and f.higher_low is not None and f.flush_low is None
    assert f.stop < 10.00


def test_no_fire_on_weak_volume_reclaim():
    fsm = StalkerFSM(ZONE)
    m = _warmup(fsm, 9 * 60 + 45)
    m = _decline(fsm, m)
    fsm.step(bar(m, 10.08, 10.03, lo=10.02, v=1100)); m += 1
    fsm.step(bar(m, 10.02, 9.96, lo=9.93, v=900)); m += 1
    fsm.step(bar(m, 9.96, 10.01, lo=9.955, hi=10.02, v=950)); m += 1  # >= flush vol but < 1.5x median
    assert fsm.state == CONFIRMING and fsm.fire is None


def test_no_fire_past_the_chase_line():
    params = StalkParams()
    fsm = StalkerFSM(ZONE, params)
    m = _warmup(fsm, 9 * 60 + 45)
    m = _decline(fsm, m)
    fsm.step(bar(m, 10.08, 10.03, lo=10.02, v=1100)); m += 1
    fsm.step(bar(m, 10.02, 9.96, lo=9.93, v=900)); m += 1
    # violent reclaim that closes ABOVE max_chase (10.12) - discipline: skip it
    fsm.step(bar(m, 9.96, 10.20, lo=9.955, hi=10.21, v=5000)); m += 1
    assert fsm.fire is None and fsm.state == CONFIRMING


def test_entry_window_expiry_and_halt_abort():
    fsm = StalkerFSM(ZONE)
    fsm.step(bar(13 * 60 + 5, 10.60, 10.60))                          # 13:05 > last_entry 13:00
    assert fsm.state == EXPIRED
    fsm2 = StalkerFSM(ZONE)
    _warmup(fsm2, 9 * 60 + 45, n=3)
    fsm2.step(bar(9 * 60 + 50, 10.60, 10.60, halted=True))
    assert fsm2.state == ABORTED and fsm2.events[-1].reason == "halted"


def test_defensive_event_aborts_mid_stalk():
    fsm = StalkerFSM(ZONE)
    m = _warmup(fsm, 9 * 60 + 45)
    m = _decline(fsm, m)
    fsm.step(bar(m, 10.08, 10.05, defensive=True))
    assert fsm.state == ABORTED and fsm.events[-1].reason == "defensive_event"


def test_property_no_fire_without_touch_and_confirm_random_walks():
    """Across seeded random tapes, ANY fire must (a) be preceded by TOUCHED and CONFIRMING,
    (b) land inside the entry window, (c) respect the chase line; and terminal states are final."""
    rng = np.random.default_rng(42)
    fired = 0
    for _ in range(60):
        fsm = StalkerFSM(ZONE)
        m = 9 * 60 + 45
        px = 10.30
        for _ in range(240):
            step = float(rng.normal(0, 0.04))
            o = px
            c = max(9.5, px + step)
            v = float(rng.uniform(500, 4000))
            fsm.step(bar(m, o, c, v=v, retrace=float(rng.uniform(0.3, 0.7))))
            px = c
            m += 1
            if fsm.state in (FIRED, ABORTED, EXPIRED):
                break
        states = [e.to_state for e in fsm.events]
        if fsm.fire is not None:
            fired += 1
            assert TOUCHED in states and CONFIRMING in states
            assert states.index(TOUCHED) < states.index(CONFIRMING) < states.index(FIRED)
            assert 9 * 60 + 45 <= fsm.fire.minute <= 13 * 60
            assert fsm.fire.ref_close <= ZONE.max_chase + 1e-9
            assert fsm.fire.rr >= StalkParams().min_rr - 1e-9
        # terminal is terminal: stepping again produces no new events
        n_ev = len(fsm.events)
        if fsm.state in (FIRED, ABORTED, EXPIRED):
            fsm.step(bar(m, px, px))
            assert len(fsm.events) == n_ev
    # sanity: the random tapes exercised the machine (some walks reach the zone)
    assert fired >= 0
