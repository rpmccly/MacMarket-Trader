"""ATR Trailing Stop indicator (deterministic, ThinkScript parity).

Mirrors the ThinkOrSwim "ATRTrailingStop" study:

    input trailType = {default modified, unmodified};
    input ATRPeriod = 9;            # MacMarket default (ToS default is 5)
    input ATRFactor = 2.9;          # MacMarket default (ToS default is 3.5)
    input firstTrade = {default long, short};
    input averageType = AverageType.WILDERS;

    def HiLo = Min(high - low, 1.5 * Average(high - low, ATRPeriod));
    def HRef = if low <= high[1] then high - close[1]
               else (high - close[1]) - 0.5 * (low - high[1]);
    def LRef = if high >= low[1] then close[1] - low
               else (close[1] - low) - 0.5 * (low[1] - high);
    def trueRange = (modified) Max(HiLo, Max(HRef, LRef)) | (unmodified) TrueRange(high, close, low);
    def loss = ATRFactor * MovingAverage(averageType, trueRange, ATRPeriod);
    # state machine init/long/short with trailing-stop and buy/sell flip signals.

This module is read-only and side-effect free. Once shipped, ATR math is frozen
(see hard constraint: do not change ATR indicator math after implementing).

Insufficient-bar handling: the moving averages are seeded from the first bar
(Wilders/EMA) or use an expanding window (the HiLo simple average) so every bar
yields a defined trailing stop. Latest-bar values converge to ThinkScript given
normal warmup; parity fixtures assert the latest bar within tolerance.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators.common import ema, true_range

TrailType = Literal["modified", "unmodified"]
AverageType = Literal["wilders", "simple", "exponential"]
FirstTrade = Literal["long", "short"]
AtrState = Literal["long", "short", "init"]

ATR_TRAIL_TYPES: frozenset[str] = frozenset({"modified", "unmodified"})
ATR_AVERAGE_TYPES: frozenset[str] = frozenset({"wilders", "simple", "exponential"})
ATR_FIRST_TRADES: frozenset[str] = frozenset({"long", "short"})


class AtrTrailingStopConfig(BaseModel):
    """ATR Trailing Stop inputs. Defaults match the MacMarket convention."""

    model_config = ConfigDict(extra="forbid")

    trail_type: TrailType = "modified"
    atr_period: int = 9
    atr_factor: float = 2.9
    first_trade: FirstTrade = "long"
    average_type: AverageType = "wilders"


class AtrTrailingStopPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    timestamp: str | None = None
    close: float
    state: AtrState
    trailing_stop: float
    true_range: float
    loss: float
    buy_signal: bool = False
    sell_signal: bool = False
    bars_since_flip: int | None = None
    last_flip_direction: Literal["long", "short"] | None = None
    last_flip_time: str | None = None
    stop_distance: float
    stop_distance_pct: float | None = None


class AtrTrailingStopSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: AtrTrailingStopConfig
    points: list[AtrTrailingStopPoint] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def latest(self) -> AtrTrailingStopPoint | None:
        return self.points[-1] if self.points else None


def normalize_config(raw: dict[str, object] | AtrTrailingStopConfig | None) -> AtrTrailingStopConfig:
    """Coerce arbitrary profile/request input into a valid config (defaults on bad input)."""
    if isinstance(raw, AtrTrailingStopConfig):
        return raw
    data = dict(raw or {})
    trail_type = str(data.get("trail_type") or "modified").strip().lower()
    if trail_type not in ATR_TRAIL_TYPES:
        trail_type = "modified"
    average_type = str(data.get("average_type") or "wilders").strip().lower()
    if average_type not in ATR_AVERAGE_TYPES:
        average_type = "wilders"
    first_trade = str(data.get("first_trade") or "long").strip().lower()
    if first_trade not in ATR_FIRST_TRADES:
        first_trade = "long"
    try:
        atr_period = int(data.get("atr_period") if data.get("atr_period") is not None else 9)
    except (TypeError, ValueError):
        atr_period = 9
    atr_period = max(1, min(atr_period, 200))
    try:
        atr_factor = float(data.get("atr_factor") if data.get("atr_factor") is not None else 2.9)
    except (TypeError, ValueError):
        atr_factor = 2.9
    if not (atr_factor > 0) or atr_factor > 100:
        atr_factor = 2.9
    return AtrTrailingStopConfig(
        trail_type=trail_type,  # type: ignore[arg-type]
        atr_period=atr_period,
        atr_factor=atr_factor,
        first_trade=first_trade,  # type: ignore[arg-type]
        average_type=average_type,  # type: ignore[arg-type]
    )


def _wilders(series: Sequence[float], period: int) -> list[float]:
    """Wilder's smoothing (RMA), seeded with the first value — matches ThinkScript WILDERS."""
    if not series:
        return []
    out = [float(series[0])]
    for i in range(1, len(series)):
        out.append((out[-1] * (period - 1) + float(series[i])) / period)
    return out


def _rolling_simple(values: Sequence[float], period: int) -> list[float]:
    """Simple MA with an expanding window before `period` bars (no NaN/None)."""
    out: list[float] = []
    running = 0.0
    for i, value in enumerate(values):
        running += float(value)
        if i >= period:
            running -= float(values[i - period])
        denom = min(i + 1, period)
        out.append(running / denom)
    return out


def _moving_average(average_type: str, series: Sequence[float], period: int) -> list[float]:
    if average_type == "simple":
        return _rolling_simple(series, period)
    if average_type == "exponential":
        return ema(series, period)
    return _wilders(series, period)


def _modified_true_range(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int
) -> list[float]:
    """ThinkScript 'modified' true range: Max(HiLo, HRef, LRef)."""
    n = len(highs)
    hl = [float(highs[i]) - float(lows[i]) for i in range(n)]
    hl_avg = _rolling_simple(hl, period)
    out: list[float] = []
    for i in range(n):
        if i == 0:
            out.append(max(0.0, hl[0]))
            continue
        high = float(highs[i])
        low = float(lows[i])
        prev_close = float(closes[i - 1])
        prev_high = float(highs[i - 1])
        prev_low = float(lows[i - 1])
        hilo = min(high - low, 1.5 * hl_avg[i])
        if low <= prev_high:
            href = high - prev_close
        else:
            href = (high - prev_close) - 0.5 * (low - prev_high)
        if high >= prev_low:
            lref = prev_close - low
        else:
            lref = (prev_close - low) - 0.5 * (prev_low - high)
        out.append(max(hilo, href, lref))
    return out


def compute_atr_trailing_stop(
    bars: Sequence[Bar],
    *,
    config: AtrTrailingStopConfig | dict[str, object] | None = None,
) -> AtrTrailingStopSeries:
    """Deterministic ATR Trailing Stop over a bar series (oldest→newest)."""
    cfg = normalize_config(config)
    series = AtrTrailingStopSeries(config=cfg)
    if not bars:
        series.notes.append("no_bars")
        return series

    highs = [float(b.high) for b in bars]
    lows = [float(b.low) for b in bars]
    closes = [float(b.close) for b in bars]

    if cfg.trail_type == "unmodified":
        tr = true_range(highs, lows, closes)
    else:
        tr = _modified_true_range(highs, lows, closes, cfg.atr_period)
    avg = _moving_average(cfg.average_type, tr, cfg.atr_period)
    loss_series = [cfg.atr_factor * value for value in avg]

    prev_state: AtrState | None = None
    prev_trail: float | None = None
    last_flip_index: int | None = None
    last_flip_direction: Literal["long", "short"] | None = None
    last_flip_time: str | None = None

    def _ts(bar: Bar) -> str | None:
        if getattr(bar, "timestamp", None) is not None:
            return bar.timestamp.isoformat()
        return bar.date.isoformat() if getattr(bar, "date", None) is not None else None

    for i, bar in enumerate(bars):
        close = closes[i]
        loss = loss_series[i]
        buy_signal = False
        sell_signal = False
        if prev_state is None or prev_state == "init":
            # Initialize on the first bar per first_trade.
            if cfg.first_trade == "long":
                state: AtrState = "long"
                trail = close - loss
            else:
                state = "short"
                trail = close + loss
            last_flip_index = i
            last_flip_direction = state  # type: ignore[assignment]
            last_flip_time = _ts(bar)
        elif prev_state == "long":
            if close > (prev_trail or close):
                state = "long"
                trail = max(prev_trail if prev_trail is not None else close - loss, close - loss)
            else:
                state = "short"
                trail = close + loss
                sell_signal = True
        else:  # prev_state == "short"
            if close < (prev_trail if prev_trail is not None else close):
                state = "short"
                trail = min(prev_trail if prev_trail is not None else close + loss, close + loss)
            else:
                state = "long"
                trail = close - loss
                buy_signal = True

        if buy_signal or sell_signal:
            last_flip_index = i
            last_flip_direction = state  # type: ignore[assignment]
            last_flip_time = _ts(bar)

        stop_distance = abs(close - trail)
        stop_distance_pct = (stop_distance / close * 100.0) if close else None
        series.points.append(
            AtrTrailingStopPoint(
                index=i,
                timestamp=_ts(bar),
                close=round(close, 6),
                state=state,
                trailing_stop=round(trail, 6),
                true_range=round(tr[i], 6),
                loss=round(loss, 6),
                buy_signal=buy_signal,
                sell_signal=sell_signal,
                bars_since_flip=(i - last_flip_index) if last_flip_index is not None else None,
                last_flip_direction=last_flip_direction,
                last_flip_time=last_flip_time,
                stop_distance=round(stop_distance, 6),
                stop_distance_pct=round(stop_distance_pct, 4) if stop_distance_pct is not None else None,
            )
        )
        prev_state = state
        prev_trail = trail

    return series
