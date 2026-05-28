import pytest

from macmarket_trader.indicators import (
    compute_haco_states,
    compute_hacolt_direction,
    compute_metastock_haco,
    compute_thinkorswim_hacolt,
    legacy_haco_ema_3_8,
    legacy_hacolt_ema_21_55,
    metastock_alert,
)


def _bars_from_closes(closes: list[float]) -> tuple[list[float], list[float], list[float], list[float]]:
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    previous = closes[0]
    for close in closes:
        open_ = previous
        opens.append(float(open_))
        highs.append(float(max(open_, close) + 1.0))
        lows.append(float(min(open_, close) - 1.0))
        previous = close
    return opens, highs, lows, [float(item) for item in closes]


def test_metastock_alert_uses_current_or_previous_bar() -> None:
    assert metastock_alert([False, True, False, False, True], 2) == [False, True, True, False, True]


def test_metastock_haco_output_shape_values_and_flips() -> None:
    opens, highs, lows, closes = _bars_from_closes([100, 98, 96, 94, 92, 90, 91, 93, 96, 99, 102, 104, 105])

    result = compute_metastock_haco(opens, highs, lows, closes)
    points = result.points

    assert len(points) == len(closes)
    assert {point.state_value for point in points}.issubset({0, 100})
    assert {point.state for point in points}.issubset({"green", "red"})

    flips = [(idx, point.flip) for idx, point in enumerate(points) if point.flip]
    assert flips == [(2, "sell"), (9, "buy")]
    for idx, _flip in flips:
        assert points[idx].state != points[idx - 1].state
    assert sum(points[idx].state != points[idx - 1].state for idx in range(1, len(points))) == len(flips)


def test_metastock_haco_recursive_prev_result_holds_until_flip() -> None:
    opens, highs, lows, closes = _bars_from_closes([100, 98, 96, 94, 92, 90, 91, 93, 96, 99, 102, 104, 105])

    result = compute_metastock_haco(opens, highs, lows, closes)

    assert result.debug.dnw[2] is True
    assert result.debug.result[2:9] == [0, 0, 0, 0, 0, 0, 0]
    assert result.debug.upw[9] is True
    assert result.debug.result[9:] == [1, 1, 1, 1]
    assert result.debug.ha_open[0] == pytest.approx((opens[0] + highs[0] + lows[0] + closes[0]) / 4.0)


def test_compute_haco_states_is_active_ohlc_formula_and_legacy_is_explicit() -> None:
    opens, highs, lows, closes = _bars_from_closes([10, 11, 12, 11, 10, 9, 10, 11])

    active = compute_haco_states(opens, highs, lows, closes)
    legacy = legacy_haco_ema_3_8(closes)

    assert len(active) == len(legacy) == len(closes)
    with pytest.raises(ValueError, match="requires OHLC arrays"):
        compute_haco_states(closes)


def test_thinkorswim_hacolt_output_shape_values_and_negative_factor() -> None:
    opens, highs, lows, closes = _bars_from_closes([100, 98, 96, 94, 92, 90] + list(range(92, 150, 2)))

    result = compute_thinkorswim_hacolt(opens, highs, lows, closes)
    points = result.points

    assert len(points) == len(closes)
    assert {point.strip_value for point in points}.issubset({0, 50, 100})
    assert {point.direction for point in points}.issubset({"up", "neutral", "down"})
    with pytest.raises(ValueError, match="must not be negative"):
        compute_thinkorswim_hacolt(opens, highs, lows, closes, candle_size_factor=-0.1)


def test_thinkorswim_hacolt_recursive_upwsave_and_neutral_state() -> None:
    closes = [100, 98, 96, 94, 92, 90] + list(range(92, 170, 2)) + list(range(169, 159, -1)) + list(range(159, 180))
    opens, highs, lows, closes = _bars_from_closes(closes)

    result = compute_thinkorswim_hacolt(opens, highs, lows, closes)

    assert result.debug.upw[11] is True
    assert result.points[11].strip_value == 100
    assert result.debug.dnw[52] is True
    assert result.debug.buy[52] is False
    assert result.debug.long_term_sell[52] is False
    assert result.debug.neutral[52] is True
    assert result.points[52].strip_value == 50
    assert result.points[52].direction == "neutral"
    assert all(point.strip_value == 50 for point in result.points[52:60])


def test_compute_hacolt_direction_is_active_ohlc_formula_and_legacy_is_explicit() -> None:
    opens, highs, lows, closes = _bars_from_closes([10, 9, 8, 9, 10, 11, 12, 11])

    active = compute_hacolt_direction(opens, highs, lows, closes)
    legacy = legacy_hacolt_ema_21_55(closes)

    assert len(active) == len(legacy) == len(closes)
    with pytest.raises(ValueError, match="requires OHLC arrays"):
        compute_hacolt_direction(closes)
