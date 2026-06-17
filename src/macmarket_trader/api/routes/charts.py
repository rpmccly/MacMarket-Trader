"""Protected chart routes."""

from fastapi import APIRouter, Depends, HTTPException

from macmarket_trader.api.deps.auth import require_approved_user
from macmarket_trader.charts.atr_heatmap_reporting import atr_heatmap_csv, atr_heatmap_html, build_atr_report_payload
from macmarket_trader.charts.atr_heatmap_service import AtrHeatmapService
from macmarket_trader.charts.atr_service import AtrChartService
from macmarket_trader.charts.haco_service import HacoChartService
from macmarket_trader.charts.momentum_heatmap_service import MomentumHeatmapService
from macmarket_trader.charts.momentum_service import MomentumChartService
from macmarket_trader.data.providers.market_data import (
    DataNotEntitledError,
    ProviderUnavailableError,
    SymbolNotFoundError,
    configured_market_data_provider_name,
)
from macmarket_trader.data.providers.registry import build_market_data_service
from macmarket_trader.domain.schemas import (
    AtrChartPayload,
    AtrChartRequest,
    AtrHeatmapRequest,
    AtrHeatmapResponse,
    Bar,
    HacoChartPayload,
    HacoChartRequest,
    MomentumHeatmapRequest,
    MomentumHeatmapResponse,
    MomentumChartPayload,
    MomentumChartRequest,
    chart_history_range_bar_limit,
    chart_history_range_to_lookback_days,
)
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import DailyBarRepository

router = APIRouter(prefix="/charts", tags=["charts"])
service = HacoChartService()
momentum_service = MomentumChartService()
atr_service = AtrChartService()
bar_repo = DailyBarRepository(SessionLocal)
market_data_service = build_market_data_service()

# Bars per timeframe for the ATR Intel multi-timeframe state table (bounded so a
# single page load stays fast; the primary timeframe gets the full chart history).
ATR_TABLE_TIMEFRAME_BAR_LIMIT = 180


def _market_data_action(provider: str) -> str:
    if provider == "schwab":
        return "reconnect_schwab"
    if provider == "polygon":
        return "check_polygon_market_data"
    if provider == "alpaca":
        return "check_alpaca_market_data"
    return "configure_market_data_provider"


def _chart_market_data_unavailable(symbol: str, exc: Exception | None = None) -> HTTPException:
    provider = configured_market_data_provider_name()
    detail: dict[str, object] = {
        "ok": False,
        "code": "MARKET_DATA_PROVIDER_UNAVAILABLE",
        "provider": provider,
        "symbol": symbol.upper(),
        "message": (
            f"{provider} market data is unavailable for {symbol.upper()} chart context. "
            "No hidden fallback data was used; reconnect or restore provider health and retry."
        ),
        "action": _market_data_action(provider),
    }
    if exc is not None:
        detail["sanitized_error"] = str(exc).replace("\n", " ").replace("\r", " ")[:300]
    return HTTPException(status_code=503, detail=detail)


def _bar_metadata(bars: list[Bar], *, source: str, timeframe: str, fallback_mode: bool) -> dict[str, object]:
    first = bars[0] if bars else None
    last = bars[-1] if bars else None
    return {
        "provider": source,
        "timeframe": timeframe,
        "fallback_mode": fallback_mode,
        "session_policy": first.session_policy if first else None,
        "source_session_policy": first.source_session_policy if first else None,
        "source_timeframe": first.source_timeframe if first else None,
        "output_timeframe": timeframe.upper(),
        "filtered_extended_hours_count": 0 if first and first.session_policy == "regular_hours" else None,
        "rth_bucket_count": len(bars) if first and first.session_policy == "regular_hours" else None,
        "first_bar_timestamp": first.timestamp.isoformat() if first and first.timestamp else None,
        "last_bar_timestamp": last.timestamp.isoformat() if last and last.timestamp else None,
    }


def _resolve_bars(
    symbol: str,
    timeframe: str,
    request_bars: list[Bar],
    *,
    history_range: str = "1Y",
) -> tuple[list[Bar], str, bool, dict[str, object]]:
    if request_bars:
        return request_bars, "request_bars", False, _bar_metadata(
            request_bars,
            source="request_bars",
            timeframe=timeframe,
            fallback_mode=False,
        )

    limit = chart_history_range_bar_limit(timeframe, history_range)

    try:
        provider_bars, provider_source, provider_fallback = market_data_service.historical_bars(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
    except DataNotEntitledError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "ok": False,
                "code": "MARKET_DATA_NOT_ENTITLED",
                "provider": configured_market_data_provider_name(),
                "symbol": symbol.upper(),
                "message": f"Current market-data entitlement does not include {symbol.upper()} chart context.",
            },
        ) from exc
    except SymbolNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "code": "MARKET_DATA_SYMBOL_NOT_FOUND",
                "provider": configured_market_data_provider_name(),
                "symbol": symbol.upper(),
                "message": f"No provider bars found for {symbol.upper()}. Verify the ticker and retry.",
            },
        ) from exc
    except ProviderUnavailableError as exc:
        raise _chart_market_data_unavailable(symbol, exc) from exc
    if provider_bars:
        provider_metadata = getattr(market_data_service, "last_historical_metadata", None)
        return provider_bars, provider_source, provider_fallback, dict(provider_metadata or _bar_metadata(
            provider_bars,
            source=provider_source,
            timeframe=timeframe,
            fallback_mode=provider_fallback,
        ))

    persisted = bar_repo.list_for_symbol(symbol=symbol) if timeframe.upper() == "1D" else []
    if persisted:
        return (
            [
                Bar(
                    date=model.bar_date.date(),
                    open=model.open,
                    high=model.high,
                    low=model.low,
                    close=model.close,
                    volume=model.volume,
                    rel_volume=None,
                )
                for model in persisted
            ],
            "daily_bars",
            False,
            {},
        )

    try:
        bars, source, fallback = market_data_service.historical_bars(symbol=symbol, timeframe=timeframe, limit=limit)
    except ProviderUnavailableError as exc:
        raise _chart_market_data_unavailable(symbol, exc) from exc
    provider_metadata = getattr(market_data_service, "last_historical_metadata", None)
    return bars, source, fallback, dict(provider_metadata or _bar_metadata(
        bars,
        source=source,
        timeframe=timeframe,
        fallback_mode=fallback,
    ))


def _attach_history_range_metadata(
    payload, *, history_range: str, lookback_days: int, bars_returned: int
):
    """Stamp the operator-selected history range + lookback onto the
    chart payload. Pure read-only echo — never mutates ranking,
    scoring, approval, or paper-order behavior."""
    try:
        payload.history_range = history_range
        payload.lookback_days = lookback_days
        payload.bars_returned = bars_returned
    except Exception:
        # The chart route must never error on a metadata stamp. If the
        # payload model is missing these fields the result still
        # serializes — extra fields are tolerated on the response side.
        pass
    return payload


@router.post("/haco", response_model=HacoChartPayload)
def get_haco_chart(req: HacoChartRequest, _user=Depends(require_approved_user)) -> HacoChartPayload:
    bars, data_source, fallback_mode, metadata = _resolve_bars(
        req.symbol, req.timeframe, req.bars, history_range=req.history_range
    )
    payload = service.build_payload(
        symbol=req.symbol,
        timeframe=req.timeframe,
        bars=bars,
        include_heikin_ashi=req.include_heikin_ashi,
        data_source=data_source,
        fallback_mode=fallback_mode,
        metadata=metadata,
    )
    return _attach_history_range_metadata(
        payload,
        history_range=req.history_range,
        lookback_days=chart_history_range_to_lookback_days(req.history_range),
        bars_returned=len(bars),
    )


@router.post("/momentum", response_model=MomentumChartPayload)
def get_momentum_chart(req: MomentumChartRequest, _user=Depends(require_approved_user)) -> MomentumChartPayload:
    bars, data_source, fallback_mode, metadata = _resolve_bars(
        req.symbol, req.timeframe, req.bars, history_range=req.history_range
    )
    payload = momentum_service.build_payload(
        symbol=req.symbol,
        timeframe=req.timeframe,
        bars=bars,
        higher_timeframe_bars=list(req.higher_timeframe_bars) if req.higher_timeframe_bars else None,
        include_markers=req.include_markers,
        data_source=data_source,
        fallback_mode=fallback_mode,
        metadata=metadata,
    )
    return _attach_history_range_metadata(
        payload,
        history_range=req.history_range,
        lookback_days=chart_history_range_to_lookback_days(req.history_range),
        bars_returned=len(bars),
    )


@router.post("/momentum-heatmap", response_model=MomentumHeatmapResponse)
def get_momentum_heatmap(req: MomentumHeatmapRequest, _user=Depends(require_approved_user)) -> MomentumHeatmapResponse:
    return MomentumHeatmapService(market_data_service).build_heatmap(req)


@router.post("/atr", response_model=AtrChartPayload)
def get_atr_chart(req: AtrChartRequest, _user=Depends(require_approved_user)) -> AtrChartPayload:
    """ATR Trailing Stop intel: price + trailing-stop series for the primary
    timeframe plus a multi-timeframe state table. Research-only; reads the frozen
    ATR engine and never changes scoring/ranking/paper behavior."""
    config = {
        "trail_type": req.trail_type,
        "atr_period": req.atr_period,
        "atr_factor": req.atr_factor,
        "first_trade": req.first_trade,
        "average_type": req.average_type,
    }
    bars, data_source, fallback_mode, metadata = _resolve_bars(
        req.symbol, req.timeframe, req.bars, history_range=req.history_range
    )
    # Multi-timeframe table: a bounded recent window per timeframe (the primary
    # timeframe reuses the chart bars when no custom bars were supplied).
    timeframe_bars: dict[str, tuple[list[Bar], str, bool]] = {}
    for tf in req.multi_timeframes:
        if tf == req.timeframe and not req.bars and bars:
            timeframe_bars[tf] = (bars, data_source, fallback_mode)
            continue
        try:
            tf_bars, tf_source, tf_fallback = market_data_service.historical_bars(
                symbol=req.symbol, timeframe=tf, limit=ATR_TABLE_TIMEFRAME_BAR_LIMIT
            )
        except Exception:  # noqa: BLE001 - a single timeframe failing must not break the page.
            tf_bars, tf_source, tf_fallback = [], "unavailable", False
        timeframe_bars[tf] = (list(tf_bars or []), tf_source, bool(tf_fallback))
    payload = atr_service.build_payload(
        symbol=req.symbol,
        timeframe=req.timeframe,
        bars=bars,
        config=config,
        timeframe_bars=timeframe_bars,
        include_markers=req.include_markers,
        data_source=data_source,
        fallback_mode=fallback_mode,
        metadata=metadata,
    )
    return _attach_history_range_metadata(
        payload,
        history_range=req.history_range,
        lookback_days=chart_history_range_to_lookback_days(req.history_range),
        bars_returned=len(bars),
    )


@router.post("/atr-heatmap", response_model=AtrHeatmapResponse)
def get_atr_heatmap(req: AtrHeatmapRequest, _user=Depends(require_approved_user)) -> AtrHeatmapResponse:
    """ATR Direction Heatmap (research-only, stateless): per-symbol LONG/SHORT
    states across timeframes + deterministic alignment + trailing stop / distance /
    flip. Symbols come from the request (manual entry or an existing watchlist)."""
    return AtrHeatmapService(market_data_service).build_heatmap(req)


@router.post("/atr-heatmap/report/csv")
def get_atr_heatmap_csv(req: AtrHeatmapRequest, _user=Depends(require_approved_user)) -> dict[str, object]:
    response = AtrHeatmapService(market_data_service).build_heatmap(req).model_dump(mode="json")
    report = build_atr_report_payload(response=response, profile_name="ATR Direction Heatmap")
    return {"csv": atr_heatmap_csv(report), "filename": "atr-direction-heatmap-report.csv"}


@router.post("/atr-heatmap/report/preview")
def get_atr_heatmap_report_preview(req: AtrHeatmapRequest, _user=Depends(require_approved_user)) -> dict[str, object]:
    response = AtrHeatmapService(market_data_service).build_heatmap(req).model_dump(mode="json")
    report = build_atr_report_payload(response=response, profile_name="ATR Direction Heatmap")
    return {
        "report": report,
        "html": atr_heatmap_html(report),
        "emailStatus": "preview_only_no_email_sent",
    }
