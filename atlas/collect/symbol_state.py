"""Symbol operational STATE (2026-07-04) - trading halts, SEC-suspension denylist, self-computed SSR.

This is the DEFENSE layer the edge-source research earned (memory edge-source-research-2026-07-04):
the halt-REOPENING trade is dead (spreads 2x+, vol ~9x at resume - CCH JF 2002, Hautsch-Horvath JFE
2019), so halt data is worth exactly three things here: a scan-context veto (don't spend LLM
throughput on a name that cannot trade), a pre-submit ORDER GUARD (never send into a halt), and LLM
context. Same for SEC suspensions (instant 10-business-day halts, unreactable - pre-buy blacklist
only). SSR is CONTEXT ONLY: it restricts SHORTS and this is a long-only buyer.

Contracts (the plan's non-negotiables):
  * FAIL-OPEN: "halted" is asserted ONLY on affirmatively-fresh data (record age <= max_age_s,
    default 180s). Missing symbol / stale snapshot / dead feed => no reasons => trading proceeds.
    A down feed must never block a trading day.
  * "sec_suspended" has NO staleness bound - a suspension is a durable multi-day event; entries
    expire by their own release date instead.
  * SSR is computed CLIENT-SIDE from (intraday low, prior close): low <= 0.90 x prevclose. The
    Nasdaq SSR *file* is archival-proven to regenerate only ~4:15AM/~4:30PM ET - it is NOT an
    intraday source (do-NOT-build list) - so self-compute is the only sanctioned SSR source.
  * Feeds are stdlib-parsed (xml.etree), breaker-wrapped, and polled at most once per cycle
    (nasdaqtrader asks <=1/min; the ATLAS cycle is 120s). SEC endpoints REQUIRE the declared
    User-Agent (403 without it) - reuse catalysts._UA.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Mapping

from atlas.collect.catalysts import _SYMBOL_RE, _http_text  # shared fair-use UA + fetch shim
from atlas.fsutil import atomic_replace

HALT_RSS_URL = "https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"
SEC_SUSPENSION_RSS_URL = "https://www.sec.gov/enforcement-litigation/trading-suspensions/rss"

# A suspension runs 10 BUSINESS days (Exchange Act 12(k)); 14 calendar days covers that span.
_SUSPENSION_CALENDAR_DAYS = 14
# Halts older than this many calendar days are dropped even if never marked resumed: the feed
# carries years-dead rows. (Deliberately WIDER than the plan's current-day filter: a T1
# news-pending halt genuinely spans days/weekends - e.g. JZ halted Thu 07/02 was still halted
# Sat 07/04 - and a current-day-only filter would blind the guard to it on day 2.)
_MAX_HALT_AGE_DAYS = 7

_STATE_HALTED = "halted"
_STATE_SUSPENDED = "sec_suspended"
_STATE_SSR = "ssr_active"
_EPS = 1e-9


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce a possibly-corrupted persisted value to float - never raises. A hand-edited or
    torn symbol_state.json must never take a live cycle down (this platform has crashed on
    state-file corruption before - memory winError5-atomic-write-crash)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# Pure predicates (unit-tested without the live feeds).
# --------------------------------------------------------------------------- #

def ssr_active(intraday_low: "float | None", prev_close: "float | None") -> bool:
    """Reg-SHO short-sale-restriction trigger, self-computed: today's low touched -10% vs the prior
    close. Missing/zero inputs => False (no flag; SSR is context-only anyway)."""
    try:
        lo = float(intraday_low or 0.0)
        pc = float(prev_close or 0.0)
    except (TypeError, ValueError):
        return False
    if lo <= 0.0 or pc <= 0.0:
        return False
    return lo <= 0.90 * pc + _EPS


def state_reasons(symbol: str, snapshot: Mapping[str, Any], now_epoch: float,
                  max_age_s: float = 180.0) -> list[str]:
    """Operational-state reasons for `symbol`, subset of {halted, sec_suspended, ssr_active}.
    FAIL-OPEN contract: "halted" only when the record is affirmatively fresh (<= max_age_s old);
    a missing symbol, stale record, or empty snapshot yields [] and can never block anything.
    "sec_suspended" expires by its own release date, never by wall-age."""
    sym = (symbol or "").upper()
    out: list[str] = []
    if not isinstance(snapshot, Mapping):     # a torn / wrong-shape snapshot never crashes a cycle
        return out
    _halts = snapshot.get("halts")
    halt = _halts.get(sym) if isinstance(_halts, Mapping) else None
    if isinstance(halt, Mapping):
        try:
            # abs(): a record whose ts_epoch is in the FUTURE (clock rollback / corrupted persisted
            # state) must read STALE, not permanently-fresh - otherwise it would block that symbol's
            # submits indefinitely. A far-future age fails the bound in both directions -> fail-open.
            fresh = abs(now_epoch - float(halt.get("ts_epoch", 0.0))) <= float(max_age_s)
        except (TypeError, ValueError):
            fresh = False
        if fresh:
            out.append(_STATE_HALTED)
    _susps = snapshot.get("suspensions")
    susp = _susps.get(sym) if isinstance(_susps, Mapping) else None
    if isinstance(susp, Mapping):
        try:
            active = now_epoch < float(susp.get("released_epoch", 0.0))
        except (TypeError, ValueError):
            active = False
        if active:
            out.append(_STATE_SUSPENDED)
    _ssr = snapshot.get("ssr")
    if isinstance(_ssr, Mapping) and _ssr.get(sym):
        out.append(_STATE_SSR)
    return out


# --------------------------------------------------------------------------- #
# Pure parsers (recorded-fixture-tested; stdlib xml.etree only).
# --------------------------------------------------------------------------- #

def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _halt_time_seconds(hms: str) -> float:
    """HaltTime 'HH:MM:SS.mmm' -> seconds-since-midnight for a NUMERIC latest-row compare. A
    lexicographic string compare would rank '9:45' after '10:05' if the feed ever drops zero-
    padding; parse defensively (unparseable -> 0.0, never raises)."""
    parts = (hms or "").split(":")
    try:
        h = float(parts[0]) if len(parts) > 0 and parts[0] else 0.0
        m = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
        s = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
        return h * 3600.0 + m * 60.0 + s
    except (TypeError, ValueError):
        return 0.0


def _parse_mdy(mdy: str) -> "date | None":
    m = re.match(r"^\s*(\d{2})/(\d{2})/(\d{4})", mdy or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def parse_halt_rss(xml_text: str, *, today: str, fetch_epoch: float,
                   max_age_days: int = _MAX_HALT_AGE_DAYS) -> dict[str, dict]:
    """{SYMBOL: {reason, code, name, halt_date, ts_epoch}} for halts still ACTIVE (latest row per
    symbol has no ResumptionTradeTime) within the age window. Unknown tags are ignored; malformed
    rows are skipped - a schema drift shrinks coverage, never raises. ts_epoch = the FETCH time:
    the order guard's freshness bound is about how current our DATA is, not how old the halt is."""
    try:
        today_d = date.fromisoformat((today or "")[:10])
    except ValueError:
        return {}
    root = ET.fromstring(xml_text)
    latest: dict[str, tuple[tuple[str, str], dict]] = {}
    for item in root.iter():
        if _localname(item.tag) != "item":
            continue
        f: dict[str, str] = {}
        for child in item:
            f[_localname(child.tag)] = (child.text or "").strip()
        sym = f.get("IssueSymbol", "").upper()
        if not _SYMBOL_RE.match(sym):
            continue
        halt_d = _parse_mdy(f.get("HaltDate", ""))
        if halt_d is None:
            continue
        age_days = (today_d - halt_d).days
        if age_days < 0 or age_days > max_age_days:
            continue
        key = (halt_d.toordinal(), _halt_time_seconds(f.get("HaltTime", "")))
        rec = {"reason": f.get("ReasonCode", "") or "halt", "code": f.get("ReasonCode", ""),
               "name": f.get("IssueName", ""), "halt_date": halt_d.isoformat(),
               "resumed": bool(f.get("ResumptionTradeTime", "")), "ts_epoch": float(fetch_epoch)}
        prior = latest.get(sym)
        if prior is None or key >= prior[0]:
            latest[sym] = (key, rec)
    out: dict[str, dict] = {}
    for sym, (_key, rec) in latest.items():
        if rec.pop("resumed"):
            continue                       # latest halt event already has a resumption print
        out[sym] = rec
    return out


def parse_suspension_rss(xml_text: str, *,
                         release_days: int = _SUSPENSION_CALENDAR_DAYS) -> list[dict]:
    """SEC trading-suspension items -> [{name, order_url, start_epoch, released_epoch, released}].
    The feed titles carry COMPANY NAMES only (no tickers - verified live 2026-07-04); resolution
    to a ticker is the caller's job (EntityResolver, high-confidence only). Items whose release
    window already lapsed are still returned - the caller filters by released_epoch."""
    root = ET.fromstring(xml_text)
    out: list[dict] = []
    for item in root.iter():
        if _localname(item.tag) != "item":
            continue
        f: dict[str, str] = {}
        for child in item:
            f[_localname(child.tag)] = (child.text or "").strip()
        name = f.get("title", "")
        if not name:
            continue
        try:
            start = parsedate_to_datetime(f.get("pubDate", "")).timestamp()
        except (TypeError, ValueError):
            continue
        released_epoch = start + float(release_days) * 86400.0
        out.append({
            "name": name, "order_url": f.get("link", ""), "start_epoch": start,
            "released_epoch": released_epoch,
            "released": date.fromtimestamp(released_epoch).isoformat(),
        })
    return out


# --------------------------------------------------------------------------- #
# Poller.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SymbolStateParams:
    enabled: bool = False
    poll_every_cycles: int = 1
    halt_rss: bool = True
    sec_suspensions: bool = True
    max_state_age_seconds: float = 180.0
    ssr_self_compute: bool = True
    timeout: float = 8.0

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any] | None) -> "SymbolStateParams":
        r = dict(raw or {})
        return cls(
            enabled=bool(r.get("enabled", False)),
            poll_every_cycles=max(1, int(r.get("poll_every_cycles", 1))),
            halt_rss=bool(r.get("halt_rss", True)),
            sec_suspensions=bool(r.get("sec_suspensions", True)),
            max_state_age_seconds=float(r.get("max_state_age_seconds", 180.0)),
            ssr_self_compute=bool(r.get("ssr_self_compute", True)),
            timeout=float(r.get("timeout_seconds", 8.0)),
        )


class _Breaker:
    """Per-feed circuit breaker, same discipline as CatalystFeed: N consecutive failures open it
    for a cooldown of zero-cost cycles; existing state simply ages (halts) or persists to its own
    expiry (suspensions) while open."""

    def __init__(self, failures: int = 3, cooldown_seconds: float = 900.0):
        self._fails = 0
        self._open_until = 0.0
        self._failures = int(failures)
        self._cooldown = float(cooldown_seconds)
        self.last_error: str = ""

    def ok(self, now_epoch: float) -> bool:
        return now_epoch >= self._open_until

    def success(self) -> None:
        self._fails = 0
        self.last_error = ""

    def failure(self, now_epoch: float, exc: Exception) -> None:
        self._fails += 1
        self.last_error = repr(exc)[:200]
        if self._fails >= self._failures:
            self._open_until = now_epoch + self._cooldown
            self._fails = 0


class SymbolStatePoller:
    """Owns the symbol-state snapshot: {halts, suspensions, ssr}. poll() never raises. State is
    persisted to runtime/symbol_state.json (atomic) so suspensions survive restarts - halts
    deliberately go stale across a restart (ts_epoch ages out => fail-open until the first poll)."""

    def __init__(self, params: SymbolStateParams, *, resolver=None,
                 state_path: Path | str | None = None):
        self.p = params
        self.resolver = resolver               # EntityResolver | None (suspension names -> tickers)
        self.state_path = Path(state_path) if state_path else None
        self.halts: dict[str, dict] = {}
        self.suspensions: dict[str, dict] = {}
        self.ssr: dict[str, bool] = {}
        self.generated_epoch = 0.0
        self.cycle_epoch = 0.0                 # set by the orchestrator each cycle (sim-safe clock)
        self.unresolved_count = 0              # suspension names with no confident ticker
        self._halt_brk = _Breaker()
        self._susp_brk = _Breaker()
        self.load()

    # ---- polling ---------------------------------------------------------------
    def poll(self, now_iso: str, now_epoch: float, cycle: int = 0) -> None:
        if not self.p.enabled or (cycle % self.p.poll_every_cycles) != 0:
            return
        if self.p.halt_rss and self._halt_brk.ok(now_epoch):
            try:
                text = _http_text(HALT_RSS_URL, timeout=self.p.timeout)
                self.halts = parse_halt_rss(text, today=now_iso[:10], fetch_epoch=now_epoch)
                self._halt_brk.success()
            except Exception as exc:  # noqa: BLE001 - stale halts age out; guard fail-opens
                self._halt_brk.failure(now_epoch, exc)
        if self.p.sec_suspensions and self._susp_brk.ok(now_epoch):
            try:
                text = _http_text(SEC_SUSPENSION_RSS_URL, timeout=self.p.timeout)
                for entry in parse_suspension_rss(text):
                    if entry["released_epoch"] <= now_epoch:
                        continue               # release window already lapsed
                    ticker = self._resolve(entry["name"])
                    if not ticker:
                        self.unresolved_count += 1
                        continue
                    self.suspensions[ticker] = {
                        "name": entry["name"], "order": entry["order_url"],
                        "released": entry["released"],
                        "released_epoch": entry["released_epoch"],
                    }
                self._susp_brk.success()
            except Exception as exc:  # noqa: BLE001 - existing denylist entries persist (durable)
                self._susp_brk.failure(now_epoch, exc)
        # Entries expire by their own release date, not wall-age (10-business-day events).
        # _safe_float so a corrupted released_epoch can never raise here (poll() never raises).
        self.suspensions = {s: v for s, v in self.suspensions.items()
                            if _safe_float((v or {}).get("released_epoch"), 0.0) > now_epoch}
        self.generated_epoch = now_epoch
        self.save()

    def _resolve(self, name: str) -> "str | None":
        if self.resolver is None:
            return None
        try:
            return self.resolver.resolve(name)
        except Exception:  # noqa: BLE001 - resolver trouble == unresolvable, never fatal
            return None

    # ---- SSR self-compute --------------------------------------------------------
    def update_ssr(self, low_prev_by_symbol: Mapping[str, tuple]) -> None:
        """Recompute the SSR flags for this cycle's bounded set (candidates + held) from
        (intraday_low, prev_close) pairs. Whole-map replace: SSR is context-only and recomputed
        from fresh tape every cycle - names outside the set simply carry no flag."""
        if not (self.p.enabled and self.p.ssr_self_compute):
            return
        ssr: dict[str, bool] = {}
        for sym, pair in low_prev_by_symbol.items():
            try:
                lo, pc = pair
            except (TypeError, ValueError):
                continue
            if ssr_active(lo, pc):
                ssr[(sym or "").upper()] = True
        self.ssr = ssr
        self.save()

    # ---- reads ---------------------------------------------------------------------
    def snapshot(self) -> dict:
        return {"halts": self.halts, "suspensions": self.suspensions, "ssr": self.ssr,
                "generated_epoch": self.generated_epoch,
                "unresolved_count": self.unresolved_count,
                "feeds": [{"name": "halt_rss", "breaker_error": self._halt_brk.last_error},
                          {"name": "sec_suspensions", "breaker_error": self._susp_brk.last_error}]}

    snapshot_for_hub = snapshot

    def reasons(self, symbol: str, now_epoch: float) -> tuple[str, ...]:
        return tuple(state_reasons(symbol, self.snapshot(), now_epoch,
                                   self.p.max_state_age_seconds))

    def reasons_cycle(self, symbol: str) -> tuple[str, ...]:
        """Reasons at the orchestrator-stamped cycle epoch (discovery-path hook). Before the first
        cycle stamp, everything reads stale => () => fail-open, by construction."""
        return self.reasons(symbol, self.cycle_epoch)

    def features_for(self, symbol: str) -> dict:
        """Deterministic candidate-feature keys (context, never a gate): ssr_active only."""
        return {"ssr_active": 1.0} if self.ssr.get((symbol or "").upper()) else {}

    # ---- persistence -----------------------------------------------------------------
    def save(self) -> None:
        if self.state_path is None:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_name(self.state_path.name + ".tmp")
            tmp.write_text(json.dumps(self.snapshot(), ensure_ascii=False), encoding="utf-8")
            atomic_replace(tmp, self.state_path)
        except OSError:
            pass                               # telemetry/state publish must never break a cycle

    def load(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.halts = {str(k).upper(): dict(v) for k, v in (data.get("halts") or {}).items()
                      if isinstance(v, dict)}
        self.suspensions = {str(k).upper(): dict(v) for k, v in
                            (data.get("suspensions") or {}).items() if isinstance(v, dict)}
        self.ssr = {str(k).upper(): bool(v) for k, v in (data.get("ssr") or {}).items()}
        try:
            self.generated_epoch = float(data.get("generated_epoch", 0.0))
        except (TypeError, ValueError):
            self.generated_epoch = 0.0
