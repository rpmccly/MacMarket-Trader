"""Indicator package exports."""

from macmarket_trader.indicators.haco import (
    HacoPoint,
    MetastockHacoDebug,
    MetastockHacoResult,
    compute_haco_states,
    compute_metastock_haco,
    legacy_haco_ema_3_8,
    metastock_alert,
)
from macmarket_trader.indicators.haco_ha import compute_haco_from_ha
from macmarket_trader.indicators.hacolt import (
    HacoltPoint,
    ThinkorswimHacoltDebug,
    ThinkorswimHacoltResult,
    compute_hacolt_direction,
    compute_thinkorswim_hacolt,
    legacy_hacolt_ema_21_55,
)
from macmarket_trader.indicators.hilo_elite import (
    HiLoEliteConfig,
    HiLoElitePoint,
    HiLoEliteSeries,
    compute_hilo_elite,
)
from macmarket_trader.indicators.true_momentum import (
    TrueMomentumConfig,
    TrueMomentumPoint,
    TrueMomentumSeries,
    compute_true_momentum,
)
from macmarket_trader.indicators.true_momentum_score import (
    MomentumScoreComponentBreakdown,
    MomentumScorePoint,
    MomentumScoreSeries,
    compute_true_momentum_score,
)

__all__ = [
    "HacoPoint",
    "HacoltPoint",
    "MetastockHacoDebug",
    "MetastockHacoResult",
    "ThinkorswimHacoltDebug",
    "ThinkorswimHacoltResult",
    "compute_haco_states",
    "compute_metastock_haco",
    "compute_haco_from_ha",
    "compute_hacolt_direction",
    "compute_thinkorswim_hacolt",
    "legacy_haco_ema_3_8",
    "legacy_hacolt_ema_21_55",
    "metastock_alert",
    "HiLoEliteConfig",
    "HiLoElitePoint",
    "HiLoEliteSeries",
    "compute_hilo_elite",
    "TrueMomentumConfig",
    "TrueMomentumPoint",
    "TrueMomentumSeries",
    "compute_true_momentum",
    "MomentumScoreComponentBreakdown",
    "MomentumScorePoint",
    "MomentumScoreSeries",
    "compute_true_momentum_score",
]
