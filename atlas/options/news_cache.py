"""NewsFlagsCache - O(1) reader of runtime/news_flags.jsonl for options entry COVARIATES (WS4) and
the news-shock mark-ACCELERATOR (WS5). Mission reincorporate-cut-systems.

Async enrichment law: refreshed by a single byte-offset TAIL read (reuse of news_flag_tap's
read_new_records idiom) once per reval sweep / at entry - NEVER per tick - and every query is an
O(1) lookup over a bounded per-symbol ring. It NEVER contacts the exit engine: the WS5 accel only
tells the runner WHEN to re-mark (last_mark_ts=0.0 + journal), never WHAT to decide.

news_flags.jsonl row (scripts/news_flag_tap.append_flags): {"event":"news_flag","schema":1,
"symbol","shock"(bool),"kind","direction"(up|down|unclear),"materiality"(float),"engine","news_id",
"fingerprint","headline_ts"(ET-aware ISO8601), and on LLM rows also "latency_s"}. Two producers
(tier-0 regex + groq/local) differ slightly in keys - both handled by .get().

ALL thresholds are MODULE constants (NOT the runner's self.cfg) so they can never move config_hash
/ split the entry cohort - the load-bearing cohort rule for this batch.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path

from atlas.config_loader import FRAMEWORK_ROOT

FLAGS_PATH = FRAMEWORK_ROOT / "runtime" / "news_flags.jsonl"
NEWS_SHOCK_WINDOW_MIN = 15.0        # news_shock_15m covariate window
NEWS_WINDOW_MIN = 60.0             # news_count_60m / kind / direction / age lookback
NEWS_ACCEL_WINDOW_MIN = 10.0      # WS5 mark-accel freshness window
NEWS_ACCEL_MIN_MATERIALITY = 0.7  # WS5 mark-accel materiality floor
_MAX_PER_SYMBOL = 64              # bounded ring per underlying


def _ts_epoch(iso) -> float:
    try:
        return datetime.fromisoformat(str(iso)).timestamp()
    except (ValueError, TypeError):
        return 0.0


class NewsFlagsCache:
    def __init__(self, path=FLAGS_PATH):
        self._path = Path(path)
        self._offset = 0
        self._by_sym: dict[str, deque] = {}

    def update(self) -> None:
        """Incremental byte-offset tail read; index new news_flag rows by symbol. Fail-open."""
        try:
            size = self._path.stat().st_size
        except OSError:
            return
        if size < self._offset:               # truncated / rotated
            self._offset = 0
            self._by_sym.clear()
        if size == self._offset:
            return
        try:
            with self._path.open("rb") as fh:
                fh.seek(self._offset)
                chunk = fh.read()
        except OSError:
            return
        last_nl = chunk.rfind(b"\n")
        if last_nl == -1:                      # no complete line yet
            return
        for line in chunk[:last_nl].decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("event") != "news_flag":
                continue
            sym = str(r.get("symbol") or "").upper()
            if not sym:
                continue
            r["_ts"] = _ts_epoch(r.get("headline_ts"))
            self._by_sym.setdefault(sym, deque(maxlen=_MAX_PER_SYMBOL)).append(r)
        self._offset += last_nl + 1

    def _recent(self, sym: str, now: float, window_min: float) -> list[dict]:
        cutoff = now - window_min * 60.0
        return [r for r in self._by_sym.get((sym or "").upper(), ()) if r.get("_ts", 0.0) >= cutoff]

    # ---- WS4 entry covariates (graded at N, gate nothing) --------------------
    def news_shock_15m(self, sym: str, now: float) -> bool:
        return any(r.get("shock") for r in self._recent(sym, now, NEWS_SHOCK_WINDOW_MIN))

    def news_count_60m(self, sym: str, now: float) -> int:
        return len(self._recent(sym, now, NEWS_WINDOW_MIN))

    def news_kind_recent(self, sym: str, now: float):
        rows = self._recent(sym, now, NEWS_WINDOW_MIN)
        return max(rows, key=lambda r: r.get("_ts", 0.0)).get("kind") if rows else None

    def news_direction_align(self, sym: str, direction: str, now: float):
        """+1 if the newest flag's direction agrees with the position (call->up / put->down),
        -1 if it opposes, 0 if unclear, None if no recent flag."""
        rows = self._recent(sym, now, NEWS_WINDOW_MIN)
        if not rows:
            return None
        d = str(max(rows, key=lambda r: r.get("_ts", 0.0)).get("direction") or "unclear")
        if d == "unclear":
            return 0
        want = "up" if direction == "call" else "down"
        return 1 if d == want else -1

    def headline_age_min(self, sym: str, now: float):
        rows = self._recent(sym, now, NEWS_WINDOW_MIN)
        if not rows:
            return None
        newest = max((r.get("_ts", 0.0) for r in rows), default=0.0)
        return round(max(0.0, now - newest) / 60.0, 1) if newest > 0 else None

    # ---- WS5 mark-accel (observability only; the sole exit-ladder contact) ----
    def fresh_shock(self, sym: str, now: float):
        """The newest high-materiality shock within the accel window, else None. Returns the row
        (carrying fingerprint) so the caller can dedupe + journal - it NEVER touches exit logic."""
        best = None
        for r in self._recent(sym, now, NEWS_ACCEL_WINDOW_MIN):
            try:
                mat = float(r.get("materiality") or 0.0)
            except (TypeError, ValueError):
                mat = 0.0
            if r.get("shock") and mat >= NEWS_ACCEL_MIN_MATERIALITY:
                if best is None or r.get("_ts", 0.0) >= best.get("_ts", 0.0):
                    best = r
        return best
