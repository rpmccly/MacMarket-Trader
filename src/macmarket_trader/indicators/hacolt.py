"""Thinkorswim/Schwab HACOLT parity implementation.

The active HACOLT calculation follows the Thinkorswim/Schwab source captured
for this pass. Thinkorswim ``ExpAverage`` and ``TEMA`` can use prefetch/warmup
behavior; MacMarket's deterministic helpers seed from the first loaded bar, so
early bars can differ when insufficient warmup history is loaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from pydantic import BaseModel

from macmarket_trader.indicators.common import ema, tema
from macmarket_trader.indicators.haco import _validate_ohlc


class HacoltPoint(BaseModel):
    direction: str
    strip_value: int
    spread: float


@dataclass(frozen=True)
class ThinkorswimHacoltDebug:
    ha_open: list[float]
    ha_close: list[float]
    tema_ha_close: list[float]
    zero_lag_ha_close: list[float]
    tema_typ_price: list[float]
    zero_lag_typ_price: list[float]
    short_candle: list[bool]
    keep_green: list[bool]
    keep_green_all: list[bool]
    utr: list[bool]
    keep_red: list[bool]
    keep_red_all: list[bool]
    dtr: list[bool]
    upw: list[bool]
    dnw: list[bool]
    upw_save: list[bool]
    buy: list[bool]
    long_term_sell: list[bool]
    neutral: list[bool]
    hacolt_value: list[int]


@dataclass(frozen=True)
class ThinkorswimHacoltResult:
    points: list[HacoltPoint]
    debug: ThinkorswimHacoltDebug


def _tos_zero_lag_tema(series: Sequence[float], period: int) -> tuple[list[float], list[float]]:
    first = tema(series, period)
    second = tema(first, period)
    return first, [(2.0 * a) - b for a, b in zip(first, second, strict=True)]


def legacy_hacolt_ema_21_55(closes: Sequence[float]) -> list[HacoltPoint]:
    """Legacy close-only HACOLT proxy kept explicitly out of the active path."""
    close_values = [float(item) for item in closes]
    if not close_values:
        return []
    mid = ema(close_values, period=21)
    long = ema(close_values, period=55)
    out: list[HacoltPoint] = []
    for m, l in zip(mid, long, strict=True):
        bull = m >= l
        out.append(HacoltPoint(direction="up" if bull else "down", strip_value=100 if bull else 0, spread=m - l))
    return out


def compute_thinkorswim_hacolt(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    tema_length: int = 55,
    ema_length: int = 60,
    candle_size_factor: float = 1.1,
) -> ThinkorswimHacoltResult:
    if tema_length <= 0 or ema_length <= 0:
        raise ValueError("tema_length and ema_length must be > 0")
    if candle_size_factor < 0:
        raise ValueError("candle_size_factor must not be negative")
    open_values, high_values, low_values, close_values = _validate_ohlc(opens, highs, lows, closes)
    if not open_values:
        debug = ThinkorswimHacoltDebug([], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], [])
        return ThinkorswimHacoltResult(points=[], debug=debug)

    ohlc4 = [(o + h + l + c) / 4.0 for o, h, l, c in zip(open_values, high_values, low_values, close_values, strict=True)]
    hl2 = [(h + l) / 2.0 for h, l in zip(high_values, low_values, strict=True)]
    ha_open = [ohlc4[0]]
    for idx in range(1, len(ohlc4)):
        ha_open.append((ha_open[idx - 1] + ohlc4[idx - 1]) / 2.0)
    ha_close = [
        (ha_o + max(high, ha_o) + min(low, ha_o) + typical) / 4.0
        for ha_o, high, low, typical in zip(ha_open, high_values, low_values, ohlc4, strict=True)
    ]

    tema_ha_close, zero_lag_ha_close = _tos_zero_lag_tema(ha_close, tema_length)
    tema_typ_price, zero_lag_typ_price = _tos_zero_lag_tema(hl2, tema_length)
    close_ema = ema(close_values, ema_length)
    short_candle = [
        abs(c - o) < (h - l) * candle_size_factor
        for o, h, l, c in zip(open_values, high_values, low_values, close_values, strict=True)
    ]

    keep_green: list[bool] = []
    keep_green_all: list[bool] = []
    utr: list[bool] = []
    keep_red: list[bool] = []
    keep_red_all: list[bool] = []
    dtr: list[bool] = []
    upw: list[bool] = []
    dnw: list[bool] = []
    upw_save: list[bool] = []
    buy: list[bool] = []
    long_term_sell: list[bool] = []
    neutral: list[bool] = []
    hacolt_value: list[int] = []

    for idx, (o, h, l, c) in enumerate(zip(open_values, high_values, low_values, close_values, strict=True)):
        has_prev = idx > 0
        prev_h = high_values[idx - 1] if has_prev else h
        prev_l = low_values[idx - 1] if has_prev else l
        prev_c = close_values[idx - 1] if has_prev else c
        prev_ha_green = ha_close[idx - 1] >= ha_open[idx - 1] if has_prev else False
        prev_ha_red = ha_close[idx - 1] < ha_open[idx - 1] if has_prev else False

        keep_green.append(
            ha_close[idx] >= ha_open[idx]
            or prev_ha_green
            or c >= ha_close[idx]
            or (has_prev and h > prev_h)
            or (has_prev and l > prev_l)
            or zero_lag_typ_price[idx] >= zero_lag_ha_close[idx]
        )
        prev_keep_green = keep_green[idx - 1] if has_prev else False
        keep_green_all.append(keep_green[idx] or (prev_keep_green and (c >= o or (has_prev and c >= prev_c))))
        hold_long = short_candle[idx] and has_prev and h >= prev_l
        prev_keep_green_all = keep_green_all[idx - 1] if has_prev else False
        utr.append(keep_green_all[idx] or (prev_keep_green_all and hold_long))

        keep_red.append(ha_close[idx] < ha_open[idx] or prev_ha_red or zero_lag_typ_price[idx] < zero_lag_ha_close[idx])
        prev_keep_red = keep_red[idx - 1] if has_prev else False
        keep_red_all.append(keep_red[idx] or (prev_keep_red and (c < o or (has_prev and c < prev_c))))
        hold_short = short_candle[idx] and has_prev and l <= prev_h
        prev_keep_red_all = keep_red_all[idx - 1] if has_prev else False
        dtr.append(keep_red_all[idx] or (prev_keep_red_all and hold_short))

        prev_dtr = dtr[idx - 1] if has_prev else False
        prev_utr = utr[idx - 1] if has_prev else False
        upw.append((not dtr[idx]) and prev_dtr and utr[idx])
        dnw.append((not utr[idx]) and prev_utr and dtr[idx])
        prev_upw_save = upw_save[idx - 1] if has_prev else False
        upw_save.append(upw[idx] if (upw[idx] or dnw[idx]) else prev_upw_save)
        buy.append(upw[idx] or ((not dnw[idx]) and upw_save[idx]))
        long_term_sell.append(c < close_ema[idx])
        prev_neutral = neutral[idx - 1] if has_prev else False
        neutral.append(buy[idx] or (False if long_term_sell[idx] else prev_neutral))
        hacolt_value.append(100 if buy[idx] else (50 if neutral[idx] else 0))

    points = [
        HacoltPoint(
            direction="up" if value == 100 else ("neutral" if value == 50 else "down"),
            strip_value=value,
            spread=zero_lag_typ_price[idx] - zero_lag_ha_close[idx],
        )
        for idx, value in enumerate(hacolt_value)
    ]
    debug = ThinkorswimHacoltDebug(
        ha_open=ha_open,
        ha_close=ha_close,
        tema_ha_close=tema_ha_close,
        zero_lag_ha_close=zero_lag_ha_close,
        tema_typ_price=tema_typ_price,
        zero_lag_typ_price=zero_lag_typ_price,
        short_candle=short_candle,
        keep_green=keep_green,
        keep_green_all=keep_green_all,
        utr=utr,
        keep_red=keep_red,
        keep_red_all=keep_red_all,
        dtr=dtr,
        upw=upw,
        dnw=dnw,
        upw_save=upw_save,
        buy=buy,
        long_term_sell=long_term_sell,
        neutral=neutral,
        hacolt_value=hacolt_value,
    )
    return ThinkorswimHacoltResult(points=points, debug=debug)


def compute_hacolt_direction(
    opens: Sequence[float],
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
    closes: Sequence[float] | None = None,
    *,
    tema_length: int = 55,
    ema_length: int = 60,
    candle_size_factor: float = 1.1,
) -> list[HacoltPoint]:
    """Return active Thinkorswim/Schwab HACOLT points.

    This function now requires full OHLC arrays. Use
    ``legacy_hacolt_ema_21_55`` for the retired close-only proxy.
    """
    if highs is None or lows is None or closes is None:
        raise ValueError("compute_hacolt_direction requires OHLC arrays; use legacy_hacolt_ema_21_55 for the old close-only proxy")
    return compute_thinkorswim_hacolt(
        opens,
        highs,
        lows,
        closes,
        tema_length=tema_length,
        ema_length=ema_length,
        candle_size_factor=candle_size_factor,
    ).points
