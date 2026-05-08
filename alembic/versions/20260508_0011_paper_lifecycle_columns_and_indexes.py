"""Backfill paper lifecycle columns and add missing lineage indexes.

Revision ID: 20260508_0011
Revises: 20260503_0010
Create Date: 2026-05-08

Background
----------
The original ``20260415_0005_replay_stageable_and_paper_portfolio_scaffold``
migration created ``paper_positions`` and ``paper_trades`` from an earlier
ORM shape.  Several columns that ``src/macmarket_trader/domain/models.py``
declares today were never written into a follow-up Alembic revision and
have been patched into the live schema at startup by
``apply_schema_updates()`` in ``src/macmarket_trader/storage/db.py``
instead.  The corresponding ``index=True`` indexes that the ORM declares
were also never produced by Alembic on databases that started from
migration 0005, because ``apply_schema_updates()`` only adds missing
columns — it does not add indexes on existing tables.

Per-column status going into this revision
------------------------------------------
* ``paper_positions.opened_qty`` — declared by the ORM, never added by
  any pre-0011 Alembic revision.  Patched in by ``apply_schema_updates()``
  at runtime.  Truly needs a backfill here.
* ``paper_positions.remaining_qty`` — same story as ``opened_qty``.
  Truly needs a backfill here.
* ``paper_trades.realized_pnl`` — *was* in fact created by 0005 (see
  ``alembic/versions/20260415_0005_replay_stageable_and_paper_portfolio_scaffold.py``
  line 52, ``sa.Column("realized_pnl", sa.Float(), nullable=False,
  server_default="0")``).  The 2026-05-07 roadmap reality audit listed
  it as missing from the migration set; that specific item was incorrect.
  We still include ``realized_pnl`` in the idempotent "if missing" list
  here so that databases bootstrapped via ``init_db()`` /
  ``Base.metadata.create_all()`` end up at the same state regardless of
  which path they took, but the column is **not** new in this revision.
* ``paper_positions.replay_run_id`` — declared by the ORM with
  ``index=True`` but the column itself was never written into Alembic.
  Patched in by ``apply_schema_updates()`` at runtime; the index
  ``ix_paper_positions_replay_run_id`` is missing on those databases
  and is created here.
* ``paper_trades.replay_run_id`` — same pattern as
  ``paper_positions.replay_run_id``.  The index
  ``ix_paper_trades_replay_run_id`` is created here.
* ``paper_trades.position_id`` — same pattern.  The index
  ``ix_paper_trades_position_id`` is created here.

What this migration does
------------------------
* Pass 1: idempotently backfill the six columns above if missing.  On
  any database where ``apply_schema_updates()`` has already patched
  them in, this pass is a no-op.
* Pass 2: idempotently add the three lineage indexes if missing.  On
  any database where ``Base.metadata.create_all()`` already produced
  the ``index=True`` indexes from the ORM, this pass is a no-op.

Downgrade behaviour (data-preserving)
-------------------------------------
This migration's downgrade is intentionally **index-only**.  None of
the data-bearing columns are dropped on downgrade because, on the
deployed alpha database, those columns may have been added by
``apply_schema_updates()`` long before this revision existed and may
already hold real paper-lifecycle data (opened/remaining quantities,
realized P&L, and lineage IDs that join paper trades back to their
recommendations and replay runs).  Dropping them on downgrade would
silently destroy that data.

The downgrade therefore only removes what this revision actually
created on the deployed schema: the three lineage indexes.  Operators
who genuinely need to remove the columns must do so via a separate,
explicit, data-aware migration — not by using ``alembic downgrade``.

Safety
------
Every step is guarded by an SQLAlchemy inspector check, so the
migration is a no-op on databases where ``apply_schema_updates()`` has
already added the columns or where ``Base.metadata.create_all()``
already produced the lineage indexes from the ORM ``index=True``
declarations.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260508_0011"
down_revision = "20260503_0010"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


# Columns this migration is responsible for, in upgrade order.
# Each entry is (table_name, column_name, sqlalchemy_column_factory).
# Factories are zero-argument callables so that each call returns a
# fresh ``sa.Column`` (Alembic mutates the column on add_column).
_BACKFILL_COLUMNS: tuple[tuple[str, str, "callable[[], sa.Column]"], ...] = (
    ("paper_positions", "opened_qty",
        lambda: sa.Column("opened_qty", sa.Float(), nullable=True)),
    ("paper_positions", "remaining_qty",
        lambda: sa.Column("remaining_qty", sa.Float(), nullable=True)),
    ("paper_positions", "replay_run_id",
        lambda: sa.Column("replay_run_id", sa.Integer(), nullable=True)),
    ("paper_trades", "realized_pnl",
        lambda: sa.Column("realized_pnl", sa.Float(), nullable=False, server_default="0")),
    ("paper_trades", "position_id",
        lambda: sa.Column("position_id", sa.Integer(), nullable=True)),
    ("paper_trades", "replay_run_id",
        lambda: sa.Column("replay_run_id", sa.Integer(), nullable=True)),
)


# Indexes this migration is responsible for.
# (index_name, table_name, column_name)
_LINEAGE_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_paper_positions_replay_run_id", "paper_positions", "replay_run_id"),
    ("ix_paper_trades_replay_run_id", "paper_trades", "replay_run_id"),
    ("ix_paper_trades_position_id", "paper_trades", "position_id"),
)


def upgrade() -> None:
    # Pass 1 — backfill any missing columns.  Each table is inspected
    # once per column to keep the conditional logic obvious; the
    # underlying ``inspect`` call is cheap enough at private-alpha scale.
    for table_name, column_name, factory in _BACKFILL_COLUMNS:
        if column_name not in _column_names(table_name):
            op.add_column(table_name, factory())

    # Pass 2 — add lineage indexes if both column and index are in the
    # expected state.  Skip silently when the column is missing for any
    # unexpected reason; this keeps the migration idempotent on
    # partially patched databases.
    for index_name, table_name, column_name in _LINEAGE_INDEXES:
        if column_name not in _column_names(table_name):
            continue
        if index_name not in _index_names(table_name):
            op.create_index(index_name, table_name, [column_name], unique=False)


def downgrade() -> None:
    # Index-only downgrade.  All data-bearing columns are intentionally
    # preserved — see the module docstring for the data-preservation
    # rationale.  ``alembic downgrade`` from 0011 to 0010 must not
    # destroy paper-lifecycle data that may pre-date this revision via
    # ``apply_schema_updates()``.
    for index_name, table_name, _ in _LINEAGE_INDEXES:
        if index_name in _index_names(table_name):
            op.drop_index(index_name, table_name=table_name)
