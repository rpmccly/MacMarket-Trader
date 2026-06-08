"""Unit + parity tests for the ATR Trailing Stop indicator (math is frozen)."""

from __future__ import annotations

from datetime import date

import pytest

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators.atr_trailing_stop import (
    AtrTrailingStopConfig,
    _modified_true_range,
    _moving_average,
    _wilders,
    compute_atr_trailing_stop,
    normalize_config,
)
from macmarket_trader.indicators.common import true_range


def _bar(day: int, o: float, h: float, l: float, c: float, v: int = 1_000_000) -> Bar:
    return Bar(date=date(2026, 1, day), open=o, high=h, low=l, close=c, volume=v)


def _rising(n: int) -> list[Bar]:
    return [_bar(i + 1, 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(n)]


# ── helpers ──────────────────────────────────────────────────────────────────
def test_wilders_smoothing_recurrence() -> None:
    # seeded with first value; out[i] = (out[i-1]*(p-1) + x[i]) / p
    assert _wilders([1.0, 2.0, 3.0], 2) == pytest.approx([1.0, 1.5, 2.25])


def test_moving_average_dispatch() -> None:
    series = [2.0, 4.0, 6.0, 8.0]
    assert _moving_average("wilders", series, 2) == pytest.approx(_wilders(series, 2))
    # simple uses an expanding window before `period`
    assert _moving_average("simple", series, 2) == pytest.approx([2.0, 3.0, 5.0, 7.0])


def test_unmodified_true_range_matches_common() -> None:
    bars = _rising(6)
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    series = compute_atr_trailing_stop(bars, config={"trail_type": "unmodified", "atr_period": 3})
    expected_tr = true_range(highs, lows, closes)
    assert [p.true_range for p in series.points] == pytest.approx([round(v, 6) for v in expected_tr])


def test_modified_true_range_first_bar_is_high_low_and_differs() -> None:
    bars = _rising(8)
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    modified = _modified_true_range(highs, lows, closes, 5)
    assert modified[0] == pytest.approx(highs[0] - lows[0])
    assert len(modified) == len(bars)
    assert all(v >= 0 for v in modified)


# ── insufficient bars ────────────────────────────────────────────────────────
def test_no_bars_is_safe() -> None:
    series = compute_atr_trailing_stop([])
    assert series.points == []
    assert "no_bars" in series.notes


def test_single_bar_initializes_to_first_trade() -> None:
    bar = _bar(1, 100, 102, 98, 100)
    series = compute_atr_trailing_stop([bar], config={"trail_type": "unmodified", "atr_factor": 2.0})
    point = series.points[-1]
    assert point.state == "long"  # first_trade default long
    # loss = factor * TR[0] = 2.0 * (102 - 98) = 8.0 ; trail = close - loss = 92
    assert point.loss == pytest.approx(8.0)
    assert point.trailing_stop == pytest.approx(92.0)
    assert point.stop_distance == pytest.approx(8.0)
    assert point.bars_since_flip == 0
    assert point.last_flip_direction == "long"


def test_first_trade_short_initializes_short() -> None:
    bar = _bar(1, 100, 102, 98, 100)
    series = compute_atr_trailing_stop([bar], config={"first_trade": "short", "trail_type": "unmodified", "atr_factor": 2.0})
    point = series.points[-1]
    assert point.state == "short"
    assert point.trailing_stop == pytest.approx(108.0)  # close + loss


# ── state transitions + flips ────────────────────────────────────────────────
def test_rising_trend_stays_long_no_flips() -> None:
    series = compute_atr_trailing_stop(_rising(15), config={"trail_type": "unmodified", "atr_factor": 1.0, "atr_period": 5})
    assert all(p.state == "long" for p in series.points)
    assert not any(p.sell_signal for p in series.points)
    # long trailing stop sits below price
    assert series.points[-1].trailing_stop < series.points[-1].close


def test_long_flips_short_on_drop_below_trail() -> None:
    bars = _rising(10) + [_bar(11, 109, 109.5, 104, 104.5)]
    series = compute_atr_trailing_stop(bars, config={"trail_type": "unmodified", "atr_factor": 1.0, "atr_period": 5})
    last = series.points[-1]
    assert last.state == "short"
    assert last.sell_signal is True
    assert last.buy_signal is False
    assert last.last_flip_direction == "short"
    assert last.bars_since_flip == 0
    assert last.trailing_stop > last.close  # short trail sits above price


def test_short_first_trade_flips_long_on_rising_prices() -> None:
    series = compute_atr_trailing_stop(
        _rising(15), config={"trail_type": "unmodified", "atr_factor": 1.0, "atr_period": 5, "first_trade": "short"}
    )
    assert series.points[0].state == "short"
    assert any(p.buy_signal for p in series.points)
    assert series.points[-1].state == "long"


def test_stop_distance_pct_is_consistent() -> None:
    series = compute_atr_trailing_stop(_rising(12), config={"trail_type": "modified"})
    for point in series.points:
        if point.close:
            assert point.stop_distance == pytest.approx(abs(point.close - point.trailing_stop), abs=1e-6)
            assert point.stop_distance_pct == pytest.approx(point.stop_distance / point.close * 100.0, abs=1e-3)


# ── config normalization ─────────────────────────────────────────────────────
def test_defaults() -> None:
    cfg = AtrTrailingStopConfig()
    assert (cfg.trail_type, cfg.atr_period, cfg.atr_factor, cfg.first_trade, cfg.average_type) == (
        "modified", 9, 2.9, "long", "wilders",
    )


def test_normalize_config_rejects_bad_input() -> None:
    cfg = normalize_config({
        "trail_type": "weird", "atr_period": -5, "atr_factor": 0, "first_trade": "sideways", "average_type": "kalman",
    })
    assert cfg.trail_type == "modified"
    assert cfg.atr_period == 1
    assert cfg.atr_factor == 2.9
    assert cfg.first_trade == "long"
    assert cfg.average_type == "wilders"
