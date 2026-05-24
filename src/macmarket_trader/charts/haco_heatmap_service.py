"""HACO Direction Heatmap payload builder.

This service reuses the existing deterministic HACO chart path and translates
latest HACO state into LONG/SHORT research direction labels. It does not
create a numeric momentum-strength score and it does not affect recommendation,
approval, sizing, routing, or paper-order behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from macmarket_trader.charts.haco_service import HacoChartService
from macmarket_trader.charts.momentum_heatmap_service import (
    HEATMAP_MAX_CATEGORIES_PER_REQUEST,
    HEATMAP_MAX_ROWS_PER_REQUEST,
    HEATMAP_PROVIDER_SYMBOL_PATTERN,
    HEATMAP_REQUEST_MAX_SECONDS,
    HEATMAP_UNSUPPORTED_PROVIDER_SYMBOLS,
)
from macmarket_trader.data.providers.market_data import DataNotEntitledError, SymbolNotFoundError
from macmarket_trader.domain.schemas import (
    Bar,
    HacoChartPayload,
    HacoHeatmapCategoryRequest,
    HacoHeatmapCategoryResponse,
    HacoHeatmapDirectionCell,
    HacoHeatmapRequest,
    HacoHeatmapResponse,
    HacoHeatmapRowRequest,
    HacoHeatmapRowResponse,
)
from macmarket_trader.domain.time import utc_now
from macmarket_trader.domain.timeframes import CHART_BAR_LIMIT_BY_TIMEFRAME, ChartTimeframe

HACO_HEATMAP_TIMEFRAMES: tuple[ChartTimeframe, ...] = ("1W", "1D", "4H", "1H", "30M")
HACO_ALIGNMENT_WEIGHTS: dict[str, int] = {"1W": 3, "1D": 3, "4H": 2, "1H": 1, "30M": 1}
HACO_SHORT_TERM_WEIGHTS: dict[str, int] = {"4H": 2, "1H": 1, "30M": 1}


@dataclass(frozen=True)
class _HacoPayloadResult:
    payload: HacoChartPayload | None
    status: str
    reason: str | None = None
    data_source: str | None = None
    fallback_mode: bool | None = None
    as_of: str | None = None


class HacoHeatmapService:
    def __init__(self, market_data_service) -> None:  # noqa: ANN001
        self.market_data_service = market_data_service
        self.haco_chart_service = HacoChartService()
        self._payload_cache: dict[tuple[str, str], _HacoPayloadResult] = {}

    @staticmethod
    def _normalize_provider_symbol(row: HacoHeatmapRowRequest) -> str:
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
        if not HacoHeatmapService._is_supported_provider_symbol(provider_symbol):
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
    def _budget_exceeded(deadline: float | None) -> bool:
        return deadline is not None and monotonic() >= deadline

    @staticmethod
    def _direction_from_haco_state(state: str | None) -> tuple[str | None, str]:
        normalized = str(state or "").strip().lower()
        if normalized == "green":
            return "long", "LONG"
        if normalized == "red":
            return "short", "SHORT"
        return None, "—"

    @staticmethod
    def _encoded(cell: HacoHeatmapDirectionCell | None) -> int | None:
        if cell is None or cell.status != "ok":
            return None
        if cell.value == "long":
            return 1
        if cell.value == "short":
            return -1
        return None

    @staticmethod
    def _round(value: float | None) -> float | None:
        return round(value, 2) if value is not None else None

    @classmethod
    def _weighted_alignment(cls, states: dict[str, HacoHeatmapDirectionCell], weights: dict[str, int]) -> float | None:
        numerator = 0.0
        denominator = 0.0
        for timeframe, weight in weights.items():
            encoded = cls._encoded(states.get(timeframe))
            if encoded is None:
                continue
            numerator += encoded * weight
            denominator += weight
        if denominator <= 0:
            return None
        return cls._round((numerator / denominator) * 100)

    @staticmethod
    def _bias(alignment_percent: float | None) -> str | None:
        if alignment_percent is None:
            return None
        if alignment_percent >= 60:
            return "LONG"
        if alignment_percent <= -60:
            return "SHORT"
        return "MIXED"

    @staticmethod
    def _cell(
        *,
        status: str,
        reason: str,
        data_source: str | None = None,
        fallback_mode: bool | None = None,
        as_of: str | None = None,
    ) -> HacoHeatmapDirectionCell:
        return HacoHeatmapDirectionCell(
            value=None,
            label="—",
            status=status,  # type: ignore[arg-type]
            reason=reason,
            data_source=data_source,
            fallback_mode=fallback_mode,
            as_of=as_of,
        )

    @classmethod
    def _cell_map(cls, timeframes: list[str], *, status: str, reason: str) -> dict[str, HacoHeatmapDirectionCell]:
        return {timeframe: cls._cell(status=status, reason=reason) for timeframe in timeframes}

    def _haco_payload(self, *, provider_symbol: str, timeframe: ChartTimeframe) -> _HacoPayloadResult:
        cache_key = (provider_symbol, timeframe)
        cached = self._payload_cache.get(cache_key)
        if cached is not None:
            return cached

        unsupported_reason = self._unsupported_provider_symbol_reason(provider_symbol)
        if unsupported_reason is not None:
            result = _HacoPayloadResult(payload=None, status="unsupported", reason=unsupported_reason)
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
            result = _HacoPayloadResult(payload=None, status="unsupported", reason="symbol_not_found_or_provider_unsupported")
            self._payload_cache[cache_key] = result
            return result
        except DataNotEntitledError:
            result = _HacoPayloadResult(payload=None, status="unavailable", reason="data_not_entitled")
            self._payload_cache[cache_key] = result
            return result
        except Exception as exc:  # pragma: no cover - defensive row isolation
            result = _HacoPayloadResult(payload=None, status="error", reason=f"haco_fetch_failed:{type(exc).__name__}")
            self._payload_cache[cache_key] = result
            return result

        as_of = self._bar_as_of(bars[-1] if bars else None)
        if not bars:
            result = _HacoPayloadResult(
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
            payload = self.haco_chart_service.build_payload(
                symbol=provider_symbol,
                timeframe=timeframe,
                bars=bars,
                include_heikin_ashi=False,
                data_source=source,
                fallback_mode=fallback_mode,
            )
        except Exception as exc:  # pragma: no cover - existing HACO path should not crash a row
            result = _HacoPayloadResult(
                payload=None,
                status="error",
                reason=f"haco_state_failed:{type(exc).__name__}",
                data_source=source,
                fallback_mode=fallback_mode,
                as_of=as_of,
            )
            self._payload_cache[cache_key] = result
            return result

        result = _HacoPayloadResult(
            payload=payload,
            status="ok",
            data_source=source,
            fallback_mode=fallback_mode,
            as_of=as_of,
        )
        self._payload_cache[cache_key] = result
        return result

    def _state_cell(self, *, provider_symbol: str, timeframe: ChartTimeframe) -> HacoHeatmapDirectionCell:
        result = self._haco_payload(provider_symbol=provider_symbol, timeframe=timeframe)
        if result.status != "ok" or result.payload is None:
            return HacoHeatmapDirectionCell(
                value=None,
                label="—",
                status="error" if result.status == "error" else result.status,  # type: ignore[arg-type]
                reason=result.reason,
                data_source=result.data_source,
                fallback_mode=result.fallback_mode,
                as_of=result.as_of,
            )
        value, label = self._direction_from_haco_state(result.payload.explanation.current_haco_state)
        if value is None:
            return HacoHeatmapDirectionCell(
                value=None,
                label="—",
                status="unavailable",
                reason="haco_state_unavailable",
                data_source=result.data_source,
                fallback_mode=result.fallback_mode,
                as_of=result.as_of,
            )
        return HacoHeatmapDirectionCell(
            value=value,  # type: ignore[arg-type]
            label=label,
            status="ok",
            data_source=result.data_source,
            fallback_mode=result.fallback_mode,
            as_of=result.as_of,
        )

    @classmethod
    def _tags(
        cls,
        *,
        states: dict[str, HacoHeatmapDirectionCell],
        overall_bias: str | None,
        overall_alignment: float | None,
        short_term_bias: str | None,
        short_term_alignment: float | None,
    ) -> list[str]:
        valid_states = [cell.value for cell in states.values() if cell.status == "ok" and cell.value is not None]
        if not valid_states:
            return ["Unsupported"]
        if all(value == "long" for value in valid_states):
            return ["All LONG"]
        if all(value == "short" for value in valid_states):
            return ["All SHORT"]

        tags: list[str] = []
        daily = states.get("1D")
        if daily and daily.status == "ok" and daily.value == "long" and (short_term_bias == "SHORT" or (short_term_alignment is not None and short_term_alignment <= 0)):
            tags.append("Daily LONG / Short-Term Pullback")
        if daily and daily.status == "ok" and daily.value == "short" and (short_term_bias == "LONG" or (short_term_alignment is not None and short_term_alignment >= 0)):
            tags.append("Daily SHORT / Short-Term Bounce")
        if overall_bias == "MIXED" or (overall_alignment is not None and -60 < overall_alignment < 60):
            tags.append("Mixed / Chop")
        return tags or ["Mixed / Chop"]

    def _build_row(
        self,
        row: HacoHeatmapRowRequest,
        timeframes: list[str],
        *,
        deadline: float | None = None,
        forced_reason: str | None = None,
    ) -> HacoHeatmapRowResponse:
        provider_symbol = self._normalize_provider_symbol(row)
        symbol = str(row.symbol or provider_symbol).strip().upper()
        display_name = str(row.display_name or symbol or provider_symbol).strip()
        unsupported_reason = self._unsupported_provider_symbol_reason(provider_symbol)
        if forced_reason is not None:
            states = self._cell_map(timeframes, status="unavailable", reason=forced_reason)
        elif unsupported_reason is not None:
            states = self._cell_map(timeframes, status="unsupported", reason=unsupported_reason)
        else:
            states = {}
            for timeframe in timeframes:
                if self._budget_exceeded(deadline):
                    states[timeframe] = self._cell(status="unavailable", reason="haco_heatmap_request_time_budget_exceeded")
                    continue
                states[timeframe] = self._state_cell(provider_symbol=provider_symbol, timeframe=timeframe)  # type: ignore[arg-type]

        overall_alignment = self._weighted_alignment(states, HACO_ALIGNMENT_WEIGHTS)
        short_term_alignment = self._weighted_alignment(states, HACO_SHORT_TERM_WEIGHTS)
        overall_bias = self._bias(overall_alignment)
        short_term_bias = self._bias(short_term_alignment)
        daily_cell = states.get("1D")
        weekly_cell = states.get("1W")
        daily_context = daily_cell.label if daily_cell and daily_cell.status == "ok" else None
        macro_context = weekly_cell.label if weekly_cell and weekly_cell.status == "ok" else None
        tags = self._tags(
            states=states,
            overall_bias=overall_bias,
            overall_alignment=overall_alignment,
            short_term_bias=short_term_bias,
            short_term_alignment=short_term_alignment,
        )
        return HacoHeatmapRowResponse(
            id=row.id,
            symbol=symbol,
            displayName=display_name,
            providerSymbol=provider_symbol,
            states=states,
            overall_bias=overall_bias,  # type: ignore[arg-type]
            overall_alignment_percent=overall_alignment,
            daily_context=daily_context,  # type: ignore[arg-type]
            macro_context=macro_context,  # type: ignore[arg-type]
            short_term_bias=short_term_bias,  # type: ignore[arg-type]
            short_term_alignment_percent=short_term_alignment,
            tags=tags,
        )

    def _build_category(
        self,
        category: HacoHeatmapCategoryRequest,
        timeframes: list[str],
        *,
        deadline: float | None = None,
        forced_reason: str | None = None,
    ) -> HacoHeatmapCategoryResponse:
        rows: list[HacoHeatmapRowResponse] = []
        for idx, row in enumerate(category.rows):
            row_reason = forced_reason
            if row_reason is None and idx >= HEATMAP_MAX_ROWS_PER_REQUEST:
                row_reason = "haco_heatmap_request_row_limit_exceeded"
            rows.append(self._build_row(row, timeframes, deadline=deadline, forced_reason=row_reason))
        return HacoHeatmapCategoryResponse(categoryId=category.category_id, categoryLabel=category.category_label, rows=rows)

    def build_heatmap(self, request: HacoHeatmapRequest) -> HacoHeatmapResponse:
        timeframes = [tf for tf in request.timeframes if tf in HACO_HEATMAP_TIMEFRAMES]
        deadline = monotonic() + HEATMAP_REQUEST_MAX_SECONDS
        categories: list[HacoHeatmapCategoryResponse] = []
        for idx, category in enumerate(request.categories):
            forced_reason = None if idx < HEATMAP_MAX_CATEGORIES_PER_REQUEST else "haco_heatmap_request_category_limit_exceeded"
            categories.append(self._build_category(category, timeframes, deadline=deadline, forced_reason=forced_reason))
        return HacoHeatmapResponse(generated_at=utc_now(), timeframes=timeframes, categories=categories)
