"""Phase B1 unit tests for ``build_momentum_ranking_contribution``.

These tests pin the bounded, audited Momentum Intelligence ranking
contribution against the rules in ``docs/momentum-intelligence-layer.md``:

- ``off`` mode never computes a contribution.
- ``shadow`` mode computes a contribution but never applies it.
- ``active`` mode applies the bounded contribution.
- Contributions are clamped, never NaN/inf.
- Reason codes surface parity-pending, derived-HTF, no-trade, reversal,
  pullback, and direction-unknown signals.
- The function never approves, rejects, sizes, or routes trades.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from macmarket_trader.domain.schemas import (
    MomentumChartExplanation,
    MomentumChartPayload,
    MomentumComponentBreakdownPayload,
    MomentumScoreSnapshot,
)
from macmarket_trader.recommendation.momentum_ranking import (
    MomentumRankingConfig,
    build_momentum_ranking_contribution,
    resolve_momentum_ranking_mode,
)


def _snapshot(
    *,
    total_score: int = 90,
    total_label: str = "Bull",
    total_state: str = "bull",
    trend_score: float = 75.0,
    momo_score: float = 70.0,
    hilo_thrust: int = 1,
    hilo_score: int = 15,
) -> MomentumScoreSnapshot:
    return MomentumScoreSnapshot(
        total_score=total_score,
        total_label=total_label,
        total_state=total_state,
        trend_score=trend_score,
        momo_score=momo_score,
        true_momentum=65.5,
        true_momentum_ema=60.1,
        true_momentum_score=15,
        hilo_thrust=hilo_thrust,
        hilo_score=hilo_score,
        atr_bias=5,
        macd_bias=5,
        ma_bias=30,
        component_breakdown=MomentumComponentBreakdownPayload(
            true_momentum_score=15,
            hilo_thrust=hilo_score,
            bull_ma=30,
            bear_ma=0,
            atr_value=5,
            macd_bias=5,
            intraday_penalty=0,
            base_score=60,
        ),
    )


def _payload(
    snap: MomentumScoreSnapshot | None = None,
    *,
    reversal_warning: bool = False,
    pullback_signal: bool = False,
    no_trade_warning: bool = False,
    parity_status: str = "pending_thinkorswim_fixture_validation",
    higher_timeframe_source: str = "derived_from_chart_bars",
) -> MomentumChartPayload:
    s = snap or _snapshot()
    explanation = MomentumChartExplanation(
        snapshot=s,
        reversal_warning=reversal_warning,
        pullback_signal=pullback_signal,
        no_trade_warning=no_trade_warning,
        notes=[],
    )
    return MomentumChartPayload(
        symbol="AAPL",
        timeframe="1D",
        candles=[],
        true_momentum_line=[],
        true_momentum_ema_line=[],
        hilo_slowd_line=[],
        hilo_slowd_x_line=[],
        hilo_thrust_strip=[],
        score_strip=[],
        markers=[],
        latest_snapshot=s,
        explanation=explanation,
        data_source="polygon",
        fallback_mode=False,
        higher_timeframe_source=higher_timeframe_source,
        higher_timeframe="weekly",
        parity_status=parity_status,
        calculation_notes=[],
    )


# ── Mode behavior ──────────────────────────────────────────────────────────


def test_off_mode_returns_disabled_contribution() -> None:
    config = MomentumRankingConfig(mode="off")
    out = build_momentum_ranking_contribution(_payload(), {"direction": "long"}, config)
    assert out.mode == "off"
    assert out.enabled is False
    assert out.applied is False
    assert out.total_contribution == 0.0
    assert out.shadow_contribution == 0.0


def test_shadow_mode_computes_but_does_not_apply() -> None:
    config = MomentumRankingConfig(mode="shadow")
    out = build_momentum_ranking_contribution(_payload(), {"direction": "long"}, config)
    assert out.mode == "shadow"
    assert out.enabled is True
    assert out.applied is False
    assert out.total_contribution == 0.0  # shadow never applies
    assert out.shadow_contribution > 0  # but still computes a positive number for bull-aligned long


def test_active_mode_applies_when_direction_known() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(_payload(), {"direction": "long"}, config)
    assert out.mode == "active"
    assert out.enabled is True
    assert out.applied is True
    assert out.total_contribution > 0
    assert out.total_contribution == out.shadow_contribution


def test_active_mode_with_unknown_direction_does_not_apply() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(_payload(), {}, config)
    assert out.applied is False
    assert out.total_contribution == 0.0
    assert "direction_unknown" in out.reason_codes


# ── Component bounds ───────────────────────────────────────────────────────


def test_max_bull_aligned_long_caps_at_total_cap() -> None:
    config = MomentumRankingConfig(mode="active")
    snap = _snapshot(
        total_score=130,
        total_label="Max Bull",
        total_state="max_bull",
        trend_score=130.0,
        momo_score=130.0,
        hilo_score=20,
    )
    out = build_momentum_ranking_contribution(_payload(snap), {"direction": "long"}, config)
    # 10 (momentum) + 8 (trend) + 5 (hilo) = 23 raw → clamped to 20.
    assert out.shadow_contribution == pytest.approx(config.max_total_contribution)
    assert out.total_contribution == pytest.approx(config.max_total_contribution)


def test_max_bear_aligned_short_caps_at_total_cap() -> None:
    config = MomentumRankingConfig(mode="active")
    snap = _snapshot(
        total_score=-130,
        total_label="Max Bear",
        total_state="max_bear",
        trend_score=-130.0,
        momo_score=-130.0,
        hilo_score=-20,
    )
    out = build_momentum_ranking_contribution(_payload(snap), {"direction": "short"}, config)
    assert out.shadow_contribution == pytest.approx(config.max_total_contribution)
    assert out.applied is True


def test_bear_momentum_opposed_to_long_recommendation_yields_no_positive_contribution() -> None:
    config = MomentumRankingConfig(mode="active")
    snap = _snapshot(total_label="Bear", total_state="bear", total_score=-90, trend_score=-80, hilo_score=-15)
    out = build_momentum_ranking_contribution(_payload(snap), {"direction": "long"}, config)
    assert out.momentum_alignment_score == 0.0
    assert out.trend_alignment_score == 0.0
    assert out.hilo_confirmation_bonus == 0.0
    assert out.shadow_contribution == 0.0
    assert out.applied is False


def test_reversal_warning_applies_full_penalty_capped_to_floor() -> None:
    config = MomentumRankingConfig(mode="active")
    snap = _snapshot(total_label="Neutral Up", total_state="neutral_up", trend_score=10.0, hilo_score=2)
    out = build_momentum_ranking_contribution(
        _payload(snap, reversal_warning=True),
        {"direction": "long"},
        config,
    )
    assert out.reversal_warning is True
    assert out.reversal_warning_penalty == -config.max_reversal_warning_penalty
    assert "momentum_reversal_warning" in out.reason_codes
    assert out.shadow_contribution >= config.min_total_contribution
    # Combined: small positive + (-12) reversal must clamp into [floor, cap].
    assert config.min_total_contribution <= out.shadow_contribution <= config.max_total_contribution


def test_no_trade_warning_does_not_reject_but_suppresses_positive() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(no_trade_warning=True),
        {"direction": "long"},
        config,
    )
    assert "momentum_no_trade_warning" in out.reason_codes
    assert out.no_trade_warning is True
    # Positive contributions are suppressed but the function does not raise
    # or hard-reject — applied may be False because total goes to 0.
    assert out.shadow_contribution <= 0.0


# ── Reason codes ──────────────────────────────────────────────────────────


def test_pending_parity_adds_reason_code() -> None:
    config = MomentumRankingConfig(mode="shadow")
    out = build_momentum_ranking_contribution(
        _payload(parity_status="pending_thinkorswim_fixture_validation"),
        {"direction": "long"},
        config,
    )
    assert "thinkorswim_parity_pending" in out.reason_codes


def test_validated_parity_does_not_add_pending_code() -> None:
    config = MomentumRankingConfig(mode="shadow")
    out = build_momentum_ranking_contribution(
        _payload(parity_status="validated_against_thinkorswim_fixture"),
        {"direction": "long"},
        config,
    )
    assert "thinkorswim_parity_pending" not in out.reason_codes


def test_derived_higher_timeframe_adds_reason_code() -> None:
    config = MomentumRankingConfig(mode="shadow")
    out = build_momentum_ranking_contribution(
        _payload(higher_timeframe_source="derived_from_chart_bars"),
        {"direction": "long"},
        config,
    )
    assert "derived_higher_timeframe" in out.reason_codes


def test_pullback_signal_adds_reason_code() -> None:
    config = MomentumRankingConfig(mode="shadow")
    out = build_momentum_ranking_contribution(
        _payload(pullback_signal=True),
        {"direction": "long"},
        config,
    )
    assert "momentum_pullback_signal" in out.reason_codes


def test_parity_required_for_active_blocks_when_pending() -> None:
    config = MomentumRankingConfig(mode="active", parity_required_for_active=True)
    out = build_momentum_ranking_contribution(
        _payload(parity_status="pending_thinkorswim_fixture_validation"),
        {"direction": "long"},
        config,
    )
    assert out.applied is False
    assert "active_blocked_parity_required" in out.reason_codes


def test_parity_required_for_active_allows_when_validated() -> None:
    config = MomentumRankingConfig(mode="active", parity_required_for_active=True)
    out = build_momentum_ranking_contribution(
        _payload(parity_status="validated_against_thinkorswim_fixture"),
        {"direction": "long"},
        config,
    )
    assert out.applied is True


# ── Missing payload + sanitation ──────────────────────────────────────────


def test_missing_payload_fails_soft_with_unavailable_reason_code() -> None:
    for mode in ("shadow", "active"):
        config = MomentumRankingConfig(mode=mode)
        out = build_momentum_ranking_contribution(None, {"direction": "long"}, config)
        assert out.enabled is True
        assert out.applied is False
        assert out.total_contribution == 0.0
        assert "momentum_payload_unavailable" in out.reason_codes


def test_dict_shaped_payload_is_accepted() -> None:
    config = MomentumRankingConfig(mode="shadow")
    snap_dict = _snapshot().model_dump()
    payload_dict: dict[str, Any] = {
        "latest_snapshot": snap_dict,
        "explanation": {
            "snapshot": snap_dict,
            "reversal_warning": False,
            "pullback_signal": False,
            "no_trade_warning": False,
            "notes": [],
        },
        "parity_status": "pending_thinkorswim_fixture_validation",
        "higher_timeframe_source": "provided_higher_timeframe_bars",
        "calculation_notes": [],
    }
    out = build_momentum_ranking_contribution(payload_dict, {"direction": "long"}, config)
    assert out.shadow_contribution > 0
    assert "derived_higher_timeframe" not in out.reason_codes
    assert "thinkorswim_parity_pending" in out.reason_codes


def test_contribution_is_never_nan_or_inf_even_with_bad_inputs() -> None:
    config = MomentumRankingConfig(mode="active")
    snap = _snapshot()
    out = build_momentum_ranking_contribution(_payload(snap), {"direction": "long"}, config)
    for value in (
        out.total_contribution,
        out.shadow_contribution,
        out.momentum_alignment_score,
        out.trend_alignment_score,
        out.hilo_confirmation_bonus,
        out.reversal_warning_penalty,
    ):
        assert isinstance(value, float)
        assert not math.isnan(value)
        assert not math.isinf(value)


def test_strategy_inferred_direction_from_recent_trend() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"strategy": "Event Continuation", "recent_trend": 5.0},
        config,
    )
    assert out.inferred_direction == "long"
    assert out.applied is True

    out_short = build_momentum_ranking_contribution(
        _payload(_snapshot(total_label="Bear", total_state="bear", trend_score=-80, hilo_score=-15)),
        {"strategy": "Pullback Continuation", "recent_trend": -5.0},
        config,
    )
    assert out_short.inferred_direction == "short"


def test_fade_strategies_keep_direction_unknown_without_explicit_side() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"strategy": "Failed Event Fade", "recent_trend": 5.0},
        config,
    )
    assert out.inferred_direction == "unknown"
    assert "direction_unknown" in out.reason_codes
    assert out.applied is False


# ── Phase B4.2 direction-inference tests ─────────────────────────────────


def test_breakout_prior_day_high_infers_long_via_strategy_id() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"strategy": "Breakout / Prior-Day High", "strategy_id": "breakout_prior_day_high"},
        config,
    )
    assert out.inferred_direction == "long"
    assert "direction_unknown" not in out.reason_codes
    assert "bullish_strategy_direction_inferred" in out.reason_codes
    assert out.applied is True
    assert out.total_contribution > 0


def test_breakout_prior_day_high_infers_long_via_label_only() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"strategy": "Breakout / Prior-Day High"},  # no strategy_id, no profile
        config,
    )
    assert out.inferred_direction == "long"
    assert "direction_unknown" not in out.reason_codes
    assert "bullish_strategy_direction_inferred" in out.reason_codes


def test_event_continuation_label_infers_long_without_recent_trend() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"strategy": "Event Continuation"},
        config,
    )
    assert out.inferred_direction == "long"
    assert "bullish_strategy_direction_inferred" in out.reason_codes
    assert "direction_unknown" not in out.reason_codes


def test_pullback_trend_continuation_label_infers_long() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"strategy": "Pullback / Trend Continuation"},
        config,
    )
    assert out.inferred_direction == "long"
    assert "bullish_strategy_direction_inferred" in out.reason_codes


def test_directional_profile_bullish_yields_long_via_registry_metadata() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(),
        {
            "strategy": "Some Strategy We Don't Know",
            "strategy_id": "completely_unknown_id",
            "directional_profile": "bullish",
        },
        config,
    )
    assert out.inferred_direction == "long"
    assert "direction_from_strategy_metadata" in out.reason_codes
    assert "direction_unknown" not in out.reason_codes


def test_directional_profile_bearish_yields_short_via_registry_metadata() -> None:
    config = MomentumRankingConfig(mode="active")
    bear_snap = _snapshot(total_label="Bear", total_state="bear", trend_score=-80, hilo_score=-15)
    out = build_momentum_ranking_contribution(
        _payload(bear_snap),
        {
            "strategy": "Bear Put Debit Spread",
            "strategy_id": "bear_put_debit_spread",
            "directional_profile": "bearish",
        },
        config,
    )
    assert out.inferred_direction == "short"
    assert "direction_from_strategy_metadata" in out.reason_codes
    assert "direction_unknown" not in out.reason_codes
    assert out.applied is True


def test_directional_profile_neutral_does_not_infer_long_even_with_bullish_label() -> None:
    """When the registry explicitly says neutral/carry/volatility the
    label fallback must not override it."""
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(),
        {
            "strategy": "Breakout / Prior-Day High",
            "strategy_id": "breakout_prior_day_high",
            "directional_profile": "neutral",
        },
        config,
    )
    assert out.inferred_direction == "unknown"
    assert "direction_unknown" in out.reason_codes
    assert "bullish_strategy_direction_inferred" not in out.reason_codes
    assert out.applied is False


def test_explicit_candidate_metadata_beats_registry_metadata() -> None:
    config = MomentumRankingConfig(mode="active")
    bear_snap = _snapshot(total_label="Bear", total_state="bear", trend_score=-80, hilo_score=-15)
    out = build_momentum_ranking_contribution(
        _payload(bear_snap),
        {
            "strategy": "Event Continuation",
            "strategy_id": "event_continuation",
            "directional_profile": "bullish",
            "side": "short",  # explicit metadata wins
        },
        config,
    )
    assert out.inferred_direction == "short"
    assert "direction_from_candidate_metadata" in out.reason_codes
    assert "direction_from_strategy_metadata" not in out.reason_codes
    assert "bullish_strategy_direction_inferred" not in out.reason_codes


def test_explicit_direction_alias_uses_candidate_metadata_reason() -> None:
    config = MomentumRankingConfig(mode="shadow")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"direction": "long"},
        config,
    )
    assert out.inferred_direction == "long"
    assert "direction_from_candidate_metadata" in out.reason_codes


def test_truly_unknown_strategy_stays_unknown_and_unapplied() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"strategy": "Some Mystery Strategy Without Hints"},
        config,
    )
    assert out.inferred_direction == "unknown"
    assert "direction_unknown" in out.reason_codes
    assert out.applied is False


def test_mean_reversion_stays_unknown_via_strategy_id() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"strategy": "Mean Reversion", "strategy_id": "mean_reversion"},
        config,
    )
    assert out.inferred_direction == "unknown"
    assert "direction_unknown" in out.reason_codes


def test_bullish_inference_still_respects_total_contribution_cap() -> None:
    """Phase B4.2 must not change contribution caps; bullish inference
    only allows the existing bounded contribution to apply."""
    config = MomentumRankingConfig(mode="active")
    extreme = _snapshot(
        total_score=130, total_label="Max Bull", total_state="max_bull",
        trend_score=130.0, momo_score=130.0, hilo_score=20,
    )
    out = build_momentum_ranking_contribution(
        _payload(extreme),
        {"strategy": "Breakout / Prior-Day High", "strategy_id": "breakout_prior_day_high"},
        config,
    )
    assert out.shadow_contribution == pytest.approx(config.max_total_contribution)
    assert out.total_contribution == pytest.approx(config.max_total_contribution)


def test_breakout_in_shadow_mode_does_not_apply_but_carries_inferred_reason() -> None:
    config = MomentumRankingConfig(mode="shadow")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"strategy": "Breakout / Prior-Day High", "strategy_id": "breakout_prior_day_high"},
        config,
    )
    assert out.mode == "shadow"
    assert out.applied is False
    assert out.inferred_direction == "long"
    assert "bullish_strategy_direction_inferred" in out.reason_codes


def test_off_mode_does_not_run_inference() -> None:
    config = MomentumRankingConfig(mode="off")
    out = build_momentum_ranking_contribution(
        _payload(),
        {"strategy": "Breakout / Prior-Day High", "strategy_id": "breakout_prior_day_high"},
        config,
    )
    assert out.mode == "off"
    assert out.applied is False
    assert "bullish_strategy_direction_inferred" not in out.reason_codes
    assert "direction_from_strategy_metadata" not in out.reason_codes


def test_label_normalization_handles_punctuation_and_casing() -> None:
    config = MomentumRankingConfig(mode="active")
    for label in (
        "BREAKOUT / Prior-Day High",
        "  breakout   prior-day  high  ",
        "Prior-Day High Breakout",
    ):
        out = build_momentum_ranking_contribution(_payload(), {"strategy": label}, config)
        assert out.inferred_direction == "long", f"failed to infer long from label: {label!r}"
        assert "bullish_strategy_direction_inferred" in out.reason_codes


# ── Mode resolution ───────────────────────────────────────────────────────


def test_resolve_mode_falls_back_safely_on_unknown_input() -> None:
    assert resolve_momentum_ranking_mode("off") == "off"
    assert resolve_momentum_ranking_mode("Shadow") == "shadow"
    assert resolve_momentum_ranking_mode("ACTIVE") == "active"
    assert resolve_momentum_ranking_mode("garbage") == "shadow"
    assert resolve_momentum_ranking_mode(None) == "shadow"
    assert resolve_momentum_ranking_mode("") == "shadow"


# ── Trade-approval guardrails (Phase B1 must not approve trades) ──────────


def test_contribution_payload_does_not_include_approval_or_routing_fields() -> None:
    config = MomentumRankingConfig(mode="active")
    out = build_momentum_ranking_contribution(_payload(), {"direction": "long"}, config)
    dumped = out.model_dump(mode="json")
    forbidden = {"approved", "rejected", "approve", "reject", "side", "shares", "size", "order_id", "route"}
    overlap = forbidden & dumped.keys()
    assert overlap == set(), f"Phase B1 contribution must not surface approval/sizing fields, found: {overlap}"
