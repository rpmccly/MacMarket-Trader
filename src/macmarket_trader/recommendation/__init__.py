"""Recommendation-layer helpers (ranking influence, scoring contributions).

Phase B1 introduces the bounded Momentum Intelligence ranking contribution.
The helpers in this package are pure: they translate Momentum payloads into
typed, capped, audited score adjustments without ever approving, rejecting,
sizing, or routing trades. See ``docs/momentum-intelligence-layer.md``.
"""

from macmarket_trader.recommendation.momentum_ranking import (
    ACTIVE_DELTA_FORMULA_VERSION,
    DEFAULT_ACTIVE_DELTA_SCALE,
    MomentumRankingConfig,
    MomentumScoreConsistencyResult,
    RANKING_SCORE_CONSISTENCY_GUARD,
    apply_momentum_score_delta,
    build_momentum_ranking_contribution,
    build_momentum_ranking_status,
    enforce_score_consistency,
    momentum_ranking_config_from_settings,
    resolve_effective_momentum_ranking_mode,
    resolve_momentum_ranking_mode,
)

__all__ = [
    "ACTIVE_DELTA_FORMULA_VERSION",
    "DEFAULT_ACTIVE_DELTA_SCALE",
    "MomentumRankingConfig",
    "MomentumScoreConsistencyResult",
    "RANKING_SCORE_CONSISTENCY_GUARD",
    "apply_momentum_score_delta",
    "build_momentum_ranking_contribution",
    "build_momentum_ranking_status",
    "enforce_score_consistency",
    "momentum_ranking_config_from_settings",
    "resolve_effective_momentum_ranking_mode",
    "resolve_momentum_ranking_mode",
]
