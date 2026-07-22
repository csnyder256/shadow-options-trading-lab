"""Data-feed world-size model for ATLAS.

Answers: given Alpaca + Finnhub rate limits, how many symbols' bars+quotes can the
PICKER refresh per cycle, and at what world size does the system become DATA-bound
rather than compute-bound (the auditor LLM)?

All rate-limit numbers are sourced and dated in the research notes (2026-06). Treat the
HTTP request budget as the binding constraint, NOT raw symbol count: Alpaca multi-symbol
bars/snapshot endpoints pack many symbols per HTTP call but PAGINATE at 10,000 data
points per page (total across symbols, not per symbol).

Run:  python tools/datafeed_world_size.py
"""
from __future__ import annotations

from dataclasses import dataclass


# ---- sourced constants (Alpaca market-data, 2026-06) -----------------------
ALPACA_RPM_BASIC = 200        # requests/min, Basic (free) plan
ALPACA_RPM_PLUS = 10_000      # requests/min, Algo Trader Plus ($99/mo) per official docs
PAGE_DATA_POINTS = 10_000     # max data points returned per bars page (total, not per symbol)

# ---- sourced constants (Finnhub, 2026-06) ----------------------------------
FINNHUB_RPM_FREE = 60         # calls/min, free tier
FINNHUB_RPM_PAID = 300        # calls/min, premium tier (~$60-100/mo)

# ---- ATLAS measured ground truth -------------------------------------------
PICKER_MS_PER_SYMBOL = 0.9    # signal engine, effectively free
AUDITOR_S = 43.0             # mid of 36-50s; the dominant bottleneck, sequential
ANALYST_S = 19.0            # mid of 18-20s, batched ~1.40x
ENTER_RATE = 0.34           # analyst enter-rate -> fraction that hits the auditor
PASS_RATE = 0.10            # picker pass-rate at min_quality=55


@dataclass
class FeedPlan:
    name: str
    alpaca_rpm: int
    finnhub_rpm: int
    bars_lookback_rows: int = 250   # daily bars needed per symbol for 200-SMA (~1yr)


def bars_requests_for(n_symbols: int, rows_per_symbol: int) -> int:
    """Multi-symbol daily-bars refresh: ALL symbols go in ONE HTTP call body, but the
    response paginates at 10k data points TOTAL. So #requests = ceil(total_rows / 10k)."""
    total_rows = n_symbols * rows_per_symbol
    return max(1, -(-total_rows // PAGE_DATA_POINTS))   # ceil


def snapshot_requests_for(n_symbols: int) -> int:
    """A snapshot returns ~6 data points/symbol (trade/quote/min-bar/day-bar/prev-day).
    Pagination at 10k points -> ~1666 symbols/page. One page covers a few thousand names."""
    points = n_symbols * 6
    return max(1, -(-points // PAGE_DATA_POINTS))


def max_world_data_bound(plan: FeedPlan, cycle_seconds: float) -> dict:
    """Largest universe whose bars+quotes refresh fits inside one cycle's request budget.

    Bars need refreshing only ~once/day (daily strategy) -> amortized cheap. Quotes/snapshots
    are the per-cycle cost. We model the WORST case: full bars + full snapshot every cycle,
    then also the realistic case (snapshot-only per cycle, bars daily).
    """
    budget = plan.alpaca_rpm * (cycle_seconds / 60.0)   # requests available this cycle

    # Worst case: refresh full daily bars + snapshot every cycle.
    def fits_worst(n):
        return bars_requests_for(n, plan.bars_lookback_rows) + snapshot_requests_for(n) <= budget

    # Realistic: bars cached daily, only a snapshot sweep per cycle.
    def fits_real(n):
        return snapshot_requests_for(n) <= budget

    def bisect(fits):
        lo, hi = 1, 5_000_000
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if fits(mid):
                lo = mid
            else:
                hi = mid - 1
        return lo

    return {
        "budget_requests": budget,
        "world_worstcase_bars+snap": bisect(fits_worst),
        "world_realistic_snap_only": bisect(fits_real),
    }


def compute_bound_world(cycle_seconds: float) -> dict:
    """How many candidates the LLM stack can clear per cycle, and the world that feeds it.

    Per cycle the models clear: analyst on all candidates (batched), auditor on enters
    (sequential). Solve for #candidates C such that the LLM phase ~= cycle_seconds, then
    back out world = C / PASS_RATE.
    """
    # llm_seconds(C) = swap + C*ANALYST/1.40 + C*ENTER_RATE*AUDITOR
    per_candidate = ANALYST_S / 1.40 + ENTER_RATE * AUDITOR_S
    swap = 10.0
    usable = max(0.0, cycle_seconds - swap)
    candidates = usable / per_candidate
    world = candidates / PASS_RATE
    return {
        "per_candidate_s": per_candidate,
        "candidates_per_cycle": candidates,
        "world_compute_bound": world,
    }


def main() -> None:
    plans = [
        FeedPlan("Alpaca Basic (free IEX) + Finnhub free", ALPACA_RPM_BASIC, FINNHUB_RPM_FREE),
        FeedPlan("Alpaca Algo Trader Plus + Finnhub paid", ALPACA_RPM_PLUS, FINNHUB_RPM_PAID),
    ]
    for cycle in (30.0, 60.0, 120.0):
        print(f"\n===== CYCLE = {cycle:.0f}s =====")
        cb = compute_bound_world(cycle)
        print(f"  COMPUTE-bound world (auditor-limited): "
              f"~{cb['world_compute_bound']:.0f} names "
              f"({cb['candidates_per_cycle']:.1f} candidates/cycle, "
              f"{cb['per_candidate_s']:.1f}s each)")
        for plan in plans:
            d = max_world_data_bound(plan, cycle)
            print(f"  [{plan.name}]")
            print(f"      request budget/cycle: {d['budget_requests']:.0f}")
            print(f"      DATA-bound world (bars+snapshot every cycle): "
                  f"~{d['world_worstcase_bars+snap']:,}")
            print(f"      DATA-bound world (snapshot/cycle, bars daily): "
                  f"~{d['world_realistic_snap_only']:,}")
            # Finnhub gates news on candidates only:
            cands = cb["candidates_per_cycle"]
            news_room = plan.finnhub_rpm * (cycle / 60.0)
            print(f"      Finnhub news budget/cycle: {news_room:.0f} calls "
                  f"vs ~{cands:.0f} candidates -> "
                  f"{'OK' if news_room >= cands else 'TIGHT'}")


if __name__ == "__main__":
    main()
