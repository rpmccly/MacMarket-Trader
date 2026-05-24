"""Momentum Heatmap payload builder.

The heatmap reuses the existing deterministic True Momentum Score model. It
does not define an alternate score formula and it does not promote any score
into approval, sizing, routing, or execution logic.
"""

from __future__ import annotations

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


class MomentumHeatmapService:
    def __init__(self, market_data_service) -> None:  # noqa: ANN001
        self.market_data_service = market_data_service
        self.momentum_chart_service = MomentumChartService()

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

    def _score_cell(self, *, provider_symbol: str, timeframe: ChartTimeframe) -> MomentumHeatmapScoreCell:
        unsupported_reason = self._unsupported_provider_symbol_reason(provider_symbol)
        if unsupported_reason is not None:
            return self._cell(status="unsupported", reason=unsupported_reason)

        try:
            limit = CHART_BAR_LIMIT_BY_TIMEFRAME[timeframe]
            bars, source, fallback_mode = self.market_data_service.historical_bars(
                symbol=provider_symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except SymbolNotFoundError:
            return MomentumHeatmapScoreCell(
                value=None,
                status="unsupported",
                reason="symbol_not_found_or_provider_unsupported",
            )
        except DataNotEntitledError:
            return MomentumHeatmapScoreCell(
                value=None,
                status="unavailable",
                reason="data_not_entitled",
            )
        except Exception as exc:  # pragma: no cover - defensive row isolation
            return MomentumHeatmapScoreCell(
                value=None,
                status="error",
                reason=f"score_fetch_failed:{type(exc).__name__}",
            )

        if not bars:
            return MomentumHeatmapScoreCell(
                value=None,
                status="unavailable",
                reason="market_data_bars_unavailable",
                data_source=source,
                fallback_mode=fallback_mode,
            )

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
            return MomentumHeatmapScoreCell(
                value=None,
                status="error",
                reason=f"momentum_intelligence_score_failed:{type(exc).__name__}",
                data_source=source,
                fallback_mode=fallback_mode,
                as_of=self._bar_as_of(bars[-1] if bars else None),
            )

        if payload.latest_snapshot is None:
            return MomentumHeatmapScoreCell(
                value=None,
                status="unavailable",
                reason="momentum_intelligence_score_unavailable",
                data_source=source,
                fallback_mode=fallback_mode,
                as_of=self._bar_as_of(bars[-1] if bars else None),
            )

        return MomentumHeatmapScoreCell(
            value=float(payload.latest_snapshot.total_score),
            status="ok",
            data_source=source,
            fallback_mode=fallback_mode,
            as_of=self._bar_as_of(bars[-1]),
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
        # TODO(momentum-heatmap): wire an approved squeeze algorithm/version
        # here. Do not infer TTM/John Carter squeeze behavior from memory.
        squeeze = MomentumHeatmapSqueezeCell(
            value=None,
            status="deferred",
            reason="squeeze_algorithm_not_implemented",
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
