"""Phase B2 serialization smoke.

Confirms ``RankedCandidate.momentum_contribution`` survives the dataclass →
dict serialization the API consumers rely on, so the frontend can read it
off the queue payload without backend changes.

Recommendation approval, paper-order, options, and ranking math are not
exercised here — this is a frontend-surface contract pin only.
"""

from __future__ import annotations

from datetime import date, timedelta

from macmarket_trader.domain.enums import MarketMode
from macmarket_trader.domain.schemas import Bar
from macmarket_trader.ranking_engine import DeterministicRankingEngine
from macmarket_trader.recommendation.momentum_ranking import MomentumRankingConfig


def _bullish_bars(*, n: int = 220) -> list[Bar]:
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


def _bars_by_symbol(symbol: str = "AAPL") -> dict[str, tuple[list[Bar], str, bool]]:
    return {symbol: (_bullish_bars(), "test_provider", False)}


def _frontend_contract_fields() -> set[str]:
    """Fields the frontend Phase B2 surfaces consume off the queue payload."""
    return {
        "mode",
        "enabled",
        "applied",
        "total_contribution",
        "shadow_contribution",
        "momentum_alignment_score",
        "trend_alignment_score",
        "hilo_confirmation_bonus",
        "reversal_warning_penalty",
        "no_trade_warning",
        "pullback_signal",
        "reversal_warning",
        "parity_status",
        "higher_timeframe_source",
        "total_score",
        "total_label",
        "trend_score",
        "momo_score",
        "inferred_direction",
        "calculation_notes",
        "reason_codes",
    }


def test_shadow_mode_queue_payload_carries_all_contribution_fields() -> None:
    out = DeterministicRankingEngine(MomentumRankingConfig(mode="shadow")).rank_candidates(
        bars_by_symbol=_bars_by_symbol(),
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )
    assert out["queue"]
    contribution = out["queue"][0]["momentum_contribution"]
    assert isinstance(contribution, dict)
    missing = _frontend_contract_fields() - contribution.keys()
    assert not missing, f"frontend-expected contribution fields missing: {missing}"
    assert contribution["mode"] == "shadow"
    assert contribution["enabled"] is True
    assert contribution["applied"] is False
    assert contribution["total_contribution"] == 0.0


def test_off_mode_queue_payload_still_emits_stable_contribution_shape() -> None:
    out = DeterministicRankingEngine(MomentumRankingConfig(mode="off")).rank_candidates(
        bars_by_symbol=_bars_by_symbol(),
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )
    contribution = out["queue"][0]["momentum_contribution"]
    assert isinstance(contribution, dict)
    assert contribution["mode"] == "off"
    assert contribution["enabled"] is False
    assert contribution["applied"] is False


def test_active_mode_marks_applied_for_aligned_bullish_candidate() -> None:
    out = DeterministicRankingEngine(MomentumRankingConfig(mode="active")).rank_candidates(
        bars_by_symbol=_bars_by_symbol(),
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )
    contribution = out["queue"][0]["momentum_contribution"]
    assert contribution["mode"] == "active"
    assert contribution["applied"] is True
    assert contribution["total_contribution"] != 0.0


def test_contribution_payload_never_carries_approval_or_routing_fields() -> None:
    out = DeterministicRankingEngine(MomentumRankingConfig(mode="active")).rank_candidates(
        bars_by_symbol=_bars_by_symbol(),
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )
    contribution = out["queue"][0]["momentum_contribution"]
    forbidden = {"approved", "rejected", "approve", "reject", "side", "shares", "size", "order_id", "route"}
    overlap = forbidden & contribution.keys()
    assert overlap == set(), f"contribution must not surface approval/routing fields, found: {overlap}"
