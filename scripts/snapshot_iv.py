"""EOD ATM-IV snapshotter (2026-07-09, O1) - meant for a 15:45 ET scheduled run.

  .venv\\Scripts\\python.exe scripts\\snapshot_iv.py                 # snapshot the watchlist
  .venv\\Scripts\\python.exe scripts\\snapshot_iv.py --symbols SPY,QQQ,IWM,TSLA
  .venv\\Scripts\\python.exe scripts\\snapshot_iv.py --seed-from "C:\\path\\to\\options-project\\data\\options.db"

For each symbol: pull the nearest N (default 3) expirations' chains via Tradier greeks=true,
find the ATM strike per expiration, and record atm_iv into runtime/options_iv.db
(atlas.options.iv_archive). atm_iv = vendor ORATS mid_iv at the ATM strike (call preferred,
put fallback); if the vendor block is absent/zero, solve implied vol from the ATM mid via the
vendored BSM solver. Underlying comes from one batched get_quotes call.

FAIL-OPEN per symbol: any single name's failure logs and continues; a missing
config/tradier.local.yaml exits 0 with a clear message (never breaks a scheduled chain).
Watchlist default = SPY,QQQ,IWM. config/hunter.yaml carries no readable watch-name list (its
discovery is server-side scan-id based), so the ETFs are the standing default; --symbols
overrides. Zero order paths anywhere. --once is the only mode (kept as an explicit flag for
launcher-symmetry with the other runtime processes).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.collect.tradier_data import TOption, TradierData  # noqa: E402
from atlas.config_loader import FRAMEWORK_ROOT
from atlas.options.iv_archive import DEFAULT_DB_PATH, IVArchive, IVRow, SurfaceRow
from atlas.options.vendor.blackscholes import implied_vol
from atlas.options.vendor.models import OptionType

DEFAULT_WATCHLIST = ("SPY", "QQQ", "IWM")
MAX_EXTRA_SYMBOLS = 25       # hunt-list cap (opts-iv-surface-v1 request budget: ~115 req total)
N_EXPIRATIONS = 3
RISK_FREE = 0.04     # coarse; only the IV-from-mid fallback uses it (vendor mid_iv preferred)
MIN_T_YEARS = 0.5 / 365.0  # 0-DTE floor so the solver never sees T<=0 on expiration day


def _atm_iv_for_expiration(chain: list[TOption], underlying_px: float, dte: int) -> float:
    """ATM IV for one expiration: nearest strike; vendor IV (call then put) first, else solve
    from the ATM mid. Returns 0.0 when nothing is recoverable (caller drops the row)."""
    if not chain or underlying_px <= 0:
        return 0.0
    atm_strike = min({o.strike for o in chain if o.strike > 0},
                     key=lambda k: abs(k - underlying_px), default=0.0)
    if atm_strike <= 0:
        return 0.0
    at_strike = [o for o in chain if o.strike == atm_strike]
    calls = [o for o in at_strike if o.option_type == "call"]
    puts = [o for o in at_strike if o.option_type == "put"]
    for o in calls + puts:                     # vendor ORATS IV (mid_iv/smv_vol via parser)
        if o.iv > 0:
            return o.iv
    T = max(float(dte) / 365.0, MIN_T_YEARS)
    for o, otype in [(c, OptionType.CALL) for c in calls] + [(p, OptionType.PUT) for p in puts]:
        mid = o.mid
        if mid > 0:
            iv = implied_vol(mid, underlying_px, atm_strike, RISK_FREE, 0.0, T, otype)
            if iv is not None and iv > 0:
                return iv
    return 0.0


def snapshot_symbol(td: TradierData, symbol: str, underlying_px: float,
                    today: date, n_expirations: int = N_EXPIRATIONS,
                    ) -> tuple[list[IVRow], list[SurfaceRow]]:
    """Nearest-N-expirations rows for one symbol: (ATM-IV rows, full-chain surface rows).
    The chains were ALWAYS fetched - opts-iv-surface-v1 just stops throwing them away.
    Raises on transport errors - main() catches per symbol."""
    rows: list[IVRow] = []
    surface: list[SurfaceRow] = []
    day = today.isoformat()
    for exp in td.get_option_expirations(symbol)[:n_expirations]:
        try:
            dte = (date.fromisoformat(exp) - today).days
        except ValueError:
            continue
        if dte < 0:
            continue
        chain = td.get_option_chain(symbol, exp, greeks=True)
        iv = _atm_iv_for_expiration(chain, underlying_px, dte)
        if iv > 0:
            rows.append(IVRow(symbol=symbol, day=day, tenor_dte=dte,
                              atm_iv=iv, underlying=underlying_px, source="tradier"))
        for o in chain:
            if o.strike > 0 and o.option_type in ("call", "put"):
                surface.append(SurfaceRow(
                    symbol=symbol, day=day, expiry=exp, tenor_dte=dte, strike=o.strike,
                    opt_type=o.option_type, delta=o.delta, iv=o.iv, bid=o.bid, ask=o.ask,
                    oi=int(o.open_interest or 0), volume=int(o.volume or 0),
                    underlying=underlying_px, source="tradier"))
    return rows, surface


def _extra_symbols() -> list[str]:
    """opts-iv-surface-v1 symbol expansion: today's hunt-list names (<= MAX_EXTRA_SYMBOLS) +
    open shadow-position underlyings. Every layer fail-open to [] - the surface expansion
    must never break the ATM snapshot chain."""
    out: list[str] = []
    try:
        import json
        raw = json.loads((FRAMEWORK_ROOT / "runtime" / "hunt_list.json")
                         .read_text(encoding="utf-8-sig"))
        rows = (raw.get("candidates") or raw.get("symbols")) if isinstance(raw, dict) else raw
        for r in rows if isinstance(rows, list) else []:
            sym = (r if isinstance(r, str) else (r or {}).get("symbol") or "")
            sym = str(sym).strip().upper()
            if sym and sym not in out:
                out.append(sym)
            if len(out) >= MAX_EXTRA_SYMBOLS:
                break
    except Exception:  # noqa: BLE001
        pass
    try:
        from atlas.options.shadow import ShadowLedger
        for pos in ShadowLedger(FRAMEWORK_ROOT / "runtime").open_positions_all():
            sym = str(pos.underlying or "").upper()
            if sym and sym not in out:
                out.append(sym)
    except Exception:  # noqa: BLE001
        pass
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="EOD ATM-IV snapshotter (options shadow, O1)")
    ap.add_argument("--symbols", default=",".join(DEFAULT_WATCHLIST),
                    help="comma-separated watchlist (default %(default)s)")
    ap.add_argument("--db", default=str(DEFAULT_DB_PATH),
                    help="SQLite archive path (default %(default)s)")
    ap.add_argument("--seed-from", default=None, metavar="OPTIONS_DB",
                    help="one-shot: import IV history from the owner's options project store "
                         "(read-only) into --db, then exit")
    ap.add_argument("--expirations", type=int, default=N_EXPIRATIONS,
                    help="nearest expirations per symbol (default %(default)s)")
    ap.add_argument("--once", action="store_true", default=True,
                    help="single pass (the only mode; flag kept for launcher symmetry)")
    ap.add_argument("--no-surface", action="store_true",
                    help="skip the opts-iv-surface-v1 full-chain persist + symbol expansion")
    ap.add_argument("--force", action="store_true",
                    help="snapshot even on a non-session day (weekend/holiday chains are "
                         "Friday-stale; only for deliberate manual runs)")
    args = ap.parse_args(argv)

    archive = IVArchive(args.db)
    try:
        if args.seed_from:
            n, note = archive.seed_from_options_db(args.seed_from)
            print(f"snapshot_iv seed: {note}")
            return 0

        # Non-session guard (2026-07-11): ATLAS-IVSnapshot fires on schedule regardless of the
        # calendar; a weekend/holiday snapshot re-records Friday's stale chains under the wrong
        # day. FAIL-OPEN - a calendar error must never cost a real session's snapshot.
        if not args.force:
            try:
                from atlas.options.session_calendar import is_trading_day
                if not is_trading_day(date.today()):
                    print(f"snapshot_iv: {date.today()} is not a trading session - "
                          "skipping (--force overrides)")
                    return 0
            except Exception as exc:  # noqa: BLE001
                print(f"snapshot_iv: session check failed ({exc}) - proceeding (fail-open)")

        td = TradierData.from_local_config(FRAMEWORK_ROOT / "config" / "tradier.local.yaml")
        if td is None:
            print("snapshot_iv: config/tradier.local.yaml absent/empty - nothing to do (exit 0)")
            return 0

        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if not args.no_surface:
            # opts-iv-surface-v1 expansion: hunt-list + open positions get surface coverage
            symbols += [s for s in _extra_symbols() if s not in symbols]
        try:
            quotes = td.get_quotes(symbols)
        except Exception as exc:  # noqa: BLE001 - scheduled task must not crash-loop
            print(f"snapshot_iv: quote batch failed ({exc}) - no snapshot today (exit 0)")
            return 0

        total, surf_total, failed = 0, 0, []
        for sym in symbols:
            q = quotes.get(sym)
            if q is None or q.last <= 0:
                failed.append(f"{sym}: no quote")
                continue
            try:
                rows, surface = snapshot_symbol(td, sym, q.last, date.today(),
                                                args.expirations)
                # iv_daily FIRST and unchanged - a surface failure can never cost ATM history
                n = archive.upsert_snapshot(rows)
                total += n
                sn = 0
                if not args.no_surface:
                    try:
                        sn = archive.upsert_surface(surface)
                        surf_total += sn
                    except Exception as exc:  # noqa: BLE001 - surface is strictly additive
                        failed.append(f"{sym}: surface {exc}")
                tenors = ",".join(str(r.tenor_dte) for r in rows)
                print(f"  {sym}: {n} tenor rows (dte {tenors or '-'}) "
                      f"+ {sn} surface rows @ {q.last}")
            except Exception as exc:  # noqa: BLE001 - fail-open per symbol
                failed.append(f"{sym}: {exc}")
        td.close()

        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"snapshot_iv [{stamp}]: {total} ATM rows + {surf_total} surface rows -> {args.db}")
        for f in failed:
            print(f"  FAILED {f}")
        return 0
    finally:
        archive.close()


if __name__ == "__main__":
    raise SystemExit(main())
