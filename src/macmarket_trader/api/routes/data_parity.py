"""Admin-only Market Data Parity Lab API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from macmarket_trader.api.deps.auth import require_admin
from macmarket_trader.api.security import capped_int, normalize_symbol_list
from macmarket_trader.config import settings
from macmarket_trader.data_parity.service import ProviderParityService, snapshot_to_summary
from macmarket_trader.domain.timeframes import SUPPORTED_CHART_TIMEFRAMES, chart_timeframe_error_message, validate_chart_timeframe
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import ProviderOAuthRepository, ProviderParitySnapshotRepository


router = APIRouter(prefix="/admin/data-parity", tags=["data-parity"])
oauth_repo = ProviderOAuthRepository(SessionLocal)
snapshot_repo = ProviderParitySnapshotRepository(SessionLocal)


def _normalize_timeframes(value: object) -> list[str]:
    if value is None:
        return list(SUPPORTED_CHART_TIMEFRAMES)
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail="timeframes must be a list.")
    output: list[str] = []
    for item in value:
        try:
            timeframe = validate_chart_timeframe(item)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=chart_timeframe_error_message()) from exc
        if timeframe not in output:
            output.append(timeframe)
    return output or list(SUPPORTED_CHART_TIMEFRAMES)


@router.post("/run")
def run_data_parity(req: dict[str, object], admin=Depends(require_admin)):
    if not settings.data_parity_enabled:
        raise HTTPException(status_code=403, detail="Data parity lab is disabled.")
    symbols = normalize_symbol_list(
        req.get("symbols"),
        max_items=settings.data_parity_max_symbols,
        field_name="symbols",
    )
    timeframes = _normalize_timeframes(req.get("timeframes"))
    lookback = capped_int(
        req.get("lookbackBars"),
        default=settings.data_parity_default_lookback_bars,
        minimum=5,
        maximum=settings.data_parity_max_lookback_bars,
        field_name="lookbackBars",
    )
    normalized_request = dict(req)
    normalized_request["symbols"] = symbols
    normalized_request["timeframes"] = timeframes
    normalized_request["lookbackBars"] = lookback
    service = ProviderParityService(oauth_repo=oauth_repo, snapshot_repo=snapshot_repo)
    return service.run(normalized_request, app_user_id=admin.id)


@router.get("/snapshots")
def list_data_parity_snapshots(admin=Depends(require_admin)):
    rows = snapshot_repo.list_recent(app_user_id=admin.id, limit=25)
    return {"snapshots": [snapshot_to_summary(row) for row in rows]}


@router.get("/snapshots/{run_id}")
def get_data_parity_snapshot(run_id: str, admin=Depends(require_admin)):
    row = snapshot_repo.get_by_run_id(app_user_id=admin.id, run_id=run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Data parity snapshot not found.")
    return {
        "runId": row.run_id,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "request": row.request_json,
        "response": row.response_json,
    }
