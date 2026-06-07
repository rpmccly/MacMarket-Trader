"""Local operator CLI for health checks, samples, and database init."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from pathlib import Path
from datetime import date, datetime, timedelta

from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import make_url

from macmarket_trader.config import settings
from macmarket_trader.agent_mode.service import AgentModeService
from macmarket_trader.dev.seed_demo import seed_demo_data
from macmarket_trader.domain.schemas import Bar, PortfolioSnapshot, ReplayRunRequest
from macmarket_trader.replay.engine import ReplayEngine
from macmarket_trader.service import RecommendationService
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import (
    AgentProfileRepository,
    EmailLogRepository,
    StrategyReportRepository,
)
from macmarket_trader.data.providers.registry import build_email_provider
from macmarket_trader.strategy_reports import REPORT_TYPE_MOMENTUM_HEATMAP, StrategyReportService
from macmarket_trader.storage.db import apply_schema_updates, init_db


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


def _safe_init_db_for_cli() -> None:
    try:
        init_db()
        # Self-heal the schema for every CLI entrypoint (the scheduler check runs
        # here). apply_schema_updates ALTER-adds columns that init_db's create_all
        # cannot add to existing tables — e.g. the Phase 11 agent_mode_runs profile
        # columns. Then migrate any legacy single-agent settings into profiles so
        # the scheduler can evaluate them.
        apply_schema_updates()
        _migrate_agent_profiles_safely()
    except OperationalError as exc:
        if "already exists" not in str(exc).lower():
            raise


def _migrate_agent_profiles_safely() -> dict[str, int] | None:
    """Idempotently migrate legacy Agent Mode settings into Agent Profiles.

    Never raises: a migration hiccup must not crash a CLI command or app startup.
    """
    try:
        return AgentProfileRepository(SessionLocal).migrate_legacy_settings_to_profiles()
    except Exception:  # noqa: BLE001 - migration is best-effort and self-healing.
        return None


def _safe_subprocess_json(command: list[str]) -> dict[str, object]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except Exception as exc:  # noqa: BLE001 - diagnostics should never crash the CLI.
        return {"available": False, "reason": type(exc).__name__}
    return {
        "available": True,
        "returncode": result.returncode,
        "stdout": (result.stdout or "").strip()[:500],
        "stderr": (result.stderr or "").strip()[:500],
    }


def _windows_agent_scheduler_runtime() -> dict[str, object]:
    if platform.system().lower() != "windows":
        return {"platform": platform.system(), "windows_checks": False}
    task = _safe_subprocess_json(["schtasks", "/query", "/tn", "MacMarket-AgentScheduler", "/fo", "LIST", "/v"])
    process = _safe_subprocess_json(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "$self = $PID; "
            "$all = @(Get-CimInstance Win32_Process); "
            "$p = @($all | Where-Object { "
            "$_.ProcessId -ne $self -and $_.Name -match '(?i)powershell' -and $_.CommandLine -and "
            "$_.CommandLine -notmatch '(?i)\\s-Command\\s' -and "
            "$_.CommandLine -match '(?i)\\s-File\\s+.*run-agent-mode-scheduler\\.ps1' "
            "}); "
            "$checks = @($all | Where-Object { "
            "$_.ProcessId -ne $self -and $_.CommandLine -and "
            "$_.CommandLine -match '(?i)agent-scheduler-check' "
            "}); "
            "[pscustomobject]@{"
            "count=$p.Count;"
            "schedulerCheckCount=$checks.Count;"
            "processIds=($p | Select-Object -ExpandProperty ProcessId);"
            "schedulerCheckProcessIds=($checks | Select-Object -ExpandProperty ProcessId)"
            "} | ConvertTo-Json -Compress",
        ]
    )
    detected_scheduler_process_count = None
    detected_scheduler_check_count = None
    if process.get("stdout"):
        try:
            parsed = json.loads(str(process["stdout"]))
            detected_scheduler_process_count = int(parsed.get("count", 0))
            detected_scheduler_check_count = int(parsed.get("schedulerCheckCount", 0))
        except Exception:
            detected_scheduler_process_count = None
    return {
        "platform": "Windows",
        "windows_checks": True,
        "task_registered": bool(task.get("returncode") == 0),
        "task_query": task,
        "process_query": process,
        "detected_scheduler_process_count": detected_scheduler_process_count,
        "detected_scheduler_check_count": detected_scheduler_check_count,
    }


def _agent_scheduler_log_diagnostics(log_path: Path) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": str(log_path),
        "exists": log_path.exists(),
        "last_write_time": None,
        "last_startup_error": None,
        "last_heartbeat": None,
        "last_check_start": None,
        "last_check_end": None,
        "last_check_exit_code": None,
    }
    if not log_path.exists():
        return payload
    try:
        payload["last_write_time"] = datetime.fromtimestamp(log_path.stat().st_mtime).astimezone().isoformat()
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
    except Exception as exc:  # noqa: BLE001 - diagnostics should stay safe and redacted.
        payload["last_startup_error"] = f"log_read_error:{type(exc).__name__}"
        return payload
    for line in lines:
        safe_line = line[:500]
        if "STARTUP_ERROR" in line:
            payload["last_startup_error"] = safe_line
        if "HEARTBEAT" in line:
            payload["last_heartbeat"] = safe_line
        if "SCHEDULER_CHECK START" in line:
            payload["last_check_start"] = safe_line
        if "SCHEDULER_CHECK END" in line:
            payload["last_check_end"] = safe_line
            marker = "exit_code="
            if marker in line:
                payload["last_check_exit_code"] = line.rsplit(marker, 1)[-1].strip()[:20]
    return payload


def _agent_scheduler_diagnostics_payload() -> dict[str, object]:
    _safe_init_db_for_cli()
    service_payload = AgentModeService().scheduler_diagnostics()
    repo_root = Path.cwd()
    script_path = repo_root / "scripts" / "run-agent-mode-scheduler.ps1"
    log_path = repo_root / "logs" / "agent_scheduler.log"
    return {
        **service_payload,
        "database": _database_diagnostics()["database"],
        "working_directory": str(repo_root),
        "scheduler_script": {
            "path": str(script_path),
            "exists": script_path.exists(),
        },
        "scheduler_log": {
            **_agent_scheduler_log_diagnostics(log_path),
        },
        "runtime": _windows_agent_scheduler_runtime(),
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
    sub.add_parser("agent-scheduler-diagnostics")
    agent_check = sub.add_parser("agent-scheduler-check")
    agent_check.add_argument("--dry-run", action="store_true", help="Run due users through dry-run only; creates no paper orders.")
    agent_check.add_argument("--no-notifications", action="store_true", help="Suppress Agent Mode email/SMS digests for this check.")
    agent_check.add_argument("--force", action="store_true", help="Run the check even when the configured time is not due.")
    agent_check.add_argument("--user-id", type=int, default=None, help="Limit the check to one local app_user_id.")
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
        _safe_init_db_for_cli()
        payload = {"runs": strategy_report_service.run_due_schedules()}
    elif args.command == "run-due-agent-mode":
        _safe_init_db_for_cli()
        payload = {
            "runs": AgentModeService().run_due(),
            "status": "agent_mode_due_run_complete",
            "paper_only": True,
            "no_live_routing": True,
        }
    elif args.command == "agent-scheduler-diagnostics":
        payload = _agent_scheduler_diagnostics_payload()
    elif args.command == "agent-scheduler-check":
        _safe_init_db_for_cli()
        dry_run = bool(getattr(args, "dry_run", False))
        no_notifications = bool(getattr(args, "no_notifications", False)) or dry_run
        payload = {
            "runs": AgentModeService().run_due(
                dry_run=dry_run,
                no_notifications=no_notifications,
                force=bool(getattr(args, "force", False)),
                app_user_id=getattr(args, "user_id", None),
            ),
            "status": "agent_scheduler_check_complete",
            "dry_run": dry_run,
            "notifications_suppressed": no_notifications,
            "paper_only": True,
            "no_live_routing": True,
            "secrets_redacted": True,
        }
    elif args.command == "run-due-momentum-heatmap-reports":
        _safe_init_db_for_cli()
        payload = {
            "runs": strategy_report_service.run_due_schedules(report_types={REPORT_TYPE_MOMENTUM_HEATMAP}),
            "status": "momentum_heatmap_due_schedule_run_complete",
            "detail": "Delegates to strategy_report_schedules entries with report_type=momentum_heatmap.",
        }
    else:
        _safe_init_db_for_cli()
        payload = {"status": "initialized", "database": "sqlite"}

    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
