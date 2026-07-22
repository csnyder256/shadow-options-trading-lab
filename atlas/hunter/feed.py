"""HUNTER FEED - 5-second Tradier ticks folded into completed 1-minute bars for the StalkerFSM (P3).

Two layers, Guardian idiom (pure core + thin IO wrapper):

  * `LiveBarBuilder` - PURE per-symbol accumulation. Ticks in (last/bid/ask/day-cum-volume),
    COMPLETED left-labeled 1-min bars out: a bar is emitted only when a tick arrives in a LATER
    minute, so the FSM only ever sees closed bars (same convention as the replay gate). Bar volume
    is the day-cumulative-volume DELTA across the minute (guarded: a decreasing/reset cumvol reads
    as 0, never negative). The builder also maintains the causal session context every BarInput
    needs - session VWAP (per-minute typical*vol accumulation), running HOD, the 5-min ATR (the
    SAME `_atr5m_asof` the floor map uses, i.e. full ATR14 on 5-min aggregates once available, else
    mean 5-min true range, else a 1-min proxy - mirroring replay.session_arrays), and the
    running-HOD/impulse-low retrace fraction. Backfilled HISTORY bars are seeded through the SAME
    commit path (`seed_bar`), so a plan armed mid-session gets the identical context replay had.

  * `HunterFeed` - the thin Tradier wrapper. `poll(symbols)` = ONE batched quotes call -> Ticks;
    `backfill(symbol)` = one timesales call -> today's completed 1-min bars. Self-caps its own
    request rate (hunter.tradier_self_cap_per_min - three processes share the account's 120/min)
    and every method FAILS OPEN: any transport/parse error returns {}/[] and never raises out of
    the poll loop. Clock is injected - no wall-clock reads in logic.
"""

from __future__ import annotations

import time as _time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from atlas.clock import NY
from atlas.hunter.floors import _atr5m_asof
from atlas.hunter.stalker import BarInput


@dataclass(frozen=True)
class Tick:
    symbol: str
    ts_epoch: float
    last: float
    bid: float
    ask: float
    spread_bps: float          # nan when bid/ask unusable
    day_cum_volume: float


@dataclass(frozen=True)
class CompletedBar:
    minute: int                # minutes since midnight ET (bar START - left-labeled)
    open: float
    high: float
    low: float
    close: float
    volume: float


def minute_of_day_et(ts_epoch: float) -> int:
    """Epoch seconds -> minutes since midnight ET (the bar-bucket key)."""
    dt = datetime.fromtimestamp(ts_epoch, tz=NY)
    return dt.hour * 60 + dt.minute


@dataclass
class _Snapshot:
    """Causal session context AS OF one committed bar (stored per bar so multi-bar flushes
    hand each bar ITS OWN context, not the newest)."""
    svwap: float
    atr5m: float
    hod: float
    retrace_frac: float
    spread_bps: float


class _SymState:
    __slots__ = ("cur_minute", "o", "h", "l", "c", "base_cum", "last_cum", "cur_spread",
                 "mins", "opens", "highs", "lows", "closes", "vols",
                 "cum_pv", "cum_v", "hod", "hod_idx", "prefix_min_low", "snaps", "last_tick")

    def __init__(self) -> None:
        self.cur_minute: int | None = None         # forming bucket (None = nothing forming)
        self.o = self.h = self.l = self.c = float("nan")
        self.base_cum: float | None = None          # day-cum-volume at the bucket boundary
        self.last_cum: float | None = None
        self.cur_spread = float("nan")              # last tick spread INSIDE the forming bucket
        self.mins: list[int] = []                   # committed bars
        self.opens: list[float] = []
        self.highs: list[float] = []
        self.lows: list[float] = []
        self.closes: list[float] = []
        self.vols: list[float] = []
        self.cum_pv = 0.0                           # session VWAP accumulators (typical * vol)
        self.cum_v = 0.0
        self.hod = float("-inf")
        self.hod_idx = -1
        self.prefix_min_low: list[float] = []       # running min low by bar index
        self.snaps: dict[int, _Snapshot] = {}       # minute -> context snapshot
        self.last_tick: Tick | None = None


class LiveBarBuilder:
    """Per-symbol 5s-tick -> completed-1-min-bar accumulator + causal session context. Pure:
    everything is driven by the ticks/bars fed in; no clock, no IO."""

    def __init__(self) -> None:
        self._sym: dict[str, _SymState] = {}

    # ------------------------------------------------------------------ internals
    def _state(self, symbol: str) -> _SymState:
        st = self._sym.get(symbol)
        if st is None:
            st = self._sym[symbol] = _SymState()
        return st

    def _commit(self, st: _SymState, bar: CompletedBar) -> None:
        """The ONE path every completed bar takes (live tick roll-over AND backfill seed), so
        seeded history and live bars build byte-identical context."""
        st.mins.append(bar.minute)
        st.opens.append(bar.open); st.highs.append(bar.high)
        st.lows.append(bar.low); st.closes.append(bar.close); st.vols.append(bar.volume)
        typ = (bar.high + bar.low + bar.close) / 3.0
        st.cum_pv += typ * bar.volume
        st.cum_v += bar.volume
        i = len(st.mins) - 1
        prev_min_low = st.prefix_min_low[-1] if st.prefix_min_low else float("inf")
        st.prefix_min_low.append(min(prev_min_low, bar.low))
        if bar.high >= st.hod:                      # replay convention: ties advance the HOD bar
            st.hod = bar.high
            st.hod_idx = i
        svwap = st.cum_pv / st.cum_v if st.cum_v > 0 else bar.close
        atr5 = _atr5m_asof(np.asarray(st.opens, float), np.asarray(st.highs, float),
                           np.asarray(st.lows, float), np.asarray(st.closes, float))
        imp_low = st.prefix_min_low[st.hod_idx] if st.hod_idx >= 0 else float("nan")
        leg = st.hod - imp_low
        retrace = (st.hod - bar.close) / leg if np.isfinite(leg) and leg > 0 else float("nan")
        st.snaps[bar.minute] = _Snapshot(svwap=float(svwap), atr5m=float(atr5),
                                         hod=float(st.hod), retrace_frac=float(retrace),
                                         spread_bps=float(st.cur_spread))

    def _roll(self, st: _SymState) -> CompletedBar | None:
        if st.cur_minute is None:
            return None
        base = st.base_cum if st.base_cum is not None else (st.last_cum or 0.0)
        vol = max(0.0, (st.last_cum or 0.0) - base)   # reset/decrease guard -> 0, never negative
        bar = CompletedBar(minute=st.cur_minute, open=st.o, high=st.h, low=st.l,
                           close=st.c, volume=vol)
        st.base_cum = st.last_cum                     # next bucket counts from here
        st.cur_minute = None
        return bar

    # ------------------------------------------------------------------ public API
    def seed_bar(self, symbol: str, bar: CompletedBar) -> None:
        """Feed one HISTORICAL completed bar (backfill) through the same commit path. Out-of-order
        or already-covered minutes are ignored."""
        st = self._state(symbol)
        if st.mins and bar.minute <= st.mins[-1]:
            return
        self._commit(st, bar)

    def on_tick(self, tick: Tick) -> list[CompletedBar]:
        """Accumulate one 5s tick; returns bars COMPLETED by this tick (usually 0 or 1)."""
        st = self._state(tick.symbol)
        st.last_tick = tick
        if not np.isfinite(tick.last) or tick.last <= 0:
            return []                                # unreadable tick never poisons a bar
        minute = minute_of_day_et(tick.ts_epoch)
        out: list[CompletedBar] = []
        if st.cur_minute is not None and minute > st.cur_minute:
            done = self._roll(st)
            if done is not None:
                self._commit(st, done)
                out.append(done)
        if st.cur_minute is None:
            # never (re)form a bucket for a minute history already covers, or a stale tick
            if (st.mins and minute <= st.mins[-1]) or (st.cur_minute is None and minute < 0):
                st.last_cum = tick.day_cum_volume
                return out
            st.cur_minute = minute
            st.o = st.h = st.l = st.c = tick.last
            if st.base_cum is None:                  # first live bucket: count from its first tick
                st.base_cum = tick.day_cum_volume
            st.cur_spread = tick.spread_bps
        elif minute == st.cur_minute:
            st.h = max(st.h, tick.last)
            st.l = min(st.l, tick.last)
            st.c = tick.last
            st.cur_spread = tick.spread_bps
        else:                                        # minute < cur_minute: stale/out-of-order tick
            return out
        if st.last_cum is not None and tick.day_cum_volume < st.last_cum:
            st.base_cum = tick.day_cum_volume        # cumvol reset mid-bucket: this minute reads 0
        st.last_cum = tick.day_cum_volume
        return out

    def bar_input(self, symbol: str, bar: CompletedBar, minute: int | None = None) -> BarInput:
        """The FSM-facing view of one COMMITTED bar, with the context snapshot taken at its
        commit (svwap/atr5m/hod/retrace) and the spread of that bar's last tick."""
        st = self._state(symbol)
        m = bar.minute if minute is None else int(minute)
        snap = st.snaps.get(m)
        if snap is None:                             # defensive: uncommitted bar -> flat context
            snap = _Snapshot(bar.close, float("nan"), bar.high, float("nan"), float("nan"))
        return BarInput(minute=m, open=bar.open, high=bar.high, low=bar.low, close=bar.close,
                        volume=bar.volume, svwap=snap.svwap, atr5m=snap.atr5m, hod=snap.hod,
                        retrace_frac=snap.retrace_frac, spread_bps=snap.spread_bps)

    def n_bars(self, symbol: str) -> int:
        st = self._sym.get(symbol)
        return len(st.mins) if st else 0

    def session_arrays(self, symbol: str) -> tuple[list, list, list, list, list, list]:
        """Read-only view of the COMMITTED session bars (mins, opens, highs, lows, closes,
        vols) - the options exit engine's live-trajectory estimator reads trailing closes
        from here (opts-rework-exit-core-v1). Committed bars only: the forming minute never
        leaks (causality). Returns empty lists for an unknown symbol."""
        st = self._sym.get(symbol)
        if st is None:
            return [], [], [], [], [], []
        return st.mins, st.opens, st.highs, st.lows, st.closes, st.vols

    def latest_tick(self, symbol: str) -> Tick | None:
        st = self._sym.get(symbol)
        return st.last_tick if st else None


def _spread_bps(bid: float, ask: float) -> float:
    if bid > 0 and ask > 0 and ask >= bid:
        mid = (bid + ask) / 2.0
        if mid > 0:
            return (ask - bid) / mid * 1e4
    return float("nan")


class HunterFeed:
    """Thin Tradier wrapper: batched quote polls + one-shot 1-min backfill, self-capped and
    fail-open. `client=None` (config/tradier.local.yaml absent) degrades to an empty feed - 
    the Hunter then runs heartbeat-only, exactly like the Guardian's optional alt-quote path."""

    def __init__(self, client, *, clock_fn=_time.time, cap_per_min: int = 30):
        self.client = client
        self.clock_fn = clock_fn
        self.cap_per_min = max(1, int(cap_per_min))
        self._req_times: deque = deque()

    def _budget_ok(self, cost: int = 1) -> bool:
        now = self.clock_fn()
        while self._req_times and now - self._req_times[0] > 60.0:
            self._req_times.popleft()
        if len(self._req_times) + cost > self.cap_per_min:
            return False
        for _ in range(cost):
            self._req_times.append(now)
        return True

    def poll(self, symbols: list[str]) -> dict[str, Tick]:
        """One batched quotes call for ALL stalked names. {} on any failure / empty input /
        budget exhaustion - the caller just sees a quiet tick."""
        syms = [s for s in symbols if s]
        if self.client is None or not syms:
            return {}
        cost = 1 + (len(syms) - 1) // 100            # TradierData batches 100 symbols/POST
        if not self._budget_ok(cost):
            return {}
        try:
            quotes = self.client.get_quotes(syms)
        except Exception:  # noqa: BLE001 - fail-open; protection never depends on one poll
            return {}
        now = self.clock_fn()
        out: dict[str, Tick] = {}
        for sym, q in quotes.items():
            try:
                out[sym] = Tick(symbol=sym, ts_epoch=now, last=float(q.last),
                                bid=float(q.bid), ask=float(q.ask),
                                spread_bps=_spread_bps(float(q.bid), float(q.ask)),
                                day_cum_volume=float(q.volume))
            except (TypeError, ValueError):
                continue
        return out

    def backfill(self, symbol: str) -> list[CompletedBar]:
        """Today's completed 1-min bars via timesales - used ONCE at plan arming to seed the
        builder. [] on any failure (the FSM then just starts context-poor, never crashes)."""
        if self.client is None or not symbol:
            return []
        if not self._budget_ok(1):
            return []
        day = datetime.fromtimestamp(self.clock_fn(), tz=NY).strftime("%Y-%m-%d")
        try:
            rows = self.client.get_timesales(symbol, interval="1min", start=f"{day} 09:30")
        except Exception:  # noqa: BLE001
            return []
        out: list[CompletedBar] = []
        for r in rows:
            m = _minute_from_ts(str(getattr(r, "ts", "")))
            if m is None:
                continue
            try:
                out.append(CompletedBar(minute=m, open=float(r.open), high=float(r.high),
                                        low=float(r.low), close=float(r.close),
                                        volume=float(r.volume)))
            except (TypeError, ValueError):
                continue
        out.sort(key=lambda b: b.minute)
        return out


def _minute_from_ts(ts: str) -> int | None:
    """Tradier timesales `time` is ISO local-exchange time ('2026-07-09T09:31:00'). Tolerant."""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.hour * 60 + dt.minute
    except ValueError:
        try:
            return minute_of_day_et(float(ts))       # epoch fallback (timestamp field)
        except (TypeError, ValueError, OSError, OverflowError):
            return None
