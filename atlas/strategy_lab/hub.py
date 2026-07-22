"""MarketHub - the lab's SHARED market-data layer (one Tradier client, one budget).

Registered lab-strategy-runtime-v1. Why shared: chain cost scales with UNIVERSE, not with
strategy count - a bull-put-spread scan and an iron-condor scan of SPY ~45DTE hit the same
cached chain. Budget reality (M0 finding E3): there is NO second Tradier token - the lab
shares the single production token's ~120/min with the main shadow (self-cap 60/min), so the
lab's slice is CAP_PER_MIN=40 PERMANENTLY, enforced here by a rolling-minute governor with a
priority ladder:

    P0 open-position leg quotes   never shed (feed exits)
    P1 underlying quotes          shed last
    P2 manage-path chain refresh  shed after P3
    P3 entry-scan chains          shed first

Rolling usage >= 80% of cap -> chain TTLs double and P3 is suppressed (journaled
`lab_data_degraded` once per stretch). Entries always require fresh data (a stale chain
fails to "no entry", never to a stale-priced entry); exits may use stale quotes but stamp
`age_s` so the grader can flag them.

Greeks: SELF-COMPUTED from live mid via the vendored solver (the platform law - vendor ORATS
greeks are ~hourly and archive-only). T here is CALENDAR days/365 for strike selection - 
a selection convention, not exit-engine math (the lab has no exit engine; strategies own exits).
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from atlas.options.vendor.blackscholes import greeks as bs_greeks
from atlas.options.vendor.blackscholes import implied_vol

CAP_PER_MIN = 40
DEGRADE_FRAC = 0.8
CHAIN_TTL_S = 300.0
EXPIRATIONS_TTL_S = 3600.0
STALE_QUOTE_S = 120.0
SELECTION_R = 0.04            # flat selection-rate convention (label: PLATFORM-POLICY)

P0_EXIT_QUOTES, P1_UNDERLYING, P2_MANAGE_CHAIN, P3_SCAN_CHAIN = 0, 1, 2, 3


class BudgetGovernor:
    """Rolling-60s request budget with priority shedding (pure given a clock)."""

    def __init__(self, cap_per_min: int = CAP_PER_MIN, clock=time.monotonic):
        self.cap = int(cap_per_min)
        self.clock = clock
        self._stamps: deque = deque()
        self.degraded = False

    def _prune(self) -> None:
        cut = self.clock() - 60.0
        while self._stamps and self._stamps[0] < cut:
            self._stamps.popleft()

    def used(self) -> int:
        self._prune()
        return len(self._stamps)

    def allow(self, priority: int) -> bool:
        self._prune()
        used = len(self._stamps)
        was_degraded = self.degraded
        self.degraded = used >= DEGRADE_FRAC * self.cap
        if priority == P0_EXIT_QUOTES:
            ok = True                              # never shed the exit feed
        elif used >= self.cap:
            ok = False
        elif self.degraded and priority >= P3_SCAN_CHAIN:
            ok = False
        else:
            ok = True
        self.entered_degraded = self.degraded and not was_degraded
        if ok:
            self._stamps.append(self.clock())
        return ok

    def chain_ttl(self) -> float:
        return CHAIN_TTL_S * (2.0 if self.degraded else 1.0)


@dataclass
class CachedChain:
    rows: list
    fetched: float


class MarketHub:
    """One TradierData client + caches + governor + file-fed context (vol regime, earnings).
    `client` is duck-typed (tests inject fakes): get_option_expirations, get_option_chain,
    get_quotes, get_daily_history."""

    def __init__(self, client, runtime_dir: Path, *, cap_per_min: int = CAP_PER_MIN,
                 journal=None, clock=time.monotonic):
        self.client = client
        self.runtime = Path(runtime_dir)
        self.governor = BudgetGovernor(cap_per_min, clock)
        self.journal = journal or (lambda rec: None)
        self.clock = clock
        self._chains: dict[tuple, CachedChain] = {}
        self._expirations: dict[str, CachedChain] = {}
        self._last_quotes: dict[str, tuple] = {}      # sym -> (bid, ask, ts)

    # ---------------------------------------------------------------- quotes
    def poll_quotes(self, underlyings: list, leg_occs: list) -> dict:
        """ONE batched call for underlyings + all open leg OCCs (P0 - never shed).
        Returns {sym: TQuote}; also refreshes the staleness book."""
        syms = sorted(set(underlyings) | set(leg_occs))
        if not syms:
            return {}
        self.governor.allow(P0_EXIT_QUOTES)
        try:
            quotes = self.client.get_quotes(syms)
        except Exception as exc:  # noqa: BLE001 - feed fail-open
            self.journal({"event": "hub_quote_error", "ts_epoch": time.time(),
                          "detail": f"{type(exc).__name__}: {exc}", "n_syms": len(syms)})
            return {}
        now = self.clock()
        for sym, q in quotes.items():
            self._last_quotes[sym] = (q.bid, q.ask, now, float(getattr(q, "last", 0.0) or 0.0))
        return quotes

    def nbbo_age_s(self, sym: str) -> float | None:
        rec = self._last_quotes.get(sym)
        return None if rec is None else round(self.clock() - rec[2], 1)

    def last_nbbo(self, sym: str) -> tuple | None:
        rec = self._last_quotes.get(sym)
        if rec is None:
            return None
        return (rec[0], rec[1], round(self.clock() - rec[2], 1))

    def ref_price(self, sym: str) -> float:
        """Entry reference price: last trade when known, else NBBO mid (ADAPTED convention - 
        strategies citing a 'last disseminated value' reference use this)."""
        rec = self._last_quotes.get(sym)
        if rec is None:
            return 0.0
        last = rec[3] if len(rec) > 3 else 0.0
        if last > 0:
            return last
        bid, ask = rec[0], rec[1]
        return (bid + ask) / 2.0 if (bid > 0 and ask > 0) else 0.0

    # ---------------------------------------------------------------- chains
    def expirations(self, underlying: str, *, priority: int = P3_SCAN_CHAIN) -> list:
        u = underlying.upper()
        c = self._expirations.get(u)
        if c and self.clock() - c.fetched < EXPIRATIONS_TTL_S:
            return c.rows
        if not self.governor.allow(priority):
            self._note_degraded()
            return c.rows if c else []
        try:
            rows = self.client.get_option_expirations(u)
        except Exception as exc:  # noqa: BLE001
            self.journal({"event": "hub_chain_error", "ts_epoch": time.time(),
                          "detail": f"{type(exc).__name__}: {exc}", "underlying": u})
            return c.rows if c else []
        self._expirations[u] = CachedChain(rows, self.clock())
        return rows

    def chain(self, underlying: str, expiration: str, *,
              priority: int = P3_SCAN_CHAIN) -> list:
        """Cached chain rows; returns [] (never stale rows) for ENTRY-path requests that
        cannot be served fresh - a scan that gets [] simply finds nothing today."""
        key = (underlying.upper(), expiration)
        c = self._chains.get(key)
        ttl = self.governor.chain_ttl()
        if c and self.clock() - c.fetched < ttl:
            return c.rows
        if not self.governor.allow(priority):
            self._note_degraded()
            if priority >= P3_SCAN_CHAIN:
                return []                      # entries need fresh; fail to no-entry
            return c.rows if c else []         # manage path may use the stale copy
        try:
            rows = self.client.get_option_chain(underlying.upper(), expiration, greeks=False)
        except Exception as exc:  # noqa: BLE001
            self.journal({"event": "hub_chain_error", "ts_epoch": time.time(),
                          "detail": f"{type(exc).__name__}: {exc}",
                          "underlying": underlying, "expiration": expiration})
            return [] if priority >= P3_SCAN_CHAIN else (c.rows if c else [])
        self._chains[key] = CachedChain(rows, self.clock())
        return rows

    def expiration_near_dte(self, underlying: str, target_dte: int, *, today: date,
                            priority: int = P3_SCAN_CHAIN) -> str | None:
        exps = self.expirations(underlying, priority=priority)
        if not exps:
            return None
        def key(e):
            try:
                y, m, d = map(int, e.split("-"))
                return abs((date(y, m, d) - today).days - target_dte)
            except ValueError:
                return 9999
        return min(exps, key=key)

    def _note_degraded(self) -> None:
        if getattr(self.governor, "entered_degraded", False):
            self.journal({"event": "lab_data_degraded", "ts_epoch": time.time(),
                          "used_per_min": self.governor.used(), "cap": self.governor.cap})

    # ---------------------------------------------------------------- daily history
    def daily_history(self, underlying: str, days: int = 260, *,
                      priority: int = P2_MANAGE_CHAIN) -> list:
        if not self.governor.allow(priority):
            return []
        try:
            return self.client.get_daily_history(underlying.upper(), days=days)
        except Exception as exc:  # noqa: BLE001
            self.journal({"event": "hub_history_error", "ts_epoch": time.time(),
                          "detail": f"{type(exc).__name__}: {exc}", "underlying": underlying})
            return []

    # ---------------------------------------------------------------- self-computed greeks
    @staticmethod
    def row_greeks(*, opt_type: str, strike: float, S: float, mid: float, dte_days: float,
                   r: float = SELECTION_R) -> dict | None:
        """Solve IV from mid and compute greeks (vendored, calendar T - selection use only).
        None when unsolvable (deep ITM/zero mid/expired)."""
        T = max(0.5, float(dte_days)) / 365.0
        try:
            iv = implied_vol(float(mid), float(S), float(strike), r, 0.0, T, opt_type)
            if iv is None or iv <= 0:
                return None
            g = bs_greeks(float(S), float(strike), r, 0.0, iv, T, opt_type)
            return {"iv": round(iv, 4), "delta": round(g.delta, 4),
                    "gamma": round(g.gamma, 6), "vega": round(g.vega, 4),
                    "theta_day": round(g.theta, 4)}
        except (ValueError, ZeroDivisionError, OverflowError):
            return None

    # ---------------------------------------------------------------- file-fed context
    def vol_regime(self, max_age_days: int = 5) -> dict | None:
        return self._read_json(self.runtime / "vol_regime.json")

    def earnings_week(self) -> dict:
        rec = self._read_json(self.runtime / "earnings_week.json") or {}
        return rec.get("by_symbol") or {}

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
