from __future__ import annotations

import math
from uuid import uuid4
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select

from macmarket_trader.api.routes import admin as workflow
from macmarket_trader.domain.enums import ApprovalStatus, MarketMode
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import PortfolioSnapshot, TradeRecommendation
from macmarket_trader.domain.time import utc_now
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import (
    AgentModeRepository,
    PaperPortfolioRepository,
    RecommendationRepository,
    SymbolUniverseRepository,
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
    ) -> None:
        self.agent_repo = agent_repo or AgentModeRepository(SessionLocal)
        self.paper_repo = paper_repo or PaperPortfolioRepository(SessionLocal)
        self.recommendation_repo = recommendation_repo or RecommendationRepository(SessionLocal)
        self.symbol_universe_repo = symbol_universe_repo or SymbolUniverseRepository(SessionLocal)

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
            "max_positions": int(row.max_positions or 5),
            "scan_depth": int(row.scan_depth or 12),
            "allow_opens": bool(row.allow_opens),
            "allow_closes": bool(row.allow_closes),
            "allow_scale_resize": bool(row.allow_scale_resize),
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

    def normalize_settings_update(self, payload: dict[str, object]) -> dict[str, object]:
        updates: dict[str, object] = {}
        for key in ("enabled", "paused", "kill_switch_enabled", "allow_opens", "allow_closes", "allow_scale_resize"):
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
        if "max_positions" in payload:
            # MVP fixed cap: never allow above 5 even if the payload asks.
            updates["max_positions"] = self._coerce_int(payload.get("max_positions"), default=5, minimum=1, maximum=5)
        if "scan_depth" in payload:
            updates["scan_depth"] = self._coerce_int(payload.get("scan_depth"), default=12, minimum=1, maximum=25)
        return updates

    def resolve_universe(self, *, app_user_id: int, settings_payload: dict[str, object], overrides: dict[str, object]) -> dict[str, object]:
        manual_symbols = overrides.get("symbols") or overrides.get("manual_symbols") or settings_payload.get("manual_symbols") or ["SPY", "QQQ", "MTUM"]
        manual_list = workflow.normalize_symbol_list(manual_symbols, max_items=25, field_name="symbols")
        source = str(overrides.get("universe_source") or settings_payload.get("universe_source") or "manual").strip().lower()
        watchlist_ids = overrides.get("watchlist_ids") or settings_payload.get("watchlist_ids") or []
        if not isinstance(watchlist_ids, list):
            watchlist_ids = []
        include_all_active = source == "all_active"
        if source == "manual":
            watchlist_ids = []
            include_all_active = False
        resolution = self.symbol_universe_repo.resolve_symbols(
            app_user_id=app_user_id,
            manual_symbols=manual_list if source in {"manual", "watchlist_plus_manual", "all_active"} else [],
            watchlist_ids=[int(item) for item in watchlist_ids if str(item).isdigit()],
            include_all_active=include_all_active,
            include_inactive=False,
            exclusions=[],
            pinned_symbols=[],
        )
        symbols = resolution.symbols or manual_list
        scan_depth = self._coerce_int(overrides.get("scan_depth") or settings_payload.get("scan_depth"), default=12, minimum=1, maximum=25)
        return {
            "symbols": symbols[:scan_depth],
            "source": source,
            "source_label": source.replace("_", " "),
            "scan_depth": scan_depth,
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

    def _execute_open(self, *, intent: dict[str, object], candidate: dict[str, object], user, bars_by_symbol: dict[str, tuple[list[Any], str, bool]], timeframe: str) -> dict[str, object]:
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
        sizing_plan = workflow._paper_order_sizing_plan(rec, user=user)
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
        return {
            **payload,
            "qty": self._round_qty(payload.get("remaining_qty")),
            "avg_entry_price": self._round_price(payload.get("avg_entry_price")),
            "open_notional": self._round_money(payload.get("open_notional")),
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

    def list_runs(self, *, user, limit: int = 50, status: str | None = None, dry_run: bool | None = None) -> dict[str, object]:
        limit = self._coerce_limit(limit, default=50, maximum=100)
        rows = self.agent_repo.list_runs(app_user_id=user.id, limit=limit, status=status, dry_run=dry_run)
        return {
            "items": [self._serialize_run_history_row(row) for row in rows],
            "limit": limit,
            "paperOnly": True,
            "executionMode": "paper",
        }

    def list_trades(self, *, user, limit: int = 100) -> dict[str, object]:
        limit = self._coerce_limit(limit, default=100, maximum=250)
        run_rows = self.agent_repo.list_runs(app_user_id=user.id, limit=100)
        links = self._agent_links_from_runs(run_rows)
        rows = self.paper_repo.list_trades(app_user_id=user.id, limit=limit)
        items = [
            self._serialize_agent_trade(row, links=links)
            for row in rows
            if self._is_agent_trade(row, links=links)
        ]
        return {
            "items": items,
            "limit": limit,
            "paperOnly": True,
            "executionMode": "paper",
        }

    def performance(self, *, user) -> dict[str, object]:
        settings_payload = self.serialize_settings(self.agent_repo.get_or_create_settings(app_user_id=user.id))
        run_rows = self.agent_repo.list_runs(app_user_id=user.id, limit=100)
        links = self._agent_links_from_runs(run_rows)
        trade_rows = [
            row
            for row in self.paper_repo.list_trades(app_user_id=user.id, limit=500)
            if self._is_agent_trade(row, links=links)
        ]
        trade_items = [self._serialize_agent_trade(row, links=links) for row in trade_rows]
        open_positions = self.paper_repo.list_positions(app_user_id=user.id, status="open", limit=100)
        now = utc_now()
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
        return {
            "paperOnly": True,
            "executionMode": "paper",
            "asOf": now.isoformat(),
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
        if not bool(settings_payload["enabled"]):
            dry_run = True
        enabled_for_execution = bool(settings_payload["enabled"]) and not dry_run
        if settings_payload["paused"] or settings_payload["kill_switch_enabled"]:
            enabled_for_execution = False
            dry_run = True

        max_positions = self._coerce_int(settings_payload.get("max_positions"), default=5, minimum=1, maximum=5)
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
        bars_by_symbol: dict[str, tuple[list[Any], str, bool]] = {}
        data_quality: list[dict[str, object]] = []
        for symbol in universe["symbols"]:
            if symbol in held_symbols:
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
            if symbol in held_symbols:
                candidate["already_open"] = True
                intents.append(self._cash_intent(symbol=symbol, reason="already_open", summary="cash/no trade because the symbol is already open.", candidate=candidate))
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
            "maxPositions": max_positions,
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
