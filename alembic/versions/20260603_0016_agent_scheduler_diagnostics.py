"""Add Agent Mode scheduler diagnostic columns.

Revision ID: 20260603_0016
Revises: 20260602_0015
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260603_0016"
down_revision = "20260602_0015"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def upgrade() -> None:
    if not _has_table("agent_mode_settings"):
        return
    columns: list[tuple[str, sa.Column]] = [
        ("scheduler_last_checked_at", sa.Column("scheduler_last_checked_at", sa.DateTime(timezone=True), nullable=True)),
        ("scheduler_last_check_result", sa.Column("scheduler_last_check_result", sa.String(length=32), nullable=True)),
        ("scheduler_last_check_reason", sa.Column("scheduler_last_check_reason", sa.String(length=255), nullable=True)),
        ("scheduler_last_due_at", sa.Column("scheduler_last_due_at", sa.DateTime(timezone=True), nullable=True)),
        ("scheduler_last_run_id", sa.Column("scheduler_last_run_id", sa.String(length=80), nullable=True)),
        ("scheduler_last_window_key", sa.Column("scheduler_last_window_key", sa.String(length=80), nullable=True)),
    ]
    for column_name, column in columns:
        if not _has_column("agent_mode_settings", column_name):
            op.add_column("agent_mode_settings", column)
    indexes = {
        "ix_agent_mode_settings_scheduler_last_checked_at": ["scheduler_last_checked_at"],
        "ix_agent_mode_settings_scheduler_last_check_result": ["scheduler_last_check_result"],
        "ix_agent_mode_settings_scheduler_last_due_at": ["scheduler_last_due_at"],
        "ix_agent_mode_settings_scheduler_last_run_id": ["scheduler_last_run_id"],
        "ix_agent_mode_settings_scheduler_last_window_key": ["scheduler_last_window_key"],
    }
    for index_name, columns_for_index in indexes.items():
        if not _has_index("agent_mode_settings", index_name):
            op.create_index(index_name, "agent_mode_settings", columns_for_index)


def downgrade() -> None:
    if not _has_table("agent_mode_settings"):
        return
    for index_name in (
        "ix_agent_mode_settings_scheduler_last_window_key",
        "ix_agent_mode_settings_scheduler_last_run_id",
        "ix_agent_mode_settings_scheduler_last_due_at",
        "ix_agent_mode_settings_scheduler_last_check_result",
        "ix_agent_mode_settings_scheduler_last_checked_at",
    ):
        if _has_index("agent_mode_settings", index_name):
            op.drop_index(index_name, table_name="agent_mode_settings")
    for column_name in (
        "scheduler_last_window_key",
        "scheduler_last_run_id",
        "scheduler_last_due_at",
        "scheduler_last_check_reason",
        "scheduler_last_check_result",
        "scheduler_last_checked_at",
    ):
        if _has_column("agent_mode_settings", column_name):
            op.drop_column("agent_mode_settings", column_name)
