from __future__ import annotations

from collections.abc import Iterable
from datetime import timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from macmarket_trader.api.routes import admin as workflow
from macmarket_trader.domain.enums import MarketMode
from macmarket_trader.domain.time import utc_now
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import (
    DEFAULT_AGENT_MODE_MANUAL_SYMBOLS,
    PaperPortfolioRepository,
    RecommendationRepository,
    SymbolUniverseRepository,
)


TARGET_SLOT_COUNT = 5
DEFAULT_SCAN_DEPTH = 12
MAX_SCAN_DEPTH = 25
MAX_MANUAL_SYMBOLS = 40
MAX_WATCHLIST_IDS = 10
EXIT_REVIEW_ACTIONS = {"stop_triggered", "invalidated", "time_stop_exit", "target_reached_take_profit"}


def _coerce_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None and value != "" else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _safe_float(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and parsed not in {float("inf"), float("-inf")} else None


def _round_number(value: object, digits: int = 2) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _iso(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


def _dedupe(items: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = str(item or "").strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _extract_symbols_from_categories(categories: object) -> list[str]:
    if not isinstance(categories, list):
        return []
    symbols: list[str] = []
    for category in categories:
        if not isinstance(category, dict):
            continue
        rows = category.get("rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = row.get("providerSymbol") or row.get("symbol") or row.get("ticker")
            if isinstance(symbol, str) and symbol.strip():
                symbols.append(symbol)
    return _dedupe(symbols)


def _default_profile_symbols() -> list[str]:
    try:
        from macmarket_trader.charts.momentum_heatmap_defaults import (
            seeded_momentum_heatmap_profile_payload,
        )

        payload = seeded_momentum_heatmap_profile_payload("morning-macro")
        if isinstance(payload, dict):
            symbols = _extract_symbols_from_categories(payload.get("categories"))
            if symbols:
                return symbols
    except Exception:
        return list(DEFAULT_AGENT_MODE_MANUAL_SYMBOLS)
    return list(DEFAULT_AGENT_MODE_MANUAL_SYMBOLS)


def _symbol_from_candidate(candidate: dict[str, object] | None) -> str | None:
    if not candidate:
        return None
    symbol = str(candidate.get("symbol") or "").strip().upper()
    return symbol or None


def _candidate_sort_value(row: dict[str, object]) -> tuple[int, float]:
    rank = _coerce_int(row.get("rank"), default=9999, minimum=1, maximum=9999)
    score = _safe_float(row.get("score")) or 0.0
    return (rank, -score)


def _risk_state_from_candidate(candidate: dict[str, object] | None) -> str | None:
    if not candidate:
        return None
    risk = candidate.get("risk_calendar")
    if isinstance(risk, dict):
        decision = risk.get("decision")
        if isinstance(decision, dict):
            return str(decision.get("decision_state") or decision.get("state") or "").strip() or None
    status = str(candidate.get("status") or "").strip()
    return status or None


def _candidate_warnings(candidate: dict[str, object] | None) -> list[str]:
    if not candidate:
        return []
    warnings: list[str] = []
    rejection = candidate.get("rejection_reason")
    if rejection:
        warnings.append(str(rejection))
    risk = candidate.get("risk_calendar")
    if isinstance(risk, dict):
        decision = risk.get("decision")
        if isinstance(decision, dict):
            warning = decision.get("warning_summary") or decision.get("block_reason")
            if warning:
                warnings.append(str(warning))
    return _dedupe(warnings)


def _safe_targets(candidate: dict[str, object] | None) -> object:
    if not candidate:
        return None
    return candidate.get("targets")


def _operator_action(action: str) -> str:
    messages = {
        "KEEP_REVIEW": "Review and keep this paper position if the thesis still holds. No order is created here.",
        "EXIT_REVIEW": "Review a manual paper close in Orders if the thesis is invalidated. No close is created here.",
        "OPEN_REVIEW": "Review opening this paper idea through the normal paper workflow. No order is created here.",
        "REPLACE_REVIEW": "Review replacement only after an operator decides to exit an existing paper position. No order is created here.",
        "SCALE_REVIEW": "Review an explicit paper scale-in separately. No order is created here.",
        "CASH_NO_TRADE": "Keep the slot in cash/no-trade. Deterministic gates did not produce a valid target.",
    }
    return messages.get(action, "Operator review required. No order is created here.")


class DailyTargetBookService:
    """Build a read-only 5-slot target book from paper positions and ranking data."""

    def __init__(
        self,
        *,
        paper_repo: PaperPortfolioRepository | None = None,
        recommendation_repo: RecommendationRepository | None = None,
        symbol_universe_repo: SymbolUniverseRepository | None = None,
    ) -> None:
        self.paper_repo = paper_repo or PaperPortfolioRepository(SessionLocal)
        self.recommendation_repo = recommendation_repo or RecommendationRepository(SessionLocal)
        self.symbol_universe_repo = symbol_universe_repo or SymbolUniverseRepository(SessionLocal)

    @staticmethod
    def latest_template() -> dict[str, object]:
        return {
            "latest": None,
            "empty": True,
            "readOnly": True,
            "paperOnly": True,
            "executionMode": "review_only",
            "defaults": {
                "symbols": list(DEFAULT_AGENT_MODE_MANUAL_SYMBOLS),
                "scanDepth": DEFAULT_SCAN_DEPTH,
                "targetSlots": TARGET_SLOT_COUNT,
                "universeSource": "manual",
                "includeExistingPositions": True,
                "includeReplacementReviews": True,
            },
            "sourceOptions": ["manual", "watchlist", "watchlist_plus_manual", "profile", "default", "all_active"],
        }

    def _resolve_universe(
        self,
        *,
        app_user_id: int,
        request: dict[str, object],
        pinned_symbols: list[str],
        warnings: list[str],
    ) -> dict[str, object]:
        raw_source = str(request.get("universeSource") or request.get("universe_source") or "manual").strip().lower()
        if raw_source not in {"manual", "watchlist", "watchlist_plus_manual", "profile", "default", "all_active"}:
            raw_source = "manual"
            warnings.append("Unknown universe source was treated as manual.")

        manual_symbols = self.symbol_universe_repo.normalize_symbols(request.get("symbols") or DEFAULT_AGENT_MODE_MANUAL_SYMBOLS)
        manual_symbols = manual_symbols[:MAX_MANUAL_SYMBOLS]
        watchlist_ids = [
            _coerce_int(item, default=0, minimum=0, maximum=999999)
            for item in (request.get("watchlistIds") or request.get("watchlist_ids") or [])
        ][:MAX_WATCHLIST_IDS]
        watchlist_ids = [item for item in watchlist_ids if item > 0]
        profile_symbols = self.symbol_universe_repo.normalize_symbols(
            request.get("profileSymbols") or request.get("profile_symbols") or []
        )
        if not profile_symbols:
            profile_symbols = _extract_symbols_from_categories(
                request.get("profileCategories") or request.get("profile_categories")
            )
        if raw_source in {"profile", "default"} and not profile_symbols:
            profile_symbols = _default_profile_symbols()

        include_all_active = raw_source == "all_active"
        include_manual = raw_source in {"manual", "watchlist_plus_manual"}
        include_watchlist = raw_source in {"watchlist", "watchlist_plus_manual"}
        if raw_source == "default":
            include_manual = True
            manual_symbols = self.symbol_universe_repo.normalize_symbols(DEFAULT_AGENT_MODE_MANUAL_SYMBOLS)
        if raw_source == "profile":
            include_manual = True
            manual_symbols = profile_symbols

        resolution = self.symbol_universe_repo.resolve_symbols(
            app_user_id=app_user_id,
            manual_symbols=manual_symbols if include_manual else [],
            watchlist_ids=watchlist_ids if include_watchlist else [],
            include_all_active=include_all_active,
            pinned_symbols=pinned_symbols,
        )
        symbols = resolution.symbols[:MAX_MANUAL_SYMBOLS]
        if not symbols:
            warnings.append("No symbols resolved for the selected universe.")
        return {
            "symbols": symbols,
            "source": raw_source,
            "resolvedSource": resolution.source,
            "provenance": resolution.provenance,
            "manualSymbols": manual_symbols,
            "watchlistIds": watchlist_ids,
            "pinnedSymbols": pinned_symbols,
            "profileSymbols": profile_symbols if raw_source == "profile" else [],
        }

    def _serialize_position(self, position, *, review: dict[str, object] | None) -> dict[str, object]:  # noqa: ANN001
        qty = _round_number(position.remaining_qty if position.remaining_qty is not None else position.quantity, 4)
        avg_entry = _round_number(position.average_price, 2)
        mark = _round_number((review or {}).get("current_mark_price"), 2)
        opened_at = position.opened_at
        if opened_at is not None and getattr(opened_at, "tzinfo", None) is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        return {
            "positionId": position.id,
            "symbol": str(position.symbol or "").upper(),
            "side": position.side,
            "quantity": qty,
            "averageEntry": avg_entry,
            "mark": mark,
            "unrealizedPnl": _round_number((review or {}).get("unrealized_pnl"), 2),
            "unrealizedReturnPct": _round_number((review or {}).get("unrealized_return_pct"), 2),
            "daysHeld": (review or {}).get("days_held"),
            "maxHoldDays": (review or {}).get("max_holding_days"),
            "status": position.status,
            "openedAt": _iso(opened_at),
            "orderId": position.order_id,
            "recommendationId": position.recommendation_id,
            "reviewAction": (review or {}).get("action_classification"),
            "reviewSummary": (review or {}).get("action_summary"),
            "warnings": list((review or {}).get("warnings") or []),
            "missingData": list((review or {}).get("missing_data") or []),
        }

    def _position_slot(
        self,
        *,
        slot_number: int,
        position,
        review: dict[str, object] | None,
        candidate_group: dict[str, object] | None,
    ) -> dict[str, object]:
        action_classification = str((review or {}).get("action_classification") or "hold_valid")
        if action_classification in EXIT_REVIEW_ACTIONS:
            action = "EXIT_REVIEW"
        elif action_classification == "scale_in_candidate":
            action = "SCALE_REVIEW"
        else:
            action = "KEEP_REVIEW"

        best = candidate_group.get("best") if candidate_group else None
        best_candidate = best if isinstance(best, dict) else None
        supporting = candidate_group.get("supportingStrategies") if candidate_group else []
        return {
            "slot": slot_number,
            "symbol": str(position.symbol or "").upper(),
            "side": position.side,
            "action": action,
            "alreadyOpen": True,
            "positionId": position.id,
            "quantity": _round_number(position.remaining_qty if position.remaining_qty is not None else position.quantity, 4),
            "averageEntry": _round_number(position.average_price, 2),
            "mark": _round_number((review or {}).get("current_mark_price"), 2),
            "unrealizedPnl": _round_number((review or {}).get("unrealized_pnl"), 2),
            "unrealizedReturnPct": _round_number((review or {}).get("unrealized_return_pct"), 2),
            "rank": best_candidate.get("rank") if best_candidate else (review or {}).get("current_rank"),
            "score": _round_number(best_candidate.get("score") if best_candidate else None, 3),
            "bestStrategy": best_candidate.get("strategy") if best_candidate else None,
            "supportingStrategies": supporting,
            "confidence": _round_number(best_candidate.get("confidence") if best_candidate else None, 3),
            "expectedRr": _round_number(best_candidate.get("expected_rr") if best_candidate else None, 2),
            "entryZone": best_candidate.get("entry_zone") if best_candidate else None,
            "stopInvalidation": (review or {}).get("stop_price") or (best_candidate.get("invalidation") if best_candidate else None),
            "targets": _safe_targets(best_candidate) or {
                "target_1": (review or {}).get("target_1"),
                "target_2": (review or {}).get("target_2"),
            },
            "daysHeld": (review or {}).get("days_held"),
            "maxHoldDays": (review or {}).get("max_holding_days"),
            "riskState": _risk_state_from_candidate(best_candidate) or "position_review",
            "source": "paper_position",
            "warnings": _dedupe(list((review or {}).get("warnings") or []) + _candidate_warnings(best_candidate)),
            "missingData": list((review or {}).get("missing_data") or []),
            "reason": (review or {}).get("action_summary") or "Existing paper position preserved for operator review.",
            "suggestedOperatorAction": _operator_action(action),
        }

    def _candidate_slot(
        self,
        *,
        slot_number: int,
        candidate_group: dict[str, object] | None,
        replacement_available: bool,
        include_replacement_reviews: bool,
    ) -> dict[str, object]:
        best = candidate_group.get("best") if candidate_group else None
        candidate = best if isinstance(best, dict) else None
        symbol = _symbol_from_candidate(candidate)
        status = str((candidate or {}).get("status") or "").strip()
        is_top = status == "top_candidate"
        warnings = _candidate_warnings(candidate)
        if candidate and is_top:
            action = "REPLACE_REVIEW" if include_replacement_reviews and replacement_available else "OPEN_REVIEW"
            reason = str(candidate.get("reason_text") or "Ranked deterministic candidate available for review.")
        elif candidate:
            action = "CASH_NO_TRADE"
            reason = str(candidate.get("rejection_reason") or candidate.get("reason_text") or "Candidate failed deterministic target-book gates.")
            if not warnings:
                warnings = [f"Candidate status is {status or 'unavailable'}; slot remains cash/no-trade."]
        else:
            action = "CASH_NO_TRADE"
            reason = "No qualified deterministic candidate filled this slot."

        supporting = candidate_group.get("supportingStrategies") if candidate_group else []
        return {
            "slot": slot_number,
            "symbol": symbol,
            "side": "long" if candidate else None,
            "action": action,
            "alreadyOpen": False,
            "positionId": None,
            "quantity": None,
            "averageEntry": None,
            "mark": None,
            "unrealizedPnl": None,
            "unrealizedReturnPct": None,
            "rank": candidate.get("rank") if candidate else None,
            "score": _round_number(candidate.get("score") if candidate else None, 3),
            "bestStrategy": candidate.get("strategy") if candidate else None,
            "supportingStrategies": supporting,
            "confidence": _round_number(candidate.get("confidence") if candidate else None, 3),
            "expectedRr": _round_number(candidate.get("expected_rr") if candidate else None, 2),
            "entryZone": candidate.get("entry_zone") if candidate else None,
            "stopInvalidation": candidate.get("invalidation") if candidate else None,
            "targets": _safe_targets(candidate),
            "daysHeld": None,
            "maxHoldDays": None,
            "riskState": _risk_state_from_candidate(candidate) if candidate else "cash_no_trade",
            "source": candidate.get("workflow_source") if candidate else "cash",
            "warnings": warnings,
            "missingData": [],
            "reason": reason,
            "suggestedOperatorAction": _operator_action(action),
        }

    def _group_candidates(self, queue: list[dict[str, object]]) -> list[dict[str, object]]:
        groups: dict[str, list[dict[str, object]]] = {}
        for candidate in queue:
            symbol = _symbol_from_candidate(candidate)
            if not symbol:
                continue
            groups.setdefault(symbol, []).append(candidate)
        output: list[dict[str, object]] = []
        for symbol, rows in groups.items():
            sorted_rows = sorted(rows, key=_candidate_sort_value)
            best = sorted_rows[0]
            supporting = sorted_rows[1:]
            output.append(
                {
                    "symbol": symbol,
                    "best": best,
                    "supporting": supporting,
                    "supportingStrategies": [
                        {
                            "strategy": row.get("strategy"),
                            "rank": row.get("rank"),
                            "score": _round_number(row.get("score"), 3),
                            "status": row.get("status"),
                        }
                        for row in supporting
                    ],
                    "duplicateCandidateCount": max(0, len(sorted_rows) - 1),
                }
            )
        return sorted(output, key=lambda item: _candidate_sort_value(item["best"]))[:MAX_SCAN_DEPTH]

    def _build_position_reviews(self, *, app_user_id: int, user, positions: list) -> tuple[dict[int, dict[str, object]], list[str]]:  # noqa: ANN001
        recent_rows = self.recommendation_repo.list_recent(limit=100, app_user_id=app_user_id)
        now = utc_now()
        reviews: dict[int, dict[str, object]] = {}
        warnings: list[str] = []
        for position in positions:
            try:
                reviews[position.id] = workflow._build_position_review(
                    position,
                    app_user_id=app_user_id,
                    user=user,
                    recent_rows=recent_rows,
                    now=now,
                )
            except Exception as exc:
                warnings.append(f"Position review unavailable for {position.symbol}: {exc}")
                reviews[position.id] = {
                    "action_classification": "review_unavailable",
                    "action_summary": f"{position.symbol} requires manual review because position diagnostics failed.",
                    "warnings": ["position_review_unavailable"],
                    "missing_data": ["position_review"],
                }
        return reviews, warnings

    def _build_ranking(
        self,
        *,
        symbols: list[str],
        scan_depth: int,
        timeframe: str,
        app_user_id: int,
        warnings: list[str],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
        bars_by_symbol: dict[str, tuple[list[Any], str, bool]] = {}
        data_quality: list[dict[str, object]] = []
        session_metadata_by_symbol: dict[str, dict[str, object]] = {}
        for symbol in symbols:
            try:
                bars_tuple = workflow._workflow_bars(symbol, limit=120, timeframe=timeframe)
                bars_by_symbol[symbol] = bars_tuple
                metadata = workflow._workflow_session_metadata(bars_tuple[0], timeframe=timeframe)
                session_metadata_by_symbol[symbol] = metadata
                data_quality.append(
                    {
                        "symbol": symbol,
                        "status": "ok",
                        "source": bars_tuple[1],
                        "fallbackMode": bool(bars_tuple[2]),
                        "barCount": len(bars_tuple[0]),
                        "sessionPolicy": metadata.get("session_policy") or "regular_hours",
                        "sourceTimeframe": metadata.get("source_timeframe"),
                        "firstBarTimestamp": metadata.get("first_bar_timestamp"),
                        "lastBarTimestamp": metadata.get("last_bar_timestamp"),
                        "warnings": ["fallback_market_data"] if bars_tuple[2] else [],
                        "missingData": [],
                    }
                )
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                data_quality.append(
                    {
                        "symbol": symbol,
                        "status": "error",
                        "source": "unavailable",
                        "fallbackMode": False,
                        "barCount": 0,
                        "sessionPolicy": "regular_hours",
                        "sourceTimeframe": timeframe,
                        "warnings": [detail],
                        "missingData": ["historical_bars"],
                    }
                )
            except Exception as exc:
                data_quality.append(
                    {
                        "symbol": symbol,
                        "status": "error",
                        "source": "unavailable",
                        "fallbackMode": False,
                        "barCount": 0,
                        "sessionPolicy": "regular_hours",
                        "sourceTimeframe": timeframe,
                        "warnings": [f"Historical bars unavailable: {exc}"],
                        "missingData": ["historical_bars"],
                    }
                )
        if not bars_by_symbol:
            warnings.append("No ranked candidates were computed because no symbol had usable bars.")
            return [], data_quality, {"total": 0, "top_candidate_count": 0, "watchlist_count": 0, "no_trade_count": 0}

        selected_strategies = [entry.display_name for entry in workflow.list_strategies(MarketMode.EQUITIES)[:3]]
        ranking = workflow.ranking_engine.rank_candidates(
            bars_by_symbol=bars_by_symbol,
            strategies=selected_strategies,
            market_mode=MarketMode.EQUITIES,
            timeframe=timeframe,
            top_n=scan_depth,
        )
        index_context = workflow._current_index_context_for_risk()
        queue = list(ranking.get("queue") or [])
        for item in queue:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper()
            metadata = session_metadata_by_symbol.get(symbol, {})
            if metadata:
                item["session_policy"] = metadata.get("session_policy")
                item["data_quality"] = {
                    "session_policy": metadata.get("session_policy"),
                    "source_session_policy": metadata.get("source_session_policy"),
                    "source_timeframe": metadata.get("source_timeframe"),
                    "output_timeframe": metadata.get("output_timeframe"),
                    "filtered_extended_hours_count": metadata.get("filtered_extended_hours_count"),
                    "rth_bucket_count": metadata.get("rth_bucket_count"),
                }
            bars_tuple = bars_by_symbol.get(symbol)
            if bars_tuple:
                risk = workflow.risk_calendar_service.assess(
                    symbol=symbol,
                    timeframe=timeframe,
                    bars=bars_tuple[0],
                    index_context=index_context,
                )
                item["risk_calendar"] = risk.model_dump(mode="json")
                if not risk.decision.allow_new_entries and item.get("status") == "top_candidate":
                    item["status"] = risk.decision.decision_state
                    item["rejection_reason"] = risk.decision.block_reason or risk.decision.warning_summary
            item["recommendation_id"] = workflow._queue_candidate_id(item)
            item["read_only"] = True
            item["no_order_created"] = True
            item["app_user_id_scoped"] = app_user_id
        workflow.apply_queue_response_consistency(queue)
        return queue, data_quality, dict(ranking.get("summary") or {})

    def build(self, *, user, request: dict[str, object]) -> dict[str, object]:  # noqa: ANN001
        warnings: list[str] = []
        scan_depth = _coerce_int(request.get("scanDepth") or request.get("scan_depth"), default=DEFAULT_SCAN_DEPTH, minimum=1, maximum=MAX_SCAN_DEPTH)
        include_existing = _coerce_bool(
            request.get("includeExistingPositions") if "includeExistingPositions" in request else request.get("include_existing_positions"),
            default=True,
        )
        include_replacements = _coerce_bool(
            request.get("includeReplacementReviews") if "includeReplacementReviews" in request else request.get("include_replacement_reviews"),
            default=True,
        )
        timeframe = str(request.get("timeframe") or "1D").strip().upper()
        if timeframe != "1D":
            warnings.append("Daily Target Book MVP uses 1D ranking context; requested timeframe was ignored.")
            timeframe = "1D"

        open_positions = self.paper_repo.list_positions(app_user_id=user.id, status="open", limit=100)
        pinned_symbols = [str(row.symbol or "").upper() for row in open_positions] if include_existing else []
        universe = self._resolve_universe(
            app_user_id=user.id,
            request=request,
            pinned_symbols=_dedupe(pinned_symbols),
            warnings=warnings,
        )
        symbols = list(universe["symbols"])[:MAX_MANUAL_SYMBOLS]
        queue, data_quality, ranking_summary = self._build_ranking(
            symbols=symbols,
            scan_depth=scan_depth,
            timeframe=timeframe,
            app_user_id=user.id,
            warnings=warnings,
        )
        candidate_groups = self._group_candidates(queue)
        group_by_symbol = {str(group["symbol"]).upper(): group for group in candidate_groups}

        reviews, review_warnings = self._build_position_reviews(
            app_user_id=user.id,
            user=user,
            positions=open_positions,
        )
        warnings.extend(review_warnings)
        current_book = [
            self._serialize_position(position, review=reviews.get(position.id))
            for position in open_positions
        ]

        slots: list[dict[str, object]] = []
        used_symbols: set[str] = set()
        replacement_available = False
        if include_existing:
            for position in open_positions[:TARGET_SLOT_COUNT]:
                symbol = str(position.symbol or "").upper()
                if not symbol or symbol in used_symbols:
                    continue
                group = group_by_symbol.get(symbol)
                slot = self._position_slot(
                    slot_number=len(slots) + 1,
                    position=position,
                    review=reviews.get(position.id),
                    candidate_group=group,
                )
                if slot["action"] == "EXIT_REVIEW":
                    replacement_available = True
                slots.append(slot)
                used_symbols.add(symbol)
                if len(slots) >= TARGET_SLOT_COUNT:
                    break
            if len(open_positions) > TARGET_SLOT_COUNT:
                warnings.append("Current paper book exceeds the 5-slot target cap; overflow positions are listed in Current Paper Book for manual review.")

        for group in candidate_groups:
            if len(slots) >= TARGET_SLOT_COUNT:
                break
            symbol = str(group["symbol"]).upper()
            if symbol in used_symbols:
                continue
            slot = self._candidate_slot(
                slot_number=len(slots) + 1,
                candidate_group=group,
                replacement_available=replacement_available,
                include_replacement_reviews=include_replacements,
            )
            slots.append(slot)
            used_symbols.add(symbol)

        while len(slots) < TARGET_SLOT_COUNT:
            slots.append(
                self._candidate_slot(
                    slot_number=len(slots) + 1,
                    candidate_group=None,
                    replacement_available=False,
                    include_replacement_reviews=include_replacements,
                )
            )

        action_counts: dict[str, int] = {}
        for slot in slots:
            action = str(slot.get("action") or "UNKNOWN")
            action_counts[action] = action_counts.get(action, 0) + 1

        target_symbols = {str(slot.get("symbol") or "").upper() for slot in slots if slot.get("symbol")}
        current_symbols = {str(item.get("symbol") or "").upper() for item in current_book if item.get("symbol")}
        differences = {
            "currentOnly": sorted(current_symbols - target_symbols),
            "targetOnly": sorted(target_symbols - current_symbols),
            "exitReviews": [slot for slot in slots if slot.get("action") == "EXIT_REVIEW"],
            "replacementReviews": [slot for slot in slots if slot.get("action") == "REPLACE_REVIEW"],
            "cashSlots": [slot for slot in slots if slot.get("action") == "CASH_NO_TRADE"],
            "operatorRequired": True,
            "noAutomaticReplacement": True,
        }

        as_of = utc_now()
        return {
            "runId": f"dtb_{uuid4().hex[:16]}",
            "generatedAt": as_of.isoformat(),
            "asOf": as_of.isoformat(),
            "mode": "review_only",
            "readOnly": True,
            "paperOnly": True,
            "executionMode": "review_only",
            "noOrdersCreated": True,
            "noPositionsChanged": True,
            "universe": {
                **universe,
                "scanDepth": scan_depth,
                "timeframe": timeframe,
            },
            "summary": {
                "targetSlots": TARGET_SLOT_COUNT,
                "slotsReturned": len(slots),
                "currentPaperBookCount": len(current_book),
                "candidateGroupCount": len(candidate_groups),
                "rawCandidateCount": len(queue),
                "actions": action_counts,
                "keepReviews": action_counts.get("KEEP_REVIEW", 0),
                "exitReviews": action_counts.get("EXIT_REVIEW", 0),
                "openReviews": action_counts.get("OPEN_REVIEW", 0),
                "replaceReviews": action_counts.get("REPLACE_REVIEW", 0),
                "scaleReviews": action_counts.get("SCALE_REVIEW", 0),
                "cashNoTrade": action_counts.get("CASH_NO_TRADE", 0),
                "ranking": ranking_summary,
                "operatorReviewRequired": True,
                "readOnly": True,
                "paperOnly": True,
            },
            "targetBook": slots,
            "currentPaperBook": current_book,
            "candidateQueue": queue[:scan_depth],
            "candidateGroups": candidate_groups,
            "differences": differences,
            "decisionMemo": [
                "Daily Target Book is read-only manual review. It creates no paper orders and changes no positions.",
                "Existing valid paper positions are preserved in target slots before new open reviews are considered.",
                "Replacement reviews are labels only; the operator must decide any paper close/open workflow separately.",
                "Candidate ranking, risk calendar checks, and paper position diagnostics are deterministic MacMarket services.",
            ],
            "dataQuality": data_quality,
            "warnings": _dedupe(warnings),
        }
