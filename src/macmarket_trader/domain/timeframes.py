"""Shared chart timeframe constants.

The chart and workflow APIs intentionally keep this list narrow. New
timeframes should be wired through provider mapping, chart time rendering, and
operator UI controls together so workflow provenance stays auditable.
"""

from __future__ import annotations

from typing import Literal, TypeAlias

ChartTimeframe: TypeAlias = Literal["1W", "1D", "4H", "1H", "30M"]

DEFAULT_CHART_TIMEFRAME: ChartTimeframe = "1D"
SUPPORTED_CHART_TIMEFRAMES: tuple[ChartTimeframe, ...] = ("1W", "1D", "4H", "1H", "30M")
SUPPORTED_CHART_TIMEFRAME_SET = set(SUPPORTED_CHART_TIMEFRAMES)
INTRADAY_CHART_TIMEFRAMES: tuple[ChartTimeframe, ...] = ("30M", "1H", "4H")
INTRADAY_CHART_TIMEFRAME_SET = set(INTRADAY_CHART_TIMEFRAMES)
REGULAR_HOURS_SOURCE_TIMEFRAME: ChartTimeframe = "30M"

CHART_BAR_LIMIT_BY_TIMEFRAME: dict[ChartTimeframe, int] = {
    "1W": 156,
    "1D": 120,
    "4H": 200,
    "1H": 400,
    "30M": 500,
}


def normalize_chart_timeframe(value: object, *, default: ChartTimeframe = DEFAULT_CHART_TIMEFRAME) -> str:
    candidate = str(value or default).strip().upper()
    return candidate or default


def is_supported_chart_timeframe(value: object) -> bool:
    return normalize_chart_timeframe(value) in SUPPORTED_CHART_TIMEFRAME_SET


def validate_chart_timeframe(value: object, *, default: ChartTimeframe = DEFAULT_CHART_TIMEFRAME) -> ChartTimeframe:
    timeframe = normalize_chart_timeframe(value, default=default)
    if timeframe not in SUPPORTED_CHART_TIMEFRAME_SET:
        raise ValueError(chart_timeframe_error_message())
    return timeframe  # type: ignore[return-value]


def chart_timeframe_error_message() -> str:
    return f"timeframe must be one of: {', '.join(SUPPORTED_CHART_TIMEFRAMES)}"


def is_intraday_chart_timeframe(value: object) -> bool:
    return normalize_chart_timeframe(value) in INTRADAY_CHART_TIMEFRAME_SET
