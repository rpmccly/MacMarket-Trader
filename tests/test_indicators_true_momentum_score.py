from __future__ import annotations

from datetime import date, timedelta

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators import compute_true_momentum_score


def _bars_from_closes(closes: list[float], *, start: date = date(2024, 1, 1)) -> list[Bar]:
    return [
        Bar(
            date=start + timedelta(days=i),
            open=c,
            high=c + 1.0,
            low=c - 1.0,
            close=c,
            volume=1_000_000,
        )
        for i, c in enumerate(closes)
    ]


def test_compute_true_momentum_score_empty_bars_returns_no_points() -> None:
    series = compute_true_momentum_score([])
    assert series.points == []


def test_strong_uptrend_yields_bullish_total_score() -> None:
    closes = [100.0 + i * 0.8 for i in range(220)]
    series = compute_true_momentum_score(_bars_from_closes(closes), timeframe="1D")
    last = series.points[-1]
    assert last.total_score > 0
    assert last.total_state in {"max_bull", "bull", "neutral_up"}


def test_strong_downtrend_yields_bearish_total_score() -> None:
    closes = [300.0 - i * 0.8 for i in range(220)]
    series = compute_true_momentum_score(_bars_from_closes(closes), timeframe="1D")
    last = series.points[-1]
    assert last.total_score < 0
    assert last.total_state in {"max_bear", "bear", "neutral_down"}


def test_component_breakdown_keys_present_on_every_point() -> None:
    closes = [100.0 + (i % 5) for i in range(60)]
    series = compute_true_momentum_score(_bars_from_closes(closes), timeframe="1D")
    for p in series.points:
        cb = p.component_breakdown
        assert hasattr(cb, "true_momentum_score")
        assert hasattr(cb, "hilo_thrust")
        assert hasattr(cb, "bull_ma")
        assert hasattr(cb, "bear_ma")
        assert hasattr(cb, "atr_value")
        assert hasattr(cb, "macd_bias")
        assert hasattr(cb, "intraday_penalty")
        assert hasattr(cb, "base_score")


def test_pullback_and_reversal_flags_are_booleans() -> None:
    closes = [100.0 + (i % 3) for i in range(80)]
    series = compute_true_momentum_score(_bars_from_closes(closes), timeframe="1D")
    p = series.points[-1]
    for flag in (
        p.max_bull_pullback,
        p.bull_pullback,
        p.max_bear_rally,
        p.bear_rally,
        p.new_max_bull_pullback,
        p.new_bull_pullback,
        p.new_max_bear_rally,
        p.new_bear_rally,
        p.from_max_bull_to_weak,
        p.from_bull_to_weak,
        p.from_max_bear_to_weak,
        p.from_bear_to_weak,
        p.neutral_up_to_bull,
        p.neutral_dn_to_bear,
    ):
        assert isinstance(flag, bool)


def test_atr_stop_mode_is_documented_approximation() -> None:
    series = compute_true_momentum_score(_bars_from_closes([100.0 + i for i in range(40)]), timeframe="1D")
    assert series.atr_stop_mode == "deterministic_ema_trailing_stop_approximation"
