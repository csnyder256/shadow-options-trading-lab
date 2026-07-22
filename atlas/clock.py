"""Session / blackout clock (docs/02 §2.2, system.yaml: loop.timezone).

Deterministic 'now' handling for an equities session (NYSE 09:30-16:00 ET, weekdays). The MVP
has no holiday calendar; `now` is always passed in explicitly so cycles are reproducible.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)


class Clock:
    def __init__(self, tz: ZoneInfo = NY):
        self.tz = tz

    def to_local(self, now: datetime) -> datetime:
        return now.astimezone(self.tz)

    def is_trading_day(self, now: datetime) -> bool:
        return self.to_local(now).weekday() < 5  # Mon-Fri (no holiday calendar in MVP)

    def is_in_session(self, now: datetime) -> bool:
        local = self.to_local(now)
        return self.is_trading_day(now) and SESSION_OPEN <= local.time() <= SESSION_CLOSE

    def minutes_since_open(self, now: datetime) -> float | None:
        if not self.is_in_session(now):
            return None
        local = self.to_local(now)
        open_dt = local.replace(hour=SESSION_OPEN.hour, minute=SESSION_OPEN.minute,
                                second=0, microsecond=0)
        return (local - open_dt).total_seconds() / 60.0

    def minutes_to_close(self, now: datetime) -> float | None:
        """Minutes until the 16:00 ET close, or None when out of session. Mirrors minutes_since_open and
        drives the close-side entry blackout so a NEW position is never opened right before the Guardian's
        end-of-day flatten window (2026-07-01: bought FRT 15:48 ET, EOD-flatted 15:50 -> -$0.01 round trip)."""
        if not self.is_in_session(now):
            return None
        local = self.to_local(now)
        close_dt = local.replace(hour=SESSION_CLOSE.hour, minute=SESSION_CLOSE.minute,
                                 second=0, microsecond=0)
        return (close_dt - local).total_seconds() / 60.0

    def week_key(self, now: datetime) -> str:
        """ISO year-week (e.g. '2026-W26') in market-local time - the weekly-drawdown bucket."""
        iso = self.to_local(now).isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
