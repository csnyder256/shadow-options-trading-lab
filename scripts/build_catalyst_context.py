"""build_catalyst_context (opts-catalyst-context-writer-v1, mission reincorporate-cut-systems):
run the OPTIONS catalyst-context feeds once and write runtime/catalyst_state.json in its native
schema, so the research crew + archiver + catalyst-memory un-starve (they read this file already).

Scheduled PREMARKET (before ATLAS-Premarket 05:15 CT). Best-effort, fail-open per feed (each feed's
circuit breaker turns repeated failures into zero-cost cycles). Public data only; NO account
awareness, NO AI, NO live-loop contact. Defensive event kinds (fda/dilution/edgar_neg) are carried
as event metadata (observe-first) - they gate nothing here.

  .venv\\Scripts\\python.exe scripts\\build_catalyst_context.py --once
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from atlas.collect import catalysts as C          # noqa: E402
from atlas.collect.catalyst_book import CatalystBook  # noqa: E402
from atlas.config_loader import FRAMEWORK_ROOT     # noqa: E402

CATALYST_STATE = FRAMEWORK_ROOT / "runtime" / "catalyst_state.json"


def build_feeds(book: CatalystBook, *, borrow_symbols_fn=None) -> list:
    """The options-relevant CONTEXT feeds. Form4 + Borrow are handed the book's persisted ring
    state (they mutate it in place; the book saves it). FDA needs an EntityResolver (sponsor->ticker)
    which lands with symbol_state (WS3) - wired then; omitting it just means no FDA events yet."""
    feeds: list = [
        # scan positive (1.01 material agreement, 2.01 acquisition, 5.02 officer) AND negative
        # (1.03 bankruptcy, 3.01 delisting) items; negatives split to source="edgar_neg" (defensive tag)
        C.EdgarMaterialEventsFeed(items=("1.01", "2.01", "5.02", "1.03", "3.01")),
        C.Schedule13DFeed(),                               # activist 5%+ stakes
        C.Form4InsiderBuyFeed(book.insider_window),        # insider open-market buys (validated small-cap alpha)
        C.DilutionWatchFeed(),                             # shelf/dilution-class filings (defensive tag)
        C.GlobeNewswirePrFeed(),                           # public-company PR (precedes the 8-K; context)
        C.ApeWisdomFeed(),                                 # WSB crowding (context; long signal dead post-GME)
    ]
    if borrow_symbols_fn is not None:
        feeds.append(C.BorrowFeeFeed(borrow_symbols_fn, book.borrow_snapshots))
    return feeds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ATLAS options catalyst-context writer")
    ap.add_argument("--once", action="store_true", help="single poll then exit (the scheduled mode)")
    ap.add_argument("--state", default=str(CATALYST_STATE))
    args = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    now_iso, now_epoch = now.isoformat(), now.timestamp()
    book = CatalystBook(state_path=args.state)              # loads prior events/seen/ring state
    book.feeds = build_feeds(book)
    accepted = book.poll(now_iso, now_epoch)
    book.save()

    print(f"catalyst_context: {len(book.feeds)} feeds -> {len(accepted)} new events "
          f"({len(book.events)} live) -> {args.state}")
    for f in book.feeds:
        if getattr(f, "last_error", ""):
            print(f"  feed {f.name}: breaker_error {str(f.last_error)[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
