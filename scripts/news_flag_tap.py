#!/usr/bin/env python3
"""C6 NEWS-FLAG TAP (opts-svc-news-flag-tap-v1) - the first consumer of news_stream.jsonl.

Tails runtime/news_stream.jsonl (byte-offset, truncation-safe), classifies each burst of
headlines, and appends validated flag rows to runtime/news_flags.jsonl - its OWN single-writer
file (the shadow's ledgers are untouchable). Stage 0 of the promotion ladder: NOTHING reads
these flags yet; consumers (news_shock reval, entry covariates, lane 5) each land under their
own registration.

Engine ladder per burst (all fail-open, never blocks anything downstream):
  tier-0  deterministic regex shocks (atlas/crew/news_flags.tier0_flags) - instant, and the
          floor when every model is down
  tier-1  groq llama-3.3-70b (benchmarked 0.7-2.6s; ~5-16% of the free tier at this cadence)
  tier-2  local GLM-4.7-Flash on llama-swap :8080 (HttpLLMClient, max_tokens=600) - the
          sovereign fallback. The tap NEVER starts/stops llama-swap (the overnight lab's rule,
          adopted verbatim): if :8080 is down, tier-2 is simply unavailable.

GPU residency (charter): during RTH this tap is the single local-AI owner - it keeps GLM warm
with an hourly keepalive echo (ttl 7200 makes residency ~free) and never touches the scouts
group. Public data only leaves the box (headlines/symbols); nothing here imports the ledgers.

Run: .venv\\Scripts\\python.exe scripts\\news_flag_tap.py [--once] [--tail-seconds 2]
Lifecycle: launched/killed by scripts/launch_options_day.ps1 (session-scoped, best-effort).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.crew import news_flags as nf                       # noqa: E402
from atlas.crew.providers import load_crew_providers          # noqa: E402
from atlas.fsutil import atomic_replace                       # noqa: E402
from atlas.models.http_client import HttpLLMClient            # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RUNTIME = REPO / "runtime"
STREAM = RUNTIME / "news_stream.jsonl"
FLAGS = RUNTIME / "news_flags.jsonl"
MACRO = RUNTIME / "news_macro.jsonl"
HEARTBEAT = RUNTIME / "news_flags_heartbeat.json"
LOCAL_BASE = "http://127.0.0.1:8080"
LOCAL_MODEL = "glm-4.7-flash"
KEEPALIVE_S = 3600.0


def log(msg: str) -> None:
    print(f"[news_flag_tap {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def append_flags(rows: list[dict]) -> int:
    if not rows:
        return 0
    with FLAGS.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({"event": "news_flag", "schema": 1, **r},
                                separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return len(rows)


def append_macro(records: list[dict]) -> int:
    """OBSERVE-FIRST macro sink (mission 20260712): ticker-less world/market headlines (Finnhub
    general, GDELT) written VERBATIM and UN-classified - they never enter the per-symbol shock
    classifier (which is meaningless for a symbol-less story). Own single-writer file; NOTHING reads
    it yet (stage 0 of the promotion ladder - a macro consumer lands under its own registration)."""
    if not records:
        return 0
    with MACRO.open("a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps({
                "event": "news_macro", "schema": 1,
                "news_id": str(r.get("id") or ""),
                "ts": str(r.get("ts") or ""),
                "source": str(r.get("source") or ""),
                "headline": str(r.get("headline") or ""),
                "summary": str(r.get("summary") or ""),
                "url": str(r.get("url") or ""),
                "fingerprint": str(r.get("fingerprint") or ""),
            }, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return len(records)


class Engines:
    """groq-primary / local-fallback classification with fail streaks for the heartbeat."""

    def __init__(self) -> None:
        provs = {}
        try:
            provs = load_crew_providers()
        except Exception:  # noqa: BLE001 - no creds file = regex-only mode
            provs = {}
        self.groq = provs.get("groq")
        # enable_thinking:false (2026-07-11): GLM is a hybrid thinker - left thinking it eats
        # the whole 600-token budget in reasoning_content and the fallback returns EMPTY.
        self.local = HttpLLMClient(base_url=LOCAL_BASE, timeout=45.0,
                                   max_retries=1, max_tokens=nf.MAX_TOKENS,
                                   extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        self.groq_fail_streak = 0
        self.local_fail_streak = 0
        self._local_last_ok = 0.0

    def classify(self, packet: str, allowed: frozenset) -> tuple[list[dict], str]:
        """Returns (validated flags, engine used). Empty list + 'none' when all tiers fail."""
        if self.groq is not None:
            reply = self.groq.complete(packet, system=nf.SYSTEM_PROMPT,
                                       timeout=20, max_tokens=nf.MAX_TOKENS)
            # success = the reply contains a decodable JSON array (possibly empty / all-routine);
            # validation may still drop rows - that is admission policy, not engine failure
            if reply is not None and nf.first_json_array(reply) is not None:
                self.groq_fail_streak = 0
                return nf.validate_flags(reply, allowed, engine="groq"), "groq"
            self.groq_fail_streak += 1
        flags = self._classify_local(packet, allowed)
        if flags is not None:
            self.local_fail_streak = 0
            return flags, "local"
        self.local_fail_streak += 1
        return [], "none"

    def _classify_local(self, packet: str, allowed: frozenset) -> list[dict] | None:
        try:
            if not self.local.health():
                return None
            raw = self.local.complete_json(
                model=LOCAL_MODEL, system=nf.SYSTEM_PROMPT, user=packet,
                schema={"type": "array"})
            self._local_last_ok = time.time()
            return nf.validate_flags(raw, allowed, engine="local")
        except Exception:  # noqa: BLE001 - tier-2 unavailable is a normal state
            return None

    def keepalive(self) -> None:
        """Hourly GLM warmth ping - only when the server is already up (never start it)."""
        try:
            if self.local.health():
                self.local.complete_json(model=LOCAL_MODEL,
                                         system="Reply with exactly {\"ok\": true}.",
                                         user="ping", schema={"type": "object"})
                self._local_last_ok = time.time()
        except Exception:  # noqa: BLE001
            pass


def read_new_records(offset: int) -> tuple[list[dict], int]:
    """Byte-offset tail of the stream; truncation/rotation resets to 0. Fail-open to []."""
    try:
        size = STREAM.stat().st_size
    except OSError:
        return [], offset
    if size < offset:
        offset = 0                      # truncated/rotated - reread from the top
    if size == offset:
        return [], offset
    try:
        with STREAM.open("rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
            new_offset = fh.tell()
    except OSError:
        return [], offset
    records: list[dict] = []
    for line in chunk.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if isinstance(rec, dict):
                records.append(rec)
        except ValueError:
            continue                     # partial trailing line lands in the next read
    # a partial last line (no trailing newline yet) would have failed json.loads; back the
    # offset up to just after the final newline so it is re-read complete next pass
    last_nl = chunk.rfind(b"\n")
    if last_nl == -1:
        return [], offset               # nothing complete yet
    return records, offset + last_nl + 1


def write_heartbeat(state: dict) -> None:
    try:
        tmp = HEARTBEAT.with_name(HEARTBEAT.name + ".tmp")
        tmp.write_text(json.dumps({"schema": 1, "ts_epoch": round(time.time(), 3), **state},
                                  indent=2, sort_keys=True), encoding="utf-8")
        atomic_replace(tmp, HEARTBEAT)
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="C6 news-flag classifier tap (stage 0; own files only)")
    ap.add_argument("--once", action="store_true", help="one tail+classify pass then exit")
    ap.add_argument("--tail-seconds", type=float, default=2.0)
    args = ap.parse_args()

    engines = Engines()
    log(f"start: groq={'yes' if engines.groq else 'NO'} "
        f"local={'up' if engines.local.health() else 'down'} stream={STREAM}")
    offset = STREAM.stat().st_size if STREAM.exists() else 0   # start at TAIL: old rows are stale
    lines_read = 0
    flags_written = 0
    macro_written = 0
    last_keepalive = 0.0

    while True:
        try:
            records, offset = read_new_records(offset)
            if records:
                lines_read += len(records)
                # SPLIT: symbol-tagged rows -> the per-symbol classifier (unchanged); ticker-less
                # macro/world rows -> their own observe-first sink, never the classifier.
                symbol_batch = [r for r in records if r.get("symbols")]
                macro_batch = [r for r in records if not r.get("symbols")]
                if macro_batch:
                    macro_written += append_macro(macro_batch)
                if symbol_batch:
                    t0 = time.time()
                    t0_flags = nf.tier0_flags(symbol_batch)
                    flags_written += append_flags(t0_flags)
                    packet, allowed = nf.build_packet(symbol_batch)
                    llm_flags, engine = engines.classify(packet, allowed) if allowed else ([], "none")
                    if llm_flags:
                        # join each symbol-level flag back to the newest record carrying it;
                        # skip pairs tier-0 already flagged this burst
                        t0_pairs = {(f["fingerprint"], f["symbol"]) for f in t0_flags}
                        by_sym: dict = {}
                        for rec in symbol_batch:
                            for s in nf.clean_symbols(rec.get("symbols")):
                                by_sym[s] = rec
                        rows = []
                        for f in llm_flags:
                            rec = by_sym.get(f["symbol"])
                            if rec is None:
                                continue
                            fp = str(rec.get("fingerprint") or "")
                            if (fp, f["symbol"]) in t0_pairs:
                                continue
                            rows.append({**f, "news_id": str(rec.get("id") or ""),
                                         "fingerprint": fp,
                                         "headline_ts": str(rec.get("ts") or ""),
                                         "latency_s": round(time.time() - t0, 2)})
                        flags_written += append_flags(rows)
                    log(f"burst: {len(symbol_batch)} sym + {len(macro_batch)} macro records -> "
                        f"{len(t0_flags)} regex + {len(llm_flags)} {engine} flags")
                elif macro_batch:
                    log(f"burst: {len(macro_batch)} macro records (no symbol records)")
            if time.time() - last_keepalive > KEEPALIVE_S:
                engines.keepalive()
                last_keepalive = time.time()
            write_heartbeat({"lines_read": lines_read, "flags_written": flags_written,
                             "macro_written": macro_written, "offset": offset,
                             "groq_fail_streak": engines.groq_fail_streak,
                             "local_fail_streak": engines.local_fail_streak,
                             "groq_configured": engines.groq is not None})
        except KeyboardInterrupt:
            log("interrupt - clean exit")
            return 0
        except Exception as exc:  # noqa: BLE001 - one bad burst never kills the tap
            log(f"tolerated error: {exc!r}")
        if args.once:
            return 0
        time.sleep(max(0.5, args.tail_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
