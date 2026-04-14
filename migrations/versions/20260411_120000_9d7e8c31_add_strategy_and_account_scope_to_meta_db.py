"""add_strategy_and_account_scope_to_meta_db

Revision ID: 20260411_120000_9d7e8c31
Revises: 20260405_120000_c751dc66
Create Date: 2026-04-11 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from src.infrastructure.db.meta_db import get_meta_db_trading_schema

# revision identifiers, used by Alembic.
revision = "20260411_120000_9d7e8c31"
down_revision = "20260405_120000_c751dc66"
branch_labels = None
depends_on = None

SCHEMA = get_meta_db_trading_schema()
EMPTY_STRING_DEFAULT = sa.text("''")


def _table_exists(bind, schema: str, table_name: str) -> bool:
    return inspect(bind).has_table(table_name, schema=schema)


def _column_exists(bind, schema: str, table_name: str, column_name: str) -> bool:
    insp = inspect(bind)
    if not insp.has_table(table_name, schema=schema):
        return False
    cols = [c["name"] for c in insp.get_columns(table_name, schema=schema)]
    return column_name in cols


def _index_exists(bind, schema: str, table_name: str, index_name: str) -> bool:
    insp = inspect(bind)
    if not insp.has_table(table_name, schema=schema):
        return False
    indexes = insp.get_indexes(table_name, schema=schema)
    return any(ix["name"] == index_name for ix in indexes)


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    if _column_exists(bind, SCHEMA, table_name, column.name):
        return
    op.add_column(table_name, column, schema=SCHEMA)


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    bind = op.get_bind()
    if _index_exists(bind, SCHEMA, table_name, index_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique, schema=SCHEMA)


def upgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, SCHEMA, "trading_signals"):
        _add_column_if_missing(
            "trading_signals",
            sa.Column(
                "strategy_id",
                sa.String(length=100),
                nullable=False,
                server_default=EMPTY_STRING_DEFAULT,
            ),
        )
        _create_index_if_missing(
            "trading_signals",
            "ix_trading_signals_strategy_id",
            ["strategy_id"],
        )

    if _table_exists(bind, SCHEMA, "order_records"):
        _add_column_if_missing(
            "order_records",
            sa.Column(
                "strategy_id",
                sa.String(length=100),
                nullable=False,
                server_default=EMPTY_STRING_DEFAULT,
            ),
        )
        _add_column_if_missing(
            "order_records",
            sa.Column("account_id", sa.String(length=50), nullable=True),
        )
        _create_index_if_missing("order_records", "ix_order_records_strategy_id", ["strategy_id"])
        _create_index_if_missing("order_records", "ix_order_records_account_id", ["account_id"])

    if _table_exists(bind, SCHEMA, "trade_executions"):
        _add_column_if_missing(
            "trade_executions",
            sa.Column(
                "strategy_id",
                sa.String(length=100),
                nullable=False,
                server_default=EMPTY_STRING_DEFAULT,
            ),
        )
        _add_column_if_missing(
            "trade_executions",
            sa.Column("account_id", sa.String(length=50), nullable=True),
        )
        _create_index_if_missing(
            "trade_executions",
            "ix_trade_executions_strategy_id",
            ["strategy_id"],
        )
        _create_index_if_missing(
            "trade_executions",
            "ix_trade_executions_account_id",
            ["account_id"],
        )

    if _table_exists(bind, SCHEMA, "order_cancellations"):
        _add_column_if_missing(
            "order_cancellations",
            sa.Column(
                "strategy_id",
                sa.String(length=100),
                nullable=False,
                server_default=EMPTY_STRING_DEFAULT,
            ),
        )
        _add_column_if_missing(
            "order_cancellations",
            sa.Column("account_id", sa.String(length=50), nullable=True),
        )
        _create_index_if_missing(
            "order_cancellations",
            "ix_order_cancellations_strategy_id",
            ["strategy_id"],
        )
        _create_index_if_missing(
            "order_cancellations",
            "ix_order_cancellations_account_id",
            ["account_id"],
        )

    if _table_exists(bind, SCHEMA, "account_positions"):
        _add_column_if_missing(
            "account_positions",
            sa.Column(
                "strategy_id",
                sa.String(length=100),
                nullable=False,
                server_default=EMPTY_STRING_DEFAULT,
            ),
        )
        _create_index_if_missing(
            "account_positions",
            "ix_account_positions_strategy_id",
            ["strategy_id"],
        )
        if _index_exists(bind, SCHEMA, "account_positions", "idx_account_position_account_stock"):
            op.drop_index(
                "idx_account_position_account_stock",
                table_name="account_positions",
                schema=SCHEMA,
            )
        _create_index_if_missing(
            "account_positions",
            "idx_account_position_strategy_account_stock",
            ["strategy_id", "account_id", "stock_code"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, SCHEMA, "account_positions"):
        if _index_exists(
            bind,
            SCHEMA,
            "account_positions",
            "idx_account_position_strategy_account_stock",
        ):
            op.drop_index(
                "idx_account_position_strategy_account_stock",
                table_name="account_positions",
                schema=SCHEMA,
            )
        _create_index_if_missing(
            "account_positions",
            "idx_account_position_account_stock",
            ["account_id", "stock_code"],
            unique=True,
        )
        if _index_exists(bind, SCHEMA, "account_positions", "ix_account_positions_strategy_id"):
            op.drop_index(
                "ix_account_positions_strategy_id",
                table_name="account_positions",
                schema=SCHEMA,
            )
        if _column_exists(bind, SCHEMA, "account_positions", "strategy_id"):
            op.drop_column("account_positions", "strategy_id", schema=SCHEMA)

    for table_name, strategy_index, account_index in (
        ("order_cancellations", "ix_order_cancellations_strategy_id", "ix_order_cancellations_account_id"),
        ("trade_executions", "ix_trade_executions_strategy_id", "ix_trade_executions_account_id"),
        ("order_records", "ix_order_records_strategy_id", "ix_order_records_account_id"),
    ):
        if not _table_exists(bind, SCHEMA, table_name):
            continue
        if _index_exists(bind, SCHEMA, table_name, account_index):
            op.drop_index(account_index, table_name=table_name, schema=SCHEMA)
        if _index_exists(bind, SCHEMA, table_name, strategy_index):
            op.drop_index(strategy_index, table_name=table_name, schema=SCHEMA)
        if _column_exists(bind, SCHEMA, table_name, "account_id"):
            op.drop_column(table_name, "account_id", schema=SCHEMA)
        if _column_exists(bind, SCHEMA, table_name, "strategy_id"):
            op.drop_column(table_name, "strategy_id", schema=SCHEMA)

    if _table_exists(bind, SCHEMA, "trading_signals"):
        if _index_exists(bind, SCHEMA, "trading_signals", "ix_trading_signals_strategy_id"):
            op.drop_index(
                "ix_trading_signals_strategy_id",
                table_name="trading_signals",
                schema=SCHEMA,
            )
        if _column_exists(bind, SCHEMA, "trading_signals", "strategy_id"):
            op.drop_column("trading_signals", "strategy_id", schema=SCHEMA)
