"""Local operator CLI for health checks, samples, and database init."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import date, timedelta

from sqlalchemy.engine import make_url

from macmarket_trader.config import settings
from macmarket_trader.agent_mode.service import AgentModeService
from macmarket_trader.dev.seed_demo import seed_demo_data
from macmarket_trader.domain.schemas import Bar, PortfolioSnapshot, ReplayRunRequest
from macmarket_trader.replay.engine import ReplayEngine
from macmarket_trader.service import RecommendationService
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import EmailLogRepository, StrategyReportRepository
from macmarket_trader.data.providers.registry import build_email_provider
from macmarket_trader.strategy_reports import REPORT_TYPE_MOMENTUM_HEATMAP, StrategyReportService
from macmarket_trader.storage.db import init_db


def _sample_bars() -> list[Bar]:
    base = date(2026, 1, 1)
    return [
        Bar(
            date=base + timedelta(days=i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100.5 + i,
            volume=1_000_000 + i * 10_000,
            rel_volume=1.2,
        )
        for i in range(25)
    ]


def _database_diagnostics() -> dict[str, object]:
    url = make_url(settings.database_url)
    dialect = url.get_backend_name()
    database = url.database
    sqlite_path = None
    if dialect == "sqlite" and database and database != ":memory:":
        sqlite_path = str(Path(database).expanduser().resolve())
    return {
        "status": "ok",
        "database": {
            "dialect": dialect,
            "driver": url.drivername,
            "url_redacted": url.render_as_string(hide_password=True),
            "sqlite_path": sqlite_path,
            "sqlite_path_exists": Path(sqlite_path).exists() if sqlite_path else None,
        },
        "working_directory": str(Path.cwd()),
        "secrets_redacted": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="macmarket-trader")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    sub.add_parser("db-diagnostics")
    sub.add_parser("generate-sample-recommendation")
    sub.add_parser("run-sample-replay")
    sub.add_parser("init-db")
    sub.add_parser("seed-demo-data")
    sub.add_parser("run-due-strategy-schedules")
    sub.add_parser("run-due-agent-mode")
    sub.add_parser("run-due-momentum-heatmap-reports")
    args = parser.parse_args()

    service = RecommendationService()
    strategy_report_service = StrategyReportService(
        report_repo=StrategyReportRepository(SessionLocal),
        email_provider=build_email_provider(),
        email_log_repo=EmailLogRepository(SessionLocal),
    )

    if args.command == "health":
        payload = {"status": "ok", "service": "macmarket-trader"}
    elif args.command == "db-diagnostics":
        payload = _database_diagnostics()
    elif args.command == "generate-sample-recommendation":
        rec = service.generate(
            symbol="AAPL",
            bars=_sample_bars(),
            event_text="Earnings beat with raised guidance and strong cloud demand.",
            event=None,
            portfolio=PortfolioSnapshot(),
        )
        payload = rec.model_dump(mode="json")
    elif args.command == "run-sample-replay":
        replay = ReplayEngine(service=service)
        response = replay.run(
            ReplayRunRequest(
                symbol="AAPL",
                event_texts=[
                    "Earnings beat with guidance raise",
                    "Follow-through analyst upgrades",
                    "Macro rates shock",
                ],
                bars=_sample_bars(),
                portfolio=PortfolioSnapshot(),
            )
        )
        payload = response.model_dump(mode="json")
    elif args.command == "seed-demo-data":
        payload = seed_demo_data()
    elif args.command == "run-due-strategy-schedules":
        init_db()
        payload = {"runs": strategy_report_service.run_due_schedules()}
    elif args.command == "run-due-agent-mode":
        init_db()
        payload = {
            "runs": AgentModeService().run_due(),
            "status": "agent_mode_due_run_complete",
            "paper_only": True,
            "no_live_routing": True,
        }
    elif args.command == "run-due-momentum-heatmap-reports":
        init_db()
        payload = {
            "runs": strategy_report_service.run_due_schedules(report_types={REPORT_TYPE_MOMENTUM_HEATMAP}),
            "status": "momentum_heatmap_due_schedule_run_complete",
            "detail": "Delegates to strategy_report_schedules entries with report_type=momentum_heatmap.",
        }
    else:
        init_db()
        payload = {"status": "initialized", "database": "sqlite"}

    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
