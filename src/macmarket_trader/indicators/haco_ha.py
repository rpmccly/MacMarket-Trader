"""HACO with MetaStock Heikin-Ashi internals exposed for chart display."""

from __future__ import annotations

from macmarket_trader.indicators.haco import HacoPoint, compute_metastock_haco


def compute_haco_from_ha(
    opens: list[float], highs: list[float], lows: list[float], closes: list[float]
) -> tuple[list[float], list[float], list[float], list[float], list[HacoPoint]]:
    result = compute_metastock_haco(opens, highs, lows, closes)
    ha_open = result.debug.ha_open
    ha_close = result.debug.ha_c
    ha_high = [max(high, ha_o, ha_c) for high, ha_o, ha_c in zip(highs, ha_open, ha_close, strict=True)]
    ha_low = [min(low, ha_o, ha_c) for low, ha_o, ha_c in zip(lows, ha_open, ha_close, strict=True)]
    return ha_open, ha_high, ha_low, ha_close, result.points
