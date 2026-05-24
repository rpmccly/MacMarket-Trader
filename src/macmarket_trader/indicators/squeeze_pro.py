"""MacMarket Squeeze Pro research indicator.

This module implements Squeeze Pro compression states from user-provided
reference formulas. The histogram is a deterministic MacMarket approximation:
linear-regression momentum of close versus a rolling high/low + SMA midpoint.
It is not claimed to be exact Thinkorswim or TTM parity.
"""

from __future__ import annotations

from math import sqrt
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators.common import atr, sma

OscillatorState = Literal["up", "up_decreasing", "down", "down_decreasing"]
SqueezeState = Literal["high", "mid", "low", "none", "unavailable"]
ArrowEvent = Literal["bullish", "bearish"]


SQUEEZE_PRO_VERSION = "macmarket_squeeze_pro.v1"
SQUEEZE_PRO_HISTOGRAM_MODE = "macmarket_linear_regression_momentum_approximation"
SQUEEZE_PRO_ARROW_MODE = "disabled_pending_approved_arrow_rules"

SQUEEZE_STATE_COLORS: dict[str, str] = {
    "none": "#21c06e",
    "low": "#10151d",
    "mid": "#d14b4b",
    "high": "#f2a03f",
    "unavailable": "#5a6b7c",
}

OSCILLATOR_STATE_COLORS: dict[str, str] = {
    "up": "#4dd9ff",
    "up_decreasing": "#4d8dff",
    "down": "#d14b4b",
    "down_decreasing": "#ffd166",
}


class SqueezeProConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    length: int = Field(default=20, ge=2)
    nBB: float = 2.0
    nK_High: float = 1.0
    nK_Mid: float = 1.5
    nK_Low: float = 2.0
    price: str = "close"
    version: str = SQUEEZE_PRO_VERSION
    histogram_mode: str = SQUEEZE_PRO_HISTOGRAM_MODE
    arrow_mode: str = SQUEEZE_PRO_ARROW_MODE
    show_arrows: bool = False


class SqueezeProPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    oscillator_value: float | None = None
    oscillator_state: OscillatorState | None = None
    oscillator_color: str | None = None
    squeeze_state: SqueezeState = "unavailable"
    squeeze_color: str | None = None
    delta_high: float | None = None
    delta_mid: float | None = None
    delta_low: float | None = None
    arrow: ArrowEvent | None = None
    arrow_reason: str | None = None
    status: Literal["ok", "unavailable"] = "ok"
    reason: str | None = None


class SqueezeProSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: SqueezeProConfig
    points: list[SqueezeProPoint] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _rolling_stdev(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for idx, _value in enumerate(values):
        if idx < period - 1:
            out.append(None)
            continue
        window = values[idx - period + 1 : idx + 1]
        mean = sum(window) / period
        variance = sum((item - mean) ** 2 for item in window) / period
        out.append(sqrt(variance))
    return out


def _rolling_high(values: Sequence[float], period: int, idx: int) -> float:
    return max(values[idx - period + 1 : idx + 1])


def _rolling_low(values: Sequence[float], period: int, idx: int) -> float:
    return min(values[idx - period + 1 : idx + 1])


def _linear_regression_last(values: Sequence[float]) -> float:
    """Return the fitted value at the last x position for a value window."""
    count = len(values)
    if count == 0:
        return 0.0
    if count == 1:
        return float(values[0])
    x_mean = (count - 1) / 2.0
    y_mean = sum(values) / count
    denom = sum((idx - x_mean) ** 2 for idx in range(count))
    if denom == 0:
        return float(values[-1])
    slope = sum((idx - x_mean) * (values[idx] - y_mean) for idx in range(count)) / denom
    intercept = y_mean - slope * x_mean
    return intercept + slope * (count - 1)


def _momentum_oscillator(
    *,
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    length: int,
) -> list[float | None]:
    close_sma = sma(closes, length)
    raw: list[float | None] = []
    for idx, close in enumerate(closes):
        if idx < length - 1 or close_sma[idx] is None:
            raw.append(None)
            continue
        midpoint = (_rolling_high(highs, length, idx) + _rolling_low(lows, length, idx)) / 2.0
        baseline = (midpoint + float(close_sma[idx])) / 2.0
        raw.append(float(close) - baseline)

    out: list[float | None] = []
    for idx, value in enumerate(raw):
        if value is None or idx < length - 1:
            out.append(None)
            continue
        window = raw[idx - length + 1 : idx + 1]
        if any(item is None for item in window):
            out.append(None)
            continue
        out.append(_linear_regression_last([float(item) for item in window]))
    return out


def classify_squeeze_state(delta_high: float, delta_mid: float, delta_low: float) -> SqueezeState:
    if delta_high <= 0:
        return "high"
    if delta_mid <= 0:
        return "mid"
    if delta_low <= 0:
        return "low"
    return "none"


def classify_oscillator_state(current: float, previous: float) -> OscillatorState:
    if previous < current and current >= 0:
        return "up"
    if previous < current and current < 0:
        return "down_decreasing"
    if previous >= current and current >= 0:
        return "up_decreasing"
    return "down"


def compute_squeeze_pro(
    bars: Sequence[Bar],
    *,
    length: int = 20,
    nBB: float = 2.0,
    nK_High: float = 1.0,
    nK_Mid: float = 1.5,
    nK_Low: float = 2.0,
) -> SqueezeProSeries:
    config = SqueezeProConfig(length=length, nBB=nBB, nK_High=nK_High, nK_Mid=nK_Mid, nK_Low=nK_Low)
    bars_list = sorted(list(bars), key=lambda bar: (bar.timestamp or bar.date, bar.date))
    if not bars_list:
        return SqueezeProSeries(config=config, points=[], notes=["no chart bars provided"])

    highs = [float(bar.high) for bar in bars_list]
    lows = [float(bar.low) for bar in bars_list]
    closes = [float(bar.close) for bar in bars_list]

    basis = sma(closes, length)
    stdev = _rolling_stdev(closes, length)
    range_basis = atr(highs, lows, closes, length)
    oscillator = _momentum_oscillator(highs=highs, lows=lows, closes=closes, length=length)

    points: list[SqueezeProPoint] = []
    previous_valid_oscillator: float | None = None

    for idx, _bar in enumerate(bars_list):
        basis_value = basis[idx]
        stdev_value = stdev[idx]
        oscillator_value = oscillator[idx]
        if basis_value is None or stdev_value is None or oscillator_value is None:
            points.append(
                SqueezeProPoint(
                    index=idx,
                    squeeze_state="unavailable",
                    squeeze_color=SQUEEZE_STATE_COLORS["unavailable"],
                    status="unavailable",
                    reason="insufficient_bars_for_squeeze_pro",
                )
            )
            continue

        bb_upper = float(basis_value) + (nBB * float(stdev_value))
        center = float(basis_value)
        range_value = float(range_basis[idx])
        kc_upper_high = center + (nK_High * range_value)
        kc_upper_mid = center + (nK_Mid * range_value)
        kc_upper_low = center + (nK_Low * range_value)

        delta_high = bb_upper - kc_upper_high
        delta_mid = bb_upper - kc_upper_mid
        delta_low = bb_upper - kc_upper_low
        state = classify_squeeze_state(delta_high, delta_mid, delta_low)
        previous_oscillator = previous_valid_oscillator if previous_valid_oscillator is not None else float(oscillator_value)
        osc_state = classify_oscillator_state(float(oscillator_value), previous_oscillator)
        points.append(
            SqueezeProPoint(
                index=idx,
                oscillator_value=_round(float(oscillator_value)),
                oscillator_state=osc_state,
                oscillator_color=OSCILLATOR_STATE_COLORS[osc_state],
                squeeze_state=state,
                squeeze_color=SQUEEZE_STATE_COLORS[state],
                delta_high=_round(delta_high),
                delta_mid=_round(delta_mid),
                delta_low=_round(delta_low),
                arrow=None,
                arrow_reason=None,
            )
        )
        previous_valid_oscillator = float(oscillator_value)

    return SqueezeProSeries(
        config=config,
        points=points,
        notes=[
            "Squeeze Pro compression states use Bollinger upper versus three Keltner upper bands.",
            "Histogram uses MacMarket linear-regression momentum approximation; exact TTM histogram parity is not claimed.",
            "Arrow logic is deferred until approved arrow rules are provided.",
        ],
    )


__all__ = [
    "OSCILLATOR_STATE_COLORS",
    "SQUEEZE_PRO_ARROW_MODE",
    "SQUEEZE_PRO_HISTOGRAM_MODE",
    "SQUEEZE_PRO_VERSION",
    "SQUEEZE_STATE_COLORS",
    "SqueezeProConfig",
    "SqueezeProPoint",
    "SqueezeProSeries",
    "classify_oscillator_state",
    "classify_squeeze_state",
    "compute_squeeze_pro",
]
