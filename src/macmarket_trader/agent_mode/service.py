from __future__ import annotations

import math
from uuid import uuid4
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select

from macmarket_trader.agent_mode import market_session
from macmarket_trader.agent_mode import triggers as agent_triggers
from macmarket_trader.api.routes import admin as workflow
from macmarket_trader.config import settings
from macmarket_trader.domain.enums import ApprovalStatus, Direction, MarketMode
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import OrderIntent, PortfolioSnapshot, TradeRecommendation
from macmarket_trader.domain.time import utc_now
from macmarket_trader.email_templates import render_agent_mode_run_digest_html
from macmarket_trader.notifications import NotificationService
from macmarket_trader.strategy_registry import get_strategy_by_id
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import (
    DEFAULT_STANDARD_STRATEGY_IDS,
    AgentModeRepository,
    AgentProfileRepository,
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

AGENT_MODE_SOURCE_MANUAL = "manual_agent"
AGENT_MODE_SOURCE_SCHEDULED = "scheduled_agent"
AGENT_MODE_SOURCE_DIAGNOSTIC = "scheduler_diagnostic"
AGENT_SCHEDULER_HEALTH_STALE_SECONDS = 15 * 60


class AgentModeService:
    """Deterministic paper-only operator loop for the Agent Mode MVP."""

    def __init__(
        self,
        *,
        agent_repo: AgentModeRepository | None = None,
        profile_repo: AgentProfileRepository | None = None,
        paper_repo: PaperPortfolioRepository | None = None,
        recommendation_repo: RecommendationRepository | None = None,
        symbol_universe_repo: SymbolUniverseRepository | None = None,
        watchlist_repo: WatchlistRepository | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.agent_repo = agent_repo or AgentModeRepository(SessionLocal)
        self.profile_repo = profile_repo or AgentProfileRepository(SessionLocal)
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
            "scheduler_last_checked_at": row.scheduler_last_checked_at.isoformat() if getattr(row, "scheduler_last_checked_at", None) else None,
            "scheduler_last_check_result": getattr(row, "scheduler_last_check_result", None),
            "scheduler_last_check_reason": getattr(row, "scheduler_last_check_reason", None),
            "scheduler_last_due_at": row.scheduler_last_due_at.isoformat() if getattr(row, "scheduler_last_due_at", None) else None,
            "scheduler_last_run_id": getattr(row, "scheduler_last_run_id", None),
            "scheduler_last_window_key": getattr(row, "scheduler_last_window_key", None),
            "sms_provider_status": NotificationService.sms_readiness(),
            # Phase 11 — Agent Profile identity + agent-type config (absent on
            # legacy settings rows, where these getattr defaults apply).
            "profile_uid": getattr(row, "profile_uid", None),
            "agent_profile_id": getattr(row, "id", None),
            "name": getattr(row, "name", None),
            "agent_type": str(getattr(row, "agent_type", "standard") or "standard"),
            "is_default": bool(getattr(row, "is_default", False)),
            "strategy_families": list(getattr(row, "strategy_families", None) or []),
            "haco_direction_mode": str(getattr(row, "haco_direction_mode", "long_only") or "long_only"),
            "true_momentum_trigger_mode": str(getattr(row, "true_momentum_trigger_mode", "review_only") or "review_only"),
            "use_haco_filter": bool(getattr(row, "use_haco_filter", False)),
            "use_true_momentum_confirmation": bool(getattr(row, "use_true_momentum_confirmation", False)),
            # Phase 12 — ATR config + directional/bidirectional controls.
            "atr_trail_type": str(getattr(row, "atr_trail_type", "modified") or "modified"),
            "atr_period": int(getattr(row, "atr_period", 9) or 9),
            "atr_factor": float(getattr(row, "atr_factor", 2.9) or 2.9),
            "atr_first_trade": str(getattr(row, "atr_first_trade", "long") or "long"),
            "atr_average_type": str(getattr(row, "atr_average_type", "wilders") or "wilders"),
            "atr_decision_timeframe": str(getattr(row, "atr_decision_timeframe", "1D") or "1D"),
            "atr_alignment_mode": str(getattr(row, "atr_alignment_mode", "decision_timeframe_only") or "decision_timeframe_only"),
            "allow_shorts": bool(getattr(row, "allow_shorts", False)),
            "allow_direction_flip": bool(getattr(row, "allow_direction_flip", True)),
            "close_opposite_before_open": bool(getattr(row, "close_opposite_before_open", True)),
            "close_on_opposite_signal": bool(getattr(row, "close_on_opposite_signal", True)),
            "hedge_allowed": bool(getattr(row, "hedge_allowed", False)),
            "use_atr_filter": bool(getattr(row, "use_atr_filter", False)),
            "prevent_opposing_agent_positions_across_profiles": bool(
                getattr(row, "prevent_opposing_agent_positions_across_profiles", False)
            ),
            "paper_only": True,
            "execution_mode": "paper",
        }

    @staticmethod
    def serialize_profile(row) -> dict[str, object]:
        """Strict superset of :meth:`serialize_settings` for an Agent Profile row."""
        return AgentModeService.serialize_settings(row)

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
            "use_haco_filter",
            "use_true_momentum_confirmation",
            "use_atr_filter",
            "allow_shorts",
            "allow_direction_flip",
            "close_opposite_before_open",
            "close_on_opposite_signal",
            "hedge_allowed",
            "prevent_opposing_agent_positions_across_profiles",
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
        # Phase 11 — Agent Profile identity + agent-type configuration.
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise HTTPException(status_code=400, detail="name must not be empty.")
            updates["name"] = name[:128]
        if "strategy_families" in payload:
            raw_families = payload.get("strategy_families") or []
            if not isinstance(raw_families, list):
                raise HTTPException(status_code=400, detail="strategy_families must be a list.")
            valid_ids = {entry.strategy_id for entry in workflow.list_strategies(MarketMode.EQUITIES)}
            cleaned_families: list[str] = []
            for item in raw_families:
                strategy_id = str(item).strip()
                if strategy_id and strategy_id not in valid_ids:
                    raise HTTPException(status_code=400, detail=f"unknown_strategy_id:{strategy_id}")
                if strategy_id and strategy_id not in cleaned_families:
                    cleaned_families.append(strategy_id)
            updates["strategy_families"] = cleaned_families
        if "haco_direction_mode" in payload:
            mode = str(payload.get("haco_direction_mode") or "long_only").strip().lower()
            if mode not in {"long_only", "short_only", "long_and_short"}:
                raise HTTPException(status_code=400, detail="unsupported_haco_direction_mode")
            updates["haco_direction_mode"] = mode
        if "true_momentum_trigger_mode" in payload:
            mode = str(payload.get("true_momentum_trigger_mode") or "review_only").strip().lower()
            if mode not in {"conservative", "balanced", "aggressive", "review_only"}:
                raise HTTPException(status_code=400, detail="unsupported_true_momentum_trigger_mode")
            updates["true_momentum_trigger_mode"] = mode
        # Phase 12 — ATR Trailing Stop config (validated; defaults frozen by the engine).
        if "atr_trail_type" in payload:
            value = str(payload.get("atr_trail_type") or "modified").strip().lower()
            if value not in {"modified", "unmodified"}:
                raise HTTPException(status_code=400, detail="unsupported_atr_trail_type")
            updates["atr_trail_type"] = value
        if "atr_average_type" in payload:
            value = str(payload.get("atr_average_type") or "wilders").strip().lower()
            if value not in {"wilders", "simple", "exponential"}:
                raise HTTPException(status_code=400, detail="unsupported_atr_average_type")
            updates["atr_average_type"] = value
        if "atr_first_trade" in payload:
            value = str(payload.get("atr_first_trade") or "long").strip().lower()
            if value not in {"long", "short"}:
                raise HTTPException(status_code=400, detail="unsupported_atr_first_trade")
            updates["atr_first_trade"] = value
        if "atr_alignment_mode" in payload:
            value = str(payload.get("atr_alignment_mode") or "decision_timeframe_only").strip().lower()
            if value not in {"decision_timeframe_only", "daily_and_hourly", "multi_timeframe_alignment"}:
                raise HTTPException(status_code=400, detail="unsupported_atr_alignment_mode")
            updates["atr_alignment_mode"] = value
        if "atr_decision_timeframe" in payload:
            updates["atr_decision_timeframe"] = str(payload.get("atr_decision_timeframe") or "1D").strip()[:8] or "1D"
        if "atr_period" in payload:
            updates["atr_period"] = self._coerce_int(payload.get("atr_period"), default=9, minimum=1, maximum=200)
        if "atr_factor" in payload:
            parsed = self._coerce_optional_float(payload.get("atr_factor"), minimum=0.1, maximum=100.0, field_name="atr_factor")
            updates["atr_factor"] = parsed if parsed is not None else 2.9
        return updates

    def _resolve_profile_or_404(self, *, user, profile_uid=None, profile_id=None):
        raw_id = profile_id
        parsed_id = int(raw_id) if str(raw_id or "").strip().isdigit() else None
        profile = self.profile_repo.resolve_profile(
            app_user_id=user.id,
            profile_uid=str(profile_uid) if profile_uid else None,
            profile_id=parsed_id,
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="agent_profile_not_found")
        return profile

    def _optional_profile_id(self, *, user, profile_uid=None, profile_id=None) -> int | None:
        """Resolve a profile id when a filter is supplied; None means 'all agents'.

        An explicit-but-unknown profile id/uid is a 404 (user scoping enforced).
        """
        if not profile_uid and not str(profile_id or "").strip().isdigit():
            return None
        return int(self._resolve_profile_or_404(user=user, profile_uid=profile_uid, profile_id=profile_id).id)

    def _validate_default_watchlist(self, *, user, updates: dict[str, object]) -> None:
        default_watchlist_id = updates.get("default_watchlist_id")
        if default_watchlist_id is not None:
            row = self.watchlist_repo.get_for_user(watchlist_id=int(default_watchlist_id), app_user_id=user.id)
            if row is None:
                raise HTTPException(status_code=404, detail="default_watchlist_id not found for user")

    def get_settings(self, *, user, profile_uid=None, profile_id=None) -> dict[str, object]:
        return self.serialize_profile(
            self._resolve_profile_or_404(user=user, profile_uid=profile_uid, profile_id=profile_id)
        )

    def latest_run_response(self, *, user, profile_uid=None, profile_id=None) -> dict[str, object]:
        profile = self._resolve_profile_or_404(user=user, profile_uid=profile_uid, profile_id=profile_id)
        latest = self.profile_repo.latest_run(app_user_id=user.id, agent_profile_id=profile.id)
        return {
            "settings": self.serialize_profile(profile),
            "latestRun": self.serialize_run(latest) if latest else None,
            "empty": latest is None,
            "paperOnly": True,
            "executionMode": "paper",
        }

    def update_settings(self, *, user, payload: dict[str, object]) -> dict[str, object]:
        mode = str(payload.get("mode") or payload.get("execution_mode") or "paper").strip().lower()
        if mode not in {"paper", "paper_only"}:
            raise HTTPException(status_code=409, detail="Agent Mode only supports paper mode.")
        profile = self._resolve_profile_or_404(
            user=user,
            profile_uid=payload.get("profile_uid") or payload.get("profile"),
            profile_id=payload.get("profile_id") or payload.get("agent_profile_id"),
        )
        updates = self.normalize_settings_update(payload)
        self._validate_default_watchlist(user=user, updates=updates)
        row = self.profile_repo.update_profile(app_user_id=user.id, profile_uid=profile.profile_uid, updates=updates)
        if row is None:
            raise HTTPException(status_code=404, detail="agent_profile_not_found")
        return self.serialize_profile(row)

    def list_profiles(self, *, user) -> dict[str, object]:
        rows = self.profile_repo.list_profiles(app_user_id=user.id)
        now = utc_now()
        return {
            "profiles": [self._profile_overview(row, user=user, now=now) for row in rows],
            "paperOnly": True,
            "executionMode": "paper",
        }

    def agents_overview(self, *, user) -> dict[str, object]:
        return self.list_profiles(user=user)

    def create_profile(self, *, user, payload: dict[str, object]) -> dict[str, object]:
        mode = str(payload.get("mode") or payload.get("execution_mode") or "paper").strip().lower()
        if mode not in {"paper", "paper_only"}:
            raise HTTPException(status_code=409, detail="Agent Mode only supports paper mode.")
        agent_type = str(payload.get("agent_type") or payload.get("template") or "standard").strip().lower()
        if agent_type not in {"standard", "haco_direction", "true_momentum", "hybrid", "atr_trailing_stop"}:
            raise HTTPException(status_code=400, detail="unsupported_agent_type")
        # Validate the config fields, then merge onto an agent-type default payload.
        updates = self.normalize_settings_update(payload)
        self._validate_default_watchlist(user=user, updates=updates)
        create_payload: dict[str, object] = {
            "agent_type": agent_type,
            "name": str(payload.get("name") or "").strip() or self._default_profile_name(agent_type),
        }
        create_payload.update(updates)
        # Identity fields are controlled here, never by arbitrary update keys.
        create_payload["agent_type"] = agent_type
        create_payload["name"] = create_payload.get("name") or self._default_profile_name(agent_type)
        row = self.profile_repo.create_profile(app_user_id=user.id, payload=create_payload)
        return self.serialize_profile(row)

    @staticmethod
    def _default_profile_name(agent_type: str) -> str:
        return {
            "standard": "Standard Strategy Agent",
            "haco_direction": "HACO Direction Agent",
            "true_momentum": "True Momentum Agent",
            "hybrid": "Hybrid Agent",
        }.get(agent_type, "Agent Profile")

    def delete_profile(self, *, user, profile_uid: str) -> dict[str, object]:
        status, _row = self.profile_repo.delete_profile(app_user_id=user.id, profile_uid=profile_uid)
        if status == "not_found":
            raise HTTPException(status_code=404, detail="agent_profile_not_found")
        if status == "blocked_default":
            raise HTTPException(status_code=409, detail="cannot_delete_default_profile")
        if status == "blocked_last":
            raise HTTPException(status_code=409, detail="cannot_delete_last_profile")
        return {"status": "deleted", "profile_uid": profile_uid, "paperOnly": True}

    def set_default_profile(self, *, user, profile_uid: str) -> dict[str, object]:
        row = self.profile_repo.set_default_profile(app_user_id=user.id, profile_uid=profile_uid)
        if row is None:
            raise HTTPException(status_code=404, detail="agent_profile_not_found")
        return self.serialize_profile(row)

    def _profile_overview(self, row, *, user, now: datetime | None = None) -> dict[str, object]:
        now = now or utc_now()
        settings_payload = self.serialize_profile(row)
        try:
            universe = self.resolve_universe(app_user_id=user.id, settings_payload=settings_payload, overrides={})
        except Exception:  # noqa: BLE001 - overview must stay available if universe diagnostics fail.
            universe = {"symbols": [], "watchlist_name": None}
        window = self._scheduler_window(settings_payload=settings_payload, now=now)
        already_ran = self.profile_repo.scheduled_run_for_window(
            app_user_id=user.id, agent_profile_id=row.id, window_key=str(window.get("window_key") or "")
        ) is not None
        next_run = self._next_scheduled_candidate(settings_payload=settings_payload, now=now, already_ran_window=already_ran)
        latest = self.profile_repo.latest_run(app_user_id=user.id, agent_profile_id=row.id)
        last_status = (
            "never_run"
            if latest is None
            else "running"
            if latest.status == "running"
            else "failed"
            if latest.status in {"error", "failed"}
            else "success"
            if latest.status == "completed"
            else str(latest.status)
        )
        run_rows = self.profile_repo.list_runs(app_user_id=user.id, agent_profile_id=row.id, limit=100)
        links = self._agent_links_from_runs(run_rows)
        trades = [
            trade
            for trade in self.paper_repo.list_trades(app_user_id=user.id, limit=500)
            if self._is_agent_trade(trade, links=links)
        ]
        realized = round(sum(self._safe_float(getattr(trade, "realized_pnl", 0.0)) or 0.0 for trade in trades), 2)
        open_positions = [
            position
            for position in self.paper_repo.list_positions(app_user_id=user.id, status="open", limit=100)
            if self._is_agent_position(position, links=links)
        ]
        agent_type = str(settings_payload.get("agent_type") or "standard")
        # Phase 12 — directional capability + current side/last action for the card.
        directional = self._profile_is_directional(agent_type=agent_type, settings_payload=settings_payload)
        own_sides = {str(getattr(p, "side", "") or "").lower() for p in open_positions}
        own_sides.discard("")
        current_position_side = (
            "flat" if not own_sides else next(iter(own_sides)) if len(own_sides) == 1 else "mixed"
        )
        return {
            "profile_uid": row.profile_uid,
            "agent_profile_id": row.id,
            "name": row.name,
            "agent_type": agent_type,
            "is_default": bool(row.is_default),
            "enabled": bool(row.enabled) and not bool(row.paused) and not bool(row.kill_switch_enabled),
            "enabled_setting": bool(row.enabled),
            "paused": bool(row.paused),
            "kill_switch_enabled": bool(row.kill_switch_enabled),
            "daily_run_time": settings_payload.get("daily_run_time"),
            "timezone": settings_payload.get("timezone"),
            "next_scheduled_run_at": next_run.isoformat() if next_run else None,
            "last_run_status": last_status,
            "last_run_at": latest.created_at.isoformat() if latest and latest.created_at else None,
            "last_action": self._last_action_label(latest),
            "universe_source": settings_payload.get("universe_source"),
            "watchlist_name": universe.get("watchlist_name"),
            "resolved_symbol_count": len(universe.get("symbols") or []),
            "strategy_count": len(settings_payload.get("strategy_families") or []) if agent_type in {"standard", "hybrid"} else None,
            "haco_direction_mode": settings_payload.get("haco_direction_mode") if agent_type in {"haco_direction", "hybrid"} else None,
            "true_momentum_trigger_mode": settings_payload.get("true_momentum_trigger_mode") if agent_type in {"true_momentum", "hybrid"} else None,
            # Directional execution capability (Phase 12).
            "directional": directional,
            "allow_shorts": bool(settings_payload.get("allow_shorts", False)),
            "allow_direction_flip": bool(settings_payload.get("allow_direction_flip", True)),
            "current_position_side": current_position_side,
            "open_position_count": len(open_positions),
            "realized_pnl": realized,
            "trade_count": len(trades),
            "paperOnly": True,
        }

    def _last_action_label(self, latest) -> str | None:
        """Human-readable label of the most recent executed open/close/flip action."""
        if latest is None:
            return None
        response = self._run_response(latest)
        intents = response.get("intents") if isinstance(response.get("intents"), list) else []
        executed = [
            i for i in intents
            if isinstance(i, dict) and i.get("intent") in {"OPEN_PAPER", "CLOSE_PAPER"} and i.get("status") == "executed"
        ]
        if not executed:
            return None
        last = executed[-1]
        reason = str(last.get("reason") or "")
        side = str(last.get("side") or "").lower()
        if reason in {"flipped_long_to_short", "flipped_short_to_long"}:
            return reason.replace("_", " ")
        if last.get("intent") == "OPEN_PAPER":
            return f"opened {side}".strip() if side else "opened"
        return f"closed {side}".strip() if side else "closed"

    def resolve_universe(self, *, app_user_id: int, settings_payload: dict[str, object], overrides: dict[str, object]) -> dict[str, object]:
        explicit_source = overrides.get("universe_source")
        raw_source = str(overrides.get("source") or "").strip().lower()
        if not explicit_source and raw_source in {"manual", "watchlist", "watchlist_plus_manual", "all_active"}:
            explicit_source = raw_source
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

    @staticmethod
    def _safe_error_summary(value: object) -> str:
        text = str(value or "agent_scheduler_error").strip() or "agent_scheduler_error"
        for marker in ("Authorization:", "Bearer ", "access_token", "refresh_token", "client_secret", "TWILIO_AUTH_TOKEN"):
            if marker.lower() in text.lower():
                return "redacted_sensitive_error"
        return text[:240]

    @staticmethod
    def _parse_iso_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _run_source_from_request(request: dict[str, object]) -> str:
        raw_source = str(request.get("source") or "").strip().lower()
        if raw_source in {AGENT_MODE_SOURCE_MANUAL, AGENT_MODE_SOURCE_SCHEDULED, AGENT_MODE_SOURCE_DIAGNOSTIC}:
            return raw_source
        trigger = str(request.get("trigger") or "").strip().lower()
        if trigger in {"daily_scheduler", "scheduled_agent"}:
            return AGENT_MODE_SOURCE_SCHEDULED
        if trigger in {"scheduler_diagnostic", "diagnostic"}:
            return AGENT_MODE_SOURCE_DIAGNOSTIC
        return AGENT_MODE_SOURCE_MANUAL

    @staticmethod
    def _notifications_suppressed(request: dict[str, object]) -> bool:
        for key in ("no_notifications", "suppress_notifications", "notifications_disabled"):
            value = request.get(key)
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "on"}:
                return True
        return False

    def _scheduler_window(self, *, settings_payload: dict[str, object], now: datetime) -> dict[str, object]:
        zone_name = str(settings_payload.get("timezone") or "America/New_York")
        zone = self._setting_zone(zone_name)
        current_utc = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        local_now = current_utc.astimezone(zone)
        hour, minute = self._parse_run_time(settings_payload.get("daily_run_time"))
        due_local = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        due_utc = due_local.astimezone(timezone.utc)
        window_key = f"{local_now.date().isoformat()}|{hour:02d}:{minute:02d}|{zone_name}"
        # Phase 11 — qualify the window by profile so two profiles of the same user
        # at the same daily time get independent scheduler claims and dedup keys.
        profile_uid = settings_payload.get("profile_uid")
        if profile_uid:
            window_key = f"{window_key}|{profile_uid}"
        return {
            "timezone": zone_name,
            "local_date": local_now.date().isoformat(),
            "local_now": local_now.isoformat(),
            "run_time": f"{hour:02d}:{minute:02d}",
            "due_at": due_utc,
            "due_at_iso": due_utc.isoformat(),
            "due_at_local": due_local.isoformat(),
            "due_now": local_now >= due_local,
            "window_key": window_key,
        }

    def _next_scheduled_candidate(
        self,
        *,
        settings_payload: dict[str, object],
        now: datetime,
        already_ran_window: bool,
    ) -> datetime | None:
        if (
            not bool(settings_payload.get("enabled"))
            or bool(settings_payload.get("paused"))
            or bool(settings_payload.get("kill_switch_enabled"))
        ):
            return None
        window = self._scheduler_window(settings_payload=settings_payload, now=now)
        due_at = window["due_at"]
        if isinstance(due_at, datetime) and (not bool(window["due_now"]) or not already_ran_window):
            return due_at
        zone = self._setting_zone(str(settings_payload.get("timezone") or "America/New_York"))
        tomorrow_local = due_at.astimezone(zone) + timedelta(days=1) if isinstance(due_at, datetime) else now.astimezone(zone) + timedelta(days=1)
        return tomorrow_local.astimezone(timezone.utc)

    def _next_eligible_trading_run(
        self,
        *,
        settings_payload: dict[str, object],
        now: datetime,
        already_ran_window: bool,
    ) -> str | None:
        """Next scheduled run that lands on an open US trading day (ISO 8601 UTC).

        Walks the profile's next scheduled candidate forward (preserving the local
        run time across day boundaries) until it falls on a day the US market is
        open, so the operator sees when the agent will actually next trade.
        """
        candidate = self._next_scheduled_candidate(
            settings_payload=settings_payload, now=now, already_ran_window=already_ran_window
        )
        if candidate is None:
            return None
        zone = self._setting_zone(str(settings_payload.get("timezone") or "America/New_York"))
        market_zone = ZoneInfo(market_session.MARKET_TIMEZONE)
        for _ in range(14):  # bounded; covers any weekend+holiday cluster
            if market_session.is_trading_day(candidate.astimezone(market_zone).date()):
                return candidate.astimezone(timezone.utc).isoformat()
            next_local = candidate.astimezone(zone) + timedelta(days=1)
            candidate = next_local.astimezone(timezone.utc)
        return candidate.astimezone(timezone.utc).isoformat()

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

    def schedule_status(self, *, user, profile_uid=None, profile_id=None) -> dict[str, object]:
        row = self._resolve_profile_or_404(user=user, profile_uid=profile_uid, profile_id=profile_id)
        settings_payload = self.serialize_profile(row)
        latest = self.profile_repo.latest_run(app_user_id=user.id, agent_profile_id=row.id)
        latest_scheduled = self.profile_repo.latest_scheduled_run(app_user_id=user.id, agent_profile_id=row.id)
        now = utc_now()
        window = self._scheduler_window(settings_payload=settings_payload, now=now)
        already_ran_window = self.profile_repo.scheduled_run_for_window(
            app_user_id=user.id,
            agent_profile_id=row.id,
            window_key=str(window.get("window_key") or ""),
        ) is not None
        next_run = self._next_scheduled_candidate(
            settings_payload=settings_payload,
            now=now,
            already_ran_window=already_ran_window,
        )
        latest_payload = self._run_response(latest) if latest else {}
        summary = latest_payload.get("summary") if isinstance(latest_payload.get("summary"), dict) else {}
        latest_scheduled_payload = self._run_response(latest_scheduled) if latest_scheduled else {}
        scheduled_summary = (
            latest_scheduled_payload.get("summary")
            if isinstance(latest_scheduled_payload.get("summary"), dict)
            else {}
        )
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
        scheduler_checked_at = row.scheduler_last_checked_at
        if scheduler_checked_at and scheduler_checked_at.tzinfo is None:
            scheduler_checked_at = scheduler_checked_at.replace(tzinfo=timezone.utc)
        scheduler_age_seconds = (
            int(max(0.0, (now - scheduler_checked_at).total_seconds()))
            if scheduler_checked_at
            else None
        )
        scheduler_health = "unknown"
        if scheduler_checked_at:
            if row.scheduler_last_check_result == "error":
                scheduler_health = "degraded"
            elif scheduler_age_seconds is not None and scheduler_age_seconds > AGENT_SCHEDULER_HEALTH_STALE_SECONDS:
                scheduler_health = "stale"
            else:
                scheduler_health = "ok"
        try:
            universe = self.resolve_universe(app_user_id=user.id, settings_payload=settings_payload, overrides={})
        except Exception as exc:  # noqa: BLE001 - status should stay available if universe diagnostics fail.
            universe = {
                "symbols": [],
                "source": settings_payload.get("universe_source") or "unknown",
                "source_status": "error",
                "reason": self._safe_error_summary(exc),
                "watchlist_id": settings_payload.get("default_watchlist_id"),
                "watchlist_name": None,
            }
        warnings = list(latest_payload.get("warnings") or []) if isinstance(latest_payload, dict) else []
        due_now = bool(window.get("due_now")) and not already_ran_window and bool(settings_payload.get("enabled")) and not bool(settings_payload.get("paused")) and not bool(settings_payload.get("kill_switch_enabled"))
        return {
            "agent_enabled": bool(settings_payload.get("enabled")) and not bool(settings_payload.get("paused")) and not bool(settings_payload.get("kill_switch_enabled")),
            "agent_profile_id": row.id,
            "agent_profile_uid": row.profile_uid,
            "agent_profile_name": row.name,
            "agent_type": settings_payload.get("agent_type"),
            "is_default": bool(getattr(row, "is_default", False)),
            "configured_timezone": settings_payload.get("timezone"),
            "configured_daily_run_time": settings_payload.get("daily_run_time"),
            "current_server_time": now.isoformat(),
            "current_server_timezone": "UTC",
            "next_scheduled_run_at": next_run.isoformat() if next_run else None,
            "seconds_until_next_run": int(max(0.0, (next_run - now).total_seconds())) if next_run else None,
            "scheduler_health": scheduler_health,
            "scheduler_last_checked_at": scheduler_checked_at.isoformat() if scheduler_checked_at else None,
            "scheduler_last_check_result": row.scheduler_last_check_result,
            "scheduler_last_check_reason": row.scheduler_last_check_reason,
            "scheduler_last_due_at": row.scheduler_last_due_at.isoformat() if row.scheduler_last_due_at else None,
            "scheduler_last_run_id": row.scheduler_last_run_id,
            "scheduler_last_window_key": row.scheduler_last_window_key,
            "scheduler_check_age_seconds": scheduler_age_seconds,
            "scheduler_expected_interval_seconds": 300,
            "scheduler_stale_after_seconds": AGENT_SCHEDULER_HEALTH_STALE_SECONDS,
            "scheduler_due_now": due_now,
            "scheduler_current_window_key": window.get("window_key"),
            "scheduler_current_due_at": window.get("due_at_iso"),
            "scheduler_current_due_at_local": window.get("due_at_local"),
            "scheduler_already_ran_current_window": already_ran_window,
            "selected_watchlist_id": universe.get("watchlist_id"),
            "selected_watchlist_name": universe.get("watchlist_name"),
            "resolved_symbol_count": len(universe.get("symbols") or []),
            "resolved_symbols_preview": list(universe.get("symbols") or [])[:10],
            "universe_source": universe.get("source"),
            "universe_source_status": universe.get("source_status"),
            "universe_skip_reason": universe.get("reason"),
            "last_run_started_at": latest.created_at.isoformat() if latest and latest.created_at else None,
            "last_run_completed_at": latest.completed_at.isoformat() if latest and latest.completed_at else None,
            "last_run_status": status,
            "last_skip_reason": last_skip_reason,
            "last_error_summary": (warnings[0] if warnings else None) if status != "success" else None,
            "last_run_id": latest.run_id if latest else None,
            "last_run_trade_count": int(summary.get("totalExecutedActions", summary.get("executedOrderCount", 0)) or 0) if isinstance(summary, dict) else 0,
            "last_run_position_review_count": len(latest_payload.get("positionReviews") or []) if isinstance(latest_payload, dict) else 0,
            "last_run_blocked_count": int(summary.get("blockedActions", 0) or 0) if isinstance(summary, dict) else 0,
            "last_scheduled_run_id": latest_scheduled.run_id if latest_scheduled else None,
            "last_scheduled_run_started_at": latest_scheduled.created_at.isoformat() if latest_scheduled and latest_scheduled.created_at else None,
            "last_scheduled_run_completed_at": latest_scheduled.completed_at.isoformat() if latest_scheduled and latest_scheduled.completed_at else None,
            "last_scheduled_run_status": (
                "never_run"
                if latest_scheduled is None
                else "failed"
                if latest_scheduled.status in {"error", "failed"}
                else "success"
                if latest_scheduled.status == "completed"
                else str(latest_scheduled.status)
            ),
            "last_scheduled_skip_reason": (
                scheduled_summary.get("skipReason") or scheduled_summary.get("universeSkipReason")
                if isinstance(scheduled_summary, dict)
                else None
            ),
            "last_scheduled_trade_count": int(scheduled_summary.get("totalExecutedActions", scheduled_summary.get("executedOrderCount", 0)) or 0) if isinstance(scheduled_summary, dict) else 0,
            "in_progress": status == "running",
            "lock_diagnostics": {
                "available": False,
                "reason": "database_lock_not_configured",
                "duplicate_guard": "scheduled_window_key_plus_scheduler_claim",
                "current_window_key": window.get("window_key"),
            },
            "scheduler_source": "external-cli-loop",
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
            if intent.get("intent") != "CASH_NO_TRADE" and intent.get("status") in {"blocked", "skipped"}
        ]
        trigger_reviews = [
            intent for intent in final_intents
            if intent.get("intent") == "CASH_NO_TRADE" and intent.get("status") == "review_only"
        ]
        # Ownership boundary: positions this profile does NOT own (another agent's
        # or a manual trade) that were close-worthy are reviewed, never closed.
        ownership_block_reasons = {"blocked_foreign_agent_position", "blocked_manual_position"}
        reviewed_external = [
            intent for intent in trigger_reviews
            if str(intent.get("reason")) in ownership_block_reasons
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
        # Phase 12 — directional action buckets for the digest (side-aware).
        def _side(intent: dict[str, object]) -> str:
            return str(intent.get("side") or "").lower()
        opened_long = [i for i in paper_opens if _side(i) == "long"]
        opened_short = [i for i in paper_opens if _side(i) == "short"]
        flip_reasons = {"flipped_long_to_short", "flipped_short_to_long"}
        flips = [i for i in paper_closes if str(i.get("reason")) in flip_reasons]
        flipped_long_to_short = [i for i in flips if str(i.get("reason")) == "flipped_long_to_short"]
        flipped_short_to_long = [i for i in flips if str(i.get("reason")) == "flipped_short_to_long"]
        non_flip_closes = [i for i in paper_closes if str(i.get("reason")) not in flip_reasons]
        closed_long = [i for i in non_flip_closes if _side(i) == "long"]
        closed_short = [i for i in non_flip_closes if _side(i) == "short"]
        return {
            "positionsBeforeCount": positions_before_count,
            "positionsAfterCount": positions_after_count,
            "paperOpensExecuted": len(paper_opens),
            "paperClosesExecuted": len(paper_closes),
            # Directional breakdown (side-aware) for the digest action buckets.
            "openedLong": len(opened_long),
            "openedShort": len(opened_short),
            "closedLong": len(closed_long),
            "closedShort": len(closed_short),
            "flippedLongToShort": len(flipped_long_to_short),
            "flippedShortToLong": len(flipped_short_to_long),
            "holds": sum(1 for intent in final_intents if intent.get("intent") == "HOLD"),
            "blockedActions": len(blocked_actions),
            "triggerReviewOnly": len(trigger_reviews),
            "reviewedExternalPositions": len(reviewed_external),
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
        profile_name: str | None = None,
        agent_type: str | None = None,
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
        reviewed = [
            self._digest_item(intent)
            for intent in final_intents
            if intent.get("intent") == "CASH_NO_TRADE" and intent.get("status") == "review_only"
        ]
        blocked = [
            self._digest_item(intent)
            for intent in final_intents
            if (intent.get("intent") == "CASH_NO_TRADE" and intent.get("status") != "review_only")
            or intent.get("status") in {"blocked", "skipped"}
        ]
        digest_summary = {
            **summary,
            "candidateCount": len(candidates),
        }
        link = f"{settings.app_base_url.rstrip('/')}/agent-mode?tab=Trades"
        watchlist_name = str(universe.get("watchlist_name") or universe.get("source_label") or "manual symbols")
        type_label = str(agent_type or "standard").replace("_", " ")
        profile_label = f"{profile_name} ({type_label})" if profile_name else "Agent Mode"
        notable = [
            str(item.get("symbol") or "").upper()
            for item in opened + closed + blocked
            if str(item.get("symbol") or "").strip()
        ][:3]
        sms = (
            f"MacMarket Agent [{profile_name or 'Agent'}/{type_label}] {status_label}: "
            f"opened {summary.get('paperOpensExecuted', 0)}, "
            f"closed {summary.get('paperClosesExecuted', 0)}, blocked {summary.get('blockedActions', 0)}, "
            f"reviewed {summary.get('triggerReviewOnly', 0)}."
        )
        if notable:
            sms += f" Notable: {', '.join(notable)}."
        sms += f" {link}"
        if len(sms) > 320:
            sms = sms[:282].rstrip() + " See Agent Mode for details."
        text_lines = [
            "MacMarket Trader - Agent Mode Run Summary",
            f"Agent: {profile_name or 'Agent Mode'}",
            f"Type: {type_label}",
            f"Run: {run_id}",
            f"Status: {status_label}",
            f"Timestamp: {response.get('asOf')}",
            f"Watchlist: {watchlist_name}",
            f"Candidates reviewed: {len(candidates)}",
            f"Positions reviewed: {summary.get('positionsBeforeCount', 0)}",
            f"Opened (own): {summary.get('paperOpensExecuted', 0)} (long {summary.get('openedLong', 0)} / short {summary.get('openedShort', 0)})",
            f"Closed (own): {summary.get('paperClosesExecuted', 0)} (long {summary.get('closedLong', 0)} / short {summary.get('closedShort', 0)})",
            f"Flipped: long→short {summary.get('flippedLongToShort', 0)} / short→long {summary.get('flippedShortToLong', 0)}",
            f"Held/reviewed: {summary.get('holds', 0)}",
            f"Reviewed (no trade): {summary.get('triggerReviewOnly', 0)}",
            f"Reviewed (not owned - another agent/manual, never closed): {summary.get('reviewedExternalPositions', 0)}",
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
            reviewed=reviewed,
            profile_name=profile_name,
            agent_type=agent_type,
            app_url=settings.app_base_url,
        )
        return {
            "event_type": event_type,
            "status": status_label,
            "title": f"MacMarket Agent · {profile_label} — {status_label} summary",
            "text": "\n".join(text_lines),
            "sms": sms,
            "html": html,
            "payload": {
                "paperOnly": True,
                "executionMode": "paper",
                "digest": True,
                "runId": run_id,
                "status": status_label,
                "agentProfileId": response.get("agentProfileId"),
                "agentProfileName": profile_name,
                "agentType": agent_type,
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

    def _paper_opens_today(self, *, app_user_id: int, agent_profile_id: int | None, timezone_name: str, now: datetime) -> int:
        zone = self._setting_zone(timezone_name)
        local_today = now.astimezone(zone).date()
        count = 0
        for row in self.profile_repo.list_runs(app_user_id=app_user_id, agent_profile_id=agent_profile_id, limit=100, dry_run=False):
            created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
            if created.astimezone(zone).date() != local_today:
                continue
            payload = self._run_response(row)
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            count += int(summary.get("paperOpensExecuted", 0) or 0)
        return count

    def _position_intent(
        self,
        review: dict[str, object],
        *,
        settings_payload: dict[str, object],
        dry_run: bool,
        owner_kind: str = "own",
    ) -> dict[str, object] | None:
        action = str(review.get("action_classification") or "review_unavailable")
        allow_closes = bool(settings_payload.get("allow_closes", True))
        allow_scale = bool(settings_payload.get("allow_scale_resize", False))
        close_actions = {"stop_triggered", "invalidated", "time_stop_exit", "target_reached_take_profit"}
        is_close_worthy = action in close_actions
        # Ownership boundary: never close/flip a position this profile does not own.
        if owner_kind != "own":
            if not is_close_worthy:
                return None  # do not emit holds/scale reviews for others' positions
            block_reason = "blocked_manual_position" if owner_kind == "manual" else "blocked_foreign_agent_position"
            owner_label = "a manual paper trade" if owner_kind == "manual" else "another Agent Profile"
            return {
                "intent": "CASH_NO_TRADE",
                "symbol": review.get("symbol"),
                "side": review.get("side"),
                "position_id": review.get("position_id"),
                "status": "review_only",
                "review_only": True,
                "reason": block_reason,
                "position_owner": owner_kind,
                "summary": f"Review only: {review.get('symbol')} would close on {action}, but the open position belongs to {owner_label}. Agent Mode never closes positions it does not own.",
                "paper_only": True,
                "no_live_routing": True,
                "review": review,
            }
        if is_close_worthy and allow_closes:
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
            "position_owner": "own",
            "action_reason": "managed_own_position",
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

    def _review_intent(self, *, symbol: str | None, verdict, candidate: dict[str, object] | None = None) -> dict[str, object]:
        """Review-only (no-order) intent for an agent trigger that did not authorize a long.

        Modeled as CASH_NO_TRADE with status ``review_only`` so it never reaches the
        paper lifecycle, is excluded from ``blockedActions``, and surfaces in the
        digest's separate 'Reviewed (no trade)' bucket. Used for bearish/short-bias
        and exit-caution reads — paper shorting is never created.
        """
        return {
            "intent": "CASH_NO_TRADE",
            "symbol": symbol,
            "status": "review_only",
            "reason": verdict.reason,
            "summary": verdict.summary,
            "primary_trigger": verdict.primary_trigger,
            "candidate": candidate,
            "paper_only": True,
            "no_live_routing": True,
            "review_only": True,
        }

    # ── Phase 12 — directional (bidirectional) lifecycle helpers ──────────────
    @staticmethod
    def _profile_is_directional(*, agent_type: str, settings_payload: dict[str, object]) -> bool:
        """A profile uses the bidirectional decision engine when it is an ATR agent
        (always directional) or any agent that has explicitly enabled shorts.

        Standard stays long-only and backward-compatible; HACO/True Momentum/Hybrid
        only get the directional lifecycle once ``allow_shorts`` is turned on.
        """
        if str(agent_type or "").strip().lower() == "atr_trailing_stop":
            return True
        return bool(settings_payload.get("allow_shorts"))

    @staticmethod
    def _directional_flags(settings_payload: dict[str, object]) -> dict[str, bool]:
        return {
            "allow_shorts": bool(settings_payload.get("allow_shorts", False)),
            "allow_direction_flip": bool(settings_payload.get("allow_direction_flip", True)),
            "close_opposite_before_open": bool(settings_payload.get("close_opposite_before_open", True)),
            "close_on_opposite_signal": bool(settings_payload.get("close_on_opposite_signal", True)),
            "hedge_allowed": bool(settings_payload.get("hedge_allowed", False)),
        }

    def _execute_directional_short_open(
        self,
        *,
        intent: dict[str, object],
        candidate: dict[str, object],
        user,
        bars_by_symbol: dict[str, tuple[list[Any], str, bool]],
        timeframe: str,
        settings_payload: dict[str, object],
        open_positions: list[object],
        agent_profile_id: int | None = None,
    ) -> dict[str, object]:
        """Open a paper SHORT for a directional agent (allow_shorts only).

        Risk-sized off the indicator's protective stop (ATR trailing stop when
        available) instead of the long-biased deterministic recommendation engine,
        then routed through the same paper broker/OMS. Paper-only; never live.
        """
        symbol = str(candidate.get("symbol") or "").upper()
        bars_tuple = bars_by_symbol.get(symbol)
        if not bars_tuple:
            return {**intent, "status": "skipped", "execution_error": "bars_unavailable"}
        bars, source, fallback_mode = bars_tuple
        # Entry = latest mark (snapshot close, else last bar close).
        entry = None
        try:
            snapshot = workflow.market_data_service.latest_snapshot(symbol, timeframe)
            entry = self._safe_float(getattr(snapshot, "close", None))
        except Exception:  # noqa: BLE001 - fall back to the last bar close.
            entry = None
        if (entry is None or entry <= 0) and bars:
            entry = self._safe_float(getattr(bars[-1], "close", None))
        if entry is None or entry <= 0:
            return {**intent, "status": "skipped", "execution_error": "mark_unavailable"}
        # Protective stop: prefer the indicator stop (ATR); else re-derive from ATR;
        # else a conservative fallback. A short needs a stop ABOVE entry.
        stop = self._safe_float(intent.get("protective_stop"))
        if stop is None or stop <= entry:
            try:
                stop = self._safe_float(agent_triggers.evaluate_atr_signal(bars, profile=settings_payload, timeframe=timeframe).protective_stop)
            except Exception:  # noqa: BLE001
                stop = None
        if stop is None or stop <= entry:
            stop = entry * 1.05  # fallback: 5% protective stop above entry
        risk_per_share = stop - entry
        if risk_per_share <= 0:
            return {**intent, "status": "skipped", "execution_error": "protective_stop_unusable"}
        risk_dollars = workflow._effective_risk_dollars(user)
        max_notional = workflow._effective_paper_max_order_notional(user)
        if not (isinstance(risk_dollars, (int, float)) and risk_dollars > 0) or not (max_notional and max_notional > 0):
            return {**intent, "status": "blocked", "execution_error": "agent_sizing_unavailable"}
        risk_shares = int(max(0, math.floor(risk_dollars / risk_per_share)))
        notional_cap_shares = int(max(0, math.floor(max_notional / entry)))
        final_shares = min(risk_shares, notional_cap_shares)
        sizing_plan = self._apply_agent_sizing_caps(
            sizing_plan={
                "recommended_shares": risk_shares,
                "final_order_shares": final_shares,
                "operator_override_shares": None,
                "max_paper_order_notional": workflow._round_money(max_notional),
                "notional_cap_shares": notional_cap_shares,
                "estimated_notional": workflow._round_money(final_shares * entry),
                "risk_at_stop": workflow._round_money(final_shares * risk_per_share),
                "sizing_mode": "atr_risk_and_notional_capped",
                "notional_cap_reduced": final_shares < risk_shares,
                "protective_stop": round(stop, 4),
                "risk_per_share": round(risk_per_share, 4),
            },
            settings_payload=settings_payload,
            user=user,
            open_positions=open_positions,
        )
        capped_shares = int(sizing_plan.get("final_order_shares") or 0)
        if capped_shares <= 0:
            return {**intent, "status": "blocked", "execution_error": sizing_plan.get("agent_sizing_block_reason") or "agent_sizing_blocked", **sizing_plan}
        recommendation_id = f"agentdir_{uuid4().hex[:12]}"
        order_intent = OrderIntent(
            recommendation_id=recommendation_id,
            symbol=symbol,
            side=Direction.SHORT,
            shares=capped_shares,
            limit_price=round(entry, 4),
        )
        order, fill = workflow.paper_broker.execute(order_intent)
        workflow.recommendation_service.persist_order(
            order,
            notes=(
                "agent_mode_paper_short_open"
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
                recommendation_id=None,
                replay_run_id=None,
                order_id=order.order_id,
                agent_profile_id=agent_profile_id,
            )
        return {
            **intent,
            "status": "executed",
            "outcome": "opened_paper_short",
            "side": "short",
            "order_id": order.order_id,
            "position_id": position.id if position is not None else None,
            "recommendation_id": recommendation_id,
            "shares": order.shares,
            "limit_price": self._round_price(order.limit_price),
            "fill_price": self._round_price(fill.fill_price),
            "protective_stop": round(stop, 4),
            "market_data_source": source,
            "fallback_mode": fallback_mode,
            "paper_only": True,
            "no_live_routing": True,
            **sizing_plan,
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
            agent_profile_id=getattr(position, "agent_profile_id", None),
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
        agent_profile_id: int | None = None,
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
        # Paper-long-only guard: Agent Mode never routes a paper short. The
        # deterministic setup engine can resolve Direction.SHORT (e.g. a failed-
        # event fade in a risk-off regime), and the user-approval override would
        # otherwise approve it. If the resolved side is not long, surface a
        # review-only no-order intent instead of building/routing a short order.
        resolved_side = str(getattr(rec.side, "value", rec.side) or "").lower()
        if resolved_side != "long":
            return {
                **intent,
                "intent": "CASH_NO_TRADE",
                "status": "review_only",
                "review_only": True,
                "side": resolved_side or None,
                "reason": "paper_short_not_supported",
                "summary": (
                    "Review only: deterministic recommendation resolved "
                    f"{resolved_side or 'non-long'}; paper shorting is not supported, "
                    "so Agent Mode never routes this as a paper order."
                ),
                "recommendation_id": rec.recommendation_id,
                "paper_only": True,
                "no_live_routing": True,
            }
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
                agent_profile_id=agent_profile_id,
            )
        return {
            **intent,
            "status": "executed",
            "outcome": "opened_paper_long",
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
        # Phase 12 — side-aware unrealized P&L. Long = (mark-entry)*qty; short =
        # (entry-mark)*qty. Recompute for paper shorts (the review helper assumes long).
        side = str(payload.get("side") or "long").lower()
        if side == "short" and qty is not None and avg_entry_price is not None and mark_price is not None:
            unrealized_pnl = (avg_entry_price - mark_price) * qty
            return_pct = ((avg_entry_price - mark_price) / avg_entry_price * 100.0) if avg_entry_price else return_pct
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
            "agentProfileId": getattr(row, "agent_profile_id", None),
            "agentProfileName": getattr(row, "agent_profile_name", None),
            "agentType": getattr(row, "agent_type", None),
            "triggerReviewOnly": int(summary.get("triggerReviewOnly", 0) or 0),
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

    def _agent_links_from_runs(self, rows: list[object], *, opens_only: bool = False) -> dict[str, dict[object, dict[str, object]]]:
        """Map order/position/trade ids to the run that referenced them.

        With ``opens_only`` only OPEN_PAPER intents contribute, so ownership follows
        the open: a paper trade/position attributes to the profile whose run opened
        it even if a different profile's run later closed it (a paper trade's
        ``order_id`` equals its opening order's id).
        """
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
                if opens_only and intent.get("intent") != "OPEN_PAPER":
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
    def _is_agent_trade(row, *, links: dict[str, dict[object, dict[str, object]]], strict: bool = False) -> bool:
        # strict (profile-scoped) ownership ignores the global close_reason marker so
        # a trade attributes only to the profile whose OPEN links contain it.
        if not strict:
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
    def _is_agent_position(row, *, links: dict[str, dict[object, dict[str, object]]], strict: bool = False) -> bool:
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
        profile_uid=None,
        profile_id=None,
    ) -> dict[str, object]:
        limit = self._coerce_limit(limit, default=50, maximum=100)
        now = utc_now()
        start, end, timeframe_key = self._range_for_timeframe(timeframe, now=now)
        agent_profile_id = self._optional_profile_id(user=user, profile_uid=profile_uid, profile_id=profile_id)
        rows = [
            row
            for row in self.profile_repo.list_runs(app_user_id=user.id, agent_profile_id=agent_profile_id, limit=100, status=status, dry_run=dry_run)
            if self._in_range(row.created_at, start=start, end=end)
        ][:limit]
        return {
            "items": [self._serialize_run_history_row(row) for row in rows],
            "limit": limit,
            "timeframe": timeframe_key,
            "agentProfileId": agent_profile_id,
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
        profile_uid=None,
        profile_id=None,
    ) -> dict[str, object]:
        limit = self._coerce_limit(limit, default=100, maximum=250)
        if source and source != "agent_mode":
            return {"items": [], "limit": limit, "timeframe": timeframe or "all_time", "source": source, "paperOnly": True, "executionMode": "paper"}
        now = utc_now()
        start, end, timeframe_key = self._range_for_timeframe(timeframe, now=now)
        agent_profile_id = self._optional_profile_id(user=user, profile_uid=profile_uid, profile_id=profile_id)
        scoped = agent_profile_id is not None
        run_rows = self.profile_repo.list_runs(app_user_id=user.id, agent_profile_id=agent_profile_id, limit=200 if scoped else 100)
        links = self._agent_links_from_runs(run_rows, opens_only=scoped)
        rows = self.paper_repo.list_trades(app_user_id=user.id, limit=limit)
        items = [
            self._serialize_agent_trade(row, links=links)
            for row in rows
            if self._is_agent_trade(row, links=links, strict=scoped)
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
            "agentProfileId": agent_profile_id,
            "paperOnly": True,
            "executionMode": "paper",
        }

    def performance(self, *, user, timeframe: str | None = None, source: str | None = "agent_mode", profile_uid=None, profile_id=None) -> dict[str, object]:
        agent_profile_id = self._optional_profile_id(user=user, profile_uid=profile_uid, profile_id=profile_id)
        scoped = agent_profile_id is not None
        profile = (
            self._resolve_profile_or_404(user=user, profile_uid=profile_uid, profile_id=profile_id)
            if scoped
            else self.profile_repo.get_default_profile(app_user_id=user.id)
        )
        settings_payload = self.serialize_profile(profile)
        now = utc_now()
        start, end, timeframe_key = self._range_for_timeframe(timeframe, now=now)
        if source and source != "agent_mode":
            run_rows: list[object] = []
        else:
            run_rows = [
                row
                for row in self.profile_repo.list_runs(app_user_id=user.id, agent_profile_id=agent_profile_id, limit=100)
                if self._in_range(row.created_at, start=start, end=end)
            ]
        links = self._agent_links_from_runs(run_rows, opens_only=scoped)
        trade_rows = [
            row
            for row in self.paper_repo.list_trades(app_user_id=user.id, limit=500)
            if self._is_agent_trade(row, links=links, strict=scoped)
            and self._in_range(row.closed_at or row.opened_at, start=start, end=end)
        ]
        trade_items = [self._serialize_agent_trade(row, links=links) for row in trade_rows]
        all_open_positions = self.paper_repo.list_positions(app_user_id=user.id, status="open", limit=100)
        open_positions = [
            row
            for row in all_open_positions
            if (source or "agent_mode") == "agent_mode" and self._is_agent_position(row, links=links, strict=scoped)
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
            "agentProfileId": agent_profile_id,
            "agentProfileName": getattr(profile, "name", None),
            "agentType": settings_payload.get("agent_type"),
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

    def send_test_notification(self, *, user, channel: str | None = None, profile_uid=None, profile_id=None) -> dict[str, object]:
        profile = self._resolve_profile_or_404(user=user, profile_uid=profile_uid, profile_id=profile_id)
        settings_payload = self.serialize_profile(profile)
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

    @staticmethod
    def _equities_strategy_names() -> list[str]:
        return [entry.display_name for entry in workflow.list_strategies(MarketMode.EQUITIES)]

    def _ranking_strategies_for_profile(self, settings_payload: dict[str, object]) -> list[str]:
        """Resolve the strategy display names passed to the ranking engine.

        Standard/Hybrid use the profile's selected ``strategy_families`` (stored as
        stable strategy_ids), falling back to the legacy first-three behavior when
        none are selected. HACO/True Momentum rank across all equities strategies so
        every universe symbol gets a sized candidate for the indicator gate to act
        on. Ranking/scoring itself is unchanged — this only chooses which strategies
        are scored.
        """
        agent_type = str(settings_payload.get("agent_type") or "standard").strip().lower()
        all_names = self._equities_strategy_names()
        if agent_type in {"standard", "hybrid"}:
            names: list[str] = []
            for raw_id in list(settings_payload.get("strategy_families") or []):
                entry = get_strategy_by_id(str(raw_id), market_mode=MarketMode.EQUITIES)
                if entry is not None and entry.display_name not in names:
                    names.append(entry.display_name)
            if names:
                return names
            # Legacy parity: the pre-Phase-11 call used list_strategies(EQUITIES)[:3].
            legacy: list[str] = []
            for raw_id in DEFAULT_STANDARD_STRATEGY_IDS:
                entry = get_strategy_by_id(raw_id, market_mode=MarketMode.EQUITIES)
                if entry is not None:
                    legacy.append(entry.display_name)
            return legacy or all_names[:3]
        return all_names or self._equities_strategy_names()

    def _resolve_run_profile(self, *, user, request: dict[str, object]):
        """Resolve the Agent Profile for a run, defaulting to the user's default.

        An explicit-but-unknown profile id/uid is a 404 (never a silent fallback);
        user scoping is enforced by the repository.
        """
        profile_uid = request.get("profile_uid") or request.get("profile")
        raw_id = request.get("profile_id") or request.get("agent_profile_id")
        profile_id = int(raw_id) if str(raw_id or "").strip().isdigit() else None
        profile = self.profile_repo.resolve_profile(
            app_user_id=user.id,
            profile_uid=str(profile_uid) if profile_uid else None,
            profile_id=profile_id,
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="agent_profile_not_found")
        return profile

    def run(self, *, user, request: dict[str, object] | None = None) -> dict[str, object]:
        request = dict(request or {})
        run_source = self._run_source_from_request(request)
        request["source"] = run_source
        suppress_notifications = self._notifications_suppressed(request)
        if not self._user_is_approved(user):
            raise HTTPException(status_code=403, detail=f"Approval status is {getattr(user, 'approval_status', 'unknown')}")
        mode = str(request.get("mode") or request.get("execution_mode") or "paper").strip().lower()
        if mode not in {"paper", "paper_only"}:
            raise HTTPException(status_code=409, detail="Agent Mode only supports paper mode.")
        profile = self._resolve_run_profile(user=user, request=request)
        settings_row = profile
        settings_payload = self.serialize_profile(profile)
        agent_profile_id = int(getattr(profile, "id"))
        agent_profile_name = str(getattr(profile, "name", None) or "Agent Profile")
        agent_type = str(settings_payload.get("agent_type") or "standard")
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
        all_open_positions = self.paper_repo.list_positions(app_user_id=user.id, status="open", limit=100)
        # Ownership boundary: an Agent Profile manages (closes/flips) only its OWN
        # positions (agent_profile_id == this profile). A position owned by another
        # profile, or opened manually (agent_profile_id NULL), is NEVER closed — a
        # close-worthy review on it becomes a blocked_foreign_agent_position /
        # blocked_manual_position action instead.
        def _owner_kind(position) -> str:
            owner = getattr(position, "agent_profile_id", None)
            if owner is None:
                return "manual"
            return "own" if owner == agent_profile_id else "foreign_agent"

        own_open_positions = [p for p in all_open_positions if _owner_kind(p) == "own"]
        external_by_symbol: dict[str, list[object]] = {}
        for position in all_open_positions:
            if _owner_kind(position) != "own":
                external_by_symbol.setdefault(str(position.symbol or "").upper(), []).append(position)
        open_positions = own_open_positions  # sizing/cap math uses the agent's own book
        # Phase 12 — directional (bidirectional) lifecycle. Directional profiles
        # (ATR, or any agent with allow_shorts) decide open/close/flip per symbol via
        # the pure decision engine; Standard and shorts-off agents stay long-only.
        directional = self._profile_is_directional(agent_type=agent_type, settings_payload=settings_payload)
        directional_flags = self._directional_flags(settings_payload)
        own_position_by_id = {int(p.id): p for p in own_open_positions}
        flip_opens: list[dict[str, object]] = []  # symbols whose own position flips to the opposite side
        recent_rows = self.recommendation_repo.list_recent(limit=100, app_user_id=user.id)
        now = utc_now()
        # Review ALL positions (so a close-worthy external position is reported as a
        # block), but only act on owned positions.
        position_reviews = [
            workflow._build_position_review(position, app_user_id=user.id, user=user, recent_rows=recent_rows, now=now)
            for position in all_open_positions
        ]
        owner_kind_by_position_id = {int(p.id): _owner_kind(p) for p in all_open_positions}
        intents: list[dict[str, object]] = []
        for review in position_reviews:
            pid = review.get("position_id")
            owner_kind = owner_kind_by_position_id.get(int(pid)) if str(pid or "").strip().isdigit() else "manual"
            intents.append(self._position_intent(review, settings_payload=settings_payload, dry_run=dry_run, owner_kind=owner_kind or "manual"))
        intents = [intent for intent in intents if intent is not None]

        closing_symbols = {
            str(intent.get("symbol") or "").upper()
            for intent in intents
            if intent.get("intent") == "CLOSE_PAPER" and bool(settings_payload.get("allow_closes", True))
        }
        held_symbols = {
            str(position.symbol or "").upper()
            for position in own_open_positions
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

        # Phase 12 — directional own-position reconciliation. For directional
        # profiles, an OWN position that is not already closing on its protective
        # stop is re-evaluated against the directional signal: an opposing signal
        # closes it (close_on_opposite_signal) or flips it (allow_direction_flip +
        # allow_shorts for the short leg); same-direction/neutral holds. Foreign and
        # manual positions are never touched (ownership boundary). Bars for own held
        # symbols are fetched here on demand.
        if directional:
            intents_by_position_id = {
                int(i.get("position_id")): i
                for i in intents
                if str(i.get("position_id") or "").strip().isdigit()
            }
            for position in own_open_positions:
                symbol = str(position.symbol or "").upper()
                existing = intents_by_position_id.get(int(position.id))
                # Only reconcile a plain HOLD — a protective-stop CLOSE keeps priority.
                if existing is None or existing.get("intent") != "HOLD":
                    continue
                bars_tuple = bars_by_symbol.get(symbol)
                if not bars_tuple:
                    try:
                        bars_tuple = workflow._workflow_bars(symbol, limit=120, timeframe=timeframe)
                        bars_by_symbol[symbol] = bars_tuple
                    except HTTPException:
                        continue
                signal = agent_triggers.directional_signal(
                    agent_type=agent_type, profile=settings_payload, bars=bars_tuple[0], timeframe=timeframe
                )
                own_side = str(getattr(position, "side", "") or "").lower()
                decision = agent_triggers.decide_bidirectional_action(
                    signal_direction=signal.direction, fresh_flip=signal.fresh_flip,
                    own_side=own_side if own_side in {"long", "short"} else None,
                    foreign_opposing=False, **directional_flags,
                )
                action = str(decision.get("action") or "")
                existing["directional_action"] = action
                existing["primary_trigger"] = signal.primary_trigger
                if not bool(decision.get("close_own")) or not bool(settings_payload.get("allow_closes", True)):
                    continue  # held_* / no_signal / closes disabled → keep the HOLD
                existing.update({
                    "intent": "CLOSE_PAPER",
                    "status": "dry_run" if dry_run else "pending",
                    "reason": action,
                    "action_reason": "managed_own_position",
                    "summary": signal.summary,
                })
                if action in {"flipped_long_to_short", "flipped_short_to_long"}:
                    flip_opens.append({
                        "symbol": symbol,
                        "open_side": str(decision.get("open_side") or ""),
                        "protective_stop": signal.protective_stop,
                        "primary_trigger": signal.primary_trigger,
                        "summary": signal.summary,
                        "reason": action,
                    })

        strategies = self._ranking_strategies_for_profile(settings_payload)
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
        paper_opens_today = self._paper_opens_today(app_user_id=user.id, agent_profile_id=agent_profile_id, timezone_name=str(settings_payload.get("timezone") or "America/New_York"), now=now)
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
            # Decide the open SIDE. Applied AFTER deterministic ranking and BEFORE any
            # open is planned, so scoring is untouched. Directional profiles (ATR or
            # allow_shorts) use the bidirectional decision engine — own_side is None
            # here because held symbols are excluded above and own-position flips/closes
            # are reconciled separately. Everyone else keeps the Phase 11 long-only
            # eligibility gate exactly as before.
            planned_open_side: str | None = None
            open_reason = ""
            open_summary = ""
            open_primary_trigger = ""
            open_protective_stop: float | None = None
            if directional:
                signal = agent_triggers.directional_signal(
                    agent_type=agent_type, profile=settings_payload,
                    bars=bars_tuple[0] if bars_tuple else [], candidate=candidate, timeframe=timeframe,
                )
                candidate["primary_trigger"] = signal.primary_trigger
                candidate["agent_trigger_reason"] = signal.reason
                candidate["agent_trigger_detail"] = signal.detail
                # Cross-profile opposing exposure only blocks when the operator opted in
                # (default OFF → cross-agent opposing is allowed).
                prevent_opposing = bool(settings_payload.get("prevent_opposing_agent_positions_across_profiles"))
                opposing_side = "long" if signal.direction == "short" else "short" if signal.direction == "long" else None
                foreign_opposing = bool(prevent_opposing and opposing_side and any(
                    str(getattr(p, "side", "") or "").lower() == opposing_side
                    for p in external_by_symbol.get(symbol, [])
                ))
                bid = agent_triggers.decide_bidirectional_action(
                    signal_direction=signal.direction, fresh_flip=signal.fresh_flip,
                    own_side=None, foreign_opposing=foreign_opposing, **directional_flags,
                )
                action = str(bid.get("action") or "")
                if action == "opened_long":
                    planned_open_side = "long"
                elif action == "opened_short":
                    planned_open_side = "short"
                    open_protective_stop = signal.protective_stop
                elif action == "blocked_by_short_not_allowed":
                    intents.append({
                        "intent": "CASH_NO_TRADE", "symbol": symbol, "status": "review_only",
                        "review_only": True, "reason": "paper_short_not_allowed",
                        "summary": "Review only: directional signal is SHORT but allow_shorts is off for this Agent Profile (no paper short).",
                        "primary_trigger": signal.primary_trigger, "candidate": candidate,
                        "paper_only": True, "no_live_routing": True,
                    })
                    continue
                elif action == "review_opposing_external_position":
                    intents.append(self._cash_intent(
                        symbol=symbol, reason="blocked_opposing_cross_profile",
                        summary=("cash/no trade because another profile/manual holds an opposing "
                                 "position in this symbol and this Agent Profile prevents cross-profile "
                                 "opposing exposure. The other position is not closed."),
                        candidate=candidate,
                    ))
                    continue
                else:  # no_signal / held_* (no own position to hold) → nothing to open
                    continue
                open_reason = signal.reason
                open_summary = signal.summary
                open_primary_trigger = signal.primary_trigger
            else:
                # Phase 11 long-only eligibility gate (unchanged).
                verdict = agent_triggers.evaluate_agent_eligibility(
                    agent_type=agent_type,
                    profile=settings_payload,
                    bars=bars_tuple[0] if bars_tuple else [],
                    candidate=candidate,
                    timeframe=timeframe,
                )
                candidate["primary_trigger"] = verdict.primary_trigger
                candidate["agent_trigger_reason"] = verdict.reason
                candidate["agent_trigger_detail"] = verdict.detail
                if not verdict.eligible_long:
                    # Bearish/short or exit-caution reads surface as review-only intents
                    # (no order, never a paper short). Neutral/no-signal symbols skip silently.
                    if verdict.emit_review:
                        intents.append(self._review_intent(symbol=symbol, verdict=verdict, candidate=candidate))
                    continue
                # Optional cross-profile opposing-exposure guard (default OFF). When the
                # operator enables it, this profile will not open a new long while
                # ANOTHER profile (or a manual trade) holds an opposing SHORT in the same
                # symbol. It only blocks the new open — it never closes the other
                # position (ownership boundary still holds).
                if bool(settings_payload.get("prevent_opposing_agent_positions_across_profiles")):
                    opposing_external = [
                        p for p in external_by_symbol.get(symbol, [])
                        if str(getattr(p, "side", "") or "").lower() == "short"
                    ]
                    if opposing_external:
                        intents.append(self._cash_intent(
                            symbol=symbol,
                            reason="blocked_opposing_cross_profile",
                            summary=(
                                "cash/no trade because another position holds an opposing "
                                "(short) side in this symbol and this Agent Profile prevents "
                                "cross-profile opposing exposure. The other position is not closed."
                            ),
                            candidate=candidate,
                        ))
                        continue
                planned_open_side = "long"
                open_reason = verdict.reason
                open_summary = verdict.summary
                open_primary_trigger = verdict.primary_trigger
            if planned_open_side is None:
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
            open_intent: dict[str, object] = {
                "intent": "OPEN_PAPER",
                "symbol": symbol,
                "side": planned_open_side,
                "status": "dry_run" if dry_run else "pending",
                "reason": open_reason,
                "summary": open_summary,
                "primary_trigger": open_primary_trigger,
                "agent_type": agent_type,
                "candidate": candidate,
                "paper_only": True,
                "no_live_routing": True,
            }
            if planned_open_side == "short" and open_protective_stop is not None:
                open_intent["protective_stop"] = open_protective_stop
            intents.append(open_intent)

        # Phase 12 — flip open-legs. Each own position that flipped above is closed by
        # its reconciled CLOSE_PAPER intent (appended earlier, so it executes first);
        # here we append the opposite-side OPEN for the same symbol. Long legs reuse the
        # deterministic open path; short legs use the directional short open path.
        for flip in flip_opens:
            fsymbol = str(flip.get("symbol") or "").upper()
            fside = str(flip.get("open_side") or "").lower()
            if fside not in {"long", "short"} or fsymbol in planned_open_symbols:
                continue
            if not bool(settings_payload.get("allow_opens", True)):
                continue
            planned_open_symbols.add(fsymbol)
            flip_open_intent: dict[str, object] = {
                "intent": "OPEN_PAPER",
                "symbol": fsymbol,
                "side": fside,
                "status": "dry_run" if dry_run else "pending",
                "reason": str(flip.get("reason") or "flip_open"),
                "summary": str(flip.get("summary") or "Flip: open opposite side after closing the prior position."),
                "primary_trigger": str(flip.get("primary_trigger") or ""),
                "agent_type": agent_type,
                "candidate": {"symbol": fsymbol},
                "is_flip_open": True,
                "paper_only": True,
                "no_live_routing": True,
            }
            if fside == "short" and flip.get("protective_stop") is not None:
                flip_open_intent["protective_stop"] = flip.get("protective_stop")
            intents.append(flip_open_intent)

        if not any(intent.get("intent") in {"OPEN_PAPER", "CLOSE_PAPER"} for intent in intents):
            intents.append(self._cash_intent(symbol=None, reason="no_approved_paper_changes", summary="cash/no trade because no deterministic paper change passed all gates."))

        executed_order_count = 0
        final_intents: list[dict[str, object]] = []
        for intent in intents:
            if not enabled_for_execution:
                # Preserve blocked + review_only statuses through dry-run so the
                # trigger-review and blocked buckets stay honest; everything else
                # becomes a review-only dry-run intent.
                if intent.get("status") in {"blocked", "review_only"}:
                    final_intents.append(intent)
                else:
                    final_intents.append({**intent, "status": "dry_run"})
                continue
            if intent.get("intent") == "CLOSE_PAPER":
                final_intents.append(self._execute_close(intent=intent, user=user))
            elif intent.get("intent") == "OPEN_PAPER":
                if str(intent.get("side") or "long").lower() == "short":
                    # Directional paper short (allow_shorts profiles only).
                    executed = self._execute_directional_short_open(
                        intent=intent,
                        candidate=dict(intent.get("candidate") or {}),
                        user=user,
                        bars_by_symbol=bars_by_symbol,
                        timeframe=timeframe,
                        settings_payload=settings_payload,
                        open_positions=open_positions,
                        agent_profile_id=agent_profile_id,
                    )
                else:
                    executed = self._execute_open(
                        intent=intent,
                        candidate=dict(intent.get("candidate") or {}),
                        user=user,
                        bars_by_symbol=bars_by_symbol,
                        timeframe=timeframe,
                        settings_payload=settings_payload,
                        open_positions=open_positions,
                        agent_profile_id=agent_profile_id,
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
        no_universe = not (universe.get("symbols") or [])
        universe_skip_reason = (
            str(universe.get("reason") or "")
            if universe.get("source_status") in {"missing", "empty", "error"}
            else None
        ) or ("no_universe" if no_universe else None)
        scheduler_payload = request.get("scheduler") if isinstance(request.get("scheduler"), dict) else {}
        scheduled_window_key = str(
            request.get("scheduled_window_key")
            or scheduler_payload.get("window_key")
            or ""
        ) or None
        scheduled_due_at = self._parse_iso_datetime(scheduler_payload.get("due_at_iso") or scheduler_payload.get("due_at"))
        # Market-session label (the scheduler skips closed days before ever calling
        # run(); a manual dry-run may still run on a closed day but is labeled so the
        # operator knows it is off-session). Labeling only — never blocks a run.
        market_session_state = market_session.market_session_state(now)
        summary = {
            "paperOnly": True,
            "executionMode": "paper",
            "dryRun": dry_run,
            "source": run_source,
            "marketClosed": not bool(market_session_state["is_open_trading_day"]),
            "marketSession": market_session_state,
            "schedulerDiagnostic": run_source == AGENT_MODE_SOURCE_DIAGNOSTIC,
            "agentProfileId": agent_profile_id,
            "agentProfileName": agent_profile_name,
            "agentProfileUid": settings_payload.get("profile_uid"),
            "agentType": agent_type,
            "enabled": bool(settings_payload["enabled"]),
            "paused": bool(settings_payload["paused"]),
            "killSwitchEnabled": bool(settings_payload["kill_switch_enabled"]),
            "skipReason": run_guard_reason or universe_skip_reason,
            "universeSkipReason": universe_skip_reason,
            "noUniverse": no_universe,
            "scheduledWindowKey": scheduled_window_key,
            "scheduledDueAt": scheduler_payload.get("due_at_iso") or scheduler_payload.get("due_at"),
            "scheduledDueAtLocal": scheduler_payload.get("due_at_local"),
            "scheduledActualStartAt": now.isoformat(),
            "scheduledDelaySeconds": (
                int(max(0.0, (now - scheduled_due_at).total_seconds()))
                if scheduled_due_at is not None
                else None
            ),
            "schedulerTimezone": scheduler_payload.get("timezone") or settings_payload.get("timezone"),
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
            "source": run_source,
            "agentProfileId": agent_profile_id,
            "agentProfileName": agent_profile_name,
            "agentProfileUid": settings_payload.get("profile_uid"),
            "agentType": agent_type,
            "scheduler": scheduler_payload,
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
        if suppress_notifications:
            response["notificationDigestSuppressed"] = True
        else:
            digest = self._build_run_notification_digest(
                run_id=run_id,
                response=response,
                final_intents=final_intents,
                candidates=candidates,
                universe=universe,
                profile_name=agent_profile_name,
                agent_type=agent_type,
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
        self.profile_repo.create_run(
            app_user_id=user.id,
            agent_profile_id=agent_profile_id,
            agent_profile_name=agent_profile_name,
            agent_type=agent_type,
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

    @staticmethod
    def _scheduler_request_metadata(window: dict[str, object]) -> dict[str, object]:
        return {
            "timezone": window.get("timezone"),
            "local_date": window.get("local_date"),
            "local_now": window.get("local_now"),
            "run_time": window.get("run_time"),
            "due_at": window.get("due_at_iso"),
            "due_at_iso": window.get("due_at_iso"),
            "due_at_local": window.get("due_at_local"),
            "window_key": window.get("window_key"),
        }

    def scheduler_diagnostics(self, *, now: datetime | None = None) -> dict[str, object]:
        current_utc = now or datetime.now(timezone.utc)
        self.profile_repo.migrate_legacy_settings_to_profiles()
        profiles = self.profile_repo.list_all_profiles()
        session_state = market_session.market_session_state(current_utc)
        market_open_today = bool(session_state["is_open_trading_day"])
        rows: list[dict[str, object]] = []
        for profile in profiles:
            payload = self.serialize_profile(profile)
            window = self._scheduler_window(settings_payload=payload, now=current_utc)
            already_ran = self.profile_repo.scheduled_run_for_window(
                app_user_id=profile.app_user_id,
                agent_profile_id=profile.id,
                window_key=str(window.get("window_key") or ""),
            ) is not None
            try:
                universe = self.resolve_universe(app_user_id=profile.app_user_id, settings_payload=payload, overrides={})
            except Exception as exc:  # noqa: BLE001 - diagnostics should keep reporting other profiles.
                universe = {"symbols": [], "reason": self._safe_error_summary(exc), "source_status": "error"}
            enabled = bool(profile.enabled) and not bool(profile.paused) and not bool(profile.kill_switch_enabled)
            rows.append(
                {
                    "app_user_id": profile.app_user_id,
                    "agent_profile_id": profile.id,
                    "agent_profile_uid": profile.profile_uid,
                    "agent_profile_name": profile.name,
                    "agent_type": profile.agent_type,
                    "is_default": bool(profile.is_default),
                    "enabled": enabled,
                    "paused": bool(profile.paused),
                    "kill_switch_enabled": bool(profile.kill_switch_enabled),
                    "timezone": profile.timezone,
                    "daily_run_time": profile.daily_run_time,
                    "due_now": bool(window.get("due_now")) and enabled and not already_ran,
                    "would_run_now": bool(window.get("due_now")) and enabled and not already_ran and market_open_today,
                    "market_open_today": market_open_today,
                    "market_closed_reason": session_state.get("closed_reason"),
                    "next_eligible_trading_run": (
                        self._next_eligible_trading_run(
                            settings_payload=payload, now=current_utc, already_ran_window=already_ran
                        )
                    ),
                    "already_ran_current_window": already_ran,
                    "current_window_key": window.get("window_key"),
                    "current_due_at": window.get("due_at_iso"),
                    "last_checked_at": payload.get("scheduler_last_checked_at"),
                    "last_check_result": payload.get("scheduler_last_check_result"),
                    "last_check_reason": payload.get("scheduler_last_check_reason"),
                    "selected_watchlist_id": universe.get("watchlist_id"),
                    "selected_watchlist_name": universe.get("watchlist_name"),
                    "resolved_symbol_count": len(universe.get("symbols") or []),
                    "universe_source": universe.get("source") or payload.get("universe_source"),
                    "universe_source_status": universe.get("source_status"),
                    "universe_reason": universe.get("reason"),
                }
            )
        user_ids = {row["app_user_id"] for row in rows}
        return {
            "status": "ok",
            "paper_only": True,
            "no_live_routing": True,
            "as_of": current_utc.isoformat(),
            "market_session": session_state,
            "scheduler": {
                "entrypoint": "python -m macmarket_trader.cli agent-scheduler-check",
                "loop_script": "scripts/run-agent-mode-scheduler.ps1",
                "wake_interval_seconds": 300,
                "duplicate_guard": "scheduled_window_key_plus_scheduler_claim_per_profile",
                "source_for_scheduled_runs": AGENT_MODE_SOURCE_SCHEDULED,
                "source_for_diagnostics": AGENT_MODE_SOURCE_DIAGNOSTIC,
                "skips_weekends_and_holidays": True,
                "market_open_today": market_open_today,
                "market_closed_reason": session_state.get("closed_reason"),
            },
            "counts": {
                "profiles": len(profiles),
                "users": len(user_ids),
                "enabled_profiles": sum(1 for row in rows if row.get("enabled")),
                "due_now": sum(1 for row in rows if row.get("due_now")),
                "unknown_scheduler_health": sum(1 for row in rows if not row.get("last_checked_at")),
                # Back-compat aliases (previously per-user settings rows).
                "settings_rows": len(profiles),
                "enabled_rows": sum(1 for row in rows if row.get("enabled")),
            },
            "profiles": rows,
            "users": rows,
        }

    def run_due(
        self,
        *,
        now: datetime | None = None,
        dry_run: bool = False,
        no_notifications: bool = False,
        force: bool = False,
        app_user_id: int | None = None,
    ) -> list[dict[str, object]]:
        current_utc = now or datetime.now(timezone.utc)
        # Self-heal + migrate legacy single-agent settings into profiles so every
        # enabled profile (incl. users who never opened the new UI) is evaluated.
        self.profile_repo.migrate_legacy_settings_to_profiles()
        output: list[dict[str, object]] = []
        run_source = AGENT_MODE_SOURCE_DIAGNOSTIC if dry_run else AGENT_MODE_SOURCE_SCHEDULED
        for profile in self.profile_repo.list_all_profiles():
            if app_user_id is not None and int(profile.app_user_id) != int(app_user_id):
                continue
            settings_payload = self.serialize_profile(profile)
            window = self._scheduler_window(settings_payload=settings_payload, now=current_utc)
            due_at = window.get("due_at") if isinstance(window.get("due_at"), datetime) else None
            window_key = str(window.get("window_key") or "")
            base = {
                "app_user_id": profile.app_user_id,
                "agent_profile_id": profile.id,
                "agent_profile_uid": profile.profile_uid,
                "agent_type": profile.agent_type,
            }
            enabled = bool(profile.enabled) and not bool(profile.paused) and not bool(profile.kill_switch_enabled)
            if not enabled:
                reason = "agent_paused" if profile.paused else "kill_switch_enabled" if profile.kill_switch_enabled else "agent_disabled"
                self.profile_repo.update_scheduler_check(
                    profile_id=profile.id, checked_at=current_utc, result="skipped",
                    reason=reason, due_at=due_at, run_id=None, window_key=window_key,
                )
                output.append({**base, "status": "skipped", "reason": reason, "due_now": False})
                continue
            # Market-session guard: the scheduler never runs trading actions on a
            # weekend or known US market holiday. This is a SKIP, not a failure —
            # no orders, no trade notifications, no scheduled-run row, and the
            # window is left UNCLAIMED so the first open-market tick runs it once
            # (the next trading day has a different date → a different window_key,
            # so there is no duplicate/dup-block). ``force`` (an explicit operator
            # override) bypasses the guard; a manual dry-run via run() is labeled
            # but still allowed.
            session_state = market_session.market_session_state(current_utc)
            if not force and not session_state["is_open_trading_day"]:
                closed_reason = str(session_state.get("closed_reason") or market_session.REASON_OUTSIDE_SESSION)
                self.profile_repo.update_scheduler_check(
                    profile_id=profile.id, checked_at=current_utc, result="skipped",
                    reason=closed_reason, due_at=due_at, run_id=None, window_key=window_key,
                )
                output.append({
                    **base,
                    "status": "skipped",
                    "reason": closed_reason,
                    "market_closed": True,
                    "market_session": session_state,
                    "due_now": bool(window.get("due_now")),
                    "window_key": window_key,
                })
                continue
            due_now = bool(window.get("due_now"))
            if not due_now and not force:
                self.profile_repo.update_scheduler_check(
                    profile_id=profile.id, checked_at=current_utc, result="skipped",
                    reason="not_due_yet", due_at=due_at, run_id=None, window_key=window_key,
                )
                output.append({**base, "status": "skipped", "reason": "not_due_yet", "due_now": False, "window_key": window_key})
                continue
            existing = self.profile_repo.scheduled_run_for_window(
                app_user_id=profile.app_user_id, agent_profile_id=profile.id, window_key=window_key
            )
            if existing is not None and not force:
                self.profile_repo.update_scheduler_check(
                    profile_id=profile.id, checked_at=current_utc, result="skipped",
                    reason="already_ran_for_window", due_at=due_at, run_id=existing.run_id, window_key=window_key,
                )
                output.append({**base, "status": "skipped", "reason": "already_ran_for_window", "runId": existing.run_id, "window_key": window_key})
                continue
            # No-universe guard: do NOT claim the window or create a (misleading)
            # completed scheduled run when the profile resolves zero symbols — e.g.
            # universe_source=watchlist with no/empty watchlist selected. Record a
            # clear skip; the window stays unclaimed so a later tick can run it once
            # the operator fixes the universe.
            try:
                universe_preview = self.resolve_universe(
                    app_user_id=profile.app_user_id, settings_payload=settings_payload, overrides={}
                )
            except Exception as exc:  # noqa: BLE001 - treat resolution failure as no-universe.
                universe_preview = {"symbols": [], "reason": self._safe_error_summary(exc), "source_status": "error"}
            if not (universe_preview.get("symbols") or []):
                detail_reason = str(universe_preview.get("reason") or "no_universe") or "no_universe"
                self.profile_repo.update_scheduler_check(
                    profile_id=profile.id, checked_at=current_utc, result="skipped",
                    reason="no_universe", due_at=due_at, run_id=None, window_key=window_key,
                )
                output.append({
                    **base, "status": "skipped", "reason": "no_universe",
                    "universe_reason": detail_reason, "universe_source": universe_preview.get("source"),
                    "due_now": True, "window_key": window_key,
                })
                continue
            if not force and not self.profile_repo.claim_scheduler_window(
                profile_id=profile.id,
                checked_at=current_utc,
                due_at=due_at,
                window_key=window_key,
                stale_after_seconds=AGENT_SCHEDULER_HEALTH_STALE_SECONDS,
            ):
                output.append({**base, "status": "skipped", "reason": "scheduler_window_already_claimed", "due_now": True, "window_key": window_key})
                continue
            with SessionLocal() as session:
                user = session.execute(select(AppUserModel).where(AppUserModel.id == profile.app_user_id)).scalar_one_or_none()
            if user is None:
                self.profile_repo.update_scheduler_check(
                    profile_id=profile.id, checked_at=current_utc, result="skipped",
                    reason="user_not_found", due_at=due_at, run_id=None, window_key=window_key,
                )
                output.append({**base, "status": "skipped", "reason": "user_not_found", "window_key": window_key})
                continue
            if not self._user_is_approved(user):
                self.profile_repo.update_scheduler_check(
                    profile_id=profile.id, checked_at=current_utc, result="skipped",
                    reason="user_not_approved", due_at=due_at, run_id=None, window_key=window_key,
                )
                output.append({**base, "status": "skipped", "reason": "user_not_approved", "window_key": window_key})
                continue
            try:
                result = self.run(
                    user=user,
                    request={
                        "mode": "paper",
                        "dry_run": bool(dry_run),
                        "trigger": "scheduler_diagnostic" if dry_run else "daily_scheduler",
                        "source": run_source,
                        "profile_id": profile.id,
                        "profile_uid": profile.profile_uid,
                        "scheduler": self._scheduler_request_metadata(window),
                        "scheduled_window_key": window_key,
                        "no_notifications": bool(no_notifications),
                    },
                )
            except Exception as exc:  # noqa: BLE001 - scheduler reports per-profile failure and continues.
                reason = self._safe_error_summary(exc)
                run_id = f"agent_error_{uuid4().hex[:16]}"
                response_json = {
                    "runId": run_id,
                    "status": "error",
                    "source": run_source,
                    "agentProfileId": profile.id,
                    "agentProfileName": profile.name,
                    "agentType": profile.agent_type,
                    "scheduler": self._scheduler_request_metadata(window),
                    "summary": {
                        "paperOnly": True,
                        "executionMode": "paper",
                        "dryRun": bool(dry_run),
                        "source": run_source,
                        "skipReason": reason,
                        "scheduledWindowKey": window_key,
                        "agentProfileId": profile.id,
                        "agentProfileName": profile.name,
                        "agentType": profile.agent_type,
                    },
                    "warnings": [reason],
                    "notificationAttempts": [],
                    "notificationDigestSuppressed": True,
                }
                self.profile_repo.create_run(
                    app_user_id=profile.app_user_id,
                    agent_profile_id=profile.id,
                    agent_profile_name=profile.name,
                    agent_type=profile.agent_type,
                    run_id=run_id,
                    status="error",
                    execution_mode="paper",
                    dry_run=bool(dry_run),
                    intent_count=0,
                    executed_order_count=0,
                    request_json={
                        "mode": "paper",
                        "dry_run": bool(dry_run),
                        "source": run_source,
                        "profile_id": profile.id,
                        "scheduler": self._scheduler_request_metadata(window),
                        "scheduled_window_key": window_key,
                        "no_notifications": True,
                    },
                    response_json=response_json,
                    completed_at=utc_now(),
                )
                self.profile_repo.update_scheduler_check(
                    profile_id=profile.id, checked_at=current_utc, result="error",
                    reason=reason, due_at=due_at, run_id=run_id, window_key=window_key,
                )
                output.append({**base, "status": "error", "reason": reason, "runId": run_id, "window_key": window_key})
                continue
            run_id = str(result.get("runId") or "")
            self.profile_repo.update_scheduler_check(
                profile_id=profile.id,
                checked_at=current_utc,
                result="completed",
                reason=str((result.get("summary") if isinstance(result.get("summary"), dict) else {}).get("skipReason") or "") or None,
                due_at=due_at,
                run_id=run_id,
                window_key=window_key,
            )
            output.append(
                {
                    **base,
                    "status": "completed",
                    "runId": run_id,
                    "source": run_source,
                    "dry_run": bool(dry_run),
                    "no_notifications": bool(no_notifications),
                    "window_key": window_key,
                    "resolved_symbol_count": len((result.get("universe") if isinstance(result.get("universe"), dict) else {}).get("symbols") or []),
                }
            )
        return output
