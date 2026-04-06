"""add_trade_executions_and_order_cancellations

Revision ID: 20260405_120000_c751dc66
Revises: 20260329_181000_f604a8cb
Create Date: 2026-04-05 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from src.infrastructure.db.meta_db import get_meta_db_trading_schema

# revision identifiers, used by Alembic.
revision = "20260405_120000_c751dc66"
down_revision = "20260329_181000_f604a8cb"
branch_labels = None
depends_on = None

SCHEMA = get_meta_db_trading_schema()


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


def _constraint_exists(bind, schema: str, table_name: str, constraint_name: str) -> bool:
    insp = inspect(bind)
    if not insp.has_table(table_name, schema=schema):
        return False
    ucs = insp.get_unique_constraints(table_name, schema=schema)
    return any(uc["name"] == constraint_name for uc in ucs)


def upgrade() -> None:
    bind = op.get_bind()

    # --- trade_executions table ---
    if not _table_exists(bind, SCHEMA, "trade_executions"):
        op.create_table(
            "trade_executions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("execution_uid", sa.String(50), nullable=False),
            sa.Column("order_uid", sa.String(50), nullable=True),
            sa.Column("broker_trade_id", sa.String(50), nullable=True),
            sa.Column("broker_order_id", sa.String(50), nullable=True),
            sa.Column("stock_code", sa.String(20), nullable=False),
            sa.Column("direction", sa.String(10), nullable=False),
            sa.Column("filled_volume", sa.Integer(), nullable=False),
            sa.Column("filled_price", sa.Float(), nullable=False),
            sa.Column("filled_amount", sa.Float(), nullable=False),
            sa.Column("filled_time", sa.DateTime(), nullable=False),
            sa.Column("commission", sa.Float(), nullable=True),
            sa.Column("transfer_fee", sa.Float(), nullable=True),
            sa.Column("stamp_duty", sa.Float(), nullable=True),
            sa.Column("total_fee", sa.Float(), nullable=True),
            sa.Column("execution_source", sa.String(50), nullable=True),
            sa.Column("dedupe_key", sa.String(100), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("execution_uid", name="uq_trade_executions_execution_uid"),
            sa.UniqueConstraint("dedupe_key", name="uq_trade_executions_dedupe_key"),
            sa.Index("ix_trade_executions_order_uid", "order_uid"),
            sa.Index("ix_trade_executions_broker_trade_id", "broker_trade_id"),
            sa.Index("ix_trade_executions_broker_order_id", "broker_order_id"),
            schema=SCHEMA,
        )
    else:
        for index_name, col in [
            ("ix_trade_executions_order_uid", "order_uid"),
            ("ix_trade_executions_broker_trade_id", "broker_trade_id"),
            ("ix_trade_executions_broker_order_id", "broker_order_id"),
        ]:
            if not _index_exists(bind, SCHEMA, "trade_executions", index_name):
                op.create_index(index_name, "trade_executions", [col], schema=SCHEMA)

    # --- order_cancellations table ---
    if not _table_exists(bind, SCHEMA, "order_cancellations"):
        op.create_table(
            "order_cancellations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("order_uid", sa.String(50), nullable=False),
            sa.Column("broker_order_id", sa.String(50), nullable=True),
            sa.Column("stock_code", sa.String(20), nullable=False),
            sa.Column("cancelled_volume", sa.Integer(), nullable=False),
            sa.Column("cancel_time", sa.DateTime(), nullable=False),
            sa.Column("cancel_reason", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.Index("ix_order_cancellations_order_uid", "order_uid"),
            schema=SCHEMA,
        )
    else:
        if not _index_exists(bind, SCHEMA, "order_cancellations", "ix_order_cancellations_order_uid"):
            op.create_index(
                "ix_order_cancellations_order_uid",
                "order_cancellations",
                ["order_uid"],
                schema=SCHEMA,
            )

    # --- new columns on order_records ---
    for col_name, col_def in [
        ("order_uid", sa.Column("order_uid", sa.String(50), nullable=True)),
        (
            "order_type",
            sa.Column("order_type", sa.String(50), nullable=True, server_default="LIMIT"),
        ),
        (
            "submit_request_id",
            sa.Column("submit_request_id", sa.String(50), nullable=True),
        ),
        (
            "order_source",
            sa.Column(
                "order_source", sa.String(50), nullable=True, server_default="signal_submit"
            ),
        ),
    ]:
        if not _column_exists(bind, SCHEMA, "order_records", col_name):
            op.add_column("order_records", col_def, schema=SCHEMA)

    if not _constraint_exists(bind, SCHEMA, "order_records", "uq_order_records_order_uid"):
        op.create_unique_constraint(
            "uq_order_records_order_uid",
            "order_records",
            ["order_uid"],
            schema=SCHEMA,
        )

    for index_name, col in [
        ("ix_order_records_order_uid", "order_uid"),
        ("ix_order_records_submit_request_id", "submit_request_id"),
    ]:
        if not _index_exists(bind, SCHEMA, "order_records", index_name):
            op.create_index(index_name, "order_records", [col], schema=SCHEMA)


def downgrade() -> None:
    bind = op.get_bind()

    # Reverse order_records changes
    if _index_exists(bind, SCHEMA, "order_records", "ix_order_records_submit_request_id"):
        op.drop_index(
            "ix_order_records_submit_request_id", table_name="order_records", schema=SCHEMA
        )
    if _index_exists(bind, SCHEMA, "order_records", "ix_order_records_order_uid"):
        op.drop_index(
            "ix_order_records_order_uid", table_name="order_records", schema=SCHEMA
        )
    if _constraint_exists(bind, SCHEMA, "order_records", "uq_order_records_order_uid"):
        op.drop_constraint(
            "uq_order_records_order_uid", "order_records", schema=SCHEMA, type_="unique"
        )
    for col_name in ("order_source", "submit_request_id", "order_type", "order_uid"):
        if _column_exists(bind, SCHEMA, "order_records", col_name):
            op.drop_column("order_records", col_name, schema=SCHEMA)

    # Reverse order_cancellations
    if _index_exists(bind, SCHEMA, "order_cancellations", "ix_order_cancellations_order_uid"):
        op.drop_index(
            "ix_order_cancellations_order_uid",
            table_name="order_cancellations",
            schema=SCHEMA,
        )
    if _table_exists(bind, SCHEMA, "order_cancellations"):
        op.drop_table("order_cancellations", schema=SCHEMA)

    # Reverse trade_executions
    for index_name in [
        "ix_trade_executions_broker_order_id",
        "ix_trade_executions_broker_trade_id",
        "ix_trade_executions_order_uid",
    ]:
        if _index_exists(bind, SCHEMA, "trade_executions", index_name):
            op.drop_index(index_name, table_name="trade_executions", schema=SCHEMA)
    if _table_exists(bind, SCHEMA, "trade_executions"):
        op.drop_table("trade_executions", schema=SCHEMA)
