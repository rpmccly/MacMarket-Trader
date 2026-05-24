"""Momentum Heatmap payload builder.

The heatmap reuses the existing deterministic True Momentum Score model. It
does not define an alternate score formula and it does not promote any score
into approval, sizing, routing, or execution logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from time import monotonic

from macmarket_trader.charts.momentum_service import MomentumChartService
from macmarket_trader.data.providers.market_data import DataNotEntitledError, SymbolNotFoundError
from macmarket_trader.domain.schemas import (
    Bar,
    MomentumHeatmapCategoryRequest,
    MomentumHeatmapCategoryResponse,
    MomentumHeatmapRequest,
    MomentumHeatmapResponse,
    MomentumHeatmapRowRequest,
    MomentumHeatmapRowResponse,
    MomentumHeatmapScoreCell,
    MomentumHeatmapSqueezeCell,
    MomentumChartPayload,
)
from macmarket_trader.domain.time import utc_now
from macmarket_trader.domain.timeframes import CHART_BAR_LIMIT_BY_TIMEFRAME, ChartTimeframe

HEATMAP_PROVIDER_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.]{0,14}$")
HEATMAP_SCORE_TIMEFRAMES: tuple[ChartTimeframe, ...] = ("1W", "1D", "4H", "1H", "30M")
HEATMAP_MAX_CATEGORIES_PER_REQUEST = 1
HEATMAP_MAX_ROWS_PER_REQUEST = 12
HEATMAP_REQUEST_MAX_SECONDS = 25.0
HEATMAP_UNSUPPORTED_PROVIDER_SYMBOLS: dict[str, str] = {
    "MAG7": "composite_symbol_deferred",
}

SQUEEZE_STATE_LABELS = {
    "high": "High squeeze",
    "mid": "Mid squeeze",
    "low": "Low squeeze",
    "none": "No squeeze",
}

SQUEEZE_STATE_RANK = {
    "high": 3,
    "mid": 2,
    "low": 1,
    "none": 0,
}


@dataclass(frozen=True)
class _MomentumPayloadResult:
    payload: MomentumChartPayload | None
    status: str
    reason: str | None = None
    data_source: str | None = None
    fallback_mode: bool | None = None
    as_of: str | None = None


class MomentumHeatmapService:
    def __init__(self, market_data_service) -> None:  # noqa: ANN001
        self.market_data_service = market_data_service
        self.momentum_chart_service = MomentumChartService()
        self._payload_cache: dict[tuple[str, str], _MomentumPayloadResult] = {}

    @staticmethod
    def _normalize_provider_symbol(row: MomentumHeatmapRowRequest) -> str:
        raw = row.provider_symbol or row.symbol
        return str(raw or "").strip().upper()

    @staticmethod
    def _is_supported_provider_symbol(provider_symbol: str) -> bool:
        return bool(HEATMAP_PROVIDER_SYMBOL_PATTERN.fullmatch(provider_symbol))

    @staticmethod
    def _unsupported_provider_symbol_reason(provider_symbol: str) -> str | None:
        if not provider_symbol:
            return "provider_symbol_missing"
        if provider_symbol in HEATMAP_UNSUPPORTED_PROVIDER_SYMBOLS:
            return HEATMAP_UNSUPPORTED_PROVIDER_SYMBOLS[provider_symbol]
        if not MomentumHeatmapService._is_supported_provider_symbol(provider_symbol):
            return "unsupported_symbol_format"
        return None

    @staticmethod
    def _bar_as_of(bar: Bar | None) -> str | None:
        if bar is None:
            return None
        if bar.timestamp is not None:
            return bar.timestamp.isoformat()
        return bar.date.isoformat()

    @staticmethod
    def _round_score(value: float | int | None) -> float | None:
        if value is None:
            return None
        return round(float(value), 2)

    @staticmethod
    def _cell(
        *,
        status: str,
        reason: str,
        data_source: str | None = None,
        fallback_mode: bool | None = None,
        as_of: str | None = None,
    ) -> MomentumHeatmapScoreCell:
        return MomentumHeatmapScoreCell(
            value=None,
            status=status,  # type: ignore[arg-type]
            reason=reason,
            data_source=data_source,
            fallback_mode=fallback_mode,
            as_of=as_of,
        )

    @classmethod
    def _cell_map(cls, timeframes: list[str], *, status: str, reason: str) -> dict[str, MomentumHeatmapScoreCell]:
        return {timeframe: cls._cell(status=status, reason=reason) for timeframe in timeframes}

    @staticmethod
    def _budget_exceeded(deadline: float | None) -> bool:
        return deadline is not None and monotonic() >= deadline

    def _momentum_payload(self, *, provider_symbol: str, timeframe: ChartTimeframe) -> _MomentumPayloadResult:
        cache_key = (provider_symbol, timeframe)
        cached = self._payload_cache.get(cache_key)
        if cached is not None:
            return cached

        unsupported_reason = self._unsupported_provider_symbol_reason(provider_symbol)
        if unsupported_reason is not None:
            result = _MomentumPayloadResult(payload=None, status="unsupported", reason=unsupported_reason)
            self._payload_cache[cache_key] = result
            return result

        try:
            limit = CHART_BAR_LIMIT_BY_TIMEFRAME[timeframe]
            bars, source, fallback_mode = self.market_data_service.historical_bars(
                symbol=provider_symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except SymbolNotFoundError:
            result = _MomentumPayloadResult(
                payload=None,
                status="unsupported",
                reason="symbol_not_found_or_provider_unsupported",
            )
            self._payload_cache[cache_key] = result
            return result
        except DataNotEntitledError:
            result = _MomentumPayloadResult(payload=None, status="unavailable", reason="data_not_entitled")
            self._payload_cache[cache_key] = result
            return result
        except Exception as exc:  # pragma: no cover - defensive row isolation
            result = _MomentumPayloadResult(payload=None, status="error", reason=f"score_fetch_failed:{type(exc).__name__}")
            self._payload_cache[cache_key] = result
            return result

        as_of = self._bar_as_of(bars[-1] if bars else None)
        if not bars:
            result = _MomentumPayloadResult(
                payload=None,
                status="unavailable",
                reason="market_data_bars_unavailable",
                data_source=source,
                fallback_mode=fallback_mode,
                as_of=as_of,
            )
            self._payload_cache[cache_key] = result
            return result

        try:
            payload = self.momentum_chart_service.build_payload(
                symbol=provider_symbol,
                timeframe=timeframe,
                bars=bars,
                include_markers=False,
                data_source=source,
                fallback_mode=fallback_mode,
            )
        except Exception as exc:  # pragma: no cover - deterministic scorer should not crash the row
            result = _MomentumPayloadResult(
                payload=None,
                status="error",
                reason=f"momentum_intelligence_score_failed:{type(exc).__name__}",
                data_source=source,
                fallback_mode=fallback_mode,
                as_of=as_of,
            )
            self._payload_cache[cache_key] = result
            return result

        result = _MomentumPayloadResult(
            payload=payload,
            status="ok",
            data_source=source,
            fallback_mode=fallback_mode,
            as_of=as_of,
        )
        self._payload_cache[cache_key] = result
        return result

    def _score_cell(self, *, provider_symbol: str, timeframe: ChartTimeframe) -> MomentumHeatmapScoreCell:
        result = self._momentum_payload(provider_symbol=provider_symbol, timeframe=timeframe)
        if result.status != "ok":
            score_status = "error" if result.status == "error" else result.status
            return MomentumHeatmapScoreCell(
                value=None,
                status=score_status,  # type: ignore[arg-type]
                reason=result.reason,
                data_source=result.data_source,
                fallback_mode=result.fallback_mode,
                as_of=result.as_of,
            )

        payload = result.payload
        if payload.latest_snapshot is None:
            return MomentumHeatmapScoreCell(
                value=None,
                status="unavailable",
                reason="momentum_intelligence_score_unavailable",
                data_source=result.data_source,
                fallback_mode=result.fallback_mode,
                as_of=result.as_of,
            )

        return MomentumHeatmapScoreCell(
            value=float(payload.latest_snapshot.total_score),
            status="ok",
            data_source=result.data_source,
            fallback_mode=result.fallback_mode,
            as_of=result.as_of,
        )

    def _squeeze_timeframe_detail(self, *, provider_symbol: str, timeframe: ChartTimeframe) -> dict[str, object]:
        result = self._momentum_payload(provider_symbol=provider_symbol, timeframe=timeframe)
        if result.status != "ok" or result.payload is None:
            return {
                "status": "unsupported" if result.status == "unsupported" else result.status,
                "reason": result.reason,
                "as_of": result.as_of,
            }
        squeeze_payload = result.payload.squeeze_pro
        if squeeze_payload is None or squeeze_payload.status != "ok":
            return {
                "status": "unavailable",
                "reason": squeeze_payload.reason if squeeze_payload else "squeeze_pro_unavailable",
                "as_of": result.as_of,
            }
        latest = next((point for point in reversed(squeeze_payload.series) if point.status == "ok"), None)
        if latest is None:
            return {
                "status": "unavailable",
                "reason": "insufficient_bars_for_squeeze_pro",
                "as_of": result.as_of,
            }
        return {
            "status": "ok",
            "state": latest.squeeze_state,
            "value": SQUEEZE_STATE_LABELS.get(latest.squeeze_state, latest.squeeze_state),
            "oscillator_value": latest.oscillator_value,
            "oscillator_state": latest.oscillator_state,
            "as_of": result.as_of,
            "data_source": result.data_source,
            "fallback_mode": result.fallback_mode,
        }

    def _squeeze_cell(
        self,
        *,
        provider_symbol: str,
        timeframes: list[str],
        deadline: float | None = None,
        forced_reason: str | None = None,
    ) -> MomentumHeatmapSqueezeCell:
        if forced_reason is not None:
            return MomentumHeatmapSqueezeCell(
                value=None,
                status="unavailable",
                reason=forced_reason,
                timeframes={timeframe: {"status": "unavailable", "reason": forced_reason} for timeframe in timeframes},
            )

        unsupported_reason = self._unsupported_provider_symbol_reason(provider_symbol)
        if unsupported_reason is not None:
            return MomentumHeatmapSqueezeCell(
                value=None,
                status="unavailable",
                reason=unsupported_reason,
                timeframes={timeframe: {"status": "unsupported", "reason": unsupported_reason} for timeframe in timeframes},
            )

        details: dict[str, dict[str, object]] = {}
        for timeframe in timeframes:
            if self._budget_exceeded(deadline):
                details[timeframe] = {"status": "unavailable", "reason": "heatmap_request_time_budget_exceeded"}
                continue
            details[timeframe] = self._squeeze_timeframe_detail(
                provider_symbol=provider_symbol,
                timeframe=timeframe,  # type: ignore[arg-type]
            )

        ok_details = [(timeframe, detail) for timeframe, detail in details.items() if detail.get("status") == "ok"]
        if not ok_details:
            reason = next((str(detail.get("reason")) for detail in details.values() if detail.get("reason")), "squeeze_pro_unavailable")
            return MomentumHeatmapSqueezeCell(value=None, status="unavailable", reason=reason, timeframes=details)

        selected_timeframe, selected = max(
            ok_details,
            key=lambda item: SQUEEZE_STATE_RANK.get(str(item[1].get("state")), -1),
        )
        state = str(selected.get("state") or "none")
        label = SQUEEZE_STATE_LABELS.get(state, state)
        return MomentumHeatmapSqueezeCell(
            value=label,
            status="ok",
            state=state if state in SQUEEZE_STATE_LABELS else None,  # type: ignore[arg-type]
            reason=f"strongest_active_squeeze:{selected_timeframe}",
            as_of=str(selected.get("as_of")) if selected.get("as_of") else None,
            timeframes=details,
        )

    @staticmethod
    def _numeric_score(scores: dict[str, MomentumHeatmapScoreCell], timeframe: str) -> float | None:
        cell = scores.get(timeframe)
        if cell is None or cell.status != "ok" or cell.value is None:
            return None
        return float(cell.value)

    def _long_term_score(self, scores: dict[str, MomentumHeatmapScoreCell]) -> float | None:
        weekly = self._numeric_score(scores, "1W")
        daily = self._numeric_score(scores, "1D")
        if weekly is None or daily is None:
            return None
        return self._round_score((weekly + daily) / 2)

    def _short_term_score(self, scores: dict[str, MomentumHeatmapScoreCell]) -> float | None:
        h4 = self._numeric_score(scores, "4H")
        h1 = self._numeric_score(scores, "1H")
        m30 = self._numeric_score(scores, "30M")
        if h4 is None or h1 is None or m30 is None:
            return None
        return self._round_score((h4 + h1 + m30) / 3)

    def _strength_percent(self, scores: dict[str, MomentumHeatmapScoreCell]) -> float | None:
        weekly = self._numeric_score(scores, "1W")
        daily = self._numeric_score(scores, "1D")
        h4 = self._numeric_score(scores, "4H")
        h1 = self._numeric_score(scores, "1H")
        m30 = self._numeric_score(scores, "30M")
        if None in {weekly, daily, h4, h1, m30}:
            return None
        return self._round_score(((weekly * 3) + (daily * 3) + h4 + h1 + m30) / 9)  # type: ignore[operator]

    def _build_row(
        self,
        row: MomentumHeatmapRowRequest,
        timeframes: list[str],
        *,
        deadline: float | None = None,
        forced_reason: str | None = None,
    ) -> MomentumHeatmapRowResponse:
        provider_symbol = self._normalize_provider_symbol(row)
        symbol = str(row.symbol or provider_symbol).strip().upper()
        display_name = str(row.display_name or symbol or provider_symbol).strip()
        if forced_reason is not None:
            scores = self._cell_map(timeframes, status="unavailable", reason=forced_reason)
        else:
            scores = {}
            for timeframe in timeframes:
                if self._budget_exceeded(deadline):
                    scores[timeframe] = self._cell(status="unavailable", reason="heatmap_request_time_budget_exceeded")
                    continue
                scores[timeframe] = self._score_cell(provider_symbol=provider_symbol, timeframe=timeframe)  # type: ignore[arg-type]
        squeeze = self._squeeze_cell(
            provider_symbol=provider_symbol,
            timeframes=timeframes,
            deadline=deadline,
            forced_reason=forced_reason,
        )
        return MomentumHeatmapRowResponse(
            id=row.id,
            symbol=symbol,
            displayName=display_name,
            providerSymbol=provider_symbol,
            scores=scores,
            long_term_score=self._long_term_score(scores),
            short_term_score=self._short_term_score(scores),
            strength_percent=self._strength_percent(scores),
            squeeze=squeeze,
        )

    def _build_category(
        self,
        category: MomentumHeatmapCategoryRequest,
        timeframes: list[str],
        *,
        deadline: float | None = None,
        forced_reason: str | None = None,
    ) -> MomentumHeatmapCategoryResponse:
        rows: list[MomentumHeatmapRowResponse] = []
        for idx, row in enumerate(category.rows):
            row_reason = forced_reason
            if row_reason is None and idx >= HEATMAP_MAX_ROWS_PER_REQUEST:
                row_reason = "heatmap_request_row_limit_exceeded"
            rows.append(self._build_row(row, timeframes, deadline=deadline, forced_reason=row_reason))
        return MomentumHeatmapCategoryResponse(
            categoryId=category.category_id,
            categoryLabel=category.category_label,
            rows=rows,
        )

    def build_heatmap(self, request: MomentumHeatmapRequest) -> MomentumHeatmapResponse:
        timeframes = [tf for tf in request.timeframes if tf in HEATMAP_SCORE_TIMEFRAMES]
        deadline = monotonic() + HEATMAP_REQUEST_MAX_SECONDS
        categories: list[MomentumHeatmapCategoryResponse] = []
        for idx, category in enumerate(request.categories):
            forced_reason = None if idx < HEATMAP_MAX_CATEGORIES_PER_REQUEST else "heatmap_request_category_limit_exceeded"
            categories.append(
                self._build_category(
                    category,
                    timeframes,
                    deadline=deadline,
                    forced_reason=forced_reason,
                )
            )
        return MomentumHeatmapResponse(
            generated_at=utc_now(),
            timeframes=timeframes,
            categories=categories,
        )
