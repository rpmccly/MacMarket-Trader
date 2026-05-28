"""MetaStock HACO parity implementation.

The active HACO calculation in MacMarket is the MetaStock formula captured in
the README/task charter for this pass. The older close-only EMA(3)/EMA(8)
proxy remains available only as ``legacy_haco_ema_3_8`` for historical tests or
diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from pydantic import BaseModel

from macmarket_trader.indicators.common import ema, tema


class HacoPoint(BaseModel):
    state: str
    state_value: int
    momentum: float
    flip: str | None = None


@dataclass(frozen=True)
class MetastockHacoDebug:
    ha_open: list[float]
    ha_c: list[float]
    zl_ha_up: list[float]
    zl_cl_up: list[float]
    zl_dif_up: list[float]
    utr: list[bool]
    zl_ha_down: list[float]
    zl_cl_down: list[float]
    zl_dif_down: list[float]
    dtr: list[bool]
    upw: list[bool]
    dnw: list[bool]
    result: list[int]


@dataclass(frozen=True)
class MetastockHacoResult:
    points: list[HacoPoint]
    debug: MetastockHacoDebug


def _validate_ohlc(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> tuple[list[float], list[float], list[float], list[float]]:
    if not (len(opens) == len(highs) == len(lows) == len(closes)):
        raise ValueError("OHLC arrays must be the same length")
    return [float(item) for item in opens], [float(item) for item in highs], [float(item) for item in lows], [float(item) for item in closes]


def metastock_alert(condition: Sequence[bool], lookback: int = 2) -> list[bool]:
    """MetaStock ``Alert(condition, 2)`` compatibility helper.

    This intentionally implements the confirmed interpretation for this pass:
    true when the condition is true on the current bar or previous bar.
    """
    if lookback <= 0:
        raise ValueError("lookback must be > 0")
    values = [bool(item) for item in condition]
    out: list[bool] = []
    for idx in range(len(values)):
        start = max(0, idx - lookback + 1)
        out.append(any(values[start : idx + 1]))
    return out


def _zero_lag_tema(series: Sequence[float], period: int) -> tuple[list[float], list[float], list[float]]:
    tma1 = tema(series, period)
    tma2 = tema(tma1, period)
    zero_lag = [first + (first - second) for first, second in zip(tma1, tma2, strict=True)]
    return tma1, tma2, zero_lag


def legacy_haco_ema_3_8(closes: Sequence[float]) -> list[HacoPoint]:
    """Legacy close-only HACO proxy kept explicitly out of the active path."""
    close_values = [float(item) for item in closes]
    if not close_values:
        return []

    fast = ema(close_values, period=3)
    slow = ema(close_values, period=8)
    momentum = [f - s for f, s in zip(fast, slow, strict=True)]

    out: list[HacoPoint] = []
    previous_state: str | None = None
    for value in momentum:
        state = "green" if value >= 0 else "red"
        state_value = 100 if state == "green" else 0
        flip: str | None = None
        if previous_state and previous_state != state:
            flip = "buy" if state == "green" else "sell"
        out.append(HacoPoint(state=state, state_value=state_value, momentum=value, flip=flip))
        previous_state = state
    return out


def compute_metastock_haco(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    avg: int = 34,
    avgdn: int = 34,
) -> MetastockHacoResult:
    """Compute active HACO state from the confirmed MetaStock formula."""
    if avg <= 0 or avgdn <= 0:
        raise ValueError("avg and avgdn must be > 0")
    open_values, high_values, low_values, close_values = _validate_ohlc(opens, highs, lows, closes)
    if not open_values:
        debug = MetastockHacoDebug([], [], [], [], [], [], [], [], [], [], [], [], [])
        return MetastockHacoResult(points=[], debug=debug)

    ohlc4 = [(o + h + l + c) / 4.0 for o, h, l, c in zip(open_values, high_values, low_values, close_values, strict=True)]
    ha_open = [ohlc4[0]]
    for idx in range(1, len(ohlc4)):
        ha_open.append((ohlc4[idx - 1] + ha_open[idx - 1]) / 2.0)
    ha_c = [
        (typical + ha_o + max(high, ha_o) + min(low, ha_o)) / 4.0
        for typical, ha_o, high, low in zip(ohlc4, ha_open, high_values, low_values, strict=True)
    ]
    hl2 = [(high + low) / 2.0 for high, low in zip(high_values, low_values, strict=True)]

    _up_tma1, _up_tma2, zl_ha_up = _zero_lag_tema(ha_c, avg)
    _up_cl_tma1, _up_cl_tma2, zl_cl_up = _zero_lag_tema(hl2, avg)
    zl_dif_up = [zl_cl - zl_ha for zl_cl, zl_ha in zip(zl_cl_up, zl_ha_up, strict=True)]

    _down_tma1, _down_tma2, zl_ha_down = _zero_lag_tema(ha_c, avgdn)
    _down_cl_tma1, _down_cl_tma2, zl_cl_down = _zero_lag_tema(hl2, avgdn)
    zl_dif_down = [zl_cl - zl_ha for zl_cl, zl_ha in zip(zl_cl_down, zl_ha_down, strict=True)]

    up_alert = metastock_alert([ha_close >= ha_o for ha_close, ha_o in zip(ha_c, ha_open, strict=True)], 2)
    down_alert = metastock_alert([ha_close < ha_o for ha_close, ha_o in zip(ha_c, ha_open, strict=True)], 2)

    up_keeping: list[bool] = []
    up_keepall: list[bool] = []
    utr: list[bool] = []
    down_keeping: list[bool] = []
    down_keepall: list[bool] = []
    dtr: list[bool] = []

    for idx, (o, h, l, c) in enumerate(zip(open_values, high_values, low_values, close_values, strict=True)):
        has_prev = idx > 0
        prev_h = high_values[idx - 1] if has_prev else h
        prev_l = low_values[idx - 1] if has_prev else l
        prev_c = close_values[idx - 1] if has_prev else c

        up_keep1 = up_alert[idx] or c >= ha_c[idx] or (has_prev and (h > prev_h or l > prev_l))
        up_keep2 = zl_dif_up[idx] >= 0
        up_keeping.append(up_keep1 or up_keep2)
        prev_up_keeping = up_keeping[idx - 1] if has_prev else False
        # Preserve MetaStock precedence: A OR (B AND C OR D) is
        # A OR ((B AND C) OR D), not A OR (B AND (C OR D)).
        up_keepall.append(up_keeping[idx] or ((prev_up_keeping and c >= o) or (has_prev and c >= prev_c)))
        up_keep3 = abs(c - o) < (h - l) * 0.35 and has_prev and h >= prev_l
        prev_up_keepall = up_keepall[idx - 1] if has_prev else False
        utr.append(up_keepall[idx] or (prev_up_keepall and up_keep3))

        down_keep1 = down_alert[idx]
        down_keep2 = zl_dif_down[idx] < 0
        down_keeping.append(down_keep1 or down_keep2)
        prev_down_keeping = down_keeping[idx - 1] if has_prev else False
        down_keepall.append(down_keeping[idx] or ((prev_down_keeping and c < o) or (has_prev and c < prev_c)))
        down_keep3 = abs(c - o) < (h - l) * 0.35 and has_prev and l <= prev_h
        prev_down_keepall = down_keepall[idx - 1] if has_prev else False
        dtr.append(down_keepall[idx] or (prev_down_keepall and down_keep3))

    upw: list[bool] = []
    dnw: list[bool] = []
    result: list[int] = []
    for idx in range(len(open_values)):
        has_prev = idx > 0
        prev_dtr = dtr[idx - 1] if has_prev else False
        prev_utr = utr[idx - 1] if has_prev else False
        upw_value = (not dtr[idx]) and prev_dtr and utr[idx]
        dnw_value = (not utr[idx]) and prev_utr and dtr[idx]
        upw.append(upw_value)
        dnw.append(dnw_value)
        if upw_value:
            result.append(1)
        elif dnw_value:
            result.append(0)
        elif has_prev:
            result.append(result[idx - 1])
        else:
            result.append(1 if ha_c[idx] >= ha_open[idx] else 0)

    points: list[HacoPoint] = []
    previous_state: str | None = None
    for value, momentum in zip(result, zl_dif_up, strict=True):
        state = "green" if value == 1 else "red"
        flip: str | None = None
        if previous_state is not None and previous_state != state:
            flip = "buy" if state == "green" else "sell"
        points.append(HacoPoint(state=state, state_value=100 if state == "green" else 0, momentum=momentum, flip=flip))
        previous_state = state

    debug = MetastockHacoDebug(
        ha_open=ha_open,
        ha_c=ha_c,
        zl_ha_up=zl_ha_up,
        zl_cl_up=zl_cl_up,
        zl_dif_up=zl_dif_up,
        utr=utr,
        zl_ha_down=zl_ha_down,
        zl_cl_down=zl_cl_down,
        zl_dif_down=zl_dif_down,
        dtr=dtr,
        upw=upw,
        dnw=dnw,
        result=result,
    )
    return MetastockHacoResult(points=points, debug=debug)


def compute_haco_states(
    opens: Sequence[float],
    highs: Sequence[float] | None = None,
    lows: Sequence[float] | None = None,
    closes: Sequence[float] | None = None,
    *,
    avg: int = 34,
    avgdn: int = 34,
) -> list[HacoPoint]:
    """Return active MetaStock HACO points.

    This function now requires full OHLC arrays. Use
    ``legacy_haco_ema_3_8`` for the retired close-only proxy.
    """
    if highs is None or lows is None or closes is None:
        raise ValueError("compute_haco_states requires OHLC arrays; use legacy_haco_ema_3_8 for the old close-only proxy")
    return compute_metastock_haco(opens, highs, lows, closes, avg=avg, avgdn=avgdn).points
