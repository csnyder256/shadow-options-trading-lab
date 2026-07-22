"""Options-flow feature tests (2026-07-04, M5) - pure parsers against recorded-shape fixtures
(single-element collapse), the feature computation (put-heavy caution note, volume-vs-prior-OI
heuristic), and the features-only contract (empty dict on a dead chain)."""

import pytest

from atlas.collect.tradier_data import (
    TOption,
    options_flow_features,
    parse_expirations,
    parse_option_chain,
)


def test_expirations_parse():
    payload = {"expirations": {"date": ["2026-07-10", "2026-07-17", "2026-08-21"]}}
    assert parse_expirations(payload) == ["2026-07-10", "2026-07-17", "2026-08-21"]
    # Tradier collapses single-element arrays; empty/None payloads are safe.
    assert parse_expirations({"expirations": {"date": "2026-07-10"}}) == ["2026-07-10"]
    assert parse_expirations({}) == [] and parse_expirations({"expirations": None}) == []


def test_option_chain_parse():
    payload = {"options": {"option": [
        {"symbol": "ACME260710C00050000", "option_type": "call", "strike": 50.0,
         "volume": 1200, "open_interest": 300, "bid": 1.1, "ask": 1.3},
        {"symbol": "ACME260710P00045000", "option_type": "put", "strike": 45.0,
         "volume": 200, "open_interest": 800},
        {"symbol": "", "option_type": "call", "strike": 55.0},                  # no symbol -> drop
        {"symbol": "ACME260710X00060000", "option_type": "weird", "strike": 60.0},  # bad type
    ]}}
    chain = parse_option_chain(payload)
    assert [(o.option_type, o.strike) for o in chain] == [("call", 50.0), ("put", 45.0)]
    # single-element collapse
    single = parse_option_chain({"options": {"option": {"symbol": "X260710C1", "option_type": "call",
                                                        "strike": 1.0, "volume": 5,
                                                        "open_interest": 2}}})
    assert len(single) == 1 and single[0].volume == 5.0


def _opt(t, vol, oi):
    return TOption(symbol=f"X{t}{vol}", option_type=t, strike=10.0, volume=vol, open_interest=oi)


def test_options_flow_features():
    # Put-heavy tape -> caution note; call volume measured against PRIOR-DAY OI.
    feats = options_flow_features([_opt("call", 100, 400), _opt("put", 300, 100)])
    assert feats["put_call_vol_ratio"] == pytest.approx(3.0)
    assert feats["call_vol_vs_prior_oi"] == pytest.approx(0.25)
    assert feats["options_activity_note"] == "put_heavy_caution"
    # Call-heavy and balanced notes.
    assert options_flow_features([_opt("call", 400, 100), _opt("put", 100, 50)])[
        "options_activity_note"] == "call_heavy"
    assert options_flow_features([_opt("call", 100, 100), _opt("put", 100, 100)])[
        "options_activity_note"] == "balanced"
    # FEATURES ONLY contract: zero-volume chain -> {} (nothing to say, nothing gates on it).
    assert options_flow_features([_opt("call", 0, 500), _opt("put", 0, 500)]) == {}
    assert options_flow_features([]) == {}
