"""Add Agent Mode operational controls and notification audit rows.

Revision ID: 20260602_0015
Revises: 20260531_0014
Create Date: 2026-06-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260602_0015"
down_revision = "20260531_0014"
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


def _backfill_watchlists_updated_at() -> None:
    if not _has_column("watchlists", "updated_at"):
        return
    if _has_column("watchlists", "created_at"):
        op.execute(
            "UPDATE watchlists "
            "SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
            "WHERE updated_at IS NULL"
        )
    else:
        op.execute(
            "UPDATE watchlists "
            "SET updated_at = CURRENT_TIMESTAMP "
            "WHERE updated_at IS NULL"
        )


def upgrade() -> None:
    if _has_table("watchlists"):
        if not _has_column("watchlists", "description"):
            op.add_column("watchlists", sa.Column("description", sa.Text(), nullable=True))
        if not _has_column("watchlists", "is_default"):
            op.add_column(
                "watchlists",
                sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
        op.execute("UPDATE watchlists SET is_default = 0 WHERE is_default IS NULL")
        if not _has_index("watchlists", "ix_watchlists_is_default"):
            op.create_index("ix_watchlists_is_default", "watchlists", ["is_default"])
        if not _has_column("watchlists", "updated_at"):
            op.add_column("watchlists", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        _backfill_watchlists_updated_at()
        if not _has_index("watchlists", "ix_watchlists_updated_at"):
            op.create_index("ix_watchlists_updated_at", "watchlists", ["updated_at"])

    if _has_table("agent_mode_settings"):
        columns: list[tuple[str, sa.Column]] = [
            ("default_watchlist_id", sa.Column("default_watchlist_id", sa.Integer(), nullable=True)),
            ("max_dollars_per_trade", sa.Column("max_dollars_per_trade", sa.Float(), nullable=True)),
            ("max_percent_of_paper_account_per_trade", sa.Column("max_percent_of_paper_account_per_trade", sa.Float(), nullable=True)),
            ("max_new_trades_per_run", sa.Column("max_new_trades_per_run", sa.Integer(), nullable=False, server_default="5")),
            ("max_new_trades_per_day", sa.Column("max_new_trades_per_day", sa.Integer(), nullable=False, server_default="5")),
            ("max_open_agent_positions", sa.Column("max_open_agent_positions", sa.Integer(), nullable=False, server_default="5")),
            ("max_exposure_per_symbol", sa.Column("max_exposure_per_symbol", sa.Float(), nullable=True)),
            ("min_cash_reserve", sa.Column("min_cash_reserve", sa.Float(), nullable=False, server_default="0")),
            ("allow_scale_ins", sa.Column("allow_scale_ins", sa.Boolean(), nullable=False, server_default=sa.false())),
            (
                "allow_new_trade_when_symbol_already_open",
                sa.Column("allow_new_trade_when_symbol_already_open", sa.Boolean(), nullable=False, server_default=sa.false()),
            ),
            (
                "require_confirmation_for_restricted",
                sa.Column("require_confirmation_for_restricted", sa.Boolean(), nullable=False, server_default=sa.true()),
            ),
            ("notification_preference", sa.Column("notification_preference", sa.String(length=16), nullable=False, server_default="none")),
            ("notification_phone_number", sa.Column("notification_phone_number", sa.String(length=32), nullable=True)),
            ("sms_consent_confirmed", sa.Column("sms_consent_confirmed", sa.Boolean(), nullable=False, server_default=sa.false())),
            (
                "email_notifications_enabled",
                sa.Column("email_notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            ),
            (
                "sms_notifications_enabled",
                sa.Column("sms_notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            ),
        ]
        for column_name, column in columns:
            if not _has_column("agent_mode_settings", column_name):
                op.add_column("agent_mode_settings", column)
        if not _has_index("agent_mode_settings", "ix_agent_mode_settings_default_watchlist_id"):
            op.create_index("ix_agent_mode_settings_default_watchlist_id", "agent_mode_settings", ["default_watchlist_id"])

    if not _has_table("notification_attempts"):
        op.create_table(
            "notification_attempts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id"), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False),
            sa.Column("channel", sa.String(length=16), nullable=False),
            sa.Column("recipient_redacted", sa.String(length=80), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("run_id", sa.String(length=80), nullable=True),
            sa.Column("failure_reason", sa.String(length=255), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_notification_attempts_app_user_id", "notification_attempts", ["app_user_id"])
        op.create_index("ix_notification_attempts_provider", "notification_attempts", ["provider"])
        op.create_index("ix_notification_attempts_channel", "notification_attempts", ["channel"])
        op.create_index("ix_notification_attempts_event_type", "notification_attempts", ["event_type"])
        op.create_index("ix_notification_attempts_status", "notification_attempts", ["status"])
        op.create_index("ix_notification_attempts_run_id", "notification_attempts", ["run_id"])
        op.create_index("ix_notification_attempts_created_at", "notification_attempts", ["created_at"])
        op.create_index("ix_notification_attempts_sent_at", "notification_attempts", ["sent_at"])
        op.create_index("ix_notification_attempts_user_created", "notification_attempts", ["app_user_id", "created_at"])


def downgrade() -> None:
    if _has_table("notification_attempts"):
        op.drop_table("notification_attempts")

    if _has_table("agent_mode_settings"):
        for index_name in ("ix_agent_mode_settings_default_watchlist_id",):
            try:
                op.drop_index(index_name, table_name="agent_mode_settings")
            except Exception:  # noqa: BLE001 - support partially-applied local migrations.
                pass
        for column_name in (
            "sms_notifications_enabled",
            "email_notifications_enabled",
            "sms_consent_confirmed",
            "notification_phone_number",
            "notification_preference",
            "require_confirmation_for_restricted",
            "allow_new_trade_when_symbol_already_open",
            "allow_scale_ins",
            "min_cash_reserve",
            "max_exposure_per_symbol",
            "max_open_agent_positions",
            "max_new_trades_per_day",
            "max_new_trades_per_run",
            "max_percent_of_paper_account_per_trade",
            "max_dollars_per_trade",
            "default_watchlist_id",
        ):
            if _has_column("agent_mode_settings", column_name):
                op.drop_column("agent_mode_settings", column_name)

    if _has_table("watchlists"):
        if _has_column("watchlists", "updated_at"):
            if _has_index("watchlists", "ix_watchlists_updated_at"):
                op.drop_index("ix_watchlists_updated_at", table_name="watchlists")
            op.drop_column("watchlists", "updated_at")
        if _has_column("watchlists", "is_default"):
            if _has_index("watchlists", "ix_watchlists_is_default"):
                op.drop_index("ix_watchlists_is_default", table_name="watchlists")
            op.drop_column("watchlists", "is_default")
        if _has_column("watchlists", "description"):
            op.drop_column("watchlists", "description")
