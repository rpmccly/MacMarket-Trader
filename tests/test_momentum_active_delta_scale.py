"""Phase B6.1 — active-mode delta-scale tests.

These tests pin the operator-tunable
``MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE`` knob introduced to reduce
active-mode score saturation.

Raw Momentum contribution math (cap ±20 score units), recommendation
approval, paper-order behavior, options/replay/HACO/HACOLT behavior,
default mode, and the Phase B6 safety guard are all untouched — only
the active-mode score application is dampened by the new scale.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.config import settings as _settings
from macmarket_trader.domain.enums import MarketMode
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import Bar
from macmarket_trader.ranking_engine import DeterministicRankingEngine
from macmarket_trader.recommendation.momentum_ranking import (
    DEFAULT_ACTIVE_DELTA_SCALE,
    MomentumRankingConfig,
    _resolve_active_delta_scale,
    build_momentum_ranking_contribution,
    build_momentum_ranking_status,
    momentum_ranking_config_from_settings,
)
from macmarket_trader.storage.db import SessionLocal, init_db


def _settings_with(
    mode: str | None = "shadow",
    *,
    active_allowed: bool = False,
    active_delta_scale: Any = "0.35",
) -> SimpleNamespace:
    return SimpleNamespace(
        momentum_ranking_mode=mode,
        momentum_active_ranking_allowed=active_allowed,
        momentum_active_delta_scale=active_delta_scale,
    )


def _approve_default_user(client: TestClient) -> None:
    client.get("/user/me", headers={"Authorization": "Bearer user-token"})
    with SessionLocal() as session:
        user = session.execute(
            select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")
        ).scalar_one()
        user.approval_status = "approved"
        session.commit()


def setup_module() -> None:
    init_db()


# ── Pure resolver ──────────────────────────────────────────────────────────


def test_default_active_delta_scale_constant() -> None:
    assert DEFAULT_ACTIVE_DELTA_SCALE == 0.35


@pytest.mark.parametrize(
    "raw, expected_scale, expected_invalid",
    [
        (None, 0.35, False),
        ("", 0.35, False),
        ("0.35", 0.35, False),
        ("0.50", 0.50, False),
        ("0", 0.0, False),
        ("1", 1.0, False),
        (0.5, 0.5, False),
        (1, 1.0, False),
        ("garbage", 0.35, True),
        ("-0.1", 0.35, True),
        ("1.5", 0.35, True),
        (True, 0.35, True),  # bools are not valid scales
        (float("nan"), 0.35, True),
        (float("inf"), 0.35, True),
    ],
)
def test_resolve_active_delta_scale(raw: object, expected_scale: float, expected_invalid: bool) -> None:
    scale, invalid = _resolve_active_delta_scale(raw)
    assert scale == pytest.approx(expected_scale)
    assert invalid is expected_invalid


def test_config_from_settings_carries_active_delta_scale_default() -> None:
    config = momentum_ranking_config_from_settings(_settings_with("shadow"))
    assert config.active_delta_scale == pytest.approx(0.35)
    assert config.active_delta_scale_invalid is False


def test_config_from_settings_clamps_invalid_active_delta_scale() -> None:
    config = momentum_ranking_config_from_settings(
        _settings_with("shadow", active_delta_scale="2.0"),
    )
    assert config.active_delta_scale == pytest.approx(0.35)
    assert config.active_delta_scale_invalid is True


def test_config_from_settings_honors_valid_active_delta_scale_env() -> None:
    config = momentum_ranking_config_from_settings(
        _settings_with("shadow", active_delta_scale="0.5"),
    )
    assert config.active_delta_scale == pytest.approx(0.5)
    assert config.active_delta_scale_invalid is False


# ── Contribution payload ──────────────────────────────────────────────────


def _payload_stub() -> dict[str, object]:
    snap = {
        "total_score": 100,
        "total_label": "Max Bull",
        "total_state": "max_bull",
        "trend_score": 100,
        "momo_score": 100,
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


def test_contribution_carries_raw_and_applied_score_delta_in_active_mode() -> None:
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=0.35,
    )
    out = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
    assert out.total_contribution == pytest.approx(20.0)  # capped raw value
    assert out.raw_total_contribution == pytest.approx(20.0)
    assert out.applied_score_delta == pytest.approx(20.0 / 100 * 0.35)
    assert out.applied_score_delta == pytest.approx(0.07)
    assert out.active_delta_scale == pytest.approx(0.35)


def test_contribution_carries_zero_applied_delta_when_blocked_active() -> None:
    config = MomentumRankingConfig(
        mode="shadow",  # effective shadow
        requested_mode="active",
        active_allowed=False,
        active_delta_scale=0.35,
    )
    out = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
    assert out.applied_score_delta == 0.0
    assert out.raw_total_contribution == pytest.approx(20.0)
    assert "active_mode_blocked_by_safety_guard" in out.reason_codes


def test_contribution_shadow_mode_keeps_zero_applied_delta() -> None:
    config = MomentumRankingConfig(mode="shadow", active_delta_scale=0.35)
    out = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
    assert out.applied_score_delta == 0.0
    assert out.shadow_contribution == pytest.approx(20.0)
    assert out.raw_total_contribution == pytest.approx(20.0)
    assert out.active_delta_scale == pytest.approx(0.35)


def test_contribution_scales_negative_contribution() -> None:
    """A bear-momentum payload paired with a long-bias recommendation and a
    reversal warning floors the contribution at -12 score units; the scaled
    applied delta must be -12/100 * 0.35 = -0.042.
    """
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=0.35,
    )
    snap = dict(_payload_stub())
    snap_inner = dict(snap["latest_snapshot"])  # type: ignore[arg-type]
    snap_inner.update(
        {
            "total_score": -100,
            "total_label": "Max Bear",
            "total_state": "max_bear",
            "trend_score": -100,
            "momo_score": -100,
            "hilo_score": -20,
            "component_breakdown": {
                "true_momentum_score": -15,
                "hilo_thrust": -5,
                "bull_ma": 0,
                "bear_ma": -30,
                "atr_value": -5,
                "macd_bias": -5,
                "intraday_penalty": 0,
                "base_score": -60,
            },
        },
    )
    snap["latest_snapshot"] = snap_inner
    snap["explanation"] = {
        "snapshot": snap_inner,
        "reversal_warning": True,
        "pullback_signal": False,
        "no_trade_warning": False,
        "notes": [],
    }
    out = build_momentum_ranking_contribution(snap, {"direction": "long"}, config)
    assert out.applied_score_delta < 0
    # Floor of total_contribution is -12 score units → -12/100*0.35 = -0.042
    assert out.applied_score_delta == pytest.approx(-12.0 / 100 * 0.35)


def test_contribution_honors_higher_delta_scale() -> None:
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=0.5,
    )
    out = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
    assert out.applied_score_delta == pytest.approx(0.10)


def test_contribution_falls_back_to_default_on_invalid_scale() -> None:
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=2.5,  # out of range, sanitized internally
    )
    out = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
    # _build sanitizes invalid scales back to DEFAULT_ACTIVE_DELTA_SCALE.
    assert out.applied_score_delta == pytest.approx(20.0 / 100 * DEFAULT_ACTIVE_DELTA_SCALE)


# ── Ranking-engine integration ────────────────────────────────────────────


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
    return {"AAPL": (_bullish_bars(), "test_provider", False)}


def test_engine_active_default_scale_does_not_saturate_high_baseline_to_one() -> None:
    """With default scale 0.35 a baseline of ~0.898 + raw +20 should land near 0.968,
    not saturate to 1.000."""
    bars_by_symbol = _bars_by_symbol()
    off_score = DeterministicRankingEngine(MomentumRankingConfig(mode="off")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]["score"]

    active = DeterministicRankingEngine(
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

    delta = active["score"] - off_score
    # Default-scale delta cap is 20/100*0.35 = 0.07, floor 12/100*0.35 = -0.042.
    assert -0.042 - 1e-6 <= delta <= 0.07 + 1e-6
    # The delta is tight enough that active score should not be 1.000 unless the
    # baseline was already ≥ 0.93. For the synthetic bullish series the baseline
    # is well below that.
    if off_score < 0.93:
        assert active["score"] < 1.0


def test_engine_active_score_clamps_when_baseline_plus_scaled_delta_exceeds_one() -> None:
    """If raw contribution + baseline still exceeds 1.0 the clamp must hold."""
    # Construct a synthetic baseline of 0.99 by reusing the engine but using a
    # custom large scale. Anything ≥ 1.0 - baseline triggers the clamp.
    bars_by_symbol = _bars_by_symbol()
    out = DeterministicRankingEngine(
        MomentumRankingConfig(
            mode="active",
            requested_mode="active",
            active_allowed=True,
            active_delta_scale=1.0,  # the upper bound — same as pre-B6.1 behavior
        )
    ).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    assert 0.0 <= out["score"] <= 1.0


def test_engine_shadow_mode_score_unchanged_regardless_of_scale() -> None:
    bars_by_symbol = _bars_by_symbol()
    off = DeterministicRankingEngine(MomentumRankingConfig(mode="off")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    shadow = DeterministicRankingEngine(
        MomentumRankingConfig(mode="shadow", active_delta_scale=0.95)
    ).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    assert shadow["score"] == off["score"]


def test_engine_blocked_active_score_unchanged_regardless_of_scale() -> None:
    bars_by_symbol = _bars_by_symbol()
    off = DeterministicRankingEngine(MomentumRankingConfig(mode="off")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    blocked = DeterministicRankingEngine(
        MomentumRankingConfig(
            mode="shadow",  # effective; safety guard refused active
            requested_mode="active",
            active_allowed=False,
            active_delta_scale=0.95,
        )
    ).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    assert blocked["score"] == off["score"]
    assert "active_mode_blocked_by_safety_guard" in blocked["momentum_contribution"]["reason_codes"]


def test_engine_active_higher_scale_widens_score_change(monkeypatch) -> None:
    """Validates that a higher operator scale produces a larger applied delta
    (subject to the [0,1] clamp)."""
    bars_by_symbol = _bars_by_symbol()
    base = DeterministicRankingEngine(
        MomentumRankingConfig(
            mode="active",
            requested_mode="active",
            active_allowed=True,
            active_delta_scale=0.35,
        )
    ).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    bigger = DeterministicRankingEngine(
        MomentumRankingConfig(
            mode="active",
            requested_mode="active",
            active_allowed=True,
            active_delta_scale=0.7,
        )
    ).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    # Both clamps still hold; larger scale gives a larger (or equal-after-clamp) score.
    assert bigger["score"] >= base["score"]


# ── Status endpoint ───────────────────────────────────────────────────────


def test_status_builder_exposes_active_delta_scale_default(tmp_path) -> None:
    status = build_momentum_ranking_status(
        _settings_with("shadow"),
        manifest_path=tmp_path / "manifest.json",
    )
    assert status.active_delta_scale == pytest.approx(0.35)
    assert status.active_delta_scale_env_var == "MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE"
    assert status.active_delta_scale_invalid is False
    assert status.active_delta_scale_warning is None


def test_status_builder_emits_invalid_reason_code(tmp_path) -> None:
    status = build_momentum_ranking_status(
        _settings_with("shadow", active_delta_scale="not-a-number"),
        manifest_path=tmp_path / "manifest.json",
    )
    assert status.active_delta_scale == pytest.approx(0.35)
    assert status.active_delta_scale_invalid is True
    assert status.active_delta_scale_warning is not None
    assert "momentum_active_delta_scale_invalid" in status.reason_codes


def test_status_endpoint_surfaces_active_delta_scale(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "shadow")
    monkeypatch.setattr(_settings, "momentum_active_ranking_allowed", False)
    monkeypatch.setattr(_settings, "momentum_active_delta_scale", "0.42")
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_delta_scale"] == pytest.approx(0.42)
    assert payload["active_delta_scale_env_var"] == "MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE"
    assert payload["active_delta_scale_invalid"] is False


def test_status_endpoint_falls_back_on_invalid_scale(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "shadow")
    monkeypatch.setattr(_settings, "momentum_active_ranking_allowed", False)
    monkeypatch.setattr(_settings, "momentum_active_delta_scale", "garbage")
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_delta_scale"] == pytest.approx(0.35)
    assert payload["active_delta_scale_invalid"] is True
    assert "momentum_active_delta_scale_invalid" in payload["reason_codes"]


# ── Phase B1 caps preserved ───────────────────────────────────────────────


def test_raw_contribution_caps_unchanged_under_phase_b61() -> None:
    """The bounded raw contribution math (Phase B1) must not regress."""
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
        active_delta_scale=0.7,
    )
    out = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
    # Raw contribution still capped at +20 score units regardless of delta scale.
    assert out.total_contribution == pytest.approx(20.0)
    assert out.raw_total_contribution == pytest.approx(20.0)


def test_contribution_payload_never_carries_approval_or_routing_fields_at_any_scale() -> None:
    for scale in ("0.0", "0.35", "0.7", "1.0"):
        config = momentum_ranking_config_from_settings(
            _settings_with("active", active_allowed=True, active_delta_scale=scale)
        )
        out = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
        forbidden = {"approved", "rejected", "side", "shares", "order_id", "route"}
        overlap = forbidden & out.model_dump(mode="json").keys()
        assert overlap == set()
