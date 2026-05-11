"""Phase C0 — True Momentum strategy-family scaffolding tests.

These tests pin the read-only Phase C0 surface:

- :func:`build_true_momentum_strategy_status` is pure, never raises on
  bad input, and defaults to ``disabled``.
- The guard env var blocks ``research_preview`` / ``active`` requests.
- ``active`` is reserved — Phase C0 forces it to ``research_preview``.
- :func:`list_true_momentum_strategy_family_specs` returns exactly the
  three planned families with no action / approval / routing fields.
- :func:`evaluate_true_momentum_strategy_preview` never emits queue
  candidates and never returns entry/stop/target/size/approval/routing
  fields.
- ``GET /user/true-momentum-strategy-families/status`` requires an
  approved user, has no side effects, and emits the typed payload.
- No active Phase C entries appear in the existing ``StrategyRegistry``.
- The Phase C evaluator is not imported by the ranking engine or
  recommendation generator.

Recommendation approval, ranking math, paper-order behavior, options /
replay / HACO behavior are not exercised — Phase C0 is scaffold-only.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.config import settings as _settings
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import (
    TrueMomentumStrategyFamilySpecPayload,
    TrueMomentumStrategyFamilyStatusPayload,
    TrueMomentumStrategyModeStatus,
)
from macmarket_trader.recommendation.true_momentum_strategy_families import (
    GUARD_ENV_VAR,
    IMPLEMENTATION_STATUS,
    MODE_ENV_VAR,
    PHASE,
    REASON_INVALID_ENV_VALUE_RESOLVED_TO_DISABLED,
    REASON_THINKORSWIM_PARITY_PENDING,
    REASON_TRUE_MOMENTUM_ACTIVE_NOT_IMPLEMENTED,
    REASON_TRUE_MOMENTUM_STRATEGY_MODE_BLOCKED_BY_GUARD,
    TrueMomentumStrategyFamilySpec,
    TrueMomentumStrategyStatus,
    build_true_momentum_strategy_status,
    evaluate_true_momentum_strategy_preview,
    list_true_momentum_strategy_family_specs,
)
from macmarket_trader.storage.db import SessionLocal, init_db

REPO_ROOT = Path(__file__).resolve().parent.parent


# Identifiers / fields that must never appear in any Phase C0 surface.
FORBIDDEN_ACTION_FIELDS = {
    "entry",
    "entry_price",
    "stop",
    "stop_price",
    "target",
    "target_price",
    "size",
    "shares",
    "contracts",
    "approve",
    "approved",
    "reject",
    "rejected",
    "route",
    "order_id",
    "buy_now",
    "sell_now",
    "enter_now",
    "short_now",
}


def _settings_ns(
    *,
    mode: str | None = None,
    guard: object = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        true_momentum_strategy_mode=mode,
        allow_true_momentum_strategy_families=guard,
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


# ── Pure builder ───────────────────────────────────────────────────────


def test_default_mode_is_disabled() -> None:
    status = build_true_momentum_strategy_status(_settings_ns())
    assert isinstance(status, TrueMomentumStrategyStatus)
    assert status.requested_mode == "disabled"
    assert status.effective_mode == "disabled"
    assert status.enabled is False
    assert status.guard_enabled is False
    assert status.phase == PHASE
    assert status.implementation_status == IMPLEMENTATION_STATUS
    assert status.mode_env_var == MODE_ENV_VAR
    assert status.guard_env_var == GUARD_ENV_VAR
    assert status.parity_required_for_active is True
    assert REASON_THINKORSWIM_PARITY_PENDING in status.reason_codes


def test_research_preview_without_guard_is_blocked() -> None:
    status = build_true_momentum_strategy_status(
        _settings_ns(mode="research_preview", guard=False)
    )
    assert status.requested_mode == "research_preview"
    assert status.effective_mode == "disabled"
    assert status.enabled is False
    assert REASON_TRUE_MOMENTUM_STRATEGY_MODE_BLOCKED_BY_GUARD in status.reason_codes


def test_active_without_guard_is_blocked() -> None:
    status = build_true_momentum_strategy_status(
        _settings_ns(mode="active", guard=False)
    )
    assert status.requested_mode == "active"
    assert status.effective_mode == "disabled"
    assert status.enabled is False
    assert REASON_TRUE_MOMENTUM_STRATEGY_MODE_BLOCKED_BY_GUARD in status.reason_codes


def test_research_preview_with_guard_resolves_to_research_preview() -> None:
    status = build_true_momentum_strategy_status(
        _settings_ns(mode="research_preview", guard="true")
    )
    assert status.requested_mode == "research_preview"
    assert status.effective_mode == "research_preview"
    assert status.enabled is True
    assert status.guard_enabled is True
    assert (
        REASON_TRUE_MOMENTUM_STRATEGY_MODE_BLOCKED_BY_GUARD not in status.reason_codes
    )


def test_active_with_guard_is_forced_to_research_preview_until_C1() -> None:
    status = build_true_momentum_strategy_status(
        _settings_ns(mode="active", guard="true")
    )
    assert status.requested_mode == "active"
    # Active is reserved in Phase C0. The guard alone does not unlock it.
    assert status.effective_mode == "research_preview"
    assert REASON_TRUE_MOMENTUM_ACTIVE_NOT_IMPLEMENTED in status.reason_codes


@pytest.mark.parametrize("truthy", ["true", "TRUE", "True", "1", "yes", "YES", "on", "ON"])
def test_guard_accepts_truthy_string_variants(truthy: str) -> None:
    status = build_true_momentum_strategy_status(
        _settings_ns(mode="research_preview", guard=truthy)
    )
    assert status.guard_enabled is True
    assert status.effective_mode == "research_preview"


@pytest.mark.parametrize("falsy", ["", "false", "0", "no", "off", "garbage"])
def test_guard_rejects_falsy_or_unknown_string_variants(falsy: str) -> None:
    status = build_true_momentum_strategy_status(
        _settings_ns(mode="research_preview", guard=falsy)
    )
    assert status.guard_enabled is False
    assert status.effective_mode == "disabled"
    assert REASON_TRUE_MOMENTUM_STRATEGY_MODE_BLOCKED_BY_GUARD in status.reason_codes


def test_invalid_mode_resolves_to_disabled_with_reason_code() -> None:
    status = build_true_momentum_strategy_status(
        _settings_ns(mode="garbage", guard="true")
    )
    assert status.requested_mode == "disabled"
    assert status.effective_mode == "disabled"
    assert status.invalid_env_value is True
    assert REASON_INVALID_ENV_VALUE_RESOLVED_TO_DISABLED in status.reason_codes


def test_missing_mode_resolves_to_disabled_without_invalid_flag() -> None:
    status = build_true_momentum_strategy_status(_settings_ns())
    assert status.requested_mode == "disabled"
    assert status.invalid_env_value is False
    assert REASON_INVALID_ENV_VALUE_RESOLVED_TO_DISABLED not in status.reason_codes


# ── Spec listing ───────────────────────────────────────────────────────


EXPECTED_FAMILY_IDS = (
    "true_momentum_continuation",
    "true_momentum_pullback",
    "true_momentum_reversal_watch",
)


def test_lists_exactly_three_family_specs() -> None:
    specs = list_true_momentum_strategy_family_specs()
    assert len(specs) == 3
    assert tuple(spec.id for spec in specs) == EXPECTED_FAMILY_IDS


def test_specs_are_planned_and_carry_no_action_fields() -> None:
    specs = list_true_momentum_strategy_family_specs()
    for spec in specs:
        assert isinstance(spec, TrueMomentumStrategyFamilySpec)
        assert spec.status == "planned"
        assert spec.phase == PHASE
        assert spec.implementation_status == IMPLEMENTATION_STATUS
        assert spec.intended_direction in {"long", "short", "watch"}
        # Specs never expose entry / stop / target / order fields.
        dumped_keys = set(spec.__dataclass_fields__.keys())
        assert not (dumped_keys & FORBIDDEN_ACTION_FIELDS)
        # Spec text never contains action language.
        text = " ".join(
            [
                spec.id,
                spec.label,
                spec.description,
                *spec.required_inputs,
                *spec.deterministic_signals,
                *spec.guardrails,
            ]
        ).lower()
        for phrase in ("buy now", "sell now", "enter now", "short now", "route order", "auto approve"):
            assert phrase not in text


def test_specs_declare_not_allowed_actions_for_clarity() -> None:
    for spec in list_true_momentum_strategy_family_specs():
        for action in (
            "approve_trade",
            "reject_trade",
            "size_trade",
            "route_order",
            "open_position",
            "close_position",
            "settle_position",
        ):
            assert action in spec.not_allowed_actions


# ── Preview evaluator ──────────────────────────────────────────────────


def test_evaluate_preview_returns_no_candidates_in_disabled_mode() -> None:
    result = evaluate_true_momentum_strategy_preview(_settings_ns())
    assert result["previews"] == []
    assert result["previews_generated"] is False
    assert result["phase"] == PHASE
    assert result["implementation_status"] == IMPLEMENTATION_STATUS


def test_evaluate_preview_returns_no_candidates_in_research_preview() -> None:
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true")
    )
    assert result["previews"] == []
    assert result["previews_generated"] is False


def test_evaluate_preview_returns_no_candidates_in_active_mode_too() -> None:
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="active", guard="true")
    )
    assert result["previews"] == []
    assert result["previews_generated"] is False


def test_evaluate_preview_payload_has_no_action_fields() -> None:
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true")
    )
    assert "entry" not in result
    assert "stop" not in result
    assert "target" not in result
    assert "size" not in result
    assert "order_id" not in result
    assert "approve" not in result
    assert "route" not in result


# ── Pydantic payload ───────────────────────────────────────────────────


def test_status_payload_alias_resolves_to_same_schema() -> None:
    assert TrueMomentumStrategyModeStatus is TrueMomentumStrategyFamilyStatusPayload


def test_status_payload_carries_no_approval_or_routing_fields() -> None:
    payload = TrueMomentumStrategyFamilyStatusPayload()
    dumped = payload.model_dump(mode="json")
    overlap = FORBIDDEN_ACTION_FIELDS & set(dumped.keys())
    assert overlap == set()


def test_spec_payload_carries_no_approval_or_routing_fields() -> None:
    payload = TrueMomentumStrategyFamilySpecPayload(
        id="x",
        label="X",
        description="desc",
        intended_direction="watch",
    )
    dumped = payload.model_dump(mode="json")
    overlap = FORBIDDEN_ACTION_FIELDS & set(dumped.keys())
    assert overlap == set()


# ── Read-only endpoint ─────────────────────────────────────────────────


def test_status_endpoint_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/user/true-momentum-strategy-families/status")
    assert response.status_code == 401


def test_status_endpoint_default_disabled(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "true_momentum_strategy_mode", "disabled")
    monkeypatch.setattr(_settings, "allow_true_momentum_strategy_families", False)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/true-momentum-strategy-families/status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_mode"] == "disabled"
    assert payload["effective_mode"] == "disabled"
    assert payload["enabled"] is False
    assert payload["guard_enabled"] is False
    assert payload["phase"] == "C0"
    assert payload["implementation_status"] == "scaffold_only"
    assert payload["mode_env_var"] == MODE_ENV_VAR
    assert payload["guard_env_var"] == GUARD_ENV_VAR
    assert isinstance(payload["family_specs"], list)
    assert len(payload["family_specs"]) == 3
    ids = [spec["id"] for spec in payload["family_specs"]]
    assert ids == list(EXPECTED_FAMILY_IDS)


def test_status_endpoint_research_preview_with_guard(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "true_momentum_strategy_mode", "research_preview")
    monkeypatch.setattr(_settings, "allow_true_momentum_strategy_families", True)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/true-momentum-strategy-families/status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_mode"] == "research_preview"
    assert payload["effective_mode"] == "research_preview"
    assert payload["enabled"] is True
    assert payload["guard_enabled"] is True


def test_status_endpoint_blocks_research_preview_without_guard(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "true_momentum_strategy_mode", "research_preview")
    monkeypatch.setattr(_settings, "allow_true_momentum_strategy_families", False)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/true-momentum-strategy-families/status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["effective_mode"] == "disabled"
    assert (
        REASON_TRUE_MOMENTUM_STRATEGY_MODE_BLOCKED_BY_GUARD in payload["reason_codes"]
    )


def test_status_endpoint_does_not_call_market_provider(monkeypatch) -> None:
    """No provider/market-data side effects when the endpoint runs."""

    def _no_provider(*args: object, **kwargs: object) -> None:  # pragma: no cover - guard
        raise AssertionError("Phase C0 status endpoint must not call providers")

    import macmarket_trader.api.routes.admin as admin_module

    monkeypatch.setattr(
        admin_module.market_data_service, "historical_bars", _no_provider, raising=False
    )
    monkeypatch.setattr(
        admin_module.market_data_service, "provider_health", _no_provider, raising=False
    )
    monkeypatch.setattr(_settings, "true_momentum_strategy_mode", "disabled")
    monkeypatch.setattr(_settings, "allow_true_momentum_strategy_families", False)

    client = TestClient(app)
    _approve_default_user(client)
    response = client.get(
        "/user/true-momentum-strategy-families/status",
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200


# ── Isolation guards ───────────────────────────────────────────────────


def test_strategy_registry_has_no_generating_phase_c_entries() -> None:
    from macmarket_trader.strategy_registry import REGISTRY

    # Phase C0 is scaffold-only — no registry entries should exist that
    # could be discovered by the recommendation generator. The
    # `list_strategies` callsites enumerate REGISTRY as-is so even a
    # disabled entry would surface in pickers.
    for entry in REGISTRY:
        assert "true_momentum" not in entry.strategy_id


def test_ranking_engine_does_not_import_phase_c_evaluator() -> None:
    from macmarket_trader import ranking_engine

    source = Path(ranking_engine.__file__).read_text(encoding="utf-8")
    assert "true_momentum_strategy_families" not in source
    assert "evaluate_true_momentum_strategy_preview" not in source
    assert "list_true_momentum_strategy_family_specs" not in source


def test_recommendation_service_does_not_import_phase_c_evaluator() -> None:
    candidates = (
        REPO_ROOT / "src/macmarket_trader/recommendation/__init__.py",
        REPO_ROOT / "src/macmarket_trader/recommendation/momentum_ranking.py",
    )
    for path in candidates:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        # The evaluator/spec module is not consumed anywhere in the
        # recommendation pipeline at Phase C0.
        assert "evaluate_true_momentum_strategy_preview" not in source
        assert "build_true_momentum_strategy_status" not in source


def test_paper_order_helpers_do_not_import_phase_c_module() -> None:
    candidates = [
        REPO_ROOT / "apps/web/lib/orders-helpers.ts",
        REPO_ROOT / "apps/web/lib/recommendations.ts",
    ]
    for path in candidates:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        assert "true_momentum_strategy_families" not in source
        assert "true-momentum-strategy-families" not in source


def test_phase_c_module_does_not_import_provider_or_market_data() -> None:
    path = REPO_ROOT / "src/macmarket_trader/recommendation/true_momentum_strategy_families.py"
    source = path.read_text(encoding="utf-8")
    forbidden_imports = (
        "providers",
        "market_data",
        "alpaca",
        "polygon",
        "openai",
        "anthropic",
        "execution",
        "paper_order",
    )
    for token in forbidden_imports:
        assert f"import {token}" not in source
        assert f"from macmarket_trader.{token}" not in source


def test_phase_c_source_has_no_action_language() -> None:
    path = REPO_ROOT / "src/macmarket_trader/recommendation/true_momentum_strategy_families.py"
    text = path.read_text(encoding="utf-8").lower()
    for phrase in ("buy now", "sell now", "enter now", "short now", "auto approve", "route order"):
        assert phrase not in text
