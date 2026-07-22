"""Signal Engine (docs/04) - deterministic candidate generation.

Computes a fully-numeric feature record from OHLCV bars, then detects candidates from the
closed setup-type taxonomy and scores each with the deterministic quality filter. No LLM
involvement: these numbers are authoritative and are what the model is later allowed to
argue about (and what the orchestrator re-checks the model's cited_numbers against).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from atlas.signals import features as F
from atlas.signals.price_action import score_buy_low
from atlas.signals.quality_filter import quality_score

# Nominal ATR stop multiple used only for the reward:risk *quality* estimate. The Risk Engine
# computes the real bracket from risk_limits/position_sizing; this is a pre-LLM heuristic.
_NOMINAL_ATR_STOP_MULT = 2.0


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    if math.isnan(x):
        return lo
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class SignalParams:
    rsi_period: int
    adx_period: int
    atr_period: int
    ema_fast: int
    ema_slow: int
    sma_trend: int
    bollinger_period: int
    bollinger_std: float
    vol_zscore_window: int
    rel_strength_window: int
    benchmark_symbol: str
    adx_trend_min: float
    rsi_oversold: float
    rsi_overbought: float
    vol_anomaly_zscore: float
    gap_pct_min: float
    min_quality_score: float
    quality_weights: Mapping[str, float]
    # Whole-share affordability band (Path 1) - the picker drops names outside [min,max] share price
    # before the LLM cascade. Defaults are permissive so direct (non-config) constructions are unaffected.
    min_entry_price: float = 5.0
    max_entry_price: float = 1.0e12

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> "SignalParams":
        ind = raw["indicators"]
        dt = raw["derived_thresholds"]
        qs = raw["quality_score"]
        pb = raw.get("price_band", {})
        return cls(
            rsi_period=int(ind["rsi_period"]),
            adx_period=int(ind["adx_period"]),
            atr_period=int(ind["atr_period"]),
            ema_fast=int(ind["ema_fast"]),
            ema_slow=int(ind["ema_slow"]),
            sma_trend=int(ind["sma_trend"]),
            bollinger_period=int(ind["bollinger_period"]),
            bollinger_std=float(ind["bollinger_std"]),
            vol_zscore_window=int(ind["vol_zscore_window"]),
            rel_strength_window=int(ind["rel_strength_window"]),
            benchmark_symbol=str(ind["benchmark_symbol"]),
            adx_trend_min=float(dt["adx_trend_min"]),
            rsi_oversold=float(dt["rsi_oversold"]),
            rsi_overbought=float(dt["rsi_overbought"]),
            vol_anomaly_zscore=float(dt["vol_anomaly_zscore"]),
            gap_pct_min=float(dt["gap_pct_min"]),
            min_quality_score=float(qs["min_quality_score"]),
            quality_weights=dict(qs["weights"]),
            min_entry_price=float(pb.get("min_entry_price", 5.0)),
            max_entry_price=float(pb.get("max_entry_price", 1.0e12)),
        )


@dataclass(frozen=True)
class FeatureRecord:
    last_close: float
    prev_close: float
    last_open: float
    rsi: float
    adx: float
    atr: float
    vwap: float
    ema_fast: float
    ema_slow: float
    sma_trend: float
    bb_upper: float
    bb_mid: float
    bb_lower: float
    vol_zscore: float
    gap_pct: float
    rel_strength: float
    recent_high: float
    recent_low: float

    def as_dict(self) -> dict[str, float]:
        return {
            "rsi_14": round(self.rsi, 4),
            "adx_14": round(self.adx, 4),
            "atr_14": round(self.atr, 4),
            "vwap": round(self.vwap, 4),
            "ema_9": round(self.ema_fast, 4),
            "ema_21": round(self.ema_slow, 4),
            "sma_200": None if math.isnan(self.sma_trend) else round(self.sma_trend, 4),
            "bb_upper": round(self.bb_upper, 4),
            "bb_lower": round(self.bb_lower, 4),
            "vol_zscore": round(self.vol_zscore, 4),
            "gap_pct": round(self.gap_pct, 4),
            "rel_strength": round(self.rel_strength, 4),
            "last_close": round(self.last_close, 4),
        }


@dataclass(frozen=True)
class CandidateSetup:
    symbol: str
    setup_type: str
    direction: str
    entry_price: float
    atr: float
    quality: float
    quality_components: dict[str, float]
    features: dict[str, float] = field(default_factory=dict)


class SignalEngine:
    def __init__(self, params: SignalParams):
        self.p = params

    # ---- features ---------------------------------------------------------
    def compute_features(
        self, *, high, low, close, volume, open_, benchmark_close,
        session_fraction: float | None = None,
    ) -> FeatureRecord:
        high = np.asarray(high, float)
        low = np.asarray(low, float)
        close = np.asarray(close, float)
        volume = np.asarray(volume, float)
        open_ = np.asarray(open_, float)
        p = self.p

        rsi = F.rsi(close, p.rsi_period)
        adx = F.adx(high, low, close, p.adx_period)
        atr = F.atr(high, low, close, p.atr_period)
        vwap = F.vwap(high, low, close, volume)
        ema_fast = F.ema(close, p.ema_fast)
        ema_slow = F.ema(close, p.ema_slow)
        sma_trend = F.sma(close, p.sma_trend)
        bb_mid, bb_up, bb_lo = F.bollinger(close, p.bollinger_period, p.bollinger_std)
        # Live daily bars end with TODAY'S PARTIAL bar: z-scoring its cumulative volume against 20
        # COMPLETE days reads -1..-2 all morning on every name (33/55 live analyst vetoes cited exactly
        # this fabricated "no volume" - on names the RH scan REQUIRED RVOL>=1.3-1.8 to surface). When the
        # caller says how much of the session has elapsed, project the partial bar to a full-day estimate
        # for the z-score ONLY (VWAP etc. keep the true traded volume). Floor guards the open, where a
        # tiny elapsed fraction would explode the projection.
        vol_for_z = volume
        if session_fraction is not None and len(volume) > 0 and 0.0 < session_fraction < 0.98:
            vol_for_z = volume.copy()
            vol_for_z[-1] = volume[-1] / max(session_fraction, 0.08)
        vol_z = F.volume_zscore(vol_for_z, p.vol_zscore_window)
        prior = high[:-1]
        recent_high = float(np.max(prior[-20:])) if len(prior) >= 1 else float(high[-1])
        prior_low = low[:-1]
        recent_low = float(np.min(prior_low[-20:])) if len(prior_low) >= 1 else float(low[-1])

        return FeatureRecord(
            last_close=float(close[-1]),
            prev_close=float(close[-2]) if len(close) >= 2 else float(close[-1]),
            last_open=float(open_[-1]),
            rsi=float(rsi[-1]),
            adx=float(adx[-1]),
            atr=float(atr[-1]),
            vwap=float(vwap[-1]),
            ema_fast=float(ema_fast[-1]),
            ema_slow=float(ema_slow[-1]),
            sma_trend=float(sma_trend[-1]),
            bb_upper=float(bb_up[-1]),
            bb_mid=float(bb_mid[-1]),
            bb_lower=float(bb_lo[-1]),
            vol_zscore=float(vol_z[-1]),
            gap_pct=F.gap_pct(float(close[-2]) if len(close) >= 2 else float(open_[-1]),
                              float(open_[-1])),
            rel_strength=F.relative_strength(close, benchmark_close, p.rel_strength_window),
            recent_high=recent_high,
            recent_low=recent_low,
        )

    # ---- quality components ----------------------------------------------
    def _trend_alignment(self, f: FeatureRecord) -> float:
        ta = _clamp(f.adx / (self.p.adx_trend_min * 2.0) * 100.0)
        if not (f.ema_fast > f.ema_slow):
            ta *= 0.5
        if not math.isnan(f.sma_trend) and f.last_close < f.sma_trend:
            ta *= 0.5
        return ta

    def _confirmation(self, f: FeatureRecord) -> float:
        return _clamp(f.vol_zscore / self.p.vol_anomaly_zscore * 100.0)

    def _location(self, f: FeatureRecord, reference: float) -> float:
        if reference <= 0 or math.isnan(reference):
            return 0.0
        dist_pct = abs(f.last_close - reference) / reference * 100.0
        return _clamp(100.0 - dist_pct * 20.0)  # within 0% -> 100; 5% away -> 0

    def _reward_risk(self, f: FeatureRecord, target: float) -> float:
        stop_dist = _NOMINAL_ATR_STOP_MULT * f.atr if f.atr > 0 else f.last_close * 0.02
        reward = target - f.last_close
        if stop_dist <= 0 or reward <= 0:
            return 0.0
        ratio = reward / stop_dist
        return _clamp(ratio / 2.0 * 100.0)  # 2:1 -> 100, 1:1 -> 50

    def _score(self, components: dict[str, float]) -> float:
        return quality_score(components, self.p.quality_weights)

    # ---- detection --------------------------------------------------------
    def detect(self, symbol: str, f: FeatureRecord, *, bars=None) -> list[CandidateSetup]:
        """The closed-taxonomy setup detectors. `bars` (open,high,low,close,volume causal arrays) is the M5
        buy-low seam: when supplied, the instrument-agnostic price-action core (score_buy_low) also runs and
        its archetype is emitted as a first-class candidate. bars=None (legacy callers) is byte-identical."""
        p = self.p
        out: list[CandidateSetup] = []
        uptrend = f.ema_fast > f.ema_slow and (math.isnan(f.sma_trend) or f.last_close >= f.sma_trend)

        def add(setup_type: str, reference: float, target: float):
            comps = {
                "trend_alignment": self._trend_alignment(f),
                "location": self._location(f, reference),
                "confirmation": self._confirmation(f),
                "reward_risk": self._reward_risk(f, target),
            }
            out.append(
                CandidateSetup(
                    symbol=symbol,
                    setup_type=setup_type,
                    direction="long",
                    entry_price=f.last_close,
                    atr=f.atr,
                    quality=self._score(comps),
                    quality_components=comps,
                    features=f.as_dict(),
                )
            )

        # 1. breakout_with_volume: new 20-bar high on a volume anomaly.
        if f.last_close > f.recent_high and f.vol_zscore >= p.vol_anomaly_zscore:
            add("breakout_with_volume", reference=f.recent_high,
                target=f.last_close + 2.0 * f.atr)

        # 2. pullback_in_uptrend: uptrend, price near VWAP, not overbought.
        if uptrend and f.vwap > 0 and abs(f.last_close - f.vwap) / f.vwap < 0.015 \
                and f.rsi < p.rsi_overbought:
            add("pullback_in_uptrend", reference=f.vwap, target=f.recent_high)

        # 3. range_reversion: chop (low ADX), oversold, near lower band.
        if f.adx < p.adx_trend_min and f.rsi < p.rsi_oversold \
                and f.last_close <= f.bb_lower * 1.005:
            add("range_reversion", reference=f.bb_lower, target=f.bb_mid)

        # 4. momentum_continuation: trending up with momentum.
        if f.adx >= p.adx_trend_min and f.ema_fast > f.ema_slow and f.rsi >= 50:
            add("momentum_continuation", reference=f.ema_fast,
                target=f.last_close + 2.0 * f.atr)

        # 5. relative_strength_leader: outperforming the benchmark in an uptrend.
        if f.rel_strength > 0 and uptrend and f.adx >= p.adx_trend_min:
            add("relative_strength_leader", reference=f.ema_slow,
                target=f.last_close + 2.0 * f.atr)

        # 6. BUY-LOW price-action CORE (M5): the instrument-agnostic supported_dip / early_wave archetypes.
        # Only when OHLCV arrays are supplied (backtest via engine.py, live via scan()/discovery). The SAME
        # score_buy_low() runs on every surface, so the backtest certifies the live discovery path (parity).
        # quality carries the core score on the 0-100 scale; support/core_stop feed the M6 exit engine.
        if bars is not None:
            sig = score_buy_low(*bars)
            if sig.passed and sig.archetype:
                feats = f.as_dict()
                feats.update({
                    "buy_low_score": round(sig.score, 4), "buy_low_archetype": sig.archetype,
                    "support": None if sig.support is None else round(sig.support, 6),
                    "core_stop": None if sig.stop is None else round(sig.stop, 6),
                    "core_target": None if sig.target is None else round(sig.target, 6),   # M6 sell-high level
                    "extension": None if sig.extension is None else round(sig.extension, 4),
                    "rsi2": None if sig.rsi2 is None else round(sig.rsi2, 4),
                })
                out.append(CandidateSetup(
                    symbol=symbol, setup_type=sig.archetype, direction="long",
                    entry_price=f.last_close, atr=f.atr, quality=round(sig.score * 100.0, 4),
                    quality_components={"buy_low_score": round(sig.score * 100.0, 4),
                                        "support_families": float(sig.support_families)},
                    features=feats))

        return out

    def scan(self, symbol: str, *, high, low, close, volume, open_, benchmark_close
             ) -> list[CandidateSetup]:
        """Full pipeline: features -> detect -> drop below min_quality_score / outside price_band, sorted desc."""
        f = self.compute_features(
            high=high, low=low, close=close, volume=volume, open_=open_,
            benchmark_close=benchmark_close,
        )
        p = self.p
        survivors = [
            c for c in self.detect(symbol, f, bars=(open_, high, low, close, volume))
            if c.quality >= p.min_quality_score
            and p.min_entry_price <= c.entry_price <= p.max_entry_price   # whole-share affordability gate
        ]
        return sorted(survivors, key=lambda c: c.quality, reverse=True)
