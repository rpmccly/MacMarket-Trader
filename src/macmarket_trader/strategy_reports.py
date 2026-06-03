from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from macmarket_trader.config import settings as _app_settings
from macmarket_trader.analysis_packets import (
    build_analysis_packet,
    build_macro_context_summary,
    build_provider_context_summary,
)
from macmarket_trader.charts.haco_heatmap_reporting import (
    annotate_rows as annotate_haco_rows,
    build_report_payload as build_haco_report_payload,
    category_summaries as haco_category_summaries,
    compute_changes as compute_haco_changes,
    haco_heatmap_html,
    unsupported_summary as haco_unsupported_summary,
)
from macmarket_trader.charts.haco_heatmap_service import (
    HACO_HEATMAP_TIMEFRAMES,
    HacoHeatmapService,
)
from macmarket_trader.charts.momentum_heatmap_reporting import (
    annotate_rows as annotate_momentum_rows,
    build_report_payload as build_momentum_report_payload,
    category_summaries as momentum_category_summaries,
    compute_deltas as compute_momentum_deltas,
    heatmap_html,
    heatmap_text,
    unsupported_summary as momentum_unsupported_summary,
)
from macmarket_trader.charts.momentum_heatmap_service import (
    HEATMAP_MAX_ROWS_PER_REQUEST,
    HEATMAP_SCORE_TIMEFRAMES,
    MomentumHeatmapService,
)
from macmarket_trader.data.providers.base import EmailMessage, EmailProvider
from macmarket_trader.data.providers.registry import build_market_data_service
from macmarket_trader.domain.enums import MarketMode
from macmarket_trader.domain.schemas import HacoHeatmapRequest, MomentumHeatmapRequest
from macmarket_trader.email_templates import (
    render_scheduled_heatmap_failure_html,
    render_scheduled_heatmap_failure_text,
    render_strategy_report_html,
    render_strategy_report_text,
)
from macmarket_trader.ranking_engine import DeterministicRankingEngine
from macmarket_trader.recommendation.true_momentum_applicability import (
    attach_true_momentum_applicability,
)
from macmarket_trader.strategy_registry import list_strategies
from macmarket_trader.storage.repositories import (
    EmailLogRepository,
    StrategyReportRepository,
)


REPORT_TYPE_STRATEGY_SCAN = "strategy_scan"
REPORT_TYPE_MOMENTUM_HEATMAP = "momentum_heatmap"
REPORT_TYPE_HACO_HEATMAP = "haco_heatmap"
SCHEDULE_REPORT_TYPES = {
    REPORT_TYPE_STRATEGY_SCAN,
    REPORT_TYPE_MOMENTUM_HEATMAP,
    REPORT_TYPE_HACO_HEATMAP,
}
HEATMAP_REPORT_TYPES = {
    REPORT_TYPE_MOMENTUM_HEATMAP,
    REPORT_TYPE_HACO_HEATMAP,
}
REPORT_TYPE_LABELS = {
    REPORT_TYPE_STRATEGY_SCAN: "Strategy Candidate Scan",
    REPORT_TYPE_MOMENTUM_HEATMAP: "Momentum Heatmap",
    REPORT_TYPE_HACO_HEATMAP: "HACO Heatmap",
}


def normalize_schedule_report_type(value: object | None) -> str:
    report_type = str(value or REPORT_TYPE_STRATEGY_SCAN).strip().lower()
    if report_type not in SCHEDULE_REPORT_TYPES:
        raise ValueError("unsupported report_type")
    return report_type


def schedule_report_type_label(report_type: object | None) -> str:
    try:
        normalized = normalize_schedule_report_type(report_type)
    except ValueError:
        normalized = REPORT_TYPE_STRATEGY_SCAN
    return REPORT_TYPE_LABELS[normalized]


class StrategyReportService:
    def __init__(
        self,
        *,
        report_repo: StrategyReportRepository,
        email_provider: EmailProvider,
        email_log_repo: EmailLogRepository,
    ) -> None:
        self.report_repo = report_repo
        self.email_provider = email_provider
        self.email_log_repo = email_log_repo
        self.market_data_service = build_market_data_service()
        self.ranking_engine = DeterministicRankingEngine()

    @staticmethod
    def _next_run_at(*, now: datetime, frequency: str, run_time: str, timezone_name: str) -> datetime:
        tz = ZoneInfo(timezone_name)
        local_now = now.astimezone(tz)
        hour, minute = [int(part) for part in run_time.split(":", 1)]
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        weekdays = {"weekdays"}
        if frequency in weekdays:
            while candidate.weekday() >= 5 or candidate <= local_now:
                candidate = candidate + timedelta(days=1)
                candidate = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
        elif frequency == "weekly":
            while candidate.weekday() != 0 or candidate <= local_now:
                candidate = candidate + timedelta(days=1)
                candidate = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
        else:
            if candidate <= local_now:
                candidate = (candidate + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return candidate.astimezone(timezone.utc)

    def run_schedule(self, schedule_id: int, *, trigger: str = "manual") -> dict[str, object]:
        schedule = self.report_repo.get_schedule(schedule_id)
        if schedule is None:
            raise ValueError("schedule not found")
        settings = dict(schedule.payload or {})
        report_type = normalize_schedule_report_type(settings.get("report_type"))
        if report_type == REPORT_TYPE_MOMENTUM_HEATMAP:
            return self._run_momentum_heatmap_schedule(schedule, settings, trigger=trigger)
        if report_type == REPORT_TYPE_HACO_HEATMAP:
            return self._run_haco_heatmap_schedule(schedule, settings, trigger=trigger)
        return self._run_strategy_scan_schedule(schedule, settings, trigger=trigger)

    def _run_strategy_scan_schedule(self, schedule, settings: dict[str, object], *, trigger: str) -> dict[str, object]:  # noqa: ANN001
        market_mode = MarketMode(str(settings.get("market_mode") or MarketMode.EQUITIES.value))
        symbols = [str(item).upper() for item in settings.get("symbols", []) if str(item).strip()]
        strategies = [str(item) for item in settings.get("enabled_strategies", []) if str(item).strip()]
        allowed = {entry.display_name for entry in list_strategies(market_mode)}
        strategies = [strategy for strategy in strategies if strategy in allowed]
        top_n = int(settings.get("top_n", 5))
        if not symbols:
            raise ValueError("schedule requires at least one symbol")
        if not strategies:
            default_strategy = next(iter(allowed), None)
            strategies = [default_strategy] if default_strategy else []
        if not strategies:
            raise ValueError("no runnable strategies configured for this market mode")

        bars_by_symbol = {}
        last_source = "provider"
        last_fallback = False
        for symbol in symbols:
            bars, source, fallback_mode = self.market_data_service.historical_bars(symbol=symbol, timeframe="1D", limit=60)
            if not bars:
                continue
            bars_by_symbol[symbol] = (bars, source, fallback_mode)
            last_source = source
            last_fallback = fallback_mode

        ranking = self.ranking_engine.rank_candidates(
            bars_by_symbol=bars_by_symbol,
            strategies=strategies,
            market_mode=market_mode,
            timeframe="1D",
            top_n=top_n,
        )
        attach_true_momentum_applicability(ranking["queue"])
        queue_by_key = {
            (item.get("symbol"), item.get("strategy"), item.get("rank")): item
            for item in ranking["queue"]
        }
        for bucket_name in ("top_candidates", "watchlist_only", "no_trade"):
            for entry in ranking.get(bucket_name, []):
                if not isinstance(entry, dict):
                    continue
                canonical = queue_by_key.get(
                    (entry.get("symbol"), entry.get("strategy"), entry.get("rank"))
                )
                if canonical is not None and "true_momentum_applicability" in canonical:
                    entry["true_momentum_applicability"] = canonical[
                        "true_momentum_applicability"
                    ]

        payload = {
            "schedule_id": schedule.id,
            "report_type": REPORT_TYPE_STRATEGY_SCAN,
            "report_type_label": REPORT_TYPE_LABELS[REPORT_TYPE_STRATEGY_SCAN],
            "trigger": trigger,
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "source": f"fallback ({last_source})" if last_fallback else last_source,
            "email_provider": _app_settings.email_provider,
            "top_candidates": ranking["top_candidates"],
            "watchlist_only": ranking["watchlist_only"],
            "no_trade": ranking["no_trade"],
            "queue": ranking["queue"],
            "summary": ranking["summary"],
        }
        macro_context = build_macro_context_summary()
        analysis_packets: list[dict[str, object]] = []
        for candidate in list(ranking["top_candidates"])[: min(top_n, 5)]:
            symbol = str(candidate.get("symbol") or "").upper()
            if not symbol:
                continue
            candidate_payload = {
                **candidate,
                "symbol": symbol,
                "side": candidate.get("side") or "long",
                "strategy": candidate.get("strategy"),
                "thesis": candidate.get("thesis"),
                "true_momentum_applicability": candidate.get("true_momentum_applicability") or [],
                "entry_zone": candidate.get("entry_zone"),
                "invalidation": candidate.get("invalidation"),
                "targets": candidate.get("targets"),
                "quality": {
                    "score": candidate.get("score"),
                    "confidence": candidate.get("confidence"),
                    "expected_rr": candidate.get("expected_rr"),
                },
                "workflow": {
                    "market_mode": market_mode.value,
                    "timeframe": "1D",
                    "market_data_source": candidate.get("workflow_source") or last_source,
                    "fallback_mode": bool(last_fallback),
                    "session_policy": None,
                    "ranking_provenance": {
                        "rank": candidate.get("rank"),
                        "score": candidate.get("score"),
                        "confidence": candidate.get("confidence"),
                        "expected_rr": candidate.get("expected_rr"),
                        "strategy": candidate.get("strategy"),
                        "true_momentum_applicability": candidate.get("true_momentum_applicability") or [],
                    },
                },
            }
            packet = build_analysis_packet(
                symbol=symbol,
                market_mode=market_mode.value,
                timeframe="1D",
                source_payload=candidate_payload,
                market_data_source=str(candidate.get("workflow_source") or last_source),
                fallback_mode=bool(last_fallback),
                session_policy=None,
                macro_context=macro_context,
                provider_context=build_provider_context_summary(
                    market_data_source=str(candidate.get("workflow_source") or last_source),
                    fallback_mode=bool(last_fallback),
                    session_policy=None,
                    market_mode=market_mode.value,
                ),
            )
            analysis_packets.append(packet.model_dump(mode="json"))
        payload["analysis_packets"] = analysis_packets
        run_row = self.report_repo.create_run(
            schedule_id=schedule.id,
            status="sent",
            payload=payload,
            delivered_to=str(settings.get("email_delivery_target") or schedule.email_target),
        )

        target_email = str(settings.get("email_delivery_target") or schedule.email_target)
        ran_at = str(payload.get("ran_at") or datetime.now(timezone.utc).isoformat())

        # Build the subject line: "MacMarket · Apr 13 · Top: NVDA (0.93) + 4 more"
        try:
            _ran_dt = datetime.fromisoformat(ran_at.replace("Z", "+00:00")).astimezone(timezone.utc)
            _date_label = f"{_ran_dt.strftime('%b')} {_ran_dt.day}"
        except Exception:  # noqa: BLE001
            _date_label = ran_at[:10]
        _top_candidates = list(payload.get("top_candidates") or [])
        _top_count = int((payload.get("summary") or {}).get("top_candidate_count", len(_top_candidates)))
        if _top_candidates:
            _first = _top_candidates[0]
            _top_sym = str(_first.get("symbol") or "")
            _top_score = _first.get("score")
            _score_str = f"{_top_score:.2f}" if isinstance(_top_score, (int, float)) else ""
            _top_label = f"{_top_sym} ({_score_str})" if _score_str else _top_sym
            _remaining = _top_count - 1
            if _remaining > 0:
                subject = f"MacMarket \u00b7 {_date_label} \u00b7 Top: {_top_label} + {_remaining} more"
            else:
                subject = f"MacMarket \u00b7 {_date_label} \u00b7 Top: {_top_label}"
        else:
            subject = f"MacMarket \u00b7 {_date_label} \u00b7 No candidates"

        email_html = render_strategy_report_html(
            schedule_name=schedule.name,
            ran_at=ran_at,
            source=str(payload.get("source") or "fallback"),
            top_candidates=list(payload.get("top_candidates") or []),
            watchlist_only=list(payload.get("watchlist_only") or []),
            no_trade=list(payload.get("no_trade") or []),
            summary=dict(payload.get("summary") or {}),
            analysis_packets=list(payload.get("analysis_packets") or []),
        )
        email_text = render_strategy_report_text(
            schedule_name=schedule.name,
            ran_at=ran_at,
            source=str(payload.get("source") or "fallback"),
            top_candidates=list(payload.get("top_candidates") or []),
            watchlist_only=list(payload.get("watchlist_only") or []),
            no_trade=list(payload.get("no_trade") or []),
            summary=dict(payload.get("summary") or {}),
            analysis_packets=list(payload.get("analysis_packets") or []),
        )
        message_id = self.email_provider.send(
            EmailMessage(
                to_email=target_email,
                subject=subject,
                body=email_text,
                template_name="strategy_report",
                html=email_html,
            )
        )
        self.email_log_repo.create(schedule.app_user_id, "strategy_report", target_email, "sent", message_id)

        now = datetime.now(timezone.utc)
        next_run = self._next_run_at(
            now=now,
            frequency=schedule.frequency,
            run_time=schedule.run_time,
            timezone_name=schedule.timezone,
        )
        self.report_repo.mark_schedule_run(
            schedule_id=schedule.id,
            status="sent",
            next_run_at=next_run,
            latest_run_id=run_row.id,
        )
        return payload

    @staticmethod
    def _normalize_symbols(raw_symbols: object) -> list[str]:
        symbols: list[str] = []
        seen: set[str] = set()
        for item in raw_symbols or []:  # type: ignore[union-attr]
            symbol = str(item or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
        return symbols

    @staticmethod
    def _normalize_heatmap_timeframes(raw_timeframes: object, *, allowed: tuple[str, ...]) -> list[str]:
        output: list[str] = []
        raw_items = raw_timeframes if isinstance(raw_timeframes, list) else list(allowed)
        for item in raw_items:
            timeframe = str(item or "").strip().upper()
            if timeframe in allowed and timeframe not in output:
                output.append(timeframe)
        return output or list(allowed)

    @staticmethod
    def _chunked(rows: list[dict[str, object]], size: int) -> list[list[dict[str, object]]]:
        return [rows[index:index + size] for index in range(0, len(rows), size)]

    @staticmethod
    def _schedule_heatmap_rows(*, schedule_id: int, symbols: list[str]) -> list[dict[str, object]]:
        return [
            {
                "id": f"schedule-{schedule_id}-{symbol}",
                "symbol": symbol,
                "displayName": symbol,
                "providerSymbol": symbol,
            }
            for symbol in symbols
        ]

    @staticmethod
    def _row_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for category in payload.get("categories") or []:
            if not isinstance(category, dict):
                continue
            rows.extend(row for row in category.get("rows") or [] if isinstance(row, dict))
        return rows

    @staticmethod
    def _safe_failure_reason(reason: object) -> str:
        text = str(reason or "heatmap_report_failed").replace("\n", " ").replace("\r", " ").strip()
        if not text:
            return "heatmap_report_failed"
        if "Authorization" in text:
            text = text.split("Authorization", 1)[0].strip()
        return text[:240]

    @staticmethod
    def _date_label(value: str) -> str:
        try:
            ran_dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
            return f"{ran_dt.strftime('%b')} {ran_dt.day}"
        except Exception:  # noqa: BLE001
            return value[:10]

    def _mark_completed(self, schedule, *, status: str, latest_run_id: int) -> None:  # noqa: ANN001
        now = datetime.now(timezone.utc)
        next_run = self._next_run_at(
            now=now,
            frequency=schedule.frequency,
            run_time=schedule.run_time,
            timezone_name=schedule.timezone,
        )
        self.report_repo.mark_schedule_run(
            schedule_id=schedule.id,
            status=status,
            next_run_at=next_run,
            latest_run_id=latest_run_id,
        )

    @staticmethod
    def _momentum_summary(report: dict[str, Any]) -> dict[str, object]:
        full_heatmap = report.get("full_heatmap") if isinstance(report.get("full_heatmap"), dict) else {}
        rows = StrategyReportService._row_items(full_heatmap)
        usable = sum(1 for row in rows if str(row.get("availability_status")) in {"fresh", "partial"})
        unsupported = report.get("unsupported_summary") if isinstance(report.get("unsupported_summary"), dict) else {}
        return {
            "row_count": len(rows),
            "usable_row_count": usable,
            "unsupported_count": int(unsupported.get("unsupported_count") or 0),
            "unavailable_count": int(unsupported.get("unavailable_count") or 0),
            "top_strongest_count": len(report.get("top_strongest") or []),
            "bullish_alignment_count": len(report.get("bullish_alignment") or []),
            "bearish_alignment_count": len(report.get("bearish_alignment") or []),
        }

    @staticmethod
    def _haco_summary(report: dict[str, Any]) -> dict[str, object]:
        full_heatmap = report.get("full_heatmap") if isinstance(report.get("full_heatmap"), dict) else {}
        rows = StrategyReportService._row_items(full_heatmap)
        usable = sum(1 for row in rows if str(row.get("availability_status")) in {"fresh", "partial"})
        unsupported = report.get("unsupported_summary") if isinstance(report.get("unsupported_summary"), dict) else {}
        return {
            "row_count": len(rows),
            "usable_row_count": usable,
            "unsupported_count": int(unsupported.get("unsupported_count") or 0),
            "unavailable_count": int(unsupported.get("unavailable_count") or 0),
            "all_long_count": len(report.get("all_long") or []),
            "all_short_count": len(report.get("all_short") or []),
            "mixed_chop_count": len(report.get("mixed_chop") or []),
            "fresh_long_flip_count": len(report.get("fresh_long_flips") or []),
            "fresh_short_flip_count": len(report.get("fresh_short_flips") or []),
        }

    def _record_heatmap_failure(
        self,
        schedule,
        settings: dict[str, object],
        *,
        report_type: str,
        trigger: str,
        reason: object,
        symbols: list[str],
        partial_summary: dict[str, object] | None = None,
    ) -> dict[str, object]:  # noqa: ANN001
        ran_at = datetime.now(timezone.utc).isoformat()
        safe_reason = self._safe_failure_reason(reason)
        target_email = str(settings.get("email_delivery_target") or schedule.email_target)
        payload: dict[str, object] = {
            "schedule_id": schedule.id,
            "report_type": report_type,
            "report_type_label": REPORT_TYPE_LABELS[report_type],
            "trigger": trigger,
            "ran_at": ran_at,
            "source": "scheduled_symbols",
            "email_provider": _app_settings.email_provider,
            "status": "failed",
            "summary": partial_summary or {
                "row_count": len(symbols),
                "usable_row_count": 0,
                "unsupported_count": 0,
                "unavailable_count": len(symbols),
            },
            "failure": {
                "reason": safe_reason,
                "symbol_count": len(symbols),
                "requested_symbols": symbols,
            },
            "warnings": [
                "Scheduled heatmap reports are research-only diagnostics and do not create recommendations, orders, paper positions, broker routes, or live trades.",
            ],
        }
        run_row = self.report_repo.create_run(
            schedule_id=schedule.id,
            status="failed",
            payload=payload,
            delivered_to=target_email,
        )
        self._mark_completed(schedule, status="failed", latest_run_id=run_row.id)
        try:
            message_id = self.email_provider.send(
                EmailMessage(
                    to_email=target_email,
                    subject=f"MacMarket \u00b7 {REPORT_TYPE_LABELS[report_type]} Failure \u00b7 {self._date_label(ran_at)} \u00b7 {schedule.name}",
                    body=render_scheduled_heatmap_failure_text(
                        report_type_label=REPORT_TYPE_LABELS[report_type],
                        schedule_name=schedule.name,
                        ran_at=ran_at,
                        symbol_count=len(symbols),
                        requested_symbols=symbols,
                        reason=safe_reason,
                        partial_summary=partial_summary or {},
                    ),
                    template_name=f"{report_type}_scheduled_failure",
                    html=render_scheduled_heatmap_failure_html(
                        report_type_label=REPORT_TYPE_LABELS[report_type],
                        schedule_name=schedule.name,
                        ran_at=ran_at,
                        symbol_count=len(symbols),
                        requested_symbols=symbols,
                        reason=safe_reason,
                        partial_summary=partial_summary or {},
                    ),
                )
            )
            self.email_log_repo.create(schedule.app_user_id, f"{report_type}_scheduled_failure", target_email, "sent", message_id)
        except Exception as exc:  # pragma: no cover - provider failure should not hide run audit
            self.email_log_repo.create(
                schedule.app_user_id,
                f"{report_type}_scheduled_failure",
                target_email,
                f"failed:{type(exc).__name__}",
                None,
            )
        return payload

    def _run_momentum_heatmap_schedule(self, schedule, settings: dict[str, object], *, trigger: str) -> dict[str, object]:  # noqa: ANN001
        symbols = self._normalize_symbols(settings.get("symbols", []))
        if not symbols:
            raise ValueError("momentum heatmap schedule requires at least one symbol")
        try:
            rows = self._schedule_heatmap_rows(schedule_id=schedule.id, symbols=symbols)
            timeframes = self._normalize_heatmap_timeframes(
                settings.get("timeframes"),
                allowed=HEATMAP_SCORE_TIMEFRAMES,
            )
            service = MomentumHeatmapService(self.market_data_service)
            merged_rows: list[dict[str, Any]] = []
            generated_at: str | None = None
            for chunk in self._chunked(rows, HEATMAP_MAX_ROWS_PER_REQUEST):
                request = MomentumHeatmapRequest(
                    categories=[
                        {
                            "categoryId": "scheduled_symbols",
                            "categoryLabel": str(schedule.name or "Scheduled Symbols")[:120],
                            "rows": chunk,
                        }
                    ],
                    timeframes=timeframes,
                )
                heatmap = service.build_heatmap(request).model_dump(mode="json", by_alias=True)
                generated_at = str(heatmap.get("generated_at") or generated_at or "")
                category = (heatmap.get("categories") or [{}])[0]
                if isinstance(category, dict):
                    merged_rows.extend(row for row in category.get("rows") or [] if isinstance(row, dict))
            raw_payload = {
                "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
                "timeframes": timeframes,
                "categories": [
                    {
                        "categoryId": "scheduled_symbols",
                        "categoryLabel": str(schedule.name or "Scheduled Symbols")[:120],
                        "rows": merged_rows,
                    }
                ],
            }
            deltas = compute_momentum_deltas(raw_payload, None)
            annotated = annotate_momentum_rows(raw_payload, deltas)
            summaries = momentum_category_summaries(annotated, deltas)
            unsupported = momentum_unsupported_summary(annotated)
            report = build_momentum_report_payload(
                profile={
                    "id": f"scheduled-{schedule.id}",
                    "name": schedule.name,
                    "colorRanges": [],
                },
                snapshot={
                    "generated_at": raw_payload["generated_at"],
                    "payload": annotated,
                    "categorySummaries": summaries,
                    "unsupportedSummary": unsupported,
                },
                previous_snapshot=None,
            )
            summary = self._momentum_summary(report)
            if int(summary.get("usable_row_count") or 0) <= 0:
                return self._record_heatmap_failure(
                    schedule,
                    settings,
                    report_type=REPORT_TYPE_MOMENTUM_HEATMAP,
                    trigger=trigger,
                    reason="no_usable_momentum_heatmap_rows",
                    symbols=symbols,
                    partial_summary=summary,
                )
        except Exception as exc:  # noqa: BLE001
            return self._record_heatmap_failure(
                schedule,
                settings,
                report_type=REPORT_TYPE_MOMENTUM_HEATMAP,
                trigger=trigger,
                reason=f"momentum_heatmap_refresh_failed:{type(exc).__name__}",
                symbols=symbols,
            )

        return self._send_heatmap_report(
            schedule,
            settings,
            report_type=REPORT_TYPE_MOMENTUM_HEATMAP,
            trigger=trigger,
            report=report,
            summary=summary,
            html=heatmap_html(report),
            text=heatmap_text(report),
        )

    def _run_haco_heatmap_schedule(self, schedule, settings: dict[str, object], *, trigger: str) -> dict[str, object]:  # noqa: ANN001
        symbols = self._normalize_symbols(settings.get("symbols", []))
        if not symbols:
            raise ValueError("haco heatmap schedule requires at least one symbol")
        try:
            rows = self._schedule_heatmap_rows(schedule_id=schedule.id, symbols=symbols)
            timeframes = self._normalize_heatmap_timeframes(
                settings.get("timeframes"),
                allowed=HACO_HEATMAP_TIMEFRAMES,
            )
            service = HacoHeatmapService(self.market_data_service)
            merged_rows: list[dict[str, Any]] = []
            generated_at: str | None = None
            for chunk in self._chunked(rows, HEATMAP_MAX_ROWS_PER_REQUEST):
                request = HacoHeatmapRequest(
                    categories=[
                        {
                            "categoryId": "scheduled_symbols",
                            "categoryLabel": str(schedule.name or "Scheduled Symbols")[:120],
                            "rows": chunk,
                        }
                    ],
                    timeframes=timeframes,
                )
                heatmap = service.build_heatmap(request).model_dump(mode="json", by_alias=True)
                generated_at = str(heatmap.get("generated_at") or generated_at or "")
                category = (heatmap.get("categories") or [{}])[0]
                if isinstance(category, dict):
                    merged_rows.extend(row for row in category.get("rows") or [] if isinstance(row, dict))
            raw_payload = {
                "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
                "timeframes": timeframes,
                "categories": [
                    {
                        "categoryId": "scheduled_symbols",
                        "categoryLabel": str(schedule.name or "Scheduled Symbols")[:120],
                        "rows": merged_rows,
                    }
                ],
            }
            changes = compute_haco_changes(raw_payload, None)
            annotated = annotate_haco_rows(raw_payload, changes)
            summaries = haco_category_summaries(annotated)
            unsupported = haco_unsupported_summary(annotated)
            report = build_haco_report_payload(
                profile={
                    "id": f"scheduled-{schedule.id}",
                    "name": schedule.name,
                },
                snapshot={
                    "generated_at": raw_payload["generated_at"],
                    "payload": annotated,
                    "categorySummaries": summaries,
                    "unsupportedSummary": unsupported,
                },
                previous_snapshot=None,
            )
            summary = self._haco_summary(report)
            if int(summary.get("usable_row_count") or 0) <= 0:
                return self._record_heatmap_failure(
                    schedule,
                    settings,
                    report_type=REPORT_TYPE_HACO_HEATMAP,
                    trigger=trigger,
                    reason="no_usable_haco_heatmap_rows",
                    symbols=symbols,
                    partial_summary=summary,
                )
        except Exception as exc:  # noqa: BLE001
            return self._record_heatmap_failure(
                schedule,
                settings,
                report_type=REPORT_TYPE_HACO_HEATMAP,
                trigger=trigger,
                reason=f"haco_heatmap_refresh_failed:{type(exc).__name__}",
                symbols=symbols,
            )

        return self._send_heatmap_report(
            schedule,
            settings,
            report_type=REPORT_TYPE_HACO_HEATMAP,
            trigger=trigger,
            report=report,
            summary=summary,
            html=haco_heatmap_html(report),
            text=self._haco_heatmap_text(report),
        )

    @staticmethod
    def _haco_heatmap_text(report: dict[str, Any]) -> str:
        rows = [row for row in report.get("all_long") or [] if isinstance(row, dict)]
        short_rows = [row for row in report.get("all_short") or [] if isinstance(row, dict)]
        lines = [
            f"MacMarket HACO Heatmap - {report.get('profile_name') or 'Scheduled HACO Heatmap'}",
            f"Generated: {report.get('generated_at')}",
            "Research dashboard only. Not trade execution or investment advice.",
            "HACO LONG/SHORT states are directional research context.",
            "",
            "All LONG rows:",
            *(f"- {row.get('displayName')}: {row.get('overall_alignment_percent')}%" for row in rows[:5]),
            "" if rows else "- No rows available.",
            "All SHORT rows:",
            *(f"- {row.get('displayName')}: {row.get('overall_alignment_percent')}%" for row in short_rows[:5]),
            "" if short_rows else "- No rows available.",
            "",
            "No live trading, broker routing, recommendations, paper orders, or automatic execution are created by this report.",
        ]
        return "\n".join(lines)

    def _send_heatmap_report(
        self,
        schedule,
        settings: dict[str, object],
        *,
        report_type: str,
        trigger: str,
        report: dict[str, Any],
        summary: dict[str, object],
        html: str,
        text: str,
    ) -> dict[str, object]:  # noqa: ANN001
        ran_at = datetime.now(timezone.utc).isoformat()
        target_email = str(settings.get("email_delivery_target") or schedule.email_target)
        payload: dict[str, object] = {
            "schedule_id": schedule.id,
            "report_type": report_type,
            "report_type_label": REPORT_TYPE_LABELS[report_type],
            "trigger": trigger,
            "ran_at": ran_at,
            "source": "scheduled_symbols",
            "email_provider": _app_settings.email_provider,
            "summary": summary,
            "report": report,
            "heatmap": report.get("full_heatmap") if isinstance(report.get("full_heatmap"), dict) else {},
            "warnings": [
                "Scheduled heatmap reports are research-only diagnostics and do not create recommendations, orders, paper positions, broker routes, or live trades.",
            ],
        }
        run_row = self.report_repo.create_run(
            schedule_id=schedule.id,
            status="sent",
            payload=payload,
            delivered_to=target_email,
        )
        subject = f"MacMarket \u00b7 {REPORT_TYPE_LABELS[report_type]} \u00b7 {self._date_label(ran_at)} \u00b7 {schedule.name}"
        message_id = self.email_provider.send(
            EmailMessage(
                to_email=target_email,
                subject=subject,
                body=text,
                template_name=f"{report_type}_scheduled_report",
                html=html,
            )
        )
        self.email_log_repo.create(schedule.app_user_id, f"{report_type}_scheduled_report", target_email, "sent", message_id)
        self._mark_completed(schedule, status="sent", latest_run_id=run_row.id)
        return payload

    def run_due_schedules(
        self,
        *,
        now: datetime | None = None,
        report_types: set[str] | None = None,
    ) -> list[dict[str, object]]:
        current = now or datetime.now(timezone.utc)
        schedules = self.report_repo.list_due_schedules(now=current)
        output: list[dict[str, object]] = []
        for schedule in schedules:
            schedule_type = normalize_schedule_report_type((schedule.payload or {}).get("report_type"))
            if report_types is not None and schedule_type not in report_types:
                continue
            output.append(self.run_schedule(schedule.id, trigger="scheduler"))
        return output
