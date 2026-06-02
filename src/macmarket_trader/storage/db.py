"""Database engine/session factory."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from macmarket_trader.config import settings
from macmarket_trader.domain.models import Base


def build_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured database URL."""
    target = database_url or settings.database_url
    connect_args = {"check_same_thread": False} if target.startswith("sqlite") else {}
    return create_engine(target, future=True, pool_pre_ping=True, connect_args=connect_args)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a SQLAlchemy session factory for dependency injection in tests."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


engine = build_engine()
SessionLocal = build_session_factory(engine)


def init_db(target_engine: Engine | None = None) -> None:
    """Initialize schema for local runs/tests."""
    Base.metadata.create_all(bind=target_engine or engine)


def apply_schema_updates(target_engine: Engine | None = None) -> list[str]:
    """Add any columns that exist in the ORM models but are missing from the DB.

    Safe to call on both fresh and existing databases — it is a no-op when the
    schema is already current.  Returns a list of '<table>.<column>' strings
    for every column that was added.
    """
    from sqlalchemy import inspect, text  # local to avoid circular import at module level

    def _has_column(conn, table_name: str, column_name: str) -> bool:
        columns = inspect(conn).get_columns(table_name)
        return any(column["name"] == column_name for column in columns)

    def _backfill_watchlist_update_columns(conn) -> None:
        if _has_column(conn, "watchlists", "is_default"):
            conn.execute(text("UPDATE watchlists SET is_default = 0 WHERE is_default IS NULL"))
        if not _has_column(conn, "watchlists", "updated_at"):
            return
        if _has_column(conn, "watchlists", "created_at"):
            conn.execute(
                text(
                    "UPDATE watchlists "
                    "SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
                    "WHERE updated_at IS NULL"
                )
            )
        else:
            conn.execute(
                text(
                    "UPDATE watchlists "
                    "SET updated_at = CURRENT_TIMESTAMP "
                    "WHERE updated_at IS NULL"
                )
            )

    e = target_engine or engine
    inspector = inspect(e)
    applied: list[str] = []

    # Ensure tables that don't exist yet are created first.
    Base.metadata.create_all(bind=e)

    with e.connect() as conn:
        for table_name, table in Base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing_col_names = {col["name"] for col in inspector.get_columns(table_name)}
            for col in table.columns:
                if col.name in existing_col_names:
                    continue
                # Compile the column type for the target dialect.
                col_type_str = col.type.compile(e.dialect)
                default_clause = ""
                if col.default is not None and col.default.is_scalar:
                    raw = col.default.arg
                    if isinstance(raw, str):
                        default_clause = f" DEFAULT '{raw}'"
                    elif isinstance(raw, bool):
                        default_clause = f" DEFAULT {int(raw)}"
                    elif isinstance(raw, (int, float)):
                        default_clause = f" DEFAULT {raw}"
                sqlite_requires_nullable_add = (
                    e.dialect.name == "sqlite"
                    and not col.nullable
                    and not default_clause
                )
                null_clause = "NULL" if col.nullable or sqlite_requires_nullable_add else "NOT NULL"
                ddl = (
                    f"ALTER TABLE {table_name} ADD COLUMN "
                    f"{col.name} {col_type_str} {null_clause}{default_clause}"
                )
                conn.execute(text(ddl))
                applied.append(f"{table_name}.{col.name}")
        if inspector.has_table("watchlists"):
            _backfill_watchlist_update_columns(conn)
        conn.commit()

    return applied
