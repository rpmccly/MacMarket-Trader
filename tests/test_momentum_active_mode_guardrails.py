"""Phase B6 — active-mode safety guard tests.

These tests pin the contract introduced by ``MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING``:

- Default deployment behavior remains ``shadow`` (no safety-guard required).
- ``MACMARKET_MOMENTUM_RANKING_MODE=active`` **without** the guard flag is
  silently downgraded to ``shadow`` and surfaces
  ``active_mode_blocked_by_safety_guard``.
- ``MACMARKET_MOMENTUM_RANKING_MODE=active`` **with** the guard flag
  truthy applies the bounded contribution exactly as Phase B1 designed.
- Approval, paper-order, sizing, and routing behavior remains untouched
  regardless of mode.

Phase B6 deliberately does **not** change recommendation approval,
paper-order, options, replay, HACO/HACOLT, ranking-math, contribution
caps, or default mode.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

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
    MomentumRankingConfig,
    build_momentum_ranking_contribution,
    build_momentum_ranking_status,
    momentum_ranking_config_from_settings,
    resolve_effective_momentum_ranking_mode,
)
from macmarket_trader.storage.db import SessionLocal, init_db


def _settings_with(mode: str | None, *, active_allowed: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        momentum_ranking_mode=mode,
        momentum_active_ranking_allowed=active_allowed,
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


# ── Pure resolution helpers ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw_mode, allow, expected_effective, expected_requested, expected_blocked",
    [
        (None, False, "shadow", "shadow", False),
        ("shadow", False, "shadow", "shadow", False),
        ("off", False, "off", "off", False),
        ("garbage", False, "shadow", "shadow", False),  # invalid falls to shadow first
        ("active", False, "shadow", "active", True),  # safety guard blocks
        ("active", True, "active", "active", False),
        ("ACTIVE", True, "active", "active", False),  # case-insensitive
    ],
)
def test_resolve_effective_mode_table(
    raw_mode: str | None,
    allow: bool,
    expected_effective: str,
    expected_requested: str,
    expected_blocked: bool,
) -> None:
    effective, requested, blocked = resolve_effective_momentum_ranking_mode(
        raw_mode, active_allowed=allow
    )
    assert effective == expected_effective
    assert requested == expected_requested
    assert blocked is expected_blocked


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        (1, True),
        (True, True),
        ("yes", True),
        ("YES", True),
        ("on", True),
        ("false", False),
        ("0", False),
        (0, False),
        (False, False),
        ("", False),
        (None, False),
        ("nonsense", False),
    ],
)
def test_truthy_resolution_for_allow_flag(raw: object, expected: bool) -> None:
    """Build the config from a settings-shaped object and confirm
    ``active_allowed`` is parsed truthy-tolerantly."""
    config = momentum_ranking_config_from_settings(
        SimpleNamespace(momentum_ranking_mode="shadow", momentum_active_ranking_allowed=raw)
    )
    assert config.active_allowed is expected


# ── Contribution behavior ──────────────────────────────────────────────────


def test_active_without_allow_falls_back_to_shadow_in_config() -> None:
    config = momentum_ranking_config_from_settings(_settings_with("active", active_allowed=False))
    assert config.mode == "shadow"
    assert config.requested_mode == "active"
    assert config.active_allowed is False


def test_active_with_allow_resolves_to_active_in_config() -> None:
    config = momentum_ranking_config_from_settings(_settings_with("active", active_allowed=True))
    assert config.mode == "active"
    assert config.requested_mode == "active"
    assert config.active_allowed is True


def _payload_stub() -> dict[str, object]:
    snap = {
        "total_score": 90,
        "total_label": "Bull",
        "total_state": "bull",
        "trend_score": 80,
        "momo_score": 70,
        "true_momentum": 65.0,
        "true_momentum_ema": 60.0,
        "true_momentum_score": 15,
        "hilo_thrust": 1,
        "hilo_score": 15,
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


def test_blocked_active_contribution_behaves_like_shadow() -> None:
    """When active is requested but blocked by the safety guard, the
    contribution must compute the shadow value but never apply it, and
    surface ``active_mode_blocked_by_safety_guard``."""
    config = MomentumRankingConfig(
        mode="shadow",  # effective
        requested_mode="active",
        active_allowed=False,
    )
    out = build_momentum_ranking_contribution(
        _payload_stub(),
        {"direction": "long"},
        config,
    )
    assert out.mode == "shadow"
    assert out.applied is False
    assert out.total_contribution == 0.0
    assert out.shadow_contribution > 0  # shadow value still computed
    assert "active_mode_blocked_by_safety_guard" in out.reason_codes


def test_allowed_active_contribution_applies() -> None:
    config = MomentumRankingConfig(
        mode="active",
        requested_mode="active",
        active_allowed=True,
    )
    out = build_momentum_ranking_contribution(
        _payload_stub(),
        {"direction": "long"},
        config,
    )
    assert out.mode == "active"
    assert out.applied is True
    assert out.total_contribution > 0
    # The safety-guard reason code must NOT appear when the guard is satisfied.
    assert "active_mode_blocked_by_safety_guard" not in out.reason_codes


def test_off_mode_short_circuits_even_when_active_is_requested_externally() -> None:
    config = MomentumRankingConfig(mode="off")
    out = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
    assert out.mode == "off"
    assert out.enabled is False
    assert out.applied is False


def test_contribution_payload_in_blocked_active_carries_no_approval_or_routing_fields() -> None:
    config = MomentumRankingConfig(mode="shadow", requested_mode="active", active_allowed=False)
    out = build_momentum_ranking_contribution(_payload_stub(), {"direction": "long"}, config)
    dumped = out.model_dump(mode="json")
    forbidden = {"approved", "rejected", "approve", "reject", "side", "shares", "size", "order_id", "route"}
    overlap = forbidden & dumped.keys()
    assert overlap == set()


# ── Ranking-engine integration ────────────────────────────────────────────


def _bars_by_symbol() -> dict[str, tuple[list[Bar], str, bool]]:
    return {"AAPL": (_bullish_bars(), "test_provider", False)}


def test_engine_blocked_active_does_not_change_scores() -> None:
    """Active requested without the allow flag must not move scores."""
    bars_by_symbol = _bars_by_symbol()
    off_score = DeterministicRankingEngine(MomentumRankingConfig(mode="off")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]["score"]

    blocked = DeterministicRankingEngine(
        MomentumRankingConfig(mode="shadow", requested_mode="active", active_allowed=False)
    ).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]

    assert blocked["score"] == off_score
    contrib = blocked["momentum_contribution"]
    assert contrib["mode"] == "shadow"
    assert contrib["applied"] is False
    assert "active_mode_blocked_by_safety_guard" in contrib["reason_codes"]


def test_engine_allowed_active_applies_and_emits_before_after_fields() -> None:
    bars_by_symbol = _bars_by_symbol()
    out = DeterministicRankingEngine(
        MomentumRankingConfig(mode="active", requested_mode="active", active_allowed=True)
    ).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    assert out["momentum_contribution"]["mode"] == "active"
    assert out["momentum_contribution"]["applied"] is True
    assert "active_mode_blocked_by_safety_guard" not in out["momentum_contribution"]["reason_codes"]
    # Phase B6 — before/after visibility fields are populated.
    assert out["score_before_momentum"] is not None
    assert out["score_after_momentum"] is not None
    assert out["momentum_score_delta"] is not None
    assert out["momentum_rank_mode"] == "active"


def test_engine_active_score_change_stays_inside_cap() -> None:
    """Phase B1 caps still hold under Phase B6."""
    bars_by_symbol = _bars_by_symbol()
    config = MomentumRankingConfig(mode="active", requested_mode="active", active_allowed=True)
    off_score = DeterministicRankingEngine(MomentumRankingConfig(mode="off")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]["score"]
    active = DeterministicRankingEngine(config).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    cap = config.max_total_contribution / config.ranking_score_scale
    floor = config.min_total_contribution / config.ranking_score_scale
    delta = active["score"] - off_score
    assert floor - 1e-9 <= delta <= cap + 1e-9
    assert 0.0 <= active["score"] <= 1.0


# ── Status builder + endpoint ─────────────────────────────────────────────


def test_status_builder_default_resolves_shadow_and_active_allowed_false(tmp_path) -> None:
    status = build_momentum_ranking_status(
        _settings_with(None),
        manifest_path=tmp_path / "manifest.json",
    )
    assert status.mode == "shadow"
    assert status.requested_mode == "shadow"
    assert status.effective_mode == "shadow"
    assert status.active_allowed is False
    assert status.active_mode_blocked is False


def test_status_builder_active_without_allow_reports_blocked(tmp_path) -> None:
    status = build_momentum_ranking_status(
        _settings_with("active", active_allowed=False),
        manifest_path=tmp_path / "manifest.json",
    )
    assert status.mode == "shadow"
    assert status.requested_mode == "active"
    assert status.effective_mode == "shadow"
    assert status.active_allowed is False
    assert status.active_mode_blocked is True
    assert status.active_mode_block_reason is not None
    assert "MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING" in status.active_mode_block_reason
    assert "active_mode_blocked_by_safety_guard" in status.reason_codes


def test_status_builder_active_with_allow_reports_active(tmp_path) -> None:
    status = build_momentum_ranking_status(
        _settings_with("active", active_allowed=True),
        manifest_path=tmp_path / "manifest.json",
    )
    assert status.mode == "active"
    assert status.requested_mode == "active"
    assert status.effective_mode == "active"
    assert status.active_allowed is True
    assert status.active_mode_blocked is False
    assert status.active_mode_block_reason is None
    assert "active_mode_blocked_by_safety_guard" not in status.reason_codes


def test_status_endpoint_default_reports_safety_guard_metadata(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "shadow")
    monkeypatch.setattr(_settings, "momentum_active_ranking_allowed", False)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_guard_env_var"] == "MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING"
    assert payload["active_allowed"] is False
    assert payload["active_mode_blocked"] is False
    assert payload["effective_mode"] == "shadow"
    assert payload["requested_mode"] == "shadow"


def test_status_endpoint_blocked_active_reports_block_reason(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "active")
    monkeypatch.setattr(_settings, "momentum_active_ranking_allowed", False)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "shadow"
    assert payload["requested_mode"] == "active"
    assert payload["effective_mode"] == "shadow"
    assert payload["active_allowed"] is False
    assert payload["active_mode_blocked"] is True
    assert "MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING" in payload["active_mode_block_reason"]
    assert "active_mode_blocked_by_safety_guard" in payload["reason_codes"]


def test_status_endpoint_active_with_allow_reports_unblocked_active(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "active")
    monkeypatch.setattr(_settings, "momentum_active_ranking_allowed", True)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "active"
    assert payload["effective_mode"] == "active"
    assert payload["active_allowed"] is True
    assert payload["active_mode_blocked"] is False
    assert payload["active_mode_block_reason"] is None
    assert "active_mode_blocked_by_safety_guard" not in payload["reason_codes"]


def test_status_endpoint_does_not_call_market_provider(monkeypatch) -> None:
    """No provider/market-data side effects when the endpoint runs."""
    called: list[str] = []

    def _no_provider(*args: object, **kwargs: object) -> None:  # pragma: no cover - guard
        called.append("provider")
        raise AssertionError("Phase B6 status endpoint must not call providers")

    import macmarket_trader.api.routes.admin as admin_module

    monkeypatch.setattr(admin_module.market_data_service, "historical_bars", _no_provider, raising=False)
    monkeypatch.setattr(admin_module.market_data_service, "provider_health", _no_provider, raising=False)
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "active")
    monkeypatch.setattr(_settings, "momentum_active_ranking_allowed", True)

    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    assert called == []
