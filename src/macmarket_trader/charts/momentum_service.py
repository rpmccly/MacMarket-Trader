"""Deterministic Momentum Intelligence Layer chart payload builder."""

from __future__ import annotations

from datetime import UTC, datetime

from macmarket_trader.domain.schemas import (
    Bar,
    ChartCandle,
    MomentumChartExplanation,
    MomentumChartPayload,
    MomentumComponentBreakdownPayload,
    MomentumLinePoint,
    MomentumScoreSnapshot,
    MomentumScoreStripPoint,
    MomentumSignalMarker,
    MomentumStripPoint,
)
from macmarket_trader.indicators.hilo_elite import compute_hilo_elite
from macmarket_trader.indicators.true_momentum import compute_true_momentum
from macmarket_trader.indicators.true_momentum_score import compute_true_momentum_score


class MomentumChartService:
    @staticmethod
    def _canonical_bars(bars: list[Bar]) -> list[Bar]:
        return sorted(
            bars,
            key=lambda bar: bar.timestamp or datetime.combine(bar.date, datetime.min.time(), tzinfo=UTC),
        )

    @staticmethod
    def _is_intraday_timeframe(timeframe: str) -> bool:
        return timeframe.upper() != "1D"

    @classmethod
    def _chart_time(cls, bar: Bar, timeframe: str) -> str | int:
        if cls._is_intraday_timeframe(timeframe) and bar.timestamp is not None:
            return int(bar.timestamp.astimezone(UTC).timestamp())
        return bar.date.isoformat()

    @classmethod
    def _dedupe_canonical_bars(cls, bars: list[Bar], timeframe: str) -> list[Bar]:
        if not cls._is_intraday_timeframe(timeframe):
            return bars
        by_time: dict[str | int, Bar] = {}
        for bar in bars:
            by_time[cls._chart_time(bar, timeframe)] = bar
        return list(by_time.values())

    def build_payload(
        self,
        symbol: str,
        timeframe: str,
        bars: list[Bar],
        *,
        higher_timeframe_bars: list[Bar] | None = None,
        include_markers: bool = True,
        data_source: str = "request_bars",
        fallback_mode: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> MomentumChartPayload:
        timeframe_upper = timeframe.upper()
        canonical_bars = self._dedupe_canonical_bars(self._canonical_bars(bars), timeframe_upper)
        metadata = metadata or {}
        chart_times = [self._chart_time(bar, timeframe_upper) for bar in canonical_bars]

        if not canonical_bars:
            return MomentumChartPayload(
                symbol=symbol,
                timeframe=timeframe_upper,
                candles=[],
                true_momentum_line=[],
                true_momentum_ema_line=[],
                hilo_slowd_line=[],
                hilo_slowd_x_line=[],
                hilo_thrust_strip=[],
                score_strip=[],
                markers=[],
                latest_snapshot=None,
                explanation=None,
                data_source=data_source,
                fallback_mode=fallback_mode,
                higher_timeframe_source="insufficient_data",
                higher_timeframe=None,
                parity_status="pending_thinkorswim_fixture_validation",
                calculation_notes=["no chart bars provided"],
            )

        tm_series = compute_true_momentum(
            canonical_bars,
            timeframe=timeframe_upper,  # type: ignore[arg-type]
            higher_timeframe_bars=higher_timeframe_bars,
        )
        hilo_series = compute_hilo_elite(canonical_bars, timeframe=timeframe_upper)  # type: ignore[arg-type]
        score_series = compute_true_momentum_score(
            canonical_bars,
            timeframe=timeframe_upper,  # type: ignore[arg-type]
            true_momentum_series=tm_series,
            hilo_series=hilo_series,
        )

        candles = [
            ChartCandle(
                index=idx,
                time=chart_times[idx],
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for idx, bar in enumerate(canonical_bars)
        ]

        true_momentum_line = [
            MomentumLinePoint(index=idx, time=chart_times[idx], value=p.true_momentum)
            for idx, p in enumerate(tm_series.points)
        ]
        true_momentum_ema_line = [
            MomentumLinePoint(index=idx, time=chart_times[idx], value=p.true_momentum_ema)
            for idx, p in enumerate(tm_series.points)
        ]
        hilo_slowd_line = [
            MomentumLinePoint(index=idx, time=chart_times[idx], value=p.slow_d)
            for idx, p in enumerate(hilo_series.points)
        ]
        hilo_slowd_x_line = [
            MomentumLinePoint(index=idx, time=chart_times[idx], value=p.slow_d_x)
            for idx, p in enumerate(hilo_series.points)
        ]

        hilo_thrust_strip = [
            MomentumStripPoint(
                index=idx,
                time=chart_times[idx],
                value=100 if p.thrust == 1 else (0 if p.thrust == -1 else 50),
                state="bullish" if p.thrust == 1 else ("bearish" if p.thrust == -1 else "neutral"),
            )
            for idx, p in enumerate(hilo_series.points)
        ]

        score_strip = [
            MomentumScoreStripPoint(
                index=idx,
                time=chart_times[idx],
                total_score=p.total_score,
                state=p.total_state,
            )
            for idx, p in enumerate(score_series.points)
        ]

        markers: list[MomentumSignalMarker] = []
        if include_markers:
            for idx, p in enumerate(score_series.points):
                bar = canonical_bars[idx]
                if p.new_max_bull_pullback or p.new_bull_pullback:
                    markers.append(
                        MomentumSignalMarker(
                            index=idx,
                            time=chart_times[idx],
                            marker_type="bullish_pullback_buy",
                            direction="buy",
                            price=bar.low,
                            text="Pullback Buy",
                        )
                    )
                if p.new_max_bear_rally or p.new_bear_rally:
                    markers.append(
                        MomentumSignalMarker(
                            index=idx,
                            time=chart_times[idx],
                            marker_type="bearish_rally_sell",
                            direction="sell",
                            price=bar.high,
                            text="Rally Sell",
                        )
                    )
                if (
                    p.from_max_bull_to_weak
                    or p.from_bull_to_weak
                    or p.from_max_bear_to_weak
                    or p.from_bear_to_weak
                ):
                    markers.append(
                        MomentumSignalMarker(
                            index=idx,
                            time=chart_times[idx],
                            marker_type="reversal_warning",
                            direction="warning",
                            price=bar.close,
                            text="Reversal Warning",
                        )
                    )
                if p.neutral_up_to_bull:
                    markers.append(
                        MomentumSignalMarker(
                            index=idx,
                            time=chart_times[idx],
                            marker_type="neutral_to_bull",
                            direction="buy",
                            price=bar.low,
                            text="Neutral → Bull",
                        )
                    )
                if p.neutral_dn_to_bear:
                    markers.append(
                        MomentumSignalMarker(
                            index=idx,
                            time=chart_times[idx],
                            marker_type="neutral_to_bear",
                            direction="sell",
                            price=bar.high,
                            text="Neutral → Bear",
                        )
                    )

        latest_score = score_series.points[-1]
        snapshot = MomentumScoreSnapshot(
            total_score=latest_score.total_score,
            total_label=latest_score.total_label,
            total_state=latest_score.total_state,
            trend_score=latest_score.trend_score,
            momo_score=latest_score.momo_score,
            true_momentum=latest_score.true_momentum,
            true_momentum_ema=latest_score.true_momentum_ema,
            true_momentum_score=latest_score.component_breakdown.true_momentum_score,
            hilo_thrust=latest_score.hilo_thrust,
            hilo_score=latest_score.component_breakdown.hilo_thrust,
            atr_bias=latest_score.component_breakdown.atr_value,
            macd_bias=latest_score.component_breakdown.macd_bias,
            ma_bias=latest_score.component_breakdown.bull_ma + latest_score.component_breakdown.bear_ma,
            component_breakdown=MomentumComponentBreakdownPayload(
                true_momentum_score=latest_score.component_breakdown.true_momentum_score,
                hilo_thrust=latest_score.component_breakdown.hilo_thrust,
                bull_ma=latest_score.component_breakdown.bull_ma,
                bear_ma=latest_score.component_breakdown.bear_ma,
                atr_value=latest_score.component_breakdown.atr_value,
                macd_bias=latest_score.component_breakdown.macd_bias,
                intraday_penalty=latest_score.component_breakdown.intraday_penalty,
                base_score=latest_score.component_breakdown.base_score,
            ),
        )

        reversal_warning = (
            latest_score.from_max_bull_to_weak
            or latest_score.from_bull_to_weak
            or latest_score.from_max_bear_to_weak
            or latest_score.from_bear_to_weak
        )
        pullback_signal = (
            latest_score.new_max_bull_pullback
            or latest_score.new_bull_pullback
            or latest_score.new_max_bear_rally
            or latest_score.new_bear_rally
        )
        no_trade_warning = latest_score.total_state == "neutral"

        notes = list(tm_series.notes) + list(hilo_series.notes) + list(score_series.notes)

        explanation = MomentumChartExplanation(
            snapshot=snapshot,
            reversal_warning=bool(reversal_warning),
            pullback_signal=bool(pullback_signal),
            no_trade_warning=bool(no_trade_warning),
            notes=notes,
        )

        first_bar = canonical_bars[0]
        last_bar = canonical_bars[-1]

        return MomentumChartPayload(
            symbol=symbol,
            timeframe=timeframe_upper,
            candles=candles,
            true_momentum_line=true_momentum_line,
            true_momentum_ema_line=true_momentum_ema_line,
            hilo_slowd_line=hilo_slowd_line,
            hilo_slowd_x_line=hilo_slowd_x_line,
            hilo_thrust_strip=hilo_thrust_strip,
            score_strip=score_strip,
            markers=markers,
            latest_snapshot=snapshot,
            explanation=explanation,
            data_source=data_source,
            fallback_mode=fallback_mode,
            session_policy=metadata.get("session_policy") or first_bar.session_policy,
            source_session_policy=metadata.get("source_session_policy") or first_bar.source_session_policy,
            source_timeframe=metadata.get("source_timeframe") or first_bar.source_timeframe,
            output_timeframe=metadata.get("output_timeframe") or timeframe_upper,
            first_bar_timestamp=(
                str(metadata.get("first_bar_timestamp"))
                if metadata.get("first_bar_timestamp") is not None
                else (first_bar.timestamp.isoformat() if first_bar.timestamp else None)
            ),
            last_bar_timestamp=(
                str(metadata.get("last_bar_timestamp"))
                if metadata.get("last_bar_timestamp") is not None
                else (last_bar.timestamp.isoformat() if last_bar.timestamp else None)
            ),
            higher_timeframe_source=tm_series.higher_timeframe_source,
            higher_timeframe=tm_series.higher_timeframe_label,
            parity_status=tm_series.parity_status,
            calculation_notes=notes,
        )
