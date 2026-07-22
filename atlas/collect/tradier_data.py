"""Tradier market-data client (vendored 2026-07-03 from the user's options project and adapted).

WHY: Tradier production brokerage tokens get REAL-TIME consolidated-tape US equity quotes with a
DOCUMENTED 120 req/min cap - versus Robinhood's undocumented ~15-burst limit that forced the 25s
scan cadence and made per-symbol quote polling precious. One batched POST returns up to ~100
symbols' quotes INCLUDING bid/ask (NBBO), day volume, and 90-day average volume - i.e. price,
spread, AND a consolidated relative-volume estimate in a single request. USER DIRECTIVE
(2026-07-03): use Tradier to its fullest as the high-frequency data path; RH keeps orders, scans,
and the venue-truth exec quote at send time. The user runs only per-ticker scans in his options
calculator during ATLAS hours, so ATLAS budgets ~100/min of the 120 (MAX_PER_MINUTE below).

Design rules carried from the source (options/app/providers/tradier.py):
  * Pure module-level parsers, testable offline against recorded fixtures (tests/test_tradier_data.py).
  * Token-bucket throttle + 429 backoff honoring Retry-After.
  * Tradier collapses single-element arrays to a scalar - _as_list normalizes everywhere.
ATLAS adaptations: bid/ask/volume/average_volume on the quote (the options project only needed
last+dividend), a timesales (intraday bars) endpoint, dataclasses local to this module (no external
config import), and a from_local_config() constructor that returns None when config/tradier.local.yaml
is absent - every caller must degrade gracefully to the existing RH/Alpaca paths.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import yaml

PRODUCTION_BASE = "https://api.tradier.com"
SANDBOX_BASE = "https://sandbox.tradier.com"


@dataclass(frozen=True)
class TQuote:
    symbol: str
    last: float
    bid: float
    ask: float
    prevclose: float
    volume: float            # consolidated day volume
    average_volume: float    # ~90-day average day volume (0 when Tradier omits it)
    low: float = 0.0         # intraday session low (0 when omitted) - feeds the SSR self-compute
                             # (low <= 0.90 x prevclose); default keeps every existing consumer intact

    @property
    def rvol_day(self) -> float | None:
        """Cumulative consolidated relative volume (day volume / avg day volume); None if unknown."""
        if self.average_volume and self.average_volume > 0 and self.volume >= 0:
            return self.volume / self.average_volume
        return None


@dataclass(frozen=True)
class TOption:
    symbol: str              # OCC option symbol
    option_type: str         # "call" | "put"
    strike: float
    volume: float            # today's contract volume
    open_interest: float     # PRIOR-DAY open interest (OI updates only overnight - by design)
    bid: float = 0.0
    ask: float = 0.0
    # -- OPTIONS SHADOW extension (2026-07-09, O1): OPTIONAL fields, all defaulted so every
    # pre-existing construction/consumer is untouched. Populated by parse_option_chain when the
    # chain row carries them; the greeks block only arrives when get_option_chain(greeks=True).
    # NOTE: vendor greeks/IV are ORATS values updated ~hourly - decision greeks are SELF-COMPUTED
    # from live mid (plan: "never trust vendor greeks intraday"); these fields feed the EOD IV
    # archive + divergence tripwire only.
    last: float = 0.0        # last trade price (0 when the contract hasn't printed)
    expiration: str = ""     # YYYY-MM-DD (Tradier `expiration_date`); "" when omitted
    iv: float = 0.0          # ORATS implied vol: greeks.mid_iv, falling back to greeks.smv_vol
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0

    @property
    def mid(self) -> float:
        """(bid+ask)/2 when a two-sided market exists, else the last trade (0 if neither)."""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.last


@dataclass(frozen=True)
class TBar:
    ts: str                  # ISO timestamp (timesales) or YYYY-MM-DD (daily)
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float = 0.0        # timesales carries a per-bar vwap ("price" field); 0 for daily


# --------------------------------------------------------------------------- #
# Pure helpers / parsers (no network) - tested offline.
# --------------------------------------------------------------------------- #

def _as_list(value: Any) -> list[Any]:
    """Tradier collapses single-element arrays to a scalar/object; normalize."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_quotes_batch(payload: dict[str, Any]) -> dict[str, TQuote]:
    """Parse a (possibly multi-symbol) /v1/markets/quotes response into {SYMBOL: TQuote}."""
    quotes = _as_list((payload.get("quotes") or {}).get("quote"))
    out: dict[str, TQuote] = {}
    for q in quotes:
        sym = (q.get("symbol") or "").upper()
        if not sym:
            continue
        last = _f(q.get("last"))
        if last <= 0:
            last = _f(q.get("close")) or _f(q.get("prevclose"))
        out[sym] = TQuote(
            symbol=sym, last=last, bid=_f(q.get("bid")), ask=_f(q.get("ask")),
            prevclose=_f(q.get("prevclose")), volume=_f(q.get("volume")),
            average_volume=_f(q.get("average_volume")), low=_f(q.get("low")),
        )
    return out


def parse_timesales(payload: dict[str, Any]) -> list[TBar]:
    """Parse /v1/markets/timesales into ordered minute bars. Tradier's `price` field on a
    timesales row is the interval's volume-weighted price - kept as the bar vwap."""
    rows = _as_list((payload.get("series") or {}).get("data"))
    out: list[TBar] = []
    for r in rows:
        ts = str(r.get("time") or r.get("timestamp") or "")
        if not ts:
            continue
        out.append(TBar(ts=ts, open=_f(r.get("open")), high=_f(r.get("high")),
                        low=_f(r.get("low")), close=_f(r.get("close")),
                        volume=_f(r.get("volume")), vwap=_f(r.get("price"))))
    return out


def parse_expirations(payload: dict[str, Any]) -> list[str]:
    """Parse /v1/markets/options/expirations into an ordered list of YYYY-MM-DD strings."""
    dates = _as_list((payload.get("expirations") or {}).get("date"))
    return sorted(str(d) for d in dates if d)


def parse_calendar(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Parse /v1/markets/calendar into {ISO date: {"status": "open"|"closed", "close_min": int}}.
    `close_min` (minutes-of-day ET, from the RTH block's `open.end` "HH:MM") is present only for
    open days - a 13:00 half-day close parses to 780. Single-element collapse normalized;
    malformed rows are skipped (the session-calendar fallback tables carry the truth then)."""
    days = _as_list(((payload.get("calendar") or {}).get("days") or {}).get("day"))
    out: dict[str, dict[str, Any]] = {}
    for d in days:
        iso = str(d.get("date") or "")
        if not iso:
            continue
        status = str(d.get("status") or "").lower() or "closed"
        row: dict[str, Any] = {"status": status}
        end = str(((d.get("open") or {}) if isinstance(d.get("open"), dict) else {}).get("end") or "")
        if status == "open" and len(end) >= 4 and ":" in end:
            try:
                hh, mm = end.split(":", 1)
                row["close_min"] = int(hh) * 60 + int(mm[:2])
            except (TypeError, ValueError):
                pass
        out[iso] = row
    return out


def parse_option_chain(payload: dict[str, Any]) -> list[TOption]:
    """Parse /v1/markets/options/chains into TOption rows (single-element collapse normalized).

    Tolerant of the optional per-row extras: `last`, `expiration_date`, and - when the request
    was made with greeks=true - a `greeks` sub-object (ORATS) whose fields are
    delta/gamma/theta/vega/rho/phi/bid_iv/mid_iv/ask_iv/smv_vol/updated_at. We take mid_iv as
    the IV (falling back to smv_vol, ORATS's smoothed vol, when mid_iv is absent/zero). Any
    missing piece defaults to 0.0/"" - a plain greeks=false chain parses exactly as before.
    """
    rows = _as_list((payload.get("options") or {}).get("option"))
    out: list[TOption] = []
    for r in rows:
        if not isinstance(r, dict):
            continue                      # malformed row (Tradier hiccup) - skip, never crash
        sym = (r.get("symbol") or "").upper()
        opt_type = str(r.get("option_type") or "").lower()
        if not sym or opt_type not in ("call", "put"):
            continue
        g = r.get("greeks")
        if not isinstance(g, dict):
            g = {}                        # absent (greeks=false) or malformed -> all-zero greeks
        out.append(TOption(symbol=sym, option_type=opt_type, strike=_f(r.get("strike")),
                           volume=_f(r.get("volume")), open_interest=_f(r.get("open_interest")),
                           bid=_f(r.get("bid")), ask=_f(r.get("ask")),
                           last=_f(r.get("last")),
                           expiration=str(r.get("expiration_date") or ""),
                           iv=_f(g.get("mid_iv")) or _f(g.get("smv_vol")),
                           delta=_f(g.get("delta")), gamma=_f(g.get("gamma")),
                           theta=_f(g.get("theta")), vega=_f(g.get("vega"))))
    return out


def options_flow_features(options: "list[TOption]") -> dict:
    """Self-computed options-activity features (2026-07-04, M5) - FEATURES ONLY, no gate/veto
    (the academic long side needs signed open/close data Tradier doesn't have). OI updates only
    overnight, so live volume vs PRIOR-DAY OI is the opening-activity heuristic - documented,
    not a bug. Put-heavy flow is a caution note for the LLMs."""
    call_vol = sum(o.volume for o in options if o.option_type == "call")
    put_vol = sum(o.volume for o in options if o.option_type == "put")
    call_oi = sum(o.open_interest for o in options if o.option_type == "call")
    if call_vol + put_vol <= 0:
        return {}
    pcr = put_vol / max(1.0, call_vol)
    note = ("put_heavy_caution" if pcr >= 1.5
            else "call_heavy" if pcr <= 0.5 else "balanced")
    return {"put_call_vol_ratio": round(pcr, 3),
            "call_vol_vs_prior_oi": round(call_vol / max(1.0, call_oi), 3),
            "options_activity_note": note}


def parse_daily_history(payload: dict[str, Any]) -> list[TBar]:
    days = _as_list((payload.get("history") or {}).get("day"))
    out: list[TBar] = []
    for d in days:
        ts = str(d.get("date") or "")
        if not ts:
            continue
        out.append(TBar(ts=ts, open=_f(d.get("open")), high=_f(d.get("high")),
                        low=_f(d.get("low")), close=_f(d.get("close")),
                        volume=_f(d.get("volume"))))
    out.sort(key=lambda b: b.ts)
    return out


# --------------------------------------------------------------------------- #
# Live client.
# --------------------------------------------------------------------------- #

class TradierData:
    """REST client with a rate-limit guard and 429 backoff. ~100/min of the documented 120/min
    cap is ATLAS's share (the user's per-ticker options scans keep the remainder)."""

    MAX_PER_MINUTE = 100
    QUOTE_BATCH = 100        # symbols per batched POST

    def __init__(self, token: str, *, base_url: str = PRODUCTION_BASE, timeout: float = 5.0,
                 max_per_minute: int | None = None):
        if not token:
            raise ValueError("Tradier token is empty")
        self.max_per_minute = int(max_per_minute or self.MAX_PER_MINUTE)
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout)
        self._req_times: deque = deque()

    @classmethod
    def from_local_config(cls, path: Path | str = "config/tradier.local.yaml") -> "TradierData | None":
        """Build from the gitignored local config, or None (caller degrades to RH/Alpaca paths).
        Keys: token (required), env: production|sandbox, timeout_seconds, max_per_minute."""
        p = Path(path)
        try:
            cfg = yaml.safe_load(p.read_text("utf-8")) or {}
        except OSError:
            return None
        token = str(cfg.get("token") or "").strip()
        if not token:
            return None
        base = SANDBOX_BASE if str(cfg.get("env", "production")).lower() == "sandbox" else PRODUCTION_BASE
        try:
            return cls(token, base_url=base, timeout=float(cfg.get("timeout_seconds", 5.0)),
                       max_per_minute=int(cfg.get("max_per_minute", cls.MAX_PER_MINUTE)))
        except ValueError:
            return None

    # -- rate limiting -------------------------------------------------------
    def _throttle(self) -> None:
        now = time.monotonic()
        while self._req_times and now - self._req_times[0] > 60.0:
            self._req_times.popleft()
        if len(self._req_times) >= self.max_per_minute:
            sleep_for = 60.0 - (now - self._req_times[0]) + 0.05
            if sleep_for > 0:
                time.sleep(sleep_for)
        self._req_times.append(time.monotonic())

    def _request(self, method: str, path: str, params: dict[str, Any], retries: int = 2) -> dict[str, Any]:
        """One HTTP call with bounded retries. Audit 2026-07-16 TRADIER-FEED-1/2
        (opts-audit-wave1-funnel-v1): the old loop retried ONLY 429 - a single transient
        timeout/connect error/5xx was first-failure-fatal, and the chain-fetch caller killed
        the whole lane signal on one blip (~7 days of expected funnel output at the observed
        fire rate). Now: transport errors and 5xx retry with a short capped backoff;
        Retry-After is bounded (a '0' or HTTP-date header no longer hammers or crashes)."""
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            self._throttle()
            try:
                if method == "POST":
                    resp = self._client.post(path, data=params)
                else:
                    resp = self._client.get(path, params=params)
            except httpx.HTTPError as exc:            # timeouts, connect errors, protocol errors
                last_exc = exc
                if attempt < retries:
                    time.sleep(min(2.0, 0.5 * (2.0 ** attempt)))
                    continue
                raise
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else min(30.0, 2.0 ** attempt)
                except (TypeError, ValueError):       # HTTP-date form - never crash on a header
                    wait = min(30.0, 2.0 ** attempt)
                wait = min(30.0, max(0.5, wait))      # bounded; a '0' header no longer hammers
                if attempt < retries:
                    time.sleep(wait)
                    continue
            if 500 <= resp.status_code < 600 and attempt < retries:
                time.sleep(min(2.0, 0.5 * (2.0 ** attempt)))
                continue
            resp.raise_for_status()
            return resp.json()
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("unreachable")

    # -- data ------------------------------------------------------------------
    def get_quotes(self, symbols: list[str]) -> dict[str, TQuote]:
        """Batched real-time quotes: one POST per ~100 symbols. Raises on transport errors - 
        callers are expected to catch and fall back (protection never depends on one feed)."""
        out: dict[str, TQuote] = {}
        syms = [s.upper() for s in symbols if s]
        for i in range(0, len(syms), self.QUOTE_BATCH):
            chunk = syms[i:i + self.QUOTE_BATCH]
            payload = self._request("POST", "/v1/markets/quotes",
                                    {"symbols": ",".join(chunk), "greeks": "false"})
            out.update(parse_quotes_batch(payload))
        return out

    def get_timesales(self, symbol: str, *, interval: str = "1min",
                      start: str | None = None, end: str | None = None) -> list[TBar]:
        """Intraday consolidated bars (1min/5min/15min). start/end: 'YYYY-MM-DD HH:MM'."""
        params: dict[str, Any] = {"symbol": symbol.upper(), "interval": interval,
                                  "session_filter": "open"}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return parse_timesales(self._request("GET", "/v1/markets/timesales", params))

    def get_option_expirations(self, symbol: str) -> list[str]:
        """Listed expirations for `symbol` (nearest first)."""
        return parse_expirations(self._request("GET", "/v1/markets/options/expirations",
                                               {"symbol": symbol.upper()}))

    def get_option_chain(self, symbol: str, expiration: str, greeks: bool = False) -> list[TOption]:
        """Full chain for one expiration (volume + prior-day OI; greeks omitted by default - 
        100/min budget). greeks=True adds Tradier's ORATS greeks/IV block per row (~hourly
        refresh; EOD IV archive + tripwire use only - intraday decision greeks stay self-computed)."""
        return parse_option_chain(self._request("GET", "/v1/markets/options/chains",
                                                {"symbol": symbol.upper(),
                                                 "expiration": expiration,
                                                 "greeks": "true" if greeks else "false"}))

    def get_calendar(self, month: int, year: int) -> dict[str, dict[str, Any]]:
        """One month of the market calendar (per-day status + RTH close incl. half-day early
        closes) - the authoritative early-close source for atlas/options/session_calendar.py."""
        return parse_calendar(self._request("GET", "/v1/markets/calendar",
                                            {"month": f"{int(month):02d}", "year": str(int(year))}))

    def get_daily_history(self, symbol: str, days: int = 60) -> list[TBar]:
        end = date.today()
        start = end - timedelta(days=int(days * 1.6) + 10)
        return parse_daily_history(self._request("GET", "/v1/markets/history", {
            "symbol": symbol.upper(), "interval": "daily",
            "start": start.isoformat(), "end": end.isoformat()}))

    def close(self) -> None:
        self._client.close()
