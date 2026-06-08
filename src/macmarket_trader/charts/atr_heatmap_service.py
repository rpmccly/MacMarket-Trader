"""Deterministic ATR Direction Heatmap service (research-only, stateless).

Per symbol × timeframe, reads the frozen ATR Trailing Stop engine and emits a
LONG/SHORT/unavailable state plus the trailing stop, distance-to-stop %, bars
since flip, and last flip. Alignment is deterministic: +1 per LONG timeframe and
−1 per SHORT timeframe, with a LONG/SHORT/MIXED label. No persistence, no
provider-default changes, no indicator-math changes.
"""

from __future__ import annotations

from datetime import datetime, timezone

from macmarket_trader.domain.schemas import (
    AtrChartConfigEcho,
    AtrHeatmapCell,
    AtrHeatmapRequest,
    AtrHeatmapResponse,
    AtrHeatmapRow,
    AtrHeatmapSummary,
)
from macmarket_trader.indicators.atr_trailing_stop import compute_atr_trailing_stop, normalize_config

# Per-timeframe bar window for the heatmap (bounded so a refresh stays fast).
HEATMAP_TIMEFRAME_BAR_LIMIT = 180
ATR_HEATMAP_TIMEFRAMES = ["1W", "1D", "4H", "1H", "30M"]
# Decision-timeframe priority for the single-value columns when 1D is missing.
_DECISION_PRIORITY = ["1D", "1W", "4H", "1H", "30M"]
_DIRECTIONAL = {"long", "short"}


class AtrHeatmapService:
    def __init__(self, market_data_service) -> None:  # noqa: ANN001
        self.market_data_service = market_data_service

    def _latest_point(self, symbol: str, timeframe: str, cfg) -> tuple[object | None, str | None]:  # noqa: ANN001
        try:
            bars, _source, _fallback = self.market_data_service.historical_bars(
                symbol=symbol, timeframe=timeframe, limit=HEATMAP_TIMEFRAME_BAR_LIMIT
            )
        except Exception:  # noqa: BLE001 - a single (symbol, timeframe) failing is unavailable, not fatal.
            return None, "provider_error"
        bars = list(bars or [])
        if not bars:
            return None, "no_bars"
        point = compute_atr_trailing_stop(bars, config=cfg).latest
        if point is None:
            return None, "insufficient_bars"
        return point, None

    def _build_row(self, symbol: str, timeframes: list[str], decision_timeframe: str, cfg) -> AtrHeatmapRow:  # noqa: ANN001
        states: dict[str, AtrHeatmapCell] = {}
        long_count = 0
        short_count = 0
        available_count = 0
        for tf in timeframes:
            point, reason = self._latest_point(symbol, tf, cfg)
            if point is None:
                states[tf] = AtrHeatmapCell(timeframe=tf, status="unavailable", reason=reason)
                continue
            state = point.state if point.state in _DIRECTIONAL else None
            available_count += 1
            if state == "long":
                long_count += 1
            elif state == "short":
                short_count += 1
            states[tf] = AtrHeatmapCell(
                timeframe=tf,
                status="ok",
                state=state,
                label=state.upper() if state else None,
                trailing_stop=point.trailing_stop,
                stop_distance_pct=point.stop_distance_pct,
                bars_since_flip=point.bars_since_flip,
                last_flip_direction=point.last_flip_direction,
                last_flip_time=point.last_flip_time,
            )
        alignment_score = long_count - short_count
        if available_count == 0:
            alignment_label = "—"
        elif long_count > 0 and short_count == 0:
            alignment_label = "LONG"
        elif short_count > 0 and long_count == 0:
            alignment_label = "SHORT"
        else:
            alignment_label = "MIXED"
        # Single-value columns from the decision timeframe (1D, else first available).
        decision_order = [decision_timeframe] + [tf for tf in _DECISION_PRIORITY if tf != decision_timeframe]
        decision_cell = None
        decision_tf = None
        for tf in decision_order:
            cell = states.get(tf)
            if cell is not None and cell.status == "ok":
                decision_cell = cell
                decision_tf = tf
                break
        status = "ok" if available_count > 0 else "unavailable"
        return AtrHeatmapRow(
            symbol=symbol,
            states=states,
            alignment_score=alignment_score,
            alignment_label=alignment_label,
            long_count=long_count,
            short_count=short_count,
            available_count=available_count,
            decision_timeframe=decision_tf,
            latest_trailing_stop=decision_cell.trailing_stop if decision_cell else None,
            distance_to_stop_pct=decision_cell.stop_distance_pct if decision_cell else None,
            bars_since_flip=decision_cell.bars_since_flip if decision_cell else None,
            last_flip_direction=decision_cell.last_flip_direction if decision_cell else None,
            last_flip_time=decision_cell.last_flip_time if decision_cell else None,
            status=status,
            reason=None if status == "ok" else "no_supported_timeframes",
        )

    def build_heatmap(self, request: AtrHeatmapRequest) -> AtrHeatmapResponse:
        cfg = normalize_config(
            {
                "trail_type": request.trail_type,
                "atr_period": request.atr_period,
                "atr_factor": request.atr_factor,
                "first_trade": request.first_trade,
                "average_type": request.average_type,
            }
        )
        timeframes = [tf for tf in (request.timeframes or ATR_HEATMAP_TIMEFRAMES)]
        rows = [self._build_row(symbol, timeframes, request.decision_timeframe, cfg) for symbol in request.symbols]
        summary = AtrHeatmapSummary(
            total=len(rows),
            long_count=sum(1 for r in rows if r.alignment_label == "LONG"),
            short_count=sum(1 for r in rows if r.alignment_label == "SHORT"),
            mixed_count=sum(1 for r in rows if r.alignment_label == "MIXED"),
            unavailable_count=sum(1 for r in rows if r.status != "ok"),
        )
        notes: list[str] = []
        if not request.symbols:
            notes.append("no_symbols")
        return AtrHeatmapResponse(
            rows=rows,
            summary=summary,
            timeframes=timeframes,
            config=AtrChartConfigEcho(
                trail_type=cfg.trail_type, atr_period=cfg.atr_period, atr_factor=cfg.atr_factor,
                first_trade=cfg.first_trade, average_type=cfg.average_type,
            ),
            generated_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
        )
