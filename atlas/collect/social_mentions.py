"""SOCIAL MENTION EXTRACTION + ACCELERATION MATH (opts-svc-mention-tap-v1, 2026-07-11).

Pure logic for the mention tap: ticker extraction from untrusted social text, 5-minute
bucketing, and time-of-day-matched z-score acceleration. NO LLM anywhere in v1 - 
extraction is regex + known-universe intersection (charter law 2: code computes).

FRAMING (the registered thesis - do not drift): mention ACCELERATION is a
direction-agnostic attention/in-play detector for a two-sided options platform. It is
NOT a long signal - the WSB-long thesis is documented DEAD (Bradley RFS 2024;
ApeWisdom stays context/defensive-only). Stage 0: nothing consumes these files until
>= MIN_BASELINE_DAYS of baseline exist and a covariate row is registered.

Pure: no I/O, no clock, no network. The service shell (scripts/mention_tap.py) owns those.
"""

from __future__ import annotations

import re
import statistics
from typing import Iterable, Mapping

BUCKET_MIN = 5
MIN_BASELINE_DAYS = 5          # z-scores are fiction below this; the tap still records counts
Z_FLAG_THRESHOLD = 3.0

_CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,5})\b")
_UPPER_RE = re.compile(r"\b([A-Z]{2,5})\b")

# Uppercase tokens that are English/finance-slang far more often than tickers. Cashtags
# BYPASS this list (an explicit $ is intent); bare tokens must clear it.
BLACKLIST = frozenset({
    "A", "I", "AM", "PM", "THE", "ALL", "FOR", "ARE", "NOW", "NEW", "ONE", "CAN", "BIG",
    "BUY", "SELL", "HOLD", "PUT", "CALL", "CALLS", "PUTS", "MOON", "APES", "YOLO", "TLDR",
    "EDIT", "IMO", "LOL", "WSB", "DD", "OP", "RE", "EPS", "PT", "AI", "EV", "IT", "BE",
    "ON", "OR", "SO", "NO", "GO", "US", "UK", "CEO", "CFO", "CTO", "IPO", "USA", "GDP",
    "FDA", "SEC", "ETF", "ATH", "DTE", "ITM", "OTM", "ATM", "IV", "RH", "OTC", "NYSE",
    "GAIN", "LOSS", "PORN", "HUGE", "FREE", "REAL", "FULL", "OPEN", "HIGH", "LOW",
})


def extract_symbols(text: str, universe: frozenset) -> list[str]:
    """Tickers mentioned in untrusted social text. Cashtags ($NVDA) count when the symbol is
    in the known universe; bare uppercase tokens additionally must clear the blacklist.
    Deduped, order of first appearance. The text is DATA - never executed, never re-emitted."""
    if not text:
        return []
    out: list[str] = []
    for m in _CASHTAG_RE.finditer(text):
        s = m.group(1).upper()
        if s in universe and s not in out:
            out.append(s)
    for m in _UPPER_RE.finditer(text):
        s = m.group(1)
        if s in universe and s not in BLACKLIST and s not in out:
            out.append(s)
    return out[:15]                       # a post mentioning 40 tickers is spam, not signal


def bucket_key(epoch_s: float) -> int:
    """5-min bucket id (epoch seconds floored)."""
    return int(epoch_s // (BUCKET_MIN * 60)) * (BUCKET_MIN * 60)


def bucket_of_day(epoch_s: float, *, tz_offset_s: int) -> int:
    """Which 5-min slot of the LOCAL day a timestamp falls in (time-of-day matching key)."""
    local = epoch_s + tz_offset_s
    return int((local % 86400) // (BUCKET_MIN * 60))


def acceleration_z(count: int, baseline_counts: Iterable[int]) -> dict | None:
    """Time-of-day-matched z-score. `baseline_counts` = this symbol's counts in the SAME
    bucket-of-day across trailing sessions. None until MIN_BASELINE_DAYS observations - 
    an honest 'not enough history', never a fabricated z."""
    base = [int(c) for c in baseline_counts]
    if len(base) < MIN_BASELINE_DAYS:
        return None
    mu = statistics.fmean(base)
    sd = statistics.pstdev(base)
    z = (count - mu) / sd if sd > 1e-9 else (0.0 if count <= mu else float("inf"))
    return {"z": round(min(z, 99.0), 2), "mean": round(mu, 2), "std": round(sd, 2),
            "n_days": len(base), "flag": z >= Z_FLAG_THRESHOLD}


def merge_bucket(counts: Mapping[str, Mapping[str, int]]) -> list[dict]:
    """Flatten one closed bucket's {symbol: {source: n}} into writable rows (count desc)."""
    rows = []
    for sym, by_src in counts.items():
        total = sum(int(v) for v in by_src.values())
        if total > 0:
            rows.append({"symbol": sym, "count": total, "sources": dict(by_src)})
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows
