"""Recommendation-layer helpers (ranking influence, scoring contributions).

Phase B1 introduces the bounded Momentum Intelligence ranking contribution.
The helpers in this package are pure: they translate Momentum payloads into
typed, capped, audited score adjustments without ever approving, rejecting,
sizing, or routing trades. See ``docs/momentum-intelligence-layer.md``.
"""

from macmarket_trader.recommendation.momentum_ranking import (
    DEFAULT_ACTIVE_DELTA_SCALE,
    MomentumRankingConfig,
    apply_momentum_score_delta,
    build_momentum_ranking_contribution,
    build_momentum_ranking_status,
    momentum_ranking_config_from_settings,
    resolve_effective_momentum_ranking_mode,
    resolve_momentum_ranking_mode,
)

__all__ = [
    "DEFAULT_ACTIVE_DELTA_SCALE",
    "MomentumRankingConfig",
    "apply_momentum_score_delta",
    "build_momentum_ranking_contribution",
    "build_momentum_ranking_status",
    "momentum_ranking_config_from_settings",
    "resolve_effective_momentum_ranking_mode",
    "resolve_momentum_ranking_mode",
]
