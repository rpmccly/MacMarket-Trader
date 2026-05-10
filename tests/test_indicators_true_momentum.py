from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators import compute_true_momentum
from macmarket_trader.indicators.true_momentum import config_for_timeframe


def _daily_bars(closes: list[float], *, start: date = date(2025, 1, 1)) -> list[Bar]:
    return [
        Bar(
            date=start + timedelta(days=i),
            open=c,
            high=c + 0.5,
            low=c - 0.5,
            close=c,
            volume=1_000_000,
        )
        for i, c in enumerate(closes)
    ]


def _hourly_bars(closes: list[float]) -> list[Bar]:
    base = datetime(2025, 1, 6, 14, 30, tzinfo=UTC)
    return [
        Bar(
            date=(base + timedelta(hours=i)).date(),
            timestamp=base + timedelta(hours=i),
            open=c,
            high=c + 0.5,
            low=c - 0.5,
            close=c,
            volume=1_000_000,
        )
        for i, c in enumerate(closes)
    ]


def test_compute_true_momentum_empty_bars_returns_neutral_series() -> None:
    series = compute_true_momentum([])
    assert series.points == []
    assert series.higher_timeframe_source == "insufficient_data"
    assert series.parity_status == "pending_thinkorswim_fixture_validation"


def test_monotonic_bullish_daily_pushes_true_momentum_above_50() -> None:
    bars = _daily_bars([100 + i for i in range(120)])
    series = compute_true_momentum(bars, timeframe="1D")
    assert series.points
    last = series.points[-1]
    assert last.true_momentum > 50
    assert last.true_momentum_ema > 50
    assert last.trend_direction == 1


def test_monotonic_bearish_daily_pushes_true_momentum_below_50() -> None:
    bars = _daily_bars([220 - i for i in range(120)])
    series = compute_true_momentum(bars, timeframe="1D")
    assert series.points[-1].true_momentum < 50
    assert series.points[-1].true_momentum_ema < 50


def test_provided_higher_timeframe_bars_are_labeled() -> None:
    daily = _daily_bars([100 + i for i in range(60)])
    weekly = [
        Bar(date=date(2024, 12, 30) + timedelta(weeks=i), open=100, high=102, low=99, close=100 + i, volume=1)
        for i in range(20)
    ]
    series = compute_true_momentum(daily, timeframe="1D", higher_timeframe_bars=weekly)
    assert series.higher_timeframe_source == "provided_higher_timeframe_bars"
    assert series.parity_status == "pending_thinkorswim_fixture_validation"


def test_derived_higher_timeframe_bars_are_labeled() -> None:
    series = compute_true_momentum(_daily_bars([100 + i for i in range(40)]), timeframe="1D")
    assert series.higher_timeframe_source == "derived_from_chart_bars"
    assert any("derived" in note for note in series.notes)


def test_hourly_timeframe_uses_daily_higher_timeframe_label() -> None:
    series = compute_true_momentum(_hourly_bars([100 + i * 0.1 for i in range(50)]), timeframe="1H")
    assert series.config.higher_timeframe_label == "daily"


def test_config_for_timeframe_matches_documented_l1_l2() -> None:
    assert config_for_timeframe("1D").L1 == 21 and config_for_timeframe("1D").L2 == 21
    assert config_for_timeframe("4H").L1 == 30 and config_for_timeframe("4H").L2 == 35
    assert config_for_timeframe("1H").L1 == 30 and config_for_timeframe("1H").L2 == 21
