"""iv_surface collector (opts-iv-surface-v1): the surface table is strictly ADDITIVE - 
iv_daily's schema/write path byte-identical; surface rows validated; upsert idempotent."""

from __future__ import annotations

from atlas.options.iv_archive import IVArchive, IVRow, SurfaceRow


def _row(strike=560.0, opt="call", **kw):
    base = dict(symbol="SPY", day="2026-07-11", expiry="2026-07-13", tenor_dte=2,
                strike=strike, opt_type=opt, delta=0.5, iv=0.18, bid=1.0, ask=1.1,
                oi=100, volume=10, underlying=560.0)
    base.update(kw)
    return SurfaceRow(**base)


def test_surface_upsert_and_idempotence():
    a = IVArchive(":memory:")
    rows = [_row(), _row(opt="put"), _row(strike=565.0)]
    assert a.upsert_surface(rows) == 3
    assert a.upsert_surface(rows) == 3                    # INSERT OR REPLACE - no dupes
    n = a._conn.execute("SELECT COUNT(*) FROM iv_surface").fetchone()[0]
    assert n == 3


def test_surface_drops_garbage_rows():
    a = IVArchive(":memory:")
    assert a.upsert_surface([_row(strike=0.0), _row(opt="straddle"),
                             SurfaceRow(symbol="", day="d", expiry="e", tenor_dte=1,
                                        strike=5.0, opt_type="call")]) == 0


def test_iv_daily_write_path_untouched_by_surface():
    """The ATM history must be writable exactly as before, with the surface table present."""
    a = IVArchive(":memory:")
    assert a.upsert_snapshot([IVRow(symbol="SPY", day="2026-07-11", tenor_dte=2,
                                    atm_iv=0.18, underlying=560.0, source="tradier")]) == 1
    cols = [r[1] for r in a._conn.execute("PRAGMA table_info(iv_daily)").fetchall()]
    assert cols == ["symbol", "day", "tenor_dte", "atm_iv", "underlying", "source"]
    assert a.iv_history("SPY", 2) == [0.18]


# ------------------------------------------------- non-session guard (2026-07-11 audit)
# Born of the 07-11 Saturday catch-up storm: ATLAS-IVSnapshot fired on a weekend and would
# have archived Friday-stale chains under Saturday's date. The guard self-skips; --force
# is the deliberate-manual-run escape.

def test_snapshot_main_skips_non_session_day(monkeypatch, capsys):
    from atlas.options import session_calendar
    from scripts import snapshot_iv

    monkeypatch.setattr(session_calendar, "is_trading_day", lambda d, **k: False)
    rc = snapshot_iv.main(["--db", ":memory:"])
    assert rc == 0
    assert "not a trading session" in capsys.readouterr().out


def test_snapshot_force_overrides_session_guard(monkeypatch, tmp_path, capsys):
    from atlas.options import session_calendar
    from scripts import snapshot_iv

    monkeypatch.setattr(session_calendar, "is_trading_day", lambda d, **k: False)
    # steer the config lookup at an empty dir: proves we got PAST the guard and reached
    # the (network-free) missing-token exit, not the guard's skip
    monkeypatch.setattr(snapshot_iv, "FRAMEWORK_ROOT", tmp_path)
    rc = snapshot_iv.main(["--force", "--db", str(tmp_path / "iv.db")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tradier.local.yaml absent" in out
    assert "not a trading session" not in out
