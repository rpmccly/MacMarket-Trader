"""Phase B3 status tests.

These tests pin the read-only Momentum ranking status surface:

- :func:`build_momentum_ranking_status` is pure, never raises on bad
  input, and always resolves to ``shadow`` for invalid env values.
- The ``GET /user/momentum-ranking-status`` endpoint requires an
  approved user, has no side effects, and emits the typed payload.

Recommendation approval, ranking math, paper-order behavior, options/
replay/HACO behavior are not exercised — Phase B3 is operator status
visibility only.
"""

from __future__ import annotations

from copy import copy
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.config import settings as _settings
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.recommendation.momentum_ranking import (
    MomentumRankingConfig,
    build_momentum_ranking_status,
)
from macmarket_trader.storage.db import SessionLocal, init_db


def _settings_with_mode(value: str | None) -> SimpleNamespace:
    """Return a minimal settings-shaped object with the given mode."""
    return SimpleNamespace(momentum_ranking_mode=value)


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


# ── Pure builder ───────────────────────────────────────────────────────────


def test_default_resolved_status_is_shadow_and_pending_parity(tmp_path: Path) -> None:
    status = build_momentum_ranking_status(
        _settings_with_mode("shadow"),
        manifest_path=tmp_path / "manifest.json",
    )
    assert status.mode == "shadow"
    assert status.default_mode == "shadow"
    assert status.env_var == "MACMARKET_MOMENTUM_RANKING_MODE"
    assert status.enabled is True
    assert status.applied_by_default is False
    assert status.parity_fixture_manifest_present is False
    assert status.real_thinkorswim_parity_pending is True
    assert status.parity_status == "pending_thinkorswim_fixture_validation"
    assert "thinkorswim_parity_pending" in status.reason_codes
    # Guardrails always include the deterministic-context line.
    assert any("does not approve" in g.lower() for g in status.guardrails)


def test_off_mode_reports_disabled_and_not_applied(tmp_path: Path) -> None:
    status = build_momentum_ranking_status(
        _settings_with_mode("off"),
        manifest_path=tmp_path / "manifest.json",
    )
    assert status.mode == "off"
    assert status.enabled is False
    assert status.applied_by_default is False
    assert status.active_mode_warning is None


def test_active_mode_with_parity_pending_emits_warning(tmp_path: Path) -> None:
    status = build_momentum_ranking_status(
        _settings_with_mode("active"),
        manifest_path=tmp_path / "manifest.json",
    )
    assert status.mode == "active"
    assert status.enabled is True
    assert status.applied_by_default is True
    assert status.active_mode_warning is not None
    assert "parity" in status.active_mode_warning.lower()
    assert "active_mode_with_parity_pending" in status.reason_codes


def test_active_mode_with_parity_required_and_pending_emits_blocked_reason(tmp_path: Path) -> None:
    status = build_momentum_ranking_status(
        _settings_with_mode("active"),
        manifest_path=tmp_path / "manifest.json",
        config=MomentumRankingConfig(mode="active", parity_required_for_active=True),
    )
    assert "active_blocked_parity_required" in status.reason_codes
    assert status.parity_required_for_active is True
    assert status.active_mode_warning is not None
    assert "blocked" in status.active_mode_warning.lower()


def test_invalid_env_value_resolves_to_shadow_and_emits_reason_code(tmp_path: Path) -> None:
    status = build_momentum_ranking_status(
        _settings_with_mode("garbage"),
        manifest_path=tmp_path / "manifest.json",
    )
    assert status.mode == "shadow"
    assert status.invalid_env_value is True
    assert status.raw_env_value == "garbage"
    assert "invalid_env_value_resolved_to_shadow" in status.reason_codes


def test_missing_env_value_resolves_to_shadow_without_invalid_flag(tmp_path: Path) -> None:
    status = build_momentum_ranking_status(
        _settings_with_mode(None),
        manifest_path=tmp_path / "manifest.json",
    )
    assert status.mode == "shadow"
    assert status.invalid_env_value is False
    assert "invalid_env_value_resolved_to_shadow" not in status.reason_codes


def test_manifest_present_marks_parity_validated(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{\"fixtures\":[]}", encoding="utf-8")
    status = build_momentum_ranking_status(
        _settings_with_mode("shadow"),
        manifest_path=manifest,
    )
    assert status.parity_fixture_manifest_present is True
    assert status.parity_status == "validated_against_thinkorswim_fixture"
    assert status.real_thinkorswim_parity_pending is False
    assert status.parity_fixture_manifest_path is not None
    assert "thinkorswim_parity_pending" not in status.reason_codes


def test_status_payload_carries_no_approval_or_routing_fields(tmp_path: Path) -> None:
    status = build_momentum_ranking_status(
        _settings_with_mode("active"),
        manifest_path=tmp_path / "manifest.json",
    )
    dumped = status.model_dump(mode="json")
    forbidden = {"approved", "rejected", "approve", "reject", "side", "shares", "size", "order_id", "route"}
    overlap = forbidden & dumped.keys()
    assert overlap == set(), f"status payload must not carry approval/routing fields, found: {overlap}"


# ── /user/momentum-ranking-status endpoint ─────────────────────────────────


def test_status_endpoint_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/user/momentum-ranking-status")
    assert response.status_code == 401


def test_status_endpoint_returns_shadow_default(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "shadow")
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "shadow"
    assert payload["default_mode"] == "shadow"
    assert payload["env_var"] == "MACMARKET_MOMENTUM_RANKING_MODE"
    assert payload["enabled"] is True
    assert payload["applied_by_default"] is False
    # Either pending or validated depending on whether parity manifest landed.
    assert payload["parity_status"] in {
        "pending_thinkorswim_fixture_validation",
        "validated_against_thinkorswim_fixture",
    }
    # Phase B3 guardrails always include the deterministic-context line.
    assert any("does not approve" in g.lower() for g in payload["guardrails"])


def test_status_endpoint_returns_off_when_settings_off(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "off")
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "off"
    assert payload["enabled"] is False
    assert payload["applied_by_default"] is False


def test_status_endpoint_returns_active_with_warning_when_parity_pending(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "active")
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "active"
    if payload["real_thinkorswim_parity_pending"]:
        assert payload["active_mode_warning"]
        assert "active_mode_with_parity_pending" in payload["reason_codes"]
    else:
        assert payload["active_mode_warning"] is None


def test_status_endpoint_resolves_invalid_env_to_shadow(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "bogus-mode")
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "shadow"
    assert payload["invalid_env_value"] is True
    assert "invalid_env_value_resolved_to_shadow" in payload["reason_codes"]


def test_status_endpoint_does_not_trigger_market_provider_calls(monkeypatch) -> None:
    """No provider/market-data side effects when the endpoint runs."""
    called: list[str] = []

    def _no_provider(*args: object, **kwargs: object) -> None:  # pragma: no cover - guard
        called.append("provider")
        raise AssertionError("Phase B3 status endpoint must not call providers")

    # Cover the most likely market-data entry points used by other endpoints.
    import macmarket_trader.api.routes.admin as admin_module

    monkeypatch.setattr(admin_module.market_data_service, "historical_bars", _no_provider, raising=False)
    monkeypatch.setattr(admin_module.market_data_service, "provider_health", _no_provider, raising=False)
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "shadow")

    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/momentum-ranking-status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    assert called == []


# ── Settings mutation guard ────────────────────────────────────────────────


def test_status_builder_does_not_mutate_settings(monkeypatch) -> None:
    original = _settings.momentum_ranking_mode
    settings_copy = copy(_settings)
    monkeypatch.setattr(_settings, "momentum_ranking_mode", "active")
    build_momentum_ranking_status(_settings)
    # The builder must read the value only.
    assert _settings.momentum_ranking_mode == "active"
    # Restore.
    monkeypatch.setattr(_settings, "momentum_ranking_mode", original)
    assert settings_copy.momentum_ranking_mode == original
