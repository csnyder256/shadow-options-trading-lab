"""STALKER FSM - the Floor Hunter's deterministic confirmation engine (P1b).

Pure core in the Guardian idiom: no IO, no clock, no config reads - a per-name state machine fed
completed 1-minute bars (`BarInput`), emitting transition `Event`s and at most one `FireIntent`.
The SAME class runs in the replay gate and the live Hunter process; live merely feeds it real bars
and executes its FireIntent through the order path. There is NO LLM anywhere in here - plans are
pre-approved at admission; this is the hot path.

States:  ARMED -> STALKING -> TOUCHED -> CONFIRMING -> FIRED | ABORTED | EXPIRED

Two trigger grammars (both A/B'd at the replay gate - see config/hunter.yaml trigger_grammars):
  G1 "undercut_reclaim"  (failed breakdown / Wyckoff spring): a flush 0.2-0.8 ATR5m below the
     zone's reference low, then a 1-min close back above it within <=5 bars on volume >= the flush
     bar's, green body >= 0.5. Stop goes below the FLUSH low.
  G2 "higher_low_pivot_break": the zone holds without a flush - micro pivot low L1, an interim
     high, a second low >= L1 (the higher low), then a close above the interim high on expanding
     volume. Stop goes below the higher low.

Common fire gates (ALL must hold on the trigger bar): trigger volume >= vol_median_mult x its
20-bar median; dip-volume contraction (taper); price <= max_chase; entry window; spread <= fire
cap; no halt/defensive event; R:R >= min_rr to T1 = max(session VWAP, ref + t1_r x stop_dist);
target distance >= min_target_spread_mult x quoted spread.

Knife rule (any state after TOUCHED, before FIRED): a 1-min close < zone.bottom - knife_atr x ATR5m,
or two consecutive closes < zone.bottom => ABORTED(zone_break) - a failed floor is a real breakdown.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

# terminal + live states
ARMED, STALKING, TOUCHED, CONFIRMING, FIRED, ABORTED, EXPIRED = (
    "ARMED", "STALKING", "TOUCHED", "CONFIRMING", "FIRED", "ABORTED", "EXPIRED")

G1, G2 = "undercut_reclaim", "higher_low_pivot_break"


@dataclass(frozen=True)
class StalkParams:
    grammars: tuple[str, ...] = (G1, G2)
    pullback_start_atr: float = 0.75      # ARMED->STALKING when close <= HOD - this*ATR5m (or < VWAP)
    flush_min_atr: float = 0.2            # G1 flush depth band below the reference low
    flush_max_atr: float = 0.8
    reclaim_max_bars: int = 5
    reclaim_body_min: float = 0.5
    vol_median_mult: float = 1.5
    vol_median_window: int = 20
    taper_bars: int = 3                   # last-N down-bar volume < prior-N down-bar volume
    micro_pivot_k: int = 2                # G2 micro pivot half-width on 1-min bars
    hl_undercut_reset_atr: float = 0.15   # L2 below L1 by more than this => not a higher low; reset
    knife_atr: float = 0.30
    knife_consec_closes: int = 2
    stop_buffer_atr: float = 0.35
    t1_r_multiple: float = 1.2
    min_rr: float = 2.0
    min_target_spread_mult: float = 6.0
    entry_start_min: int = 9 * 60 + 45    # 09:45 ET
    last_entry_min: int = 13 * 60         # 13:00 ET (sweep axis)
    spread_fire_cap_bps: float = 80.0
    spread_abort_consec: int = 3
    abort_retrace: float = 0.85           # leg retraced this deep pre-fire => the move failed
    max_stop_pct: float = 6.0
    min_stop_pct: float = 0.5


@dataclass(frozen=True)
class PinnedZone:
    """The LLM-approved zone the plan pinned at admission (sha-integrity lives on the plan)."""
    top: float
    bottom: float
    reference_low: float                  # lowest FAMILY level in the zone (the level being defended)
    max_chase: float


@dataclass(frozen=True)
class BarInput:
    minute: int                           # minutes since midnight ET (bar START, left-labeled)
    open: float
    high: float
    low: float
    close: float
    volume: float
    svwap: float                          # causal session VWAP at this bar
    atr5m: float                          # causal 5-min ATR
    hod: float                            # session high through this bar
    retrace_frac: float = float("nan")    # catalyst-leg retrace at this bar (nan = no leg)
    spread_bps: float = float("nan")      # nan in replay (cost model applies instead)
    halted: bool = False
    defensive_event: bool = False         # dilution/FDA/negative-8-K landed since admission


@dataclass(frozen=True)
class Event:
    minute: int
    from_state: str
    to_state: str
    reason: str


@dataclass(frozen=True)
class FireIntent:
    grammar: str
    minute: int
    ref_close: float                      # trigger-bar close = the marketable-limit peg
    stop: float
    t1: float
    stop_dist: float
    rr: float
    flush_low: float | None
    higher_low: float | None
    zone_top: float
    zone_bottom: float


@dataclass
class _G1State:
    flush_low: float = float("inf")
    flush_vol: float = 0.0
    flush_started: int = -1               # bar counter when the flush began (-1 = no flush yet)


@dataclass
class _G2State:
    l1: float | None = None               # confirmed micro pivot low
    interim_high: float = float("-inf")
    l2_candidate: float = float("inf")


class StalkerFSM:
    """One instance per (plan, session). Feed completed 1-min bars via step(); read .state,
    .events, .fire (a FireIntent once FIRED). Deterministic for a given bar sequence."""

    def __init__(self, zone: PinnedZone, params: StalkParams = StalkParams()):
        self.zone = zone
        self.p = params
        self.state = ARMED
        self.events: list[Event] = []
        self.fire: FireIntent | None = None
        self._bars: deque[BarInput] = deque(maxlen=max(params.vol_median_window,
                                                       2 * params.taper_bars + 2,
                                                       2 * params.micro_pivot_k + 3) + 5)
        self._g1 = _G1State()
        self._g2 = _G2State()
        self._below_bottom_closes = 0
        self._wide_spread_bars = 0
        self._n = 0                       # bars seen

    # ------------------------------------------------------------------ helpers
    def _emit(self, to_state: str, reason: str, minute: int) -> None:
        self.events.append(Event(minute, self.state, to_state, reason))
        self.state = to_state

    def _vol_median(self) -> float:
        vols = [b.volume for b in list(self._bars)[-self.p.vol_median_window - 1:-1]]
        return float(np.median(vols)) if vols else float("nan")

    def _down_taper(self) -> bool:
        """Sum of the last N down-bar volumes < sum of the prior N down-bar volumes (dry-up)."""
        downs = [b.volume for b in self._bars if b.close < b.open]
        if len(downs) < 2 * self.p.taper_bars:
            return True                                    # not enough evidence to refuse (fail-open)
        recent = sum(downs[-self.p.taper_bars:])
        prior = sum(downs[-2 * self.p.taper_bars:-self.p.taper_bars])
        return recent < prior

    def _terminal(self) -> bool:
        return self.state in (FIRED, ABORTED, EXPIRED)

    # ------------------------------------------------------------------ the step
    def step(self, bar: BarInput) -> list[Event]:
        if self._terminal():
            return []
        before = len(self.events)
        self._bars.append(bar)
        self._n += 1
        p, z = self.p, self.zone

        # -- universal aborts (checked every bar, any live state) -------------------------------
        if bar.halted:
            self._emit(ABORTED, "halted", bar.minute)
            return self.events[before:]
        if bar.defensive_event:
            self._emit(ABORTED, "defensive_event", bar.minute)
            return self.events[before:]
        if np.isfinite(bar.spread_bps) and bar.spread_bps > p.spread_fire_cap_bps:
            self._wide_spread_bars += 1
            if self._wide_spread_bars >= p.spread_abort_consec:
                self._emit(ABORTED, "spread_blowout", bar.minute)
                return self.events[before:]
        else:
            self._wide_spread_bars = 0
        if bar.minute > p.last_entry_min:
            self._emit(EXPIRED, "entry_window_closed", bar.minute)
            return self.events[before:]
        if (self.state in (TOUCHED, CONFIRMING) and np.isfinite(bar.retrace_frac)
                and bar.retrace_frac > p.abort_retrace):
            self._emit(ABORTED, "leg_failed_deep_retrace", bar.minute)
            return self.events[before:]

        # -- knife rule (after first touch) -------------------------------------------------------
        if self.state in (TOUCHED, CONFIRMING):
            knife_line = z.bottom - p.knife_atr * bar.atr5m
            if bar.close < knife_line:
                self._emit(ABORTED, "zone_break_knife", bar.minute)
                return self.events[before:]
            if bar.close < z.bottom:
                self._below_bottom_closes += 1
                if self._below_bottom_closes >= p.knife_consec_closes:
                    self._emit(ABORTED, "zone_break_closes", bar.minute)
                    return self.events[before:]
            else:
                self._below_bottom_closes = 0

        # -- state advances ------------------------------------------------------------------------
        if self.state == ARMED:
            pulling = (bar.close <= bar.hod - p.pullback_start_atr * bar.atr5m
                       or bar.close < bar.svwap)
            if pulling:
                self._emit(STALKING, "pullback_started", bar.minute)

        if self.state == STALKING and bar.low <= z.top:
            self._emit(TOUCHED, "zone_touched", bar.minute)
            # a gap THROUGH the zone on the touch bar is already a knife
            if bar.close < z.bottom - p.knife_atr * bar.atr5m:
                self._emit(ABORTED, "zone_break_knife", bar.minute)
                return self.events[before:]

        if self.state in (TOUCHED, CONFIRMING):
            self._advance_grammars(bar)

        return self.events[before:]

    # ------------------------------------------------------------------ grammars
    def _advance_grammars(self, bar: BarInput) -> None:
        p, z = self.p, self.zone

        # ---- G1: track the flush ------------------------------------------------------------
        if G1 in p.grammars:
            g = self._g1
            if bar.low < z.reference_low:                          # in (or beyond) the undercut
                if g.flush_started < 0:
                    g.flush_started = self._n
                    g.flush_vol = bar.volume
                if bar.low < g.flush_low:
                    g.flush_low = bar.low
                    g.flush_vol = max(g.flush_vol, bar.volume)
                if self.state == TOUCHED:
                    self._emit(CONFIRMING, "flush_below_reference", bar.minute)
            if g.flush_started >= 0:
                depth = (z.reference_low - g.flush_low) / bar.atr5m if bar.atr5m > 0 else 0.0
                stale = (self._n - g.flush_started) > p.reclaim_max_bars
                if stale:
                    self._g1 = _G1State()                          # flush window expired; re-arm
                elif (bar.close > z.reference_low
                        and p.flush_min_atr <= depth <= p.flush_max_atr
                        and bar.volume >= g.flush_vol):
                    self._try_fire(bar, G1, stop_anchor=g.flush_low, higher_low=None)

        # ---- G2: higher low + micro pivot break ----------------------------------------------
        if G2 in p.grammars and self.state in (TOUCHED, CONFIRMING) and not self._terminal():
            g = self._g2
            k = p.micro_pivot_k
            bars = list(self._bars)
            if g.l1 is None:
                # L1 = a confirmed micro pivot low that printed inside the zone
                if len(bars) >= 2 * k + 1:
                    cand = bars[-k - 1]
                    left = bars[-2 * k - 1:-k - 1]
                    right = bars[-k:]
                    if (all(cand.low < b.low for b in left) and all(cand.low < b.low for b in right)
                            and cand.low <= z.top):
                        g.l1 = cand.low
                        g.interim_high = max(b.high for b in bars[-k:])
                        if self.state == TOUCHED:
                            self._emit(CONFIRMING, "micro_pivot_low_L1", bar.minute)
            else:
                g.l2_candidate = min(g.l2_candidate, bar.low)
                if g.l2_candidate < g.l1 - p.hl_undercut_reset_atr * bar.atr5m:
                    # decisively undercut - that was not a higher low; restart L1 discovery
                    self._g2 = _G2State()
                else:
                    if g.l2_candidate < g.l1:
                        # marginal undercut (noise band): the new low becomes the reference L1
                        g.l1 = g.l2_candidate
                    # break test uses the interim high from PRIOR bars only - a bar cannot
                    # break its own high; fold this bar's high in afterward for future bars
                    if (bar.close > g.interim_high and bar.close > bar.open
                            and g.l2_candidate >= g.l1 - 1e-12):
                        self._try_fire(bar, G2, stop_anchor=min(g.l1, g.l2_candidate),
                                       higher_low=g.l2_candidate)
                    g.interim_high = max(g.interim_high, bar.high)

    # ------------------------------------------------------------------ the trigger
    def _try_fire(self, bar: BarInput, grammar: str, *, stop_anchor: float,
                  higher_low: float | None) -> None:
        p, z = self.p, self.zone
        if bar.minute < p.entry_start_min or bar.minute > p.last_entry_min:
            return
        ref = bar.close
        if ref > z.max_chase:
            return                                              # never chase past the line
        rng = bar.high - bar.low
        body = (bar.close - bar.open) / rng if rng > 0 else 0.0
        if bar.close <= bar.open or body < p.reclaim_body_min:
            return
        med = self._vol_median()
        if np.isfinite(med) and med > 0 and bar.volume < p.vol_median_mult * med:
            return
        if not self._down_taper():
            return
        stop = stop_anchor - p.stop_buffer_atr * bar.atr5m
        stop_dist = ref - stop
        if stop_dist <= 0:
            return
        stop_pct = stop_dist / ref * 100.0
        if not (p.min_stop_pct <= stop_pct <= p.max_stop_pct):
            return
        t1 = max(bar.svwap, ref + p.t1_r_multiple * stop_dist)
        rr = (t1 - ref) / stop_dist
        if rr < p.min_rr - 1e-9:
            t1 = ref + p.min_rr * stop_dist                     # lift T1 to the R:R floor …
            rr = p.min_rr                                       # … the spread gate below still rules
        if np.isfinite(bar.spread_bps):
            if bar.spread_bps > p.spread_fire_cap_bps:
                return
            if (t1 - ref) / ref * 1e4 < p.min_target_spread_mult * bar.spread_bps:
                return
        self.fire = FireIntent(grammar, bar.minute, round(ref, 6), round(stop, 6), round(t1, 6),
                               round(stop_dist, 6), round(rr, 4),
                               None if higher_low is not None else round(self._g1.flush_low, 6),
                               higher_low if higher_low is None else round(higher_low, 6),
                               z.top, z.bottom)
        self._emit(FIRED, f"trigger_{grammar}", bar.minute)
