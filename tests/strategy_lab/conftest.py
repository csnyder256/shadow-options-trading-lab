"""Shared fixture builders for the strategy-lab suite - combos built via the REAL production
builders (never hand-written dicts) so schema drift breaks tests (the main suite's idiom).
NO network, NO runtime/ writes: everything under tmp_path."""

from __future__ import annotations

from datetime import date

import pytest

from atlas.strategy_lab.carisk import grading_block
from atlas.strategy_lab.model import (LegSpec, build_combo_entry_record, combo_from_entry,
                                      combo_net_open, leg_open_fills)

EXP = date(2026, 8, 31)


def leg(occ, opt_type, strike, side, qty=1, bid=1.0, ask=1.2, delta=0.5, theta_day=-0.05,
        expiry=EXP, underlying="SPY", iv=0.2, gamma=0.01, vega=0.4):
    """One leg input dict in the exact shape scan()/the runner produce."""
    return {"occ": occ, "underlying": underlying, "opt_type": opt_type, "strike": strike,
            "expiry": str(expiry), "side": side, "qty": qty,
            "nbbo": {"bid": bid, "ask": ask},
            "fills": leg_open_fills(side, bid, ask),
            "iv": iv, "delta": delta, "gamma": gamma, "vega": vega, "theta_day": theta_day}


def specs_and_mids(legs):
    out = []
    for l in legs:
        spec = LegSpec(occ=l["occ"], underlying=l["underlying"], opt_type=l["opt_type"],
                       strike=l["strike"], expiry=date.fromisoformat(l["expiry"]),
                       side=l["side"], qty=l["qty"])
        mid = (l["nbbo"]["bid"] + l["nbbo"]["ask"]) / 2.0
        out.append((spec, mid))
    return out


def make_entry(legs, *, strategy_id="test_strat", declared_basis="debit", S=630.0,
               position_id=None, day="2026-07-20", minute=600, ts=1_784_000_000.0,
               kind="test_combo", cfg_hash="abcdef123456"):
    pairs = [(s, l["fills"]) for (s, _), l in zip(specs_and_mids(legs), legs)]
    net = combo_net_open(pairs)
    grading = grading_block(legs_with_mid=specs_and_mids(legs),
                            net_open_worst=net["worst"], S=S, declared_basis=declared_basis)
    return build_combo_entry_record(
        ts=ts, day=day, entry_minute=minute,
        position_id=position_id or f"{strategy_id}:SPY:{day}:{minute}:0",
        strategy_id=strategy_id, strategy_config_hash=cfg_hash, kind=kind,
        legs=legs, S=S, grading=grading,
        signal={"note": "fixture"}, greeks_net={"delta_dollars": 0.0, "theta_day": 0.0},
        risk_flags=(["basis_mismatch"] if grading["basis_mismatch"] else []))


@pytest.fixture
def combo_factory():
    def make(legs, **kw):
        rec = make_entry(legs, **kw)
        pos = combo_from_entry(rec)
        assert pos is not None, "fixture entry record failed to rebuild"
        return rec, pos
    return make
