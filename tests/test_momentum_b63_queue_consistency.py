"""Phase B6.3 — API/queue-level integration regression tests.

These tests exercise the real ``/user/recommendations/queue`` endpoint
via :class:`fastapi.testclient.TestClient` to pin the deployed
active-mode score-wiring bug that survived the Phase B6.2 helper fix:

  - The recommendation detail card showed the correctly **scaled**
    Momentum delta (+20 raw at scale 0.35 → +0.07).
  - The ranked queue / impact review still rendered the **un-scaled**
    legacy delta (+0.20), driving SPY baseline 0.812 to ``score=1.000``
    instead of 0.882.

Phase B6.3 fixes this by routing every active-mode score through the
single :func:`enforce_score_consistency` guard so the engine, the
contribution payload, and the API response can never disagree again.
The tests below cover the real API surface (route → engine → payload)
plus the consistency-guard pure helper.

Scope guardrails (must hold for every assertion in this file):

  * Approval/order behavior is unchanged.
  * Paper-order creation is unchanged.
  * Raw contribution caps are unchanged.
  * Default Momentum mode is unchanged.
  * Indicator math is unchanged.
  * Thinkorswim parity fixtures remain pending.
  * No Phase C strategy families are introduced.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.api.routes import admin as admin_routes
from macmarket_trader.domain.enums import MarketMode
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import (
    Bar,
    MomentumRankingContribution,
)
from macmarket_trader.ranking_engine import DeterministicRankingEngine
from macmarket_trader.recommendation.momentum_ranking import (
    ACTIVE_DELTA_FORMULA_VERSION,
    DEFAULT_ACTIVE_DELTA_SCALE,
    MomentumRankingConfig,
    RANKING_SCORE_CONSISTENCY_GUARD,
    apply_momentum_score_delta,
    enforce_score_consistency,
)
from macmarket_trader.storage.db import SessionLocal, init_db


# Fields that must never appear on a queue candidate payload — Phase B
# rules forbid approval, sizing, or routing decisions from leaking into
# the ranking surface, and the consistency guard must not introduce them.
_FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "approve",
        "approved",
        "approval",
        "approval_status",
        "broker",
        "broker_provider",
        "routed",
        "routing",
        "order",
        "order_id",
        "buy_now",
        "sell_now",
        "live_trading",
        "auto_approve",
    }
)


def setup_module() -> None:
    init_db()


def _approve_default_user(client: TestClient) -> int:
    client.get("/user/me", headers={"Authorization": "Bearer user-token"})
    with SessionLocal() as session:
        user = session.execute(
            select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")
        ).scalar_one()
        user.approval_status = "approved"
        session.commit()
        return user.id


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


def _payload_stub_max_bull() -> dict[str, Any]:
    snap = {
        "total_score": 100,
        "total_label": "Max Bull",
        "total_state": "max_bull",
        "trend_score": 100.0,
        "momo_score": 100.0,
        "true_momentum": 70.0,
        "true_momentum_ema": 60.0,
        "true_momentum_score": 15,
        "hilo_thrust": 1,
        "hilo_score": 20,
        "atr_bias": 5,
        "macd_bias": 5,
        "ma_bias": 30,
        "component_breakdown": {
            "true_momentum_score": 15,
            "hilo_thrust": 5,
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
            "reversal_warning": False,
            "pullback_signal": False,
            "no_trade_warning": False,
            "notes": [],
        },
        "parity_status": "pending_thinkorswim_fixture_validation",
        "higher_timeframe_source": "derived_from_chart_bars",
        "calculation_notes": [],
    }


def _fake_score_symbol_with_baseline(baseline: float):
    def _scorer(_bars: list[Bar], _strategy: str) -> dict[str, float]:
        return {
            "strategy_fit_score": 0.75,
            "regime_fit_score": 0.70,
            "catalyst_quality_score": 0.55,
            "liquidity_score": 0.90,
            "volatility_suitability_score": 0.60,
            "spread_slippage_penalty": 0.05,
            "regime_alignment_bonus": 0.0,
            "recency_weight": 0.0,
            "expected_rr": 2.0,
            "confidence": 0.70,
            "total_score": baseline,
        }

    return _scorer


def _force_active_mode(monkeypatch: pytest.MonkeyPatch, *, scale: float = 0.35) -> None:
    """Configure the ranking engine to run in active mode for the test."""
    monkeypatch.setattr(admin_routes.settings, "momentum_ranking_mode", "active")
    monkeypatch.setattr(admin_routes.settings, "momentum_active_ranking_allowed", True)
    monkeypatch.setattr(admin_routes.settings, "momentum_active_delta_scale", scale)
    # Replace the module-level ranking_engine with one that picks up the
    # patched settings every call. Phase B6.3 must work end-to-end through
    # the route, not just the helper.
    monkeypatch.setattr(
        admin_routes,
        "ranking_engine",
        DeterministicRankingEngine(),
    )


# ── enforce_score_consistency pure helper ───────────────────────────────


def test_consistency_guard_passes_through_when_observed_matches_expected() -> None:
    contribution = MomentumRankingContribution(
        mode="active",
        enabled=True,
        applied=True,
        total_contribution=20.0,
        shadow_contribution=20.0,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
        raw_total_contribution=20.0,
        applied_score_delta=0.07,
    )
    result = enforce_score_consistency(
        observed_score=0.882,
        score_before_momentum=0.812,
        contribution=contribution,
    )
    assert result.final_score == pytest.approx(0.882, abs=1e-6)
    assert result.intended_applied_delta == pytest.approx(0.07, abs=1e-6)
    assert result.realized_score_delta == pytest.approx(0.07, abs=1e-6)
    assert result.corrected is False


def test_consistency_guard_corrects_legacy_unscaled_delta() -> None:
    """Pin the deployed regression shape: the queue observed +0.20 (raw/100,
    pre-B6.1), but the contribution payload says applied_score_delta=0.07
    (B6.1 scaled). The guard must overwrite the score to the scaled value
    and tag the result so the operator UI can flag it."""
    contribution = MomentumRankingContribution(
        mode="active",
        enabled=True,
        applied=True,
        total_contribution=20.0,
        shadow_contribution=20.0,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
        raw_total_contribution=20.0,
        applied_score_delta=0.07,
    )
    # Legacy bug shape: baseline 0.812 + raw/100 = 1.000 (clamped from 1.012).
    result = enforce_score_consistency(
        observed_score=1.000,
        score_before_momentum=0.812,
        contribution=contribution,
    )
    # Guard forces the score back to the scaled value (0.882).
    assert result.final_score == pytest.approx(0.882, abs=1e-6)
    # Intended delta is the scaled value, NOT 0.188 (= 1.000 − 0.812).
    assert result.intended_applied_delta == pytest.approx(0.07, abs=1e-6)
    assert result.realized_score_delta == pytest.approx(0.07, abs=1e-6)
    assert result.corrected is True


def test_consistency_guard_reports_realized_delta_when_clamp_truncates() -> None:
    contribution = MomentumRankingContribution(
        mode="active",
        enabled=True,
        applied=True,
        total_contribution=20.0,
        shadow_contribution=20.0,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
        raw_total_contribution=20.0,
        applied_score_delta=0.07,
    )
    # Baseline 0.97 + intended +0.07 = 1.04 → clamped to 1.0.
    result = enforce_score_consistency(
        observed_score=1.0,
        score_before_momentum=0.97,
        contribution=contribution,
    )
    assert result.final_score == pytest.approx(1.0, abs=1e-6)
    # Intended stays at the scaled value so audit copy ("Score delta
    # +0.07") agrees with the contribution payload.
    assert result.intended_applied_delta == pytest.approx(0.07, abs=1e-6)
    # Realized reflects what actually happened to the score after clamp.
    assert result.realized_score_delta == pytest.approx(0.03, abs=1e-6)
    assert result.corrected is False


def test_consistency_guard_passthrough_for_shadow_blocked_and_disabled() -> None:
    shadow = MomentumRankingContribution(
        mode="shadow",
        enabled=True,
        applied=False,
        shadow_contribution=20.0,
        applied_score_delta=0.0,
    )
    blocked = MomentumRankingContribution(
        mode="shadow",
        enabled=True,
        applied=False,
        reason_codes=["active_mode_blocked_by_safety_guard"],
        applied_score_delta=0.0,
    )
    off = MomentumRankingContribution(mode="off", enabled=False, applied=False)
    for contribution in (shadow, blocked, off):
        result = enforce_score_consistency(
            observed_score=0.812,
            score_before_momentum=0.812,
            contribution=contribution,
        )
        assert result.final_score == pytest.approx(0.812, abs=1e-6)
        assert result.intended_applied_delta == 0.0
        assert result.realized_score_delta == 0.0
        assert result.corrected is False


def test_consistency_guard_sanitizes_non_finite_observed_score() -> None:
    contribution = MomentumRankingContribution(
        mode="active",
        enabled=True,
        applied=True,
        total_contribution=20.0,
        shadow_contribution=20.0,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
        raw_total_contribution=20.0,
        applied_score_delta=0.07,
    )
    result = enforce_score_consistency(
        observed_score=float("nan"),
        score_before_momentum=0.812,
        contribution=contribution,
    )
    # NaN observed score collapses to 0, then the guard recomputes
    # 0.812 + 0.07 = 0.882 and marks corrected=True (observed=0 != 0.882).
    assert result.final_score == pytest.approx(0.882, abs=1e-6)
    assert result.corrected is True


# ── End-to-end engine integration (RankedCandidate output) ──────────────


@pytest.mark.parametrize(
    "baseline, expected_score, expected_realized",
    [
        (0.812, 0.882, 0.07),
        (0.898, 0.968, 0.07),
        (0.970, 1.000, 0.03),  # clamp truncates realized to 0.03
        (0.500, 0.570, 0.07),
        (1.000, 1.000, 0.0),  # already at ceiling — clamp gives realized 0
    ],
)
def test_engine_active_mode_publishes_consistent_score_for_explicit_baseline(
    monkeypatch: pytest.MonkeyPatch,
    baseline: float,
    expected_score: float,
    expected_realized: float,
) -> None:
    """Pin the score-fields invariant on the engine's RankedCandidate output.

    Single source of truth:
        score == score_after_momentum == clamp01(score_before + applied_score_delta)
        momentum_score_delta == contribution.applied_score_delta (intended, NOT clamp-truncated)
        momentum_realized_score_delta == score_after - score_before (clamp-aware)
    """
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
    )
    monkeypatch.setattr(
        "macmarket_trader.ranking_engine._score_symbol",
        _fake_score_symbol_with_baseline(baseline),
    )
    engine = DeterministicRankingEngine(config)
    queue = engine.rank_candidates(
        bars_by_symbol={"SPY": (_bullish_bars(), "test_provider", False)},
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"]
    assert queue, "engine must return at least one candidate"
    row = queue[0]

    # Phase B6.3 invariants — all fields agree on the same scaled math.
    assert row["score_before_momentum"] == pytest.approx(baseline, abs=1e-3)
    assert row["score_after_momentum"] == pytest.approx(expected_score, abs=1e-3)
    assert row["score"] == pytest.approx(expected_score, abs=1e-3)
    # score == score_after_momentum exactly (no separate rounding paths).
    assert row["score"] == pytest.approx(row["score_after_momentum"], abs=1e-3)

    # Intended applied delta is always the scaled value (0.07 here), even
    # when the clamp truncates the realized score.
    if expected_score < 1.0:
        assert row["momentum_score_delta"] == pytest.approx(0.07, abs=1e-6)
    else:
        # Clamp case: intended is still 0.07 (unless baseline already ≥1.0).
        if baseline < 1.0:
            assert row["momentum_score_delta"] == pytest.approx(0.07, abs=1e-6)

    # Realized delta tracks what actually happened on the score.
    assert row["momentum_realized_score_delta"] == pytest.approx(
        expected_realized, abs=1e-3
    )

    # Regression guard: queue must NEVER apply the un-scaled raw delta.
    # raw/100 = 0.20 would give baseline+0.20; assert that did NOT happen.
    if baseline + 0.20 <= 1.0:
        assert row["score"] != pytest.approx(baseline + 0.20, abs=1e-3)


def test_engine_active_mode_contribution_payload_matches_score_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
    )
    monkeypatch.setattr(
        "macmarket_trader.ranking_engine._score_symbol",
        _fake_score_symbol_with_baseline(0.812),
    )
    engine = DeterministicRankingEngine(config)
    row = engine.rank_candidates(
        bars_by_symbol={"SPY": (_bullish_bars(), "test_provider", False)},
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    contribution = row["momentum_contribution"]
    # The contribution payload's applied_score_delta is the single source
    # of truth — momentum_score_delta on the candidate must match it.
    assert contribution["applied_score_delta"] == pytest.approx(0.07, abs=1e-6)
    assert row["momentum_score_delta"] == pytest.approx(
        contribution["applied_score_delta"], abs=1e-6
    )
    # The contribution's active_delta_scale must match what the engine used.
    assert contribution["active_delta_scale"] == pytest.approx(
        DEFAULT_ACTIVE_DELTA_SCALE, abs=1e-6
    )


def test_engine_shadow_mode_does_not_change_score(monkeypatch: pytest.MonkeyPatch) -> None:
    config = MomentumRankingConfig(mode="shadow", active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE)
    monkeypatch.setattr(
        "macmarket_trader.ranking_engine._score_symbol",
        _fake_score_symbol_with_baseline(0.812),
    )
    engine = DeterministicRankingEngine(config)
    row = engine.rank_candidates(
        bars_by_symbol={"SPY": (_bullish_bars(), "test_provider", False)},
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    # Shadow mode never moves the queue score.
    assert row["score"] == pytest.approx(0.812, abs=1e-3)
    assert row["score_after_momentum"] == pytest.approx(0.812, abs=1e-3)
    assert row["score_before_momentum"] == pytest.approx(0.812, abs=1e-3)
    # No applied delta in shadow mode.
    assert row["momentum_score_delta"] in (None, 0.0)
    assert row["momentum_realized_score_delta"] in (None, 0.0)


def test_engine_blocked_active_mode_does_not_change_score(monkeypatch: pytest.MonkeyPatch) -> None:
    # Active requested but not allowed → effective shadow, no score movement.
    config = MomentumRankingConfig(
        mode="shadow",
        requested_mode="active",
        active_allowed=False,
        active_delta_scale=DEFAULT_ACTIVE_DELTA_SCALE,
    )
    monkeypatch.setattr(
        "macmarket_trader.ranking_engine._score_symbol",
        _fake_score_symbol_with_baseline(0.812),
    )
    engine = DeterministicRankingEngine(config)
    row = engine.rank_candidates(
        bars_by_symbol={"SPY": (_bullish_bars(), "test_provider", False)},
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    assert row["score"] == pytest.approx(0.812, abs=1e-3)
    assert "active_mode_blocked_by_safety_guard" in row["momentum_contribution"]["reason_codes"]


# ── /user/recommendations/queue API integration ─────────────────────────


def test_queue_api_active_mode_returns_scaled_score_and_b6_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hit the real queue endpoint and assert candidate.score lines up with
    the scaled Phase B6.1 delta — never the legacy raw/100 value."""
    _force_active_mode(monkeypatch)
    monkeypatch.setattr(
        "macmarket_trader.ranking_engine._score_symbol",
        _fake_score_symbol_with_baseline(0.812),
    )

    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/recommendations/queue",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbols": ["AAPL"],
            "timeframe": "1D",
            "market_mode": "equities",
            "top_n": 1,
        },
    )
    assert response.status_code == 200, response.text
    queue = response.json()["queue"]
    assert queue
    row = queue[0]

    # Phase B6 fields must be present on the wire — the frontend depends
    # on them for the impact-review baseline column.
    for key in (
        "score",
        "score_before_momentum",
        "score_after_momentum",
        "momentum_score_delta",
        "momentum_realized_score_delta",
        "momentum_rank_mode",
        "momentum_contribution",
    ):
        assert key in row, f"queue response missing key {key!r}"

    # Score fields must be internally consistent.
    assert row["score"] == pytest.approx(0.882, abs=1e-3)
    assert row["score_after_momentum"] == pytest.approx(0.882, abs=1e-3)
    assert row["score_before_momentum"] == pytest.approx(0.812, abs=1e-3)
    assert row["score"] == pytest.approx(row["score_after_momentum"], abs=1e-3)

    # Intended delta is the scaled +0.07. Legacy bug shape (+0.188 / +0.20)
    # must not appear on the wire.
    assert row["momentum_score_delta"] == pytest.approx(0.07, abs=1e-6)
    assert row["momentum_realized_score_delta"] == pytest.approx(0.07, abs=1e-3)
    contribution = row["momentum_contribution"]
    assert contribution["applied_score_delta"] == pytest.approx(0.07, abs=1e-6)
    assert contribution["active_delta_scale"] == pytest.approx(
        DEFAULT_ACTIVE_DELTA_SCALE, abs=1e-6
    )
    # Raw bounded contribution is unchanged (±20 cap).
    assert contribution["raw_total_contribution"] == pytest.approx(20.0, abs=1e-3)

    # The queue must not leak approval / order / routing fields.
    for forbidden in _FORBIDDEN_PAYLOAD_KEYS:
        assert forbidden not in row, f"queue row leaked forbidden key {forbidden!r}"


@pytest.mark.parametrize(
    "baseline, expected_score, expected_realized",
    [
        (0.812, 0.882, 0.07),
        (0.898, 0.968, 0.07),
        (0.970, 1.000, 0.03),
    ],
)
def test_queue_api_active_mode_at_realistic_baselines(
    monkeypatch: pytest.MonkeyPatch,
    baseline: float,
    expected_score: float,
    expected_realized: float,
) -> None:
    """Pin the deployed regression at the realistic baselines from the
    field report (0.812, 0.898, 0.970). The queue endpoint must publish
    the scaled +0.07 intended delta, never the legacy +0.20."""
    _force_active_mode(monkeypatch)
    monkeypatch.setattr(
        "macmarket_trader.ranking_engine._score_symbol",
        _fake_score_symbol_with_baseline(baseline),
    )
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/recommendations/queue",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbols": ["MSFT"],
            "timeframe": "1D",
            "market_mode": "equities",
            "top_n": 1,
        },
    )
    assert response.status_code == 200
    row = response.json()["queue"][0]
    assert row["score"] == pytest.approx(expected_score, abs=1e-3)
    assert row["score_after_momentum"] == pytest.approx(expected_score, abs=1e-3)
    assert row["momentum_realized_score_delta"] == pytest.approx(
        expected_realized, abs=1e-3
    )
    # Intended stays 0.07 unless baseline is already ≥1.0.
    if baseline < 1.0:
        assert row["momentum_score_delta"] == pytest.approx(0.07, abs=1e-6)
    # Regression: never the legacy unscaled +0.20 delta.
    if baseline + 0.20 <= 1.0:
        assert row["score"] != pytest.approx(baseline + 0.20, abs=1e-3)


def test_queue_api_shadow_mode_does_not_change_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin_routes.settings, "momentum_ranking_mode", "shadow")
    monkeypatch.setattr(admin_routes.settings, "momentum_active_ranking_allowed", False)
    monkeypatch.setattr(admin_routes.settings, "momentum_active_delta_scale", 0.35)
    monkeypatch.setattr(
        admin_routes, "ranking_engine", DeterministicRankingEngine(),
    )
    monkeypatch.setattr(
        "macmarket_trader.ranking_engine._score_symbol",
        _fake_score_symbol_with_baseline(0.812),
    )
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/recommendations/queue",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbols": ["AAPL"],
            "timeframe": "1D",
            "market_mode": "equities",
            "top_n": 1,
        },
    )
    assert response.status_code == 200
    row = response.json()["queue"][0]
    assert row["score"] == pytest.approx(0.812, abs=1e-3)
    assert row["score_after_momentum"] == pytest.approx(0.812, abs=1e-3)
    assert row["score_before_momentum"] == pytest.approx(0.812, abs=1e-3)
    # No applied delta in shadow.
    assert row["momentum_score_delta"] in (None, 0.0)
    assert row["momentum_realized_score_delta"] in (None, 0.0)


def test_queue_api_blocked_active_mode_does_not_change_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Active requested, but guard not allowed → effective shadow.
    monkeypatch.setattr(admin_routes.settings, "momentum_ranking_mode", "active")
    monkeypatch.setattr(admin_routes.settings, "momentum_active_ranking_allowed", False)
    monkeypatch.setattr(admin_routes.settings, "momentum_active_delta_scale", 0.35)
    monkeypatch.setattr(
        admin_routes, "ranking_engine", DeterministicRankingEngine(),
    )
    monkeypatch.setattr(
        "macmarket_trader.ranking_engine._score_symbol",
        _fake_score_symbol_with_baseline(0.812),
    )
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/recommendations/queue",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbols": ["AAPL"],
            "timeframe": "1D",
            "market_mode": "equities",
            "top_n": 1,
        },
    )
    assert response.status_code == 200
    row = response.json()["queue"][0]
    assert row["score"] == pytest.approx(0.812, abs=1e-3)
    assert "active_mode_blocked_by_safety_guard" in row["momentum_contribution"]["reason_codes"]


def test_queue_api_payload_never_contains_approval_or_order_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_active_mode(monkeypatch)
    monkeypatch.setattr(
        "macmarket_trader.ranking_engine._score_symbol",
        _fake_score_symbol_with_baseline(0.812),
    )
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/recommendations/queue",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbols": ["AAPL"],
            "timeframe": "1D",
            "market_mode": "equities",
            "top_n": 1,
        },
    )
    assert response.status_code == 200
    queue = response.json()["queue"]
    for row in queue:
        for forbidden in _FORBIDDEN_PAYLOAD_KEYS:
            assert forbidden not in row, (
                f"Phase B6.3 ranking surface leaked {forbidden!r} on queue row"
            )


# ── Status endpoint surfaces the formula version + guard flag ──────────


def test_momentum_ranking_status_surfaces_formula_version_and_guard() -> None:
    from macmarket_trader.recommendation.momentum_ranking import (
        build_momentum_ranking_status,
    )

    class _Settings:
        momentum_ranking_mode = "active"
        momentum_active_ranking_allowed = True
        momentum_active_delta_scale = 0.35

    status = build_momentum_ranking_status(_Settings())
    # Operators can confirm a stale deploy from the status payload alone.
    assert status.active_delta_formula_version == ACTIVE_DELTA_FORMULA_VERSION
    assert status.active_delta_formula_version == "scaled_v1"
    assert status.ranking_score_consistency_guard is True
    assert RANKING_SCORE_CONSISTENCY_GUARD is True
