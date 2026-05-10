"""Phase B1 ranking-engine integration tests.

These tests confirm that the bounded Momentum Intelligence ranking
contribution wires into ``DeterministicRankingEngine`` correctly across the
three operator modes:

- ``off``    → contribution is attached as a stable disabled stub; existing
               score/ordering is unchanged.
- ``shadow`` → contribution is computed and attached as explanation; final
               score and ordering are unchanged.
- ``active`` → contribution is applied to the score within the configured
               cap; ordering may change but only by a bounded amount.

Recommendation approval, paper-order routing, sizing, and live trading are
explicitly **not** affected by these tests — Phase B1 only touches the
ranking engine's score-units output.
"""

from __future__ import annotations

from datetime import date, timedelta

from macmarket_trader.domain.enums import MarketMode
from macmarket_trader.domain.schemas import Bar
from macmarket_trader.ranking_engine import DeterministicRankingEngine
from macmarket_trader.recommendation.momentum_ranking import MomentumRankingConfig


def _bullish_bars(symbol: str = "AAPL", *, n: int = 220, slope: float = 0.6) -> list[Bar]:
    base = date(2024, 1, 1)
    return [
        Bar(
            date=base + timedelta(days=i),
            open=100.0 + i * slope,
            high=101.0 + i * slope,
            low=99.0 + i * slope,
            close=100.5 + i * slope,
            volume=2_000_000,
        )
        for i in range(n)
    ]


def _bearish_bars(symbol: str = "BERR", *, n: int = 220, slope: float = 0.6) -> list[Bar]:
    base = date(2024, 1, 1)
    return [
        Bar(
            date=base + timedelta(days=i),
            open=300.0 - i * slope,
            high=301.0 - i * slope,
            low=299.0 - i * slope,
            close=300.5 - i * slope,
            volume=2_000_000,
        )
        for i in range(n)
    ]


def _bars_by_symbol(*pairs: tuple[str, list[Bar]]) -> dict[str, tuple[list[Bar], str, bool]]:
    return {symbol: (bars, "test_provider", False) for symbol, bars in pairs}


# ── off mode ──────────────────────────────────────────────────────────────


def test_off_mode_attaches_disabled_contribution_and_does_not_change_scores() -> None:
    engine_off = DeterministicRankingEngine(MomentumRankingConfig(mode="off"))
    engine_baseline = DeterministicRankingEngine(MomentumRankingConfig(mode="off"))
    bars = _bullish_bars()
    base_payload = engine_baseline.rank_candidates(
        bars_by_symbol=_bars_by_symbol(("AAPL", bars)),
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )
    off_payload = engine_off.rank_candidates(
        bars_by_symbol=_bars_by_symbol(("AAPL", bars)),
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )

    assert off_payload["queue"]
    for candidate in off_payload["queue"]:
        contrib = candidate["momentum_contribution"]
        assert contrib["mode"] == "off"
        assert contrib["enabled"] is False
        assert contrib["applied"] is False

    # Scores are identical to the baseline (off mode never alters scores).
    assert [c["score"] for c in off_payload["queue"]] == [c["score"] for c in base_payload["queue"]]


# ── shadow mode ───────────────────────────────────────────────────────────


def test_shadow_mode_computes_contribution_without_changing_score_or_order() -> None:
    bars_by_symbol = _bars_by_symbol(("AAPL", _bullish_bars("AAPL")), ("BERR", _bearish_bars("BERR")))
    off = DeterministicRankingEngine(MomentumRankingConfig(mode="off")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )
    shadow = DeterministicRankingEngine(MomentumRankingConfig(mode="shadow")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )

    assert [c["symbol"] for c in shadow["queue"]] == [c["symbol"] for c in off["queue"]]
    assert [c["score"] for c in shadow["queue"]] == [c["score"] for c in off["queue"]]

    for candidate in shadow["queue"]:
        contrib = candidate["momentum_contribution"]
        assert contrib["mode"] == "shadow"
        assert contrib["enabled"] is True
        assert contrib["applied"] is False
        # Even when shadow_contribution is non-zero, total_contribution stays 0.
        assert contrib["total_contribution"] == 0.0


# ── active mode ───────────────────────────────────────────────────────────


def test_active_mode_changes_score_within_cap_for_aligned_bull() -> None:
    bars = _bullish_bars()
    bars_by_symbol = _bars_by_symbol(("AAPL", bars))
    config = MomentumRankingConfig(mode="active")

    off_score = DeterministicRankingEngine(MomentumRankingConfig(mode="off")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]["score"]

    active_payload = DeterministicRankingEngine(config).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )

    active_candidate = active_payload["queue"][0]
    contrib = active_candidate["momentum_contribution"]
    assert contrib["mode"] == "active"
    assert contrib["applied"] is True
    assert contrib["inferred_direction"] == "long"
    # Bounded contribution converted to ranking-score scale (÷ 100).
    delta_max = config.max_total_contribution / config.ranking_score_scale
    delta_min = config.min_total_contribution / config.ranking_score_scale
    delta = active_candidate["score"] - off_score
    assert delta_min - 1e-9 <= delta <= delta_max + 1e-9, (
        f"active-mode score change must stay within bounds; got delta={delta} for caps "
        f"[{delta_min}, {delta_max}]"
    )
    # And the active-mode score remains in [0, 1].
    assert 0.0 <= active_candidate["score"] <= 1.0


def test_active_mode_does_not_apply_for_unknown_direction_strategies() -> None:
    """Mean Reversion is intentionally treated as direction-unknown at the
    ranking layer (Phase B1 stays conservative). The active-mode contribution
    therefore must not change the candidate's score.
    """
    bars_by_symbol = _bars_by_symbol(("AAPL", _bullish_bars()))
    config = MomentumRankingConfig(mode="active")

    off_score = DeterministicRankingEngine(MomentumRankingConfig(mode="off")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Mean Reversion"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]["score"]

    active = DeterministicRankingEngine(config).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Mean Reversion"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    contrib = active["momentum_contribution"]
    assert contrib["applied"] is False
    assert "direction_unknown" in contrib["reason_codes"]
    assert active["score"] == off_score


# ── Phase B4.2 — registry-driven direction inference through the engine ────


def test_breakout_prior_day_high_infers_long_through_engine() -> None:
    """The ranking engine must enrich the contribution context with the
    registry directional_profile so Breakout / Prior-Day High candidates
    surface inferred_direction='long' instead of falling back to unknown.
    """
    bars_by_symbol = _bars_by_symbol(("AAPL", _bullish_bars()))
    out = DeterministicRankingEngine(MomentumRankingConfig(mode="shadow")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Breakout / Prior-Day High"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )
    contrib = out["queue"][0]["momentum_contribution"]
    assert contrib["inferred_direction"] == "long"
    assert "direction_unknown" not in contrib["reason_codes"]
    # Registry directional_profile is the canonical source for known strategies.
    assert "direction_from_strategy_metadata" in contrib["reason_codes"]


def test_event_continuation_infers_long_through_engine() -> None:
    bars_by_symbol = _bars_by_symbol(("AAPL", _bullish_bars()))
    out = DeterministicRankingEngine(MomentumRankingConfig(mode="shadow")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )
    contrib = out["queue"][0]["momentum_contribution"]
    assert contrib["inferred_direction"] == "long"
    assert "direction_from_strategy_metadata" in contrib["reason_codes"]


def test_pullback_trend_continuation_infers_long_through_engine() -> None:
    bars_by_symbol = _bars_by_symbol(("AAPL", _bullish_bars()))
    out = DeterministicRankingEngine(MomentumRankingConfig(mode="shadow")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Pullback / Trend Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )
    contrib = out["queue"][0]["momentum_contribution"]
    assert contrib["inferred_direction"] == "long"
    assert "direction_from_strategy_metadata" in contrib["reason_codes"]


def test_active_mode_applies_for_breakout_with_bull_momentum() -> None:
    """Phase B4.2 must enable the bounded contribution to actually
    apply for Breakout / Prior-Day High when Momentum is bullish — the
    pre-Phase-B4.2 bug was the inference dropping to unknown which left
    the bounded contribution unapplied."""
    bars_by_symbol = _bars_by_symbol(("AAPL", _bullish_bars()))
    off_score = DeterministicRankingEngine(MomentumRankingConfig(mode="off")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Breakout / Prior-Day High"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]["score"]

    active = DeterministicRankingEngine(MomentumRankingConfig(mode="active")).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Breakout / Prior-Day High"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )["queue"][0]
    contrib = active["momentum_contribution"]
    assert contrib["applied"] is True
    assert contrib["inferred_direction"] == "long"
    assert active["score"] != off_score


# ── stable shape & non-regression ─────────────────────────────────────────


def test_existing_engine_call_signature_remains_backward_compatible() -> None:
    """rank_candidates() must remain callable with the legacy kwargs only.

    Phase B1 added an optional ``momentum_config`` kwarg but must not break
    any existing call site (admin.py / strategy_reports.py) that uses
    positional kwargs.
    """
    bars_by_symbol = _bars_by_symbol(("AAPL", _bullish_bars()))
    out = DeterministicRankingEngine().rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
        top_n=3,
    )
    assert "queue" in out
    assert out["queue"]
    assert "momentum_contribution" in out["queue"][0]


def test_active_mode_score_stays_in_unit_interval() -> None:
    bars_by_symbol = _bars_by_symbol(("AAPL", _bullish_bars(slope=2.5)))
    config = MomentumRankingConfig(mode="active")
    out = DeterministicRankingEngine(config).rank_candidates(
        bars_by_symbol=bars_by_symbol,
        strategies=["Event Continuation"],
        market_mode=MarketMode.EQUITIES,
        timeframe="1D",
    )
    for candidate in out["queue"]:
        assert 0.0 <= candidate["score"] <= 1.0
