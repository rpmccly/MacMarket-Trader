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


def test_agent_profiles_schema_and_migration_against_legacy_db(tmp_path) -> None:
    """Guardrail: a pre-Phase-11 deployed DB upgrades and migrates safely.

    Simulates an existing DB that has app_users + agent_mode_settings + an OLD
    agent_mode_runs (no profile columns) and NO agent_profiles table. Proves
    apply_schema_updates creates agent_profiles and adds the run profile columns,
    legacy agent_mode_settings stays intact, and migration backfills runs onto the
    new default Standard Strategy Agent profile.
    """
    from macmarket_trader.domain.models import AgentModeSettingsModel, AppUserModel
    from macmarket_trader.storage.db import build_session_factory
    from macmarket_trader.storage.repositories import AgentProfileRepository

    database_url = f"sqlite:///{tmp_path / 'legacy-agent.db'}"
    engine = build_engine(database_url)
    AppUserModel.__table__.create(engine)
    AgentModeSettingsModel.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE agent_mode_runs ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, run_id VARCHAR(80), app_user_id INTEGER, "
                "status VARCHAR(32), execution_mode VARCHAR(16), dry_run BOOLEAN, "
                "intent_count INTEGER, executed_order_count INTEGER, request_json JSON, "
                "response_json JSON, created_at DATETIME, completed_at DATETIME)"
            )
        )

    factory = build_session_factory(engine)
    with factory() as session:
        user = AppUserModel(
            external_auth_user_id="legacy-sub",
            email="legacy@example.com",
            display_name="Legacy",
            approval_status="approved",
        )
        session.add(user)
        session.flush()
        uid = user.id
        session.add(
            AgentModeSettingsModel(
                app_user_id=uid, enabled=True, daily_run_time="09:30", timezone="UTC", manual_symbols=["SPY"]
            )
        )
        session.commit()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agent_mode_runs (run_id, app_user_id, status, execution_mode, dry_run, "
                "intent_count, executed_order_count, request_json, response_json, created_at) "
                "VALUES ('legacy_run_1', :uid, 'completed', 'paper', 0, 0, 0, '{}', '{}', '2026-06-01 00:00:00')"
            ),
            {"uid": uid},
        )

    inspector0 = inspect(engine)
    assert not inspector0.has_table("agent_profiles")
    assert "agent_profile_id" not in {c["name"] for c in inspector0.get_columns("agent_mode_runs")}

    applied = apply_schema_updates(engine)

    inspector = inspect(engine)
    assert inspector.has_table("agent_profiles")
    run_cols = {c["name"] for c in inspector.get_columns("agent_mode_runs")}
    assert {"agent_profile_id", "agent_profile_name", "agent_type"}.issubset(run_cols)
    assert "agent_mode_runs.agent_profile_id" in applied
    with engine.connect() as conn:
        legacy = conn.execute(
            text("SELECT enabled, daily_run_time, timezone FROM agent_mode_settings WHERE app_user_id = :uid"),
            {"uid": uid},
        ).mappings().one()
    assert legacy["daily_run_time"] == "09:30"

    repo = AgentProfileRepository(factory)
    result = repo.migrate_legacy_settings_to_profiles()
    assert result["profiles_created"] == 1
    assert result["runs_backfilled"] == 1

    profiles = repo.list_profiles(app_user_id=uid)
    assert len(profiles) == 1
    default = profiles[0]
    assert default.name == "Standard Strategy Agent"
    assert default.agent_type == "standard"
    assert bool(default.is_default) is True
    assert bool(default.enabled) is True  # copied from legacy settings
    assert default.daily_run_time == "09:30"

    with engine.connect() as conn:
        run_row = conn.execute(
            text(
                "SELECT agent_profile_id, agent_profile_name, agent_type "
                "FROM agent_mode_runs WHERE run_id = 'legacy_run_1'"
            )
        ).mappings().one()
    assert run_row["agent_profile_id"] == default.id
    assert run_row["agent_profile_name"] == "Standard Strategy Agent"
    assert run_row["agent_type"] == "standard"

    # Idempotent: a second migration creates nothing new.
    again = repo.migrate_legacy_settings_to_profiles()
    assert again["profiles_created"] == 0
    assert len(repo.list_profiles(app_user_id=uid)) == 1


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
