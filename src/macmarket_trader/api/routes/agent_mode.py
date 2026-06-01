from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from macmarket_trader.agent_mode.service import AgentModeService
from macmarket_trader.api.deps.auth import require_approved_user
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import AgentModeRepository


router = APIRouter(prefix="/user/agent-mode", tags=["agent-mode"])
agent_repo = AgentModeRepository(SessionLocal)
agent_service = AgentModeService(agent_repo=agent_repo)


@router.get("/settings")
def get_agent_mode_settings(user=Depends(require_approved_user)):
    row = agent_repo.get_or_create_settings(app_user_id=user.id)
    return agent_service.serialize_settings(row)


@router.post("/settings")
def update_agent_mode_settings(req: dict[str, object], user=Depends(require_approved_user)):
    mode = str(req.get("mode") or req.get("execution_mode") or "paper").strip().lower()
    if mode not in {"paper", "paper_only"}:
        raise HTTPException(status_code=409, detail="Agent Mode only supports paper mode.")
    updates = agent_service.normalize_settings_update(req)
    row = agent_repo.update_settings(app_user_id=user.id, updates=updates)
    return agent_service.serialize_settings(row)


@router.post("/run")
def run_agent_mode(req: dict[str, object] | None = None, user=Depends(require_approved_user)):
    return agent_service.run(user=user, request=req or {})


@router.get("/latest")
def latest_agent_mode_run(user=Depends(require_approved_user)):
    settings = agent_service.serialize_settings(agent_repo.get_or_create_settings(app_user_id=user.id))
    latest = agent_repo.latest_run(app_user_id=user.id)
    return {
        "settings": settings,
        "latestRun": agent_service.serialize_run(latest) if latest else None,
        "empty": latest is None,
        "paperOnly": True,
        "executionMode": "paper",
    }


@router.get("/runs")
def list_agent_mode_runs(
    limit: int = Query(50, ge=1, le=100),
    status: str | None = Query(None),
    dry_run: bool | None = Query(None),
    user=Depends(require_approved_user),
):
    safe_status = status if status in {None, "completed", "error"} else None
    return agent_service.list_runs(user=user, limit=limit, status=safe_status, dry_run=dry_run)


@router.get("/trades")
def list_agent_mode_trades(
    limit: int = Query(100, ge=1, le=250),
    user=Depends(require_approved_user),
):
    return agent_service.list_trades(user=user, limit=limit)


@router.get("/performance")
def get_agent_mode_performance(user=Depends(require_approved_user)):
    return agent_service.performance(user=user)
