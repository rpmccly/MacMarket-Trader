"""ATR Direction Heatmap scheduled report tests (email-only; no SMS)."""

from datetime import datetime, timezone

from sqlalchemy import select

from macmarket_trader.charts.atr_heatmap_reporting import atr_heatmap_csv, atr_heatmap_html, atr_heatmap_text, build_atr_report_payload
from macmarket_trader.charts.atr_heatmap_service import AtrHeatmapService
from macmarket_trader.data.providers.mock import ConsoleEmailProvider
from macmarket_trader.domain.models import AppUserModel, StrategyReportRunModel
from macmarket_trader.domain.schemas import AtrHeatmapRequest
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import EmailLogRepository, StrategyReportRepository
from macmarket_trader.strategy_reports import (
    REPORT_TYPE_ATR_HEATMAP,
    StrategyReportService,
    normalize_schedule_report_type,
)


class RecordingEmailProvider(ConsoleEmailProvider):
    def __init__(self) -> None:
        self.messages = []

    def send(self, message):  # noqa: ANN001
        self.messages.append(message)
        return f"recorded-{len(self.messages)}"


class EmptyBarsMarketDataService:
    def historical_bars(self, *, symbol: str, timeframe: str, limit: int):  # noqa: ANN001
        return [], "empty-test", False


def _user(email: str, external_id: str) -> int:
    with SessionLocal() as session:
        user = AppUserModel(external_auth_user_id=external_id, email=email, display_name="ATR Scheduler", approval_status="approved", app_role="user")
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


def _schedule(repo: StrategyReportRepository, app_user_id: int, name: str, email: str, symbols: list[str]):
    return repo.create_schedule(
        app_user_id=app_user_id,
        name=name,
        frequency="daily",
        run_time="08:30",
        timezone_name="America/New_York",
        email_target=email,
        enabled=True,
        next_run_at=datetime.now(timezone.utc),
        payload={
            "report_type": REPORT_TYPE_ATR_HEATMAP,
            "symbols": symbols,
            "timeframes": ["1W", "1D", "4H", "1H", "30M"],
            "email_delivery_target": email,
        },
    )


def test_atr_report_type_dispatch_normalizes() -> None:
    import pytest

    assert normalize_schedule_report_type("atr_heatmap") == REPORT_TYPE_ATR_HEATMAP
    assert normalize_schedule_report_type("ATR_HEATMAP") == REPORT_TYPE_ATR_HEATMAP
    # Backend rejects unknown report types (the UI is the place that falls back).
    with pytest.raises(ValueError):
        normalize_schedule_report_type("unknown")


def test_atr_report_payload_csv_and_html_render() -> None:
    from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider

    class MD:
        def __init__(self) -> None:
            self.p = DeterministicFallbackMarketDataProvider()

        def historical_bars(self, symbol: str, timeframe: str, limit: int):  # noqa: ANN001
            return self.p.fetch_historical_bars(symbol=symbol, timeframe=timeframe, limit=limit), "polygon", False

    svc = AtrHeatmapService(MD())
    resp = svc.build_heatmap(AtrHeatmapRequest(symbols=["SPY", "QQQ"], timeframes=["1W", "1D", "4H", "1H", "30M"])).model_dump(mode="json")
    report = build_atr_report_payload(response=resp, profile_name="Scheduled ATR")
    # Report contents required by the spec.
    assert "summary" in report and "top_long" in report and "top_short" in report and "recently_flipped" in report
    assert set(report["summary"].keys()) >= {"long_count", "short_count", "mixed_count", "unavailable_count"}
    csv = atr_heatmap_csv(report)
    assert csv.splitlines()[0].startswith("symbol,1w,1d,4h,1h,30m,alignment_score,alignment_label")
    html = atr_heatmap_html(report)
    assert "ATR Direction Heatmap" in html and "State table" in html
    text = atr_heatmap_text(report)
    assert "ATR Direction Heatmap" in text


def test_atr_heatmap_schedule_run_sends_email_only() -> None:
    repo = StrategyReportRepository(SessionLocal)
    email_repo = EmailLogRepository(SessionLocal)
    provider = RecordingEmailProvider()
    service = StrategyReportService(report_repo=repo, email_provider=provider, email_log_repo=email_repo)
    user_id = _user("atr@example.com", "atr_scheduler_user")
    schedule = _schedule(repo, user_id, "ATR scheduled symbols", "atr@example.com", ["SPY", "QQQ"])

    payload = service.run_schedule(schedule.id, trigger="test")

    assert payload["report_type"] == REPORT_TYPE_ATR_HEATMAP
    assert payload["report_type_label"] == "ATR Direction Heatmap"
    assert int(payload["summary"]["usable_row_count"]) > 0
    # Exactly one email per scheduled run; no SMS channel exists for reports.
    assert len(provider.messages) == 1
    message = provider.messages[0]
    assert message.template_name == "atr_heatmap_scheduled_report"
    assert "ATR Direction Heatmap" in message.subject
    assert "ATR Direction Heatmap" in (message.html or "")
    # The report payload carries no SMS field/channel.
    assert "sms" not in payload and "sms_body" not in payload


def test_atr_heatmap_schedule_failure_sends_failure_email_and_advances() -> None:
    repo = StrategyReportRepository(SessionLocal)
    email_repo = EmailLogRepository(SessionLocal)
    provider = RecordingEmailProvider()
    service = StrategyReportService(report_repo=repo, email_provider=provider, email_log_repo=email_repo)
    service.market_data_service = EmptyBarsMarketDataService()
    user_id = _user("atrfail@example.com", "atr_fail_user")
    schedule = _schedule(repo, user_id, "ATR no-data symbols", "atrfail@example.com", ["ZZZZ"])

    payload = service.run_schedule(schedule.id, trigger="test")

    assert payload["report_type"] == REPORT_TYPE_ATR_HEATMAP
    assert payload["status"] == "failed"
    assert provider.messages  # a failure email is sent
    with SessionLocal() as session:
        runs = list(session.execute(select(StrategyReportRunModel).where(StrategyReportRunModel.schedule_id == schedule.id)).scalars())
    assert runs and runs[-1].status == "failed"
