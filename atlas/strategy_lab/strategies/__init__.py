"""Strategy factory registry - one module per strategy, registered here.

Each strategy module implements the FROZEN spec from its VERIFIED brief
(docs/strategies/briefs/<id>.md, §11 verification CONFIRMED/CORRECTED) and registers its
factory below. An entry here does NOT arm the strategy - arming additionally requires state
`armed` in config/strategy_lab.yaml AND a lab-strat-<id>-v1 sweep-ledger row with its
config_hash (enforced by tests/strategy_lab/test_lab_provenance.py).

Mission 20260719-strategy-lab. All 20 slate strategies implemented from verified briefs
(2026-07-20).
"""

from __future__ import annotations

from .atm_calendar_low_iv import AtmCalendarLowIv
from .backspread_1x2 import Backspread1x2
from .cndr_iron_condor_hold import CndrIronCondorHold
from .donchian_breakout_debit_vert import DonchianBreakoutDebitVert
from .earnings_iv_crush_strangle import EarningsIvCrushStrangle
from .gap_fade_bull_put import GapFadeBullPut
from .ic_45d16d_managed import Ic45d16dManaged
from .jade_lizard import JadeLizard
from .overnight_1dte_strangle import Overnight1dteStrangle
from .pre_earnings_long_straddle import PreEarningsLongStraddle
from .pre_fomc_drift_call import PreFomcDriftCall
from .rsi2_overbought_bear_call import Rsi2OverboughtBearCall
from .rsi2_oversold_short_put import Rsi2OversoldShortPut
from .short_put_45d30d_managed import ShortPut45D30DManaged
from .squeeze_long_straddle import SqueezeLongStraddle
from .strangle_45d16d_managed import Strangle45D16DManaged
from .tsmom_long_options import TsmomLongOptions
from .vrp_short_straddle import VrpShortStraddle
from .wput_weekly_putwrite import WputWeeklyPutWrite
from .zero_dte_morning_ic import ZeroDteMorningIc

STRATEGY_FACTORIES: dict = {
    "atm_calendar_low_iv": AtmCalendarLowIv,
    "backspread_1x2": Backspread1x2,
    "cndr_iron_condor_hold": CndrIronCondorHold,
    "donchian_breakout_debit_vert": DonchianBreakoutDebitVert,
    "earnings_iv_crush_strangle": EarningsIvCrushStrangle,
    "gap_fade_bull_put": GapFadeBullPut,
    "ic_45d16d_managed": Ic45d16dManaged,
    "jade_lizard": JadeLizard,
    "overnight_1dte_strangle": Overnight1dteStrangle,
    "pre_earnings_long_straddle": PreEarningsLongStraddle,
    "pre_fomc_drift_call": PreFomcDriftCall,
    "rsi2_overbought_bear_call": Rsi2OverboughtBearCall,
    "rsi2_oversold_short_put": Rsi2OversoldShortPut,
    "short_put_45d30d_managed": ShortPut45D30DManaged,
    "squeeze_long_straddle": SqueezeLongStraddle,
    "strangle_45d16d_managed": Strangle45D16DManaged,
    "tsmom_long_options": TsmomLongOptions,
    "vrp_short_straddle": VrpShortStraddle,
    "wput_weekly_putwrite": WputWeeklyPutWrite,
    "zero_dte_morning_ic": ZeroDteMorningIc,
}
