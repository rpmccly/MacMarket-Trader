"""HiLo Elite oscillator (deterministic Python port).

Source: ST_HiLoEliteSTUDY.ts and the HLP_X helper script inside
ST_TrueMomentumScoreSTUDY.ts (licensed/proprietary reference). Math/state
logic is ported here as deterministic Python; production use of this module
assumes the operator has the rights to use/port the source studies.
"""

from __future__ import annotations

from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators.common import crosses_above, crosses_below, stochastic_full

Timeframe = Literal["1D", "4H", "1H"]
PresetCategory = Literal["above_day", "day", "intraday"]


def _preset_category(timeframe: Timeframe) -> PresetCategory:
    if timeframe == "1D":
        return "day"
    return "intraday"


_LEVELS_ABOVE_DAY = {
    "OB": [28.66, 34.45, 37.25, 40.0, 43.4, 47.4, 50.11, 55.9, 58.75, 62.4, 65.3, 67.03, 68.8, 72.35, 73.25],
    "OS": [76.25, 72.55, 70.11, 67.5, 65.85, 62.6, 60.5, 56.4, 53.0, 45.3, 42.5, 40.0, 37.4, 35.15, 33.2],
}
_LEVELS_DAY = {
    "OB": [29.5, 33.0, 34.94, 38.2, 41.9, 43.9, 49.2, 52.5, 55.0, 59.7, 62.67, 65.75, 68.24, 71.9, 73.6],
    "OS": [77.95, 74.0, 72.36, 70.0, 67.07, 66.22, 65.5, 64.5, 63.0, 60.3, 57.0, 51.67, 44.25, 41.95, 40.0],
}
_LEVELS_INTRADAY = {
    "OB": [27.6, 32.0, 34.9, 38.0, 40.0, 43.9, 47.9, 52.4, 57.05, 61.0, 65.4, 67.9, 69.95, 73.0, 74.5],
    "OS": [75.65, 73.4, 71.1, 70.0, 67.95, 65.5, 63.6, 62.45, 59.9, 58.1, 55.9, 48.01, 45.0, 42.0, 39.9],
}


def _levels(category: PresetCategory) -> dict[str, list[float]]:
    if category == "above_day":
        return _LEVELS_ABOVE_DAY
    if category == "day":
        return _LEVELS_DAY
    return _LEVELS_INTRADAY


def _slow_d_periods(category: PresetCategory) -> tuple[int, int, int]:
    """Returns (k_period, d_period, slowing_period) for the SlowD line."""
    if category == "day":
        return 99, 3, 3
    return 50, 3, 3


class HiLoEliteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeframe: Timeframe = "1D"
    preset_category: PresetCategory
    over_bought_levels: list[float]
    over_sold_levels: list[float]
    slow_d_k_period: int
    slow_d_d_period: int
    slow_d_slowing: int
    slow_d_x_k_period: int = 20
    slow_d_x_d_period: int = 50
    slow_d_x_slowing: int = 3


def config_for_timeframe(timeframe: Timeframe) -> HiLoEliteConfig:
    category = _preset_category(timeframe)
    levels = _levels(category)
    k, d, slowing = _slow_d_periods(category)
    return HiLoEliteConfig(
        timeframe=timeframe,
        preset_category=category,
        over_bought_levels=levels["OB"],
        over_sold_levels=levels["OS"],
        slow_d_k_period=k,
        slow_d_d_period=d,
        slow_d_slowing=slowing,
    )


class HiLoElitePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    slow_k: float
    slow_d: float
    slow_d_x: float
    slow_k_x: float
    any_buy: bool
    any_sell: bool
    thrust: int
    thrust_changed: bool
    bull_cycle: bool
    bear_cycle: bool
    hlp_a: int
    hlp_b: int
    hlp_output: int
    double_buy: bool
    double_buy2: bool
    double_sell: bool


class HiLoEliteSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeframe: Timeframe
    config: HiLoEliteConfig
    points: list[HiLoElitePoint] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _between(value: float, low: float, high: float) -> bool:
    return value >= low and value <= high


def compute_hilo_elite(bars: Sequence[Bar], *, timeframe: Timeframe = "1D") -> HiLoEliteSeries:
    config = config_for_timeframe(timeframe)
    bars_list = sorted(list(bars), key=lambda b: (b.timestamp or b.date, b.date))
    if not bars_list:
        return HiLoEliteSeries(timeframe=timeframe, config=config, points=[], notes=["no chart bars provided"])

    highs = [b.high for b in bars_list]
    lows = [b.low for b in bars_list]
    closes = [b.close for b in bars_list]

    slow_k, slow_d = stochastic_full(
        highs, lows, closes,
        over_bought=80.0, over_sold=20.0,
        k_period=config.slow_d_k_period, d_period=config.slow_d_d_period, slowing_period=config.slow_d_slowing,
    )
    slow_k_x, slow_d_x = stochastic_full(
        highs, lows, closes,
        over_bought=80.0, over_sold=20.0,
        k_period=config.slow_d_x_k_period, d_period=config.slow_d_x_d_period, slowing_period=config.slow_d_x_slowing,
    )

    ob = config.over_bought_levels
    os = config.over_sold_levels

    up_d_flags = [crosses_above(slow_d, os[i]) for i in range(15)]
    down_d_flags = [crosses_below(slow_d, ob[i]) for i in range(15)]

    n = len(bars_list)
    points: list[HiLoElitePoint] = []
    thrust = 0
    for i in range(n):
        d_now = slow_d[i]
        d_prev = slow_d[i - 1] if i > 0 else d_now
        d_diff = d_now - d_prev

        ob_sell = _between(d_now, 85.71, 87.38) and d_diff <= -1.88
        ob_sell2 = _between(d_now, 92.11, 94.329) and d_diff <= -2.11
        ob_sell3 = _between(d_now, 80.6, 100.0) and d_diff <= -2.73
        ob_sell4 = _between(d_now, 87.39, 91.08) and d_diff <= -2.11

        ob_buy = _between(d_now, 90.68, 93.16) and d_diff >= 2.08
        ob_buy2 = _between(d_now, 87.0, 96.0) and d_diff >= 2.5
        ob_buy3 = _between(d_now, 93.48, 95.43) and d_diff >= 1.405
        ob_buy4 = _between(d_now, 81.0, 100.0) and d_diff >= 3.14

        os_sell = _between(d_now, 12.75, 24.6) and d_diff <= -3.3
        os_sell2 = _between(d_now, 1.0, 76.0) and d_diff <= -4.6
        os_sell3 = _between(d_now, 1.0, 100.0) and d_diff <= -6.0

        os_buy = _between(d_now, 37.6, 100.0) and d_diff >= 4.0
        os_buy2 = _between(d_now, 20.5, 100.0) and d_diff >= 5.05

        double_buy = d_now >= d_prev * 1.42 and d_now >= 10.0
        double_buy2 = d_now >= d_prev * 1.57 and d_now >= 7.5 and d_now < 10.0
        double_sell = d_now <= d_prev * 0.86 and d_now >= 10.0

        any_buy = (
            any(up_d_flags[k][i] for k in range(15))
            or ob_buy or ob_buy2 or ob_buy3 or ob_buy4
            or os_buy or os_buy2 or double_buy or double_buy2
        )
        any_sell = (
            any(down_d_flags[k][i] for k in range(15))
            or os_sell or os_sell2 or os_sell3
            or ob_sell or ob_sell2 or ob_sell3 or ob_sell4
            or double_sell
        )

        prev_thrust = thrust
        if any_buy:
            thrust = 1
        elif any_sell:
            thrust = -1

        thrust_changed = thrust != prev_thrust
        bull_cycle = slow_d[i] > slow_d_x[i]
        bear_cycle = slow_d[i] < slow_d_x[i]

        hlp_a = 5 if thrust == 1 else (-5 if thrust == -1 else 0)
        if thrust == 1 and bull_cycle:
            hlp_b = 15
        elif thrust == -1 and bear_cycle:
            hlp_b = -15
        else:
            hlp_b = 0
        hlp_output = hlp_a + hlp_b

        points.append(
            HiLoElitePoint(
                index=i,
                slow_k=slow_k[i],
                slow_d=slow_d[i],
                slow_d_x=slow_d_x[i],
                slow_k_x=slow_k_x[i],
                any_buy=bool(any_buy),
                any_sell=bool(any_sell),
                thrust=thrust,
                thrust_changed=bool(thrust_changed),
                bull_cycle=bool(bull_cycle),
                bear_cycle=bool(bear_cycle),
                hlp_a=hlp_a,
                hlp_b=hlp_b,
                hlp_output=hlp_output,
                double_buy=bool(double_buy),
                double_buy2=bool(double_buy2),
                double_sell=bool(double_sell),
            )
        )

    return HiLoEliteSeries(timeframe=timeframe, config=config, points=points, notes=[])


__all__ = [
    "HiLoEliteConfig",
    "HiLoElitePoint",
    "HiLoEliteSeries",
    "compute_hilo_elite",
    "config_for_timeframe",
]
