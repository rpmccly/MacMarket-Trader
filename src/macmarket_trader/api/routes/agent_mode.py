from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from macmarket_trader.agent_mode.service import AgentModeService
from macmarket_trader.api.deps.auth import require_approved_user
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import AgentModeRepository, AgentProfileRepository


router = APIRouter(prefix="/user/agent-mode", tags=["agent-mode"])
agent_repo = AgentModeRepository(SessionLocal)
profile_repo = AgentProfileRepository(SessionLocal)
agent_service = AgentModeService(agent_repo=agent_repo, profile_repo=profile_repo)


# ── Agent Profiles (Phase 11) ────────────────────────────────────────────────
@router.get("/profiles")
def list_agent_profiles(user=Depends(require_approved_user)):
    return agent_service.list_profiles(user=user)


@router.post("/profiles")
def create_agent_profile(req: dict[str, object], user=Depends(require_approved_user)):
    return agent_service.create_profile(user=user, payload=req or {})


@router.get("/agents")
def agent_profiles_overview(user=Depends(require_approved_user)):
    return agent_service.agents_overview(user=user)


@router.get("/profiles/{profile_uid}")
def get_agent_profile(profile_uid: str, user=Depends(require_approved_user)):
    return agent_service.get_settings(user=user, profile_uid=profile_uid)


@router.put("/profiles/{profile_uid}")
def update_agent_profile(profile_uid: str, req: dict[str, object], user=Depends(require_approved_user)):
    return agent_service.update_settings(user=user, payload={**(req or {}), "profile_uid": profile_uid})


@router.delete("/profiles/{profile_uid}")
def delete_agent_profile(profile_uid: str, user=Depends(require_approved_user)):
    return agent_service.delete_profile(user=user, profile_uid=profile_uid)


@router.post("/profiles/{profile_uid}/default")
def set_default_agent_profile(profile_uid: str, user=Depends(require_approved_user)):
    return agent_service.set_default_profile(user=user, profile_uid=profile_uid)


# ── Per-profile settings + run controls (default profile when unscoped) ───────
@router.get("/settings")
def get_agent_mode_settings(profile_id: int | None = Query(None), user=Depends(require_approved_user)):
    return agent_service.get_settings(user=user, profile_id=profile_id)


@router.post("/settings")
def update_agent_mode_settings(req: dict[str, object], user=Depends(require_approved_user)):
    return agent_service.update_settings(user=user, payload=req)


@router.post("/run")
def run_agent_mode(req: dict[str, object] | None = None, user=Depends(require_approved_user)):
    return agent_service.run(user=user, request=req or {})


@router.get("/latest")
def latest_agent_mode_run(profile_id: int | None = Query(None), user=Depends(require_approved_user)):
    return agent_service.latest_run_response(user=user, profile_id=profile_id)


@router.get("/status")
def get_agent_mode_status(profile_id: int | None = Query(None), user=Depends(require_approved_user)):
    return agent_service.schedule_status(user=user, profile_id=profile_id)


@router.get("/runs")
def list_agent_mode_runs(
    limit: int = Query(50, ge=1, le=100),
    status: str | None = Query(None),
    dry_run: bool | None = Query(None),
    timeframe: str | None = Query(None),
    profile_id: int | None = Query(None),
    user=Depends(require_approved_user),
):
    safe_status = status if status in {None, "completed", "error"} else None
    return agent_service.list_runs(
        user=user, limit=limit, status=safe_status, dry_run=dry_run, timeframe=timeframe, profile_id=profile_id
    )


@router.get("/trades")
def list_agent_mode_trades(
    limit: int = Query(100, ge=1, le=250),
    timeframe: str | None = Query(None),
    symbol: str | None = Query(None),
    status: str | None = Query(None),
    source: str | None = Query("agent_mode"),
    run_id: str | None = Query(None),
    profile_id: int | None = Query(None),
    user=Depends(require_approved_user),
):
    return agent_service.list_trades(
        user=user,
        limit=limit,
        timeframe=timeframe,
        symbol=symbol,
        status=status,
        source=source,
        run_id=run_id,
        profile_id=profile_id,
    )


@router.get("/performance")
def get_agent_mode_performance(
    timeframe: str | None = Query(None),
    source: str | None = Query("agent_mode"),
    profile_id: int | None = Query(None),
    user=Depends(require_approved_user),
):
    return agent_service.performance(user=user, timeframe=timeframe, source=source, profile_id=profile_id)


@router.post("/notifications/test")
def send_agent_mode_test_notification(req: dict[str, object] | None = None, user=Depends(require_approved_user)):
    body = req or {}
    raw_profile_id = body.get("profile_id")
    profile_id = int(raw_profile_id) if str(raw_profile_id or "").strip().isdigit() else None
    return agent_service.send_test_notification(
        user=user,
        channel=str(body.get("channel") or ""),
        profile_uid=body.get("profile_uid"),
        profile_id=profile_id,
    )
