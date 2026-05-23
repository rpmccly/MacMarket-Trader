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
    MomentumPanelMarker,
    MomentumScoreSnapshot,
    MomentumScoreStripPoint,
    MomentumSignalMarker,
    MomentumStripPoint,
    MomentumVisualParityPoint,
    MomentumVisualParitySnapshot,
)
from macmarket_trader.domain.timeframes import is_intraday_chart_timeframe
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
        return is_intraday_chart_timeframe(timeframe)

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
                visual_parity_snapshot=MomentumVisualParitySnapshot(
                    as_of=None,
                    symbol=symbol,
                    timeframe=timeframe_upper,
                    iv_percent=None,
                    tos_hilo_elite_scalar=None,
                    source_notes=[
                        "No chart bars provided.",
                        "MacMarket does not compute a ToS-comparable ST_HiLoElite scalar.",
                    ],
                    unavailable_fields=[
                        "iv_percent",
                        "tos_hilo_elite_scalar",
                        "total_score",
                        "total_label",
                        "trend_score",
                        "momo_score",
                        "true_momentum",
                        "true_momentum_ema",
                        "hilo_slowd",
                        "hilo_slowd_x",
                        "hilo_thrust_state",
                        "hilo_score",
                        "pullback_signal",
                        "reversal_warning",
                        "no_trade_warning",
                    ],
                ),
                visual_parity_series=[],
                true_momentum_panel_markers=[],
                hilo_panel_markers=[],
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
        # Phase A3 copy hardening: marker text is context-only — no action verbs
        # like "buy", "sell", "enter", or "short". Markers describe deterministic
        # context, not trade approval.
        if include_markers:
            for idx, p in enumerate(score_series.points):
                bar = canonical_bars[idx]
                if p.new_max_bull_pullback or p.new_bull_pullback:
                    markers.append(
                        MomentumSignalMarker(
                            index=idx,
                            time=chart_times[idx],
                            marker_type="bullish_pullback_context",
                            direction="bullish",
                            price=bar.low,
                            text="Pullback context",
                        )
                    )
                if p.new_max_bear_rally or p.new_bear_rally:
                    markers.append(
                        MomentumSignalMarker(
                            index=idx,
                            time=chart_times[idx],
                            marker_type="bearish_rally_context",
                            direction="bearish",
                            price=bar.high,
                            text="Rally context",
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
                            text="Reversal warning",
                        )
                    )
                if p.neutral_up_to_bull:
                    markers.append(
                        MomentumSignalMarker(
                            index=idx,
                            time=chart_times[idx],
                            marker_type="neutral_to_bull",
                            direction="bullish",
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
                            direction="bearish",
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

        # ── Visual parity series + panel markers ────────────────────
        # Per-bar normalized parity status so the chart frontend can
        # render hover-aware top-left status badges. Values are pulled
        # from already-computed indicator state — no formula changes.
        visual_parity_series: list[MomentumVisualParityPoint] = []
        for idx, score_point in enumerate(score_series.points):
            hilo_point = hilo_series.points[idx]
            hilo_thrust_state: str
            if hilo_point.thrust == 1:
                hilo_thrust_state = "bullish"
            elif hilo_point.thrust == -1:
                hilo_thrust_state = "bearish"
            else:
                hilo_thrust_state = "neutral"
            point_reversal = bool(
                score_point.from_max_bull_to_weak
                or score_point.from_bull_to_weak
                or score_point.from_max_bear_to_weak
                or score_point.from_bear_to_weak
            )
            point_pullback = bool(
                score_point.new_max_bull_pullback
                or score_point.new_bull_pullback
                or score_point.new_max_bear_rally
                or score_point.new_bear_rally
            )
            point_no_trade = score_point.total_state == "neutral"
            visual_parity_series.append(
                MomentumVisualParityPoint(
                    index=idx,
                    time=chart_times[idx],
                    total_score=score_point.total_score,
                    total_label=score_point.total_label,
                    total_state=score_point.total_state,
                    trend_score=score_point.trend_score,
                    momo_score=score_point.momo_score,
                    true_momentum=score_point.true_momentum,
                    true_momentum_ema=score_point.true_momentum_ema,
                    # Rendered stochastic SlowD / SlowD_X from MacMarket's
                    # HiLo Elite port (range 0..100). These are NOT the
                    # ToS-comparable ST_HiLoElite scalar — that scalar is
                    # reserved as ``tos_hilo_elite_scalar`` on the parity
                    # snapshot and remains unavailable.
                    hilo_slowd=hilo_point.slow_d,
                    hilo_slowd_x=hilo_point.slow_d_x,
                    hilo_thrust_state=hilo_thrust_state,  # type: ignore[arg-type]
                    hilo_score=score_point.component_breakdown.hilo_thrust,
                    pullback_signal=point_pullback,
                    reversal_warning=point_reversal,
                    no_trade_warning=point_no_trade,
                )
            )

        # Latest-bar parity snapshot. IV% and the ToS-comparable
        # ST_HiLoElite scalar are intentionally left as None because
        # MacMarket does not currently compute either deterministically
        # — surfacing a fabricated value would break the parity charter.
        as_of_str: str | None = (
            last_bar.timestamp.isoformat() if last_bar.timestamp else last_bar.date.isoformat()
        )
        latest_parity_point = visual_parity_series[-1] if visual_parity_series else None
        unavailable_fields: list[str] = ["iv_percent", "tos_hilo_elite_scalar"]
        source_notes: list[str] = [
            "All visual parity fields come from already-computed Momentum indicator state.",
            "IV% is unavailable because no deterministic IV / IV-percentile source is wired into the Momentum chart payload.",
            "MacMarket does not compute a ToS-comparable ST_HiLoElite scalar; hilo_slowd / hilo_slowd_x are the rendered stochastic values.",
        ]
        if latest_parity_point is not None:
            visual_parity_snapshot = MomentumVisualParitySnapshot(
                as_of=as_of_str,
                symbol=symbol,
                timeframe=timeframe_upper,
                history_range=str(metadata.get("history_range")) if metadata.get("history_range") is not None else None,
                total_score=latest_parity_point.total_score,
                total_label=latest_parity_point.total_label,
                trend_score=latest_parity_point.trend_score,
                momo_score=latest_parity_point.momo_score,
                true_momentum=latest_parity_point.true_momentum,
                true_momentum_ema=latest_parity_point.true_momentum_ema,
                hilo_slowd=latest_parity_point.hilo_slowd,
                hilo_slowd_x=latest_parity_point.hilo_slowd_x,
                tos_hilo_elite_scalar=None,
                hilo_thrust_state=latest_parity_point.hilo_thrust_state,
                hilo_score=latest_parity_point.hilo_score,
                pullback_signal=latest_parity_point.pullback_signal,
                reversal_warning=latest_parity_point.reversal_warning,
                no_trade_warning=latest_parity_point.no_trade_warning,
                iv_percent=None,
                source_notes=source_notes,
                unavailable_fields=unavailable_fields,
            )
        else:
            visual_parity_snapshot = MomentumVisualParitySnapshot(
                as_of=as_of_str,
                symbol=symbol,
                timeframe=timeframe_upper,
                iv_percent=None,
                tos_hilo_elite_scalar=None,
                source_notes=source_notes,
                unavailable_fields=[
                    "iv_percent",
                    "tos_hilo_elite_scalar",
                    "total_score",
                    "total_label",
                    "trend_score",
                    "momo_score",
                    "true_momentum",
                    "true_momentum_ema",
                    "hilo_slowd",
                    "hilo_slowd_x",
                    "hilo_thrust_state",
                    "hilo_score",
                    "pullback_signal",
                    "reversal_warning",
                    "no_trade_warning",
                ],
            )

        # True Momentum / EMA panel markers — deterministic crosses
        # detected from the existing ``true_momentum`` and
        # ``true_momentum_ema`` series. Markers describe context only,
        # never buy/sell.
        true_momentum_panel_markers: list[MomentumPanelMarker] = []
        if include_markers and len(score_series.points) >= 2:
            for idx in range(1, len(score_series.points)):
                prev = score_series.points[idx - 1]
                cur = score_series.points[idx]
                prev_diff = prev.true_momentum - prev.true_momentum_ema
                cur_diff = cur.true_momentum - cur.true_momentum_ema
                if prev_diff <= 0 and cur_diff > 0:
                    true_momentum_panel_markers.append(
                        MomentumPanelMarker(
                            index=idx,
                            time=chart_times[idx],
                            panel="true_momentum",
                            marker_type="bullish_cross",
                            direction="up",
                            label="True Momentum cross up",
                            value=cur.true_momentum,
                            reason="True Momentum crossed above EMA",
                        )
                    )
                elif prev_diff >= 0 and cur_diff < 0:
                    true_momentum_panel_markers.append(
                        MomentumPanelMarker(
                            index=idx,
                            time=chart_times[idx],
                            panel="true_momentum",
                            marker_type="bearish_cross",
                            direction="down",
                            label="True Momentum cross down",
                            value=cur.true_momentum,
                            reason="True Momentum crossed below EMA",
                        )
                    )

        # HiLo panel markers — derived from the existing
        # ``thrust_changed`` flag on the HiLo series. Up/down arrows
        # render on the panel where the thrust state changed.
        hilo_panel_markers: list[MomentumPanelMarker] = []
        if include_markers:
            for idx, hilo_point in enumerate(hilo_series.points):
                if not hilo_point.thrust_changed:
                    continue
                if hilo_point.thrust == 1:
                    hilo_panel_markers.append(
                        MomentumPanelMarker(
                            index=idx,
                            time=chart_times[idx],
                            panel="hilo",
                            marker_type="hilo_confirmed",
                            direction="up",
                            label="HiLo confirmed",
                            value=hilo_point.slow_d,
                            reason="HiLo thrust transitioned to bullish/confirmed",
                        )
                    )
                elif hilo_point.thrust == -1:
                    hilo_panel_markers.append(
                        MomentumPanelMarker(
                            index=idx,
                            time=chart_times[idx],
                            panel="hilo",
                            marker_type="hilo_deconfirmed",
                            direction="down",
                            label="HiLo deconfirmed",
                            value=hilo_point.slow_d,
                            reason="HiLo thrust transitioned to bearish/unconfirmed",
                        )
                    )
                else:
                    hilo_panel_markers.append(
                        MomentumPanelMarker(
                            index=idx,
                            time=chart_times[idx],
                            panel="hilo",
                            marker_type="hilo_state_transition",
                            direction="neutral",
                            label="HiLo state transition",
                            value=hilo_point.slow_d,
                            reason="HiLo thrust state changed",
                        )
                    )

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
            visual_parity_snapshot=visual_parity_snapshot,
            visual_parity_series=visual_parity_series,
            true_momentum_panel_markers=true_momentum_panel_markers,
            hilo_panel_markers=hilo_panel_markers,
        )
