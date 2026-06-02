from __future__ import annotations

import math
from uuid import uuid4
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select

from macmarket_trader.api.routes import admin as workflow
from macmarket_trader.config import settings
from macmarket_trader.domain.enums import ApprovalStatus, MarketMode
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import PortfolioSnapshot, TradeRecommendation
from macmarket_trader.domain.time import utc_now
from macmarket_trader.email_templates import render_agent_mode_run_digest_html
from macmarket_trader.notifications import NotificationService
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import (
    AgentModeRepository,
    NotificationAttemptRepository,
    PaperPortfolioRepository,
    RecommendationRepository,
    SymbolUniverseRepository,
    WatchlistRepository,
    display_id_or_fallback,
)


AGENT_MODE_INTENTS = [
    "HOLD",
    "CLOSE_PAPER",
    "OPEN_PAPER",
    "REPLACE_PAPER",
    "SCALE_IN_PAPER",
    "REDUCE_PAPER",
    "CASH_NO_TRADE",
]


class AgentModeService:
    """Deterministic paper-only operator loop for the Agent Mode MVP."""

    def __init__(
        self,
        *,
        agent_repo: AgentModeRepository | None = None,
        paper_repo: PaperPortfolioRepository | None = None,
        recommendation_repo: RecommendationRepository | None = None,
        symbol_universe_repo: SymbolUniverseRepository | None = None,
        watchlist_repo: WatchlistRepository | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.agent_repo = agent_repo or AgentModeRepository(SessionLocal)
        self.paper_repo = paper_repo or PaperPortfolioRepository(SessionLocal)
        self.recommendation_repo = recommendation_repo or RecommendationRepository(SessionLocal)
        self.symbol_universe_repo = symbol_universe_repo or SymbolUniverseRepository(SessionLocal)
        self.watchlist_repo = watchlist_repo or WatchlistRepository(SessionLocal)
        self.notification_service = notification_service or NotificationService(
            repo=NotificationAttemptRepository(SessionLocal),
        )

    @staticmethod
    def serialize_settings(row) -> dict[str, object]:
        return {
            "enabled": bool(row.enabled),
            "paused": bool(row.paused),
            "kill_switch_enabled": bool(row.kill_switch_enabled),
            "daily_run_time": row.daily_run_time,
            "timezone": row.timezone,
            "universe_source": row.universe_source,
            "manual_symbols": list(row.manual_symbols or []),
            "watchlist_ids": list(row.watchlist_ids or []),
            "default_watchlist_id": getattr(row, "default_watchlist_id", None),
            "max_positions": int(row.max_positions or 5),
            "scan_depth": int(row.scan_depth or 12),
            "max_dollars_per_trade": AgentModeService._round_money(getattr(row, "max_dollars_per_trade", None)),
            "max_percent_of_paper_account_per_trade": getattr(row, "max_percent_of_paper_account_per_trade", None),
            "max_new_trades_per_run": 5 if getattr(row, "max_new_trades_per_run", None) is None else int(getattr(row, "max_new_trades_per_run")),
            "max_new_trades_per_day": 5 if getattr(row, "max_new_trades_per_day", None) is None else int(getattr(row, "max_new_trades_per_day")),
            "max_open_agent_positions": int(getattr(row, "max_open_agent_positions", row.max_positions or 5) or 5),
            "max_exposure_per_symbol": AgentModeService._round_money(getattr(row, "max_exposure_per_symbol", None)),
            "min_cash_reserve": AgentModeService._round_money(getattr(row, "min_cash_reserve", 0.0)) or 0.0,
            "allow_opens": bool(row.allow_opens),
            "allow_closes": bool(row.allow_closes),
            "allow_scale_resize": bool(row.allow_scale_resize),
            "allow_scale_ins": bool(getattr(row, "allow_scale_ins", False)),
            "allow_new_trade_when_symbol_already_open": bool(getattr(row, "allow_new_trade_when_symbol_already_open", False)),
            "require_confirmation_for_restricted": bool(getattr(row, "require_confirmation_for_restricted", True)),
            "notification_preference": str(getattr(row, "notification_preference", "none") or "none"),
            "notification_phone_number": getattr(row, "notification_phone_number", None),
            "sms_consent_confirmed": bool(getattr(row, "sms_consent_confirmed", False)),
            "email_notifications_enabled": bool(getattr(row, "email_notifications_enabled", False)),
            "sms_notifications_enabled": bool(getattr(row, "sms_notifications_enabled", False)),
            "sms_provider_status": NotificationService.sms_readiness(),
            "paper_only": True,
            "execution_mode": "paper",
        }

    @staticmethod
    def serialize_run(row) -> dict[str, object]:
        return {
            "runId": row.run_id,
            "status": row.status,
            "executionMode": row.execution_mode,
            "dryRun": bool(row.dry_run),
            "intentCount": int(row.intent_count or 0),
            "executedOrderCount": int(row.executed_order_count or 0),
            "createdAt": row.created_at.isoformat() if row.created_at else None,
            "completedAt": row.completed_at.isoformat() if row.completed_at else None,
            "request": row.request_json or {},
            "result": row.response_json or {},
        }

    @staticmethod
    def _coerce_bool(value: object, *, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _user_is_approved(user: object) -> bool:
        approval_status = getattr(user, "approval_status", None)
        approval_value = getattr(approval_status, "value", approval_status)
        return str(approval_value) == ApprovalStatus.APPROVED.value

    @staticmethod
    def _coerce_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value) if value is not None and value != "" else default
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _coerce_optional_float(
        value: object,
        *,
        minimum: float,
        maximum: float,
        field_name: str,
    ) -> float | None:
        if value is None or value == "":
            return None
        try:
            parsed = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{field_name} must be numeric.") from exc
        if not math.isfinite(parsed) or parsed < minimum or parsed > maximum:
            raise HTTPException(status_code=400, detail=f"{field_name} must be between {minimum} and {maximum}.")
        return parsed

    def normalize_settings_update(self, payload: dict[str, object]) -> dict[str, object]:
        updates: dict[str, object] = {}
        for key in (
            "enabled",
            "paused",
            "kill_switch_enabled",
            "allow_opens",
            "allow_closes",
            "allow_scale_resize",
            "allow_scale_ins",
            "allow_new_trade_when_symbol_already_open",
            "require_confirmation_for_restricted",
            "sms_consent_confirmed",
            "email_notifications_enabled",
            "sms_notifications_enabled",
        ):
            if key in payload:
                updates[key] = self._coerce_bool(payload.get(key), default=False)
        if "daily_run_time" in payload:
            run_time = str(payload.get("daily_run_time") or "15:45").strip()
            if not run_time or len(run_time) > 8:
                raise HTTPException(status_code=400, detail="daily_run_time must be a short HH:MM value.")
            updates["daily_run_time"] = run_time
        if "timezone" in payload:
            updates["timezone"] = str(payload.get("timezone") or "America/New_York").strip()[:64]
        if "universe_source" in payload:
            source = str(payload.get("universe_source") or "manual").strip().lower()
            if source not in {"manual", "watchlist", "watchlist_plus_manual", "all_active"}:
                raise HTTPException(status_code=400, detail="unsupported_agent_universe_source")
            updates["universe_source"] = source
        if "manual_symbols" in payload:
            updates["manual_symbols"] = workflow.normalize_symbol_list(
                payload.get("manual_symbols") or [],
                max_items=25,
                field_name="manual_symbols",
            )
        if "watchlist_ids" in payload:
            raw_ids = payload.get("watchlist_ids") or []
            if not isinstance(raw_ids, list):
                raise HTTPException(status_code=400, detail="watchlist_ids must be a list.")
            updates["watchlist_ids"] = [int(item) for item in raw_ids if str(item).strip().isdigit()][:10]
        if "default_watchlist_id" in payload:
            raw_default = payload.get("default_watchlist_id")
            updates["default_watchlist_id"] = int(raw_default) if str(raw_default or "").strip().isdigit() else None
        if "max_positions" in payload:
            # MVP fixed cap: never allow above 5 even if the payload asks.
            updates["max_positions"] = self._coerce_int(payload.get("max_positions"), default=5, minimum=1, maximum=5)
        if "scan_depth" in payload:
            updates["scan_depth"] = self._coerce_int(payload.get("scan_depth"), default=12, minimum=1, maximum=25)
        for key in ("max_new_trades_per_run", "max_new_trades_per_day", "max_open_agent_positions"):
            if key in payload:
                updates[key] = self._coerce_int(payload.get(key), default=5, minimum=0, maximum=5)
        for key, maximum in (
            ("max_dollars_per_trade", 1_000_000.0),
            ("max_exposure_per_symbol", 1_000_000.0),
            ("min_cash_reserve", 1_000_000.0),
        ):
            if key in payload:
                parsed = self._coerce_optional_float(
                    payload.get(key),
                    minimum=0.0,
                    maximum=maximum,
                    field_name=key,
                )
                updates[key] = 0.0 if key == "min_cash_reserve" and parsed is None else parsed
        if "max_percent_of_paper_account_per_trade" in payload:
            parsed = self._coerce_optional_float(
                payload.get("max_percent_of_paper_account_per_trade"),
                minimum=0.0,
                maximum=100.0,
                field_name="max_percent_of_paper_account_per_trade",
            )
            updates["max_percent_of_paper_account_per_trade"] = parsed
        if "notification_preference" in payload:
            preference = str(payload.get("notification_preference") or "none").strip().lower()
            if preference not in {"none", "email", "sms", "both"}:
                raise HTTPException(status_code=400, detail="unsupported_notification_preference")
            updates["notification_preference"] = preference
            updates["email_notifications_enabled"] = preference in {"email", "both"}
            updates["sms_notifications_enabled"] = preference in {"sms", "both"}
        if "notification_phone_number" in payload:
            phone = str(payload.get("notification_phone_number") or "").strip()
            updates["notification_phone_number"] = phone[:32] or None
        return updates

    def update_settings(self, *, user, payload: dict[str, object]) -> dict[str, object]:
        mode = str(payload.get("mode") or payload.get("execution_mode") or "paper").strip().lower()
        if mode not in {"paper", "paper_only"}:
            raise HTTPException(status_code=409, detail="Agent Mode only supports paper mode.")
        updates = self.normalize_settings_update(payload)
        default_watchlist_id = updates.get("default_watchlist_id")
        if default_watchlist_id is not None:
            row = self.watchlist_repo.get_for_user(watchlist_id=int(default_watchlist_id), app_user_id=user.id)
            if row is None:
                raise HTTPException(status_code=404, detail="default_watchlist_id not found for user")
        row = self.agent_repo.update_settings(app_user_id=user.id, updates=updates)
        return self.serialize_settings(row)

    def resolve_universe(self, *, app_user_id: int, settings_payload: dict[str, object], overrides: dict[str, object]) -> dict[str, object]:
        explicit_source = overrides.get("universe_source") or overrides.get("source")
        source = str(explicit_source or settings_payload.get("universe_source") or "manual").strip().lower()
        if source not in {"manual", "watchlist", "watchlist_plus_manual", "all_active"}:
            source = "manual"
        manual_override = source == "manual" or bool(overrides.get("manual_override"))
        if "manual_symbols" in overrides:
            manual_symbols = overrides.get("manual_symbols")
        elif "symbols" in overrides and manual_override:
            manual_symbols = overrides.get("symbols")
        else:
            manual_symbols = settings_payload.get("manual_symbols") or ["SPY", "QQQ", "MTUM"]
        manual_list = workflow.normalize_symbol_list(manual_symbols, max_items=25, field_name="symbols")
        watchlist_ids = overrides.get("watchlist_ids") if "watchlist_ids" in overrides else settings_payload.get("watchlist_ids") or []
        if not isinstance(watchlist_ids, list):
            watchlist_ids = []
        default_watchlist_id = overrides.get("default_watchlist_id") if "default_watchlist_id" in overrides else settings_payload.get("default_watchlist_id")
        if not watchlist_ids and default_watchlist_id and source in {"watchlist", "watchlist_plus_manual"}:
            watchlist_ids = [default_watchlist_id]
        cleaned_watchlist_ids: list[int] = []
        for item in watchlist_ids:
            if str(item).isdigit():
                parsed = int(item)
                if parsed not in cleaned_watchlist_ids:
                    cleaned_watchlist_ids.append(parsed)
        selected_watchlists = [
            row
            for watchlist_id in cleaned_watchlist_ids
            for row in [self.watchlist_repo.get_for_user(watchlist_id=watchlist_id, app_user_id=app_user_id)]
            if row is not None
        ]
        missing_watchlist_ids = [
            watchlist_id
            for watchlist_id in cleaned_watchlist_ids
            if all(row.id != watchlist_id for row in selected_watchlists)
        ]
        watchlist_symbol_count = sum(len(row.symbols or []) for row in selected_watchlists)
        source_status = "ok"
        source_reason: str | None = None
        if source in {"watchlist", "watchlist_plus_manual"}:
            if not cleaned_watchlist_ids:
                source_status = "missing"
                source_reason = "watchlist_missing_or_empty"
            elif missing_watchlist_ids and not selected_watchlists:
                source_status = "missing"
                source_reason = "watchlist_missing_or_unavailable"
            elif watchlist_symbol_count == 0:
                source_status = "empty"
                source_reason = "watchlist_missing_or_empty"
        include_all_active = source == "all_active"
        if source == "manual":
            cleaned_watchlist_ids = []
            include_all_active = False
        resolution = self.symbol_universe_repo.resolve_symbols(
            app_user_id=app_user_id,
            manual_symbols=manual_list if source in {"manual", "watchlist_plus_manual", "all_active"} else [],
            watchlist_ids=cleaned_watchlist_ids,
            include_all_active=include_all_active,
            include_inactive=False,
            exclusions=[],
            pinned_symbols=[],
        )
        symbols = resolution.symbols or ([] if source in {"watchlist", "watchlist_plus_manual"} else manual_list)
        if source == "watchlist" and source_status != "ok":
            symbols = []
        scan_depth = self._coerce_int(overrides.get("scan_depth") or settings_payload.get("scan_depth"), default=12, minimum=1, maximum=25)
        resolved_symbols = symbols[:scan_depth]
        watchlist_names = [row.name for row in selected_watchlists]
        return {
            "symbols": resolved_symbols,
            "source": source,
            "source_label": source.replace("_", " "),
            "scan_depth": scan_depth,
            "watchlist_ids": cleaned_watchlist_ids,
            "watchlist_id": cleaned_watchlist_ids[0] if cleaned_watchlist_ids else None,
            "watchlist_name": ", ".join(watchlist_names) if watchlist_names else None,
            "watchlist_names": watchlist_names,
            "resolved_symbols_snapshot": resolved_symbols,
            "manual_override": manual_override,
            "manual_symbols": manual_list if source in {"manual", "watchlist_plus_manual", "all_active"} else [],
            "source_status": source_status,
            "reason": source_reason,
            "missing_watchlist_ids": missing_watchlist_ids,
            "provenance": resolution.provenance,
        }

    @staticmethod
    def _safe_float(value: object) -> float | None:
        try:
            parsed = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

    @classmethod
    def _round_money(cls, value: object) -> float | None:
        parsed = cls._safe_float(value)
        return round(parsed, 2) if parsed is not None else None

    @classmethod
    def _round_price(cls, value: object) -> float | None:
        parsed = cls._safe_float(value)
        return round(parsed, 4) if parsed is not None else None

    @classmethod
    def _round_qty(cls, value: object) -> float | None:
        parsed = cls._safe_float(value)
        return round(parsed, 4) if parsed is not None else None

    @staticmethod
    def _iso(value: object) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        return None

    @staticmethod
    def _coerce_limit(value: object, *, default: int, maximum: int) -> int:
        try:
            parsed = int(value) if value is not None and value != "" else default
        except (TypeError, ValueError):
            parsed = default
        return max(1, min(parsed, maximum))

    @staticmethod
    def _parse_run_time(value: object) -> tuple[int, int]:
        parts = str(value or "15:45").split(":", 1)
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except (TypeError, ValueError):
            hour, minute = 15, 45
        return max(0, min(23, hour)), max(0, min(59, minute))

    def _next_run_at(
        self,
        *,
        settings_payload: dict[str, object],
        latest_row,
        now: datetime,
    ) -> datetime | None:
        if not bool(settings_payload.get("enabled")) or bool(settings_payload.get("paused")) or bool(settings_payload.get("kill_switch_enabled")):
            return None
        zone = self._setting_zone(str(settings_payload.get("timezone") or "America/New_York"))
        local_now = now.astimezone(zone)
        hour, minute = self._parse_run_time(settings_payload.get("daily_run_time"))
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        latest_local_date: date | None = None
        if latest_row and latest_row.created_at:
            latest_at = latest_row.created_at if latest_row.created_at.tzinfo else latest_row.created_at.replace(tzinfo=timezone.utc)
            latest_local_date = latest_at.astimezone(zone).date()
        if candidate <= local_now or latest_local_date == local_now.date():
            candidate = candidate + timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    def schedule_status(self, *, user) -> dict[str, object]:
        row = self.agent_repo.get_or_create_settings(app_user_id=user.id)
        settings_payload = self.serialize_settings(row)
        latest = self.agent_repo.latest_run(app_user_id=user.id)
        now = utc_now()
        next_run = self._next_run_at(settings_payload=settings_payload, latest_row=latest, now=now)
        latest_payload = self._run_response(latest) if latest else {}
        summary = latest_payload.get("summary") if isinstance(latest_payload.get("summary"), dict) else {}
        status = "never_run"
        if not bool(settings_payload.get("enabled")):
            status = "disabled"
        if latest is not None:
            status = "running" if latest.status == "running" else "failed" if latest.status in {"error", "failed"} else "success" if latest.status == "completed" else str(latest.status)
        last_skip_reason = None
        if bool(settings_payload.get("paused")):
            last_skip_reason = "agent_paused"
        elif bool(settings_payload.get("kill_switch_enabled")):
            last_skip_reason = "kill_switch_enabled"
        elif not bool(settings_payload.get("enabled")):
            last_skip_reason = "agent_disabled"
        elif isinstance(summary, dict):
            last_skip_reason = summary.get("skipReason")
        warnings = list(latest_payload.get("warnings") or []) if isinstance(latest_payload, dict) else []
        return {
            "agent_enabled": bool(settings_payload.get("enabled")) and not bool(settings_payload.get("paused")) and not bool(settings_payload.get("kill_switch_enabled")),
            "configured_timezone": settings_payload.get("timezone"),
            "configured_daily_run_time": settings_payload.get("daily_run_time"),
            "current_server_time": now.isoformat(),
            "current_server_timezone": "UTC",
            "next_scheduled_run_at": next_run.isoformat() if next_run else None,
            "seconds_until_next_run": int(max(0.0, (next_run - now).total_seconds())) if next_run else None,
            "last_run_started_at": latest.created_at.isoformat() if latest and latest.created_at else None,
            "last_run_completed_at": latest.completed_at.isoformat() if latest and latest.completed_at else None,
            "last_run_status": status,
            "last_skip_reason": last_skip_reason,
            "last_error_summary": (warnings[0] if warnings else None) if status != "success" else None,
            "last_run_id": latest.run_id if latest else None,
            "last_run_trade_count": int(summary.get("totalExecutedActions", summary.get("executedOrderCount", 0)) or 0) if isinstance(summary, dict) else 0,
            "last_run_position_review_count": len(latest_payload.get("positionReviews") or []) if isinstance(latest_payload, dict) else 0,
            "last_run_blocked_count": int(summary.get("blockedActions", 0) or 0) if isinstance(summary, dict) else 0,
            "in_progress": status == "running",
            "lock_diagnostics": {"available": False, "reason": "scheduler_lock_not_persisted"},
            "scheduler_source": "backend-owned",
            "paperOnly": True,
            "executionMode": "paper",
        }

    @classmethod
    def _intent_execution_metrics(
        cls,
        final_intents: list[dict[str, object]],
        *,
        positions_before_count: int,
        positions_after_count: int,
    ) -> dict[str, object]:
        paper_opens = [
            intent for intent in final_intents
            if intent.get("intent") == "OPEN_PAPER" and intent.get("status") == "executed"
        ]
        paper_closes = [
            intent for intent in final_intents
            if intent.get("intent") == "CLOSE_PAPER" and intent.get("status") == "executed"
        ]
        blocked_actions = [
            intent for intent in final_intents
            if intent.get("intent") != "CASH_NO_TRADE" and intent.get("status") in {"blocked", "skipped", "review_only"}
        ]
        linked_order_ids = sorted(
            {
                str(intent.get("order_id"))
                for intent in final_intents
                if intent.get("order_id") not in {None, ""}
            }
        )
        linked_position_ids = sorted(
            {
                int(intent.get("position_id"))
                for intent in final_intents
                if str(intent.get("position_id") or "").strip().isdigit()
            }
        )
        linked_trade_ids = sorted(
            {
                int(intent.get("trade_id"))
                for intent in final_intents
                if str(intent.get("trade_id") or "").strip().isdigit()
            }
        )
        realized_from_closes = sum(
            cls._safe_float(intent.get("net_pnl") if intent.get("net_pnl") is not None else intent.get("realized_pnl")) or 0.0
            for intent in paper_closes
        )
        return {
            "positionsBeforeCount": positions_before_count,
            "positionsAfterCount": positions_after_count,
            "paperOpensExecuted": len(paper_opens),
            "paperClosesExecuted": len(paper_closes),
            "holds": sum(1 for intent in final_intents if intent.get("intent") == "HOLD"),
            "blockedActions": len(blocked_actions),
            "cashNoTrade": sum(1 for intent in final_intents if intent.get("intent") == "CASH_NO_TRADE"),
            "totalExecutedActions": len(paper_opens) + len(paper_closes),
            "realizedPnlFromClosedPositions": cls._round_money(realized_from_closes),
            "linkedPaperOrderIds": linked_order_ids,
            "linkedPositionIds": linked_position_ids,
            "linkedTradeIds": linked_trade_ids,
        }

    @classmethod
    def _sum_money(cls, rows: list[dict[str, object]], key: str) -> float | None:
        total = 0.0
        seen = False
        for row in rows:
            parsed = cls._safe_float(row.get(key))
            if parsed is None:
                continue
            total += parsed
            seen = True
        return cls._round_money(total) if seen else None

    @classmethod
    def _digest_item(cls, intent: dict[str, object]) -> dict[str, object]:
        candidate = intent.get("candidate") if isinstance(intent.get("candidate"), dict) else {}
        risk_calendar = candidate.get("risk_calendar") if isinstance(candidate.get("risk_calendar"), dict) else {}
        risk_decision = risk_calendar.get("decision") if isinstance(risk_calendar.get("decision"), dict) else {}
        risk_status = risk_decision.get("status") or risk_decision.get("risk_level") or risk_calendar.get("status")
        qty = intent.get("shares") if intent.get("shares") is not None else intent.get("qty")
        notional = (
            intent.get("estimated_notional")
            if intent.get("estimated_notional") is not None
            else intent.get("notional")
        )
        return {
            "symbol": intent.get("symbol"),
            "action": cls._format_intent_label(str(intent.get("intent") or "")),
            "side": intent.get("side"),
            "strategy": candidate.get("strategy") or intent.get("strategy") or "Agent Mode",
            "risk_status": risk_status or "-",
            "quantity": cls._round_qty(qty),
            "notional": cls._round_money(notional),
            "reason": intent.get("reason") or intent.get("execution_error") or intent.get("summary"),
            "summary": intent.get("summary"),
            "status": intent.get("status"),
        }

    @staticmethod
    def _format_intent_label(intent: str) -> str:
        return {
            "OPEN_PAPER": "paper open",
            "CLOSE_PAPER": "paper close",
            "REPLACE_PAPER": "replace paper position",
            "SCALE_IN_PAPER": "scale-in paper review",
            "REDUCE_PAPER": "reduce paper review",
            "CASH_NO_TRADE": "cash/no trade",
            "HOLD": "hold",
        }.get(intent, intent.replace("_", " ").lower())

    @staticmethod
    def _digest_status(*, summary: dict[str, object], final_intents: list[dict[str, object]]) -> tuple[str, str]:
        if summary.get("skipReason"):
            return "agent_run_skipped", "skipped"
        if summary.get("dryRun"):
            return "agent_run_completed", "dry-run"
        if any(intent.get("status") == "failed" for intent in final_intents):
            return "agent_run_failed", "failed"
        if int(summary.get("paperOpensExecuted") or 0) or int(summary.get("paperClosesExecuted") or 0):
            return "agent_run_completed", "paper-created"
        return "agent_run_completed", "completed"

    def _build_run_notification_digest(
        self,
        *,
        run_id: str,
        response: dict[str, object],
        final_intents: list[dict[str, object]],
        candidates: list[dict[str, object]],
        universe: dict[str, object],
    ) -> dict[str, object]:
        summary = response.get("summary") if isinstance(response.get("summary"), dict) else {}
        event_type, status_label = self._digest_status(summary=summary, final_intents=final_intents)
        opened = [self._digest_item(intent) for intent in final_intents if intent.get("intent") == "OPEN_PAPER"]
        closed = [self._digest_item(intent) for intent in final_intents if intent.get("intent") == "CLOSE_PAPER"]
        held = [
            self._digest_item(intent)
            for intent in final_intents
            if intent.get("intent") in {"HOLD", "REPLACE_PAPER", "SCALE_IN_PAPER", "REDUCE_PAPER"}
        ]
        blocked = [
            self._digest_item(intent)
            for intent in final_intents
            if intent.get("intent") == "CASH_NO_TRADE" or intent.get("status") in {"blocked", "skipped"}
        ]
        digest_summary = {
            **summary,
            "candidateCount": len(candidates),
        }
        link = f"{settings.app_base_url.rstrip('/')}/agent-mode?tab=Trades"
        watchlist_name = str(universe.get("watchlist_name") or universe.get("source_label") or "manual symbols")
        notable = [
            str(item.get("symbol") or "").upper()
            for item in opened + closed + blocked
            if str(item.get("symbol") or "").strip()
        ][:3]
        sms = (
            f"MacMarket Agent {status_label}: opened {summary.get('paperOpensExecuted', 0)}, "
            f"closed {summary.get('paperClosesExecuted', 0)}, blocked {summary.get('blockedActions', 0)}."
        )
        if notable:
            sms += f" Notable: {', '.join(notable)}."
        sms += f" {link}"
        if len(sms) > 320:
            sms = sms[:282].rstrip() + " See Agent Mode for details."
        text_lines = [
            "MacMarket Trader - Agent Mode Run Summary",
            f"Run: {run_id}",
            f"Status: {status_label}",
            f"Timestamp: {response.get('asOf')}",
            f"Watchlist: {watchlist_name}",
            f"Candidates reviewed: {len(candidates)}",
            f"Positions reviewed: {summary.get('positionsBeforeCount', 0)}",
            f"Opened: {summary.get('paperOpensExecuted', 0)}",
            f"Closed: {summary.get('paperClosesExecuted', 0)}",
            f"Held/reviewed: {summary.get('holds', 0)}",
            f"Blocked/skipped: {summary.get('blockedActions', 0)}",
            f"Open Agent Mode: {link}",
            "",
            "Paper only. No live trading. No broker routing.",
        ]
        html = render_agent_mode_run_digest_html(
            status=status_label,
            run_id=run_id,
            ran_at=str(response.get("asOf") or utc_now().isoformat()),
            watchlist_name=watchlist_name,
            summary=digest_summary,
            opened=opened,
            closed=closed,
            held=held,
            blocked=blocked,
            app_url=settings.app_base_url,
        )
        return {
            "event_type": event_type,
            "status": status_label,
            "title": f"MacMarket Agent Mode {status_label} summary",
            "text": "\n".join(text_lines),
            "sms": sms,
            "html": html,
            "payload": {
                "paperOnly": True,
                "executionMode": "paper",
                "digest": True,
                "runId": run_id,
                "status": status_label,
                "watchlistId": universe.get("watchlist_id"),
                "watchlistName": universe.get("watchlist_name"),
                "resolvedSymbolsSnapshot": universe.get("resolved_symbols_snapshot") or universe.get("symbols"),
                "counts": {
                    "candidatesReviewed": len(candidates),
                    "positionsReviewed": summary.get("positionsBeforeCount", 0),
                    "opened": summary.get("paperOpensExecuted", 0),
                    "closed": summary.get("paperClosesExecuted", 0),
                    "held": summary.get("holds", 0),
                    "blocked": summary.get("blockedActions", 0),
                    "cashNoTrade": summary.get("cashNoTrade", 0),
                },
            },
        }

    @staticmethod
    def _effective_paper_account_basis(*, user, settings_payload: dict[str, object]) -> float | None:
        try:
            max_notional = workflow._effective_paper_max_order_notional(user)
        except Exception:  # noqa: BLE001 - missing paper cap is handled as sizing-unavailable.
            return None
        max_positions = AgentModeService._coerce_int(
            settings_payload.get("max_open_agent_positions") or settings_payload.get("max_positions"),
            default=5,
            minimum=1,
            maximum=5,
        )
        basis = float(max_notional) * max_positions
        return basis if math.isfinite(basis) and basis > 0 else None

    @classmethod
    def _current_open_notional(cls, rows: list[object]) -> float:
        total = 0.0
        for row in rows:
            parsed = cls._safe_float(getattr(row, "open_notional", None))
            if parsed is not None:
                total += parsed
        return total

    @classmethod
    def _normalized_percent(cls, value: object) -> float | None:
        parsed = cls._safe_float(value)
        if parsed is None or parsed <= 0:
            return None
        return parsed / 100.0 if parsed > 1 else parsed

    def _apply_agent_sizing_caps(
        self,
        *,
        sizing_plan: dict[str, object],
        settings_payload: dict[str, object],
        user,
        open_positions: list[object],
    ) -> dict[str, object]:
        final_shares = int(sizing_plan.get("final_order_shares") or 0)
        estimated_notional = self._safe_float(sizing_plan.get("estimated_notional"))
        if final_shares <= 0 or estimated_notional is None or estimated_notional <= 0:
            return {
                **sizing_plan,
                "agent_sizing_status": "blocked",
                "agent_sizing_block_reason": "sizing_unavailable",
                "final_order_shares": 0,
            }
        limit_price = estimated_notional / final_shares
        caps: list[tuple[str, float]] = [("paper_max_order_notional", estimated_notional)]
        dollars_cap = self._safe_float(settings_payload.get("max_dollars_per_trade"))
        if dollars_cap is not None and dollars_cap > 0:
            caps.append(("max_dollars_per_trade", dollars_cap))
        exposure_cap = self._safe_float(settings_payload.get("max_exposure_per_symbol"))
        if exposure_cap is not None and exposure_cap > 0:
            caps.append(("max_exposure_per_symbol", exposure_cap))
        percent = self._normalized_percent(settings_payload.get("max_percent_of_paper_account_per_trade"))
        basis = self._effective_paper_account_basis(user=user, settings_payload=settings_payload)
        if percent is not None:
            if basis is None:
                return {
                    **sizing_plan,
                    "agent_sizing_status": "blocked",
                    "agent_sizing_block_reason": "paper_account_basis_unavailable",
                    "final_order_shares": 0,
                }
            caps.append(("max_percent_of_paper_account_per_trade", basis * percent))
        min_reserve = self._safe_float(settings_payload.get("min_cash_reserve")) or 0.0
        if min_reserve > 0:
            if basis is None:
                return {
                    **sizing_plan,
                    "agent_sizing_status": "blocked",
                    "agent_sizing_block_reason": "paper_account_basis_unavailable",
                    "final_order_shares": 0,
                }
            available_after_reserve = basis - min_reserve - self._current_open_notional(open_positions)
            caps.append(("min_cash_reserve", max(0.0, available_after_reserve)))
        reason, effective_cap = min(caps, key=lambda item: item[1])
        capped_shares = max(0, math.floor(effective_cap / limit_price))
        if capped_shares <= 0:
            return {
                **sizing_plan,
                "agent_sizing_status": "blocked",
                "agent_sizing_block_reason": reason,
                "agent_effective_notional_cap": self._round_money(effective_cap),
                "final_order_shares": 0,
            }
        final = min(final_shares, capped_shares)
        return {
            **sizing_plan,
            "agent_sizing_status": "ok",
            "agent_sizing_block_reason": None,
            "agent_effective_notional_cap": self._round_money(effective_cap),
            "agent_effective_cap_reason": reason,
            "agent_paper_account_basis": self._round_money(basis),
            "agent_sizing_reduced": final < final_shares,
            "final_order_shares": final,
            "estimated_notional": self._round_money(final * limit_price),
        }

    def _paper_opens_today(self, *, app_user_id: int, timezone_name: str, now: datetime) -> int:
        zone = self._setting_zone(timezone_name)
        local_today = now.astimezone(zone).date()
        count = 0
        for row in self.agent_repo.list_runs(app_user_id=app_user_id, limit=100, dry_run=False):
            created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
            if created.astimezone(zone).date() != local_today:
                continue
            payload = self._run_response(row)
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            count += int(summary.get("paperOpensExecuted", 0) or 0)
        return count

    def _position_intent(self, review: dict[str, object], *, settings_payload: dict[str, object], dry_run: bool) -> dict[str, object]:
        action = str(review.get("action_classification") or "review_unavailable")
        allow_closes = bool(settings_payload.get("allow_closes", True))
        allow_scale = bool(settings_payload.get("allow_scale_resize", False))
        close_actions = {"stop_triggered", "invalidated", "time_stop_exit", "target_reached_take_profit"}
        if action in close_actions and allow_closes:
            intent = "CLOSE_PAPER"
        elif action == "scale_in_candidate" and allow_scale:
            intent = "SCALE_IN_PAPER"
        else:
            intent = "HOLD"
        return {
            "intent": intent,
            "symbol": review.get("symbol"),
            "side": review.get("side"),
            "position_id": review.get("position_id"),
            "status": "dry_run" if dry_run else "pending",
            "reason": action,
            "summary": review.get("action_summary"),
            "paper_only": True,
            "no_live_routing": True,
            "review": review,
            "warnings": list(review.get("warnings") or []),
            "missing_data": list(review.get("missing_data") or []),
        }

    def _cash_intent(self, *, symbol: str | None, reason: str, summary: str, candidate: dict[str, object] | None = None) -> dict[str, object]:
        return {
            "intent": "CASH_NO_TRADE",
            "symbol": symbol,
            "status": "blocked",
            "reason": reason,
            "summary": summary,
            "candidate": candidate,
            "paper_only": True,
            "no_live_routing": True,
        }

    def _execute_close(self, *, intent: dict[str, object], user) -> dict[str, object]:
        position_id = int(intent["position_id"])
        position = self.paper_repo.get_position_by_id(position_id=position_id)
        if position is None or position.app_user_id != user.id or position.status == "closed":
            return {**intent, "status": "skipped", "execution_error": "position_not_open"}
        review = dict(intent.get("review") or {})
        mark = self._safe_float(review.get("current_mark_price"))
        if mark is None or mark <= 0:
            return {**intent, "status": "skipped", "execution_error": "current_mark_unavailable"}
        remaining = float(position.remaining_qty if position.remaining_qty is not None else position.quantity)
        avg_entry = float(position.average_price)
        gross_pnl, net_pnl = workflow._equity_trade_pnl(
            entry_price=avg_entry,
            exit_price=mark,
            quantity=remaining,
            side=position.side,
            commission_per_trade=workflow._effective_commission_per_trade(user),
        )
        now = utc_now()
        opened_at = position.opened_at or now
        opened_aware = opened_at if opened_at.tzinfo is not None else opened_at.replace(tzinfo=timezone.utc)
        trade = self.paper_repo.create_trade(
            app_user_id=user.id,
            symbol=position.symbol,
            side=position.side,
            entry_price=avg_entry,
            exit_price=mark,
            quantity=remaining,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            realized_pnl=net_pnl,
            opened_at=opened_at,
            closed_at=now,
            position_id=position.id,
            hold_seconds=int(max(0.0, (now - opened_aware).total_seconds())),
            recommendation_id=position.recommendation_id,
            replay_run_id=position.replay_run_id,
            order_id=position.order_id,
            close_reason=f"agent_mode:{intent.get('reason')}",
        )
        self.paper_repo.close_position(position_id=position.id, closed_at=now)
        return {
            **intent,
            "status": "executed",
            "trade_id": trade.id,
            "summary": "paper close executed by Agent Mode paper lifecycle.",
            "mark_price": round(mark, 2),
            "gross_pnl": round(gross_pnl, 2),
            "net_pnl": round(net_pnl, 2),
            "realized_pnl": round(net_pnl, 2),
        }

    def _execute_open(
        self,
        *,
        intent: dict[str, object],
        candidate: dict[str, object],
        user,
        bars_by_symbol: dict[str, tuple[list[Any], str, bool]],
        timeframe: str,
        settings_payload: dict[str, object],
        open_positions: list[object],
    ) -> dict[str, object]:
        symbol = str(candidate.get("symbol") or "").upper()
        bars_tuple = bars_by_symbol.get(symbol)
        if not bars_tuple:
            return {**intent, "status": "skipped", "execution_error": "bars_unavailable"}
        bars, source, fallback_mode = bars_tuple
        approval_status = getattr(user.approval_status, "value", user.approval_status)
        user_is_approved = str(approval_status) == ApprovalStatus.APPROVED.value
        rec = workflow.recommendation_service.generate(
            symbol=symbol,
            bars=bars,
            event_text=f"Agent Mode deterministic paper open candidate: {candidate.get('strategy') or 'ranked queue'}",
            event=None,
            portfolio=PortfolioSnapshot(),
            market_mode=MarketMode.EQUITIES,
            user_is_approved=user_is_approved,
            app_user_id=user.id,
            risk_dollars=workflow._effective_risk_dollars(user),
            timeframe=timeframe,
            index_context=workflow._current_index_context_for_risk(),
        )
        if not rec.approved:
            return {**intent, "status": "skipped", "execution_error": rec.rejection_reason or "recommendation_no_trade"}
        workflow.recommendation_repo.attach_workflow_metadata(
            rec.recommendation_id,
            market_data_source=source,
            fallback_mode=fallback_mode,
            market_mode=MarketMode.EQUITIES.value,
            source_strategy=str(candidate.get("strategy") or "Agent Mode"),
            session_metadata=workflow._workflow_session_metadata(bars, timeframe=timeframe),
        )
        sizing_plan = self._apply_agent_sizing_caps(
            sizing_plan=workflow._paper_order_sizing_plan(rec, user=user),
            settings_payload=settings_payload,
            user=user,
            open_positions=open_positions,
        )
        if int(sizing_plan.get("final_order_shares") or 0) <= 0:
            return {
                **intent,
                "status": "blocked",
                "execution_error": sizing_plan.get("agent_sizing_block_reason") or "agent_sizing_blocked",
                **sizing_plan,
            }
        order_intent = workflow.recommendation_service.to_order_intent(rec).model_copy(
            update={"shares": int(sizing_plan["final_order_shares"])}
        )
        order, fill = workflow.paper_broker.execute(order_intent)
        workflow.recommendation_service.persist_order(
            order,
            notes=(
                "agent_mode_paper_open"
                f"|source={source}|fallback={str(fallback_mode).lower()}"
                "|paper_only=true|no_live_routing=true"
            ),
            app_user_id=user.id,
        )
        workflow.recommendation_service.persist_fill(fill)
        position = None
        if fill.filled_shares > 0:
            position = self.paper_repo.upsert_position_on_fill(
                app_user_id=user.id,
                symbol=order.symbol,
                side=order.side.value,
                fill_qty=float(fill.filled_shares),
                fill_price=float(fill.fill_price),
                recommendation_id=rec.recommendation_id,
                replay_run_id=None,
                order_id=order.order_id,
            )
        return {
            **intent,
            "status": "executed",
            "order_id": order.order_id,
            "position_id": position.id if position is not None else None,
            "recommendation_id": rec.recommendation_id,
            "display_id": self._display_id_for_recommendation(rec),
            "shares": order.shares,
            "limit_price": self._round_price(order.limit_price),
            "fill_price": self._round_price(fill.fill_price),
            "market_data_source": source,
            "fallback_mode": fallback_mode,
            **sizing_plan,
        }

    def _display_id_for_recommendation(self, rec: TradeRecommendation) -> str:
        row = self.recommendation_repo.get_by_recommendation_uid(rec.recommendation_id)
        return display_id_or_fallback(row.display_id if row else None, rec.recommendation_id)

    def _serialize_position_snapshot(
        self,
        row,
        *,
        user,
        review_by_position_id: dict[int, dict[str, object]] | None = None,
        intent_by_position_id: dict[int, dict[str, object]] | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        payload = workflow._serialize_position(row, commission_per_trade=workflow._effective_commission_per_trade(user))
        review = (review_by_position_id or {}).get(int(row.id))
        intent = (intent_by_position_id or {}).get(int(row.id))
        mark = None
        unrealized_pnl = None
        return_pct = None
        days_held = None
        current_agent_action = None
        current_agent_status = None
        action_summary = None
        if review:
            mark = review.get("current_mark_price")
            unrealized_pnl = review.get("unrealized_pnl")
            return_pct = review.get("unrealized_return_pct")
            days_held = review.get("days_held")
            current_agent_action = review.get("action_classification")
            current_agent_status = "reviewed"
            action_summary = review.get("action_summary")
        if intent:
            mark = intent.get("fill_price") or intent.get("mark_price") or mark
            current_agent_action = intent.get("intent") or current_agent_action
            current_agent_status = intent.get("status") or current_agent_status
            action_summary = intent.get("summary") or action_summary
            if unrealized_pnl is None and intent.get("intent") == "OPEN_PAPER":
                unrealized_pnl = 0.0
                return_pct = 0.0
        opened_at = row.opened_at
        if days_held is None and opened_at is not None:
            opened_aware = opened_at if opened_at.tzinfo is not None else opened_at.replace(tzinfo=timezone.utc)
            current = now or utc_now()
            days_held = max(0, (current - opened_aware).days)
        qty = self._safe_float(payload.get("remaining_qty"))
        avg_entry_price = self._safe_float(payload.get("avg_entry_price"))
        mark_price = self._safe_float(mark)
        cost_basis = self._round_money(qty * avg_entry_price) if qty is not None and avg_entry_price is not None else None
        current_market_value = self._round_money(qty * mark_price) if qty is not None and mark_price is not None else None
        return {
            **payload,
            "qty": self._round_qty(qty),
            "avg_entry_price": self._round_price(payload.get("avg_entry_price")),
            "open_notional": self._round_money(payload.get("open_notional")),
            "invested_amount": cost_basis,
            "cost_basis": cost_basis,
            "current_market_value": current_market_value,
            "current_mark_price": self._round_price(mark),
            "mark": self._round_price(mark),
            "unrealized_pnl": self._round_money(unrealized_pnl if unrealized_pnl is not None else getattr(row, "unrealized_pnl", None)),
            "unrealized_return_pct": self._round_money(return_pct),
            "days_held": days_held,
            "current_agent_action": current_agent_action,
            "current_agent_status": current_agent_status,
            "action_summary": action_summary,
        }

    @staticmethod
    def _run_response(row) -> dict[str, object]:
        response = row.response_json or {}
        return response if isinstance(response, dict) else {}

    def _serialize_run_history_row(self, row) -> dict[str, object]:
        result = self._run_response(row)
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        universe = result.get("universe") if isinstance(result.get("universe"), dict) else {}
        generated_at = str(
            result.get("asOf")
            or (row.completed_at.isoformat() if row.completed_at else None)
            or row.created_at.isoformat()
        )
        paper_opens = int(summary.get("paperOpensExecuted", summary.get("executedOrderCount", 0)) or 0)
        paper_closes = int(summary.get("paperClosesExecuted", 0) or 0)
        return {
            "runId": row.run_id,
            "run_id": row.run_id,
            "generatedAt": generated_at,
            "generated_at": generated_at,
            "mode": "dry_run" if row.dry_run else "enabled",
            "status": row.status,
            "executionMode": row.execution_mode,
            "dryRun": bool(row.dry_run),
            "universe": universe,
            "universeSource": universe.get("source") if isinstance(universe, dict) else None,
            "symbols": list(universe.get("symbols") or []) if isinstance(universe, dict) else [],
            "positionsBeforeCount": int(summary.get("positionsBeforeCount", summary.get("openPositionsBefore", 0)) or 0),
            "positionsAfterCount": int(summary.get("positionsAfterCount", summary.get("openPositionsAfter", 0)) or 0),
            "paperOpensExecuted": paper_opens,
            "paperClosesExecuted": paper_closes,
            "holds": int(summary.get("holds", 0) or 0),
            "blocked": int(summary.get("blockedActions", 0) or 0),
            "blockedActions": int(summary.get("blockedActions", 0) or 0),
            "cashNoTrade": int(summary.get("cashNoTrade", 0) or 0),
            "totalExecutedActions": int(summary.get("totalExecutedActions", paper_opens + paper_closes) or 0),
            "realizedPnlFromClosedPositions": self._round_money(summary.get("realizedPnlFromClosedPositions")),
            "unrealizedPnlAfter": self._round_money(summary.get("unrealizedPnlAfter")),
            "totalAgentPaperPnl": self._round_money(summary.get("totalAgentPaperPnl")),
            "warnings": list(result.get("warnings") or []),
            "missingData": [
                item
                for row_payload in list(result.get("dataQuality") or [])
                if isinstance(row_payload, dict) and row_payload.get("status") == "error"
                for item in [row_payload.get("reason")]
                if item
            ],
            "linkedPaperOrderIds": list(summary.get("linkedPaperOrderIds") or []),
            "linkedPositionIds": list(summary.get("linkedPositionIds") or []),
            "linkedTradeIds": list(summary.get("linkedTradeIds") or []),
        }

    def _agent_links_from_runs(self, rows: list[object]) -> dict[str, dict[object, dict[str, object]]]:
        links: dict[str, dict[object, dict[str, object]]] = {
            "orders": {},
            "positions": {},
            "trades": {},
        }
        for row in rows:
            result = self._run_response(row)
            run_id = str(result.get("runId") or getattr(row, "run_id", ""))
            for intent in list(result.get("intents") or []):
                if not isinstance(intent, dict):
                    continue
                link = {
                    "runId": run_id,
                    "intent": intent.get("intent"),
                    "reason": intent.get("reason"),
                    "summary": intent.get("summary"),
                    "status": intent.get("status"),
                }
                order_id = str(intent.get("order_id") or "").strip()
                if order_id:
                    links["orders"][order_id] = link
                position_id = str(intent.get("position_id") or "").strip()
                if position_id.isdigit():
                    links["positions"][int(position_id)] = link
                trade_id = str(intent.get("trade_id") or "").strip()
                if trade_id.isdigit():
                    links["trades"][int(trade_id)] = link
        return links

    @classmethod
    def _serialize_agent_trade(cls, row, *, links: dict[str, dict[object, dict[str, object]]]) -> dict[str, object]:
        payload = workflow._serialize_trade(row)
        trade_link = links["trades"].get(int(row.id))
        position_link = links["positions"].get(int(row.position_id)) if row.position_id is not None else None
        order_link = links["orders"].get(str(row.order_id)) if row.order_id else None
        link = trade_link or position_link or order_link or {}
        entry_notional = cls._safe_float(payload.get("entry_notional"))
        realized = cls._safe_float(payload.get("realized_pnl"))
        return_pct = round((realized / abs(entry_notional)) * 100, 2) if realized is not None and entry_notional else None
        hold_seconds = cls._safe_float(payload.get("hold_seconds"))
        close_reason = str(payload.get("close_reason") or "")
        return {
            **payload,
            "created_at": cls._iso(getattr(row, "opened_at", None)),
            "submitted_at": cls._iso(getattr(row, "opened_at", None)),
            "filled_at": cls._iso(getattr(row, "opened_at", None)),
            "executed_at": cls._iso(getattr(row, "opened_at", None)),
            "closed_at": cls._iso(getattr(row, "closed_at", None)),
            "status": "closed" if getattr(row, "closed_at", None) is not None else "open",
            "source": "agent_mode",
            "entry_price": cls._round_price(payload.get("entry_price")),
            "exit_price": cls._round_price(payload.get("exit_price")),
            "qty": cls._round_qty(payload.get("qty")),
            "realized_pnl": cls._round_money(payload.get("realized_pnl")),
            "net_pnl": cls._round_money(payload.get("net_pnl")),
            "gross_pnl": cls._round_money(payload.get("gross_pnl")),
            "return_pct": return_pct,
            "holding_days": round((hold_seconds or 0.0) / 86400, 2) if hold_seconds is not None else None,
            "entry_reason": order_link.get("reason") if order_link else None,
            "exit_reason": close_reason.replace("agent_mode:", "", 1) if close_reason.startswith("agent_mode:") else close_reason or link.get("reason"),
            "linked_run_id": link.get("runId"),
            "agent_intent": link.get("intent"),
        }

    @staticmethod
    def _is_agent_trade(row, *, links: dict[str, dict[object, dict[str, object]]]) -> bool:
        close_reason = str(getattr(row, "close_reason", "") or "")
        if close_reason.startswith("agent_mode:"):
            return True
        if getattr(row, "id", None) in links["trades"]:
            return True
        if getattr(row, "position_id", None) in links["positions"]:
            return True
        order_id = str(getattr(row, "order_id", "") or "")
        return bool(order_id and order_id in links["orders"])

    @staticmethod
    def _is_agent_position(row, *, links: dict[str, dict[object, dict[str, object]]]) -> bool:
        if getattr(row, "id", None) in links["positions"]:
            return True
        order_id = str(getattr(row, "order_id", "") or "")
        return bool(order_id and order_id in links["orders"])

    @staticmethod
    def _range_for_timeframe(timeframe: str | None, *, now: datetime) -> tuple[datetime | None, datetime | None, str]:
        key = str(timeframe or "all_time").strip().lower().replace("-", "_")
        local = now.astimezone(ZoneInfo("America/New_York"))
        start_local: datetime | None = None
        end_local: datetime | None = None
        if key in {"today", "1d"}:
            start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
            end_local = start_local + timedelta(days=1)
            key = "today"
        elif key == "yesterday":
            end_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
            start_local = end_local - timedelta(days=1)
        elif key in {"last_7_days", "7d"}:
            start_local = local - timedelta(days=7)
            end_local = local
            key = "last_7_days"
        elif key in {"last_30_days", "30d"}:
            start_local = local - timedelta(days=30)
            end_local = local
            key = "last_30_days"
        elif key in {"month_to_date", "mtd"}:
            start_local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_local = local
            key = "month_to_date"
        elif key == "previous_month":
            this_month = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            previous_end = this_month
            previous_start_month = previous_end.month - 1 or 12
            previous_start_year = previous_end.year - 1 if previous_end.month == 1 else previous_end.year
            start_local = previous_end.replace(year=previous_start_year, month=previous_start_month)
            end_local = previous_end
        else:
            key = "all_time"
        start = start_local.astimezone(timezone.utc) if start_local else None
        end = end_local.astimezone(timezone.utc) if end_local else None
        return start, end, key

    @staticmethod
    def _in_range(value: datetime | None, *, start: datetime | None, end: datetime | None) -> bool:
        if start is None and end is None:
            return True
        if value is None:
            return False
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if start is not None and aware < start:
            return False
        if end is not None and aware >= end:
            return False
        return True

    def list_runs(
        self,
        *,
        user,
        limit: int = 50,
        status: str | None = None,
        dry_run: bool | None = None,
        timeframe: str | None = None,
    ) -> dict[str, object]:
        limit = self._coerce_limit(limit, default=50, maximum=100)
        now = utc_now()
        start, end, timeframe_key = self._range_for_timeframe(timeframe, now=now)
        rows = [
            row
            for row in self.agent_repo.list_runs(app_user_id=user.id, limit=100, status=status, dry_run=dry_run)
            if self._in_range(row.created_at, start=start, end=end)
        ][:limit]
        return {
            "items": [self._serialize_run_history_row(row) for row in rows],
            "limit": limit,
            "timeframe": timeframe_key,
            "paperOnly": True,
            "executionMode": "paper",
        }

    def list_trades(
        self,
        *,
        user,
        limit: int = 100,
        timeframe: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
        run_id: str | None = None,
        source: str | None = "agent_mode",
    ) -> dict[str, object]:
        limit = self._coerce_limit(limit, default=100, maximum=250)
        if source and source != "agent_mode":
            return {"items": [], "limit": limit, "timeframe": timeframe or "all_time", "source": source, "paperOnly": True, "executionMode": "paper"}
        now = utc_now()
        start, end, timeframe_key = self._range_for_timeframe(timeframe, now=now)
        run_rows = self.agent_repo.list_runs(app_user_id=user.id, limit=100)
        links = self._agent_links_from_runs(run_rows)
        rows = self.paper_repo.list_trades(app_user_id=user.id, limit=limit)
        items = [
            self._serialize_agent_trade(row, links=links)
            for row in rows
            if self._is_agent_trade(row, links=links)
            and self._in_range(row.closed_at or row.opened_at, start=start, end=end)
            and (not symbol or str(row.symbol).upper() == symbol.upper())
        ]
        if status:
            items = [item for item in items if str(item.get("status") or "").lower() == status.lower()]
        if run_id:
            items = [item for item in items if str(item.get("linked_run_id") or "") == run_id]
        return {
            "items": items,
            "limit": limit,
            "timeframe": timeframe_key,
            "source": "agent_mode",
            "paperOnly": True,
            "executionMode": "paper",
        }

    def performance(self, *, user, timeframe: str | None = None, source: str | None = "agent_mode") -> dict[str, object]:
        settings_payload = self.serialize_settings(self.agent_repo.get_or_create_settings(app_user_id=user.id))
        now = utc_now()
        start, end, timeframe_key = self._range_for_timeframe(timeframe, now=now)
        if source and source != "agent_mode":
            run_rows: list[object] = []
        else:
            run_rows = [
                row
                for row in self.agent_repo.list_runs(app_user_id=user.id, limit=100)
                if self._in_range(row.created_at, start=start, end=end)
            ]
        links = self._agent_links_from_runs(run_rows)
        trade_rows = [
            row
            for row in self.paper_repo.list_trades(app_user_id=user.id, limit=500)
            if self._is_agent_trade(row, links=links)
            and self._in_range(row.closed_at or row.opened_at, start=start, end=end)
        ]
        trade_items = [self._serialize_agent_trade(row, links=links) for row in trade_rows]
        all_open_positions = self.paper_repo.list_positions(app_user_id=user.id, status="open", limit=100)
        open_positions = [
            row
            for row in all_open_positions
            if (source or "agent_mode") == "agent_mode" and self._is_agent_position(row, links=links)
        ]
        recent_rows = self.recommendation_repo.list_recent(limit=100, app_user_id=user.id)
        reviews: list[dict[str, object]] = []
        for position in open_positions:
            try:
                reviews.append(workflow._build_position_review(position, app_user_id=user.id, user=user, recent_rows=recent_rows, now=now))
            except Exception as exc:  # noqa: BLE001 - performance payload should remain available if one mark fails.
                del exc
                reviews.append(
                    {
                        "position_id": position.id,
                        "symbol": position.symbol,
                        "action_classification": "review_unavailable",
                        "action_summary": f"{position.symbol} review unavailable; inspect provider health and latest Agent Mode warnings.",
                        "warnings": ["position_review_unavailable"],
                    }
                )
        review_by_id = {
            int(review["position_id"]): review
            for review in reviews
            if str(review.get("position_id") or "").isdigit()
        }
        open_items = [
            self._serialize_position_snapshot(position, user=user, review_by_position_id=review_by_id, now=now)
            for position in open_positions
        ]
        realized_values = [self._safe_float(item.get("realized_pnl")) or 0.0 for item in trade_items]
        wins = [value for value in realized_values if value > 0]
        losses = [value for value in realized_values if value < 0]
        realized_total = round(sum(realized_values), 2)
        unrealized_after = self._sum_money(open_items, "unrealized_pnl") or 0.0
        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        ordered = sorted(trade_items, key=lambda item: str(item.get("closed_at") or item.get("opened_at") or ""))
        for item in ordered:
            cumulative += self._safe_float(item.get("realized_pnl")) or 0.0
            peak = max(peak, cumulative)
            max_drawdown = max(max_drawdown, peak - cumulative)
        latest = run_rows[0] if run_rows else None
        summary = self._serialize_run_history_row(latest) if latest else None
        run_items = [self._serialize_run_history_row(row) for row in run_rows]
        blocked_reasons = [
            str(intent.get("reason") or "blocked")
            for row in run_rows
            for intent in list(self._run_response(row).get("intents") or [])
            if isinstance(intent, dict) and intent.get("status") in {"blocked", "skipped", "review_only"}
        ]
        return {
            "paperOnly": True,
            "executionMode": "paper",
            "asOf": now.isoformat(),
            "timeframe": timeframe_key,
            "source": source or "agent_mode",
            "settings": settings_payload,
            "latestRun": summary,
            "openPositions": open_items,
            "tradeCount": len(trade_items),
            "openPositionCount": len(open_items),
            "realizedPnl": self._round_money(realized_total),
            "unrealizedPnl": self._round_money(unrealized_after),
            "totalPaperPnl": self._round_money(realized_total + unrealized_after),
            "cumulativeRealizedPnl": self._round_money(realized_total),
            "winCount": len(wins),
            "lossCount": len(losses),
            "winRate": round(len(wins) / len(realized_values), 4) if realized_values else None,
            "avgWin": self._round_money(sum(wins) / len(wins)) if wins else None,
            "avgLoss": self._round_money(sum(losses) / len(losses)) if losses else None,
            "profitFactor": round(sum(wins) / abs(sum(losses)), 4) if losses else None,
            "maxDrawdown": self._round_money(max_drawdown) if realized_values else None,
            "runsTracked": len(run_rows),
            "runMetrics": {
                "runsCompleted": sum(1 for row in run_items if row.get("status") == "completed"),
                "runsFailed": sum(1 for row in run_items if row.get("status") in {"error", "failed"}),
                "runsSkipped": sum(1 for row in run_items if row.get("status") == "skipped"),
                "averageCandidatesReviewed": round(
                    sum(len((self._run_response(row).get("candidateQueue") or [])) for row in run_rows) / len(run_rows),
                    2,
                ) if run_rows else 0,
                "tradesCreated": sum(int(row.get("paperOpensExecuted") or 0) for row in run_items),
                "tradesBlocked": sum(int(row.get("blockedActions") or 0) for row in run_items),
                "positionsReviewed": sum(int(row.get("positionsBeforeCount") or 0) for row in run_items),
            },
            "tradeMetrics": {
                "tradesCreated": len(trade_items),
                "openTrades": len(open_items),
                "closedTrades": len(trade_items),
                "realizedPnl": self._round_money(realized_total),
                "unrealizedPnl": self._round_money(unrealized_after),
                "averageReturn": round(
                    sum(self._safe_float(item.get("return_pct")) or 0.0 for item in trade_items) / len(trade_items),
                    2,
                ) if trade_items else None,
                "averageHoldDays": round(
                    sum(self._safe_float(item.get("holding_days")) or 0.0 for item in trade_items) / len(trade_items),
                    2,
                ) if trade_items else None,
            },
            "positionMetrics": {
                "openPositions": len(open_items),
                "openExposure": self._sum_money(open_items, "open_notional"),
                "currentUnrealizedPnl": self._round_money(unrealized_after),
                "currentMarketValue": self._sum_money(open_items, "open_notional"),
                "cashReserve": settings_payload.get("min_cash_reserve"),
                "percentOfPaperAccountExposed": None,
            },
            "riskBlockMetrics": {
                "volatilityBlocks": sum(1 for reason in blocked_reasons if "vol" in reason),
                "staleDataBlocks": sum(1 for reason in blocked_reasons if "stale" in reason or "market_data" in reason),
                "sizingBlocks": sum(1 for reason in blocked_reasons if "sizing" in reason or "cap" in reason or "max_" in reason),
                "duplicateOpenSymbolBlocks": sum(1 for reason in blocked_reasons if "already_open" in reason or "duplicate" in reason),
                "noWatchlistSkips": sum(1 for reason in blocked_reasons if "watchlist" in reason),
                "disabledAgentSkips": sum(1 for reason in blocked_reasons if "disabled" in reason),
            },
        }

    def send_test_notification(self, *, user, channel: str | None = None) -> dict[str, object]:
        settings_payload = self.serialize_settings(self.agent_repo.get_or_create_settings(app_user_id=user.id))
        requested = str(channel or settings_payload.get("notification_preference") or "none").strip().lower()
        if requested in {"email", "sms", "both", "none"}:
            settings_payload = {**settings_payload, "notification_preference": requested}
            settings_payload["email_notifications_enabled"] = requested in {"email", "both"}
            settings_payload["sms_notifications_enabled"] = requested in {"sms", "both"}
        attempts = self.notification_service.send_event(
            user=user,
            settings_payload=settings_payload,
            event_type="agent_test_notification",
            title="MacMarket Agent Mode test notification",
            body=(
                "Test notification from MacMarket Agent Mode. "
                "This is paper-only operational messaging and does not enable live trading or broker routing."
            ),
            payload={"paperOnly": True, "test": True},
        )
        return {
            "paperOnly": True,
            "executionMode": "paper",
            "preference": settings_payload.get("notification_preference"),
            "smsProvider": NotificationService.sms_readiness(),
            "attempts": attempts,
        }

    def run(self, *, user, request: dict[str, object] | None = None) -> dict[str, object]:
        request = dict(request or {})
        if not self._user_is_approved(user):
            raise HTTPException(status_code=403, detail=f"Approval status is {getattr(user, 'approval_status', 'unknown')}")
        mode = str(request.get("mode") or request.get("execution_mode") or "paper").strip().lower()
        if mode not in {"paper", "paper_only"}:
            raise HTTPException(status_code=409, detail="Agent Mode only supports paper mode.")
        settings_row = self.agent_repo.get_or_create_settings(app_user_id=user.id)
        settings_payload = self.serialize_settings(settings_row)
        dry_run = self._coerce_bool(request.get("dry_run"), default=not bool(settings_payload["enabled"]))
        run_guard_reason: str | None = None
        if not bool(settings_payload["enabled"]):
            dry_run = True
            run_guard_reason = "agent_disabled"
        enabled_for_execution = bool(settings_payload["enabled"]) and not dry_run
        if settings_payload["paused"] or settings_payload["kill_switch_enabled"]:
            enabled_for_execution = False
            dry_run = True
            run_guard_reason = "kill_switch_enabled" if settings_payload["kill_switch_enabled"] else "agent_paused"

        max_positions = min(
            self._coerce_int(settings_payload.get("max_positions"), default=5, minimum=1, maximum=5),
            self._coerce_int(settings_payload.get("max_open_agent_positions"), default=5, minimum=1, maximum=5),
        )
        max_new_trades_per_run = self._coerce_int(settings_payload.get("max_new_trades_per_run"), default=5, minimum=0, maximum=5)
        max_new_trades_per_day = self._coerce_int(settings_payload.get("max_new_trades_per_day"), default=5, minimum=0, maximum=5)
        timeframe = str(request.get("timeframe") or "1D").upper()
        universe = self.resolve_universe(app_user_id=user.id, settings_payload=settings_payload, overrides=request)
        open_positions = self.paper_repo.list_positions(app_user_id=user.id, status="open", limit=100)
        recent_rows = self.recommendation_repo.list_recent(limit=100, app_user_id=user.id)
        now = utc_now()
        position_reviews = [
            workflow._build_position_review(position, app_user_id=user.id, user=user, recent_rows=recent_rows, now=now)
            for position in open_positions
        ]
        intents: list[dict[str, object]] = [
            self._position_intent(review, settings_payload=settings_payload, dry_run=dry_run)
            for review in position_reviews
        ]

        closing_symbols = {
            str(intent.get("symbol") or "").upper()
            for intent in intents
            if intent.get("intent") == "CLOSE_PAPER" and bool(settings_payload.get("allow_closes", True))
        }
        held_symbols = {
            str(position.symbol or "").upper()
            for position in open_positions
            if str(position.symbol or "").upper() not in closing_symbols
        }
        allow_existing_symbol_open = bool(settings_payload.get("allow_new_trade_when_symbol_already_open")) and bool(settings_payload.get("allow_scale_ins"))
        bars_by_symbol: dict[str, tuple[list[Any], str, bool]] = {}
        data_quality: list[dict[str, object]] = []
        if not universe["symbols"]:
            reason = (
                str(universe.get("reason") or "watchlist_missing_or_empty")
                if universe.get("source") in {"watchlist", "watchlist_plus_manual"}
                else "empty_universe"
            )
            data_quality.append(
                {
                    "symbol": None,
                    "status": "error",
                    "reason": reason,
                    "universe_source": universe.get("source"),
                    "source_status": universe.get("source_status"),
                    "watchlist_id": universe.get("watchlist_id"),
                    "watchlist_name": universe.get("watchlist_name"),
                }
            )
            intents.append(self._cash_intent(symbol=None, reason=reason, summary="cash/no trade because Agent Mode had no valid symbols to scan."))
        for symbol in universe["symbols"]:
            if symbol in held_symbols and not allow_existing_symbol_open:
                data_quality.append({"symbol": symbol, "status": "skipped", "reason": "already_open"})
                continue
            try:
                bars_tuple = workflow._workflow_bars(symbol, limit=120, timeframe=timeframe)
                bars_by_symbol[symbol] = bars_tuple
                data_quality.append(
                    {
                        "symbol": symbol,
                        "status": "ok",
                        "source": bars_tuple[1],
                        "fallback_mode": bars_tuple[2],
                        "session": workflow._workflow_session_metadata(bars_tuple[0], timeframe=timeframe),
                    }
                )
            except HTTPException as exc:
                data_quality.append({"symbol": symbol, "status": "error", "reason": exc.detail})
                intents.append(self._cash_intent(symbol=symbol, reason="market_data_unavailable", summary="cash/no trade because market data was unavailable."))

        strategies = [entry.display_name for entry in workflow.list_strategies(MarketMode.EQUITIES)[:3]]
        ranking = workflow.ranking_engine.rank_candidates(
            bars_by_symbol=bars_by_symbol,
            strategies=strategies,
            market_mode=MarketMode.EQUITIES,
            timeframe=timeframe,
            top_n=int(universe["scan_depth"]),
        )
        candidates = list(ranking.get("queue") or [])
        planned_open_symbols: set[str] = set()
        index_context = workflow._current_index_context_for_risk()
        paper_opens_today = self._paper_opens_today(app_user_id=user.id, timezone_name=str(settings_payload.get("timezone") or "America/New_York"), now=now)
        for candidate in candidates:
            symbol = str(candidate.get("symbol") or "").upper()
            bars_tuple = bars_by_symbol.get(symbol)
            if bars_tuple:
                risk = workflow.risk_calendar_service.assess(
                    symbol=symbol,
                    timeframe=timeframe,
                    bars=bars_tuple[0],
                    index_context=index_context,
                )
                candidate["risk_calendar"] = risk.model_dump(mode="json")
                session_metadata = workflow._workflow_session_metadata(bars_tuple[0], timeframe=timeframe)
                candidate["session_policy"] = session_metadata.get("session_policy")
                candidate["data_quality"] = {
                    "source": bars_tuple[1],
                    "fallback_mode": bars_tuple[2],
                    "session_policy": session_metadata.get("session_policy"),
                    "source_session_policy": session_metadata.get("source_session_policy"),
                    "source_timeframe": session_metadata.get("source_timeframe"),
                    "output_timeframe": session_metadata.get("output_timeframe"),
                }
            if symbol in held_symbols and not allow_existing_symbol_open:
                candidate["already_open"] = True
                intents.append(self._cash_intent(symbol=symbol, reason="already_open", summary="cash/no trade because the symbol is already open.", candidate=candidate))
                continue
            if symbol in held_symbols and not bool(settings_payload.get("allow_scale_ins")):
                candidate["already_open"] = True
                intents.append(self._cash_intent(symbol=symbol, reason="scale_ins_disabled", summary="cash/no trade because scale-ins are disabled for Agent Mode.", candidate=candidate))
                continue
            if symbol in planned_open_symbols:
                intents.append(self._cash_intent(symbol=symbol, reason="duplicate_ranked_symbol", summary="cash/no trade because a higher-ranked candidate already uses this symbol.", candidate=candidate))
                continue
            risk = candidate.get("risk_calendar") if isinstance(candidate.get("risk_calendar"), dict) else {}
            decision = risk.get("decision") if isinstance(risk.get("decision"), dict) else {}
            if candidate.get("status") != "top_candidate":
                continue
            if decision and decision.get("allow_new_entries") is False:
                intents.append(self._cash_intent(symbol=symbol, reason="risk_calendar_blocks_new_entries", summary="cash/no trade because risk calendar blocks new paper opens.", candidate=candidate))
                continue
            slots_after_closes = max_positions - (len(held_symbols) + len([i for i in intents if i.get("intent") == "OPEN_PAPER"]))
            if slots_after_closes <= 0:
                intents.append(self._cash_intent(symbol=symbol, reason="max_positions_reached", summary="cash/no trade because the target paper book is full.", candidate=candidate))
                continue
            if not bool(settings_payload.get("allow_opens", True)):
                intents.append(self._cash_intent(symbol=symbol, reason="opens_disabled", summary="cash/no trade because paper opens are disabled.", candidate=candidate))
                continue
            if len([i for i in intents if i.get("intent") == "OPEN_PAPER"]) >= max_new_trades_per_run:
                intents.append(self._cash_intent(symbol=symbol, reason="max_new_trades_per_run_reached", summary="cash/no trade because the Agent Mode per-run new-trade cap is reached.", candidate=candidate))
                continue
            if paper_opens_today + len([i for i in intents if i.get("intent") == "OPEN_PAPER"]) >= max_new_trades_per_day:
                intents.append(self._cash_intent(symbol=symbol, reason="max_new_trades_per_day_reached", summary="cash/no trade because the Agent Mode daily new-trade cap is reached.", candidate=candidate))
                continue
            planned_open_symbols.add(symbol)
            intents.append(
                {
                    "intent": "OPEN_PAPER",
                    "symbol": symbol,
                    "side": "long",
                    "status": "dry_run" if dry_run else "pending",
                    "reason": "ranked_top_candidate",
                    "summary": "paper open candidate from deterministic ranking.",
                    "candidate": candidate,
                    "paper_only": True,
                    "no_live_routing": True,
                }
            )

        if not any(intent.get("intent") in {"OPEN_PAPER", "CLOSE_PAPER"} for intent in intents):
            intents.append(self._cash_intent(symbol=None, reason="no_approved_paper_changes", summary="cash/no trade because no deterministic paper change passed all gates."))

        executed_order_count = 0
        final_intents: list[dict[str, object]] = []
        for intent in intents:
            if not enabled_for_execution:
                final_intents.append({**intent, "status": "dry_run" if intent.get("status") != "blocked" else "blocked"})
                continue
            if intent.get("intent") == "CLOSE_PAPER":
                final_intents.append(self._execute_close(intent=intent, user=user))
            elif intent.get("intent") == "OPEN_PAPER":
                executed = self._execute_open(
                    intent=intent,
                    candidate=dict(intent.get("candidate") or {}),
                    user=user,
                    bars_by_symbol=bars_by_symbol,
                    timeframe=timeframe,
                    settings_payload=settings_payload,
                    open_positions=open_positions,
                )
                if executed.get("status") == "executed":
                    executed_order_count += 1
                final_intents.append(executed)
            elif intent.get("intent") in {"REPLACE_PAPER", "SCALE_IN_PAPER", "REDUCE_PAPER"}:
                final_intents.append(
                    {
                        **intent,
                        "status": "review_only",
                        "execution_error": "scale_resize_execution_deferred",
                    }
                )
            else:
                final_intents.append(intent)

        positions_after = self.paper_repo.list_positions(app_user_id=user.id, status="open", limit=100)
        review_by_position_id = {
            int(review["position_id"]): review
            for review in position_reviews
            if str(review.get("position_id") or "").strip().isdigit()
        }
        intent_by_position_id = {
            int(intent["position_id"]): intent
            for intent in final_intents
            if str(intent.get("position_id") or "").strip().isdigit()
        }
        current_paper_book = [
            self._serialize_position_snapshot(
                row,
                user=user,
                review_by_position_id=review_by_position_id,
                intent_by_position_id=intent_by_position_id,
                now=now,
            )
            for row in positions_after
        ]
        execution_metrics = self._intent_execution_metrics(
            final_intents,
            positions_before_count=len(open_positions),
            positions_after_count=len(positions_after),
        )
        unrealized_after = self._sum_money(current_paper_book, "unrealized_pnl")
        realized_from_closes = self._safe_float(execution_metrics.get("realizedPnlFromClosedPositions")) or 0.0
        total_agent_paper_pnl = None
        if unrealized_after is not None:
            total_agent_paper_pnl = self._round_money(realized_from_closes + unrealized_after)
        summary = {
            "paperOnly": True,
            "executionMode": "paper",
            "dryRun": dry_run,
            "enabled": bool(settings_payload["enabled"]),
            "paused": bool(settings_payload["paused"]),
            "killSwitchEnabled": bool(settings_payload["kill_switch_enabled"]),
            "skipReason": run_guard_reason,
            "maxPositions": max_positions,
            "maxOpenAgentPositions": max_positions,
            "maxNewTradesPerRun": max_new_trades_per_run,
            "maxNewTradesPerDay": max_new_trades_per_day,
            "paperOpensTodayBeforeRun": paper_opens_today,
            "openPositionsBefore": len(open_positions),
            "targetPositionsMax": max_positions,
            "intentCounts": {name: sum(1 for item in final_intents if item.get("intent") == name) for name in AGENT_MODE_INTENTS},
            "executedOrderCount": executed_order_count,
            **execution_metrics,
            "openPositionsAfter": len(positions_after),
            "unrealizedPnlAfter": unrealized_after,
            "totalAgentPaperPnl": total_agent_paper_pnl,
        }
        run_id = f"agent_{uuid4().hex[:16]}"
        response = {
            "runId": run_id,
            "asOf": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
            "settings": settings_payload,
            "universe": universe,
            "summary": summary,
            "paperBookBefore": [
                self._serialize_position_snapshot(
                    row,
                    user=user,
                    review_by_position_id=review_by_position_id,
                    now=now,
                )
                for row in open_positions
            ],
            "currentPaperBook": current_paper_book,
            "positionReviews": position_reviews,
            "intents": final_intents,
            "candidateQueue": candidates,
            "decisionMemo": [
                "Paper only. No live routing. Disable anytime.",
                "Deterministic ranking, risk calendar, paper sizing, stops, targets, and lifecycle state decided every intent.",
                "Enabled runs execute only through the Agent Mode paper lifecycle; dry-runs record review-only intents.",
                "LLM/AI text is not used to approve, size, route, open, or close paper positions.",
            ],
            "dataQuality": data_quality,
            "warnings": [
                warning
                for row in data_quality
                for warning in ([str(row.get("reason"))] if row.get("status") == "error" else [])
            ],
        }
        notification_attempts: list[dict[str, object]] = []
        digest = self._build_run_notification_digest(
            run_id=run_id,
            response=response,
            final_intents=final_intents,
            candidates=candidates,
            universe=universe,
        )
        notification_attempts.extend(
            self.notification_service.send_event(
                user=user,
                settings_payload=settings_payload,
                event_type=str(digest["event_type"]),
                title=str(digest["title"]),
                body=str(digest["text"]),
                email_html=str(digest["html"]),
                sms_body=str(digest["sms"]),
                run_id=run_id,
                payload=digest["payload"] if isinstance(digest.get("payload"), dict) else None,
            )
        )
        response["notificationAttempts"] = notification_attempts
        self.agent_repo.create_run(
            app_user_id=user.id,
            run_id=run_id,
            status="completed",
            execution_mode="paper",
            dry_run=dry_run,
            intent_count=len(final_intents),
            executed_order_count=executed_order_count,
            request_json=request,
            response_json=response,
            completed_at=utc_now(),
        )
        return response

    @staticmethod
    def _scheduled_time_due(*, run_time: str, now: datetime) -> bool:
        parts = str(run_time or "15:45").split(":", 1)
        try:
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except (TypeError, ValueError):
            hour, minute = 15, 45
        return (now.hour, now.minute) >= (max(0, min(23, hour)), max(0, min(59, minute)))

    @staticmethod
    def _setting_zone(timezone_name: str | None):
        try:
            return ZoneInfo(str(timezone_name or "America/New_York"))
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def run_due(self, *, now: datetime | None = None) -> list[dict[str, object]]:
        current_utc = now or datetime.now(timezone.utc)
        output: list[dict[str, object]] = []
        for setting in self.agent_repo.list_enabled_settings():
            zone = self._setting_zone(setting.timezone)
            local_now = current_utc.astimezone(zone)
            latest = self.agent_repo.latest_run(app_user_id=setting.app_user_id)
            latest_local_date = None
            if latest and latest.created_at:
                latest_at = latest.created_at if latest.created_at.tzinfo else latest.created_at.replace(tzinfo=timezone.utc)
                latest_local_date = latest_at.astimezone(zone).date()
            if latest_local_date == local_now.date():
                output.append({"app_user_id": setting.app_user_id, "status": "skipped", "reason": "already_ran_today"})
                continue
            if not self._scheduled_time_due(run_time=setting.daily_run_time, now=local_now):
                output.append({"app_user_id": setting.app_user_id, "status": "skipped", "reason": "not_due_yet"})
                continue
            with SessionLocal() as session:
                user = session.execute(select(AppUserModel).where(AppUserModel.id == setting.app_user_id)).scalar_one_or_none()
            if user is None:
                output.append({"app_user_id": setting.app_user_id, "status": "skipped", "reason": "user_not_found"})
                continue
            if not self._user_is_approved(user):
                output.append({"app_user_id": setting.app_user_id, "status": "skipped", "reason": "user_not_approved"})
                continue
            try:
                result = self.run(user=user, request={"mode": "paper", "dry_run": False, "trigger": "daily_scheduler"})
            except Exception as exc:  # noqa: BLE001 - scheduler reports per-user failure and continues.
                output.append({"app_user_id": setting.app_user_id, "status": "error", "reason": str(exc)})
                continue
            output.append({"app_user_id": setting.app_user_id, "status": "completed", "runId": result.get("runId")})
        return output
