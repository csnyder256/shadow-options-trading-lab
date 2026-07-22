"""Multi-leg combo model + fill math + record builders (pure: dict in / dict out, no IO).

Generalizes atlas/options/shadow.py's three-fill convention to N-leg structures by applying
the SAME per-leg fill functions on the correct side of every leg:

    opening a LONG leg  = buy  -> oshadow.entry_fills  (worst = ask)
    opening a SHORT leg = sell -> oshadow.exit_fills   (worst = bid)
    closing a LONG leg  = sell -> oshadow.exit_fills   (worst = bid)
    closing a SHORT leg = buy  -> oshadow.entry_fills  (worst = ask)

Sign conventions (used EVERYWHERE downstream - grader, verdicts, tests):
    side: +1 long, -1 short.
    net open fill per ledger  = sum(side*qty*open_fill)   -> POSITIVE = net debit paid.
    leg P&L = side*qty*(close_fill - open_fill)*100*units.
    Per ledger the identity  net P&L: worst <= base <= optimistic  holds because it holds
    leg-wise on both sides (buy high/sell low is worst for longs AND for closing shorts).

The grading denominator is FROZEN AT ENTRY by expiry-payoff analysis (payoff_analysis) +
the Reg-T proxy in carisk.py, stamped into the entry record, and re-derived by the grader
as a falsification gate - denominator drift is evidence corruption, never silently fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from atlas.options.shadow import entry_fills as _buy_fills
from atlas.options.shadow import exit_fills as _sell_fills

SCHEMA = 1
LEDGER_NAMES = ("worst", "base", "optimistic")


# --------------------------------------------------------------------------- legs
@dataclass(frozen=True)
class LegSpec:
    """One leg of a combo. `side` +1 long / -1 short; `qty` per combo unit (ratio spreads)."""
    occ: str
    underlying: str
    opt_type: str            # "call" | "put"
    strike: float
    expiry: date
    side: int                # +1 long, -1 short
    qty: int = 1

    def __post_init__(self):
        if self.side not in (+1, -1):
            raise ValueError(f"leg side must be +1/-1, got {self.side}")
        if self.qty < 1:
            raise ValueError(f"leg qty must be >= 1, got {self.qty}")
        if self.opt_type not in ("call", "put"):
            raise ValueError(f"opt_type must be call|put, got {self.opt_type}")


def leg_open_fills(side: int, bid: float, ask: float) -> dict:
    """Per-leg opening fills on the correct side. Long buys (worst=ask), short sells (worst=bid)."""
    return _buy_fills(bid, ask) if side > 0 else _sell_fills(bid, ask)


def leg_close_fills(side: int, bid: float, ask: float) -> dict:
    """Per-leg closing fills. Long sells to close (worst=bid), short buys to close (worst=ask)."""
    return _sell_fills(bid, ask) if side > 0 else _buy_fills(bid, ask)


def combo_net_open(legs: list[tuple[LegSpec, dict]]) -> dict:
    """Signed net opening fill per ledger from [(leg, open_fills_dict)]. Positive = debit paid
    (per combo unit, per share - multiply by 100 for USD)."""
    out = {}
    for name in LEDGER_NAMES:
        out[name] = round(sum(leg.side * leg.qty * fills[name] for leg, fills in legs), 4)
    return out


def combo_net_close(legs: list[tuple[LegSpec, dict]]) -> dict:
    """Signed net closing fill per ledger from [(leg, close_fills_dict)]. Same sign convention:
    P&L per ledger = (net_close - net_open) * 100 * units."""
    out = {}
    for name in LEDGER_NAMES:
        out[name] = round(sum(leg.side * leg.qty * fills[name] for leg, fills in legs), 4)
    return out


def intrinsic(opt_type: str, strike: float, S: float) -> float:
    if opt_type == "call":
        return max(0.0, S - strike)
    return max(0.0, strike - S)


def payoff_analysis(legs: list[LegSpec], net_debit_usd: float) -> dict:
    """Expiry P&L analysis of the combo (piecewise linear in S). Evaluates P&L(S) =
    sum(side*qty*intrinsic)*100 - net_debit_usd at S=0, every strike, and checks the slopes
    beyond the outermost strikes. Assumes ALL legs share one expiry for the analysis - for
    calendars/diagonals the near-expiry payoff is NOT well-defined, callers must use the
    declared-basis path instead (analyzable=False).

    Returns {analyzable, max_loss_usd (None when unbounded), max_gain_usd (None when unbounded),
    unbounded_up, unbounded_down_note}. `unbounded_up` True = naked short-call exposure
    (slope < 0 as S -> inf) -> CaR margin basis required. Downside is always bounded (S >= 0).
    """
    if not legs:
        return {"analyzable": False, "max_loss_usd": None, "max_gain_usd": None,
                "unbounded_up": False, "note": "no legs"}
    if len({leg.expiry for leg in legs}) > 1:
        return {"analyzable": False, "max_loss_usd": None, "max_gain_usd": None,
                "unbounded_up": False, "note": "multi-expiry combo: expiry payoff undefined"}

    def pnl(S: float) -> float:
        return sum(leg.side * leg.qty * intrinsic(leg.opt_type, leg.strike, S)
                   for leg in legs) * 100.0 - net_debit_usd

    strikes = sorted({leg.strike for leg in legs})
    # slope for S beyond the highest strike: every call is ITM (slope side*qty), puts OTM.
    slope_up = sum(leg.side * leg.qty for leg in legs if leg.opt_type == "call")
    candidates = [0.0] + strikes + [strikes[-1] * 2 + 100.0]
    values = [pnl(s) for s in candidates]
    unbounded_up = slope_up < 0
    max_gain = None if slope_up > 0 else round(max(values), 2)
    max_loss = None if unbounded_up else round(-min(values), 2)
    if max_loss is not None:
        max_loss = max(0.0, max_loss)
    return {"analyzable": True, "max_loss_usd": max_loss, "max_gain_usd": max_gain,
            "unbounded_up": unbounded_up, "note": ""}


# --------------------------------------------------------------------------- open combo
@dataclass
class LegState:
    """A LegSpec + its entry market snapshot + per-ledger open fills (rebuildable)."""
    spec: LegSpec
    entry_bid: float
    entry_ask: float
    open_fills: dict                       # {worst, base, optimistic} per-share
    entry_iv: float = 0.0
    entry_delta: float = 0.0
    entry_gamma: float = 0.0
    entry_vega: float = 0.0
    entry_theta_day: float = 0.0           # per calendar day, per share (vendor convention)

    @property
    def entry_mid(self) -> float:
        return (self.entry_bid + self.entry_ask) / 2.0


@dataclass
class ComboPosition:
    """In-memory state of one open combo (rebuildable from its lab_entry record)."""
    position_id: str
    strategy_id: str
    strategy_config_hash: str
    kind: str                              # "short_strangle" | "iron_condor" | ... (registry kind)
    underlying: str
    legs: list                             # list[LegState]
    net_open: dict                         # signed per-ledger net open fill (per share)
    grading: dict                          # frozen-at-entry basis block (see build_combo_entry_record)
    entry_ts: float
    entry_minute: int
    entry_day: str
    entry_S: float
    contracts: int = 1                     # combo units (per-leg qty is inside LegSpec)
    fav_max: float = 0.0                   # max favorable underlying move (signed by net delta)
    fav_min: float = 0.0
    last_mark_ts: float = 0.0
    carried: dict = field(default_factory=dict)   # strategy-managed state, persisted via marks
    notes: dict = field(default_factory=dict)

    @property
    def net_delta_sign(self) -> float:
        d = sum(ls.spec.side * ls.spec.qty * ls.entry_delta for ls in self.legs)
        return 1.0 if d >= 0 else -1.0

    @property
    def nearest_expiry(self) -> date:
        return min(ls.spec.expiry for ls in self.legs)

    def observe_underlying(self, S: float) -> None:
        if S <= 0 or self.entry_S <= 0:
            return
        f = (S / self.entry_S - 1.0) * self.net_delta_sign
        self.fav_max = max(self.fav_max, f)
        self.fav_min = min(self.fav_min, f)


# --------------------------------------------------------------------------- record builders (pure)
def build_combo_entry_record(*, ts: float, day: str, entry_minute: int, position_id: str,
                             strategy_id: str, strategy_config_hash: str, kind: str,
                             legs: list[dict], S: float, grading: dict, signal: dict,
                             greeks_net: dict, risk_flags: list,
                             contracts: int = 1, covariates: dict | None = None) -> dict:
    """One hypothetical combo entry. Each item of `legs` must carry:
      {occ, underlying, opt_type, strike, expiry(iso), side, qty, nbbo:{bid,ask},
       fills:{worst,base,optimistic}, iv, delta, gamma, vega, theta_day}
    `grading` is the FROZEN basis block: {basis: debit|max_loss|car, denom_usd, max_loss_usd,
    max_gain_usd, car_rule, car_inputs, declared_basis, basis_mismatch}.
    """
    specs = [(_spec_from_dict(l), l["fills"]) for l in legs]
    net = combo_net_open(specs)
    return {"schema": SCHEMA, "event": "lab_entry", "ts_epoch": round(float(ts), 3),
            "day": day, "entry_minute": int(entry_minute), "position_id": position_id,
            "strategy_id": strategy_id, "strategy_config_hash": strategy_config_hash,
            "kind": kind, "S": round(float(S), 4), "contracts": int(contracts),
            "legs": [_leg_dict(l) for l in legs],
            "net_fills": net,
            "grading": dict(grading), "greeks_net": dict(greeks_net),
            "signal": dict(signal),
            "risk_flags": sorted(set(str(f) for f in risk_flags)),
            "covariates": dict(covariates) if covariates else None}


def build_combo_mark_record(*, ts: float, position_id: str, strategy_id: str,
                            legs_nbbo: list[dict], S: float, state: dict,
                            action: str, rule: str) -> dict:
    """One reval cycle. `legs_nbbo` = [{occ, bid, ask, age_s}]; unrealized P&L is derived by
    readers from close-fills at these quotes (liquidation convention), not duplicated here."""
    return {"schema": SCHEMA, "event": "lab_mark", "ts_epoch": round(float(ts), 3),
            "position_id": position_id, "strategy_id": strategy_id,
            "legs": [{"occ": str(l["occ"]), "bid": round(max(0.0, float(l["bid"])), 4),
                      "ask": round(max(0.0, float(l["ask"])), 4),
                      "age_s": round(float(l.get("age_s", 0.0)), 1)} for l in legs_nbbo],
            "S": round(float(S), 4), "state": dict(state), "action": action, "rule": rule}


def build_combo_exit_record(*, ts: float, day: str, pos: ComboPosition, rule: str,
                            legs_close: list[dict], S: float, state: dict,
                            hold_trading_days: float,
                            fills_override: dict | None = None) -> dict:
    """One hypothetical combo exit. `legs_close` = [{occ, bid, ask}] for EVERY leg (order must
    match pos.legs by occ). `fills_override` (settlement): {occ: settle_price} - identical fill
    across all three ledgers (expiry settlement has no spread).

    Emits per-ledger {entry_net, exit_net, gross_pnl_usd, net_pnl_usd, return_pct} where
    return_pct = net_pnl_usd / grading.denom_usd (the frozen denominator).
    """
    by_occ = {l["occ"]: l for l in legs_close}
    pairs_close = []
    for ls in pos.legs:
        q = by_occ.get(ls.spec.occ)
        if q is None:
            raise ValueError(f"missing close quote for leg {ls.spec.occ}")
        if fills_override and ls.spec.occ in fills_override:
            px = round(max(0.0, float(fills_override[ls.spec.occ])), 4)
            fills = {"worst": px, "base": px, "optimistic": px}
        else:
            fills = leg_close_fills(ls.spec.side, q.get("bid", 0.0), q.get("ask", 0.0))
        pairs_close.append((ls.spec, fills))
    net_close = combo_net_close(pairs_close)

    mult = 100.0 * pos.contracts
    denom = float(pos.grading.get("denom_usd") or 0.0)
    open_mid = sum(ls.spec.side * ls.spec.qty * ls.entry_mid for ls in pos.legs)
    close_mid = sum(s.side * s.qty * ((by_occ[s.occ].get("bid", 0.0) + by_occ[s.occ].get("ask", 0.0)) / 2.0
                                      if not (fills_override and s.occ in fills_override)
                                      else fills_override[s.occ])
                    for s, _ in pairs_close)
    gross = (close_mid - open_mid) * mult
    ledgers = {}
    for name in LEDGER_NAMES:
        net_pnl = (net_close[name] - pos.net_open[name]) * mult
        ledgers[name] = {"entry_net": pos.net_open[name], "exit_net": net_close[name],
                         "gross_pnl_usd": round(gross, 2), "net_pnl_usd": round(net_pnl, 2),
                         "return_pct": round(net_pnl / denom, 6) if denom > 0 else None}
    # spread tax on the WORST ledger relative to mid-to-mid, both sides.
    spread_paid = ((pos.net_open["worst"] - open_mid) + (close_mid - net_close["worst"])) * mult
    theta_day_net = sum(ls.spec.side * ls.spec.qty * ls.entry_theta_day for ls in pos.legs)
    theta_paid = theta_day_net * max(0.0, hold_trading_days) * mult
    return {"schema": SCHEMA, "event": "lab_exit", "ts_epoch": round(float(ts), 3),
            "day": day, "position_id": pos.position_id, "strategy_id": pos.strategy_id,
            "strategy_config_hash": pos.strategy_config_hash, "kind": pos.kind,
            "underlying": pos.underlying, "rule": rule, "S": round(float(S), 4),
            "legs_close": [{"occ": s.occ, "bid": round(max(0.0, float(by_occ[s.occ].get("bid", 0.0))), 4),
                            "ask": round(max(0.0, float(by_occ[s.occ].get("ask", 0.0))), 4),
                            "iv": round(float(by_occ[s.occ].get("iv") or 0.0), 4),
                            "fills": f} for s, f in pairs_close],
            "ledgers": ledgers, "grading": dict(pos.grading),
            "decomposition": {"theta_paid_usd": round(theta_paid, 2),
                              "spread_paid_usd": round(spread_paid, 2)},
            "underlying_mfe": round(pos.fav_max, 6), "underlying_mae": round(pos.fav_min, 6),
            "hold_trading_days": round(float(hold_trading_days), 6),
            "entry_ts_epoch": round(pos.entry_ts, 3), "state": dict(state)}


def combo_from_entry(rec: dict) -> ComboPosition | None:
    """Rebuild an open combo from its lab_entry record (restart safety). None on malformed."""
    try:
        legs = []
        for l in rec["legs"]:
            spec = _spec_from_dict(l)
            legs.append(LegState(spec=spec,
                                 entry_bid=float(l["nbbo"]["bid"]), entry_ask=float(l["nbbo"]["ask"]),
                                 open_fills=dict(l["fills"]),
                                 entry_iv=float(l.get("iv") or 0.0),
                                 entry_delta=float(l.get("delta") or 0.0),
                                 entry_gamma=float(l.get("gamma") or 0.0),
                                 entry_vega=float(l.get("vega") or 0.0),
                                 entry_theta_day=float(l.get("theta_day") or 0.0)))
        return ComboPosition(
            position_id=str(rec["position_id"]), strategy_id=str(rec["strategy_id"]),
            strategy_config_hash=str(rec["strategy_config_hash"]), kind=str(rec.get("kind", "")),
            underlying=str(legs[0].spec.underlying if legs else "").upper(),
            legs=legs, net_open=dict(rec["net_fills"]), grading=dict(rec["grading"]),
            entry_ts=float(rec["ts_epoch"]), entry_minute=int(rec.get("entry_minute") or 0),
            entry_day=str(rec.get("day", "")), entry_S=float(rec.get("S", 0.0)),
            contracts=int(rec.get("contracts") or 1),
            notes=dict((rec.get("signal") or {}).get("notes") or {}))
    except (KeyError, TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- helpers
def _spec_from_dict(l: dict) -> LegSpec:
    return LegSpec(occ=str(l["occ"]), underlying=str(l["underlying"]).upper(),
                   opt_type=str(l["opt_type"]), strike=float(l["strike"]),
                   expiry=(l["expiry"] if isinstance(l["expiry"], date)
                           else date.fromisoformat(str(l["expiry"]))),
                   side=int(l["side"]), qty=int(l.get("qty", 1)))


def _leg_dict(l: dict) -> dict:
    return {"occ": str(l["occ"]), "underlying": str(l["underlying"]).upper(),
            "opt_type": str(l["opt_type"]), "strike": float(l["strike"]),
            "expiry": str(l["expiry"]), "side": int(l["side"]), "qty": int(l.get("qty", 1)),
            "nbbo": {"bid": round(float(l["nbbo"]["bid"]), 4),
                     "ask": round(float(l["nbbo"]["ask"]), 4)},
            "fills": dict(l["fills"]),
            "iv": round(float(l.get("iv") or 0.0), 4), "delta": round(float(l.get("delta") or 0.0), 4),
            "gamma": round(float(l.get("gamma") or 0.0), 6), "vega": round(float(l.get("vega") or 0.0), 4),
            "theta_day": round(float(l.get("theta_day") or 0.0), 4)}
