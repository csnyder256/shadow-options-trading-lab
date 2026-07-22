"""WS3 proof, part A (opts-fix-selector-halt-guard-v1): a halted / SEC-suspended underlying is a
DATA-VALIDITY reject in the selector (every row -> underlying_{state}, no pick), and passing no
state (the default) is byte-identical to today - cohort-safe."""

from __future__ import annotations

from datetime import date, datetime

from atlas.options.selector import ContractQuote, select_contract

NOW = datetime(2026, 7, 14, 9, 45)
EXP3 = date(2026, 7, 17)


def cq(strike, bid, ask, *, exp=EXP3, oi=2000.0, vol=500.0, under="XYZ", typ="call"):
    return ContractQuote(occ=f"{under}{exp:%y%m%d}{typ[0].upper()}{int(strike * 1000):08d}",
                         underlying=under, opt_type=typ, strike=strike, expiry=exp,
                         bid=bid, ask=ask, volume=vol, open_interest=oi)


def _run(rows, **kw):
    args = dict(underlying="XYZ", S=100.0, direction="call", target_move=0.02, p_thesis=0.6,
                horizon_T=1.0 / 252.0, now_et=NOW, hv20=0.30)
    args.update(kw)
    return select_contract(rows, **args)


def test_halted_underlying_rejects_all_rows_no_pick():
    rows = [cq(96, 4.30, 4.42), cq(98, 2.75, 2.85), cq(100, 1.55, 1.63)]   # normally pickable
    res = _run(rows, underlying_state="halted")
    assert res.picks == ()                                     # nothing selected on a halted name
    assert {code for _occ, code in res.rejections} == {"underlying_halted"}   # ONLY the validity code
    assert len(res.rejections) == len(rows)                    # every row rejected


def test_sec_suspended_rejects_all():
    res = _run([cq(98, 2.75, 2.85)], underlying_state="sec_suspended")
    assert res.picks == ()
    assert {c for _o, c in res.rejections} == {"underlying_sec_suspended"}


def test_none_state_is_byte_identical_baseline():
    rows = [cq(96, 4.30, 4.42), cq(98, 2.75, 2.85), cq(100, 1.55, 1.63), cq(102, 0.72, 0.78)]
    a = _run(rows)                                             # no state (default)
    b = _run(rows, underlying_state=None)                     # explicit None
    assert a.picks == b.picks and a.rejections == b.rejections
    assert bool(a.picks)                                      # the baseline still selects normally
