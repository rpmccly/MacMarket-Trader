"""True Momentum oscillator (deterministic Python port).

Source: ST_TrueMomentumSTUDY.ts (licensed/proprietary reference). Math/state
logic is ported here as deterministic Python; production use of this module
assumes the operator has the rights to use/port the source study.
"""

from __future__ import annotations

from datetime import date as date_cls
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators.common import crosses_above, crosses_below, ema, safe_div

Timeframe = Literal["1D", "4H", "1H"]
HigherTimeframeSource = Literal[
    "provided_higher_timeframe_bars",
    "derived_from_chart_bars",
    "insufficient_data",
]
ParityStatus = Literal[
    "pending_thinkorswim_fixture_validation",
    "validated_against_thinkorswim_fixture",
]


class TrueMomentumConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeframe: Timeframe = "1D"
    higher_timeframe_label: str = "weekly"
    L1: int = 21
    L2: int = 21


def config_for_timeframe(timeframe: Timeframe) -> TrueMomentumConfig:
    if timeframe == "1D":
        return TrueMomentumConfig(timeframe="1D", higher_timeframe_label="weekly", L1=21, L2=21)
    if timeframe == "4H":
        return TrueMomentumConfig(timeframe="4H", higher_timeframe_label="three_day", L1=30, L2=35)
    if timeframe == "1H":
        return TrueMomentumConfig(timeframe="1H", higher_timeframe_label="daily", L1=30, L2=21)
    raise ValueError(f"unsupported timeframe: {timeframe}")


class TrueMomentumPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    true_momentum: float
    true_momentum_ema: float
    cross_up: bool = False
    cross_down: bool = False
    strong_bull: bool = False
    strong_bear: bool = False
    confirmed_bull: bool = False
    confirmed_bear: bool = False
    trend_direction: int = 0
    new_bull_signal: bool = False
    new_bear_signal: bool = False


class TrueMomentumSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeframe: Timeframe
    config: TrueMomentumConfig
    higher_timeframe_source: HigherTimeframeSource
    higher_timeframe_label: str
    parity_status: ParityStatus = "pending_thinkorswim_fixture_validation"
    points: list[TrueMomentumPoint] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _iso_week_key(d: date_cls) -> tuple[int, int]:
    iso = d.isocalendar()
    return iso[0], iso[1]


def _three_session_key(d: date_cls, anchor: date_cls) -> int:
    return (d - anchor).days // 3


def _hour_to_daily(bars: Sequence[Bar]) -> list[float]:
    by_day: dict[date_cls, float] = {}
    for bar in bars:
        by_day[bar.date] = bar.close  # last close per date wins
    return [by_day[d] for d in sorted(by_day)]


def _hour4_to_three_day(bars: Sequence[Bar]) -> list[float]:
    if not bars:
        return []
    sorted_bars = sorted(bars, key=lambda b: (b.timestamp or b.date, b.date))
    anchor = sorted_bars[0].date
    by_bucket: dict[int, float] = {}
    for bar in sorted_bars:
        bucket = _three_session_key(bar.date, anchor)
        by_bucket[bucket] = bar.close
    return [by_bucket[k] for k in sorted(by_bucket)]


def _daily_to_weekly(bars: Sequence[Bar]) -> list[float]:
    by_week: dict[tuple[int, int], float] = {}
    for bar in sorted(bars, key=lambda b: b.date):
        by_week[_iso_week_key(bar.date)] = bar.close
    return [by_week[k] for k in sorted(by_week)]


def _derive_higher_closes(bars: Sequence[Bar], timeframe: Timeframe) -> list[float]:
    if timeframe == "1D":
        return _daily_to_weekly(bars)
    if timeframe == "4H":
        return _hour4_to_three_day(bars)
    return _hour_to_daily(bars)


def _bar_to_higher_index(bars: Sequence[Bar], timeframe: Timeframe) -> list[int]:
    """Project each chart bar to the index of its higher-timeframe bucket."""
    if timeframe == "1D":
        keys = sorted({_iso_week_key(b.date) for b in bars})
        index_by_key = {k: i for i, k in enumerate(keys)}
        return [index_by_key[_iso_week_key(b.date)] for b in bars]
    if timeframe == "4H":
        sorted_bars = sorted(bars, key=lambda b: (b.timestamp or b.date, b.date))
        anchor = sorted_bars[0].date if sorted_bars else None
        if anchor is None:
            return []
        keys = sorted({_three_session_key(b.date, anchor) for b in bars})
        index_by_key = {k: i for i, k in enumerate(keys)}
        return [index_by_key[_three_session_key(b.date, anchor)] for b in bars]
    keys = sorted({b.date for b in bars})
    index_by_key = {k: i for i, k in enumerate(keys)}
    return [index_by_key[b.date] for b in bars]


def compute_true_momentum(
    bars: Sequence[Bar],
    *,
    timeframe: Timeframe = "1D",
    higher_timeframe_bars: Sequence[Bar] | None = None,
    parity_validated: bool = False,
) -> TrueMomentumSeries:
    config = config_for_timeframe(timeframe)
    bars_list = list(bars)
    notes: list[str] = []

    if not bars_list:
        return TrueMomentumSeries(
            timeframe=timeframe,
            config=config,
            higher_timeframe_source="insufficient_data",
            higher_timeframe_label=config.higher_timeframe_label,
            parity_status=("validated_against_thinkorswim_fixture" if parity_validated else "pending_thinkorswim_fixture_validation"),
            points=[],
            notes=["no chart bars provided"],
        )

    sorted_bars = sorted(bars_list, key=lambda b: (b.timestamp or b.date, b.date))

    htf_source: HigherTimeframeSource
    higher_closes: list[float]
    if higher_timeframe_bars:
        htf_source = "provided_higher_timeframe_bars"
        higher_closes = [b.close for b in sorted(higher_timeframe_bars, key=lambda b: (b.timestamp or b.date, b.date))]
        # Map each chart bar to the most recent higher-bar index <= its date.
        htf_dates = [b.date for b in sorted(higher_timeframe_bars, key=lambda b: (b.timestamp or b.date, b.date))]
        index_for_bar: list[int] = []
        for bar in sorted_bars:
            best = -1
            for i, hd in enumerate(htf_dates):
                if hd <= bar.date:
                    best = i
                else:
                    break
            index_for_bar.append(max(0, best))
    else:
        htf_source = "derived_from_chart_bars"
        higher_closes = _derive_higher_closes(sorted_bars, timeframe)
        index_for_bar = _bar_to_higher_index(sorted_bars, timeframe)
        notes.append(
            "higher-timeframe close series derived from chart bars; not exact Thinkorswim secondary aggregation"
        )

    if len(higher_closes) < 2:
        return TrueMomentumSeries(
            timeframe=timeframe,
            config=config,
            higher_timeframe_source="insufficient_data",
            higher_timeframe_label=config.higher_timeframe_label,
            parity_status=("validated_against_thinkorswim_fixture" if parity_validated else "pending_thinkorswim_fixture_validation"),
            points=[
                TrueMomentumPoint(index=i, true_momentum=50.0, true_momentum_ema=50.0)
                for i, _ in enumerate(sorted_bars)
            ],
            notes=notes + ["insufficient higher-timeframe closes for delta computation; emitted neutral series"],
        )

    deltas = [0.0] + [higher_closes[i] - higher_closes[i - 1] for i in range(1, len(higher_closes))]
    abs_deltas = [abs(d) for d in deltas]
    a1 = ema(deltas, config.L1)
    a2 = ema(abs_deltas, config.L1)
    a3 = [safe_div(a1[i], a2[i], default=0.0) if a2[i] > 0 else 0.0 for i in range(len(a1))]
    htf_true_momentum = [50.0 * (val + 1.0) for val in a3]
    htf_ema = ema(htf_true_momentum, config.L2)

    # Project HTF series back to chart bar indices.
    true_momentum = [htf_true_momentum[idx] for idx in index_for_bar]
    true_momentum_ema = [htf_ema[idx] for idx in index_for_bar]

    cross_up = crosses_above(true_momentum, true_momentum_ema)
    cross_down = crosses_below(true_momentum, true_momentum_ema)

    points: list[TrueMomentumPoint] = []
    trend_direction = 0
    start_bar = max(config.L1, config.L2) + 25
    for i in range(len(sorted_bars)):
        cu = cross_up[i]
        cd = cross_down[i]
        delta = true_momentum[i] - true_momentum_ema[i]
        strong_bull = cu and delta >= 9.0
        strong_bear = cd and -delta >= 9.0
        prev_cu = cross_up[i - 1] if i > 0 else False
        prev_cd = cross_down[i - 1] if i > 0 else False
        confirmed_bull = prev_cu and true_momentum[i] > true_momentum_ema[i]
        confirmed_bear = prev_cd and true_momentum[i] < true_momentum_ema[i]
        final_bull = strong_bull or confirmed_bull
        final_bear = strong_bear or confirmed_bear

        previous_dir = trend_direction
        if i < start_bar:
            trend_direction = 0
        elif final_bull:
            trend_direction = 1
        elif final_bear:
            trend_direction = -1
        elif previous_dir != 0:
            trend_direction = previous_dir
        else:
            trend_direction = 1 if true_momentum[i] > true_momentum_ema[i] else -1

        new_bull = bool(final_bull and previous_dir != 1 and i >= start_bar)
        new_bear = bool(final_bear and previous_dir != -1 and i >= start_bar)

        points.append(
            TrueMomentumPoint(
                index=i,
                true_momentum=true_momentum[i],
                true_momentum_ema=true_momentum_ema[i],
                cross_up=bool(cu),
                cross_down=bool(cd),
                strong_bull=bool(strong_bull),
                strong_bear=bool(strong_bear),
                confirmed_bull=bool(confirmed_bull),
                confirmed_bear=bool(confirmed_bear),
                trend_direction=trend_direction,
                new_bull_signal=new_bull,
                new_bear_signal=new_bear,
            )
        )

    return TrueMomentumSeries(
        timeframe=timeframe,
        config=config,
        higher_timeframe_source=htf_source,
        higher_timeframe_label=config.higher_timeframe_label,
        parity_status=("validated_against_thinkorswim_fixture" if parity_validated else "pending_thinkorswim_fixture_validation"),
        points=points,
        notes=notes,
    )


__all__ = [
    "TrueMomentumConfig",
    "TrueMomentumPoint",
    "TrueMomentumSeries",
    "compute_true_momentum",
    "config_for_timeframe",
]
