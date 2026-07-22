"""Catalyst event feeds - OPTIONS revival (mission reincorporate-cut-systems, 2026-07-12):
context/defensive CONTEXT feeds only. DefenseGov/SamGov/Sentinel (govcon/localhost) removed;
the tape-confirmation WATCH mechanism lives in catalyst_book.py, not here. Original below.

Catalyst event feeds (2026-07-03) - external, NON-PRICE information sources.

THE RULE (research round 1, frequency math + the user's own "no GME-pumping" requirement): an
external event may only ever decide WHEN the system looks at a name - never WHETHER it trades,
never WHERE it ranks. Every provider here emits deterministic CatalystEvents; the pipeline
(atlas/catalyst_pipeline.py) turns them into (a) untrusted-fenced CONTEXT for both LLMs and (b)
bounded tape-confirmation WATCHES that re-enter the FULL gate set. No code path exists from
event magnitude to quality/ranking.

Feed philosophy mirrors NewsFeed (atlas/collect/feeds.py): poll() returns a list and NEVER raises;
each feed carries its own circuit breaker (consecutive failures -> open for cooldown -> zero-cost
cycles). ALL text from these sources is machine-authored and untrusted (see
[[robot-instructions-untrusted]]) - headlines/details are length-clamped and rendered through the
same prompt fence as news.

Channel notes (verified live 2026-07-03):
  * EDGAR full-text search (efts.sec.gov) - REAL-TIME, free, UA-header-only; 8-K Item 1.01 is
    "entry into a material definitive agreement": material to the filer BY DEFINITION and already
    ticker-attributed in display_names. THE primary live channel.
  * defense.gov/war.gov daily ~17:00 ET contracts digest - the RSS (ContentType=400) works, but the
    article BODIES are Akamai-bot-walled (403 on every local HTTP stack). Implemented + shipped
    DISABLED; flip on if the wall drops. FPDS/USAspending publish DoD awards on a 90-DAY delay - 
    useless live, fine for backtests.
  * SAM.gov opportunities API (award notices) - free key (SAM_GOV_API_KEY); civilian ~same-day.
  * iborrowdesk (IBKR borrow data) - fee snapshots; EVIDENCE-BOUND to context+watch only (high-fee
    longs have NEGATIVE average returns; the spike is a look-trigger, not a signal).
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Mapping

_UA = "ATLAS-research/1.0 (you@example.com)"
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
# Ticker inside EDGAR display_names: "Acme Corp  (ACME)  (CIK 0001234567)"
_EDGAR_TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,9})\)\s*\(CIK")
_DOLLARS_RE = re.compile(r"\$([\d,]{7,})")           # first $X,XXX,XXX+ figure in a DoD paragraph
_MAX_HEADLINE = 200
_MAX_DETAIL = 240


def materiality_for_amount(amount_usd: float) -> float:
    """A-priori govcon materiality tiers (ported from the user's Sentinel platform - do not fit):
    $10M -> 12, $50M -> 18, $100M -> 25, below $10M -> 0 (ignored)."""
    if amount_usd >= 100e6:
        return 25.0
    if amount_usd >= 50e6:
        return 18.0
    if amount_usd >= 10e6:
        return 12.0
    return 0.0


@dataclass(frozen=True)
class CatalystEvent:
    """One deterministic external event, symbol-attributed. Frozen: providers may not mutate."""
    event_id: str            # stable dedup key: f"{source}|{kind}|{symbol}|{source_ts[:13]}" (hour bucket)
    symbol: str
    kind: str                # e.g. "edgar.8k.material_agreement" | "govcon.dod.daily_award"
                             # | "borrow.squeeze_setup" | "sentinel.<correlation_kind>"
    headline: str            # deterministic provider-formatted one-liner (<=200 chars, fenced later)
    detail: str              # deterministic detail (<=240 chars)
    magnitude: float         # provider scale: materiality 0-100 (never touches quality/rank)
    observed_at_iso: str     # ATLAS ingestion timestamp
    source_ts_iso: str       # provider event timestamp - the TTL anchor
    source: str
    ttl_seconds: float
    numbers: dict = field(default_factory=dict)   # whitelisted numeric context -> candidate features

    @staticmethod
    def build(*, symbol: str, kind: str, headline: str, detail: str, magnitude: float,
              observed_at_iso: str, source_ts_iso: str, source: str, ttl_seconds: float,
              numbers: dict | None = None) -> "CatalystEvent | None":
        sym = (symbol or "").upper().strip()
        if not _SYMBOL_RE.match(sym):
            return None
        return CatalystEvent(
            event_id=f"{source}|{kind}|{sym}|{(source_ts_iso or observed_at_iso)[:13]}",
            symbol=sym, kind=str(kind), headline=str(headline)[:_MAX_HEADLINE],
            detail=str(detail)[:_MAX_DETAIL], magnitude=float(magnitude),
            observed_at_iso=str(observed_at_iso), source_ts_iso=str(source_ts_iso or observed_at_iso),
            source=str(source), ttl_seconds=float(ttl_seconds), numbers=dict(numbers or {}))


def _http_json(url: str, *, timeout: float, headers: Mapping[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _http_text(url: str, *, timeout: float, headers: Mapping[str, str] | None = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _is_rate_limited(exc: Exception) -> bool:
    """True if an exception looks like an HTTP 429 / daily-quota rejection. Retrying a rate-limit soon
    just re-burns the (often per-DAY) quota, so the caller backs off for a long cooldown instead.
    The `.code` check is authoritative for urllib HTTPError; the string fallback is word-boundaried so a
    URL/id containing '4290' or '1429' is NOT misread as a rate-limit."""
    if getattr(exc, "code", None) == 429:            # urllib.error.HTTPError carries .code
        return True
    s = repr(exc).lower()
    return ("too many requests" in s or "rate limit" in s or "over_rate_limit" in s
            or bool(re.search(r"\b429\b", s)))


class CatalystFeed:
    """Base: poll() NEVER raises; a per-feed circuit breaker turns repeated failures into zero-cost
    cycles. Subclasses implement _poll_once(now_iso, now_epoch) and may raise freely inside it.

    Two independent throttles on top of the pipeline's global poll_every_cycles:
      * min_interval_seconds - a per-feed floor between real polls, for a source whose data changes far
        less often than the cycle cadence (e.g. SAM.gov award notices update ~daily; polling every 10 min
        wastes a small free-key daily quota). Default 0 = no extra throttle (EDGAR etc. unchanged).
      * ratelimit_cooldown_seconds - how long to go quiet after an HTTP 429 / quota rejection. A 429 opens
        the breaker IMMEDIATELY (not after breaker_failures) for THIS long, because the quota won't reset
        for hours; the old 15-min breaker just retried into another 429 all day (the 2026-07-06 SAM.gov
        lockout). Defaults to breaker_cooldown_seconds."""

    name = "base"

    def __init__(self, *, breaker_failures: int = 3, breaker_cooldown_seconds: float = 900.0,
                 min_interval_seconds: float = 0.0, ratelimit_cooldown_seconds: float | None = None):
        self._fails = 0
        self._open_until = 0.0
        self._breaker_failures = int(breaker_failures)
        self._breaker_cooldown = float(breaker_cooldown_seconds)
        self._min_interval = max(0.0, float(min_interval_seconds))
        self._ratelimit_cooldown = float(ratelimit_cooldown_seconds
                                         if ratelimit_cooldown_seconds is not None else breaker_cooldown_seconds)
        self._last_attempt = 0.0
        self.last_error: str = ""

    def breaker_open(self, now_epoch: float) -> bool:
        return now_epoch < self._open_until

    def poll(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:
        if self.breaker_open(now_epoch):
            return []
        # Per-feed rate floor: skip if the last ATTEMPT (success OR failure) was within min_interval.
        # `_last_attempt == 0.0` means never polled -> always take the first poll (clock-independent).
        if (self._min_interval > 0.0 and self._last_attempt > 0.0
                and (now_epoch - self._last_attempt) < self._min_interval):
            return []
        self._last_attempt = now_epoch
        try:
            events = self._poll_once(now_iso, now_epoch) or []
            self._fails = 0
            self.last_error = ""
            return [e for e in events if e is not None]
        except Exception as exc:  # noqa: BLE001 - a feed must never take the cycle down
            self.last_error = repr(exc)[:200]
            if _is_rate_limited(exc):
                # 429 / quota: back off HARD (hours), not the 15-min retry loop that re-burns the quota.
                self._open_until = now_epoch + self._ratelimit_cooldown
                self._fails = 0
                return []
            self._fails += 1
            if self._fails >= self._breaker_failures:
                self._open_until = now_epoch + self._breaker_cooldown
                self._fails = 0
            return []

    def _poll_once(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:  # pragma: no cover
        raise NotImplementedError


class NullCatalystFeed(CatalystFeed):
    name = "null"

    def _poll_once(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:
        return []


class EdgarMaterialEventsFeed(CatalystFeed):
    """SEC EDGAR full-text search: today's 8-K filings carrying the configured items. Ticker comes
    straight from display_names, so no entity resolution is needed; filers without a listed ticker
    (funds, LLCs) drop out naturally.

    POLARITY SPLIT (2026-07-04, M4): items in `negative_items` (default 1.03 bankruptcy, 3.01
    delisting notice) are emitted with source="edgar_neg" - a _DEFENSIVE_SOURCE in the pipeline
    (never a watch, never an eval; feeds bankruptcy_risk/delisting_risk flags). A delisting can
    never become a bullish look-trigger. Positive/neutral items stay on source="edgar" (context
    via the global mode; the 1.01 watch trigger is REFUTED at n=752 and stays out of
    watch.sources permanently unless a narrowed cohort validates)."""

    name = "edgar"
    BASE = "https://efts.sec.gov/LATEST/search-index"
    _ITEM_KINDS = {"1.01": "edgar.8k.material_agreement",
                   "2.01": "edgar.8k.acquisition_completed",
                   "5.02": "edgar.8k.officer_change",
                   "1.03": "edgar.8k.bankruptcy",
                   "3.01": "edgar.8k.delisting_notice"}

    def __init__(self, *, items: tuple[str, ...] = ("1.01",),
                 negative_items: tuple[str, ...] = ("1.03", "3.01"), ttl_hours: float = 24.0,
                 timeout: float = 6.0, magnitude: float = 15.0, **kw):
        super().__init__(**kw)
        self.items = tuple(items)
        self.negative_items = tuple(negative_items)
        self.ttl = float(ttl_hours) * 3600.0
        self.timeout = float(timeout)
        self.magnitude = float(magnitude)   # a-priori: "material by SEC definition"; NOT a rank input

    def _kind_for(self, item: str) -> str:
        return self._ITEM_KINDS.get(item, f"edgar.8k.item_{item.replace('.', '_')}")

    def _poll_once(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:
        day = now_iso[:10]
        q = urllib.parse.urlencode({"q": "", "forms": "8-K", "startdt": day, "enddt": day})
        data = _http_json(f"{self.BASE}?{q}", timeout=self.timeout)
        out: list[CatalystEvent] = []
        for hit in (data.get("hits", {}).get("hits", []) or []):
            src = hit.get("_source") or {}
            items = [str(i) for i in (src.get("items") or [])]
            if not any(i in items for i in self.items):
                continue
            names = src.get("display_names") or []
            m = _EDGAR_TICKER_RE.search(str(names[0])) if names else None
            if not m:
                continue                      # no listed ticker -> not tradable -> drop
            company = str(names[0]).split("(")[0].strip()
            matched = sorted(set(items) & set(self.items))
            neg = [i for i in matched if i in self.negative_items]
            pos = [i for i in matched if i not in self.negative_items]
            # One filing can emit BOTH: the positive/neutral context event AND the negative risk
            # event (e.g. an 8-K carrying 1.01 + 1.03) - different sources, different consumers.
            if pos:
                out.append(CatalystEvent.build(
                    symbol=m.group(1), kind=self._kind_for(pos[0]),
                    headline=f"8-K Item {'/'.join(pos)} filed by {company}",
                    detail=f"SEC 8-K items={','.join(items)} filed {src.get('file_date', day)}",
                    magnitude=self.magnitude, observed_at_iso=now_iso,
                    source_ts_iso=str(src.get("file_date") or day), source="edgar",
                    ttl_seconds=self.ttl, numbers={"catalyst_materiality": self.magnitude}))
            if neg:
                out.append(CatalystEvent.build(
                    symbol=m.group(1), kind=self._kind_for(neg[0]),
                    headline=f"NEGATIVE 8-K Item {'/'.join(neg)} filed by {company}",
                    detail=f"SEC 8-K items={','.join(items)} filed {src.get('file_date', day)}; "
                           f"bankruptcy/delisting class - defensive risk flag",
                    magnitude=self.magnitude, observed_at_iso=now_iso,
                    source_ts_iso=str(src.get("file_date") or day), source="edgar_neg",
                    ttl_seconds=self.ttl, numbers={}))
        return out


class Schedule13DFeed(CatalystFeed):
    """Schedule 13D activist-stake filings via EDGAR EFTS (2026-07-04, M4). CONTEXT ONLY for
    now: a-priori constant magnitude, no cohort validation yet - do NOT add "edgar13d" to
    watch.sources until one exists. NOTE (verified live 2026-07-04): since the SEC's structured
    13D/G modernization the EFTS form type is "SCHEDULE 13D" (root form also matches /A
    amendments) - the legacy "SC 13D" string returns ZERO hits."""

    name = "edgar13d"
    BASE = EdgarMaterialEventsFeed.BASE

    def __init__(self, *, forms: tuple[str, ...] = ("SCHEDULE 13D",),
                 ttl_hours: float = 48.0, timeout: float = 6.0, magnitude: float = 20.0, **kw):
        super().__init__(**kw)
        self.forms = tuple(str(f) for f in forms)
        self.ttl = float(ttl_hours) * 3600.0
        self.timeout = float(timeout)
        self.magnitude = float(magnitude)

    def _poll_once(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:
        day = now_iso[:10]
        q = urllib.parse.urlencode({"q": "", "forms": ",".join(self.forms),
                                    "startdt": day, "enddt": day})
        data = _http_json(f"{self.BASE}?{q}", timeout=self.timeout)
        out: list[CatalystEvent] = []
        for hit in (data.get("hits", {}).get("hits", []) or []):
            src = hit.get("_source") or {}
            names = src.get("display_names") or []
            m = _EDGAR_TICKER_RE.search(str(names[0])) if names else None
            if not m:
                continue
            company = str(names[0]).split("(")[0].strip()
            ftype = str(src.get("file_type") or src.get("root_form") or "SC 13D")
            out.append(CatalystEvent.build(
                symbol=m.group(1), kind="edgar.13d.activist_stake",
                headline=f"{ftype} activist/5%+ stake filing on {company}",
                detail=f"SEC {ftype} filed {src.get('file_date', day)}; context only "
                       f"(no cohort validation yet)",
                magnitude=self.magnitude, observed_at_iso=now_iso,
                source_ts_iso=str(src.get("file_date") or day), source="edgar13d",
                ttl_seconds=self.ttl, numbers={"catalyst_materiality": self.magnitude}))
        return out


def parse_form4_xml(xml_text: str) -> "dict | None":
    """Pure ownershipDocument (Form 4) parser - shared by the LIVE feed and the offline validator.
    Returns {symbol, owner, is_officer_or_director, buy_value, buy_shares} summing OPEN-MARKET
    PURCHASES only (nonDerivative transactionCode == 'P', acquired 'A'); None on malformed XML or
    no issuer symbol. Sales/grants/derivatives are ignored by design: the validated sector is the
    prompt reaction to insider BUYS (Oenschlaeger-Moellenhoff FRL 2025)."""
    import xml.etree.ElementTree as _ET
    try:
        root = _ET.fromstring(xml_text)
    except _ET.ParseError:
        return None
    sym = (root.findtext(".//issuer/issuerTradingSymbol") or "").upper().strip()
    if not _SYMBOL_RE.match(sym):
        return None
    owner = (root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or "").strip()

    def _flag(tag: str) -> bool:
        v = (root.findtext(f".//reportingOwner/reportingOwnerRelationship/{tag}") or "").strip()
        return v in ("1", "true", "True")

    buy_value = buy_shares = 0.0
    for txn in root.iter("nonDerivativeTransaction"):
        code = (txn.findtext(".//transactionCoding/transactionCode") or "").strip()
        acq = (txn.findtext(".//transactionAcquiredDisposedCode/value") or "A").strip()
        if code != "P" or acq != "A":
            continue
        try:
            shares = float(txn.findtext(".//transactionShares/value") or 0.0)
            price = float(txn.findtext(".//transactionPricePerShare/value") or 0.0)
        except (TypeError, ValueError):
            continue
        buy_value += shares * price
        buy_shares += shares
    return {"symbol": sym, "owner": owner,
            "is_officer_or_director": _flag("isOfficer") or _flag("isDirector"),
            "buy_value": buy_value, "buy_shares": buy_shares}


class Form4InsiderBuyFeed(CatalystFeed):
    """The ONE new alpha-bearing sector from the 2026-07-04 edge-source research: prompt reaction
    to Form 4 insider open-market BUYS still earns positive (decayed) abnormal returns concentrated
    in illiquid small caps (Oenschlaeger-Moellenhoff FRL 2025) - exactly our habitat. Ships as a
    NORMAL source under the global mode=context_only ladder; it may only ever influence entries
    after scripts/validate_form4_catalyst.py PASSES + 5 clean shadow sessions + the USER adds
    "insider" to catalysts.watch.sources. Channel: EDGAR getcurrent atom (sub-second dissemination,
    verified live) -> per-filing ownershipDocument XML, ticker straight from the filing (no
    resolver). Cluster bonus (>= cluster_min distinct insiders in a rolling window) raises
    MAGNITUDE only - magnitude orders feed ingest and NOTHING else (never quality, never rank)."""

    name = "insider"
    GETCURRENT = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4"
                  "&company=&dateb=&owner=include&count=40&output=atom")
    _ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
    _TITLE_RE = re.compile(r"<title>([^<]*)</title>")
    _HREF_RE = re.compile(r'href="([^"]+)"')
    _XMLDOC_RE = re.compile(r'href="([^"]+?\.xml)"', re.I)

    def __init__(self, window_state: dict, *, min_value_usd: float = 20000.0,
                 cluster_window_days: float = 15.0, cluster_min_insiders: int = 3,
                 ttl_hours: float = 48.0, max_filings_per_poll: int = 10,
                 timeout: float = 8.0, **kw):
        super().__init__(**kw)
        self.window = window_state            # {SYM: [{"owner": str, "ts": epoch}]} - pipeline-persisted
        self.min_value = float(min_value_usd)
        self.window_days = float(cluster_window_days)
        self.cluster_min = int(cluster_min_insiders)
        self.ttl = float(ttl_hours) * 3600.0
        self.max_filings = int(max_filings_per_poll)
        self.timeout = float(timeout)
        self._seen_acc: set[str] = set()      # accessions already fetched (process-lifetime)

    def _cluster_count(self, sym: str, owner: str, now_epoch: float) -> int:
        ring = [r for r in self.window.get(sym, [])
                if now_epoch - float(r.get("ts", 0.0)) <= self.window_days * 86400.0]
        if owner and owner not in {r.get("owner") for r in ring}:
            ring.append({"owner": owner, "ts": now_epoch})
        self.window[sym] = ring[-16:]
        return len({r.get("owner") for r in ring})

    def _poll_once(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:
        atom = _http_text(self.GETCURRENT, timeout=self.timeout)
        out: list[CatalystEvent] = []
        fetched = 0
        for entry in self._ENTRY_RE.findall(atom):
            if fetched >= self.max_filings:
                break
            tm = self._TITLE_RE.search(entry)
            title = tm.group(1) if tm else ""
            if not title.strip().startswith("4 "):
                continue                       # exactly form 4 (skip 4/A amendments etc.)
            href = self._HREF_RE.search(entry)
            if not href:
                continue
            index_url = href.group(1)
            acc = index_url.rsplit("/", 1)[-1]
            if acc in self._seen_acc:
                continue
            self._seen_acc.add(acc)
            if len(self._seen_acc) > 800:
                self._seen_acc = set(list(self._seen_acc)[-400:])
            fetched += 1
            try:
                index_html = _http_text(index_url, timeout=self.timeout)
                m = None
                for cand in self._XMLDOC_RE.finditer(index_html):
                    u = cand.group(1).replace("/xslF345X05", "").replace("/xslF345X03", "")
                    if "/Archives/edgar/data/" in u:
                        m = u
                        break
                if not m:
                    continue
                xml_url = m if m.startswith("http") else f"https://www.sec.gov{m}"
                parsed = parse_form4_xml(_http_text(xml_url, timeout=self.timeout))
            except Exception:  # noqa: BLE001 - one bad filing must not kill the poll
                continue
            if not parsed or not parsed["is_officer_or_director"]:
                continue
            if parsed["buy_value"] < self.min_value:
                continue
            sym = parsed["symbol"]
            n = self._cluster_count(sym, parsed["owner"], now_epoch)
            cluster = n >= self.cluster_min
            out.append(CatalystEvent.build(
                symbol=sym, kind="insider.buy",
                headline=(f"Insider open-market buy ~${parsed['buy_value'] / 1e3:.0f}k by "
                          f"{(parsed['owner'] or 'officer/director')[:50]}"
                          + (f" ({n} insiders/{self.window_days:.0f}d cluster)" if cluster else "")),
                detail=f"Form 4 P-purchase, {parsed['buy_shares']:.0f} sh; officer/director; "
                       f"context_only pending cohort validation",
                magnitude=15.0 + (10.0 if cluster else 0.0),   # a-priori; ingest ordering ONLY
                observed_at_iso=now_iso, source_ts_iso=now_iso[:19], source="insider",
                ttl_seconds=self.ttl,
                numbers={"insider_buy_value": round(parsed["buy_value"], 0),
                         "insider_cluster_count": float(n)}))
        return out


class FdaBinaryEventFeed(CatalystFeed):
    """DEFENSIVE feed (2026-07-04): upcoming FDA-adjacent BINARY events for listed sponsors, so the
    overnight-ride logic can refuse to carry a small biotech into a CRL/AdComm gap (-50..-80%
    overnight moves - memory edge-source-research-2026-07-04). Free path ONLY:
      * clinicaltrials.gov API v2 - Phase-3 studies with a primary-completion date inside
        horizon_days (no key, 24/7);
      * Federal Register FDA advisory-committee NOTICE documents (keyless JSON) - meeting dates
        parsed from the notice text.
    HONEST COVERAGE NOTE (carried into docs): PDUFA action dates are NOT in any free API - 
    coverage here = AdComm notices + trial primary-completion dates. Partial coverage accepted;
    the blackout is best-effort, not a guarantee. Do NOT buy BPIQ (do-NOT-build list).
    Events are fenced as a _DEFENSIVE_SOURCE in the pipeline: risk FLAGS only - never a watch,
    never an eval, and the flag's only powers are the entry blackout + force_eod_flat."""

    name = "fda"
    CTGOV_BASE = "https://clinicaltrials.gov/api/v2/studies"
    FEDREG_BASE = "https://www.federalregister.gov/api/v1/documents.json"
    _MEETING_DATE_RE = re.compile(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}),\s+(\d{4})")
    _MONTHS = {m: i + 1 for i, m in enumerate(
        ("January", "February", "March", "April", "May", "June", "July", "August", "September",
         "October", "November", "December"))}

    def __init__(self, resolver, *, blackout_days: float = 5.0, horizon_days: float = 21.0,
                 clinicaltrials: bool = True, federal_register: bool = True,
                 ttl_hours: float = 72.0, timeout: float = 8.0, magnitude: float = 25.0, **kw):
        super().__init__(**kw)
        self.resolver = resolver
        self.blackout_days = float(blackout_days)
        self.horizon = float(horizon_days)
        self.use_ctgov = bool(clinicaltrials)
        self.use_fedreg = bool(federal_register)
        self.ttl = float(ttl_hours) * 3600.0
        self.timeout = float(timeout)
        self.magnitude = float(magnitude)   # a-priori constant; magnitude only orders feed ingest
        self.unresolved_count = 0

    @staticmethod
    def _days_to(date_str: str, today: date) -> "float | None":
        """YYYY-MM-DD or month-precision YYYY-MM (treated as the 15th) -> days from today."""
        s = (date_str or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}", s):
            s += "-15"
        try:
            return float((date.fromisoformat(s) - today).days)
        except ValueError:
            return None

    def _ctgov_events(self, now_iso: str, today: date) -> list[CatalystEvent]:
        end = today + timedelta(days=int(self.horizon))
        q = urllib.parse.urlencode({
            "query.term": (f"AREA[PrimaryCompletionDate]RANGE[{today.isoformat()},{end.isoformat()}]"
                           " AND AREA[Phase]PHASE3"),
            "fields": ("protocolSection.identificationModule,protocolSection.statusModule,"
                       "protocolSection.sponsorCollaboratorsModule"),
            "pageSize": "100"})
        data = _http_json(f"{self.CTGOV_BASE}?{q}", timeout=self.timeout)
        out: list[CatalystEvent] = []
        for study in (data.get("studies") or []):
            ps = study.get("protocolSection") or {}
            sponsor = str(((ps.get("sponsorCollaboratorsModule") or {}).get("leadSponsor")
                           or {}).get("name") or "")
            pcd = str(((ps.get("statusModule") or {}).get("primaryCompletionDateStruct")
                       or {}).get("date") or "")
            days = self._days_to(pcd, today)
            if not sponsor or days is None or days < 0 or days > self.horizon:
                continue
            ticker = self.resolver.resolve(sponsor) if self.resolver is not None else None
            if not ticker:
                self.unresolved_count += 1
                continue
            title = str(((ps.get("identificationModule") or {}).get("briefTitle")) or "")[:80]
            out.append(CatalystEvent.build(
                symbol=ticker, kind="fda.binary_event",
                headline=f"Phase-3 primary completion in ~{days:.0f}d for {sponsor[:60]}",
                detail=f"clinicaltrials.gov {pcd}: {title}",
                magnitude=self.magnitude, observed_at_iso=now_iso,
                source_ts_iso=now_iso[:19], source="fda", ttl_seconds=self.ttl,
                numbers={"days_to_event": float(days)}))
        return out

    def _fedreg_events(self, now_iso: str, today: date) -> list[CatalystEvent]:
        q = ("conditions%5Bagencies%5D%5B%5D=food-and-drug-administration"
             "&conditions%5Btype%5D%5B%5D=NOTICE"
             "&conditions%5Bterm%5D=advisory%20committee"
             "&per_page=20&order=newest"
             "&fields%5B%5D=title&fields%5B%5D=publication_date&fields%5B%5D=dates"
             "&fields%5B%5D=html_url")
        data = _http_json(f"{self.FEDREG_BASE}?{q}", timeout=self.timeout)
        out: list[CatalystEvent] = []
        for doc in (data.get("results") or []):
            title = str(doc.get("title") or "")
            if "advisory committee" not in title.lower():
                continue
            days = None
            for m in self._MEETING_DATE_RE.finditer(f"{doc.get('dates') or ''} {title}"):
                try:
                    d = (date(int(m.group(3)), self._MONTHS[m.group(1)], int(m.group(2)))
                         - today).days
                except ValueError:
                    continue
                if 0 <= d <= self.horizon and (days is None or d < days):
                    days = d
            if days is None:
                continue
            # Company extraction from a federal notice title is unreliable free-text; the resolver
            # is exact-normalized-match-only, so throwing title fragments at it is SAFE - junk
            # resolves to None and the notice drops (correctness over recall).
            ticker = None
            if self.resolver is not None:
                for frag in re.split(r"[;:()]", title):
                    ticker = self.resolver.resolve(frag.strip())
                    if ticker:
                        break
            if not ticker:
                self.unresolved_count += 1
                continue
            out.append(CatalystEvent.build(
                symbol=ticker, kind="fda.adcomm",   # own kind: an AdComm and a trial completion on
                                                    # the same day must not dedup into one event
                headline=f"FDA advisory committee in ~{days:.0f}d: {title[:120]}",
                detail=f"Federal Register notice {doc.get('publication_date') or ''} "
                       f"{doc.get('html_url') or ''}",
                magnitude=self.magnitude, observed_at_iso=now_iso,
                source_ts_iso=now_iso[:19], source="fda", ttl_seconds=self.ttl,
                numbers={"days_to_event": float(days)}))
        return out

    def _poll_once(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:
        today = date.fromisoformat(now_iso[:10])
        out: list[CatalystEvent] = []
        errors: list[Exception] = []
        ok = 0
        for enabled, leg in ((self.use_ctgov, self._ctgov_events),
                             (self.use_fedreg, self._fedreg_events)):
            if not enabled:
                continue
            try:
                out.extend(leg(now_iso, today))
                ok += 1
            except Exception as exc:  # noqa: BLE001 - one leg down must not silence the other
                errors.append(exc)
        # Raise ONLY when NO leg succeeded (open the breaker on a total outage). A leg that
        # succeeded-but-empty (e.g. ctgov returns [] after the resolver drops every sponsor) is a
        # VALID answer - it must not let a persistent failure in the OTHER leg open the whole
        # feed's breaker. `ok == 0` distinguishes total outage from a legitimately empty result.
        if errors and ok == 0:
            raise errors[0]
        return out


class DilutionWatchFeed(CatalystFeed):
    """DEFENSIVE feed (2026-07-04): live dilution / delisting-class filings via EDGAR EFTS - 
    forms S-3 (shelf), 424B5 (takedown prospectus), EFFECT (shelf effectiveness), 25 (delisting),
    15 (deregistration). Thesis is critic-sourced and UNVERIFIED as alpha - but as a SURVIVAL veto
    it only has to be right about what the filing IS, which EDGAR guarantees. Fenced as a
    _DEFENSIVE_SOURCE: risk flag only (dilution_risk -> entry veto + force_eod_flat), never a
    watch, never an eval."""

    name = "dilution"
    BASE = EdgarMaterialEventsFeed.BASE

    def __init__(self, *, forms: tuple[str, ...] = ("S-3", "424B5", "EFFECT", "25", "15"),
                 ttl_hours: float = 72.0, timeout: float = 6.0, magnitude: float = 20.0, **kw):
        super().__init__(**kw)
        self.forms = tuple(str(f) for f in forms)
        self.ttl = float(ttl_hours) * 3600.0
        self.timeout = float(timeout)
        self.magnitude = float(magnitude)

    def _poll_once(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:
        day = now_iso[:10]
        q = urllib.parse.urlencode({"q": "", "forms": ",".join(self.forms),
                                    "startdt": day, "enddt": day})
        data = _http_json(f"{self.BASE}?{q}", timeout=self.timeout)
        out: list[CatalystEvent] = []
        for hit in (data.get("hits", {}).get("hits", []) or []):
            src = hit.get("_source") or {}
            names = src.get("display_names") or []
            m = _EDGAR_TICKER_RE.search(str(names[0])) if names else None
            if not m:
                continue                      # no listed ticker -> not tradable -> drop
            company = str(names[0]).split("(")[0].strip()
            ftype = str(src.get("file_type") or src.get("root_form")
                        or src.get("form") or "filing")
            out.append(CatalystEvent.build(
                symbol=m.group(1), kind="dilution.filing",
                headline=f"Dilution/delisting-class filing {ftype} by {company}",
                detail=f"SEC {ftype} filed {src.get('file_date', day)}; shelf/takedown/"
                       f"effectiveness/delisting class - overnight-ride risk flag",
                magnitude=self.magnitude, observed_at_iso=now_iso,
                source_ts_iso=str(src.get("file_date") or day), source="dilution",
                ttl_seconds=self.ttl, numbers={}))
        return out


class GlobeNewswirePrFeed(CatalystFeed):
    """GlobeNewswire "News about Public Companies" RSS (2026-07-04, M5) - PURE CONTEXT: press
    releases precede their matching 8-K by hours-to-days, and the feed is ticker-tagged
    (category domain .../rss/stock = "Exchange:TICKER" - verified live), so no resolver is
    needed. GNW ONLY (PRNewswire ToS bans bots - do-NOT-build). The all-releases stream is
    dominated by law-firm spam, so a category whitelist + spam blacklist gate the titles. The
    feed window is 20 items; polled at the pipeline cadence, a burst can drop items - 
    acceptable for context. Fenced in _CONTEXT_ONLY_SOURCES: never a watch, never an eval."""

    name = "gnw"
    RSS = ("https://www.globenewswire.com/RssFeed/orgclass/1/feedTitle/"
           "GlobeNewswire%20-%20News%20about%20Public%20Companies")
    _US_EXCH = ("NYSE", "NASDAQ", "AMEX")
    _DEFAULT_CATEGORIES = ("contract", "award", "acquisition", "merger", "acquire", "fda",
                           "approval", "clearance", "partnership", "collaboration", "launch")
    _SPAM = ("class action", "law firm", "investigation", "deadline", "shareholder alert",
             "lawsuit", "investors who", "reminder")

    def __init__(self, *, categories: tuple[str, ...] = (), ttl_hours: float = 24.0,
                 timeout: float = 8.0, magnitude: float = 10.0, **kw):
        super().__init__(**kw)
        self.categories = tuple(c.lower() for c in (categories or self._DEFAULT_CATEGORIES))
        self.ttl = float(ttl_hours) * 3600.0
        self.timeout = float(timeout)
        self.magnitude = float(magnitude)

    def _poll_once(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:
        import xml.etree.ElementTree as _ET
        root = _ET.fromstring(_http_text(self.RSS, timeout=self.timeout))
        out: list[CatalystEvent] = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            low = title.lower()
            if not title or any(s in low for s in self._SPAM):
                continue
            if not any(c in low for c in self.categories):
                continue
            ticker = ""
            for cat_el in item.findall("category"):
                if str(cat_el.get("domain") or "").endswith("/rss/stock"):
                    text = (cat_el.text or "").strip()
                    exch, _, tkr = text.rpartition(":")
                    if any(e in exch.upper() for e in self._US_EXCH):
                        ticker = tkr.upper()
                        break
            if not ticker:
                continue                     # non-US listing or untagged -> drop
            desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()
            out.append(CatalystEvent.build(
                symbol=ticker, kind="pr.globenewswire",
                headline=f"PR: {title}", detail=desc[:_MAX_DETAIL],
                magnitude=self.magnitude, observed_at_iso=now_iso,
                source_ts_iso=now_iso[:19], source="gnw", ttl_seconds=self.ttl,
                numbers={}))
        return out


class ApeWisdomFeed(CatalystFeed):
    """WSB attention/crowding flag (2026-07-04, M5) - PURE CONTEXT with one optional defensive
    hook: rank <= crowded_rank marks a name CROWDED (Barber JF 2022: retail herding peaks precede
    ~-4.7%/20d, ~-2.3% after the standard haircut), which is a ride-overnight CAUTION - it joins
    force_eod_flat ONLY when catalysts.apewisdom.feeds_no_ride is true. Never a look-trigger (the
    WSB long signal is DEAD post-GME - Bradley RFS 2024). Single-maintainer site with no
    timestamps: silently-stale data is tolerated as absent; any failure = no events (fail-open)."""

    name = "apewisdom"
    URL = "https://apewisdom.io/api/v1.0/filter/wallstreetbets"

    def __init__(self, *, crowded_rank: int = 10, ttl_hours: float = 2.0,
                 timeout: float = 6.0, **kw):
        super().__init__(**kw)
        self.crowded_rank = int(crowded_rank)
        self.ttl = float(ttl_hours) * 3600.0
        self.timeout = float(timeout)

    def _poll_once(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:
        data = _http_json(self.URL, timeout=self.timeout)
        out: list[CatalystEvent] = []
        for row in (data.get("results") or []):
            try:
                rank = int(row.get("rank"))
            except (TypeError, ValueError):
                continue
            if rank > self.crowded_rank:
                break                         # results are rank-ordered; only the crowded head
            sym = str(row.get("ticker") or "").upper()
            prev = row.get("rank_24h_ago")
            try:
                delta = float(prev) - rank if prev else 0.0
            except (TypeError, ValueError):
                delta = 0.0
            ev = CatalystEvent.build(
                symbol=sym, kind="crowd.wsb_rank",
                headline=f"WSB attention rank {rank} ({row.get('mentions') or 0} mentions) - "
                         f"CROWDED (herding-peak caution)",
                detail="retail-attention crowding flag; ride-overnight caution only "
                       "(long signal dead post-GME)",
                magnitude=max(1.0, 12.0 - rank), observed_at_iso=now_iso,
                source_ts_iso=now_iso[:19], source="apewisdom", ttl_seconds=self.ttl,
                numbers={"wsb_rank": float(rank), "wsb_rank_delta_24h": delta,
                         "wsb_crowded": 1.0})
            if ev is not None:
                out.append(ev)
        return out


class BorrowFeeFeed(CatalystFeed):
    """Borrow-fee spike detector over free iborrowdesk (IBKR) per-ticker snapshots. EVIDENCE-BOUND:
    high-borrow-fee names have NEGATIVE average returns (shorting-premium literature) - the
    pipeline caps these events at watch/context IN CODE; they can never immediate-eval or
    force-inject. Deterministic a-priori detector: fee jumped >= spike_fee_jump_pp vs the oldest
    snapshot in ~24h AND fee >= min_fee_pct (utilization is ANDed only when the provider reports
    it, which iborrowdesk does not). Snapshot ring state is owned by the pipeline (persisted)."""

    name = "borrow"
    BASE = "https://iborrowdesk.com/api/ticker"

    def __init__(self, symbols_fn: Callable[[], "list[str]"], snapshots: dict, *,
                 requests_per_cycle: int = 5, spike_fee_jump_pp: float = 10.0,
                 min_fee_pct: float = 20.0, min_utilization_pct: float = 85.0,
                 max_symbols: int = 20, ttl_hours: float = 24.0, timeout: float = 4.0, **kw):
        super().__init__(**kw)
        self.symbols_fn = symbols_fn           # () -> current target set (universe ∪ pool ∪ held)
        self.snapshots = snapshots             # {symbol: [{fee, util, ts}, ...]} - pipeline-persisted
        self.requests_per_cycle = int(requests_per_cycle)
        self.spike_pp = float(spike_fee_jump_pp)
        self.min_fee = float(min_fee_pct)
        self.min_util = float(min_utilization_pct)
        self.max_symbols = int(max_symbols)
        self.ttl = float(ttl_hours) * 3600.0
        self.timeout = float(timeout)
        self._rr = 0                           # round-robin cursor

    def _poll_once(self, now_iso: str, now_epoch: float) -> list[CatalystEvent]:
        symbols = [s for s in (self.symbols_fn() or []) if _SYMBOL_RE.match(s or "")][: self.max_symbols]
        if not symbols:
            return []
        out: list[CatalystEvent] = []
        n = min(self.requests_per_cycle, len(symbols))
        for i in range(n):
            sym = symbols[(self._rr + i) % len(symbols)]
            data = _http_json(f"{self.BASE}/{sym}", timeout=self.timeout)
            latest = (data.get("daily") or data.get("real_time") or [])
            row = latest[-1] if isinstance(latest, list) and latest else (
                latest if isinstance(latest, dict) else None)
            if not row:
                continue
            try:
                fee = float(row.get("fee") or row.get("indicative_fee") or 0.0)
            except (TypeError, ValueError):
                continue
            util = row.get("utilization")
            ring = self.snapshots.setdefault(sym, [])
            ring.append({"fee": fee, "util": util, "ts": now_epoch})
            del ring[:-8]                                    # keep the last ~8 snapshots
            ref = next((s for s in ring if now_epoch - s["ts"] >= 20 * 3600), ring[0])
            jump = fee - float(ref["fee"])
            util_ok = True
            if util is not None:
                try:
                    util_ok = float(util) >= self.min_util
                except (TypeError, ValueError):
                    util_ok = True
            if jump >= self.spike_pp and fee >= self.min_fee and util_ok and ref is not ring[-1]:
                out.append(CatalystEvent.build(
                    symbol=sym, kind="borrow.squeeze_setup",
                    headline=f"Borrow fee spike on {sym}: {fee:.0f}% (+{jump:.0f}pp/24h)",
                    detail="short-covering pressure setup; CONTEXT+WATCH ONLY per shorting-premium "
                           "evidence (high-fee longs lose on average) - the tape must confirm",
                    magnitude=min(100.0, fee), observed_at_iso=now_iso,
                    source_ts_iso=now_iso[:19], source="borrow", ttl_seconds=self.ttl,
                    numbers={"catalyst_borrow_fee_pct": round(fee, 1),
                             "catalyst_fee_jump_pp": round(jump, 1)}))
        self._rr = (self._rr + n) % max(1, len(symbols))
        return out
