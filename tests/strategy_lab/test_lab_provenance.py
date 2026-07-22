"""Lab-side provenance enforcement - the strategy-lab clone of tests/test_provenance_registry.py.

Laws enforced (registered lab-strategy-runtime-v1):
  1. Every field of every registered strategy's params dataclass has a provenance entry here
     citing its brief row (the reviewed, human-readable map; updating it is when the
     discipline fires).
  2. Every ARMED strategy has a sweep-ledger row `lab-strat-<id>-v1` whose machine-greppable
     `config_hash` field equals the LIVE config_hash (the 6c1dc2a4e1a7 lesson, per-strategy).
  3. The yaml cohort_pin equals the live hash (drift = cohort split without registration).
  4. Every registered strategy's brief exists and carries a VERIFICATION section with verdict
     CONFIRMED or CORRECTED (no strategy runs on an unverified brief).
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from atlas.strategy_lab.registry import build_all, load_state

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "runtime" / "backtest_out" / "sweep_ledger.jsonl"
BRIEFS = REPO / "docs" / "strategies" / "briefs"

# strategy_id -> {param_field: provenance string citing the brief row}
PARAMS_PROVENANCE = {
    'atm_calendar_low_iv': {
        'vix_pctile_max': 'brief docs/strategies/briefs/atm_calendar_low_iv.md §8 (vix_pctile_max) - row-level provenance in the module docstring',
        'front_dte_min': 'brief docs/strategies/briefs/atm_calendar_low_iv.md §8 (front_dte_min) - row-level provenance in the module docstring',
        'front_dte_max': 'brief docs/strategies/briefs/atm_calendar_low_iv.md §8 (front_dte_max) - row-level provenance in the module docstring',
        'back_dte_min': 'brief docs/strategies/briefs/atm_calendar_low_iv.md §8 (back_dte_min) - row-level provenance in the module docstring',
        'back_dte_max': 'brief docs/strategies/briefs/atm_calendar_low_iv.md §8 (back_dte_max) - row-level provenance in the module docstring',
        'front_exit_trading_days': 'brief docs/strategies/briefs/atm_calendar_low_iv.md §8 (front_exit_trading_days) - row-level provenance in the module docstring',
    },
    'backspread_1x2': {
        'sell_delta_target': 'brief §3 SOURCE (McMillan p.842) - short ~0.40Δ leg (2:1 delta ratio)',
        'buy_delta_target': 'brief §3 SOURCE (McMillan p.842) - long ~0.20Δ leg (2:1 delta ratio)',
        'min_net_credit': 'brief §3 THE DEFINING GATE SOURCE-VERBATIM - net premium >= 0 (McMillan p.233/240)',
        'vix_pctile_max': 'brief §3 low-IV gate ADAPTED (McMillan p.841 low-percentile; no number published)',
        'trend_sma_days': 'brief §3 direction proxy ADAPTED (source trigger qualitative)',
        'dte_min_days': 'brief §8 ADAPTED - 45-75 DTE (none published)',
        'dte_max_days': 'brief §8 ADAPTED - 45-75 DTE (none published)',
        'history_days': 'PLATFORM-POLICY - window for the trend SMA',
        'ea_extrinsic_max': 'brief §4 X5 ADAPTED - /usr/bin/bash.05 extrinsic (trigger published, number ours)',
        'ea_dte': 'brief §4 X5 ADAPTED - 5 DTE (trigger published, number ours)',
        'entry_minute_from': 'PLATFORM-POLICY scan window',
        'entry_minute_to': 'PLATFORM-POLICY scan window',
    },
    'cndr_iron_condor_hold': {
        'short_delta': 'brief docs/strategies/briefs/cndr_iron_condor_hold.md §8 (short_delta) - row-level provenance in the module docstring',
        'wing_delta': 'brief docs/strategies/briefs/cndr_iron_condor_hold.md §8 (wing_delta) - row-level provenance in the module docstring',
        'entry_minute_from': 'brief docs/strategies/briefs/cndr_iron_condor_hold.md §8 (entry_minute_from) - row-level provenance in the module docstring',
        'entry_minute_to': 'brief docs/strategies/briefs/cndr_iron_condor_hold.md §8 (entry_minute_to) - row-level provenance in the module docstring',
        'dte_min_days': 'brief docs/strategies/briefs/cndr_iron_condor_hold.md §8 (dte_min_days) - row-level provenance in the module docstring',
        'dte_max_days': 'brief docs/strategies/briefs/cndr_iron_condor_hold.md §8 (dte_max_days) - row-level provenance in the module docstring',
        'monthly_tolerance_days': 'brief docs/strategies/briefs/cndr_iron_condor_hold.md §8 (monthly_tolerance_days) - row-level provenance in the module docstring',
    },
    'donchian_breakout_debit_vert': {
        'entry_channel_days': 'brief E1/E-TRIG SOURCE-VERBATIM - 20-day breakout (Ch.4 p.19)',
        'failsafe_channel_days': 'brief E3 SOURCE-VERBATIM - 55-day Failsafe (Ch.4 p.19)',
        'exit_channel_days': 'brief X1 SOURCE-VERBATIM - 10-day opposite channel (Ch.6 p.26)',
        'atr_days': 'brief N SOURCE-VERBATIM - 20-day Wilder ATR (Ch.3)',
        'stop_atr_mult': 'brief X2 SOURCE-VERBATIM - 2N stop (Ch.5)',
        'short_offset_atr_mult': 'brief strike-selection ADAPTED - short at entry±2N (2N is the source distance)',
        'roll_dte': 'brief X4 ADAPTED - 21 DTE (a few weeks before expiration, Ch.7)',
        'dte_min_days': 'brief §8 ADAPTED - 45-75 (anchored to 43-day avg winner)',
        'dte_max_days': 'brief §8 ADAPTED - 45-75 (anchored to 43-day avg winner)',
        'history_days': 'PLATFORM-POLICY - window for 55d channel + E2 look-back',
        'entry_minute_from': 'PLATFORM-POLICY scan window (intraday, E4)',
        'entry_minute_to': 'PLATFORM-POLICY scan window (intraday, E4)',
    },
    'earnings_iv_crush_strangle': {
        'target_abs_delta': 'brief docs/strategies/briefs/earnings_iv_crush_strangle.md §8 (target_abs_delta) - row-level provenance in the module docstring',
        'entry_minute_from': 'brief docs/strategies/briefs/earnings_iv_crush_strangle.md §8 (entry_minute_from) - row-level provenance in the module docstring',
        'entry_minute_to': 'brief docs/strategies/briefs/earnings_iv_crush_strangle.md §8 (entry_minute_to) - row-level provenance in the module docstring',
        'exit_minute_from': 'brief docs/strategies/briefs/earnings_iv_crush_strangle.md §8 (exit_minute_from) - row-level provenance in the module docstring',
        'dte_min_days': 'brief docs/strategies/briefs/earnings_iv_crush_strangle.md §8 (dte_min_days) - row-level provenance in the module docstring',
        'dte_max_days': 'brief docs/strategies/briefs/earnings_iv_crush_strangle.md §8 (dte_max_days) - row-level provenance in the module docstring',
    },
    'gap_fade_bull_put': {
        'gap_min_pct': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (gap_min_pct) - row-level provenance in the module docstring',
        'gap_max_pct': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (gap_max_pct) - row-level provenance in the module docstring',
        'entry_minute_from': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (entry_minute_from) - row-level provenance in the module docstring',
        'entry_minute_to': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (entry_minute_to) - row-level provenance in the module docstring',
        'dte_min_days': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (dte_min_days) - row-level provenance in the module docstring',
        'dte_max_days': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (dte_max_days) - row-level provenance in the module docstring',
        'short_delta_cap': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (short_delta_cap) - row-level provenance in the module docstring',
        'width_strikes': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (width_strikes) - row-level provenance in the module docstring',
        'credit_floor_frac': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (credit_floor_frac) - row-level provenance in the module docstring',
        'expiry_force_minute': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (expiry_force_minute) - row-level provenance in the module docstring',
        'expiry_buffer_pct': 'brief docs/strategies/briefs/gap_fade_bull_put.md §8 (expiry_buffer_pct) - row-level provenance in the module docstring',
    },
    'ic_45d16d_managed': {
        'entry_dte_target': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (entry_dte_target) - row-level provenance in the module docstring',
        'entry_dte_min': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (entry_dte_min) - row-level provenance in the module docstring',
        'entry_dte_max': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (entry_dte_max) - row-level provenance in the module docstring',
        'short_delta': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (short_delta) - row-level provenance in the module docstring',
        'delta_band_lo': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (delta_band_lo) - row-level provenance in the module docstring',
        'delta_band_hi': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (delta_band_hi) - row-level provenance in the module docstring',
        'credit_target_frac': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (credit_target_frac) - row-level provenance in the module docstring',
        'credit_floor_frac': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (credit_floor_frac) - row-level provenance in the module docstring',
        'wing_width_cap': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (wing_width_cap) - row-level provenance in the module docstring',
        'profit_take_frac': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (profit_take_frac) - row-level provenance in the module docstring',
        'time_exit_dte': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (time_exit_dte) - row-level provenance in the module docstring',
        'entry_minute_from': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (entry_minute_from) - row-level provenance in the module docstring',
        'entry_minute_to': 'brief docs/strategies/briefs/ic_45d16d_managed.md §8 (entry_minute_to) - row-level provenance in the module docstring',
    },
    'jade_lizard': {
        'dte_target': 'brief docs/strategies/briefs/jade_lizard.md §8 (dte_target) - row-level provenance in the module docstring',
        'dte_min': 'brief docs/strategies/briefs/jade_lizard.md §8 (dte_min) - row-level provenance in the module docstring',
        'dte_max': 'brief docs/strategies/briefs/jade_lizard.md §8 (dte_max) - row-level provenance in the module docstring',
        'put_delta_target': 'brief docs/strategies/briefs/jade_lizard.md §8 (put_delta_target) - row-level provenance in the module docstring',
        'put_delta_min': 'brief docs/strategies/briefs/jade_lizard.md §8 (put_delta_min) - row-level provenance in the module docstring',
        'put_delta_max': 'brief docs/strategies/briefs/jade_lizard.md §8 (put_delta_max) - row-level provenance in the module docstring',
        'call_delta_target': 'brief docs/strategies/briefs/jade_lizard.md §8 (call_delta_target) - row-level provenance in the module docstring',
        'call_delta_min': 'brief docs/strategies/briefs/jade_lizard.md §8 (call_delta_min) - row-level provenance in the module docstring',
        'call_delta_max': 'brief docs/strategies/briefs/jade_lizard.md §8 (call_delta_max) - row-level provenance in the module docstring',
        'min_width_pct_of_spot': 'brief docs/strategies/briefs/jade_lizard.md §8 (min_width_pct_of_spot) - row-level provenance in the module docstring',
        'iv_gate_pctile': 'brief docs/strategies/briefs/jade_lizard.md §8 (iv_gate_pctile) - row-level provenance in the module docstring',
        'regime_max_age_days': 'brief docs/strategies/briefs/jade_lizard.md §8 (regime_max_age_days) - row-level provenance in the module docstring',
        'profit_take_frac': 'brief docs/strategies/briefs/jade_lizard.md §8 (profit_take_frac) - row-level provenance in the module docstring',
        'manage_dte': 'brief docs/strategies/briefs/jade_lizard.md §8 (manage_dte) - row-level provenance in the module docstring',
    },
    'overnight_1dte_strangle': {
        'entry_lead_min': 'brief row 7 + §9 SOURCE-RANGE - last 15 min before session close (3:45-4:00 ET snapshot)',
        'delta_target': 'brief row 4 ADAPTED - nearest |Δ|=0.25 (boundary of the published 0.1<|Δ|<0.25 bucket)',
        'delta_band_lo': 'brief row 5 PLATFORM-POLICY - accept 0.15<=|Δ|<=0.30 else skip the symbol that night',
        'delta_band_hi': 'brief row 5 PLATFORM-POLICY - accept 0.15<=|Δ|<=0.30 else skip the symbol that night',
        'exit_minute_from': 'brief row 11 SOURCE-VERBATIM - buy back at next open 9:30 ET (first snapshot 9:30-9:35)',
    },
    'pre_earnings_long_straddle': {
        'entry_offset_sessions': 'brief §3 SOURCE-VERBATIM - buy on day -3 (T-3 trading days)',
        'entry_minute_from': 'brief §3 ADAPTED - closing-midpoint window (no wall time published)',
        'entry_minute_to': 'brief §3 ADAPTED - closing-midpoint window',
        'exit_minute_from': 'brief §4 ADAPTED - T-1 close window',
        'abs_delta_lo': 'brief filter 6 SOURCE-VERBATIM - |delta| >= 0.375',
        'abs_delta_hi': 'brief filter 6 SOURCE-VERBATIM - |delta| <= 0.625',
        'moneyness_lo': 'brief filter 7 SOURCE-VERBATIM - moneyness >= 0.9',
        'moneyness_hi': 'brief filter 7 SOURCE-VERBATIM - moneyness <= 1.1',
        'min_option_price': 'brief filter 1 SOURCE-VERBATIM - option price >= $0.125',
        'dte_min_days': 'brief filter 5 SOURCE-VERBATIM - 10 days to maturity min',
        'dte_max_days': 'brief filter 5 SOURCE-VERBATIM - 60 days to maturity max',
    },
    'pre_fomc_drift_call': {
        'entry_lead_min': 'brief rows 2/3 SOURCE-VERBATIM - window start = announcement-24h15m (1455min); 13:45 ET T-1 for a 14:00 release',
        'entry_window_min': 'ADAPTED - scan-cadence tolerance after the derived start; never enters before the published window',
        'exit_lead_min': "brief row 4 SOURCE-VERBATIM 'selling fifteen minutes before the announcement'",
        'strike_rule': 'brief row 11 ADAPTED - nearest listed strike to spot (ATM); UNKNOWN in source (no options traded)',
    },
    'rsi2_overbought_bear_call': {
        'eval_minute_from': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (eval_minute_from) - row-level provenance in the module docstring',
        'eval_minute_to': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (eval_minute_to) - row-level provenance in the module docstring',
        'rsi_period': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (rsi_period) - row-level provenance in the module docstring',
        'entry_rsi_threshold': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (entry_rsi_threshold) - row-level provenance in the module docstring',
        'sma_trend_days': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (sma_trend_days) - row-level provenance in the module docstring',
        'sma_exit_days': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (sma_exit_days) - row-level provenance in the module docstring',
        'min_history_days': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (min_history_days) - row-level provenance in the module docstring',
        'dte_min_days': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (dte_min_days) - row-level provenance in the module docstring',
        'dte_max_days': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (dte_max_days) - row-level provenance in the module docstring',
        'width_frac_of_spot': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (width_frac_of_spot) - row-level provenance in the module docstring',
        'width_floor_usd': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (width_floor_usd) - row-level provenance in the module docstring',
        'min_credit_frac_of_width': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (min_credit_frac_of_width) - row-level provenance in the module docstring',
        'max_spread_frac_of_mid': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (max_spread_frac_of_mid) - row-level provenance in the module docstring',
        'min_open_interest': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (min_open_interest) - row-level provenance in the module docstring',
        'force_close_dte': 'brief docs/strategies/briefs/rsi2_overbought_bear_call.md §8 (force_close_dte) - row-level provenance in the module docstring',
    },
    'rsi2_oversold_short_put': {
        'rsi_period': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (rsi_period) - row-level provenance in the module docstring',
        'entry_rsi_threshold': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (entry_rsi_threshold) - row-level provenance in the module docstring',
        'exit_rsi_threshold': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (exit_rsi_threshold) - row-level provenance in the module docstring',
        'trend_sma_days': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (trend_sma_days) - row-level provenance in the module docstring',
        'entry_minute_from': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (entry_minute_from) - row-level provenance in the module docstring',
        'entry_minute_to': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (entry_minute_to) - row-level provenance in the module docstring',
        'delta_target': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (delta_target) - row-level provenance in the module docstring',
        'delta_band_lo': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (delta_band_lo) - row-level provenance in the module docstring',
        'delta_band_hi': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (delta_band_hi) - row-level provenance in the module docstring',
        'dte_min_days': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (dte_min_days) - row-level provenance in the module docstring',
        'dte_max_days': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (dte_max_days) - row-level provenance in the module docstring',
        'earnings_gate_days': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (earnings_gate_days) - row-level provenance in the module docstring',
        'history_days': 'brief docs/strategies/briefs/rsi2_oversold_short_put.md §8 (history_days) - row-level provenance in the module docstring',
    },
    'short_put_45d30d_managed': {
        'dte_target': "brief row 3 SOURCE-VERBATIM 'closest to 45 days to expiration' (MM 2015-09-01)",
        'dte_band_min': "brief row 4 SOURCE-RANGE 'trades between 30-60 days' (projectoption)",
        'dte_band_max': "brief row 4 SOURCE-RANGE 'trades between 30-60 days' (projectoption)",
        'delta_target': "brief row 7 SOURCE-RANGE - house default 'Sell options with a 30 delta.'",
        'delta_tolerance': "brief row 8 SOURCE-VERBATIM '30 delta +/- 3.5 delta, closest to 30'",
        'profit_target_frac': "brief row 14 SOURCE-VERBATIM 'exiting at 50% of max profit'",
        'time_exit_dte': "brief row 15 SOURCE-VERBATIM 'we exit trades at 21 DTE'",
    },
    'squeeze_long_straddle': {
        'bb_period': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (bb_period) - row-level provenance in the module docstring',
        'bb_stdev': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (bb_stdev) - row-level provenance in the module docstring',
        'squeeze_lookback_days': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (squeeze_lookback_days) - row-level provenance in the module docstring',
        'dte_min_days': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (dte_min_days) - row-level provenance in the module docstring',
        'dte_max_days': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (dte_max_days) - row-level provenance in the module docstring',
        'dte_target_days': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (dte_target_days) - row-level provenance in the module docstring',
        'no_expansion_exit_sessions': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (no_expansion_exit_sessions) - row-level provenance in the module docstring',
        'sar_step': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (sar_step) - row-level provenance in the module docstring',
        'sar_max_af': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (sar_max_af) - row-level provenance in the module docstring',
        'dte_floor_exit': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (dte_floor_exit) - row-level provenance in the module docstring',
        'rearm_quartile': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (rearm_quartile) - row-level provenance in the module docstring',
        'earnings_gate_days': 'brief docs/strategies/briefs/squeeze_long_straddle.md §8 (earnings_gate_days) - row-level provenance in the module docstring',
    },
    'strangle_45d16d_managed': {
        'dte_target': "brief row 2 'around 45 days to expiration' - SOURCE-RANGE",
        'dte_min': 'brief row 3 entry band lower bound 35 (PLATFORM-POLICY)',
        'dte_max': 'brief row 3 band top 55 narrowed to 50 per META dte_range pin (PLATFORM-POLICY)',
        'target_abs_delta': "brief rows 4/5 SOURCE-VERBATIM 'Sell the 16 delta of the call and put'; nearest-strike row 6",
        'ivr_gate_pctile': 'brief rows 7/9 ADAPTED - IVR>=50 via VIX 252d-percentile fallback, strict >',
        'profit_take_frac': "brief row 10 SOURCE-VERBATIM 'buying the strangle back for 50% of the credit'",
        'time_exit_dte': 'brief row 11 SOURCE-VERBATIM - close at 21 DTE',
        'loss_multiple_credit': 'brief row 12 SOURCE-RANGE - net loss >= 2x credit (house convention; alt reading logged)',
    },
    'tsmom_long_options': {
        'lookback_days': 'brief docs/strategies/briefs/tsmom_long_options.md §8 (lookback_days) - row-level provenance in the module docstring',
        'entry_minute_from': 'brief docs/strategies/briefs/tsmom_long_options.md §8 (entry_minute_from) - row-level provenance in the module docstring',
        'entry_minute_to': 'brief docs/strategies/briefs/tsmom_long_options.md §8 (entry_minute_to) - row-level provenance in the module docstring',
        'dte_entry_min': 'brief docs/strategies/briefs/tsmom_long_options.md §8 (dte_entry_min) - row-level provenance in the module docstring',
        'dte_entry_max': 'brief docs/strategies/briefs/tsmom_long_options.md §8 (dte_entry_max) - row-level provenance in the module docstring',
        'dte_target': 'brief docs/strategies/briefs/tsmom_long_options.md §8 (dte_target) - row-level provenance in the module docstring',
        'history_days': 'brief docs/strategies/briefs/tsmom_long_options.md §8 (history_days) - row-level provenance in the module docstring',
    },
    'vrp_short_straddle': {
        'dte_target': 'brief docs/strategies/briefs/vrp_short_straddle.md §8 (dte_target) - row-level provenance in the module docstring',
        'dte_min': 'brief docs/strategies/briefs/vrp_short_straddle.md §8 (dte_min) - row-level provenance in the module docstring',
        'dte_max': 'brief docs/strategies/briefs/vrp_short_straddle.md §8 (dte_max) - row-level provenance in the module docstring',
        'moneyness_lo': 'brief docs/strategies/briefs/vrp_short_straddle.md §8 (moneyness_lo) - row-level provenance in the module docstring',
        'moneyness_hi': 'brief docs/strategies/briefs/vrp_short_straddle.md §8 (moneyness_hi) - row-level provenance in the module docstring',
        'hv_lookback_td': 'brief docs/strategies/briefs/vrp_short_straddle.md §8 (hv_lookback_td) - row-level provenance in the module docstring',
        'profit_target_frac': 'brief docs/strategies/briefs/vrp_short_straddle.md §8 (profit_target_frac) - row-level provenance in the module docstring',
        'stop_loss_mult': 'brief docs/strategies/briefs/vrp_short_straddle.md §8 (stop_loss_mult) - row-level provenance in the module docstring',
    },
    'wput_weekly_putwrite': {
        'entry_minute_from': "brief row 9 'final minutes before 4:00 p.m. ET' - ADAPTED minute bound (PM branch)",
        'entry_minute_to': 'brief row 9 - 16:00 ET hard end of the PM entry window',
        'dte_min_days': 'brief row 5 derived 6-8 cal days, widened -1 as listing tolerance (PLATFORM-POLICY)',
        'dte_max_days': 'brief row 5 derived 6-8 cal days, widened +1 as listing tolerance (PLATFORM-POLICY)',
    },
    'zero_dte_morning_ic': {
        'entry_minute_from': 'brief docs/strategies/briefs/zero_dte_morning_ic.md §8 (entry_minute_from) - row-level provenance in the module docstring',
        'entry_minute_to': 'brief docs/strategies/briefs/zero_dte_morning_ic.md §8 (entry_minute_to) - row-level provenance in the module docstring',
        'short_delta': 'brief docs/strategies/briefs/zero_dte_morning_ic.md §8 (short_delta) - row-level provenance in the module docstring',
        'wing_pct_of_spot': 'brief docs/strategies/briefs/zero_dte_morning_ic.md §8 (wing_pct_of_spot) - row-level provenance in the module docstring',
        'min_credit_per_side': 'brief docs/strategies/briefs/zero_dte_morning_ic.md §8 (min_credit_per_side) - row-level provenance in the module docstring',
        'min_oi_per_leg': 'brief docs/strategies/briefs/zero_dte_morning_ic.md §8 (min_oi_per_leg) - row-level provenance in the module docstring',
        'max_spread_frac_of_mid': 'brief docs/strategies/briefs/zero_dte_morning_ic.md §8 (max_spread_frac_of_mid) - row-level provenance in the module docstring',
        'stop_credit_multiple': 'brief docs/strategies/briefs/zero_dte_morning_ic.md §8 (stop_credit_multiple) - row-level provenance in the module docstring',
    },
}


def _require_ledger():
    """Skip when the operator's sweep ledger is absent.

    The ledger lives under runtime/, which is machine-local operational state and is
    not part of the source tree. Tests that cross-check live registrations against it
    are canaries for a running deployment, so on a fresh clone they skip rather than
    fail. Every test that only needs the code itself still runs.
    """
    if not LEDGER.exists():
        pytest.skip(f"no sweep ledger at {LEDGER.relative_to(REPO)} (runtime state is machine-local)")


def _ledger_rows():
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def test_every_params_field_has_provenance():
    strategies = build_all()
    for sid, strat in strategies.items():
        assert sid in PARAMS_PROVENANCE, f"{sid}: no provenance map - add it with brief rows"
        prov = PARAMS_PROVENANCE[sid]
        if strat.params is None:
            assert prov == {}, f"{sid}: provenance entries for a paramless strategy"
            continue
        fields = {f.name for f in dataclasses.fields(strat.params)}
        missing = fields - set(prov)
        stale = set(prov) - fields
        assert not missing, f"{sid}: params without provenance: {sorted(missing)}"
        assert not stale, f"{sid}: provenance for absent params: {sorted(stale)}"


def test_armed_strategies_have_registration_rows_with_live_hash():
    _require_ledger()
    strategies = build_all()
    state = load_state()
    rows = {r.get("config_id"): r for r in _ledger_rows()}
    for sid, strat in strategies.items():
        if state.get(sid, {}).get("state") != "armed":
            continue
        rid = f"lab-strat-{sid}-v1"
        assert rid in rows, f"{sid} is ARMED without sweep-ledger row {rid}"
        row_hash = rows[rid].get("config_hash")
        assert row_hash == strat.config_hash(), \
            f"{sid}: ledger hash {row_hash} != live {strat.config_hash()} - params changed " \
            f"without a new registration (cohort split)"


def test_yaml_cohort_pin_matches_live_hash():
    strategies = build_all()
    state = load_state()
    for sid, block in state.items():
        if block.get("state") != "armed" or sid not in strategies:
            continue
        assert block.get("cohort_pin") == strategies[sid].config_hash(), \
            f"{sid}: yaml cohort_pin {block.get('cohort_pin')} != live hash"


def test_registered_strategies_have_verified_briefs():
    for sid in build_all():
        brief = BRIEFS / f"{sid}.md"
        assert brief.exists(), f"{sid}: no brief at {brief}"
        text = brief.read_text(encoding="utf-8")
        m = re.search(r"Verdict:\s*(CONFIRMED|CORRECTED)", text)
        assert m, f"{sid}: brief lacks a CONFIRMED/CORRECTED verification verdict"


def test_infrastructure_registration_exists():
    _require_ledger()
    ids = {r.get("config_id") for r in _ledger_rows()}
    assert "lab-strategy-runtime-v1" in ids
