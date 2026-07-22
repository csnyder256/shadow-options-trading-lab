"""Contract selector (O2): gate table with reason codes, EV floors, owner-skew tiebreak,
lambda band, DTE-outside-skew flag, and that every gated row lands in rejections.
"""

from __future__ import annotations

from datetime import date, datetime

from atlas.options.selector import (ContractQuote, SelectorParams, SelectorResult,
                                    select_contract)

NOW = datetime(2026, 7, 14, 9, 45)          # Tuesday
EXP2 = date(2026, 7, 16)                    # DTE 2 - too short for a 1-day hold (1/3-of-life gate)
EXP3 = date(2026, 7, 17)                    # DTE 3 - the shortest expiry a 1-day hold fits inside
EXP0 = date(2026, 7, 14)                    # 0DTE


def cq(strike, bid, ask, *, exp=EXP3, oi=2000.0, vol=500.0, under="XYZ", typ="call") -> ContractQuote:
    return ContractQuote(occ=f"{under}{exp:%y%m%d}{typ[0].upper()}{int(strike*1000):08d}",
                         underlying=under, opt_type=typ, strike=strike, expiry=exp,
                         bid=bid, ask=ask, volume=vol, open_interest=oi)


def run(rows, **kw):
    args = dict(underlying="XYZ", S=100.0, direction="call", target_move=0.02, p_thesis=0.6,
                horizon_T=1.0 / 252.0, now_et=NOW, hv20=0.30)
    args.update(kw)
    return select_contract(rows, **args)


def _reasons(res: SelectorResult) -> dict:
    out: dict = {}
    for occ, code in res.rejections:
        out.setdefault(code, []).append(occ)
    return out


def test_happy_path_picks_high_delta_near_atm():
    rows = [cq(96, 4.30, 4.42), cq(98, 2.75, 2.85), cq(100, 1.55, 1.63), cq(102, 0.72, 0.78)]
    res = run(rows)
    assert res.picks, _reasons(res)
    best = res.picks[0]
    assert 0.40 <= abs(best.delta) <= 0.80
    assert best.ev_pct >= SelectorParams().ev_pct_min
    assert best.lam <= 90.0
    assert res.picks == tuple(sorted(res.picks, key=lambda s: s.score, reverse=True))
    # decomposition present for the ledger (+ the Wave-0.3 measure-disagreement fields:
    # ev_thesis/ev_mu0 branch EVs and the market-implied touch probability, all logged)
    assert set(best.decomposition) == {"delta_capture", "theta_paid", "spread_paid",
                                       "vega_per_pt", "ev_thesis_pct", "ev_mu0_pct",
                                       "p_mkt_touch"}


def test_gate_reason_codes_are_logged():
    rows = [
        cq(108, 0.55, 0.57),                                  # >= $0.50 premium lotto -> delta ban
        cq(100, 1.50, 1.75),                                  # spread ~15% of mid
        cq(100, 1.55, 1.63, oi=50.0),                         # thin OI
        cq(100, 1.55, 1.63, vol=0.0),                         # zero volume (floor is now
        #                                                       time-scaled - audit SELECTOR-6)
        cq(96, 4.30, 4.42, exp=date(2026, 8, 28)),            # DTE beyond scan
        cq(110, 0.10, 0.105),                                 # sub-$0.50 mid -> premium floor
    ]
    reasons = _reasons(run(rows))
    flat = set(reasons)
    assert "lotto_delta_ban" in flat or "delta_gate" in flat
    assert "spread_pct" in flat
    assert "open_interest" in flat
    assert "volume" in flat
    assert "dte_out_of_scan" in flat
    assert "premium_floor" in flat                            # audit Wave 1: min-tick toll gate


def test_premium_cap_and_lambda_band():
    # cap OFF by default (opts-tweak-remove-premium-cap-v1, owner 2026-07-10: the shadow grades
    # decision quality, never affordability): a deep-ITM $10.50 contract must NOT hit premium_cap
    res_uncapped = run([cq(90, 10.4, 10.6)])
    assert "premium_cap" not in _reasons(res_uncapped)
    # the gate stays functional when a cap IS set (the future "can we afford it" final filter)
    res = run([cq(90, 10.4, 10.6)], params=SelectorParams(premium_max_usd=350.0))
    assert "premium_cap" in _reasons(res)
    # per-DTE lambda caps (audit Wave 1.6, opts-audit-wave1-funnel-v1): 0DTE ATM lambda ~100
    # now PASSES the DTE-0 cap of 200 (the flat 90 was a de-facto index 0-1 DTE ban - 
    # measured ATM lambdas 107-271); a lambda beyond even the DTE-0 cap still rejects.
    lam_row = cq(100, 0.48, 0.52, exp=EXP0, oi=5000.0, vol=5000.0)
    res2 = run([lam_row], horizon_T=(120 / 390.0) / 252.0)
    assert "lambda_band" not in _reasons(res2)
    lam_row2 = cq(100.5, 0.50, 0.54, exp=EXP0, oi=5000.0, vol=5000.0)   # delta ~0.45, mid 0.52
    res3 = run([lam_row2], params=SelectorParams(lambda_cap_dte0=60.0),
               horizon_T=(120 / 390.0) / 252.0)
    assert "lambda_band" in _reasons(res3)                    # cap still functional per-DTE


def test_zero_dte_after_1400_and_overnight_dte_gates():
    late = datetime(2026, 7, 14, 14, 30)
    rows0 = [ContractQuote("O1", "SPY", "call", 100.0, EXP0, 1.20, 1.24,
                           volume=5000, open_interest=5000)]
    res = select_contract(rows0, underlying="SPY", S=100.0, direction="call", target_move=0.005,
                          p_thesis=0.6, horizon_T=(60 / 390.0) / 252.0, now_et=late, hv20=0.2)
    assert "zero_dte_after_1400" in _reasons(res)
    # overnight-capable theses need DTE >= 2
    res2 = run([cq(98, 2.75, 2.85, exp=date(2026, 7, 15))], may_run_overnight=True)
    assert "overnight_needs_dte2" in _reasons(res2)


def test_event_blackout_rejects_all():
    res = run([cq(98, 2.75, 2.85)], event_blackout="cpi")
    assert "event_cpi" in _reasons(res)
    assert not res.picks


def test_preferred_delta_bonus_is_a_tiebreak_not_a_ranking_override():
    p = SelectorParams(ev_pct_min=0.0, p_profit_min=0.0)
    rows = [cq(98, 2.75, 2.85), cq(101, 1.15, 1.21)]          # ~0.71 delta vs ~0.42 delta
    res = run(rows, params=p)
    assert len(res.picks) == 2
    by_strike = {x.quote.strike: x for x in res.picks}
    # the in-band (0.55-0.75) contract carries EXACTLY the +5 bonus over its EV-derived base;
    # the out-of-band one carries none - but EV% still rules the final ordering (owner's skew is a
    # tiebreak, never an override)
    for strike, expect_bonus in ((98.0, 5.0), (101.0, 0.0)):
        x = by_strike[strike]
        base = x.ev_pct - 0.5 * x.spread_pct * 100.0 - 0.3 * max(0.0, x.solved_iv / 0.30 - 1.2) * 100.0
        assert abs(x.score - base - expect_bonus) < 0.02, (strike, x.score, base)
    assert res.picks[0].ev_pct >= res.picks[1].ev_pct
    # and with a hopeless thesis the EV floor kills everything
    res2 = run([cq(98, 2.75, 2.85)], target_move=0.0, p_thesis=0.0)
    assert not res2.picks and ("ev_pct_floor" in _reasons(res2) or "ev_vs_spread" in _reasons(res2)
                               or "p_profit_floor" in _reasons(res2))


def test_hold_gate_rejects_one_day_thesis_on_dte2():
    # the research's 1/3-of-life rule in action: 1-day hold vs DTE-2 expiry = reject
    res = run([cq(98, 2.75, 2.85, exp=EXP2)])
    assert "hold_exceeds_third_of_life" in _reasons(res)


def test_zero_dte_third_of_life_carveout():
    # owner 2026-07-09 night (sweep_ledger opts-tweak-0dte-carveout-v1): a same-day 0DTE's
    # remaining life IS the rest-of-day horizon, so the 1/3-of-life gate structurally banned
    # the 0DTE skew the plan allows before 14:00. dte==0 is exempt; the 14:00 gate,
    # lambda/premium gates and exit rule (a)'s clock govern instead.
    row = ContractQuote("Z1", "SPY", "call", 100.0, EXP0, 1.20, 1.24,
                        volume=5000, open_interest=5000)
    kw = dict(underlying="SPY", S=100.0, direction="call", target_move=0.005, p_thesis=0.6,
              horizon_T=(375 / 390.0) / 252.0, now_et=NOW, hv20=0.2)   # rest of day from 09:45
    relaxed = SelectorParams(ev_pct_min=-1e9, ev_vs_spread_mult=-1e9, p_profit_min=0.0)
    res = select_contract([row], params=relaxed, **kw)
    assert "hold_exceeds_third_of_life" not in _reasons(res)
    assert res.picks and res.picks[0].dte == 0 and "zero_dte" in res.picks[0].flags
    # the carve-out is a registered knob: switched off, the old gate returns
    strict = SelectorParams(ev_pct_min=-1e9, ev_vs_spread_mult=-1e9, p_profit_min=0.0,
                            zero_dte_third_of_life_exempt=False)
    res2 = select_contract([row], params=strict, **kw)
    assert "hold_exceeds_third_of_life" in _reasons(res2)
    # DTE >= 1 contracts still face the gate unchanged
    res3 = run([cq(98, 2.75, 2.85, exp=EXP2)])
    assert "hold_exceeds_third_of_life" in _reasons(res3)


def test_crossed_and_non_standard_contract_guards():
    # crossed book (bid > ask): never price a decision off it - distinct reason code
    crossed = ContractQuote("XYZ260717C00098000", "XYZ", "call", 98.0, EXP3, 2.90, 2.75,
                            volume=500, open_interest=2000)
    assert "crossed_nbbo" in _reasons(run([crossed]))
    # adjusted root (XYZ1 = OSI digit suffix = non-standard deliverable): unpriceable x100
    adjusted = ContractQuote("XYZ1260717C00098000", "XYZ", "call", 98.0, EXP3, 2.75, 2.85,
                             volume=500, open_interest=2000)
    assert "non_standard_contract" in _reasons(run([adjusted]))
    # a digit-free root that differs from the quoted underlying symbol is FINE (BRK.B -> BRKB
    # class mappings - root-equality checks false-positive on these; digits are the OSI tell)
    brkb = ContractQuote("BRKB260717C00098000", "BRK.B", "call", 98.0, EXP3, 2.75, 2.85,
                         volume=500, open_interest=2000)
    res_b = run([brkb])
    assert "non_standard_contract" not in _reasons(res_b)
    # matching full-length OCC roots and short synthetic symbols both pass the root guard
    res = run([cq(98, 2.75, 2.85)])
    assert "non_standard_contract" not in _reasons(res) and res.picks


def test_index_oi_floor_stricter():
    rows = [ContractQuote("S1", "SPY", "call", 98.0, EXP3, 2.75, 2.85,
                          volume=500, open_interest=800)]    # fine for a single name, thin for SPY
    res = select_contract(rows, underlying="SPY", S=100.0, direction="call", target_move=0.02,
                          p_thesis=0.6, horizon_T=1 / 252.0, now_et=NOW, hv20=0.3)
    assert "open_interest" in _reasons(res)
