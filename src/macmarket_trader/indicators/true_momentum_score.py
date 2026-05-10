"""Composite True Momentum Score (deterministic Python port).

Source: ST_TrueMomentumScoreSTUDY.ts (licensed/proprietary reference). Math
and signal logic are ported here as deterministic Python; production use of
this module assumes the operator has the rights to use/port the source study.
"""

from __future__ import annotations

from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators.common import atr, ema, sma
from macmarket_trader.indicators.hilo_elite import HiLoEliteSeries, compute_hilo_elite
from macmarket_trader.indicators.true_momentum import (
    TrueMomentumSeries,
    compute_true_momentum,
)

Timeframe = Literal["1D", "4H", "1H"]
ScoreState = Literal[
    "max_bull",
    "bull",
    "neutral_up",
    "neutral",
    "neutral_down",
    "bear",
    "max_bear",
]
AtrStopMode = Literal["deterministic_ema_trailing_stop_approximation"]


class MomentumScoreComponentBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    true_momentum_score: int
    hilo_thrust: int
    bull_ma: int
    bear_ma: int
    atr_value: int
    macd_bias: int
    intraday_penalty: int
    base_score: int


class MomentumScorePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    total_score: int
    total_label: str
    total_state: ScoreState
    trend_score: float
    momo_score: float
    component_breakdown: MomentumScoreComponentBreakdown
    true_momentum: float
    true_momentum_ema: float
    hilo_slow_d: float
    hilo_slow_d_x: float
    hilo_thrust: int
    macd_histogram: float
    atr_value_signed: int
    bull_count: int
    bear_count: int
    has_enough_bars_for_200: bool
    max_bull_pullback: bool = False
    bull_pullback: bool = False
    max_bear_rally: bool = False
    bear_rally: bool = False
    new_max_bull_pullback: bool = False
    new_bull_pullback: bool = False
    new_max_bear_rally: bool = False
    new_bear_rally: bool = False
    from_max_bull_to_weak: bool = False
    from_bull_to_weak: bool = False
    from_max_bear_to_weak: bool = False
    from_bear_to_weak: bool = False
    neutral_up_to_bull: bool = False
    neutral_dn_to_bear: bool = False


class MomentumScoreSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeframe: Timeframe
    points: list[MomentumScorePoint] = Field(default_factory=list)
    atr_stop_mode: AtrStopMode = "deterministic_ema_trailing_stop_approximation"
    notes: list[str] = Field(default_factory=list)


_LABEL_BY_STATE: dict[ScoreState, str] = {
    "max_bull": "Max Bull",
    "bull": "Bull",
    "neutral_up": "Neutral Up",
    "neutral": "Neutral",
    "neutral_down": "Neutral Down",
    "bear": "Bear",
    "max_bear": "Max Bear",
}


def _classify(total_score: int) -> ScoreState:
    if total_score >= 100:
        return "max_bull"
    if total_score >= 75:
        return "bull"
    if total_score >= 45:
        return "neutral_up"
    if total_score <= -100:
        return "max_bear"
    if total_score <= -75:
        return "bear"
    if total_score <= -45:
        return "neutral_down"
    return "neutral"


def _atr_trailing_stop(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    period: int = 10,
    multiplier: float = 3.1,
) -> list[float]:
    """Deterministic EMA-based trailing stop approximation.

    Not an exact reproduction of Thinkorswim ATRTrailingStop with "modified"
    trail type. Documented here as
    ``deterministic_ema_trailing_stop_approximation``.
    """
    if not closes:
        return []
    a = atr(highs, lows, closes, period)
    out: list[float] = []
    long_band = closes[0] - a[0] * multiplier
    state: int = 1
    stop = long_band
    out.append(stop)
    for i in range(1, len(closes)):
        long_band = closes[i] - a[i] * multiplier
        short_band = closes[i] + a[i] * multiplier
        if state == 1:
            if closes[i] < stop:
                state = -1
                stop = short_band
            else:
                stop = max(stop, long_band)
        else:
            if closes[i] > stop:
                state = 1
                stop = long_band
            else:
                stop = min(stop, short_band)
        out.append(stop)
    return out


def _macd_histogram(closes: Sequence[float]) -> list[float]:
    fast = ema(list(closes), 55)
    slow = ema(list(closes), 75)
    macd_line = [f - s for f, s in zip(fast, slow, strict=True)]
    signal = ema(macd_line, 55)
    return [m - s for m, s in zip(macd_line, signal, strict=True)]


def _bull_count_score(bull_count: int, has_200: bool) -> int:
    if not has_200:
        if bull_count >= 7:
            return 35
        if bull_count >= 5:
            return 25
        if bull_count >= 3:
            return 10
        return 0
    if bull_count == 10:
        return 35
    if bull_count >= 7:
        return 30
    if bull_count >= 5:
        return 20
    if bull_count >= 3:
        return 10
    if bull_count >= 1:
        return 5
    return 0


def _bear_count_score(bear_count: int, has_200: bool) -> int:
    if not has_200:
        if bear_count >= 7:
            return -35
        if bear_count >= 5:
            return -25
        if bear_count >= 3:
            return -10
        return 0
    if bear_count == 10:
        return -35
    if bear_count >= 7:
        return -30
    if bear_count >= 5:
        return -20
    if bear_count >= 3:
        return -10
    if bear_count >= 1:
        return -5
    return 0


def _to_x_score(true_momentum: float, true_momentum_ema: float) -> int:
    """Port of the TO_X composite score sub-script (caps at +/-45)."""
    delta = true_momentum - true_momentum_ema
    abs_delta = abs(delta)

    bullish_override = delta >= 10.0
    bearish_override = delta <= -10.0
    extreme_bull = true_momentum >= 65.0 and true_momentum_ema >= 65.0
    extreme_bear = true_momentum <= 35.0 and true_momentum_ema <= 35.0
    delta_bull = true_momentum >= 60.0 and true_momentum_ema >= 60.0
    delta_bear = true_momentum <= 40.0 and true_momentum_ema <= 40.0

    if abs_delta >= 1.4:
        to_a = 15 if true_momentum > true_momentum_ema else -15
    elif extreme_bull and true_momentum > true_momentum_ema and abs_delta >= 0.1:
        to_a = 15
    elif extreme_bear and true_momentum < true_momentum_ema and abs_delta >= 0.1:
        to_a = -15
    elif delta_bull and true_momentum > true_momentum_ema and abs_delta >= 0.8:
        to_a = 15
    elif delta_bear and true_momentum < true_momentum_ema and abs_delta >= 0.8:
        to_a = -15
    else:
        to_a = 0

    if extreme_bull and abs_delta >= 0.1 and true_momentum > true_momentum_ema:
        pos_bias = 20
    elif extreme_bear and abs_delta >= 0.1 and true_momentum < true_momentum_ema:
        pos_bias = -20
    elif delta_bull and abs_delta >= 2.5 and true_momentum > true_momentum_ema:
        pos_bias = 20
    elif delta_bear and abs_delta >= 2.5 and true_momentum < true_momentum_ema:
        pos_bias = -20
    elif true_momentum >= 55.0 and true_momentum_ema >= 55.0 and abs_delta >= 3.0 and true_momentum > true_momentum_ema:
        pos_bias = 20
    elif true_momentum >= 51.0 and true_momentum_ema >= 51.0 and abs_delta >= 3.5 and true_momentum > true_momentum_ema:
        pos_bias = 20
    elif true_momentum <= 50.0 and true_momentum_ema <= 49.9 and abs_delta >= 1.4 and true_momentum < true_momentum_ema:
        pos_bias = -20
    elif true_momentum >= 50.0 and true_momentum_ema >= 50.0 and abs_delta >= 3.0 and true_momentum > true_momentum_ema:
        pos_bias = 10
    elif true_momentum <= 50.0 and true_momentum_ema <= 49.9 and abs_delta >= 1.0 and true_momentum < true_momentum_ema:
        pos_bias = -10
    else:
        pos_bias = 0

    override_bias = 10 if bullish_override else (-10 if bearish_override else 0)
    if override_bias != 0 and (pos_bias == 0 or _sign(override_bias) != _sign(pos_bias)):
        to_b = override_bias
    else:
        to_b = pos_bias

    if abs_delta >= 3.4:
        if true_momentum >= 50.5 and true_momentum_ema <= 50.0:
            to_c = 10
        elif true_momentum <= 49.5 and true_momentum_ema >= 50.0:
            to_c = -10
        else:
            to_c = 0
    else:
        to_c = 0

    return to_a + to_b + to_c


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def compute_true_momentum_score(
    bars: Sequence[Bar],
    *,
    timeframe: Timeframe = "1D",
    higher_timeframe_bars: Sequence[Bar] | None = None,
    true_momentum_series: TrueMomentumSeries | None = None,
    hilo_series: HiLoEliteSeries | None = None,
) -> MomentumScoreSeries:
    bars_list = sorted(list(bars), key=lambda b: (b.timestamp or b.date, b.date))
    if not bars_list:
        return MomentumScoreSeries(timeframe=timeframe, points=[], notes=["no chart bars provided"])

    closes = [b.close for b in bars_list]
    highs = [b.high for b in bars_list]
    lows = [b.low for b in bars_list]

    ema10 = ema(closes, 10)
    ema20 = ema(closes, 20)
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200)

    macd_hist = _macd_histogram(closes)
    atr_stop = _atr_trailing_stop(highs, lows, closes, period=10, multiplier=3.1)
    atr14 = atr(highs, lows, closes, 14)

    if true_momentum_series is None:
        true_momentum_series = compute_true_momentum(
            bars_list, timeframe=timeframe, higher_timeframe_bars=higher_timeframe_bars
        )
    if hilo_series is None:
        hilo_series = compute_hilo_elite(bars_list, timeframe=timeframe)

    if len(true_momentum_series.points) != len(bars_list):
        raise ValueError("true_momentum_series length must match bar count")
    if len(hilo_series.points) != len(bars_list):
        raise ValueError("hilo_series length must match bar count")

    is_intraday = timeframe in ("4H", "1H")

    points: list[MomentumScorePoint] = []
    prev_total_score: int | None = None
    prev_max_bull_pb = False
    prev_bull_pb = False
    prev_max_bear_rally = False
    prev_bear_rally = False

    for i, _bar in enumerate(bars_list):
        e10 = ema10[i]
        e20 = ema20[i]
        s50 = sma50[i]
        s200 = sma200[i]
        has_200 = s200 is not None

        bull1 = e10 > e20
        bull2 = s50 is not None and e10 > s50
        bull3 = s50 is not None and e20 > s50
        bull4 = bool(s50 is not None and s200 is not None and s50 > s200)
        bull_count = (2 if bull1 else 0) + (3 if bull2 else 0) + (3 if bull3 else 0) + (2 if bull4 else 0)

        bear1 = e20 > e10
        bear2 = s50 is not None and s50 > e10
        bear3 = s50 is not None and s50 > e20
        bear4 = bool(s50 is not None and s200 is not None and s200 > s50)
        bear_count = (2 if bear1 else 0) + (3 if bear2 else 0) + (3 if bear3 else 0) + (2 if bear4 else 0)

        bull_ma = _bull_count_score(bull_count, has_200)
        bear_ma = _bear_count_score(bear_count, has_200)

        atr_value = 5 if closes[i] > atr_stop[i] else -5
        macd_bias = 5 if macd_hist[i] > 0 else (-5 if macd_hist[i] < 0 else 0)

        tm_point = true_momentum_series.points[i]
        hilo_point = hilo_series.points[i]
        true_momentum_score = _to_x_score(tm_point.true_momentum, tm_point.true_momentum_ema)
        hilo_thrust_score = hilo_point.hlp_output

        base_score = (
            true_momentum_score + hilo_thrust_score + bull_ma + bear_ma + atr_value + macd_bias
        )
        penalty_condition = (
            is_intraday
            and has_200
            and s200 is not None
            and closes[i] < s200
            and base_score >= -95
            and base_score <= 100
        )
        intraday_penalty = -5 if penalty_condition else 0
        total_score = base_score + intraday_penalty

        true_trend = (bull_ma + bear_ma + atr_value) * 100.0 / 40.0
        trend_score = true_trend - 5.0 if penalty_condition else true_trend
        momo_score = (true_momentum_score + hilo_thrust_score + macd_bias) * 100.0 / 60.0

        atr_now = atr14[i] if i < len(atr14) else 0.0
        near10_bull = abs(lows[i] - e10) <= atr_now * 0.33
        near20_bull = abs(lows[i] - e20) <= atr_now * 0.45
        near10_bear = abs(highs[i] - e10) <= atr_now * 0.33
        near20_bear = abs(highs[i] - e20) <= atr_now * 0.45

        max_bull_pb = total_score >= 95 and near10_bull
        bull_pb = total_score >= 75 and total_score < 100 and near20_bull
        max_bear_rally = total_score <= -95 and near10_bear
        bear_rally = total_score <= -75 and total_score > -100 and near20_bear

        new_max_bull_pb = bool(max_bull_pb and not prev_max_bull_pb)
        new_bull_pb = bool(bull_pb and not prev_bull_pb)
        new_max_bear_rally = bool(max_bear_rally and not prev_max_bear_rally)
        new_bear_rally = bool(bear_rally and not prev_bear_rally)

        from_max_bull_to_weak = bool(prev_total_score is not None and prev_total_score >= 95 and total_score <= 65)
        from_bull_to_weak = bool(
            prev_total_score is not None and prev_total_score >= 75 and prev_total_score < 95 and total_score <= 55
        )
        from_max_bear_to_weak = bool(prev_total_score is not None and prev_total_score <= -95 and total_score >= -65)
        from_bear_to_weak = bool(
            prev_total_score is not None and prev_total_score <= -75 and prev_total_score > -95 and total_score >= -55
        )
        neutral_up_to_bull = bool(prev_total_score is not None and prev_total_score <= 45 and total_score >= 75)
        neutral_dn_to_bear = bool(prev_total_score is not None and prev_total_score >= -35 and total_score <= -80)

        state = _classify(total_score)

        points.append(
            MomentumScorePoint(
                index=i,
                total_score=total_score,
                total_label=_LABEL_BY_STATE[state],
                total_state=state,
                trend_score=trend_score,
                momo_score=momo_score,
                component_breakdown=MomentumScoreComponentBreakdown(
                    true_momentum_score=true_momentum_score,
                    hilo_thrust=hilo_thrust_score,
                    bull_ma=bull_ma,
                    bear_ma=bear_ma,
                    atr_value=atr_value,
                    macd_bias=macd_bias,
                    intraday_penalty=intraday_penalty,
                    base_score=base_score,
                ),
                true_momentum=tm_point.true_momentum,
                true_momentum_ema=tm_point.true_momentum_ema,
                hilo_slow_d=hilo_point.slow_d,
                hilo_slow_d_x=hilo_point.slow_d_x,
                hilo_thrust=hilo_point.thrust,
                macd_histogram=macd_hist[i],
                atr_value_signed=atr_value,
                bull_count=bull_count,
                bear_count=bear_count,
                has_enough_bars_for_200=bool(has_200),
                max_bull_pullback=bool(max_bull_pb),
                bull_pullback=bool(bull_pb),
                max_bear_rally=bool(max_bear_rally),
                bear_rally=bool(bear_rally),
                new_max_bull_pullback=new_max_bull_pb,
                new_bull_pullback=new_bull_pb,
                new_max_bear_rally=new_max_bear_rally,
                new_bear_rally=new_bear_rally,
                from_max_bull_to_weak=from_max_bull_to_weak,
                from_bull_to_weak=from_bull_to_weak,
                from_max_bear_to_weak=from_max_bear_to_weak,
                from_bear_to_weak=from_bear_to_weak,
                neutral_up_to_bull=neutral_up_to_bull,
                neutral_dn_to_bear=neutral_dn_to_bear,
            )
        )

        prev_total_score = total_score
        prev_max_bull_pb = bool(max_bull_pb)
        prev_bull_pb = bool(bull_pb)
        prev_max_bear_rally = bool(max_bear_rally)
        prev_bear_rally = bool(bear_rally)

    return MomentumScoreSeries(timeframe=timeframe, points=points, notes=[])


__all__ = [
    "MomentumScoreComponentBreakdown",
    "MomentumScorePoint",
    "MomentumScoreSeries",
    "compute_true_momentum_score",
]
