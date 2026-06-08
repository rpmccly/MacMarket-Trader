"""Deterministic ATR Trailing Stop chart / intel payload builder (research-only).

Mirrors :class:`HacoChartService`: builds a price + trailing-stop series for one
primary timeframe plus a multi-timeframe state table, by reading the frozen ATR
Trailing Stop engine. Pure / side-effect free — bar resolution lives in the route.
"""

from __future__ import annotations

from datetime import UTC, datetime

from macmarket_trader.domain.schemas import (
    AtrChartConfigEcho,
    AtrChartExplanation,
    AtrChartPayload,
    AtrTimeframeState,
    AtrTrailingStopChartPoint,
    Bar,
    ChartCandle,
    HacoMarker,
)
from macmarket_trader.domain.timeframes import is_intraday_chart_timeframe
from macmarket_trader.indicators.atr_trailing_stop import compute_atr_trailing_stop, normalize_config

_DIRECTIONAL = {"long", "short"}


class AtrChartService:
    @staticmethod
    def _canonical_bars(bars: list[Bar]) -> list[Bar]:
        return sorted(
            bars,
            key=lambda bar: bar.timestamp or datetime.combine(bar.date, datetime.min.time(), tzinfo=UTC),
        )

    @staticmethod
    def _chart_time(bar: Bar, timeframe: str) -> str | int:
        if is_intraday_chart_timeframe(timeframe) and bar.timestamp is not None:
            return int(bar.timestamp.astimezone(UTC).timestamp())
        return bar.date.isoformat()

    @classmethod
    def _dedupe(cls, bars: list[Bar], timeframe: str) -> list[Bar]:
        if not is_intraday_chart_timeframe(timeframe):
            return bars
        by_time: dict[str | int, Bar] = {}
        for bar in bars:
            by_time[cls._chart_time(bar, timeframe)] = bar
        return list(by_time.values())

    def build_payload(
        self,
        *,
        symbol: str,
        timeframe: str,
        bars: list[Bar],
        config: dict[str, object] | None = None,
        timeframe_bars: dict[str, tuple[list[Bar], str, bool]] | None = None,
        include_markers: bool = True,
        data_source: str = "request_bars",
        fallback_mode: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> AtrChartPayload:
        cfg = normalize_config(config)
        config_echo = AtrChartConfigEcho(
            trail_type=cfg.trail_type,
            atr_period=cfg.atr_period,
            atr_factor=cfg.atr_factor,
            first_trade=cfg.first_trade,
            average_type=cfg.average_type,
        )
        metadata = metadata or {}
        canonical = self._dedupe(self._canonical_bars(list(bars)), timeframe)
        notes: list[str] = []
        candles: list[ChartCandle] = []
        trailing_stop: list[AtrTrailingStopChartPoint] = []
        markers: list[HacoMarker] = []
        explanation = AtrChartExplanation(current_state="neutral")

        if not canonical:
            notes.append("no_bars")
        else:
            chart_times = [self._chart_time(bar, timeframe) for bar in canonical]
            candles = [
                ChartCandle(index=idx, time=chart_times[idx], open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume)
                for idx, bar in enumerate(canonical)
            ]
            series = compute_atr_trailing_stop(canonical, config=cfg)
            for idx, (bar, point) in enumerate(zip(canonical, series.points, strict=True)):
                trailing_stop.append(
                    AtrTrailingStopChartPoint(
                        index=idx,
                        time=chart_times[idx],
                        close=point.close,
                        state=point.state,
                        trailing_stop=point.trailing_stop,
                        stop_distance=point.stop_distance,
                        stop_distance_pct=point.stop_distance_pct,
                        buy_signal=point.buy_signal,
                        sell_signal=point.sell_signal,
                    )
                )
                if include_markers and (point.buy_signal or point.sell_signal):
                    markers.append(
                        HacoMarker(
                            index=idx,
                            time=chart_times[idx],
                            marker_type="arrow_up" if point.buy_signal else "arrow_down",
                            direction="buy" if point.buy_signal else "sell",
                            price=bar.low if point.buy_signal else bar.high,
                            text="LONG" if point.buy_signal else "SHORT",
                        )
                    )
            latest = series.latest
            if latest is not None:
                explanation = AtrChartExplanation(
                    current_state=latest.state if latest.state in _DIRECTIONAL else "neutral",
                    latest_trailing_stop=latest.trailing_stop,
                    distance_to_stop_pct=latest.stop_distance_pct,
                    bars_since_flip=latest.bars_since_flip,
                    last_flip_direction=latest.last_flip_direction,
                    last_flip_time=latest.last_flip_time,
                )

        timeframe_states: list[AtrTimeframeState] = []
        for tf, entry in (timeframe_bars or {}).items():
            tf_bars, tf_source, tf_fallback = entry
            tf_canonical = self._dedupe(self._canonical_bars(list(tf_bars or [])), tf)
            if not tf_canonical:
                timeframe_states.append(
                    AtrTimeframeState(timeframe=tf, status="unavailable", data_source=tf_source, fallback_mode=tf_fallback, reason="no_bars")
                )
                continue
            point = compute_atr_trailing_stop(tf_canonical, config=cfg).latest
            if point is None:
                timeframe_states.append(
                    AtrTimeframeState(timeframe=tf, status="unavailable", data_source=tf_source, fallback_mode=tf_fallback, reason="insufficient_bars")
                )
                continue
            timeframe_states.append(
                AtrTimeframeState(
                    timeframe=tf,
                    status="ok",
                    state=point.state if point.state in _DIRECTIONAL else None,
                    trailing_stop=point.trailing_stop,
                    stop_distance_pct=point.stop_distance_pct,
                    bars_since_flip=point.bars_since_flip,
                    last_flip_direction=point.last_flip_direction,
                    last_flip_time=point.last_flip_time,
                    data_source=tf_source,
                    fallback_mode=tf_fallback,
                )
            )

        first_bar = canonical[0] if canonical else None
        last_bar = canonical[-1] if canonical else None
        return AtrChartPayload(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            trailing_stop=trailing_stop,
            markers=markers,
            explanation=explanation,
            timeframe_states=timeframe_states,
            config=config_echo,
            data_source=data_source,
            fallback_mode=fallback_mode,
            session_policy=metadata.get("session_policy") or (first_bar.session_policy if first_bar else None),
            source_session_policy=metadata.get("source_session_policy") or (first_bar.source_session_policy if first_bar else None),
            source_timeframe=metadata.get("source_timeframe") or (first_bar.source_timeframe if first_bar else None),
            output_timeframe=metadata.get("output_timeframe") or timeframe.upper(),
            first_bar_timestamp=(
                str(metadata.get("first_bar_timestamp"))
                if metadata.get("first_bar_timestamp") is not None
                else (first_bar.timestamp.isoformat() if first_bar and first_bar.timestamp else None)
            ),
            last_bar_timestamp=(
                str(metadata.get("last_bar_timestamp"))
                if metadata.get("last_bar_timestamp") is not None
                else (last_bar.timestamp.isoformat() if last_bar and last_bar.timestamp else None)
            ),
            notes=notes,
        )
