"""User-scoped HACO Direction Heatmap profiles, snapshots, and reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from macmarket_trader.api.deps.auth import require_approved_user
from macmarket_trader.charts.haco_heatmap_reporting import (
    annotate_rows,
    build_report_payload,
    category_summaries,
    compute_changes,
    haco_heatmap_csv,
    haco_heatmap_html,
    unsupported_summary,
)
from macmarket_trader.charts.haco_heatmap_service import HacoHeatmapService
from macmarket_trader.data.providers.registry import build_market_data_service
from macmarket_trader.domain.schemas import HacoHeatmapRequest
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import HacoHeatmapRepository

router = APIRouter(prefix="/user/haco-heatmap", tags=["haco-heatmap"])

haco_heatmap_repo = HacoHeatmapRepository(SessionLocal)
market_data_service = build_market_data_service()


def _dt(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _profile_payload(profile) -> dict[str, Any]:  # noqa: ANN001
    view_settings = profile.view_settings or {}
    metadata = view_settings if isinstance(view_settings, dict) else {}
    return {
        "id": profile.profile_uid,
        "profileId": profile.profile_uid,
        "databaseId": profile.id,
        "name": profile.name,
        "description": metadata.get("description"),
        "slug": metadata.get("slug"),
        "viewType": metadata.get("viewType"),
        "categories": profile.categories or [],
        "viewSettings": view_settings,
        "reportPreferences": profile.report_preferences or {},
        "isDefault": bool(profile.is_default),
        "isSystemSeeded": bool(metadata.get("isSystemSeeded") is True),
        "createdAt": _dt(profile.created_at),
        "updatedAt": _dt(profile.updated_at),
    }


def _snapshot_payload(snapshot) -> dict[str, Any] | None:  # noqa: ANN001
    if snapshot is None:
        return None
    return {
        "id": snapshot.snapshot_uid,
        "databaseId": snapshot.id,
        "profileId": snapshot.profile_id,
        "status": snapshot.status,
        "generated_at": _dt(snapshot.generated_at),
        "generatedAt": _dt(snapshot.generated_at),
        "reportLabel": snapshot.report_label,
        "requestedCategories": snapshot.requested_categories or [],
        "requestedRows": snapshot.requested_rows or [],
        "payload": snapshot.payload or {},
        "categorySummaries": snapshot.category_summaries or [],
        "unsupportedSummary": snapshot.unsupported_summary or {},
        "previousSnapshotId": snapshot.previous_snapshot_id,
        "createdAt": _dt(snapshot.created_at),
    }


def _flatten_requested_rows(categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for category in categories:
        rows = category.get("rows") if isinstance(category, dict) else []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                output.append(dict(row))
    return output


def _snapshot_status(payload: dict[str, Any]) -> str:
    rows = _flatten_requested_rows(payload.get("categories") if isinstance(payload.get("categories"), list) else [])
    if not rows:
        return "failed"
    ok = 0
    non_ok = 0
    for category in payload.get("categories") or []:
        if not isinstance(category, dict):
            continue
        for row in category.get("rows") or []:
            if not isinstance(row, dict):
                continue
            cells = [cell for cell in (row.get("states") or {}).values() if isinstance(cell, dict)]
            if cells and all(cell.get("status") == "ok" for cell in cells):
                ok += 1
            else:
                non_ok += 1
    if ok and not non_ok:
        return "fresh"
    if ok:
        return "partial"
    return "failed"


def _profile_for_request(user, profile_id: str | None = None):  # noqa: ANN001
    if profile_id:
        profile = haco_heatmap_repo.get_profile(app_user_id=user.id, profile_uid=profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="haco_heatmap_profile_not_found")
        return profile
    return haco_heatmap_repo.get_or_create_default_profile(app_user_id=user.id)


def _profile_response(user, profile) -> dict[str, Any]:  # noqa: ANN001
    profiles = haco_heatmap_repo.list_profiles(app_user_id=user.id)
    return {
        "profile": _profile_payload(profile),
        "profiles": [_profile_payload(item) for item in profiles],
        "source": "server",
    }


@router.get("/profile")
def get_profile(profileId: str | None = None, user=Depends(require_approved_user)):  # noqa: N803
    profile = _profile_for_request(user, profileId)
    return _profile_response(user, profile)


@router.put("/profile")
def update_profile(req: dict[str, Any], user=Depends(require_approved_user)):
    profile_id = str(req.get("profileId") or req.get("id") or "").strip() or None
    profile = haco_heatmap_repo.update_profile(app_user_id=user.id, profile_uid=profile_id, updates=req)
    if profile is None:
        raise HTTPException(status_code=404, detail="haco_heatmap_profile_not_found")
    return _profile_response(user, profile)


@router.post("/profile/reset")
def reset_profile(req: dict[str, Any] | None = None, user=Depends(require_approved_user)):
    profile_id = str((req or {}).get("profileId") or "").strip() or None
    profile = haco_heatmap_repo.reset_profile(app_user_id=user.id, profile_uid=profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="haco_heatmap_profile_not_found")
    return _profile_response(user, profile)


@router.post("/rows")
def add_row(req: dict[str, Any], user=Depends(require_approved_user)):
    profile = _profile_for_request(user, str(req.get("profileId") or "").strip() or None)
    category_id = str(req.get("categoryId") or req.get("category_id") or "").strip()
    if not category_id:
        raise HTTPException(status_code=400, detail="categoryId_required")
    symbol = str(req.get("symbol") or req.get("providerSymbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol_required")
    updated, result = haco_heatmap_repo.add_row(
        app_user_id=user.id,
        profile_uid=profile.profile_uid,
        category_id=category_id,
        symbol=symbol,
        display_name=str(req.get("displayName") or "").strip() or None,
        provider_symbol=str(req.get("providerSymbol") or symbol).strip() or symbol,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="haco_heatmap_profile_not_found")
    if result.get("status") == "duplicate":
        raise HTTPException(status_code=409, detail=result)
    if result.get("status") == "category_not_found":
        raise HTTPException(status_code=404, detail="haco_heatmap_category_not_found")
    return {"profile": _profile_payload(updated), **result}


@router.delete("/rows/{row_id}")
def remove_row(row_id: str, profileId: str | None = None, user=Depends(require_approved_user)):  # noqa: N803
    updated, removed = haco_heatmap_repo.remove_row(app_user_id=user.id, profile_uid=profileId, row_id=row_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="haco_heatmap_profile_not_found")
    if not removed:
        raise HTTPException(status_code=404, detail="haco_heatmap_row_not_found")
    return {"deleted": True, "profile": _profile_payload(updated)}


@router.post("/refresh")
def refresh_heatmap(req: HacoHeatmapRequest, user=Depends(require_approved_user)):
    profile = _profile_for_request(user, req.profile_id)
    request_categories = req.model_dump(mode="json", by_alias=True).get("categories", [])
    requested_rows = _flatten_requested_rows(request_categories)
    if not requested_rows:
        raise HTTPException(status_code=400, detail="haco_heatmap_refresh_requires_rows")

    previous = haco_heatmap_repo.latest_snapshot(app_user_id=user.id, profile_id=profile.id, successful_only=True)
    heatmap = HacoHeatmapService(market_data_service).build_heatmap(req)
    payload = heatmap.model_dump(mode="json", by_alias=True)
    previous_payload = previous.payload if previous is not None and isinstance(previous.payload, dict) else None
    changes = compute_changes(payload, previous_payload)
    annotated_payload = annotate_rows(payload, changes)
    summaries = category_summaries(annotated_payload)
    unsupported = unsupported_summary(annotated_payload)
    status = _snapshot_status(annotated_payload)
    snapshot = haco_heatmap_repo.create_snapshot(
        app_user_id=user.id,
        profile_id=profile.id,
        status=status,
        payload=annotated_payload,
        category_summaries=summaries,
        unsupported_summary=unsupported,
        requested_categories=request_categories,
        requested_rows=requested_rows,
        previous_snapshot_id=previous.id if previous is not None else None,
        report_label=str(req.categories[0].category_label) if req.categories else None,
    )
    return {
        "heatmap": annotated_payload,
        "snapshot": _snapshot_payload(snapshot),
        "previousSnapshot": _snapshot_payload(previous),
        "changes": changes,
        "categorySummaries": summaries,
        "unsupportedSummary": unsupported,
        "categoryStatus": {str(item.get("categoryId")): item.get("status") for item in summaries},
    }


@router.get("/snapshots/latest")
def latest_snapshot(profileId: str | None = None, user=Depends(require_approved_user)):  # noqa: N803
    profile = _profile_for_request(user, profileId)
    snapshot = haco_heatmap_repo.latest_snapshot(app_user_id=user.id, profile_id=profile.id)
    previous = (
        haco_heatmap_repo.latest_snapshot(app_user_id=user.id, profile_id=profile.id, successful_only=True, before_id=snapshot.id)
        if snapshot is not None
        else None
    )
    changes = (
        compute_changes(snapshot.payload or {}, previous.payload if previous is not None and isinstance(previous.payload, dict) else None)
        if snapshot is not None and isinstance(snapshot.payload, dict)
        else {}
    )
    return {
        "profile": _profile_payload(profile),
        "snapshot": _snapshot_payload(snapshot),
        "previousSnapshot": _snapshot_payload(previous),
        "changes": changes,
        "message": (
            f"Loaded last HACO Direction snapshot from {_dt(snapshot.generated_at)}; refresh to update."
            if snapshot is not None
            else "No HACO Direction Heatmap snapshot stored yet."
        ),
    }


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str, user=Depends(require_approved_user)):
    snapshot = haco_heatmap_repo.get_snapshot(app_user_id=user.id, snapshot_uid=snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="haco_heatmap_snapshot_not_found")
    return {"snapshot": _snapshot_payload(snapshot)}


def _snapshot_for_report(user, req: dict[str, Any]):  # noqa: ANN001
    profile = _profile_for_request(user, str(req.get("profileId") or "").strip() or None)
    snapshot_id = str(req.get("snapshotId") or "").strip()
    if snapshot_id:
        snapshot = haco_heatmap_repo.get_snapshot(app_user_id=user.id, snapshot_uid=snapshot_id)
    else:
        snapshot = haco_heatmap_repo.latest_snapshot(app_user_id=user.id, profile_id=profile.id, successful_only=True)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="haco_heatmap_snapshot_not_found")
    if snapshot.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="haco_heatmap_snapshot_not_found")
    previous = haco_heatmap_repo.latest_snapshot(app_user_id=user.id, profile_id=profile.id, successful_only=True, before_id=snapshot.id)
    return profile, snapshot, previous


@router.post("/report/preview")
def report_preview(req: dict[str, Any], user=Depends(require_approved_user)):
    profile, snapshot, previous = _snapshot_for_report(user, req)
    report = build_report_payload(
        profile=_profile_payload(profile),
        snapshot=_snapshot_payload(snapshot) or {},
        previous_snapshot=_snapshot_payload(previous),
    )
    return {"report": report, "html": haco_heatmap_html(report), "emailStatus": report["email_status"]}


@router.post("/report/csv")
def report_csv(req: dict[str, Any], user=Depends(require_approved_user)):
    profile, snapshot, previous = _snapshot_for_report(user, req)
    report = build_report_payload(
        profile=_profile_payload(profile),
        snapshot=_snapshot_payload(snapshot) or {},
        previous_snapshot=_snapshot_payload(previous),
    )
    return {"csv": haco_heatmap_csv(report), "filename": "haco-direction-heatmap-report.csv"}
