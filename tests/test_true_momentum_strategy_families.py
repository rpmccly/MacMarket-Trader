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
    PREVIEW_DETERMINISTIC_NOTE,
    PREVIEW_IMPLEMENTATION_STATUS,
    PREVIEW_PHASE,
    REASON_INVALID_ENV_VALUE_RESOLVED_TO_DISABLED,
    REASON_THINKORSWIM_PARITY_PENDING,
    REASON_TRUE_MOMENTUM_ACTIVE_NOT_IMPLEMENTED,
    REASON_TRUE_MOMENTUM_STRATEGY_MODE_BLOCKED_BY_GUARD,
    TrueMomentumStrategyFamilySpec,
    TrueMomentumStrategyPreviewCandidate,
    TrueMomentumStrategyPreviewResult,
    TrueMomentumStrategyPreviewSummary,
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


def test_evaluate_preview_in_research_preview_with_no_candidates_runs_classifier() -> None:
    # Phase C1: research_preview mode runs the classifier even when the
    # caller passes no candidates. The output is no previews + the
    # no-match reason code, not a "feature disabled" signal.
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true")
    )
    assert result["previews"] == []
    assert result["previews_generated"] is True
    assert "true_momentum_strategy_mode_disabled" not in result["status"].reason_codes
    assert "true_momentum_preview_no_candidates" in result["status"].reason_codes


def test_evaluate_preview_active_requested_with_guard_degrades_to_research_preview() -> None:
    # Phase C1: active mode is still reserved. With the guard truthy
    # the effective mode degrades to research_preview, so the classifier
    # runs but the result carries the active-not-implemented reason.
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="active", guard="true")
    )
    assert result["previews"] == []
    assert result["previews_generated"] is True
    assert (
        "true_momentum_strategy_active_mode_not_implemented"
        in result["status"].reason_codes
    )


# ── Phase C1 — research-preview classifier ─────────────────────────────


def _contribution(
    *,
    mode: str = "active",
    applied: bool = True,
    total_score: int | None = 80,
    total_label: str | None = "Bull",
    trend_score: float | None = 75.0,
    momo_score: float | None = 72.0,
    raw_total_contribution: float = 20.0,
    applied_score_delta: float = 0.07,
    inferred_direction: str = "long",
    pullback_signal: bool = False,
    reversal_warning: bool = False,
    no_trade_warning: bool = False,
    reason_codes: list[str] | None = None,
    active_delta_scale: float = 0.35,
) -> dict:
    return {
        "mode": mode,
        "enabled": True,
        "applied": applied,
        "raw_total_contribution": raw_total_contribution,
        "applied_score_delta": applied_score_delta,
        "total_contribution": raw_total_contribution,
        "shadow_contribution": raw_total_contribution,
        "total_score": total_score,
        "total_label": total_label,
        "trend_score": trend_score,
        "momo_score": momo_score,
        "inferred_direction": inferred_direction,
        "pullback_signal": pullback_signal,
        "reversal_warning": reversal_warning,
        "no_trade_warning": no_trade_warning,
        "reason_codes": list(reason_codes) if reason_codes else [],
        "active_delta_scale": active_delta_scale,
    }


def _queue_candidate(
    *,
    symbol: str,
    strategy: str = "Event Continuation",
    rank: int = 1,
    score: float = 0.95,
    score_before_momentum: float = 0.88,
    contribution: dict | None = None,
    score_consistency_status: str = "ok",
) -> dict:
    return {
        "symbol": symbol,
        "strategy": strategy,
        "rank": rank,
        "score": score,
        "score_before_momentum": score_before_momentum,
        "score_after_momentum": score,
        "momentum_score_delta": score - score_before_momentum,
        "momentum_realized_score_delta": score - score_before_momentum,
        "momentum_contribution": contribution if contribution is not None else _contribution(),
        "score_consistency_status": score_consistency_status,
    }


def test_evaluate_preview_classifies_continuation_candidate() -> None:
    queue = [
        _queue_candidate(
            symbol="XLK",
            strategy="Event Continuation",
            contribution=_contribution(
                total_score=85,
                total_label="Bull",
                trend_score=78,
                momo_score=73,
                raw_total_contribution=20.0,
                inferred_direction="long",
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    assert result["previews_generated"] is True
    previews = result["previews"]
    assert len(previews) == 1
    preview = previews[0]
    assert isinstance(preview, TrueMomentumStrategyPreviewCandidate)
    assert preview.family_id == "true_momentum_continuation"
    assert preview.family_label == "True Momentum Continuation"
    assert preview.symbol == "XLK"
    assert preview.match_strength == "strong"
    assert preview.non_actionable is True
    assert "true_momentum_continuation_match" in preview.reason_codes
    assert "momentum_total_label_bullish" in preview.reason_codes
    assert "trend_alignment_long_confirmed" in preview.reason_codes
    assert "momo_score_long_confirmed" in preview.reason_codes


def test_evaluate_preview_classifies_continuation_as_moderate_when_trend_or_momo_weak() -> None:
    queue = [
        _queue_candidate(
            symbol="QQQ",
            strategy="Breakout / Prior-Day High",
            contribution=_contribution(
                total_score=82,
                total_label="Bull",
                trend_score=65,  # below 70 → not strong
                momo_score=68,
                raw_total_contribution=18.0,
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    assert len(result["previews"]) == 1
    preview = result["previews"][0]
    assert preview.family_id == "true_momentum_continuation"
    assert preview.match_strength == "moderate"


def test_evaluate_preview_classifies_pullback_via_signal_flag() -> None:
    queue = [
        _queue_candidate(
            symbol="IWM",
            strategy="Pullback / Trend Continuation",
            contribution=_contribution(
                total_score=82,
                total_label="Bull",
                trend_score=72,
                momo_score=74,
                raw_total_contribution=15.0,
                pullback_signal=True,
                inferred_direction="long",
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    previews = result["previews"]
    assert len(previews) == 1
    assert previews[0].family_id == "true_momentum_pullback"
    assert previews[0].match_strength == "strong"
    assert "true_momentum_pullback_match" in previews[0].reason_codes
    assert "momentum_pullback_signal_active" in previews[0].reason_codes


def test_evaluate_preview_classifies_pullback_via_strategy_label_only() -> None:
    # No pullback_signal flag but the source strategy is the Pullback /
    # Trend Continuation row — moderate strength.
    queue = [
        _queue_candidate(
            symbol="DIA",
            strategy="Pullback / Trend Continuation",
            contribution=_contribution(
                total_score=82,
                total_label="Bull",
                trend_score=72,
                momo_score=74,
                raw_total_contribution=12.0,
                pullback_signal=False,
                inferred_direction="long",
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    previews = result["previews"]
    assert len(previews) == 1
    assert previews[0].family_id == "true_momentum_pullback"
    assert previews[0].match_strength == "moderate"
    assert "strategy_is_pullback_or_trend_continuation" in previews[0].reason_codes


def test_evaluate_preview_classifies_reversal_watch_on_no_trade_warning() -> None:
    queue = [
        _queue_candidate(
            symbol="BAD",
            strategy="Event Continuation",
            contribution=_contribution(
                no_trade_warning=True,
                total_score=70,
                total_label="Bull",
                reason_codes=["momentum_no_trade_warning"],
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    previews = result["previews"]
    assert len(previews) == 1
    preview = previews[0]
    assert preview.family_id == "true_momentum_reversal_watch"
    assert preview.match_strength == "watch"
    assert "momentum_no_trade_warning" in preview.reason_codes


def test_evaluate_preview_classifies_reversal_watch_on_reversal_warning() -> None:
    queue = [
        _queue_candidate(
            symbol="REV",
            strategy="Event Continuation",
            contribution=_contribution(
                reversal_warning=True,
                reason_codes=["momentum_reversal_warning"],
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    assert result["previews"][0].family_id == "true_momentum_reversal_watch"


def test_evaluate_preview_classifies_reversal_watch_on_bear_label_for_long_strategy() -> None:
    queue = [
        _queue_candidate(
            symbol="CONTRA",
            strategy="Event Continuation",
            contribution=_contribution(
                total_label="Max Bear",
                total_score=-65,
                raw_total_contribution=-15.0,
                inferred_direction="long",
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    previews = result["previews"]
    assert len(previews) == 1
    assert previews[0].family_id == "true_momentum_reversal_watch"
    assert "bear_total_label_long_strategy_contradiction" in previews[0].reason_codes
    assert "bear_total_score_long_strategy_contradiction" in previews[0].reason_codes


def test_evaluate_preview_precedence_reversal_watch_beats_continuation() -> None:
    # A candidate that would otherwise match continuation but also has
    # a reversal warning must be classified as reversal_watch only.
    queue = [
        _queue_candidate(
            symbol="MIXED",
            strategy="Event Continuation",
            contribution=_contribution(
                total_score=85,
                total_label="Bull",
                trend_score=78,
                momo_score=72,
                reversal_warning=True,
                reason_codes=["momentum_reversal_warning"],
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    previews = result["previews"]
    assert len(previews) == 1
    assert previews[0].family_id == "true_momentum_reversal_watch"


def test_evaluate_preview_skips_candidates_with_no_family_match() -> None:
    # Short-biased / off-mode rows do not fit any of the three planned
    # families.
    queue = [
        _queue_candidate(
            symbol="OFF",
            strategy="Mean Reversion",
            contribution=_contribution(
                mode="off",
                applied=False,
                inferred_direction="unknown",
                total_label=None,
                total_score=None,
                trend_score=None,
                momo_score=None,
                raw_total_contribution=0.0,
                applied_score_delta=0.0,
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    assert result["previews"] == []
    # Summary still counts the candidate input.
    assert result["summary"].candidate_count == 1
    assert result["summary"].preview_count == 0


def test_evaluate_preview_disabled_mode_returns_disabled_reason() -> None:
    queue = [
        _queue_candidate(
            symbol="XLK",
            strategy="Event Continuation",
            contribution=_contribution(),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(), candidates=queue
    )
    assert result["previews"] == []
    assert result["previews_generated"] is False
    assert "true_momentum_strategy_mode_disabled" in result["status"].reason_codes


def test_evaluate_preview_summary_carries_per_family_counts() -> None:
    queue = [
        _queue_candidate(
            symbol="XLK",
            contribution=_contribution(
                total_score=85, total_label="Bull",
                trend_score=78, momo_score=73,
            ),
        ),
        _queue_candidate(
            symbol="IWM",
            strategy="Pullback / Trend Continuation",
            rank=2,
            contribution=_contribution(
                total_score=82, total_label="Bull",
                trend_score=72, momo_score=72,
                pullback_signal=True,
            ),
        ),
        _queue_candidate(
            symbol="BAD",
            rank=3,
            contribution=_contribution(
                no_trade_warning=True,
                reason_codes=["momentum_no_trade_warning"],
            ),
        ),
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    summary = result["summary"]
    assert isinstance(summary, TrueMomentumStrategyPreviewSummary)
    assert summary.candidate_count == 3
    assert summary.preview_count == 3
    assert summary.continuation_count == 1
    assert summary.pullback_count == 1
    assert summary.reversal_watch_count == 1


def test_evaluate_preview_records_operational_caveats_from_contribution() -> None:
    queue = [
        _queue_candidate(
            symbol="PARITY",
            contribution=_contribution(
                total_score=85, total_label="Bull",
                trend_score=78, momo_score=72,
                reason_codes=["thinkorswim_parity_pending", "derived_higher_timeframe"],
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    preview = result["previews"][0]
    assert "thinkorswim_parity_pending" in preview.operational_caveats
    assert "derived_higher_timeframe" in preview.operational_caveats
    assert result["summary"].parity_pending_count == 1
    assert result["summary"].derived_higher_timeframe_count == 1


def test_evaluate_preview_records_non_actionable_and_no_order_fields() -> None:
    queue = [
        _queue_candidate(
            symbol="XLK",
            contribution=_contribution(
                total_score=85, total_label="Bull",
                trend_score=78, momo_score=73,
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    preview = result["previews"][0]
    # The dataclass exposes exactly the documented preview fields.
    keys = set(preview.__dataclass_fields__.keys())
    assert preview.non_actionable is True
    forbidden_keys = {
        "entry", "stop", "target", "size", "order_id", "approved", "route",
    }
    assert keys.isdisjoint(forbidden_keys)


def test_evaluate_preview_typed_result_is_self_contained() -> None:
    queue = [
        _queue_candidate(
            symbol="XLK",
            contribution=_contribution(
                total_score=85, total_label="Bull",
                trend_score=78, momo_score=73,
            ),
        )
    ]
    result = evaluate_true_momentum_strategy_preview(
        _settings_ns(mode="research_preview", guard="true"),
        candidates=queue,
    )
    typed = result["result"]
    assert isinstance(typed, TrueMomentumStrategyPreviewResult)
    assert typed.preview_phase == "C1"
    assert typed.preview_implementation_status == "research_preview"
    assert typed.deterministic_note == PREVIEW_DETERMINISTIC_NOTE
    assert len(typed.previews) == 1
    assert typed.previews[0].family_id == "true_momentum_continuation"


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


def test_preview_endpoint_requires_auth() -> None:
    client = TestClient(app)
    response = client.post(
        "/user/true-momentum-strategy-families/preview", json={"candidates": []}
    )
    assert response.status_code == 401


def test_preview_endpoint_disabled_mode_returns_no_previews(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "true_momentum_strategy_mode", "disabled")
    monkeypatch.setattr(_settings, "allow_true_momentum_strategy_families", False)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/true-momentum-strategy-families/preview",
        json={
            "candidates": [
                _queue_candidate(
                    symbol="XLK",
                    contribution=_contribution(
                        total_score=85, total_label="Bull",
                        trend_score=78, momo_score=73,
                    ),
                )
            ]
        },
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["previews"] == []
    assert payload["previews_generated"] is False
    assert payload["status"]["effective_mode"] == "disabled"
    assert "true_momentum_strategy_mode_disabled" in payload["status"]["reason_codes"]


def test_preview_endpoint_research_preview_classifies_continuation(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "true_momentum_strategy_mode", "research_preview")
    monkeypatch.setattr(_settings, "allow_true_momentum_strategy_families", True)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/true-momentum-strategy-families/preview",
        json={
            "candidates": [
                _queue_candidate(
                    symbol="XLK",
                    contribution=_contribution(
                        total_score=85, total_label="Bull",
                        trend_score=78, momo_score=73,
                    ),
                ),
                _queue_candidate(
                    symbol="BAD",
                    rank=2,
                    contribution=_contribution(
                        no_trade_warning=True,
                        reason_codes=["momentum_no_trade_warning"],
                    ),
                ),
            ]
        },
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["previews_generated"] is True
    assert payload["preview_phase"] == "C1"
    family_ids = [row["family_id"] for row in payload["previews"]]
    assert "true_momentum_continuation" in family_ids
    assert "true_momentum_reversal_watch" in family_ids
    for row in payload["previews"]:
        assert row["non_actionable"] is True
        # No order / approval fields on any preview row.
        assert "entry" not in row
        assert "order_id" not in row
        assert "approved" not in row
    assert payload["summary"]["preview_count"] == 2


def test_preview_endpoint_handles_missing_candidates_payload(monkeypatch) -> None:
    monkeypatch.setattr(_settings, "true_momentum_strategy_mode", "research_preview")
    monkeypatch.setattr(_settings, "allow_true_momentum_strategy_families", True)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/true-momentum-strategy-families/preview",
        json={},
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["previews"] == []
    assert payload["previews_generated"] is True


def test_preview_endpoint_does_not_call_market_provider(monkeypatch) -> None:
    def _no_provider(*args, **kwargs):  # pragma: no cover - guard
        raise AssertionError("Phase C1 preview endpoint must not call providers")

    import macmarket_trader.api.routes.admin as admin_module

    monkeypatch.setattr(
        admin_module.market_data_service, "historical_bars", _no_provider, raising=False
    )
    monkeypatch.setattr(
        admin_module.market_data_service, "provider_health", _no_provider, raising=False
    )
    monkeypatch.setattr(_settings, "true_momentum_strategy_mode", "research_preview")
    monkeypatch.setattr(_settings, "allow_true_momentum_strategy_families", True)

    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/true-momentum-strategy-families/preview",
        json={"candidates": []},
        headers={"Authorization": "Bearer user-token"},
    )
    assert response.status_code == 200


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
