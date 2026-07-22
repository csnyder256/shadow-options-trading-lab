"""Token-bucket rate gate for the shared Robinhood MCP connection.

Robinhood's rate limit is per-USER and shared across EVERY MCP tool call (measured: ~15 rapid calls
then `ResourceExhausted: Rate limit exceeded`). So a frequent scan poll must never spend the budget an
order needs. This gate enforces that:
  * HIGH priority (place/cancel order, order-time quote) is NEVER blocked - it proceeds immediately
    (consuming a token if one is free, but never waiting). An entry/stop must always be able to fire.
  * NORMAL priority (positions/portfolio/orders reads) acquires a token, briefly blocking if the bucket
    is dry.
  * LOW priority (run_scan polling) acquires a token with a short timeout and is dropped (throttled) if
    the budget is tight - the poller simply skips and retries next cadence.

Clock + sleep are injectable so the bucket is unit-testable without real time.
"""

from __future__ import annotations

import threading
import time

# Order placement / cancellation and the quote that immediately precedes a send must never be throttled.
_HIGH_PRIORITY_TOOLS = {"place_equity_order", "cancel_equity_order", "get_equity_quotes"}
# Discovery polling yields to everything else.
_LOW_PRIORITY_TOOLS = {"run_scan"}


def classify_priority(tool: str) -> str:
    if tool in _HIGH_PRIORITY_TOOLS:
        return "high"
    if tool in _LOW_PRIORITY_TOOLS:
        return "low"
    return "normal"


class RHThrottled(RuntimeError):
    """A low-priority call was dropped by the rate gate to protect the order budget."""


class RateGate:
    def __init__(self, capacity: float = 8.0, refill_per_sec: float = 2.0, *,
                 clock=time.monotonic):
        self.capacity = float(capacity)
        self.refill = float(refill_per_sec)
        self._clock = clock
        self._tokens = float(capacity)
        self._ts = clock()
        self._lock = threading.Lock()

    def _replenish(self) -> None:
        now = self._clock()
        self._tokens = min(self.capacity, self._tokens + (now - self._ts) * self.refill)
        self._ts = now

    def tokens(self) -> float:
        with self._lock:
            self._replenish()
            return self._tokens

    def acquire(self, *, priority: str = "normal", timeout: float = 20.0, sleep=time.sleep) -> bool:
        """Acquire one token. HIGH never blocks (returns True immediately, consuming a token only if free).
        NORMAL/LOW block up to `timeout`; returns False if no token came free in time."""
        if priority == "high":
            with self._lock:
                self._replenish()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
            return True
        deadline = self._clock() + timeout
        while True:
            with self._lock:
                self._replenish()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                need = (1.0 - self._tokens) / self.refill if self.refill > 0 else timeout
            remaining = deadline - self._clock()
            if remaining <= 0:
                return False
            sleep(min(need, remaining, 0.5))
