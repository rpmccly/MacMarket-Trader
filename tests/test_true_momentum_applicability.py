"""Phase C6 True Momentum applicability review annotations.

The C6 layer annotates already-built review payloads. It must remain
non-actionable and outside ranking, strategy registry, paper orders, and
broker routing.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.analysis_packets import build_analysis_packet
from macmarket_trader.api.main import app
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.email_templates import render_strategy_report_html, render_strategy_report_text
from macmarket_trader.recommendation.true_momentum_applicability import (
    evaluate_true_momentum_applicability,
    evaluate_true_momentum_applicability_payload,
)
from macmarket_trader.storage.db import SessionLocal, init_db

REPO_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_ACTION_FIELDS = {
    "entry",
    "entry_price",
    "stop",
    "stop_price",
    "target",
    "target_price",
    "size",
    "shares",
    "approve",
    "approved",
    "route",
    "order_id",
    "paper_order_id",
    "broker_order_id",
}
_DEFAULT_CONTRIBUTION = object()


def setup_module() -> None:
    init_db()


def _approve_default_user(client: TestClient) -> None:
    client.get("/user/me", headers={"Authorization": "Bearer user-token"})
    with SessionLocal() as session:
        user = session.execute(
            select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")
        ).scalar_one()
        user.approval_status = "approved"
        session.commit()


def _contribution(
    *,
    total_score: int | None = 85,
    total_label: str | None = "Bull",
    trend_score: float | None = 78.0,
    momo_score: float | None = 73.0,
    raw_total_contribution: float = 20.0,
    inferred_direction: str = "long",
    pullback_signal: bool = False,
    reversal_warning: bool = False,
    no_trade_warning: bool = False,
    reason_codes: list[str] | None = None,
) -> dict:
    return {
        "mode": "shadow",
        "enabled": True,
        "applied": False,
        "raw_total_contribution": raw_total_contribution,
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
    }


def _queue_candidate(
    *,
    symbol: str = "XLK",
    strategy: str = "Event Continuation",
    contribution: dict | None | object = _DEFAULT_CONTRIBUTION,
    risk_calendar: dict | None = None,
) -> dict:
    return {
        "symbol": symbol,
        "strategy": strategy,
        "rank": 1,
        "score": 0.9,
        "expected_rr": 2.2,
        "confidence": 0.74,
        "momentum_contribution": _contribution() if contribution is _DEFAULT_CONTRIBUTION else contribution,
        "risk_calendar": risk_calendar,
    }


def _row_by_family(rows, family_id: str):
    return next(row for row in rows if row.family_id == family_id)


def test_continuation_classification_is_research_preview_and_non_actionable() -> None:
    rows = evaluate_true_momentum_applicability(_queue_candidate())
    continuation = _row_by_family(rows, "true_momentum_continuation")

    assert continuation.status == "applicable_research_preview"
    assert continuation.match_strength == "strong"
    assert continuation.direction == "long"
    assert continuation.non_actionable is True
    assert "true_momentum_continuation_match" in continuation.reason_codes


def test_pullback_classification_works() -> None:
    rows = evaluate_true_momentum_applicability(
        _queue_candidate(
            symbol="IWM",
            strategy="Pullback / Trend Continuation",
            contribution=_contribution(pullback_signal=True),
        )
    )
    pullback = _row_by_family(rows, "true_momentum_pullback")

    assert pullback.status == "applicable_research_preview"
    assert pullback.match_strength == "strong"
    assert "true_momentum_pullback_match" in pullback.reason_codes


def test_reversal_watch_classification_is_watch_only() -> None:
    rows = evaluate_true_momentum_applicability(
        _queue_candidate(
            contribution=_contribution(
                total_score=-65,
                total_label="Bear",
                reversal_warning=True,
            )
        )
    )
    reversal = _row_by_family(rows, "true_momentum_reversal_watch")

    assert reversal.status == "watch_only"
    assert reversal.match_strength == "watch"
    assert reversal.direction == "watch"
    assert "true_momentum_reversal_watch_match" in reversal.reason_codes
    assert "watch_only" in reversal.blockers


def test_warnings_block_research_preview_status() -> None:
    rows = evaluate_true_momentum_applicability(
        _queue_candidate(
            risk_calendar={
                "decision": {
                    "decision_state": "caution",
                    "risk_level": "warning",
                    "allow_new_entries": False,
                    "warning_summary": "risk calendar warning",
                }
            }
        )
    )
    continuation = _row_by_family(rows, "true_momentum_continuation")

    assert continuation.status == "blocked_by_warning"
    assert continuation.non_actionable is True
    assert "risk_calendar_disallows_new_entries" in continuation.blockers


def test_parity_and_composite_blockers_have_dedicated_statuses() -> None:
    parity_rows = evaluate_true_momentum_applicability(
        _queue_candidate(
            contribution=_contribution(reason_codes=["tos_reference_mismatch"])
        )
    )
    composite_rows = evaluate_true_momentum_applicability(
        _queue_candidate(
            contribution=_contribution(reason_codes=["oscillator_aligned_composite_mismatch"])
        )
    )

    assert _row_by_family(parity_rows, "true_momentum_continuation").status == "blocked_by_parity"
    assert _row_by_family(composite_rows, "true_momentum_continuation").status == "blocked_by_composite_mismatch"


def test_insufficient_evidence_is_explicit_and_non_actionable() -> None:
    rows = evaluate_true_momentum_applicability(
        _queue_candidate(contribution=None)
    )

    assert {row.status for row in rows} == {"insufficient_evidence"}
    assert all(row.non_actionable for row in rows)


def test_applicability_payload_has_no_order_or_approval_fields() -> None:
    payload = evaluate_true_momentum_applicability_payload(_queue_candidate())

    assert payload
    for row in payload:
        assert row["non_actionable"] is True
        for field in FORBIDDEN_ACTION_FIELDS:
            assert field not in row


def test_applicability_is_shown_in_analysis_packet_and_strategy_report() -> None:
    rows = evaluate_true_momentum_applicability_payload(_queue_candidate(symbol="QQQ"))
    packet = build_analysis_packet(
        symbol="QQQ",
        market_mode="equities",
        timeframe="1D",
        source_payload={
            "symbol": "QQQ",
            "side": "long",
            "strategy": "Event Continuation",
            "true_momentum_applicability": rows,
        },
        market_data_source="polygon",
        fallback_mode=False,
        session_policy="regular_hours",
    )
    html = render_strategy_report_html(
        schedule_name="Desk scan",
        ran_at="2026-06-02T14:30:00Z",
        source="polygon",
        top_candidates=[],
        watchlist_only=[],
        no_trade=[],
        summary={},
        analysis_packets=[packet.model_dump(mode="json")],
    )
    text = render_strategy_report_text(
        schedule_name="Desk scan",
        ran_at="2026-06-02T14:30:00Z",
        source="polygon",
        top_candidates=[],
        watchlist_only=[],
        no_trade=[],
        summary={},
        analysis_packets=[packet.model_dump(mode="json")],
    )

    assert packet.true_momentum_applicability
    assert "True Momentum Applicability" in html
    assert "TRUE MOMENTUM APPLICABILITY" in text
    assert "non-actionable" in html + text


def test_analyze_and_queue_payloads_include_applicability_without_ranked_true_momentum_strategy() -> None:
    client = TestClient(app)
    _approve_default_user(client)

    analyze = client.get(
        "/user/analyze/QQQ",
        headers={"Authorization": "Bearer user-token"},
    )
    assert analyze.status_code == 200
    analyze_payload = analyze.json()
    assert "true_momentum_applicability" in analyze_payload
    assert analyze_payload["strategy_scoreboard"]
    assert "true_momentum_applicability" in analyze_payload["strategy_scoreboard"][0]

    queue = client.post(
        "/user/recommendations/queue",
        json={
            "symbols": ["QQQ"],
            "strategies": ["Event Continuation"],
            "top_n": 3,
        },
        headers={"Authorization": "Bearer user-token"},
    )
    assert queue.status_code == 200
    queue_payload = queue.json()
    assert queue_payload["queue"]
    for row in queue_payload["queue"]:
        assert "true_momentum" not in str(row.get("strategy", "")).lower()
        assert "true_momentum_applicability" in row


def test_applicability_module_stays_out_of_ranking_and_order_paths() -> None:
    candidates = [
        REPO_ROOT / "src/macmarket_trader/ranking_engine.py",
        REPO_ROOT / "src/macmarket_trader/recommendation/__init__.py",
        REPO_ROOT / "src/macmarket_trader/recommendation/momentum_ranking.py",
        REPO_ROOT / "src/macmarket_trader/execution/paper_broker.py",
        REPO_ROOT / "apps/web/lib/orders-helpers.ts",
    ]
    for path in candidates:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        assert "true_momentum_applicability" not in source
        assert "evaluate_true_momentum_applicability" not in source
