"""Add server-backed HACO Direction Heatmap profiles and snapshots.

Revision ID: 20260524_0012
Revises: 20260523_0011
Create Date: 2026-05-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_0012"
down_revision = "20260523_0011"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("haco_heatmap_profiles"):
        op.create_table(
            "haco_heatmap_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("profile_uid", sa.String(length=64), nullable=False),
            sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("categories", sa.JSON(), nullable=False),
            sa.Column("view_settings", sa.JSON(), nullable=False),
            sa.Column("report_preferences", sa.JSON(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("app_user_id", "profile_uid", name="uq_haco_heatmap_profiles_user_uid"),
        )
        op.create_index("ix_haco_heatmap_profiles_profile_uid", "haco_heatmap_profiles", ["profile_uid"])
        op.create_index("ix_haco_heatmap_profiles_app_user_id", "haco_heatmap_profiles", ["app_user_id"])
        op.create_index("ix_haco_heatmap_profiles_name", "haco_heatmap_profiles", ["name"])
        op.create_index("ix_haco_heatmap_profiles_is_default", "haco_heatmap_profiles", ["is_default"])
        op.create_index("ix_haco_heatmap_profiles_created_at", "haco_heatmap_profiles", ["created_at"])
        op.create_index("ix_haco_heatmap_profiles_updated_at", "haco_heatmap_profiles", ["updated_at"])
        op.create_index("ix_haco_heatmap_profiles_user_updated", "haco_heatmap_profiles", ["app_user_id", "updated_at"])

    if not _has_table("haco_heatmap_snapshots"):
        op.create_table(
            "haco_heatmap_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("snapshot_uid", sa.String(length=64), nullable=False),
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("haco_heatmap_profiles.id"), nullable=False),
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
        op.create_index("ix_haco_heatmap_snapshots_snapshot_uid", "haco_heatmap_snapshots", ["snapshot_uid"], unique=True)
        op.create_index("ix_haco_heatmap_snapshots_profile_id", "haco_heatmap_snapshots", ["profile_id"])
        op.create_index("ix_haco_heatmap_snapshots_app_user_id", "haco_heatmap_snapshots", ["app_user_id"])
        op.create_index("ix_haco_heatmap_snapshots_status", "haco_heatmap_snapshots", ["status"])
        op.create_index("ix_haco_heatmap_snapshots_generated_at", "haco_heatmap_snapshots", ["generated_at"])
        op.create_index("ix_haco_heatmap_snapshots_report_label", "haco_heatmap_snapshots", ["report_label"])
        op.create_index("ix_haco_heatmap_snapshots_previous_snapshot_id", "haco_heatmap_snapshots", ["previous_snapshot_id"])
        op.create_index("ix_haco_heatmap_snapshots_created_at", "haco_heatmap_snapshots", ["created_at"])
        op.create_index("ix_haco_heatmap_snapshots_profile_generated", "haco_heatmap_snapshots", ["profile_id", "generated_at"])
        op.create_index("ix_haco_heatmap_snapshots_user_generated", "haco_heatmap_snapshots", ["app_user_id", "generated_at"])


def downgrade() -> None:
    if _has_table("haco_heatmap_snapshots"):
        op.drop_table("haco_heatmap_snapshots")
    if _has_table("haco_heatmap_profiles"):
        op.drop_table("haco_heatmap_profiles")
