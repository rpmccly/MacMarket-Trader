"""SQLAlchemy models for persistence and Alembic-ready metadata."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from macmarket_trader.domain.time import utc_now


class Base(DeclarativeBase):
    """Base SQLAlchemy declarative class."""


class RawIngestEventModel(Base):
    __tablename__ = "raw_ingest_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class NormalizedEventModel(Base):
    __tablename__ = "normalized_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_ingest_event_id: Mapped[int | None] = mapped_column(ForeignKey("raw_ingest_events.id"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class EventEntityModel(Base):
    __tablename__ = "event_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    normalized_event_id: Mapped[int] = mapped_column(ForeignKey("normalized_events.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_value: Mapped[str] = mapped_column(String(128), index=True)


class DailyBarModel(Base):
    __tablename__ = "daily_bars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    bar_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)


class MacroCalendarEventModel(Base):
    __tablename__ = "macro_calendar_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_name: Mapped[str] = mapped_column(String(128), index=True)
    country: Mapped[str] = mapped_column(String(32), default="US")
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)


class ProviderCursorModel(Base):
    __tablename__ = "provider_cursors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), unique=True)
    cursor: Mapped[str] = mapped_column(String(256))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProviderHealthModel(Base):
    __tablename__ = "provider_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    details: Mapped[str] = mapped_column(Text, default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class ProviderOAuthTokenModel(Base):
    __tablename__ = "provider_oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    app_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"), nullable=True, index=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="connected", index=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True)


class ProviderOAuthStateModel(Base):
    __tablename__ = "provider_oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    state: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    return_path: Mapped[str] = mapped_column(String(255), default="/admin/data-parity")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class ProviderParitySnapshotModel(Base):
    __tablename__ = "provider_parity_snapshots"
    __table_args__ = (
        Index("ix_provider_parity_snapshots_user_created", "app_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    request_json: Mapped[dict[str, object]] = mapped_column(JSON)
    response_json: Mapped[dict[str, object]] = mapped_column(JSON)
    provider_current: Mapped[str] = mapped_column(String(64), index=True)
    provider_candidate: Mapped[str] = mapped_column(String(64), default="schwab", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class RecommendationModel(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    app_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    # Pass 4 — Display-friendly recommendation label, e.g.
    # "AAPL-EVCONT-20260429-0830". Auto-generated from symbol + strategy +
    # created_at on insert. Never used as FK; canonical recommendation_id
    # (rec_<hex>) remains the unique identifier across all relations.
    display_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class RecommendationEvidenceModel(Base):
    __tablename__ = "recommendation_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    app_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"), nullable=True, index=True)
    recommendation_id: Mapped[str] = mapped_column(String(64), index=True)
    replay_run_id: Mapped[int | None] = mapped_column(ForeignKey("replay_runs.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    side: Mapped[str] = mapped_column(String(8))
    shares: Mapped[int] = mapped_column(Integer)
    limit_price: Mapped[float] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class FillModel(Base):
    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    fill_price: Mapped[float] = mapped_column(Float)
    filled_shares: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class PortfolioSnapshotModel(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_context: Mapped[str] = mapped_column(String(64), index=True)
    equity: Mapped[float] = mapped_column(Float)
    current_heat: Mapped[float] = mapped_column(Float)
    open_positions_notional: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class ReplayRunModel(Base):
    __tablename__ = "replay_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"), nullable=True, index=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_recommendation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_market_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_market_data_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_fallback_mode: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    recommendation_count: Mapped[int] = mapped_column(Integer)
    approved_count: Mapped[int] = mapped_column(Integer)
    fill_count: Mapped[int] = mapped_column(Integer)
    ending_heat: Mapped[float] = mapped_column(Float)
    ending_open_notional: Mapped[float] = mapped_column(Float)
    has_stageable_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    stageable_recommendation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stageable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class ReplayStepModel(Base):
    __tablename__ = "replay_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    replay_run_id: Mapped[int] = mapped_column(ForeignKey("replay_runs.id"), index=True)
    step_index: Mapped[int] = mapped_column(Integer)
    recommendation_id: Mapped[str] = mapped_column(String(64), index=True)
    approved: Mapped[bool] = mapped_column(Boolean)
    pre_step_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    post_step_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class AppUserModel(Base):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_auth_user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    approval_status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    app_role: Mapped[str] = mapped_column(String(24), default="user", index=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Pass 4 — Per-user risk-dollars override. NULL means fall back to
    # settings.risk_dollars_per_trade (env RISK_DOLLARS_PER_TRADE).
    risk_dollars_per_trade: Mapped[float | None] = mapped_column(Float, nullable=True)
    paper_max_order_notional: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Phase 7 — Per-user commission overrides. NULL means fall back to env
    # defaults in settings.commission_per_trade / commission_per_contract.
    commission_per_trade: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission_per_contract: Mapped[float | None] = mapped_column(Float, nullable=True)


class UserApprovalRequestModel(Base):
    __tablename__ = "user_approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailDeliveryLogModel(Base):
    __tablename__ = "email_delivery_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"), nullable=True)
    template_name: Mapped[str] = mapped_column(String(64), index=True)
    destination: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class AppInviteModel(Base):
    __tablename__ = "app_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    invite_token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="sent", index=True)
    invited_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WatchlistModel(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class UserSymbolUniverseModel(Base):
    __tablename__ = "user_symbol_universe"
    __table_args__ = (
        UniqueConstraint(
            "app_user_id",
            "normalized_symbol",
            name="uq_user_symbol_universe_user_symbol",
        ),
        Index("ix_user_symbol_universe_user_active", "app_user_id", "active"),
        Index("ix_user_symbol_universe_user_asset_type", "app_user_id", "asset_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    normalized_symbol: Mapped[str] = mapped_column(String(32), index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    asset_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    exchange: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", index=True
    )
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )


class WatchlistSymbolModel(Base):
    __tablename__ = "watchlist_symbols"
    __table_args__ = (
        UniqueConstraint(
            "watchlist_id",
            "normalized_symbol",
            name="uq_watchlist_symbols_watchlist_symbol",
        ),
        Index(
            "ix_watchlist_symbols_watchlist_active_sort",
            "watchlist_id",
            "active",
            "sort_order",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"), index=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    user_symbol_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_symbol_universe.id"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    normalized_symbol: Mapped[str] = mapped_column(String(32), index=True)
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", index=True
    )
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True
    )


class StrategyReportScheduleModel(Base):
    __tablename__ = "strategy_report_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    frequency: Mapped[str] = mapped_column(String(24), default="weekdays", index=True)
    run_time: Mapped[str] = mapped_column(String(16), default="08:30")
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    email_target: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    latest_status: Mapped[str] = mapped_column(String(24), default="idle")
    latest_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    latest_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class StrategyReportRunModel(Base):
    __tablename__ = "strategy_report_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("strategy_report_schedules.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    delivered_to: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class MomentumHeatmapProfileModel(Base):
    __tablename__ = "momentum_heatmap_profiles"
    __table_args__ = (
        UniqueConstraint(
            "app_user_id",
            "profile_uid",
            name="uq_momentum_heatmap_profiles_user_uid",
        ),
        Index("ix_momentum_heatmap_profiles_user_updated", "app_user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_uid: Mapped[str] = mapped_column(String(64), index=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="Default Momentum Heatmap", index=True)
    categories: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    color_ranges: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    view_settings: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    report_preferences: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True)


class MomentumHeatmapSnapshotModel(Base):
    __tablename__ = "momentum_heatmap_snapshots"
    __table_args__ = (
        Index("ix_momentum_heatmap_snapshots_profile_generated", "profile_id", "generated_at"),
        Index("ix_momentum_heatmap_snapshots_user_generated", "app_user_id", "generated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("momentum_heatmap_profiles.id"), index=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="partial", index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    report_label: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    requested_categories: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    requested_rows: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    category_summaries: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    unsupported_summary: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    previous_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class MomentumHeatmapSchedulePreferenceModel(Base):
    __tablename__ = "momentum_heatmap_schedule_preferences"
    __table_args__ = (
        UniqueConstraint(
            "app_user_id",
            "profile_id",
            name="uq_momentum_heatmap_schedule_user_profile",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("momentum_heatmap_profiles.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Indiana/Indianapolis")
    run_time: Mapped[str] = mapped_column(String(16), default="07:00")
    days_of_week: Mapped[list[str]] = mapped_column(JSON, default=list)
    report_mode: Mapped[str] = mapped_column(String(32), default="latest_snapshot")
    recipients: Mapped[list[str]] = mapped_column(JSON, default=list)
    include_csv_attachment: Mapped[bool] = mapped_column(Boolean, default=True)
    include_full_table: Mapped[bool] = mapped_column(Boolean, default=True)
    latest_status: Mapped[str] = mapped_column(String(32), default="not_configured")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True)


class HacoHeatmapProfileModel(Base):
    __tablename__ = "haco_heatmap_profiles"
    __table_args__ = (
        UniqueConstraint(
            "app_user_id",
            "profile_uid",
            name="uq_haco_heatmap_profiles_user_uid",
        ),
        Index("ix_haco_heatmap_profiles_user_updated", "app_user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_uid: Mapped[str] = mapped_column(String(64), index=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="Morning Macro", index=True)
    categories: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    view_settings: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    report_preferences: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True)


class HacoHeatmapSnapshotModel(Base):
    __tablename__ = "haco_heatmap_snapshots"
    __table_args__ = (
        Index("ix_haco_heatmap_snapshots_profile_generated", "profile_id", "generated_at"),
        Index("ix_haco_heatmap_snapshots_user_generated", "app_user_id", "generated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("haco_heatmap_profiles.id"), index=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="partial", index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    report_label: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    requested_categories: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    requested_rows: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    category_summaries: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    unsupported_summary: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    previous_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class PaperPositionModel(Base):
    __tablename__ = "paper_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[float] = mapped_column(Float)
    average_price: Mapped[float] = mapped_column(Float)
    open_notional: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    opened_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    remaining_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    replay_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)


class PaperTradeModel(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float)
    gross_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    position_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    hold_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    replay_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    close_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AgentModeSettingsModel(Base):
    __tablename__ = "agent_mode_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    kill_switch_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    daily_run_time: Mapped[str] = mapped_column(String(8), default="15:45")
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    universe_source: Mapped[str] = mapped_column(String(32), default="manual", index=True)
    manual_symbols: Mapped[list[str]] = mapped_column(JSON, default=list)
    watchlist_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    max_positions: Mapped[int] = mapped_column(Integer, default=5)
    scan_depth: Mapped[int] = mapped_column(Integer, default=12)
    allow_opens: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_closes: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_scale_resize: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True)


class AgentModeRunModel(Base):
    __tablename__ = "agent_mode_runs"
    __table_args__ = (
        Index("ix_agent_mode_runs_user_created", "app_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    execution_mode: Mapped[str] = mapped_column(String(16), default="paper", index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    intent_count: Mapped[int] = mapped_column(Integer, default=0)
    executed_order_count: Mapped[int] = mapped_column(Integer, default=0)
    request_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    response_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class PaperOptionOrderModel(Base):
    __tablename__ = "paper_option_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    underlying_symbol: Mapped[str] = mapped_column(String(16), index=True)
    structure_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="created", index=True)
    expiration: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    net_debit: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_credit: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    breakevens: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    execution_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class PaperOptionOrderLegModel(Base):
    __tablename__ = "paper_option_order_legs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    option_order_id: Mapped[int] = mapped_column(ForeignKey("paper_option_orders.id"), index=True)
    action: Mapped[str] = mapped_column(String(8))
    right: Mapped[str] = mapped_column(String(8))
    strike: Mapped[float] = mapped_column(Float)
    expiration: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    multiplier: Mapped[int] = mapped_column(Integer, default=100)
    premium: Mapped[float] = mapped_column(Float)
    leg_status: Mapped[str] = mapped_column(String(24), default="created", index=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    option_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_strike: Mapped[float | None] = mapped_column(Float, nullable=True)
    contract_selection: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PaperOptionPositionModel(Base):
    __tablename__ = "paper_option_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    underlying_symbol: Mapped[str] = mapped_column(String(16), index=True)
    structure_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    expiration: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    opening_net_debit: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_net_credit: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    breakevens: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    source_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_option_orders.id"), nullable=True, index=True
    )


class PaperOptionPositionLegModel(Base):
    __tablename__ = "paper_option_position_legs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("paper_option_positions.id"), index=True)
    action: Mapped[str] = mapped_column(String(8))
    right: Mapped[str] = mapped_column(String(8))
    strike: Mapped[float] = mapped_column(Float)
    expiration: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    multiplier: Mapped[int] = mapped_column(Integer, default=100)
    entry_premium: Mapped[float] = mapped_column(Float)
    exit_premium: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    option_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_strike: Mapped[float | None] = mapped_column(Float, nullable=True)
    contract_selection: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PaperOptionTradeModel(Base):
    __tablename__ = "paper_option_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), index=True)
    position_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_option_positions.id"), nullable=True, index=True
    )
    structure_type: Mapped[str] = mapped_column(String(32), index=True)
    underlying_symbol: Mapped[str] = mapped_column(String(16), index=True)
    expiration: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    gross_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_commissions: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    settlement_mode: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class PaperOptionTradeLegModel(Base):
    __tablename__ = "paper_option_trade_legs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("paper_option_trades.id"), index=True)
    action: Mapped[str] = mapped_column(String(8))
    right: Mapped[str] = mapped_column(String(8))
    strike: Mapped[float] = mapped_column(Float)
    expiration: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    multiplier: Mapped[int] = mapped_column(Integer, default=100)
    entry_premium: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_premium: Mapped[float | None] = mapped_column(Float, nullable=True)
    leg_gross_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    leg_commission: Mapped[float | None] = mapped_column(Float, nullable=True)
    leg_net_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    option_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_strike: Mapped[float | None] = mapped_column(Float, nullable=True)
    contract_selection: Mapped[dict | None] = mapped_column(JSON, nullable=True)
