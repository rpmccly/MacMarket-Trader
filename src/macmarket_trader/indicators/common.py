"""Common deterministic indicator helpers."""

from __future__ import annotations

import math
from typing import Iterable, Sequence


def is_finite(value: float | None) -> bool:
    return value is not None and not math.isnan(value) and not math.isinf(value)


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    if not is_finite(denominator) or denominator == 0:
        return default
    return numerator / denominator


def ema(values: Iterable[float], period: int) -> list[float]:
    """Return EMA series with deterministic seed using first value."""
    values_list = list(values)
    if not values_list:
        return []
    if period <= 0:
        raise ValueError("period must be > 0")

    k = 2.0 / (period + 1)
    out = [values_list[0]]
    for value in values_list[1:]:
        out.append((value * k) + (out[-1] * (1.0 - k)))
    return out


def sma(values: Sequence[float], period: int) -> list[float | None]:
    """Simple moving average. First period-1 entries are None."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if not values:
        return []
    out: list[float | None] = []
    running = 0.0
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out.append(running / period)
        else:
            out.append(None)
    return out


def heikin_ashi_candles(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float]
) -> tuple[list[float], list[float], list[float], list[float]]:
    """Project OHLC into Heikin-Ashi OHLC."""
    if not (len(opens) == len(highs) == len(lows) == len(closes)):
        raise ValueError("OHLC arrays must be the same length")
    if not opens:
        return [], [], [], []

    ha_close = [(o + h + l + c) / 4.0 for o, h, l, c in zip(opens, highs, lows, closes, strict=True)]
    ha_open = [((opens[0] + closes[0]) / 2.0)]
    for i in range(1, len(opens)):
        ha_open.append((ha_open[i - 1] + ha_close[i - 1]) / 2.0)

    ha_high = [max(h, ho, hc) for h, ho, hc in zip(highs, ha_open, ha_close, strict=True)]
    ha_low = [min(l, ho, hc) for l, ho, hc in zip(lows, ha_open, ha_close, strict=True)]
    return ha_open, ha_high, ha_low, ha_close


def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> list[float]:
    """Wilder true range. First bar uses high-low only."""
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("HLC arrays must be the same length")
    out: list[float] = []
    for i in range(len(highs)):
        h = float(highs[i])
        l = float(lows[i])
        if i == 0:
            out.append(max(0.0, h - l))
            continue
        prev_close = float(closes[i - 1])
        out.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
    return out


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int) -> list[float]:
    """Wilder-style ATR using deterministic recursive smoothing.

    ATR[0] = TR[0]; ATR[i] = (ATR[i-1] * (period - 1) + TR[i]) / period.
    """
    if period <= 0:
        raise ValueError("period must be > 0")
    tr = true_range(highs, lows, closes)
    if not tr:
        return []
    out = [tr[0]]
    for i in range(1, len(tr)):
        out.append((out[-1] * (period - 1) + tr[i]) / period)
    return out


def crosses_above(series_a: Sequence[float], series_b: Sequence[float] | float) -> list[bool]:
    """ThinkScript-style cross above: prev a <= prev b and current a > current b."""
    if isinstance(series_b, (int, float)):
        threshold = [float(series_b)] * len(series_a)
    else:
        if len(series_a) != len(series_b):
            raise ValueError("series must be the same length")
        threshold = list(series_b)
    out = [False] * len(series_a)
    for i in range(1, len(series_a)):
        out[i] = series_a[i - 1] <= threshold[i - 1] and series_a[i] > threshold[i]
    return out


def crosses_below(series_a: Sequence[float], series_b: Sequence[float] | float) -> list[bool]:
    """ThinkScript-style cross below: prev a >= prev b and current a < current b."""
    if isinstance(series_b, (int, float)):
        threshold = [float(series_b)] * len(series_a)
    else:
        if len(series_a) != len(series_b):
            raise ValueError("series must be the same length")
        threshold = list(series_b)
    out = [False] * len(series_a)
    for i in range(1, len(series_a)):
        out[i] = series_a[i - 1] >= threshold[i - 1] and series_a[i] < threshold[i]
    return out


def _rolling_extreme(values: Sequence[float], period: int, *, find_max: bool) -> list[float]:
    if period <= 0:
        raise ValueError("period must be > 0")
    out: list[float] = []
    for i in range(len(values)):
        start = max(0, i - period + 1)
        window = values[start : i + 1]
        out.append(max(window) if find_max else min(window))
    return out


def stochastic_full(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    over_bought: float,
    over_sold: float,
    k_period: int,
    d_period: int,
    slowing_period: int,
) -> tuple[list[float], list[float]]:
    """ThinkScript-style StochasticFull approximation with exponential smoothing.

    Returns (SlowK, SlowD). FastK is scaled into [over_sold, over_bought]:
        FastK = (over_bought - over_sold) * (C - LL) / (HH - LL) + over_sold
    SlowK = EMA(FastK, slowing_period); SlowD = EMA(SlowK, d_period).
    """
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("HLC arrays must be the same length")
    if k_period <= 0 or d_period <= 0 or slowing_period <= 0:
        raise ValueError("periods must be > 0")
    if not closes:
        return [], []
    rolling_high = _rolling_extreme(highs, k_period, find_max=True)
    rolling_low = _rolling_extreme(lows, k_period, find_max=False)
    fast_k: list[float] = []
    span = float(over_bought - over_sold)
    for hh, ll, c in zip(rolling_high, rolling_low, closes, strict=True):
        denom = hh - ll
        if denom <= 0:
            fast_k.append(float(over_sold) + span * 0.5)
        else:
            fast_k.append(float(over_sold) + span * ((c - ll) / denom))
    slow_k = ema(fast_k, slowing_period)
    slow_d = ema(slow_k, d_period)
    return slow_k, slow_d
