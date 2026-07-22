"""LANE DETECTORS (O3): crafted bar sequences, no network. Per lane: trigger fires, the
vol-condition gate blocks, invalidation flips, one-per-side-per-day dedup."""

from __future__ import annotations

import pandas as pd

from atlas.options.lanes import (FIRST5_UCURVE_FRAC, IndexTrendLane, InPlayCandidate,
                                 InPlayORBLane, Last30Lane, MacroReactionLane, MinuteCtx,
                                 NoiseProfile, PositionCtx, PreEarningsStubLane,
                                 build_noise_profile)

SYM = "SPY"


def profile(*, pct=80.0, noise=0.002, remaining=0.01, adr=0.01, first5=1_000_000.0):
    minutes = tuple(range(570, 960))
    return NoiseProfile(symbol=SYM, minutes=minutes,
                        noise_by_minute=tuple(noise for _ in minutes),
                        remaining_range_by_minute=tuple(remaining for _ in minutes),
                        avg_daily_range=adr, range_percentile_14d=pct,
                        avg_first5_volume=first5, n_days=14)


def ctx(minute, close, *, sym=SYM, open_=None, high=None, low=None, vol=1000.0,
        session_open=100.0, svwap=100.0, blackout=None):
    o = open_ if open_ is not None else close
    return MinuteCtx(symbol=sym, minute=minute, open=o, high=high if high is not None else max(o, close),
                     low=low if low is not None else min(o, close), close=close, volume=vol,
                     session_open=session_open, svwap=svwap, blackout=blackout)


def pctx(direction, close, *, sym=SYM, minute=700, svwap=100.0, session_open=100.0):
    return PositionCtx(symbol=sym, direction=direction, minute=minute, close=close,
                       svwap=svwap, session_open=session_open)


# ------------------------------------------------------------------ Lane 1: index_trend
def test_lane1_fires_on_boundary_break_above_noise_and_vwap():
    lane = IndexTrendLane({SYM: profile()})
    # break above 100*(1+0.002)=100.2, above VWAP, on a 5-min boundary close (minute 599 -> 10:00)
    sig = lane.update(ctx(599, 100.5, svwap=100.1))
    assert sig is not None and sig.lane == "index_trend" and sig.direction == "call"
    assert sig.underlying == SYM
    # target = max(0.35 x remaining_range, 2 x noise) = max(0.0035, 0.004)
    assert abs(sig.target_move - 0.004) < 1e-12
    assert sig.mu_thesis > 0
    assert sig.horizon_T > 0
    assert sig.notes["range_percentile_14d"] == 80.0


def test_lane1_needs_5min_boundary():
    lane = IndexTrendLane({SYM: profile()})
    assert lane.update(ctx(600, 100.5, svwap=100.1)) is None      # 600 closes at 10:01 - off-grid
    assert lane.update(ctx(601, 100.5, svwap=100.1)) is None
    assert lane.update(ctx(604, 100.5, svwap=100.1)) is not None  # 604 closes at 10:05 - on-grid


def test_lane1_vol_condition_gate_blocks_low_percentile():
    lane = IndexTrendLane({SYM: profile(pct=40.0)})               # 14d range percentile < 50
    assert lane.update(ctx(599, 100.5, svwap=100.1)) is None


def test_lane1_requires_vwap_side_agreement():
    lane = IndexTrendLane({SYM: profile()})
    # price broke above the noise band but sits BELOW session VWAP -> no call signal
    assert lane.update(ctx(599, 100.5, svwap=100.9)) is None
    # downside break but above VWAP -> no put signal
    assert lane.update(ctx(599, 99.5, svwap=99.0)) is None


def test_lane1_put_side_and_one_per_side_per_day():
    lane = IndexTrendLane({SYM: profile()})
    up = lane.update(ctx(599, 100.5, svwap=100.1))
    assert up is not None and up.direction == "call"
    assert lane.update(ctx(604, 100.6, svwap=100.1)) is None      # same side deduped
    dn = lane.update(ctx(609, 99.4, svwap=99.8))
    assert dn is not None and dn.direction == "put"
    assert lane.update(ctx(614, 99.2, svwap=99.8)) is None        # put side deduped too


def test_lane1_invalidation_vwap_recross_and_noise_reentry():
    lane = IndexTrendLane({SYM: profile()})
    assert lane.update(ctx(599, 100.5, svwap=100.1)) is not None
    assert lane.invalidated(pctx("call", 100.5, svwap=100.1)) is False   # still valid
    assert lane.invalidated(pctx("call", 99.9, svwap=100.1)) is True     # VWAP recross
    # back inside the noise area (|100.1/100 - 1| = 0.001 < 0.002) even while above VWAP
    assert lane.invalidated(pctx("call", 100.1, svwap=100.05)) is True
    # unreadable mark never flips the thesis
    assert lane.invalidated(pctx("call", 0.0, svwap=100.1)) is False


def test_lane1_unknown_symbol_stands_down():
    lane = IndexTrendLane({SYM: profile()})
    assert lane.update(ctx(599, 100.5, sym="QQQ", svwap=100.1)) is None


# ------------------------------------------------------------------ Lane 1b: last30
def test_lane1b_fires_continuation_at_1530():
    lane = Last30Lane({SYM: profile(adr=0.01)})
    # |open->15:30| = 0.8% > 0.5 x 1% -> continuation call; bar 929 closes at 15:30:00
    sig = lane.update(ctx(929, 100.8, svwap=100.3))
    assert sig is not None and sig.lane == "last30" and sig.direction == "call"
    assert sig.notes["one_dte_only"] is True
    assert sig.notes["planned_exit_minute"] == 15 * 60 + 55       # designed 15:55, not 15:45
    assert abs(sig.horizon_T - 25.0 / 390.0 / 252.0) < 1e-12
    assert lane.invalidated(pctx("call", 90.0)) is False          # clock-bound: never invalidated


def test_lane1b_half_day_close_min_threading():
    # 13:00 half day: the 30-min-before-close trigger moves to bar 749 (12:30), planned exit 12:55
    lane = Last30Lane({SYM: profile(adr=0.01)}, close_min=780)
    assert lane.update(ctx(929, 100.8, svwap=100.3)) is None      # normal-day bar: window gone
    lane2 = Last30Lane({SYM: profile(adr=0.01)}, close_min=780)
    sig = lane2.update(ctx(749, 100.8, svwap=100.3))
    assert sig is not None and sig.notes["planned_exit_minute"] == 775
    lane3 = MacroReactionLane(["cpi"], close_min=780)
    assert lane3.exit_minute == 775


def test_lane1b_below_threshold_no_fire_and_single_decision():
    lane = Last30Lane({SYM: profile(adr=0.01)})
    assert lane.update(ctx(929, 100.3, svwap=100.1)) is None      # 0.3% <= 0.5%
    # the day's decision is spent - a later bar inside the window cannot re-fire
    assert lane.update(ctx(930, 101.5, svwap=100.1)) is None


def test_lane1b_put_side_and_time_window():
    lane = Last30Lane({SYM: profile(adr=0.01)})
    assert lane.update(ctx(920, 99.0, svwap=99.5)) is None        # too early (closes 15:21)
    sig = lane.update(ctx(929, 99.0, svwap=99.5))
    assert sig is not None and sig.direction == "put"
    lane2 = Last30Lane({SYM: profile(adr=0.01)})
    assert lane2.update(ctx(940, 99.0, svwap=99.5)) is None       # past the late window (15:41)


# ------------------------------------------------------------------ Lane 2: inplay_orb
def orb_lane(**kw):
    # baseline = average_volume x 0.04 = 10,000 (consolidated scale is THE RVOL baseline
    # since opts-fix-lane2-rvol-scale-v1; the IEX-scale avg_first5_volume never gates)
    cand = InPlayCandidate(symbol="ABCD", gap_pct=6.0, catalyst=True,
                           avg_first5_volume=kw.pop("avg_first5", 10_000.0),
                           average_volume=kw.pop("avg_day_vol", 250_000.0))
    return InPlayORBLane([cand], **kw)


def feed_or(lane, *, vol=12_000.0, sym="ABCD"):
    """First 5 bars build the OR 9.90-10.10 with total volume 5 x vol/5."""
    for i in range(5):
        lane.update(ctx(570 + i, 10.0, sym=sym, open_=10.0, high=10.10, low=9.90,
                        vol=vol / 5.0, session_open=10.0, svwap=10.0))


def test_lane2_orb_break_fires_with_rvol_and_target():
    lane = orb_lane()                                             # RVOL = 12000/10000 = ... wait
    feed_or(lane, vol=60_000.0)                                   # 60k vs 10k avg -> RVOL 6 >= 5
    sig = lane.update(ctx(575, 10.15, sym="ABCD", svwap=10.02, session_open=10.0))
    assert sig is not None and sig.lane == "inplay_orb" and sig.direction == "call"
    assert abs(sig.target_move - 2.0 * (10.10 - 9.90) / 10.15) < 1e-9
    assert sig.notes["first5_rvol"] == 6.0
    assert sig.notes["catalyst"] is True


def test_lane2_rvol_gate_blocks():
    lane = orb_lane()
    feed_or(lane, vol=40_000.0)                                   # RVOL 4 < 5
    assert lane.update(ctx(575, 10.15, sym="ABCD", svwap=10.02)) is None


def test_lane2_ucurve_baseline():
    # baseline = average_volume x FIRST5_UCURVE_FRAC = 1,000,000 x 0.04 = 40,000
    cand = InPlayCandidate(symbol="ABCD", gap_pct=5.0, avg_first5_volume=0.0,
                           average_volume=1_000_000.0)
    lane = InPlayORBLane([cand])
    feed_or(lane, vol=250_000.0)                                  # RVOL 6.25 >= 5
    sig = lane.update(ctx(575, 10.15, sym="ABCD", svwap=10.02))
    assert sig is not None
    assert abs(sig.notes["first5_rvol"] - 250_000.0 / (1_000_000.0 * FIRST5_UCURVE_FRAC)) < 1e-9


def test_lane2_iex_cache_baseline_never_gates():
    """opts-fix-lane2-rvol-scale-v1: live volume is consolidated tape, the cached
    avg_first5_volume is IEX single-venue (~2-3% of tape) - gating against it inflated RVOL
    ~30-50x. The consolidated baseline must gate even when a (tiny, IEX-scale) cache value
    exists, and a name with no average_volume has no baseline at all -> stands down."""
    # IEX-scale first5 (10k) would say RVOL=25; the consolidated baseline says RVOL=2.5 -> block
    cand = InPlayCandidate(symbol="ABCD", gap_pct=6.0, catalyst=True,
                           avg_first5_volume=10_000.0, average_volume=2_500_000.0)
    lane = InPlayORBLane([cand])
    feed_or(lane, vol=250_000.0)                                  # 250k / (2.5M*0.04) = 2.5 < 5
    assert lane.update(ctx(575, 10.15, sym="ABCD", svwap=10.02)) is None
    # cache-only name (no consolidated baseline): stands down instead of false-firing at 25x
    cand2 = InPlayCandidate(symbol="EFGH", gap_pct=6.0, avg_first5_volume=10_000.0,
                            average_volume=0.0)
    lane2 = InPlayORBLane([cand2])
    feed_or(lane2, vol=250_000.0, sym="EFGH")
    assert lane2.update(ctx(575, 10.15, sym="EFGH", svwap=10.02)) is None


def test_lane2_price_floor_blocks_sub_5():
    cand = InPlayCandidate(symbol="PNNY", gap_pct=8.0, average_volume=250_000.0)
    lane = InPlayORBLane([cand])
    for i in range(5):
        lane.update(ctx(570 + i, 3.0, sym="PNNY", open_=3.0, high=3.1, low=2.9, vol=20_000.0))
    assert lane.update(ctx(575, 3.2, sym="PNNY", svwap=3.0)) is None


def test_lane2_put_side_dedup_and_invalidation():
    lane = orb_lane()
    feed_or(lane, vol=60_000.0)
    dn = lane.update(ctx(575, 9.80, sym="ABCD", svwap=9.95))
    assert dn is not None and dn.direction == "put"
    assert lane.update(ctx(576, 9.70, sym="ABCD", svwap=9.95)) is None     # deduped
    # invalidation: re-entry into the OR
    assert lane.invalidated(pctx("put", 10.00, sym="ABCD", svwap=10.05)) is True
    # invalidation: VWAP recross against the put (close above vwap, outside the OR)
    assert lane.invalidated(pctx("put", 10.30, sym="ABCD", svwap=10.20)) is True
    # still valid below the OR and below VWAP
    assert lane.invalidated(pctx("put", 9.70, sym="ABCD", svwap=9.90)) is False


def test_lane2_non_candidate_ignored():
    lane = orb_lane()
    feed_or(lane, vol=60_000.0)
    assert lane.update(ctx(575, 10.15, sym="ZZZZ", svwap=10.0)) is None


# ------------------------------------------------------------------ Lane 3: macro_reaction
def test_lane3_cpi_direction_and_emission_at_0945():
    lane = MacroReactionLane(["cpi"])
    # bars up to 09:44 do nothing
    assert lane.update(ctx(575, 100.2, session_open=100.0)) is None
    # bar 584 closes at 09:45 -> measure 09:30->09:45 and emit (blackout clear at 09:45)
    sig = lane.update(ctx(584, 100.6, session_open=100.0))
    assert sig is not None and sig.lane == "macro_reaction" and sig.direction == "call"
    assert sig.notes["event"] == "cpi"
    assert abs(sig.notes["measured_move"] - 0.006) < 1e-9
    # once per day
    assert lane.update(ctx(589, 101.0, session_open=100.0)) is None


def test_lane3_never_pre_print_defers_to_first_clean_bar():
    lane = MacroReactionLane(["fomc"])
    # 14:00 reference = close of bar 839
    assert lane.update(ctx(839, 100.0)) is None
    # 14:15 measurement bar arrives INSIDE a blackout window -> held, not emitted
    assert lane.update(ctx(854, 99.5, blackout="fomc")) is None
    assert lane.update(ctx(860, 99.4, blackout="pre_print")) is None
    # first clean bar emits with the MEASURED (14:00->14:15) direction
    sig = lane.update(ctx(886, 99.9, blackout=None))
    assert sig is not None and sig.direction == "put"
    assert sig.notes["event"] == "fomc"
    assert abs(sig.notes["measured_move"] - (99.5 / 100.0 - 1.0)) < 1e-9
    assert sig.notes["print_minute"] == 14 * 60
    assert sig.notes["planned_exit_minute"] == 15 * 60 + 55      # designed 15:55, not 15:45


def test_lane3_non_event_day_and_wrong_symbol_never_fire():
    lane = MacroReactionLane([])
    assert lane.update(ctx(584, 101.0, session_open=100.0)) is None
    lane2 = MacroReactionLane(["cpi"])
    assert lane2.update(ctx(584, 101.0, sym="QQQ", session_open=100.0)) is None
    assert lane2.invalidated(pctx("call", 0.0)) is False


# ------------------------------------------------------------------ Lane 4 stub + profile builder
def test_lane4_stub_is_inert():
    lane = PreEarningsStubLane()
    assert lane.update(ctx(599, 100.5)) is None
    assert lane.invalidated(pctx("call", 100.0)) is False


def _mk_session(day: str, open_px: float, drift: float, vol: float = 1000.0) -> pd.DataFrame:
    idx = pd.date_range(f"{day} 09:30", f"{day} 15:59", freq="1min", tz="America/New_York")
    n = len(idx)
    closes = [open_px * (1.0 + drift * (i + 1) / n) for i in range(n)]
    opens = [open_px] + closes[:-1]
    return pd.DataFrame({"open": opens,
                         "high": [max(o, c) * 1.0005 for o, c in zip(opens, closes)],
                         "low": [min(o, c) * 0.9995 for o, c in zip(opens, closes)],
                         "close": closes, "volume": [vol] * n}, index=idx)


def test_build_noise_profile_from_synthetic_sessions():
    days = [f"2026-06-{d:02d}" for d in (8, 9, 10, 11, 12, 15, 16)]      # 7 weekday sessions
    frames = [_mk_session(d, 100.0, 0.01 if i < 6 else 0.03) for i, d in enumerate(days)]
    df = pd.concat(frames)
    prof = build_noise_profile("SPY", df, lookback_days=14)
    assert prof is not None and prof.n_days == 7
    # the LAST session has the biggest range -> percentile 100
    assert prof.range_percentile_14d == 100.0
    assert prof.avg_daily_range > 0
    assert prof.avg_first5_volume == 5000.0
    # noise grows through the session (drift days): later minutes carry larger avg |move|
    assert prof.noise_at(950) > prof.noise_at(575)
    # remaining range shrinks through the session
    assert prof.remaining_range_at(575) > prof.remaining_range_at(950)
    # thin history refuses to profile
    assert build_noise_profile("SPY", df.iloc[:400], lookback_days=14) is None
