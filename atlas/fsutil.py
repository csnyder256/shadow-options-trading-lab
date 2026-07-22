"""Windows-safe atomic file replace.

`os.replace()` is atomic on POSIX even while a reader holds the destination open, but on Windows it
raises `PermissionError` (WinError 5 ACCESS_DENIED / 32 SHARING_VIOLATION) if ANY other process has the
destination open at that instant. In this system that happens routinely: the Guardian reads
`synthetic_stops.json` every tick, the read-only hub polls all the runtime JSONs, and the runtime dir
lives under `Downloads`, so OneDrive/Defender may scan the files too. The contention is transient - a
reader holds the handle for microseconds - so a short bounded retry rides it out.

On 2026-07-01 an unguarded `os.replace` of `synthetic_stops.json` hit WinError 5 and took the whole live
trading session down (the launcher watchdog then tore down the guardian/babysitter with it). This helper
turns that fatal crash into a sub-second stall, and re-raises only if the file is genuinely stuck (a
non-sharing error, or still contended after the full retry budget) so real problems still surface.
"""

from __future__ import annotations

import os
import time

# Windows error codes meaning "another process currently has this file open".
_SHARING_WINERRORS = {5, 32}


def atomic_replace(src, dst, *, retries: int = 20, base_delay: float = 0.015) -> None:
    """os.replace(src, dst) that retries transient Windows sharing/access violations.

    retries * (capped linear backoff) gives a worst case of well under ~2s before re-raising. On POSIX
    (no `winerror`) a PermissionError is never a transient sharing race, so it re-raises immediately.
    """
    src, dst = os.fspath(src), os.fspath(dst)
    for attempt in range(retries + 1):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in _SHARING_WINERRORS or attempt == retries:
                raise
            time.sleep(min(base_delay * (attempt + 1), 0.15))
