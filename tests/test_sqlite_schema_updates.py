from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from macmarket_trader.cli import _database_diagnostics
from macmarket_trader.config import settings
from macmarket_trader.storage.db import apply_schema_updates, build_engine


def _alembic_config(database_url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[1]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("script_location", str(repo_root / "alembic"))
    return config


def _create_legacy_watchlists_table(database_url: str, *, include_updated_at: bool = False) -> None:
    engine = build_engine(database_url)
    updated_at_column = ", updated_at DATETIME" if include_updated_at else ""
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE watchlists ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "app_user_id INTEGER NOT NULL, "
                "name VARCHAR(128) NOT NULL, "
                "symbols JSON, "
                "created_at DATETIME NOT NULL"
                f"{updated_at_column}"
                ")"
            )
        )
        conn.execute(
            text(
                "INSERT INTO watchlists "
                "(app_user_id, name, symbols, created_at"
                f"{', updated_at' if include_updated_at else ''}) "
                "VALUES (42, 'Legacy Watchlist', '[\"SPY\", \"QQQ\"]', "
                "'2026-05-30 13:45:00'"
                f"{', NULL' if include_updated_at else ''})"
            )
        )


def test_apply_schema_updates_adds_nullable_backfilled_watchlists_updated_at(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'legacy-watchlists.db'}"
    _create_legacy_watchlists_table(database_url)
    engine = build_engine(database_url)

    applied = apply_schema_updates(engine)

    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("watchlists")}
    assert "watchlists.updated_at" in applied
    assert columns["updated_at"]["nullable"] is True
    assert columns["is_default"]["nullable"] is False

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT created_at, updated_at, is_default FROM watchlists WHERE id = 1")
        ).mappings().one()
    assert row["updated_at"] == row["created_at"]
    assert row["is_default"] in (0, False)

    rerun = apply_schema_updates(engine)
    assert "watchlists.updated_at" not in rerun


def test_apply_schema_updates_backfills_partially_added_watchlists_updated_at(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'partial-watchlists.db'}"
    _create_legacy_watchlists_table(database_url, include_updated_at=True)
    engine = build_engine(database_url)

    applied = apply_schema_updates(engine)

    assert "watchlists.updated_at" not in applied
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT created_at, updated_at, is_default FROM watchlists WHERE id = 1")
        ).mappings().one()
    assert row["updated_at"] == row["created_at"]
    assert row["is_default"] in (0, False)


def test_agent_operational_controls_migration_backfills_legacy_watchlists(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'alembic-watchlists.db'}"
    _create_legacy_watchlists_table(database_url)
    engine = build_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE app_users (id INTEGER PRIMARY KEY AUTOINCREMENT)"))
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('20260531_0014')"))

    command.upgrade(_alembic_config(database_url), "20260602_0015")

    inspector = inspect(build_engine(database_url))
    columns = {column["name"]: column for column in inspector.get_columns("watchlists")}
    indexes = {index["name"] for index in inspector.get_indexes("watchlists")}
    assert {"description", "is_default", "updated_at"}.issubset(columns)
    assert columns["updated_at"]["nullable"] is True
    assert "ix_watchlists_is_default" in indexes
    assert "ix_watchlists_updated_at" in indexes

    with build_engine(database_url).connect() as conn:
        row = conn.execute(
            text("SELECT created_at, updated_at, is_default FROM watchlists WHERE id = 1")
        ).mappings().one()
    assert row["updated_at"] == row["created_at"]
    assert row["is_default"] in (0, False)


def test_apply_schema_updates_includes_nullable_agent_scheduler_diagnostics(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'agent-scheduler-diagnostics.db'}"
    engine = build_engine(database_url)

    apply_schema_updates(engine)

    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("agent_mode_settings")}
    for column_name in (
        "scheduler_last_checked_at",
        "scheduler_last_check_result",
        "scheduler_last_check_reason",
        "scheduler_last_due_at",
        "scheduler_last_run_id",
        "scheduler_last_window_key",
    ):
        assert column_name in columns
        assert columns[column_name]["nullable"] is True


def test_database_diagnostics_redacts_database_url(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+psycopg://macmarket:super-secret-password@localhost:5432/macmarket_trader",
    )

    payload = _database_diagnostics()

    assert payload["database"]["dialect"] == "postgresql"
    rendered = str(payload["database"]["url_redacted"])
    assert "super-secret-password" not in rendered
    assert "postgresql+psycopg://" in rendered
    assert payload["secrets_redacted"] is True
