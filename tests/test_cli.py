import subprocess
import sys
from pathlib import Path


def test_cli_health_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "macmarket_trader.cli", "health"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "ok" in result.stdout.lower()


def test_cli_run_due_strategy_schedules_command() -> None:
    result = subprocess.run([sys.executable, "-m", "macmarket_trader.cli", "run-due-strategy-schedules"], check=True, capture_output=True, text=True)
    assert "runs" in result.stdout


def test_cli_agent_scheduler_diagnostics_redacts_runtime_details() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "macmarket_trader.cli", "agent-scheduler-diagnostics"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "agent-scheduler-check" in result.stdout
    assert '"secrets_redacted": true' in result.stdout
    assert '"scheduler_log"' in result.stdout
    assert '"last_write_time"' in result.stdout
    assert '"detected_scheduler_process_count"' in result.stdout
    assert "TWILIO_AUTH_TOKEN" not in result.stdout
    assert "Authorization:" not in result.stdout


def test_cli_agent_scheduler_check_dry_run_no_notifications() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "macmarket_trader.cli",
            "agent-scheduler-check",
            "--dry-run",
            "--no-notifications",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "agent_scheduler_check_complete" in result.stdout
    assert '"dry_run": true' in result.stdout
    assert '"notifications_suppressed": true' in result.stdout


def test_agent_scheduler_script_exposes_safe_foreground_and_loop_modes() -> None:
    script = Path("scripts/run-agent-mode-scheduler.ps1").read_text(encoding="utf-8")

    assert "[switch]$Once" in script
    assert "[switch]$Loop" in script
    assert "[switch]$DryRun" in script
    assert "[switch]$NoNotifications" in script
    assert "DB_DIAGNOSTICS" in script
    assert "SCHEDULER_CHECK" in script
    assert "STARTUP_ERROR" in script
    assert "HEARTBEAT" in script
