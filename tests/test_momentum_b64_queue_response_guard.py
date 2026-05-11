"""Phase B6.4 — black-box queue API regression tests.

Pins the deployed-bug shape at the **API response boundary** by injecting
a synthetic ``ranking_engine.rank_candidates`` result that mimics the
legacy-bug payload (``candidate.score=1.000`` and
``momentum_score_delta=0.188`` while
``contribution.applied_score_delta=0.07``). The /user/recommendations/queue
endpoint MUST correct the response before serialization and surface the
correction via the score_consistency_status field and the
``momentum_score_consistency_corrected`` reason code.

Phase B6.4 must not change raw contribution caps, default mode,
approval/order behavior, paper-order behavior, indicator math, or Phase
C. All tests below enforce those invariants.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.api.routes import admin as admin_routes
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.recommendation.momentum_ranking import (
    DEFAULT_ACTIVE_DELTA_SCALE,
    QUEUE_RESPONSE_CONSISTENCY_GUARD,
    apply_queue_response_consistency,
)
from macmarket_trader.storage.db import SessionLocal, init_db


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


def _legacy_bug_candidate(
    *,
    symbol: str,
    rank: int,
    baseline: float,
    strategy: str = "Event Continuation",
) -> dict[str, Any]:
    """Return a queue candidate dict that matches the deployed-bug shape.

    - ``candidate.score`` reflects the legacy un-scaled delta (baseline + 0.20).
    - ``momentum_score_delta`` is the implied (current - baseline) value.
    - ``contribution.applied_score_delta`` is the correct scaled +0.07
      from Phase B6.1.

    A correct Phase B6.4 build must overwrite ``score`` to
    ``clamp01(baseline + 0.07)`` and emit ``score_consistency_status="corrected"``.
    """
    legacy_score = min(1.0, baseline + 0.20)
    return {
        "rank": rank,
        "symbol": symbol,
        "strategy": strategy,
        "strategy_id": "event_continuation",
        "strategy_status": "active",
        "source": "test_provider",
        "workflow_source": "test_provider",
        "market_mode": "equities",
        "timeframe": "1D",
        "status": "top_candidate",
        "conviction_tier": "HIGH",
        "score": legacy_score,
        "score_breakdown": {},
        "expected_rr": 2.0,
        "confidence": 0.7,
        "thesis": "",
        "trigger": "",
        "entry_zone": "",
        "invalidation": "",
        "targets": "",
        "reason_text": "",
        "momentum_contribution": {
            "mode": "active",
            "enabled": True,
            "applied": True,
            "total_contribution": 20.0,
            "shadow_contribution": 20.0,
            "momentum_alignment_score": 10.0,
            "trend_alignment_score": 8.0,
            "hilo_confirmation_bonus": 5.0,
            "reversal_warning_penalty": 0.0,
            "no_trade_warning": False,
            "pullback_signal": False,
            "reversal_warning": False,
            "parity_status": "pending_thinkorswim_fixture_validation",
            "higher_timeframe_source": "derived_from_chart_bars",
            "total_score": 100,
            "total_label": "Max Bull",
            "trend_score": 100.0,
            "momo_score": 100.0,
            "inferred_direction": "long",
            "calculation_notes": [],
            "reason_codes": [
                "thinkorswim_parity_pending",
                "derived_higher_timeframe",
            ],
            "active_delta_scale": DEFAULT_ACTIVE_DELTA_SCALE,
            "raw_total_contribution": 20.0,
            "applied_score_delta": 0.07,
        },
        # B6 fields published by the engine but still legacy-incorrect:
        "score_before_momentum": baseline,
        "score_after_momentum": legacy_score,
        "momentum_score_delta": round(legacy_score - baseline, 4),  # legacy 0.188 / 0.20
        "momentum_realized_score_delta": round(legacy_score - baseline, 4),
        "momentum_rank_mode": "active",
    }


def _stub_engine_with_legacy_payload(
    monkeypatch: pytest.MonkeyPatch,
    items: list[dict[str, Any]],
) -> None:
    """Replace ``ranking_engine.rank_candidates`` to return ``items``
    verbatim. The route must still run the Phase B6.4 guard."""

    class _StubEngine:
        def rank_candidates(self, **_kwargs: Any) -> dict[str, Any]:
            queue = [dict(item) for item in items]  # defensive copy
            return {
                "queue": queue,
                "top_candidates": [dict(item) for item in items],
                "watchlist_only": [],
                "no_trade": [],
                "summary": {
                    "total": len(items),
                    "top_candidate_count": len(items),
                    "watchlist_count": 0,
                    "no_trade_count": 0,
                },
            }

    monkeypatch.setattr(admin_routes, "ranking_engine", _StubEngine())


# ── apply_queue_response_consistency pure helper ────────────────────────


def test_helper_corrects_legacy_bug_shape() -> None:
    items = [_legacy_bug_candidate(symbol="SPY", rank=1, baseline=0.812)]
    corrected_items, corrected_count = apply_queue_response_consistency(items)
    assert corrected_count == 1
    row = corrected_items[0]
    assert row["score"] == pytest.approx(0.882, abs=1e-3)
    assert row["score_after_momentum"] == pytest.approx(0.882, abs=1e-3)
    assert row["momentum_score_delta"] == pytest.approx(0.07, abs=1e-6)
    assert row["momentum_realized_score_delta"] == pytest.approx(0.07, abs=1e-3)
    assert row["score_consistency_status"] == "corrected"
    assert (
        "momentum_score_consistency_corrected"
        in row["momentum_contribution"]["reason_codes"]
    )


def test_helper_marks_already_correct_rows_as_ok() -> None:
    item: dict[str, Any] = _legacy_bug_candidate(symbol="SPY", rank=1, baseline=0.812)
    item["score"] = 0.882
    item["score_after_momentum"] = 0.882
    item["momentum_score_delta"] = 0.07
    item["momentum_realized_score_delta"] = 0.07
    items, corrected_count = apply_queue_response_consistency([item])
    assert corrected_count == 0
    row = items[0]
    assert row["score_consistency_status"] == "ok"
    assert (
        "momentum_score_consistency_corrected"
        not in row["momentum_contribution"]["reason_codes"]
    )


def test_helper_passthrough_for_shadow_blocked_and_off() -> None:
    shadow_item = _legacy_bug_candidate(symbol="SPY", rank=1, baseline=0.812)
    shadow_item["momentum_contribution"]["mode"] = "shadow"
    shadow_item["momentum_contribution"]["applied"] = False
    blocked_item = _legacy_bug_candidate(symbol="MSFT", rank=2, baseline=0.812)
    blocked_item["momentum_contribution"]["mode"] = "shadow"
    blocked_item["momentum_contribution"]["applied"] = False
    blocked_item["momentum_contribution"]["reason_codes"].append(
        "active_mode_blocked_by_safety_guard"
    )
    off_item = _legacy_bug_candidate(symbol="NVDA", rank=3, baseline=0.812)
    off_item["momentum_contribution"] = {
        "mode": "off",
        "enabled": False,
        "applied": False,
    }

    items, corrected_count = apply_queue_response_consistency(
        [shadow_item, blocked_item, off_item]
    )
    assert corrected_count == 0
    for row in items:
        # Phase B6.4 still tags the row 'ok' for diagnostic visibility,
        # but no score field changed.
        assert row["score_consistency_status"] == "ok"


def test_helper_clamp_truncated_realized_delta() -> None:
    """Baseline 0.97 + intended +0.07 → score 1.0, realized +0.03."""
    item = _legacy_bug_candidate(symbol="NVDA", rank=1, baseline=0.97)
    items, corrected_count = apply_queue_response_consistency([item])
    row = items[0]
    assert row["score"] == pytest.approx(1.0, abs=1e-6)
    assert row["score_after_momentum"] == pytest.approx(1.0, abs=1e-6)
    assert row["momentum_score_delta"] == pytest.approx(0.07, abs=1e-6)
    assert row["momentum_realized_score_delta"] == pytest.approx(0.03, abs=1e-3)
    # The legacy score was already 1.0 (min(1.0, 0.97+0.20)), so the
    # helper may or may not flag "corrected" depending on whether the
    # observed score happened to equal the clamped expected. In this
    # case it does (both 1.0), so the row is tagged ok.
    assert row["score_consistency_status"] in {"ok", "corrected"}


def test_helper_handles_empty_queue() -> None:
    items, corrected_count = apply_queue_response_consistency([])
    assert items == []
    assert corrected_count == 0


def test_helper_handles_missing_contribution_field() -> None:
    item = _legacy_bug_candidate(symbol="SPY", rank=1, baseline=0.812)
    item.pop("momentum_contribution")
    items, corrected_count = apply_queue_response_consistency([item])
    assert corrected_count == 0
    # No contribution → no score modification, no status tag (because
    # the helper only stamps 'ok' on rows that have a contribution).
    assert items[0]["score"] == pytest.approx(min(1.0, 0.812 + 0.20), abs=1e-3)


def test_helper_handles_malformed_contribution() -> None:
    item = _legacy_bug_candidate(symbol="SPY", rank=1, baseline=0.812)
    item["momentum_contribution"] = {"mode": "active", "applied": True, "junk": "x"}
    items, _ = apply_queue_response_consistency([item])
    # Malformed contribution → safely treated as not-active-applied,
    # score is unchanged from the legacy input.
    assert items[0]["score"] == pytest.approx(min(1.0, 0.812 + 0.20), abs=1e-3)


# ── /user/recommendations/queue end-to-end via TestClient ──────────────


@pytest.mark.parametrize(
    "baseline, expected_score, expected_realized",
    [
        (0.812, 0.882, 0.07),
        (0.792, 0.862, 0.07),
        (0.898, 0.968, 0.07),
        (0.970, 1.000, 0.03),
    ],
)
def test_queue_api_corrects_legacy_bug_payload_at_response_boundary(
    monkeypatch: pytest.MonkeyPatch,
    baseline: float,
    expected_score: float,
    expected_realized: float,
) -> None:
    """Pin the deployed-bug shape at the queue endpoint. The route must
    correct ``candidate.score`` from the legacy unscaled value (baseline
    + 0.20) to the scaled value (baseline + 0.07), independent of what
    the engine produced."""
    _stub_engine_with_legacy_payload(
        monkeypatch,
        [_legacy_bug_candidate(symbol="SPY", rank=1, baseline=baseline)],
    )
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/recommendations/queue",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbols": ["SPY"],
            "timeframe": "1D",
            "market_mode": "equities",
            "top_n": 1,
        },
    )
    assert response.status_code == 200, response.text
    row = response.json()["queue"][0]
    # API response shows the scaled score, NOT the legacy 1.000.
    assert row["score"] == pytest.approx(expected_score, abs=1e-3)
    assert row["score_after_momentum"] == pytest.approx(expected_score, abs=1e-3)
    assert row["score_before_momentum"] == pytest.approx(baseline, abs=1e-3)
    # Intended applied delta is the scaled +0.07.
    if baseline < 1.0:
        assert row["momentum_score_delta"] == pytest.approx(0.07, abs=1e-6)
    # Realized tracks the clamp.
    assert row["momentum_realized_score_delta"] == pytest.approx(
        expected_realized, abs=1e-3
    )
    # Contribution payload still says applied_score_delta=0.07 and
    # raw_total_contribution=20 (Phase B1 caps unchanged).
    assert row["momentum_contribution"]["applied_score_delta"] == pytest.approx(
        0.07, abs=1e-6
    )
    assert row["momentum_contribution"]["raw_total_contribution"] == pytest.approx(
        20.0, abs=1e-3
    )
    # Phase B6.4 diagnostic — row tagged 'corrected' when the observed
    # legacy score actually differs from the expected scaled score.
    # When the legacy unscaled value already clamps to 1.0 (i.e.
    # baseline ≥ 0.93 with raw +20), both observed and expected are
    # 1.0 and the guard tags 'ok' even though the *delta* was wrong;
    # the score-delta field is still rewritten to the scaled value.
    legacy_score = min(1.0, baseline + 0.20)
    expected_legacy_clamp = min(1.0, baseline + 0.07)
    if abs(legacy_score - expected_legacy_clamp) > 1e-6:
        assert row["score_consistency_status"] == "corrected"
        assert (
            "momentum_score_consistency_corrected"
            in row["momentum_contribution"]["reason_codes"]
        )
    else:
        assert row["score_consistency_status"] == "ok"
    # Regression: never the legacy unscaled +0.20.
    if baseline + 0.20 <= 1.0:
        assert row["score"] != pytest.approx(baseline + 0.20, abs=1e-3)


def test_queue_api_negative_contribution_scales_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative raw contribution must be scaled correctly. With raw -12
    (the bounded floor) at scale 0.35, the applied delta is -0.042 and
    baseline 0.848 lands at 0.806."""
    bad_row = _legacy_bug_candidate(symbol="MSFT", rank=1, baseline=0.848)
    bad_row["momentum_contribution"]["total_contribution"] = -12.0
    bad_row["momentum_contribution"]["raw_total_contribution"] = -12.0
    bad_row["momentum_contribution"]["shadow_contribution"] = -12.0
    bad_row["momentum_contribution"]["applied_score_delta"] = round(
        -12.0 / 100.0 * DEFAULT_ACTIVE_DELTA_SCALE, 6
    )
    bad_row["momentum_contribution"]["inferred_direction"] = "long"
    # Legacy bug shape: queue applied raw/100 = -0.12 (un-scaled).
    bad_row["score"] = 0.728
    bad_row["score_after_momentum"] = 0.728
    bad_row["momentum_score_delta"] = -0.12
    bad_row["momentum_realized_score_delta"] = -0.12

    _stub_engine_with_legacy_payload(monkeypatch, [bad_row])
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
    # Scaled landing: 0.848 - 0.042 = 0.806.
    assert row["score"] == pytest.approx(0.806, abs=1e-3)
    assert row["score_after_momentum"] == pytest.approx(0.806, abs=1e-3)
    assert row["momentum_score_delta"] == pytest.approx(-0.042, abs=1e-6)
    assert row["score_consistency_status"] == "corrected"


def test_queue_api_response_never_contains_approval_or_order_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_engine_with_legacy_payload(
        monkeypatch,
        [_legacy_bug_candidate(symbol="SPY", rank=1, baseline=0.812)],
    )
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/recommendations/queue",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbols": ["SPY"],
            "timeframe": "1D",
            "market_mode": "equities",
            "top_n": 1,
        },
    )
    assert response.status_code == 200
    for row in response.json()["queue"]:
        for forbidden in _FORBIDDEN_PAYLOAD_KEYS:
            assert forbidden not in row, (
                f"Phase B6.4 ranking surface leaked {forbidden!r}"
            )


def test_queue_api_aligns_top_candidates_bucket_with_corrected_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``top_candidates`` is a separate dict copy emitted by the engine —
    the route must keep it in sync with the corrected ``queue`` bucket
    so a frontend that consumes either sees the same scaled score."""
    _stub_engine_with_legacy_payload(
        monkeypatch,
        [_legacy_bug_candidate(symbol="SPY", rank=1, baseline=0.812)],
    )
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/recommendations/queue",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbols": ["SPY"],
            "timeframe": "1D",
            "market_mode": "equities",
            "top_n": 1,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    queue_row = payload["queue"][0]
    top_row = payload["top_candidates"][0]
    assert queue_row["score"] == pytest.approx(top_row["score"], abs=1e-6)
    assert queue_row["score_after_momentum"] == pytest.approx(
        top_row["score_after_momentum"], abs=1e-6
    )
    assert queue_row["momentum_score_delta"] == pytest.approx(
        top_row["momentum_score_delta"], abs=1e-6
    )
    assert top_row["score_consistency_status"] == queue_row["score_consistency_status"]


def test_queue_api_multiple_legacy_rows_all_get_corrected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins the multi-row deployed-bug shape: SPY EV Continuation 0.812,
    SPY Breakout 0.792, DIA Breakout 0.791, XLC Breakout 0.785. Every
    row in the queue response must show the scaled +0.07."""
    rows = [
        _legacy_bug_candidate(symbol="SPY", rank=1, baseline=0.812),
        _legacy_bug_candidate(symbol="SPY", rank=2, baseline=0.792, strategy="Breakout"),
        _legacy_bug_candidate(symbol="DIA", rank=3, baseline=0.791, strategy="Breakout"),
        _legacy_bug_candidate(symbol="XLC", rank=4, baseline=0.785, strategy="Breakout"),
    ]
    _stub_engine_with_legacy_payload(monkeypatch, rows)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/recommendations/queue",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbols": ["SPY", "DIA", "XLC"],
            "timeframe": "1D",
            "market_mode": "equities",
            "top_n": 10,
        },
    )
    assert response.status_code == 200
    queue = response.json()["queue"]
    assert len(queue) == 4
    expected_by_baseline = {0.812: 0.882, 0.792: 0.862, 0.791: 0.861, 0.785: 0.855}
    for row in queue:
        baseline = row["score_before_momentum"]
        assert row["score"] == pytest.approx(expected_by_baseline[baseline], abs=1e-3)
        assert row["momentum_score_delta"] == pytest.approx(0.07, abs=1e-6)
        assert row["score_consistency_status"] == "corrected"


# ── Status payload diagnostics ─────────────────────────────────────────


def test_status_exposes_queue_response_consistency_guard() -> None:
    from macmarket_trader.recommendation.momentum_ranking import (
        build_momentum_ranking_status,
    )

    class _Settings:
        momentum_ranking_mode = "active"
        momentum_active_ranking_allowed = True
        momentum_active_delta_scale = 0.35

    status = build_momentum_ranking_status(_Settings())
    assert status.queue_response_consistency_guard is True
    assert QUEUE_RESPONSE_CONSISTENCY_GUARD is True


def test_status_keeps_all_b63_diagnostics_when_b64_added() -> None:
    from macmarket_trader.recommendation.momentum_ranking import (
        ACTIVE_DELTA_FORMULA_VERSION,
        build_momentum_ranking_status,
    )

    class _Settings:
        momentum_ranking_mode = "active"
        momentum_active_ranking_allowed = True
        momentum_active_delta_scale = 0.35

    status = build_momentum_ranking_status(_Settings())
    # B6.3 diagnostics are still present.
    assert status.active_delta_formula_version == ACTIVE_DELTA_FORMULA_VERSION
    assert status.ranking_score_consistency_guard is True
    # B6.4 diagnostic was added without removing the others.
    assert status.queue_response_consistency_guard is True
