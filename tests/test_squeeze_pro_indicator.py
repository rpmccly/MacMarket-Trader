from datetime import date, timedelta

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators.squeeze_pro import (
    classify_oscillator_state,
    classify_squeeze_state,
    compute_squeeze_pro,
)


def _bars(count: int, *, flat: bool = False) -> list[Bar]:
    base = date(2026, 1, 1)
    output: list[Bar] = []
    for idx in range(count):
        close = 100.0 if flat else 100.0 + idx * 0.35 + (2.0 if idx % 7 == 0 else 0.0)
        output.append(
            Bar(
                date=base + timedelta(days=idx),
                open=close - 0.25,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000_000 + idx,
            )
        )
    return output


def test_squeeze_pro_state_classification() -> None:
    assert classify_squeeze_state(-0.1, -0.2, -0.3) == "high"
    assert classify_squeeze_state(0.1, -0.2, -0.3) == "mid"
    assert classify_squeeze_state(0.1, 0.2, -0.3) == "low"
    assert classify_squeeze_state(0.1, 0.2, 0.3) == "none"


def test_squeeze_pro_histogram_color_state_transitions() -> None:
    assert classify_oscillator_state(2.0, 1.0) == "up"
    assert classify_oscillator_state(-1.0, -2.0) == "down_decreasing"
    assert classify_oscillator_state(1.0, 2.0) == "up_decreasing"
    assert classify_oscillator_state(-2.0, -1.0) == "down"


def test_squeeze_pro_arrow_logic_is_disabled_pending_approved_rules() -> None:
    series = compute_squeeze_pro(_bars(90))
    assert series.config.show_arrows is False
    assert series.config.arrow_mode == "disabled_pending_approved_arrow_rules"
    assert all(point.arrow is None for point in series.points)
    assert all(point.arrow_reason is None for point in series.points)
    assert "Arrow logic is deferred until approved arrow rules are provided." in series.notes


def test_squeeze_pro_insufficient_bars_return_unavailable_points() -> None:
    series = compute_squeeze_pro(_bars(10))
    assert len(series.points) == 10
    assert all(point.status == "unavailable" for point in series.points)
    assert all(point.reason == "insufficient_bars_for_squeeze_pro" for point in series.points)


def test_squeeze_pro_preserves_source_timeline_with_null_warmup_points() -> None:
    bars = _bars(80)
    series = compute_squeeze_pro(bars)

    assert len(series.points) == len(bars)
    assert [point.index for point in series.points] == list(range(len(bars)))

    first_ok_index = next(index for index, point in enumerate(series.points) if point.status == "ok")
    assert first_ok_index > 0
    warmup = series.points[:first_ok_index]
    assert warmup
    assert all(point.status == "unavailable" for point in warmup)
    assert all(point.oscillator_value is None for point in warmup)
    assert all(point.squeeze_state == "unavailable" for point in warmup)
    assert all(point.arrow is None for point in series.points)
    assert all(point.arrow_reason is None for point in series.points)


def test_squeeze_pro_flat_price_data_does_not_raise() -> None:
    series = compute_squeeze_pro(_bars(80, flat=True))
    assert len(series.points) == 80
    assert any(point.status == "ok" for point in series.points)
    latest = next(point for point in reversed(series.points) if point.status == "ok")
    assert latest.squeeze_state in {"high", "mid", "low", "none"}
    assert latest.oscillator_value == 0


def test_squeeze_pro_output_is_deterministic() -> None:
    bars = _bars(90)
    first = compute_squeeze_pro(bars).model_dump()
    second = compute_squeeze_pro(bars).model_dump()
    assert first == second
