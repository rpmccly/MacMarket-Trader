"""User-scoped Momentum Heatmap persistence, snapshots, and reports."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from macmarket_trader.api.deps.auth import require_approved_user
from macmarket_trader.charts.momentum_heatmap_reporting import (
    annotate_rows,
    build_report_payload,
    category_summaries,
    compute_deltas,
    heatmap_csv,
    heatmap_html,
    heatmap_text,
    unsupported_summary,
)
from macmarket_trader.charts.momentum_heatmap_service import MomentumHeatmapService
from macmarket_trader.data.providers.base import EmailMessage
from macmarket_trader.data.providers.registry import build_email_provider, build_market_data_service
from macmarket_trader.domain.schemas import MomentumHeatmapRequest
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import EmailLogRepository, MomentumHeatmapRepository

router = APIRouter(prefix="/user/momentum-heatmap", tags=["momentum-heatmap"])

heatmap_repo = MomentumHeatmapRepository(SessionLocal)
email_repo = EmailLogRepository(SessionLocal)
email_provider = build_email_provider()
market_data_service = build_market_data_service()

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _dt(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _is_default_seed(profile) -> bool:  # noqa: ANN001
    if not profile.is_default:
        return False
    from macmarket_trader.charts.momentum_heatmap_defaults import (
        DEFAULT_MOMENTUM_HEATMAP_COLOR_RANGES,
        default_momentum_heatmap_view_settings,
    )

    for category in profile.categories or []:
        if not isinstance(category, dict):
            continue
        for row in category.get("rows") or []:
            if isinstance(row, dict) and row.get("userAdded") is True:
                return False
    return (
        str(profile.name or "") == "Default Momentum Heatmap"
        and (profile.color_ranges or []) == DEFAULT_MOMENTUM_HEATMAP_COLOR_RANGES
        and (profile.view_settings or {}) == default_momentum_heatmap_view_settings()
    )


def _profile_payload(profile) -> dict[str, Any]:  # noqa: ANN001
    return {
        "id": profile.profile_uid,
        "profileId": profile.profile_uid,
        "databaseId": profile.id,
        "name": profile.name,
        "categories": profile.categories or [],
        "colorRanges": profile.color_ranges or [],
        "viewSettings": profile.view_settings or {},
        "reportPreferences": profile.report_preferences or {},
        "isDefault": bool(profile.is_default),
        "isDefaultSeed": _is_default_seed(profile),
        "createdAt": _dt(profile.created_at),
        "updatedAt": _dt(profile.updated_at),
    }


def _schedule_payload(schedule) -> dict[str, Any]:  # noqa: ANN001
    return {
        "id": schedule.schedule_uid,
        "enabled": bool(schedule.enabled),
        "timezone": schedule.timezone,
        "runTime": schedule.run_time,
        "daysOfWeek": schedule.days_of_week or [],
        "reportMode": schedule.report_mode,
        "recipients": schedule.recipients or [],
        "includeCsvAttachment": bool(schedule.include_csv_attachment),
        "includeFullTable": bool(schedule.include_full_table),
        "latestStatus": schedule.latest_status,
        "nextRunAt": _dt(schedule.next_run_at),
        "schedulerActive": False,
        "runnerHook": "python -m macmarket_trader.cli run-due-momentum-heatmap-reports",
        "payload": schedule.payload or {},
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


def _normalize_heatmap_recipients(user, raw_recipients: Any, *, allow_empty: bool) -> list[str]:  # noqa: ANN001
    if raw_recipients is None:
        raw_items: list[Any] = []
    elif isinstance(raw_recipients, list):
        raw_items = raw_recipients
    else:
        raise HTTPException(status_code=400, detail="momentum_heatmap_recipients_must_be_a_list")

    user_email = str(user.email or "").strip().lower()
    if not user_email or not EMAIL_PATTERN.fullmatch(user_email):
        if allow_empty and not raw_items:
            return []
        raise HTTPException(status_code=400, detail="momentum_heatmap_user_email_required")

    recipients: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        recipient = str(item or "").strip().lower()
        if not recipient:
            continue
        if not EMAIL_PATTERN.fullmatch(recipient):
            raise HTTPException(status_code=400, detail="momentum_heatmap_recipient_invalid")
        if recipient != user_email:
            raise HTTPException(status_code=403, detail="momentum_heatmap_recipient_not_authorized")
        if recipient not in seen:
            seen.add(recipient)
            recipients.append(recipient)

    if not recipients and not allow_empty:
        raise HTTPException(status_code=400, detail="momentum_heatmap_email_recipient_required")
    return recipients


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
            cells = [cell for cell in (row.get("scores") or {}).values() if isinstance(cell, dict)]
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
        profile = heatmap_repo.get_profile(app_user_id=user.id, profile_uid=profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="momentum_heatmap_profile_not_found")
        return profile
    return heatmap_repo.get_or_create_default_profile(app_user_id=user.id, user_email=user.email)


@router.get("/profile")
def get_profile(user=Depends(require_approved_user)):
    profile = _profile_for_request(user)
    profiles = heatmap_repo.list_profiles(app_user_id=user.id)
    schedule = heatmap_repo.get_or_create_schedule_preferences(app_user_id=user.id, profile_id=profile.id, user_email=user.email)
    return {
        "profile": _profile_payload(profile),
        "profiles": [_profile_payload(item) for item in profiles],
        "schedulePreferences": _schedule_payload(schedule),
        "source": "server",
        "localStorageMigration": {
            "supported": True,
            "symbolKey": "macmarket-momentum-heatmap-symbols-v1",
            "colorKey": "macmarket-momentum-heatmap-colors-v1",
        },
    }


@router.put("/profile")
def update_profile(req: dict[str, Any], user=Depends(require_approved_user)):
    profile_id = str(req.get("profileId") or req.get("id") or "").strip() or None
    profile = heatmap_repo.update_profile(app_user_id=user.id, profile_uid=profile_id, updates=req)
    if profile is None:
        raise HTTPException(status_code=404, detail="momentum_heatmap_profile_not_found")
    return {"profile": _profile_payload(profile), "source": "server"}


@router.post("/profile/reset")
def reset_profile(req: dict[str, Any] | None = None, user=Depends(require_approved_user)):
    profile_id = str((req or {}).get("profileId") or "").strip() or None
    profile = heatmap_repo.reset_profile(app_user_id=user.id, profile_uid=profile_id, user_email=user.email)
    if profile is None:
        raise HTTPException(status_code=404, detail="momentum_heatmap_profile_not_found")
    return {"profile": _profile_payload(profile), "source": "server"}


@router.post("/rows")
def add_row(req: dict[str, Any], user=Depends(require_approved_user)):
    profile = _profile_for_request(user, str(req.get("profileId") or "").strip() or None)
    category_id = str(req.get("categoryId") or req.get("category_id") or "").strip()
    if not category_id:
        raise HTTPException(status_code=400, detail="categoryId_required")
    symbol = str(req.get("symbol") or req.get("providerSymbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol_required")
    updated, result = heatmap_repo.add_row(
        app_user_id=user.id,
        profile_uid=profile.profile_uid,
        category_id=category_id,
        symbol=symbol,
        display_name=str(req.get("displayName") or "").strip() or None,
        provider_symbol=str(req.get("providerSymbol") or symbol).strip() or symbol,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="momentum_heatmap_profile_not_found")
    if result.get("status") == "duplicate":
        raise HTTPException(status_code=409, detail=result)
    if result.get("status") == "category_not_found":
        raise HTTPException(status_code=404, detail="momentum_heatmap_category_not_found")
    return {"profile": _profile_payload(updated), **result}


@router.delete("/rows/{row_id}")
def remove_row(row_id: str, profileId: str | None = None, user=Depends(require_approved_user)):  # noqa: N803
    updated, removed = heatmap_repo.remove_row(app_user_id=user.id, profile_uid=profileId, row_id=row_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="momentum_heatmap_profile_not_found")
    if not removed:
        raise HTTPException(status_code=404, detail="momentum_heatmap_row_not_found")
    return {"deleted": True, "profile": _profile_payload(updated)}


@router.post("/refresh")
def refresh_heatmap(req: MomentumHeatmapRequest, user=Depends(require_approved_user)):
    profile = _profile_for_request(user)
    request_categories = req.model_dump(mode="json", by_alias=True).get("categories", [])
    requested_rows = _flatten_requested_rows(request_categories)
    if not requested_rows:
        raise HTTPException(status_code=400, detail="momentum_heatmap_refresh_requires_rows")

    previous = heatmap_repo.latest_snapshot(app_user_id=user.id, profile_id=profile.id, successful_only=True)
    heatmap = MomentumHeatmapService(market_data_service).build_heatmap(req)
    payload = heatmap.model_dump(mode="json", by_alias=True)
    previous_payload = previous.payload if previous is not None and isinstance(previous.payload, dict) else None
    deltas = compute_deltas(payload, previous_payload)
    annotated_payload = annotate_rows(payload, deltas)
    summaries = category_summaries(annotated_payload, deltas)
    unsupported = unsupported_summary(annotated_payload)
    status = _snapshot_status(annotated_payload)
    snapshot = heatmap_repo.create_snapshot(
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
        "deltas": deltas,
        "categorySummaries": summaries,
        "unsupportedSummary": unsupported,
        "categoryStatus": {str(item.get("categoryId")): item.get("status") for item in summaries},
    }


@router.get("/snapshots/latest")
def latest_snapshot(user=Depends(require_approved_user)):
    profile = _profile_for_request(user)
    snapshot = heatmap_repo.latest_snapshot(app_user_id=user.id, profile_id=profile.id)
    previous = (
        heatmap_repo.latest_snapshot(app_user_id=user.id, profile_id=profile.id, successful_only=True, before_id=snapshot.id)
        if snapshot is not None
        else None
    )
    deltas = (
        compute_deltas(snapshot.payload or {}, previous.payload if previous is not None and isinstance(previous.payload, dict) else None)
        if snapshot is not None and isinstance(snapshot.payload, dict)
        else {}
    )
    return {
        "profile": _profile_payload(profile),
        "snapshot": _snapshot_payload(snapshot),
        "previousSnapshot": _snapshot_payload(previous),
        "deltas": deltas,
        "message": (
            f"Loaded last snapshot from {_dt(snapshot.generated_at)}; refresh to update."
            if snapshot is not None
            else "No Momentum Heatmap snapshot stored yet."
        ),
    }


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str, user=Depends(require_approved_user)):
    snapshot = heatmap_repo.get_snapshot(app_user_id=user.id, snapshot_uid=snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="momentum_heatmap_snapshot_not_found")
    return {"snapshot": _snapshot_payload(snapshot)}


def _snapshot_for_report(user, req: dict[str, Any]):  # noqa: ANN001
    profile = _profile_for_request(user, str(req.get("profileId") or "").strip() or None)
    snapshot_id = str(req.get("snapshotId") or "").strip()
    if snapshot_id:
        snapshot = heatmap_repo.get_snapshot(app_user_id=user.id, snapshot_uid=snapshot_id)
    else:
        snapshot = heatmap_repo.latest_snapshot(app_user_id=user.id, profile_id=profile.id, successful_only=True)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="momentum_heatmap_snapshot_not_found")
    if snapshot.profile_id != profile.id:
        raise HTTPException(status_code=404, detail="momentum_heatmap_snapshot_not_found")
    previous = heatmap_repo.latest_snapshot(app_user_id=user.id, profile_id=profile.id, successful_only=True, before_id=snapshot.id)
    return profile, snapshot, previous


@router.post("/report/preview")
def report_preview(req: dict[str, Any], user=Depends(require_approved_user)):
    profile, snapshot, previous = _snapshot_for_report(user, req)
    report = build_report_payload(
        profile=_profile_payload(profile),
        snapshot=_snapshot_payload(snapshot) or {},
        previous_snapshot=_snapshot_payload(previous),
        stale=bool(req.get("stale", False)),
    )
    return {"report": report, "html": heatmap_html(report), "emailStatus": report["email_status"]}


@router.post("/report/csv")
def report_csv(req: dict[str, Any], user=Depends(require_approved_user)):
    profile, snapshot, previous = _snapshot_for_report(user, req)
    report = build_report_payload(
        profile=_profile_payload(profile),
        snapshot=_snapshot_payload(snapshot) or {},
        previous_snapshot=_snapshot_payload(previous),
    )
    return {"csv": heatmap_csv(report), "filename": "momentum-heatmap-report.csv"}


@router.post("/report/email")
def report_email(req: dict[str, Any], user=Depends(require_approved_user)):
    recipients = _normalize_heatmap_recipients(user, req.get("recipients"), allow_empty=False)
    profile, snapshot, previous = _snapshot_for_report(user, req)
    report = build_report_payload(
        profile=_profile_payload(profile),
        snapshot=_snapshot_payload(snapshot) or {},
        previous_snapshot=_snapshot_payload(previous),
    )
    html = heatmap_html(report)
    text = heatmap_text(report)
    sent_to: list[str] = []
    for recipient in recipients:
        message_id = email_provider.send(
            EmailMessage(
                to_email=recipient,
                subject=f"MacMarket Momentum Heatmap - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                body=text,
                html=html,
                template_name="momentum_heatmap_report",
            )
        )
        email_repo.create(user.id, "momentum_heatmap_report", recipient, "sent", message_id)
        sent_to.append(recipient)
    return {"emailStatus": "sent", "sentTo": sent_to, "report": report}


@router.get("/schedule")
def get_schedule_preferences(user=Depends(require_approved_user)):
    profile = _profile_for_request(user)
    schedule = heatmap_repo.get_or_create_schedule_preferences(app_user_id=user.id, profile_id=profile.id, user_email=user.email)
    return {
        "profile": _profile_payload(profile),
        "schedulePreferences": _schedule_payload(schedule),
        "timingSuggestions": [
            {"time": "07:00", "label": "7:00 AM ET", "note": "Premarket read using prior completed session/intraday bars."},
            {"time": "10:15", "label": "10:15 AM ET", "note": "After market has enough regular-session data for 30M/1H context."},
            {"time": "15:30", "label": "3:30 PM ET", "note": "Late-session review before close."},
            {"time": "16:30", "label": "4:30 PM ET", "note": "Post-close summary."},
        ],
        "schedulerActive": False,
        "runnerHook": "python -m macmarket_trader.cli run-due-momentum-heatmap-reports",
    }


@router.put("/schedule")
def update_schedule_preferences(req: dict[str, Any], user=Depends(require_approved_user)):
    profile = _profile_for_request(user, str(req.get("profileId") or "").strip() or None)
    heatmap_repo.get_or_create_schedule_preferences(app_user_id=user.id, profile_id=profile.id, user_email=user.email)
    updates = dict(req)
    if "recipients" in updates:
        updates["recipients"] = _normalize_heatmap_recipients(user, updates.get("recipients"), allow_empty=True)
    schedule = heatmap_repo.update_schedule_preferences(app_user_id=user.id, profile_id=profile.id, updates=updates)
    if schedule is None:
        raise HTTPException(status_code=404, detail="momentum_heatmap_schedule_not_found")
    return {
        "schedulePreferences": _schedule_payload(schedule),
        "schedulerActive": False,
        "message": "Schedule preferences are saved. Wire the documented runner hook to cron or Windows Task Scheduler to execute them.",
    }
