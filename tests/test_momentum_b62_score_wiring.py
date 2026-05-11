"""Phase B6.2 — backend regression tests for the deployed active-mode
score-wiring bug.

Symptoms reported from the deployed environment with::

    MACMARKET_MOMENTUM_RANKING_MODE=active
    MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true
    MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE=0.35

- Recommendation detail card showed ``Applied +20.00 raw`` and
  ``Score delta +0.07`` (correct).
- The ranked queue saturated to ``score = 1.000`` for candidates whose
  baseline was already 0.80–0.90 (incorrect — should have landed at
  baseline + 0.07).
- The Momentum Shadow Impact Review table showed ``Applied delta @
  scale: 0.000`` for active rows (incorrect).

These tests use the pure :func:`apply_momentum_score_delta` helper and
the full :class:`DeterministicRankingEngine` to pin the expected
behavior with realistic baselines so any future regression in the
score-wiring path fails loudly.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import patch

import pytest

from macmarket_trader.domain.enums import MarketMode
from macmarket_trader.domain.schemas import Bar, MomentumRankingContribution
from macmarket_trader.ranking_engine import DeterministicRankingEngine
from macmarket_trader.recommendation.momentum_ranking import (
    DEFAULT_ACTIVE_DELTA_SCALE,
    MomentumRankingConfig,
    apply_momentum_score_delta,
    build_momentum_ranking_contribution,
)


def _bullish_bars(n: int = 220) -> list[Bar]:
    base = date(2024, 1, 1)
    return [
        Bar(
            date=base + timedelta(days=i),
            open=100.0 + i * 0.8,
            high=101.0 + i * 0.8,
            low=99.0 + i * 0.8,
            close=100.5 + i * 0.8,
            volume=2_000_000,
        )
        for i in range(n)
    ]


def _bars_by_symbol() -> dict[str, tuple[list[Bar], str, bool]]:
    return {"SPY": (_bullish_bars(), "test_provider", False)}


def _payload_stub(
    *,
    total_state: str = "max_bull",
    total_label: str = "Max Bull",
    total_score: int = 100,
    trend_score: float = 100.0,
    momo_score: float = 100.0,
    hilo_score: int = 20,
    reversal_warning: bool = False,
) -> dict[str, Any]:
    snap = {
        "total_score": total_score,
        "total_label": total_label,
        "total_state": total_state,
        "trend_score": trend_score,
        "momo_score": momo_score,
        "true_momentum": 70.0,
        "true_momentum_ema": 60.0,
        "true_momentum_score": 15,
        "hilo_thrust": 1 if hilo_score > 0 else -1,
        "hilo_score": hilo_score,
        "atr_bias": 5,
        "macd_bias": 5,
        "ma_bias": 30,
        "component_breakdown": {
            "true_momentum_score": 15,
            "hilo_thrust": abs(hilo_score) // 4,
            "bull_ma": 30,
            "bear_ma": 0,
            "atr_value": 5,
            "macd_bias": 5,
            "intraday_penalty": 0,
            "base_score": 60,
        },
    }
    return {
        "latest_snapshot": snap,
        "explanation": {
            "snapshot": snap,
            "reversal_warning": reversal_warning,
            "pullback_signal": False,
            "no_trade_warning": False,
            "notes": [],
        },
        "parity_status": "pending_thinkorswim_fixture_validation",
        "higher_timeframe_source": "derived_from_chart_bars",
        "calculation_notes": [],
    }


# ── apply_momentum_score_delta helper ─────────────────────────────────────


@pytest.mark.parametrize(
    "baseline, expected_after, expected_delta",
    [
        (0.812, 0.882, 0.07),
        (0.898, 0.968, 0.07),
        (0.970, 1.000, 0.030),  # clamp still triggers when baseline + delta > 1.0
        (0.0, 0.07, 0.07),
        (1.0, 1.0, 0.0),
    ],
)
def test_apply_momentum_score_delta_with_raw_plus_20_at_default_scale(
    baseline: float, expected_after: float, expected_delta: float
) -> None:
    """Baseline + raw +20 at default scale 0.35 should land at baseline+0.07
    unless the [0,1] clamp triggers. Pins the deployed-bug regression
    surface (SPY baseline 0.812 → 0.882, not 1.000).
    """
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
    )
    contribution = build_momentum_ranking_contribution(
        _payload_stub(), {"direction": "long"}, config
    )
    assert contribution.applied is True
    assert contribution.applied_score_delta == pytest.approx(0.07)

    score_after, delta = apply_momentum_score_delta(baseline, contribution)
    # Clamp-aware: the applied delta reported by the helper is the
    # **effective** delta after the [0,1] clamp.
    if baseline + 0.07 > 1.0:
        assert score_after == pytest.approx(1.0)
    else:
        assert score_after == pytest.approx(expected_after, abs=1e-9)
    # The raw-applied delta should still equal the scaled value
    # (the helper returns the value before clamp truncation for audit).
    # We measure the actual after - baseline to confirm the engine's
    # clamp didn't silently expand the delta.
    assert score_after - baseline == pytest.approx(min(0.07, 1.0 - baseline), abs=1e-9)


def test_apply_momentum_score_delta_negative_contribution() -> None:
    """Negative raw contribution (floor -12) at scale 0.35 gives -0.042.
    Baseline 0.848 - 0.042 = 0.806 (matches deployed regression scenario)."""
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
    )
    payload = _payload_stub(
        total_state="max_bear",
        total_label="Max Bear",
        total_score=-100,
        trend_score=-100.0,
        momo_score=-100.0,
        hilo_score=-20,
        reversal_warning=True,
    )
    # Direction long against bear momentum + reversal warning → floor -12.
    contribution = build_momentum_ranking_contribution(payload, {"direction": "long"}, config)
    assert contribution.applied_score_delta == pytest.approx(-12.0 / 100 * 0.35)
    assert contribution.applied_score_delta == pytest.approx(-0.042)

    score_after, delta = apply_momentum_score_delta(0.848, contribution)
    assert score_after == pytest.approx(0.806, abs=1e-9)
    assert delta == pytest.approx(-0.042, abs=1e-9)


def test_apply_momentum_score_delta_returns_zero_for_shadow_mode_payload() -> None:
    config = MomentumRankingConfig(mode="shadow", active_delta_scale=0.35)
    contribution = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
    score_after, delta = apply_momentum_score_delta(0.812, contribution)
    assert score_after == pytest.approx(0.812)
    assert delta == 0.0


def test_apply_momentum_score_delta_returns_zero_for_blocked_active_payload() -> None:
    config = MomentumRankingConfig(
        mode="shadow",  # effective shadow
        requested_mode="active",
        active_allowed=False,
        active_delta_scale=0.35,
    )
    contribution = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
    score_after, delta = apply_momentum_score_delta(0.812, contribution)
    assert score_after == pytest.approx(0.812)
    assert delta == 0.0


def test_apply_momentum_score_delta_handles_missing_applied_score_delta() -> None:
    """Backward-compat: contributions from older payloads (pre-B6.1) lack
    ``applied_score_delta`` but still carry ``total_contribution`` and a
    scale. The helper recomputes from those fields."""
    contribution = MomentumRankingContribution(
        mode="active",
        enabled=True,
        applied=True,
        total_contribution=20.0,
        shadow_contribution=20.0,
        # Phase B6.1 fields absent — simulate a pre-B6.1 payload:
        active_delta_scale=None,
        raw_total_contribution=None,
        applied_score_delta=None,
    )
    score_after, delta = apply_momentum_score_delta(0.812, contribution)
    # Falls back to total_contribution / 100 * DEFAULT_ACTIVE_DELTA_SCALE.
    assert delta == pytest.approx(0.07)
    assert score_after == pytest.approx(0.882, abs=1e-9)


def test_apply_momentum_score_delta_sanitizes_non_finite_inputs() -> None:
    contribution = MomentumRankingContribution(
        mode="active",
        enabled=True,
        applied=True,
        total_contribution=float("nan"),
        applied_score_delta=float("inf"),
        active_delta_scale=0.35,
        raw_total_contribution=float("nan"),
    )
    score_after, delta = apply_momentum_score_delta(0.812, contribution)
    # NaN / inf collapse to 0; score stays clamped.
    assert delta == 0.0
    assert score_after == pytest.approx(0.812)


# ── Ranking-engine end-to-end with mocked baselines ───────────────────────


@pytest.mark.parametrize(
    "baseline, expected_after",
    [
        (0.812, 0.882),
        (0.898, 0.968),
        (0.970, 1.000),  # clamp-aware
        (0.500, 0.570),
        (0.95, 1.000),  # 0.95 + 0.07 = 1.02 → clamped
    ],
)
def test_engine_active_mode_score_for_explicit_baseline(
    baseline: float, expected_after: float
) -> None:
    """Patch ``_score_symbol`` so we can drive the engine with an exact
    baseline. The active-mode score must equal the baseline plus the
    scaled delta (clamped to [0, 1])."""
    bars_by_symbol = _bars_by_symbol()
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
    )

    def _fake_score_symbol(_bars: list[Bar], _strategy: str) -> dict[str, float]:
        return {
            "strategy_fit_score": 0.75,
            "regime_fit_score": 0.7,
            "catalyst_quality_score": 0.55,
            "liquidity_score": 0.9,
            "volatility_suitability_score": 0.6,
            "spread_slippage_penalty": 0.05,
            "regime_alignment_bonus": 0.0,
            "recency_weight": 0.0,
            "expected_rr": 2.0,
            "confidence": 0.7,
            "total_score": baseline,
        }

    with patch("macmarket_trader.ranking_engine._score_symbol", _fake_score_symbol):
        active = DeterministicRankingEngine(config).rank_candidates(
            bars_by_symbol=bars_by_symbol,
            strategies=["Event Continuation"],
            market_mode=MarketMode.EQUITIES,
            timeframe="1D",
        )["queue"][0]

    assert active["score"] == pytest.approx(expected_after, abs=1e-3)
    # B6 before/after fields must be populated and internally consistent.
    assert active["score_before_momentum"] == pytest.approx(baseline, abs=1e-3)
    assert active["score_after_momentum"] == pytest.approx(expected_after, abs=1e-3)
    # Phase B6.2: momentum_score_delta records the **intended** scaled
    # delta from ``apply_momentum_score_delta`` (single source of truth).
    # Even when the clamp truncates the score (e.g., baseline 0.97 + 0.07
    # → 1.000), the published delta stays 0.07 so operator audit copy
    # ("Score delta +0.07") agrees with the contribution payload.
    assert active["momentum_score_delta"] == pytest.approx(0.07, abs=1e-6)
    assert active["momentum_rank_mode"] == "active"
    # The contribution payload must agree with the engine's published
    # delta — that was the deployed inconsistency.
    contrib = active["momentum_contribution"]
    assert contrib["applied_score_delta"] == pytest.approx(0.07)
    assert contrib["raw_total_contribution"] == pytest.approx(20.0)
    assert contrib["active_delta_scale"] == pytest.approx(DEFAULT_ACTIVE_DELTA_SCALE)


def test_engine_active_mode_does_not_use_unscaled_raw_for_score() -> None:
    """Regression pin: never apply raw_total_contribution / 100 directly.

    With baseline 0.812 and raw +20, the un-scaled delta would be +0.20
    and the score would clamp to 1.000. With scale 0.35 it must be
    +0.07 and the score must land at 0.882.
    """
    bars_by_symbol = _bars_by_symbol()
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
    )

    def _fake_score_symbol(_bars: list[Bar], _strategy: str) -> dict[str, float]:
        return {
            "strategy_fit_score": 0.75,
            "regime_fit_score": 0.7,
            "catalyst_quality_score": 0.55,
            "liquidity_score": 0.9,
            "volatility_suitability_score": 0.6,
            "spread_slippage_penalty": 0.05,
            "regime_alignment_bonus": 0.0,
            "recency_weight": 0.0,
            "expected_rr": 2.0,
            "confidence": 0.7,
            "total_score": 0.812,
        }

    with patch("macmarket_trader.ranking_engine._score_symbol", _fake_score_symbol):
        active = DeterministicRankingEngine(config).rank_candidates(
            bars_by_symbol=bars_by_symbol,
            strategies=["Event Continuation"],
            market_mode=MarketMode.EQUITIES,
            timeframe="1D",
        )["queue"][0]

    assert active["score"] != pytest.approx(1.000)
    assert active["score"] == pytest.approx(0.882, abs=1e-3)


def test_engine_shadow_mode_score_unchanged_with_high_baseline() -> None:
    """Shadow mode must not move the queue score even with raw +20."""
    bars_by_symbol = _bars_by_symbol()
    config = MomentumRankingConfig(mode="shadow", active_delta_scale=0.35)

    def _fake_score_symbol(_bars: list[Bar], _strategy: str) -> dict[str, float]:
        return {
            "strategy_fit_score": 0.75,
            "regime_fit_score": 0.7,
            "catalyst_quality_score": 0.55,
            "liquidity_score": 0.9,
            "volatility_suitability_score": 0.6,
            "spread_slippage_penalty": 0.05,
            "regime_alignment_bonus": 0.0,
            "recency_weight": 0.0,
            "expected_rr": 2.0,
            "confidence": 0.7,
            "total_score": 0.812,
        }

    with patch("macmarket_trader.ranking_engine._score_symbol", _fake_score_symbol):
        shadow = DeterministicRankingEngine(config).rank_candidates(
            bars_by_symbol=bars_by_symbol,
            strategies=["Event Continuation"],
            market_mode=MarketMode.EQUITIES,
            timeframe="1D",
        )["queue"][0]
    assert shadow["score"] == pytest.approx(0.812, abs=1e-3)
    assert shadow["momentum_score_delta"] is None


def test_engine_blocked_active_score_unchanged_with_high_baseline() -> None:
    bars_by_symbol = _bars_by_symbol()
    config = MomentumRankingConfig(
        mode="shadow",
        requested_mode="active",
        active_allowed=False,
        active_delta_scale=0.35,
    )

    def _fake_score_symbol(_bars: list[Bar], _strategy: str) -> dict[str, float]:
        return {
            "strategy_fit_score": 0.75,
            "regime_fit_score": 0.7,
            "catalyst_quality_score": 0.55,
            "liquidity_score": 0.9,
            "volatility_suitability_score": 0.6,
            "spread_slippage_penalty": 0.05,
            "regime_alignment_bonus": 0.0,
            "recency_weight": 0.0,
            "expected_rr": 2.0,
            "confidence": 0.7,
            "total_score": 0.812,
        }

    with patch("macmarket_trader.ranking_engine._score_symbol", _fake_score_symbol):
        blocked = DeterministicRankingEngine(config).rank_candidates(
            bars_by_symbol=bars_by_symbol,
            strategies=["Event Continuation"],
            market_mode=MarketMode.EQUITIES,
            timeframe="1D",
        )["queue"][0]

    assert blocked["score"] == pytest.approx(0.812, abs=1e-3)
    assert "active_mode_blocked_by_safety_guard" in blocked["momentum_contribution"]["reason_codes"]


def test_engine_queue_payload_carries_consistent_b6_fields() -> None:
    """Queue rows must surface the Phase B6 before/after fields so the
    frontend Impact Review can render them without inferring."""
    bars_by_symbol = _bars_by_symbol()
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
    )

    def _fake_score_symbol(_bars: list[Bar], _strategy: str) -> dict[str, float]:
        return {
            "strategy_fit_score": 0.75,
            "regime_fit_score": 0.7,
            "catalyst_quality_score": 0.55,
            "liquidity_score": 0.9,
            "volatility_suitability_score": 0.6,
            "spread_slippage_penalty": 0.05,
            "regime_alignment_bonus": 0.0,
            "recency_weight": 0.0,
            "expected_rr": 2.0,
            "confidence": 0.7,
            "total_score": 0.812,
        }

    with patch("macmarket_trader.ranking_engine._score_symbol", _fake_score_symbol):
        queue = DeterministicRankingEngine(config).rank_candidates(
            bars_by_symbol=bars_by_symbol,
            strategies=["Event Continuation"],
            market_mode=MarketMode.EQUITIES,
            timeframe="1D",
        )["queue"]

    row = queue[0]
    assert "score_before_momentum" in row
    assert "score_after_momentum" in row
    assert "momentum_score_delta" in row
    assert "momentum_rank_mode" in row
    # The candidate's published delta must match the contribution payload.
    contrib_delta = row["momentum_contribution"]["applied_score_delta"]
    candidate_delta = row["momentum_score_delta"]
    assert candidate_delta == pytest.approx(contrib_delta, abs=1e-6)


def test_queue_payload_never_carries_approval_or_routing_fields() -> None:
    bars_by_symbol = _bars_by_symbol()
    out = DeterministicRankingEngine(
        MomentumRankingConfig(
            mode="active",
            requested_mode="active",
            active_allowed=True,
            active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
        )
    ).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    forbidden = {"approved", "rejected", "side", "shares", "order_id", "route", "auto_approve"}
    overlap = forbidden & set(out.keys())
    assert overlap == set()
    overlap_contrib = forbidden & set(out["momentum_contribution"].keys())
    assert overlap_contrib == set()
