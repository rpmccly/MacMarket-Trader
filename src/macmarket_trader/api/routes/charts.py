"""Protected chart routes."""

from fastapi import APIRouter, Depends

from macmarket_trader.api.deps.auth import require_approved_user
from macmarket_trader.charts.haco_service import HacoChartService
from macmarket_trader.charts.momentum_service import MomentumChartService
from macmarket_trader.data.providers.registry import build_market_data_service
from macmarket_trader.domain.schemas import (
    Bar,
    HacoChartPayload,
    HacoChartRequest,
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
bar_repo = DailyBarRepository(SessionLocal)
market_data_service = build_market_data_service()


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

    provider_bars, provider_source, provider_fallback = market_data_service.historical_bars(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
    )
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

    bars, source, fallback = market_data_service.historical_bars(symbol=symbol, timeframe=timeframe, limit=limit)
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
