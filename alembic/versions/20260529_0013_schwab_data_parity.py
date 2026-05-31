"""Add Schwab OAuth and data parity snapshot tables.

Revision ID: 20260529_0013
Revises: 20260524_0012
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260529_0013"
down_revision = "20260524_0012"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table("provider_oauth_tokens"):
        op.create_table(
            "provider_oauth_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=True),
            sa.Column("encrypted_access_token", sa.Text(), nullable=False),
            sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
            sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("token_type", sa.String(length=32), nullable=True),
            sa.Column("scope", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_provider_oauth_tokens_provider", "provider_oauth_tokens", ["provider"], unique=True)
        op.create_index("ix_provider_oauth_tokens_app_user_id", "provider_oauth_tokens", ["app_user_id"])
        op.create_index("ix_provider_oauth_tokens_status", "provider_oauth_tokens", ["status"])
        op.create_index("ix_provider_oauth_tokens_created_at", "provider_oauth_tokens", ["created_at"])
        op.create_index("ix_provider_oauth_tokens_updated_at", "provider_oauth_tokens", ["updated_at"])

    if not _has_table("provider_oauth_states"):
        op.create_table(
            "provider_oauth_states",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("state", sa.String(length=160), nullable=False),
            sa.Column("return_path", sa.String(length=255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_provider_oauth_states_provider", "provider_oauth_states", ["provider"])
        op.create_index("ix_provider_oauth_states_app_user_id", "provider_oauth_states", ["app_user_id"])
        op.create_index("ix_provider_oauth_states_state", "provider_oauth_states", ["state"], unique=True)
        op.create_index("ix_provider_oauth_states_expires_at", "provider_oauth_states", ["expires_at"])
        op.create_index("ix_provider_oauth_states_used_at", "provider_oauth_states", ["used_at"])
        op.create_index("ix_provider_oauth_states_created_at", "provider_oauth_states", ["created_at"])

    if not _has_table("provider_parity_snapshots"):
        op.create_table(
            "provider_parity_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("run_id", sa.String(length=80), nullable=False),
            sa.Column("request_json", sa.JSON(), nullable=False),
            sa.Column("response_json", sa.JSON(), nullable=False),
            sa.Column("provider_current", sa.String(length=64), nullable=False),
            sa.Column("provider_candidate", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_provider_parity_snapshots_app_user_id", "provider_parity_snapshots", ["app_user_id"])
        op.create_index("ix_provider_parity_snapshots_run_id", "provider_parity_snapshots", ["run_id"], unique=True)
        op.create_index("ix_provider_parity_snapshots_provider_current", "provider_parity_snapshots", ["provider_current"])
        op.create_index("ix_provider_parity_snapshots_provider_candidate", "provider_parity_snapshots", ["provider_candidate"])
        op.create_index("ix_provider_parity_snapshots_created_at", "provider_parity_snapshots", ["created_at"])
        op.create_index("ix_provider_parity_snapshots_user_created", "provider_parity_snapshots", ["app_user_id", "created_at"])


def downgrade() -> None:
    if _has_table("provider_parity_snapshots"):
        op.drop_table("provider_parity_snapshots")
    if _has_table("provider_oauth_states"):
        op.drop_table("provider_oauth_states")
    if _has_table("provider_oauth_tokens"):
        op.drop_table("provider_oauth_tokens")
