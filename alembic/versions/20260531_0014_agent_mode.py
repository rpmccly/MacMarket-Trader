"""Add paper-only Agent Mode settings and run audit tables.

Revision ID: 20260531_0014
Revises: 20260529_0013
Create Date: 2026-05-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260531_0014"
down_revision = "20260529_0013"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("agent_mode_settings"):
        op.create_table(
            "agent_mode_settings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, default=False),
            sa.Column("paused", sa.Boolean(), nullable=False, default=False),
            sa.Column("kill_switch_enabled", sa.Boolean(), nullable=False, default=False),
            sa.Column("daily_run_time", sa.String(length=8), nullable=False),
            sa.Column("timezone", sa.String(length=64), nullable=False),
            sa.Column("universe_source", sa.String(length=32), nullable=False),
            sa.Column("manual_symbols", sa.JSON(), nullable=False),
            sa.Column("watchlist_ids", sa.JSON(), nullable=False),
            sa.Column("max_positions", sa.Integer(), nullable=False, default=5),
            sa.Column("scan_depth", sa.Integer(), nullable=False, default=12),
            sa.Column("allow_opens", sa.Boolean(), nullable=False, default=True),
            sa.Column("allow_closes", sa.Boolean(), nullable=False, default=True),
            sa.Column("allow_scale_resize", sa.Boolean(), nullable=False, default=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_mode_settings_app_user_id", "agent_mode_settings", ["app_user_id"], unique=True)
        op.create_index("ix_agent_mode_settings_enabled", "agent_mode_settings", ["enabled"])
        op.create_index("ix_agent_mode_settings_paused", "agent_mode_settings", ["paused"])
        op.create_index("ix_agent_mode_settings_kill_switch_enabled", "agent_mode_settings", ["kill_switch_enabled"])
        op.create_index("ix_agent_mode_settings_universe_source", "agent_mode_settings", ["universe_source"])
        op.create_index("ix_agent_mode_settings_created_at", "agent_mode_settings", ["created_at"])
        op.create_index("ix_agent_mode_settings_updated_at", "agent_mode_settings", ["updated_at"])

    if not _has_table("agent_mode_runs"):
        op.create_table(
            "agent_mode_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.String(length=80), nullable=False),
            sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("execution_mode", sa.String(length=16), nullable=False),
            sa.Column("dry_run", sa.Boolean(), nullable=False, default=True),
            sa.Column("intent_count", sa.Integer(), nullable=False, default=0),
            sa.Column("executed_order_count", sa.Integer(), nullable=False, default=0),
            sa.Column("request_json", sa.JSON(), nullable=False),
            sa.Column("response_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_agent_mode_runs_run_id", "agent_mode_runs", ["run_id"], unique=True)
        op.create_index("ix_agent_mode_runs_app_user_id", "agent_mode_runs", ["app_user_id"])
        op.create_index("ix_agent_mode_runs_status", "agent_mode_runs", ["status"])
        op.create_index("ix_agent_mode_runs_execution_mode", "agent_mode_runs", ["execution_mode"])
        op.create_index("ix_agent_mode_runs_dry_run", "agent_mode_runs", ["dry_run"])
        op.create_index("ix_agent_mode_runs_created_at", "agent_mode_runs", ["created_at"])
        op.create_index("ix_agent_mode_runs_completed_at", "agent_mode_runs", ["completed_at"])
        op.create_index("ix_agent_mode_runs_user_created", "agent_mode_runs", ["app_user_id", "created_at"])


def downgrade() -> None:
    if _has_table("agent_mode_runs"):
        op.drop_index("ix_agent_mode_runs_user_created", table_name="agent_mode_runs")
        op.drop_index("ix_agent_mode_runs_completed_at", table_name="agent_mode_runs")
        op.drop_index("ix_agent_mode_runs_created_at", table_name="agent_mode_runs")
        op.drop_index("ix_agent_mode_runs_dry_run", table_name="agent_mode_runs")
        op.drop_index("ix_agent_mode_runs_execution_mode", table_name="agent_mode_runs")
        op.drop_index("ix_agent_mode_runs_status", table_name="agent_mode_runs")
        op.drop_index("ix_agent_mode_runs_app_user_id", table_name="agent_mode_runs")
        op.drop_index("ix_agent_mode_runs_run_id", table_name="agent_mode_runs")
        op.drop_table("agent_mode_runs")

    if _has_table("agent_mode_settings"):
        op.drop_index("ix_agent_mode_settings_updated_at", table_name="agent_mode_settings")
        op.drop_index("ix_agent_mode_settings_created_at", table_name="agent_mode_settings")
        op.drop_index("ix_agent_mode_settings_universe_source", table_name="agent_mode_settings")
        op.drop_index("ix_agent_mode_settings_kill_switch_enabled", table_name="agent_mode_settings")
        op.drop_index("ix_agent_mode_settings_paused", table_name="agent_mode_settings")
        op.drop_index("ix_agent_mode_settings_enabled", table_name="agent_mode_settings")
        op.drop_index("ix_agent_mode_settings_app_user_id", table_name="agent_mode_settings")
        op.drop_table("agent_mode_settings")
