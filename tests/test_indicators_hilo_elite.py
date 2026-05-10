from __future__ import annotations

from datetime import date, timedelta

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators import compute_hilo_elite


def _bars_from_closes(closes: list[float], *, start: date = date(2025, 1, 1)) -> list[Bar]:
    bars: list[Bar] = []
    for i, c in enumerate(closes):
        bars.append(
            Bar(
                date=start + timedelta(days=i),
                open=c,
                high=c + 1.0,
                low=c - 1.0,
                close=c,
                volume=1_000_000,
            )
        )
    return bars


def test_compute_hilo_elite_empty_returns_no_points() -> None:
    series = compute_hilo_elite([])
    assert series.points == []


def test_thrust_flips_bullish_after_strong_rally() -> None:
    closes = [100.0] * 60 + [100.0 + i * 1.2 for i in range(60)]
    series = compute_hilo_elite(_bars_from_closes(closes), timeframe="1D")
    thrusts = [p.thrust for p in series.points]
    assert 1 in thrusts


def test_thrust_flips_bearish_after_strong_decline() -> None:
    closes = [200.0] * 60 + [200.0 - i * 1.2 for i in range(60)]
    series = compute_hilo_elite(_bars_from_closes(closes), timeframe="1D")
    thrusts = [p.thrust for p in series.points]
    assert -1 in thrusts


def test_thrust_can_flip_both_directions_on_crafted_data() -> None:
    rally = [100.0 + i * 1.2 for i in range(80)]
    decline = [rally[-1] - i * 1.2 for i in range(1, 80)]
    closes = [100.0] * 30 + rally + decline
    series = compute_hilo_elite(_bars_from_closes(closes), timeframe="1D")
    thrusts = {p.thrust for p in series.points}
    assert 1 in thrusts and -1 in thrusts


def test_hlp_output_uses_a_and_b_components() -> None:
    closes = [100.0 + i for i in range(80)]
    series = compute_hilo_elite(_bars_from_closes(closes), timeframe="1D")
    last = series.points[-1]
    assert last.hlp_output == last.hlp_a + last.hlp_b


def test_intraday_uses_intraday_levels() -> None:
    series = compute_hilo_elite(_bars_from_closes([100.0 + i for i in range(60)]), timeframe="1H")
    assert series.config.preset_category == "intraday"
    assert series.config.over_bought_levels[0] == 27.6


def test_day_uses_day_levels() -> None:
    series = compute_hilo_elite(_bars_from_closes([100.0 + i for i in range(60)]), timeframe="1D")
    assert series.config.preset_category == "day"
    assert series.config.slow_d_k_period == 99
