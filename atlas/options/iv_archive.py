"""EOD ATM-IV archive - "the archive is the moat" (2026-07-09, O1).

SQLite store of one ATM implied-vol observation per (symbol, day, tenor) written by the 15:45
snapshotter (scripts/snapshot_iv.py). IV-rank / IV-percentile become meaningful at ~60
sessions; until then the shadow trader's vol regime comes from FRED VIX/VXN percentiles (plan
"Data stack"). Rank math is the VENDORED atlas.options.vendor.volatility functions - one
implementation, one behavior, same warming-up semantics as the owner's original project.

Schema:
    iv_daily(symbol TEXT, day TEXT, tenor_dte INTEGER, atm_iv REAL, underlying REAL,
             source TEXT, PRIMARY KEY(symbol, day, tenor_dte))
tenor_dte = calendar days to expiration on the snapshot day, so history queries match on a
tenor BAND (expirations drift day to day: Friday's "7 DTE" is Monday's "4 DTE").

SEEDING: `seed_from_options_db()` maps the owner's options project store
(C:/path/to/options-project/data/options.db - opened READ-ONLY) into iv_daily.
That schema (inspected 2026-07-09) is:
    iv_snapshots(symbol TEXT, snap_date TEXT, atm_iv REAL, PRIMARY KEY(symbol, snap_date))
    underlying_cache(symbol TEXT, snap_date TEXT, price REAL, hv REAL, updated_at TEXT, ...)
Mapping: symbol->symbol, snap_date->day, atm_iv->atm_iv, underlying <- LEFT JOIN
underlying_cache.price on (symbol, snap_date) else 0.0, source='seed:options.db', and
tenor_dte=SEED_TENOR_DTE (=30): the source project stored NO tenor - its ATM IV came from its
default 14-60 DTE scan band, so 30 is the honest canonical bucket for those legacy rows.
Seeding is best-effort and idempotent (INSERT OR IGNORE - never clobbers our own snapshots);
an incompatible schema is described and skipped, never raised.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from atlas.config_loader import FRAMEWORK_ROOT
from atlas.options.vendor import volatility as vvol

DEFAULT_DB_PATH = FRAMEWORK_ROOT / "runtime" / "options_iv.db"
SEED_TENOR_DTE = 30          # legacy tenor bucket for seeded rows (see module docstring)
DEFAULT_LOOKBACK_DAYS = 252  # ~1 trading year - the classic IV-rank window


@dataclass(frozen=True)
class IVRow:
    symbol: str
    day: str            # YYYY-MM-DD (ET session date)
    tenor_dte: int      # calendar days to expiration on `day`
    atm_iv: float       # annualized decimal (e.g. 0.155)
    underlying: float = 0.0
    source: str = ""    # "tradier" | "seed:options.db" | ...


@dataclass(frozen=True)
class SurfaceRow:
    """One full-chain strike row (opts-iv-surface-v1, 2026-07-11): the snapshotter already
    fetches complete chains and used to throw away everything but the ATM point. Persisting
    per-strike IV/OI unblocks skew/term structure and the queued pin_distance / net_gex
    covariates once history accrues (~mid-Sep). Vendor (ORATS) values - EOD archive only,
    never intraday decision greeks."""
    symbol: str
    day: str
    expiry: str         # YYYY-MM-DD
    tenor_dte: int
    strike: float
    opt_type: str       # "call" | "put"
    delta: float = 0.0
    iv: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    oi: int = 0
    volume: int = 0
    underlying: float = 0.0
    source: str = "tradier"


def _tenor_tolerance(tenor_dte: int) -> int:
    """Default matching band: short tenors need tight bands (a 0-7 DTE surface moves fast),
    long tenors drift more between snapshot days."""
    return max(2, int(tenor_dte) // 4)


class IVArchive:
    """Single-connection store; callers pass an absolute path (default runtime/options_iv.db)."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        if str(db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS iv_daily (
                symbol     TEXT NOT NULL,
                day        TEXT NOT NULL,
                tenor_dte  INTEGER NOT NULL,
                atm_iv     REAL NOT NULL,
                underlying REAL NOT NULL DEFAULT 0.0,
                source     TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (symbol, day, tenor_dte)
            )
            """
        )
        # opts-iv-surface-v1 (2026-07-11): full-chain per-strike snapshots beside - never
        # instead of - the ATM history. iv_daily's schema and write path are untouched.
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS iv_surface (
                symbol     TEXT NOT NULL,
                day        TEXT NOT NULL,
                expiry     TEXT NOT NULL,
                tenor_dte  INTEGER NOT NULL,
                strike     REAL NOT NULL,
                opt_type   TEXT NOT NULL,
                delta      REAL NOT NULL DEFAULT 0.0,
                iv         REAL NOT NULL DEFAULT 0.0,
                bid        REAL NOT NULL DEFAULT 0.0,
                ask        REAL NOT NULL DEFAULT 0.0,
                oi         INTEGER NOT NULL DEFAULT 0,
                volume     INTEGER NOT NULL DEFAULT 0,
                underlying REAL NOT NULL DEFAULT 0.0,
                source     TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (symbol, day, expiry, strike, opt_type)
            )
            """
        )
        self._conn.commit()

    # -- writes ---------------------------------------------------------------
    def upsert_snapshot(self, rows: Iterable[IVRow]) -> int:
        """INSERT OR REPLACE the given rows (same-day re-runs overwrite). Non-positive IVs are
        dropped (an unreadable chain must never poison the history). Returns rows written."""
        n = 0
        with self._conn:
            for r in rows:
                if r.atm_iv is None or r.atm_iv <= 0 or not r.symbol:
                    continue
                self._conn.execute(
                    "INSERT OR REPLACE INTO iv_daily "
                    "(symbol, day, tenor_dte, atm_iv, underlying, source) VALUES (?,?,?,?,?,?)",
                    (r.symbol.upper(), str(r.day), int(r.tenor_dte), float(r.atm_iv),
                     float(r.underlying or 0.0), str(r.source or "")))
                n += 1
        return n

    def upsert_surface(self, rows: Iterable["SurfaceRow"]) -> int:
        """INSERT OR REPLACE full-chain strike rows (same-day re-runs overwrite). Rows with a
        non-positive strike or blank opt_type are dropped. Returns rows written.
        (opts-iv-surface-v1 - a surface failure must never poison iv_daily: callers write
        iv_daily FIRST and wrap this call per-symbol fail-open.)"""
        n = 0
        with self._conn:
            for r in rows:
                if not r.symbol or r.strike <= 0 or r.opt_type not in ("call", "put"):
                    continue
                self._conn.execute(
                    "INSERT OR REPLACE INTO iv_surface (symbol, day, expiry, tenor_dte, strike,"
                    " opt_type, delta, iv, bid, ask, oi, volume, underlying, source)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (r.symbol.upper(), str(r.day), str(r.expiry), int(r.tenor_dte),
                     float(r.strike), r.opt_type, float(r.delta or 0.0), float(r.iv or 0.0),
                     float(r.bid or 0.0), float(r.ask or 0.0), int(r.oi or 0),
                     int(r.volume or 0), float(r.underlying or 0.0), str(r.source or "")))
                n += 1
        return n

    # -- reads ----------------------------------------------------------------
    def iv_history(self, symbol: str, tenor_dte: int,
                   lookback_days: int = DEFAULT_LOOKBACK_DAYS,
                   tenor_tolerance: int | None = None) -> list[float]:
        """Daily ATM-IV series for the tenor band, oldest first, one value per day (the row
        whose tenor is nearest the requested one wins when a day has several)."""
        tol = _tenor_tolerance(tenor_dte) if tenor_tolerance is None else int(tenor_tolerance)
        cur = self._conn.execute(
            "SELECT day, tenor_dte, atm_iv FROM iv_daily "
            "WHERE symbol = ? AND tenor_dte BETWEEN ? AND ? "
            "ORDER BY day DESC",
            (symbol.upper(), int(tenor_dte) - tol, int(tenor_dte) + tol))
        best: dict[str, tuple[int, float]] = {}   # day -> (tenor distance, iv)
        for day, tdte, iv in cur.fetchall():
            if len(best) >= lookback_days and day not in best:
                break                              # rows are day-descending: window filled
            dist = abs(int(tdte) - int(tenor_dte))
            if day not in best or dist < best[day][0]:
                best[day] = (dist, float(iv))
        return [best[d][1] for d in sorted(best)]  # oldest first

    def latest(self, symbol: str, tenor_dte: int,
               tenor_tolerance: int | None = None) -> IVRow | None:
        """Most recent row in the tenor band (nearest tenor on the most recent day)."""
        tol = _tenor_tolerance(tenor_dte) if tenor_tolerance is None else int(tenor_tolerance)
        cur = self._conn.execute(
            "SELECT symbol, day, tenor_dte, atm_iv, underlying, source FROM iv_daily "
            "WHERE symbol = ? AND tenor_dte BETWEEN ? AND ? "
            "ORDER BY day DESC, ABS(tenor_dte - ?) ASC LIMIT 1",
            (symbol.upper(), int(tenor_dte) - tol, int(tenor_dte) + tol, int(tenor_dte)))
        row = cur.fetchone()
        return IVRow(*row) if row else None

    def iv_rank(self, symbol: str, tenor_dte: int, current_iv: float | None = None,
                lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> float | None:
        """Vendored IV Rank (0-100) of `current_iv` (default: the newest archived value)
        against the archived history. None while warming up (<10 sessions) - callers fall
        back to the FRED VIX/VXN percentile regime input."""
        history = self.iv_history(symbol, tenor_dte, lookback_days)
        if current_iv is None:
            current_iv = history[-1] if history else None
        return vvol.iv_rank(current_iv, history)

    def iv_percentile(self, symbol: str, tenor_dte: int, current_iv: float | None = None,
                      lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> float | None:
        """Vendored IV Percentile (0-100); same warming-up semantics as iv_rank."""
        history = self.iv_history(symbol, tenor_dte, lookback_days)
        if current_iv is None:
            current_iv = history[-1] if history else None
        return vvol.iv_percentile(current_iv, history)

    def day_count(self, symbol: str, tenor_dte: int | None = None) -> int:
        """Distinct archived days for a symbol (all tenors, or one exact tenor)."""
        if tenor_dte is None:
            cur = self._conn.execute(
                "SELECT COUNT(DISTINCT day) FROM iv_daily WHERE symbol = ?", (symbol.upper(),))
        else:
            cur = self._conn.execute(
                "SELECT COUNT(DISTINCT day) FROM iv_daily WHERE symbol = ? AND tenor_dte = ?",
                (symbol.upper(), int(tenor_dte)))
        return int(cur.fetchone()[0])

    # -- seeding ----------------------------------------------------------------
    def seed_from_options_db(self, seed_path: Path | str) -> tuple[int, str]:
        """Best-effort one-shot import from the owner's options project store (READ-ONLY open).
        Returns (rows_inserted, note). Never raises; an unexpected schema is described in the
        note and skipped. Mapping documented in the module docstring."""
        p = Path(seed_path)
        if not p.exists():
            return 0, f"seed skipped: {p} does not exist"
        try:
            src = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            return 0, f"seed skipped: cannot open read-only ({exc})"
        try:
            tables = {r[0] for r in src.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "iv_snapshots" not in tables:
                return 0, (f"seed skipped: no iv_snapshots table; source holds tables "
                           f"{sorted(tables)}")
            cols = {r[1] for r in src.execute("PRAGMA table_info(iv_snapshots)")}
            if not {"symbol", "snap_date", "atm_iv"} <= cols:
                return 0, (f"seed skipped: iv_snapshots columns {sorted(cols)} lack "
                           f"symbol/snap_date/atm_iv")
            # LEFT JOIN the source's own underlying cache for the price context when present.
            if "underlying_cache" in tables and {"symbol", "snap_date", "price"} <= {
                    r[1] for r in src.execute("PRAGMA table_info(underlying_cache)")}:
                query = ("SELECT s.symbol, s.snap_date, s.atm_iv, COALESCE(u.price, 0.0) "
                         "FROM iv_snapshots s LEFT JOIN underlying_cache u "
                         "ON u.symbol = s.symbol AND u.snap_date = s.snap_date")
            else:
                query = "SELECT symbol, snap_date, atm_iv, 0.0 FROM iv_snapshots"
            inserted = 0
            with self._conn:
                for sym, day, iv, px in src.execute(query):
                    if not sym or iv is None or float(iv) <= 0:
                        continue
                    cur = self._conn.execute(
                        "INSERT OR IGNORE INTO iv_daily "
                        "(symbol, day, tenor_dte, atm_iv, underlying, source) "
                        "VALUES (?,?,?,?,?,?)",
                        (str(sym).upper(), str(day), SEED_TENOR_DTE, float(iv),
                         float(px or 0.0), "seed:options.db"))
                    inserted += cur.rowcount if cur.rowcount > 0 else 0
            return inserted, (f"seeded {inserted} rows from {p} "
                              f"(tenor_dte={SEED_TENOR_DTE} legacy bucket)")
        except sqlite3.Error as exc:
            return 0, f"seed skipped: source read failed ({exc})"
        finally:
            src.close()

    def close(self) -> None:
        self._conn.close()
