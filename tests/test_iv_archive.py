"""IV-archive tests (2026-07-09, O1) - schema, upsert/idempotence, tenor-band history,
rank/percentile via the vendored math (warming-up semantics), the documented options.db seed
mapping against a fabricated source db, incompatible-schema skip, and the snapshotter's pure
ATM-IV selection helper. All on tmp_path databases - zero network."""

import sqlite3
from datetime import date, timedelta

import pytest

from atlas.collect.tradier_data import TOption
from atlas.options.iv_archive import SEED_TENOR_DTE, IVArchive, IVRow
from scripts.snapshot_iv import _atm_iv_for_expiration


def _rows(symbol, n_days, tenor, iv0=0.20, step=0.01, source="tradier"):
    start = date(2026, 1, 5)
    return [IVRow(symbol=symbol, day=(start + timedelta(days=i)).isoformat(),
                  tenor_dte=tenor, atm_iv=iv0 + i * step, underlying=100.0 + i,
                  source=source)
            for i in range(n_days)]


def test_upsert_and_history_ordering(tmp_path):
    a = IVArchive(tmp_path / "iv.db")
    assert a.upsert_snapshot(_rows("SPY", 12, tenor=7)) == 12
    hist = a.iv_history("SPY", tenor_dte=7)
    assert len(hist) == 12
    assert hist == sorted(hist)                      # oldest first (ivs increase by day)
    assert hist[0] == pytest.approx(0.20) and hist[-1] == pytest.approx(0.31)
    # Re-running the same day REPLACES (same-day correction), never duplicates.
    assert a.upsert_snapshot([IVRow("SPY", "2026-01-05", 7, 0.99)]) == 1
    hist2 = a.iv_history("SPY", tenor_dte=7)
    assert len(hist2) == 12 and hist2[0] == pytest.approx(0.99)
    # Junk rows are dropped, not stored.
    assert a.upsert_snapshot([IVRow("SPY", "2026-01-20", 7, 0.0),
                              IVRow("", "2026-01-20", 7, 0.5)]) == 0
    a.close()


def test_history_tenor_band_and_nearest_per_day(tmp_path):
    a = IVArchive(tmp_path / "iv.db")
    # Same symbol, drifting tenor across days (6,7,8) + a far tenor that must not bleed in.
    a.upsert_snapshot([IVRow("QQQ", "2026-01-05", 6, 0.30),
                       IVRow("QQQ", "2026-01-06", 7, 0.31),
                       IVRow("QQQ", "2026-01-07", 8, 0.32),
                       IVRow("QQQ", "2026-01-07", 30, 0.99),   # different tenor, same day
                       IVRow("QQQ", "2026-01-08", 30, 0.98)])  # 30-DTE-only day
    hist = a.iv_history("QQQ", tenor_dte=7)                    # default tol = max(2, 7//4) = 2
    assert hist == [pytest.approx(0.30), pytest.approx(0.31), pytest.approx(0.32)]
    # On the two-tenor day the NEAREST tenor won (0.32, not 0.99).
    assert a.iv_history("QQQ", tenor_dte=30) == [pytest.approx(0.99), pytest.approx(0.98)]
    # lookback_days caps from the newest side.
    assert a.iv_history("QQQ", tenor_dte=7, lookback_days=2) == [pytest.approx(0.31),
                                                                 pytest.approx(0.32)]
    latest = a.latest("QQQ", tenor_dte=7)
    assert latest is not None and latest.day == "2026-01-07" and latest.atm_iv == pytest.approx(0.32)
    a.close()


def test_rank_and_percentile_via_vendored_math(tmp_path):
    a = IVArchive(tmp_path / "iv.db")
    a.upsert_snapshot(_rows("IWM", 5, tenor=14))
    assert a.iv_rank("IWM", 14) is None              # warming up: <10 sessions -> None
    a.upsert_snapshot(_rows("IWM", 11, tenor=14))    # extend to 11 sessions
    rank = a.iv_rank("IWM", 14)                      # newest value == max -> 100
    assert rank == pytest.approx(100.0)
    assert a.iv_rank("IWM", 14, current_iv=0.20) == pytest.approx(0.0)
    pct = a.iv_percentile("IWM", 14, current_iv=0.251)
    assert pct == pytest.approx(6 / 11 * 100.0)      # 6 of 11 archived days below 0.251
    assert a.iv_rank("MISSING", 14) is None
    a.close()


def _make_seed_db(path, with_underlying=True):
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE iv_snapshots (symbol TEXT NOT NULL, snap_date TEXT NOT NULL, "
                "atm_iv REAL NOT NULL, PRIMARY KEY (symbol, snap_date))")
    con.executemany("INSERT INTO iv_snapshots VALUES (?,?,?)", [
        ("SPY", "2026-06-29", 0.145), ("SPY", "2026-06-30", 0.150),
        ("QQQ", "2026-06-29", 0.210), ("BAD", "2026-06-29", 0.0),   # non-positive -> dropped
    ])
    if with_underlying:
        con.execute("CREATE TABLE underlying_cache (symbol TEXT NOT NULL, snap_date TEXT NOT "
                    "NULL, price REAL NOT NULL, hv REAL, updated_at TEXT, "
                    "PRIMARY KEY (symbol, snap_date))")
        con.execute("INSERT INTO underlying_cache VALUES ('SPY','2026-06-29',620.5,0.12,'t')")
    con.commit()
    con.close()


def test_seed_from_options_db_mapping(tmp_path):
    seed = tmp_path / "options.db"
    _make_seed_db(seed)
    a = IVArchive(tmp_path / "iv.db")
    # A pre-existing OWN snapshot must survive the seed (INSERT OR IGNORE).
    a.upsert_snapshot([IVRow("SPY", "2026-06-30", SEED_TENOR_DTE, 0.555, 620.0, "tradier")])
    n, note = a.seed_from_options_db(seed)
    assert n == 2                                    # SPY 06-29 + QQQ 06-29 (BAD dropped,
    assert "seeded 2 rows" in note                   #  SPY 06-30 already owned -> ignored)
    spy = a.latest("SPY", SEED_TENOR_DTE, tenor_tolerance=0)
    assert spy.atm_iv == pytest.approx(0.555) and spy.source == "tradier"  # not clobbered
    seeded = a._conn.execute(
        "SELECT atm_iv, underlying, source FROM iv_daily WHERE symbol='SPY' AND day='2026-06-29'"
    ).fetchone()
    assert seeded == (pytest.approx(0.145), pytest.approx(620.5), "seed:options.db")
    qqq = a._conn.execute(
        "SELECT underlying FROM iv_daily WHERE symbol='QQQ' AND day='2026-06-29'").fetchone()
    assert qqq[0] == 0.0                             # no underlying_cache row -> 0.0
    # Idempotent: a second seed inserts nothing new.
    n2, _ = a.seed_from_options_db(seed)
    assert n2 == 0
    a.close()


def test_seed_incompatible_and_missing_sources(tmp_path):
    a = IVArchive(tmp_path / "iv.db")
    # Missing file: graceful skip.
    n, note = a.seed_from_options_db(tmp_path / "nope.db")
    assert n == 0 and "does not exist" in note
    # Wrong schema: describe what it holds, insert nothing, never raise.
    other = tmp_path / "other.db"
    con = sqlite3.connect(str(other))
    con.execute("CREATE TABLE trades (id INTEGER PRIMARY KEY, pnl REAL)")
    con.commit()
    con.close()
    n, note = a.seed_from_options_db(other)
    assert n == 0 and "no iv_snapshots table" in note and "trades" in note
    # Right table name, wrong columns: also a described skip.
    weird = tmp_path / "weird.db"
    con = sqlite3.connect(str(weird))
    con.execute("CREATE TABLE iv_snapshots (ticker TEXT, iv REAL)")
    con.commit()
    con.close()
    n, note = a.seed_from_options_db(weird)
    assert n == 0 and "lack symbol/snap_date/atm_iv" in note
    a.close()


# ----------------------------- snapshotter pure helper -------------------------


def _opt(otype, strike, iv=0.0, bid=0.0, ask=0.0, last=0.0):
    return TOption(symbol=f"X{otype}{strike}", option_type=otype, strike=strike, volume=10,
                   open_interest=10, bid=bid, ask=ask, last=last, iv=iv)


def test_atm_iv_selection_prefers_vendor_then_solves_from_mid():
    # Vendor IV at the ATM strike wins outright.
    chain = [_opt("call", 95.0, iv=0.5), _opt("call", 100.0, iv=0.22),
             _opt("put", 100.0, iv=0.23), _opt("call", 105.0, iv=0.6)]
    assert _atm_iv_for_expiration(chain, underlying_px=100.4, dte=7) == pytest.approx(0.22)
    # Vendor block absent -> solve from the ATM mid (round-trips a known BSM price).
    from atlas.options.vendor.blackscholes import bs_price
    from atlas.options.vendor.models import OptionType
    S, K, sigma, T = 100.0, 100.0, 0.30, 7.0 / 365.0
    px = bs_price(S, K, 0.04, 0.0, sigma, T, OptionType.CALL)
    chain2 = [_opt("call", 100.0, bid=px - 0.001, ask=px + 0.001), _opt("put", 100.0)]
    solved = _atm_iv_for_expiration(chain2, underlying_px=S, dte=7)
    assert solved == pytest.approx(sigma, abs=5e-3)
    # Nothing recoverable -> 0.0 (caller drops the row, never poisons the archive).
    assert _atm_iv_for_expiration([_opt("call", 100.0)], 100.0, 7) == 0.0
    assert _atm_iv_for_expiration([], 100.0, 7) == 0.0
