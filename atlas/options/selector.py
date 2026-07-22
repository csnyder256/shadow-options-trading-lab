"""CONTRACT SELECTOR (O2) - value-based contract choice, NOT affordability (owner, 2026-07-09:
"some contracts have better intrinsic value than others"). Three stages per the research-
calibrated plan: hard gates (every rejection logged with a reason code) -> EV via full-BSM
scenario repricing (never linear-greek-only) -> score with the owner's skew as a TIEBREAK
(high delta 0.55-0.75, short DTE) on top of EV%, never instead of it.

Pure: chain rows + context in, ranked picks + rejections out. No IO, no clock reads.
The selector scans DTE 0-5 and RECORDS when the best value lands at DTE 4-5 (outside the owner's
stated 0-3 skew) - evidence to renegotiate the cap, never a silent override.
"""

from __future__ import annotations

import math as _m
from dataclasses import dataclass, field
from datetime import date, datetime

from atlas.options import math as om
from atlas.options.vendor.blackscholes import bs_price, greeks, implied_vol
from atlas.options.vendor.models import OptionType

INDEX_UNDERLYINGS = {"SPY", "QQQ", "IWM", "DIA"}


@dataclass(frozen=True)
class ContractQuote:
    """One chain row, feed-agnostic (Tradier greeks=true or any provider)."""
    occ: str
    underlying: str
    opt_type: str            # "call" | "put"
    strike: float
    expiry: date
    bid: float
    ask: float
    last: float = 0.0
    volume: float = 0.0
    open_interest: float = 0.0
    vendor_iv: float = 0.0

    @property
    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.last


@dataclass(frozen=True)
class SelectorParams:
    delta_gate: tuple = (0.40, 0.80)
    delta_preferred: tuple = (0.55, 0.75)
    delta_ban_below: float = 0.35          # lotto zone - permanent ban
    spread_clean_pct: float = 0.05
    spread_max_pct: float = 0.10
    # premium-TIERED absolute cap (audit 2026-07-16 Wave 1 / FUNNEL-THROUGHPUT-4,
    # opts-audit-wave1-funnel-v1): effective cap = max(spread_abs_max_nonindex,
    # spread_abs_pct_of_mid x mid) - a flat $0.30 banned every large-cap catalyst book whose
    # spread is pennies in % terms; spread_max_pct stays the binding relative gate.
    spread_abs_max_nonindex: float = 0.30
    spread_abs_pct_of_mid: float = 0.05
    oi_min: float = 300.0
    oi_min_index: float = 1000.0
    # clock-consistent liquidity floors (audit SELECTOR-6, measured live 2026-07-16:
    # a fresh post-gap ATM strike had OI=0 with 6,255 contracts traded by 09:35 and was
    # hard-vetoed; day-cum volume>=100 at 09:35 is a full-day standard applied to minutes):
    # volume scales with elapsed session fraction; index DTE<=1 daily-expiry series may pass
    # on live volume alone when prior-day OI is structurally unrepresentative.
    volume_min: float = 100.0
    volume_alt_index_dte1: float = 500.0   # index DTE<=1: OI>=oi_min_index OR day-volume>=this
    # premium floor (audit + microstructure research, opts-audit-wave1-funnel-v1): below
    # ~$0.50 the 1-tick minimum spread alone is a 3-6% round-trip toll no funnel edge clears.
    premium_min_mid: float = 0.50
    # touch-feasibility coherence gate (audit PROBABILITY-MEASURE-1/SELECTOR-3, 2/2 upheld:
    # ev_pct was a target-ambition meter - the market-implied weight on the live IWM trade was
    # -0.004 while the claimed EV was +53%). p_touch_target is computed below and now GATES:
    # the priced-lottery class (10+ sigma late-day targets) dies here.
    p_touch_min: float = 0.25
    # None = NO premium cap (owner, 2026-07-10; sweep_ledger opts-tweak-remove-premium-cap-v1):
    # the shadow grades decision quality, never affordability - the old 350.0 rejected every
    # 0.55-0.75-delta index contract except deep-0DTE, fighting the delta skew. Set a number
    # to re-enable as a "can we afford it" FINAL filter.
    premium_max_usd: float | None = None
    # per-DTE lambda caps (audit Wave 1.6 / FUNNEL-THROUGHPUT-3, opts-audit-wave1-funnel-v1):
    # lambda = delta*S/mid scales ~1/(sigma*sqrt(T)), so the flat 90 cap was a de-facto ban on
    # 0-1 DTE index ATM (measured live 2026-07-16: ATM lambdas 107-271 across DTE 0-5). The
    # floor drops to lambda_floor_deep for delta>=deep_delta (stock-replacement contracts on
    # high-IV names compute lambda ~10-12 and were quietly vetoed).
    lambda_band: tuple = (15.0, 90.0)      # (floor, cap for DTE>=2) - legacy field, still live
    lambda_cap_dte0: float = 200.0
    lambda_cap_dte1: float = 120.0
    lambda_floor_deep: float = 10.0
    deep_delta: float = 0.70
    max_dte: int = 5
    no_0dte_after_min: int = 14 * 60       # no 0DTE entries after close-120 (14:00 normal days)
    session_close_min: int = 16 * 60       # today's RTH close (per-day via for_close)
    overnight_min_dte: int = 2             # a hold that may run overnight needs DTE >= 2
    hold_max_frac_of_life: float = 1.0 / 3.0
    # 0DTE carve-out (owner, 2026-07-09 night; sweep_ledger opts-tweak-0dte-carveout-v1): a
    # same-day 0DTE's remaining life IS the rest-of-day horizon, so the 1/3-of-life gate
    # structurally banned the 0DTE skew the plan explicitly allows before 14:00. Exempt dte==0
    # (already gated by no_0dte_after_min + overnight_needs_dte2); risk is governed by the EV
    # stage, the lambda/premium gates, and exit rule (a)'s 15:00 clock.
    zero_dte_third_of_life_exempt: bool = True
    ev_pct_min: float = 10.0
    ev_vs_spread_mult: float = 2.0         # EV$ >= 2x round-trip spread
    p_profit_min: float = 0.40
    r: float = 0.04
    q: float = 0.0
    n_grid: int = 11

    @classmethod
    def for_close(cls, close_min: int = 16 * 60) -> "SelectorParams":
        """Per-day params: the 0DTE entry cutoff keeps its 'two hours before the close' intent
        (14:00 normal days, 11:00 half days). for_close(960) == SelectorParams() - pinned."""
        return cls(no_0dte_after_min=int(close_min) - 120, session_close_min=int(close_min))


@dataclass(frozen=True)
class ScoredPick:
    quote: ContractQuote
    score: float
    ev_usd: float                          # per contract (x100)
    ev_pct: float
    p_profit: float
    p_touch_target: float
    solved_iv: float
    delta: float
    gamma: float
    theta_day: float
    vega: float
    lam: float                             # effective leverage
    spread_pct: float
    dte: int
    flags: tuple = ()
    decomposition: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SelectorResult:
    picks: tuple                           # top-N ScoredPick, best first
    rejections: tuple                      # (occ, reason) pairs - every gated row, always logged
    best_dte_outside_skew: bool = False    # argmax landed at DTE 4-5 (renegotiation evidence)


def _gate(reasons: list, occ: str, cond: bool, code: str) -> bool:
    if not cond:
        reasons.append((occ, code))
        return False
    return True


def select_contract(rows: list, *, underlying: str, S: float, direction: str,
                    target_move: float, p_thesis: float, horizon_T: float,
                    now_et: datetime, hv20: float | None = None, iv_rank: float | None = None,
                    event_blackout: str | None = None, underlying_state: str | None = None,
                    may_run_overnight: bool = False,
                    params: SelectorParams = SelectorParams(), top_n: int = 3) -> SelectorResult:
    """Rank the chain for one directional thesis. `rows` = ContractQuote list (any expiries,
    both types); direction 'call'|'put'; target_move fractional (+0.005 = +0.5% underlying);
    horizon_T = planned hold in TRADING years. Returns picks + every rejection with its reason."""
    p = params
    is_index = underlying.upper() in INDEX_UNDERLYINGS
    minute = now_et.hour * 60 + now_et.minute
    rejections: list = []
    scored: list[ScoredPick] = []

    for cq in rows:
        occ = cq.occ
        # DATA-VALIDITY gate (opts-fix-selector-halt-guard-v1): a halted / SEC-suspended underlying
        # cannot be traded or validly priced - reject EVERY row, the same class as crossed_nbbo /
        # no_quote. This is NOT a promotion-ladder signal (the halt-reopening trade has no edge);
        # it is threaded in as a per-underlying param because the selector is pure, and it lives in
        # SelectorParams space (not DEFAULTS) so it does not move config_hash / split the cohort.
        if underlying_state:
            _gate(rejections, occ, False, f"underlying_{underlying_state}")
            continue
        if cq.opt_type != direction:
            continue                                          # not a rejection - wrong half
        mid = cq.mid
        if not _gate(rejections, occ, not (cq.bid > 0 and cq.ask > 0 and cq.ask < cq.bid),
                     "crossed_nbbo"):
            continue                                          # crossed book - never price off it
        if not _gate(rejections, occ, mid > 0 and cq.bid > 0 and cq.ask >= cq.bid, "no_quote"):
            continue
        # adjusted/non-standard contracts (OSI digit-suffixed roots like NLY1, deliverable
        # != 100) can't be priced with a hardcoded x100 multiplier - reject on a DIGIT in the
        # OCC root (research-verified rule: root-vs-underlying equality false-positives on
        # BRK.B->BRKB-style symbol mappings; the OI floor never catches these because adjusted
        # series retain large stale OI). Short non-OCC symbols (test fakes) pass through.
        root = occ[:-15].strip().upper() if len(occ) > 15 else None
        if not _gate(rejections, occ,
                     root is None or not any(ch.isdigit() for ch in root),
                     "non_standard_contract"):
            continue
        dte = (cq.expiry - now_et.date()).days
        if not _gate(rejections, occ, 0 <= dte <= p.max_dte, "dte_out_of_scan"):
            continue
        if not _gate(rejections, occ, not (dte == 0 and minute >= p.no_0dte_after_min),
                     "zero_dte_after_1400"):
            continue
        if not _gate(rejections, occ, not (may_run_overnight and dte < p.overnight_min_dte),
                     "overnight_needs_dte2"):
            continue
        T = om.trading_T(now_et, cq.expiry, close_minute=p.session_close_min)
        third_of_life_exempt = dte == 0 and p.zero_dte_third_of_life_exempt
        if not third_of_life_exempt and not _gate(
                rejections, occ, horizon_T <= p.hold_max_frac_of_life * T,
                "hold_exceeds_third_of_life"):
            continue
        spread = cq.ask - cq.bid
        spread_pct = spread / mid if mid > 0 else 1.0
        if not _gate(rejections, occ, spread_pct <= p.spread_max_pct, "spread_pct"):
            continue
        # premium-tiered absolute cap (audit Wave 1 / FUNNEL-THROUGHPUT-4)
        abs_cap = max(p.spread_abs_max_nonindex, p.spread_abs_pct_of_mid * mid)
        if not _gate(rejections, occ, is_index or spread <= abs_cap, "spread_abs"):
            continue
        # premium floor (audit: below ~$0.50 the minimum tick alone is a 3-6% round-trip toll)
        if not _gate(rejections, occ, mid >= p.premium_min_mid, "premium_floor"):
            continue
        # clock-consistent liquidity (audit SELECTOR-6): prior-day OI OR live volume for index
        # daily expiries; volume floor scaled by elapsed session fraction
        oi_floor = p.oi_min_index if is_index else p.oi_min
        oi_ok = cq.open_interest >= oi_floor
        if is_index and dte <= 1 and not oi_ok:
            oi_ok = cq.volume >= p.volume_alt_index_dte1
        if not _gate(rejections, occ, oi_ok, "open_interest"):
            continue
        elapsed_frac = min(1.0, max(0.0, (minute - 570) / 390.0))
        vol_floor = p.volume_min * max(elapsed_frac, 5.0 / 390.0)   # >=5-min-equivalent floor
        if not _gate(rejections, occ, cq.volume >= vol_floor, "volume"):
            continue
        premium_usd = cq.ask * 100.0
        if p.premium_max_usd is not None and \
                not _gate(rejections, occ, premium_usd <= p.premium_max_usd, "premium_cap"):
            continue
        if not _gate(rejections, occ, event_blackout is None, f"event_{event_blackout}"):
            continue

        ot = OptionType.CALL if direction == "call" else OptionType.PUT
        iv = implied_vol(mid, S, cq.strike, p.r, p.q, T, ot)
        if iv is None or iv <= 0:
            iv = cq.vendor_iv
        if not _gate(rejections, occ, iv is not None and iv > 0, "no_iv"):
            continue
        g = greeks(S, cq.strike, p.r, p.q, iv, T, ot)
        adelta = abs(g.delta)
        if not _gate(rejections, occ, adelta >= p.delta_ban_below, "lotto_delta_ban"):
            continue
        if not _gate(rejections, occ, p.delta_gate[0] <= adelta <= p.delta_gate[1], "delta_gate"):
            continue
        # per-DTE lambda band (audit Wave 1.6): cap 200/120/90 for DTE 0/1/>=2; floor 15
        # (10 for deep delta >= 0.70 stock-replacement contracts)
        lam = adelta * S / mid
        lam_cap = (p.lambda_cap_dte0 if dte == 0
                   else p.lambda_cap_dte1 if dte == 1 else p.lambda_band[1])
        lam_floor = p.lambda_floor_deep if adelta >= p.deep_delta else p.lambda_band[0]
        if not _gate(rejections, occ, lam_floor <= lam <= lam_cap, "lambda_band"):
            continue

        # ---- touch-feasibility coherence gate (audit PROBABILITY-MEASURE-1/SELECTOR-3) -------
        # p_touch under mu=0 with the contract's own solved IV: the market-consistent
        # probability the thesis target is even reachable in the horizon. Gating here kills the
        # priced-lottery class BEFORE the mixture EV can manufacture a +50% ev_pct from it.
        target_px = S * (1.0 + (abs(target_move) if direction == "call" else -abs(target_move)))
        pt = om.p_touch(S, target_px, max(iv, (hv20 or 0.0)), min(horizon_T, T), mu=0.0)
        if not _gate(rejections, occ, pt >= p.p_touch_min, "touch_feasibility"):
            continue

        # ---- Stage 2: EV via scenario repricing, worst-ledger fill (buy at ask) --------------
        exit_cost = spread / 2.0                                # est. half-spread on the way out
        res = om.ev_hold_thesis(S, cq.strike, ot, p.r, p.q, iv, T, min(horizon_T, T), cq.ask,
                                target_move=target_move if direction == "call" else -abs(target_move),
                                horizon_T=horizon_T, p_thesis=p_thesis, n_grid=p.n_grid)
        ev_share = res["ev"] - exit_cost
        ev_usd = ev_share * 100.0
        ev_pct = ev_share / cq.ask * 100.0 if cq.ask > 0 else -100.0
        # market-implied touch probability (audit Wave 0.3 instrumentation): p_touch under the
        # risk-neutral drift r - logged beside the physical p_touch so the measure disagreement
        # is visible on every entry row (the live IWM trade carried five unreconciled numbers)
        p_mkt = om.p_touch(S, target_px, max(iv, (hv20 or 0.0)), min(horizon_T, T), mu=p.r)

        if not _gate(rejections, occ, ev_pct >= p.ev_pct_min, "ev_pct_floor"):
            continue
        if not _gate(rejections, occ, ev_usd >= p.ev_vs_spread_mult * spread * 100.0,
                     "ev_vs_spread"):
            continue
        if not _gate(rejections, occ, res["p_profit"] >= p.p_profit_min, "p_profit_floor"):
            continue

        # ---- Stage 3: score --------------------------------------------------------------------
        # (audit DEAD-LAYERS-3/IV-ARCHIVE-2: the iv_rank and hv20 richness penalties were
        # provably order-invariant no-ops - a per-call constant subtracted from every candidate
        # before a within-call sort. Deleted; iv_rank stays a logged entry covariate.)
        score = ev_pct
        score -= 0.5 * spread_pct * 100.0
        in_pref = p.delta_preferred[0] <= adelta <= p.delta_preferred[1]
        if in_pref:
            score += 5.0
        flags = []
        if spread_pct > p.spread_clean_pct:
            flags.append("spread_5_10pct")
        if dte == 0:
            flags.append("zero_dte")
        # theta convention unified with the exit engine (audit MATH-CORE-5/SELECTOR-9,
        # opts-audit-wave2-exitv3-v1): trading-day units (x365/252), and the 0DTE afternoon
        # multiplier is GONE - the exit engine removed it as double-counting in the 07-10 math
        # audit while the selector kept applying it, so entry and exit ledgers logged theta on
        # two different conventions.
        theta_day = g.theta * (365.0 / 252.0)
        dt_days = min(horizon_T, T) * 252.0
        signed_move = abs(target_move) if direction == "call" else -abs(target_move)
        decomposition = {
            # SELECTOR-12 fix: sign the move by direction so a put's thesis capture is positive
            "delta_capture": round(g.delta * S * signed_move * p_thesis * 100.0, 2),
            "theta_paid": round(theta_day * dt_days * 100.0, 2),
            "spread_paid": round((cq.ask - mid + exit_cost) * 100.0, 2),
            "vega_per_pt": round(g.vega * 100.0, 2),
            # audit Wave 0.3 measure-disagreement instrumentation (all logged, none gate here):
            "ev_thesis_pct": round(res.get("ev_thesis", 0.0) / cq.ask * 100.0, 2) if cq.ask > 0 else None,
            "ev_mu0_pct": round(res.get("ev_mu0", 0.0) / cq.ask * 100.0, 2) if cq.ask > 0 else None,
            "p_mkt_touch": round(p_mkt, 4),
        }
        scored.append(ScoredPick(cq, round(score, 3), round(ev_usd, 2), round(ev_pct, 2),
                                 round(res["p_profit"], 3), round(pt, 3), round(iv, 4),
                                 round(g.delta, 3), round(g.gamma, 5), round(theta_day, 4),
                                 round(g.vega, 4), round(lam, 1), round(spread_pct, 4), dte,
                                 tuple(flags), decomposition))

    scored.sort(key=lambda s: s.score, reverse=True)
    outside = bool(scored) and scored[0].dte >= 4
    return SelectorResult(tuple(scored[:top_n]), tuple(rejections), outside)
