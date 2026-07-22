"""LIVE multi-source news tap -> runtime/news_stream.jsonl.

Historically Benzinga-only; now a thin runner that hands NewsTap a MERGED `fetch` callable
(atlas.collect.multi_news_source.build_multi_fetch) so Finnhub general/company + GDELT geopolitical
headlines join the same single-writer stream WITHOUT modifying NewsTap. `--sources benzinga`
(the default) returns fetch_news itself - byte-identical to the original tap.

  .venv\\Scripts\\python.exe scripts\\news_tap.py                                 # benzinga only (default)
  .venv\\Scripts\\python.exe scripts\\news_tap.py --sources benzinga,finnhub,gdelt # multi-source
  .venv\\Scripts\\python.exe scripts\\news_tap.py --sources benzinga,finnhub --once # single poll (testing)

Appends one JSON line per NEW headline for the in-play scanner + news-flag classifier to consume.
Macro/world headlines (Finnhub general, GDELT) carry symbols=[] and are routed by the consumer to
its own macro sink - they never enter the per-symbol classifier (observe-first). REST polling only.
Headlines are UNTRUSTED external text: never echoed or format-strung to the console - counts only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from atlas.collect.benzinga_news import NewsTap  # noqa: E402
from atlas.collect.multi_news_source import (  # noqa: E402
    DEFAULT_GDELT_QUERY,
    FINNHUB_EVERY_S,
    GDELT_EVERY_S,
    build_multi_fetch,
)


def _load_finnhub_key() -> str:
    """Finnhub api_key from config/credentials.local.yaml; '' when absent (fail-open -> that
    source just yields nothing)."""
    try:
        import yaml

        from atlas.config_loader import FRAMEWORK_ROOT
        creds = yaml.safe_load(
            (FRAMEWORK_ROOT / "config" / "credentials.local.yaml").read_text("utf-8-sig"))
        return str(((creds or {}).get("finnhub") or {}).get("api_key") or "")
    except Exception:  # noqa: BLE001 - no creds file -> that source is simply unavailable
        return ""


def _load_news_cfg() -> dict:
    """Optional `news:` block from config/system.yaml (finnhub_company_symbols, gdelt_query,
    cadences). All optional; the benzinga-only path never reads it."""
    try:
        import yaml

        from atlas.config_loader import FRAMEWORK_ROOT
        cfg = yaml.safe_load(
            (FRAMEWORK_ROOT / "config" / "system.yaml").read_text("utf-8-sig")) or {}
        news = cfg.get("news") if isinstance(cfg, dict) else None
        return news if isinstance(news, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ATLAS live multi-source news tap (REST poller)")
    ap.add_argument("--out", default=str(_REPO_ROOT / "runtime" / "news_stream.jsonl"),
                    help="JSONL output path (default: runtime/news_stream.jsonl)")
    ap.add_argument("--poll-seconds", type=float, default=30.0,
                    help="seconds between polls (default: 30)")
    ap.add_argument("--once", action="store_true",
                    help="single poll then exit (for testing)")
    ap.add_argument("--since-hours", type=float, default=1.0,
                    help="initial cursor: this many hours back from now (default: 1)")
    ap.add_argument("--heartbeat", default=None,
                    help="optional NewsTap heartbeat file written each poll (atomic)")
    ap.add_argument("--sources", default="benzinga",
                    help="comma list of: benzinga,finnhub,gdelt (default: benzinga = unchanged tap)")
    ap.add_argument("--sources-heartbeat",
                    default=str(_REPO_ROOT / "runtime" / "news_sources_heartbeat.json"),
                    help="per-source health sidecar heartbeat (multi-source only)")
    ap.add_argument("--finnhub-poll-seconds", type=float, default=FINNHUB_EVERY_S,
                    help=f"Finnhub sub-poll cadence (default: {FINNHUB_EVERY_S:.0f})")
    ap.add_argument("--gdelt-poll-seconds", type=float, default=GDELT_EVERY_S,
                    help=f"GDELT sub-poll cadence (default: {GDELT_EVERY_S:.0f}; it rate-limits hard)")
    args = ap.parse_args(argv)

    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    multi = sources != ["benzinga"]
    if multi:
        cfg = _load_news_cfg()
        fetch = build_multi_fetch(
            sources,
            api_key=_load_finnhub_key(),
            company_symbols=cfg.get("finnhub_company_symbols") or (),
            gdelt_query=cfg.get("gdelt_query") or DEFAULT_GDELT_QUERY,
            finnhub_every_s=args.finnhub_poll_seconds,
            gdelt_every_s=args.gdelt_poll_seconds,
            heartbeat_path=args.sources_heartbeat,
        )
    else:
        fetch = build_multi_fetch(sources)          # -> fetch_news, byte-identical to the old tap

    tap = NewsTap(since_hours=args.since_hours, fetch=fetch)
    print(f"news_tap: sources={sources} out={args.out} poll_seconds={args.poll_seconds} "
          f"once={args.once} since_hours={args.since_hours} cursor={tap.cursor.isoformat()} "
          f"heartbeat={args.heartbeat or '-'} "
          f"sources_hb={args.sources_heartbeat if multi else '-'}")

    if args.once:
        n = tap.poll_once(args.out, heartbeat_path=args.heartbeat)
        print(f"news_tap: --once appended {n} new item(s) -> {args.out}")
        return 0

    tap.run_forever(args.out, poll_seconds=args.poll_seconds, heartbeat_path=args.heartbeat)
    print(f"news_tap: stopped after {tap.polls} poll(s), {tap.appended_total} item(s) appended")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
