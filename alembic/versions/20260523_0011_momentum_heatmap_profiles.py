"""Add server-backed Momentum Heatmap profiles and snapshots.

Revision ID: 20260523_0011
Revises: 20260503_0010
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260523_0011"
down_revision = "20260503_0010"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("momentum_heatmap_profiles"):
        op.create_table(
            "momentum_heatmap_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("profile_uid", sa.String(length=64), nullable=False),
            sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("categories", sa.JSON(), nullable=False),
            sa.Column("color_ranges", sa.JSON(), nullable=False),
            sa.Column("view_settings", sa.JSON(), nullable=False),
            sa.Column("report_preferences", sa.JSON(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("app_user_id", "profile_uid", name="uq_momentum_heatmap_profiles_user_uid"),
        )
        op.create_index("ix_momentum_heatmap_profiles_profile_uid", "momentum_heatmap_profiles", ["profile_uid"])
        op.create_index("ix_momentum_heatmap_profiles_app_user_id", "momentum_heatmap_profiles", ["app_user_id"])
        op.create_index("ix_momentum_heatmap_profiles_name", "momentum_heatmap_profiles", ["name"])
        op.create_index("ix_momentum_heatmap_profiles_is_default", "momentum_heatmap_profiles", ["is_default"])
        op.create_index("ix_momentum_heatmap_profiles_created_at", "momentum_heatmap_profiles", ["created_at"])
        op.create_index("ix_momentum_heatmap_profiles_updated_at", "momentum_heatmap_profiles", ["updated_at"])
        op.create_index(
            "ix_momentum_heatmap_profiles_user_updated",
            "momentum_heatmap_profiles",
            ["app_user_id", "updated_at"],
        )

    if not _has_table("momentum_heatmap_snapshots"):
        op.create_table(
            "momentum_heatmap_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("snapshot_uid", sa.String(length=64), nullable=False),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("momentum_heatmap_profiles.id"), nullable=False),
            sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("report_label", sa.String(length=128), nullable=True),
            sa.Column("requested_categories", sa.JSON(), nullable=True),
            sa.Column("requested_rows", sa.JSON(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("category_summaries", sa.JSON(), nullable=False),
            sa.Column("unsupported_summary", sa.JSON(), nullable=False),
            sa.Column("previous_snapshot_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_momentum_heatmap_snapshots_snapshot_uid", "momentum_heatmap_snapshots", ["snapshot_uid"], unique=True)
        op.create_index("ix_momentum_heatmap_snapshots_profile_id", "momentum_heatmap_snapshots", ["profile_id"])
        op.create_index("ix_momentum_heatmap_snapshots_app_user_id", "momentum_heatmap_snapshots", ["app_user_id"])
        op.create_index("ix_momentum_heatmap_snapshots_status", "momentum_heatmap_snapshots", ["status"])
        op.create_index("ix_momentum_heatmap_snapshots_generated_at", "momentum_heatmap_snapshots", ["generated_at"])
        op.create_index("ix_momentum_heatmap_snapshots_report_label", "momentum_heatmap_snapshots", ["report_label"])
        op.create_index("ix_momentum_heatmap_snapshots_previous_snapshot_id", "momentum_heatmap_snapshots", ["previous_snapshot_id"])
        op.create_index("ix_momentum_heatmap_snapshots_created_at", "momentum_heatmap_snapshots", ["created_at"])
        op.create_index(
            "ix_momentum_heatmap_snapshots_profile_generated",
            "momentum_heatmap_snapshots",
            ["profile_id", "generated_at"],
        )
        op.create_index(
            "ix_momentum_heatmap_snapshots_user_generated",
            "momentum_heatmap_snapshots",
            ["app_user_id", "generated_at"],
        )

    if not _has_table("momentum_heatmap_schedule_preferences"):
        op.create_table(
            "momentum_heatmap_schedule_preferences",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("schedule_uid", sa.String(length=64), nullable=False),
            sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("momentum_heatmap_profiles.id"), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("timezone", sa.String(length=64), nullable=False),
            sa.Column("run_time", sa.String(length=16), nullable=False),
            sa.Column("days_of_week", sa.JSON(), nullable=False),
            sa.Column("report_mode", sa.String(length=32), nullable=False),
            sa.Column("recipients", sa.JSON(), nullable=False),
            sa.Column("include_csv_attachment", sa.Boolean(), nullable=False),
            sa.Column("include_full_table", sa.Boolean(), nullable=False),
            sa.Column("latest_status", sa.String(length=32), nullable=False),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("app_user_id", "profile_id", name="uq_momentum_heatmap_schedule_user_profile"),
        )
        op.create_index("ix_momentum_heatmap_schedule_preferences_schedule_uid", "momentum_heatmap_schedule_preferences", ["schedule_uid"], unique=True)
        op.create_index("ix_momentum_heatmap_schedule_preferences_app_user_id", "momentum_heatmap_schedule_preferences", ["app_user_id"])
        op.create_index("ix_momentum_heatmap_schedule_preferences_profile_id", "momentum_heatmap_schedule_preferences", ["profile_id"])
        op.create_index("ix_momentum_heatmap_schedule_preferences_enabled", "momentum_heatmap_schedule_preferences", ["enabled"])
        op.create_index("ix_momentum_heatmap_schedule_preferences_next_run_at", "momentum_heatmap_schedule_preferences", ["next_run_at"])
        op.create_index("ix_momentum_heatmap_schedule_preferences_created_at", "momentum_heatmap_schedule_preferences", ["created_at"])
        op.create_index("ix_momentum_heatmap_schedule_preferences_updated_at", "momentum_heatmap_schedule_preferences", ["updated_at"])


def downgrade() -> None:
    if _has_table("momentum_heatmap_schedule_preferences"):
        op.drop_table("momentum_heatmap_schedule_preferences")
    if _has_table("momentum_heatmap_snapshots"):
        op.drop_table("momentum_heatmap_snapshots")
    if _has_table("momentum_heatmap_profiles"):
        op.drop_table("momentum_heatmap_profiles")
