"""Tradier greeks extension tests (2026-07-09, O1) - the OPTIONS SHADOW chain path.

Covers: greeks sub-object parsed (ORATS delta/gamma/theta/vega/mid_iv with smv_vol fallback),
greeks absent -> zero-defaults (old shape untouched), malformed rows skipped without crashing,
the mid property contract, and the get_option_chain greeks flag ("true"/"false" on the wire,
default byte-identical to the pre-extension request).
"""

import pytest

from atlas.collect.tradier_data import TOption, TradierData, parse_option_chain

# A realistic /v1/markets/options/chains?greeks=true row shape (Tradier docs conventions:
# greeks block carries delta/gamma/theta/vega/rho/phi/bid_iv/mid_iv/ask_iv/smv_vol/updated_at).
CHAIN_WITH_GREEKS = {"options": {"option": [
    {"symbol": "SPY260710C00620000", "option_type": "call", "strike": 620.0,
     "volume": 15234, "open_interest": 41200, "bid": 3.10, "ask": 3.18, "last": 3.14,
     "expiration_date": "2026-07-10",
     "greeks": {"delta": 0.5123, "gamma": 0.0421, "theta": -0.5210, "vega": 0.2210,
                "rho": 0.011, "phi": -0.010, "bid_iv": 0.152, "mid_iv": 0.1550,
                "ask_iv": 0.158, "smv_vol": 0.156, "updated_at": "2026-07-09 14:59:08"}},
    {"symbol": "SPY260710P00620000", "option_type": "put", "strike": 620.0,
     "volume": 9800, "open_interest": 39000, "bid": 2.95, "ask": 3.05, "last": 3.00,
     "expiration_date": "2026-07-10",
     "greeks": {"delta": -0.4877, "gamma": 0.0421, "theta": -0.5104, "vega": 0.2208,
                "mid_iv": 0.1560, "smv_vol": 0.157}},
]}}


def test_parse_chain_with_greeks_present():
    chain = parse_option_chain(CHAIN_WITH_GREEKS)
    assert len(chain) == 2
    c, p = chain
    assert c.option_type == "call" and p.option_type == "put"
    assert c.delta == pytest.approx(0.5123) and p.delta == pytest.approx(-0.4877)
    assert c.gamma == pytest.approx(0.0421)
    assert c.theta == pytest.approx(-0.5210)
    assert c.vega == pytest.approx(0.2210)
    assert c.iv == pytest.approx(0.1550)          # mid_iv preferred
    assert c.last == pytest.approx(3.14)
    assert c.expiration == "2026-07-10"
    assert c.mid == pytest.approx((3.10 + 3.18) / 2)
    # Pre-existing fields still parse identically.
    assert (c.strike, c.volume, c.open_interest, c.bid, c.ask) == (620.0, 15234.0, 41200.0, 3.10, 3.18)


def test_parse_chain_iv_falls_back_to_smv_vol():
    row = {"symbol": "X260710C00010000", "option_type": "call", "strike": 10.0,
           "volume": 1, "open_interest": 2,
           "greeks": {"delta": 0.6, "smv_vol": 0.44}}   # no mid_iv
    (opt,) = parse_option_chain({"options": {"option": row}})
    assert opt.iv == pytest.approx(0.44)
    assert opt.gamma == 0.0 and opt.theta == 0.0 and opt.vega == 0.0  # absent -> defaults


def test_parse_chain_greeks_absent_and_defaults():
    # A greeks=false response: rows carry no greeks block, maybe no last/expiration either.
    payload = {"options": {"option": [
        {"symbol": "ACME260710C00050000", "option_type": "call", "strike": 50.0,
         "volume": 1200, "open_interest": 300, "bid": 1.1, "ask": 1.3},
    ]}}
    (opt,) = parse_option_chain(payload)
    assert opt.iv == 0.0 and opt.delta == 0.0 and opt.gamma == 0.0
    assert opt.theta == 0.0 and opt.vega == 0.0
    assert opt.last == 0.0 and opt.expiration == ""
    assert opt.mid == pytest.approx(1.2)           # two-sided market -> (bid+ask)/2


def test_parse_chain_malformed_rows_skipped():
    payload = {"options": {"option": [
        "garbage-string-row",                                          # not a dict
        {"symbol": "OK260710C00010000", "option_type": "call", "strike": 10.0,
         "volume": 5, "open_interest": 2, "greeks": "hourly"},         # greeks not a dict
        {"symbol": "", "option_type": "call", "strike": 1.0},          # no symbol
        {"symbol": "BAD", "option_type": "weird", "strike": 1.0},      # bad type
        {"symbol": "IVX260710P00010000", "option_type": "put", "strike": 10.0,
         "volume": 1, "open_interest": 1, "greeks": {"mid_iv": "not-a-number"}},
    ]}}
    chain = parse_option_chain(payload)
    assert [o.symbol for o in chain] == ["OK260710C00010000", "IVX260710P00010000"]
    assert chain[0].iv == 0.0 and chain[0].delta == 0.0    # junk greeks -> zero-defaults
    assert chain[1].iv == 0.0                              # non-numeric mid_iv tolerated


def test_toption_default_construction_unchanged_and_mid_contract():
    # The pre-extension construction (exactly what old call sites/tests build) still works and
    # the new fields default inert.
    opt = TOption(symbol="X", option_type="call", strike=10.0, volume=5, open_interest=2)
    assert (opt.bid, opt.ask, opt.last, opt.expiration) == (0.0, 0.0, 0.0, "")
    assert (opt.iv, opt.delta, opt.gamma, opt.theta, opt.vega) == (0.0, 0.0, 0.0, 0.0, 0.0)
    assert opt.mid == 0.0                                  # no market, no last -> 0
    # One-sided market -> falls back to last, never a half-spread fabrication.
    one_sided = TOption(symbol="X", option_type="call", strike=10.0, volume=5,
                        open_interest=2, bid=1.0, ask=0.0, last=1.05)
    assert one_sided.mid == pytest.approx(1.05)


def test_get_option_chain_sends_greeks_flag(monkeypatch):
    td = TradierData("test-token")
    seen = []

    def fake_request(method, path, params, retries=2):
        seen.append((method, path, dict(params)))
        return {"options": {"option": []}}

    monkeypatch.setattr(td, "_request", fake_request)
    td.get_option_chain("spy", "2026-07-10")               # default: byte-identical old request
    td.get_option_chain("spy", "2026-07-10", greeks=True)
    td.close()
    assert seen[0] == ("GET", "/v1/markets/options/chains",
                       {"symbol": "SPY", "expiration": "2026-07-10", "greeks": "false"})
    assert seen[1][2]["greeks"] == "true"
