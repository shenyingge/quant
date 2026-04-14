"""create_trading_accounts

Revision ID: 20260414_120000_a1b2c3d4
Revises: 20260411_120000_9d7e8c31
Create Date: 2026-04-14 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from src.infrastructure.db.meta_db import get_meta_db_trading_schema

# revision identifiers, used by Alembic.
revision = "20260414_120000_a1b2c3d4"
down_revision = "20260411_120000_9d7e8c31"
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


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    if _column_exists(bind, SCHEMA, table_name, column.name):
        return
    op.add_column(table_name, column, schema=SCHEMA)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, SCHEMA, "trading_accounts"):
        op.create_table(
            "trading_accounts",
            sa.Column("account_id", sa.String(50), nullable=False),
            sa.Column("account_type", sa.String(20), nullable=False, server_default="paper"),
            sa.Column("initial_capital", sa.Float(), nullable=False),
            sa.Column("commission_rate", sa.Float(), nullable=False),
            sa.Column("transfer_fee_rate", sa.Float(), nullable=False, server_default="0.00001"),
            sa.Column("stamp_duty_rate", sa.Float(), nullable=False, server_default="0.001"),
            sa.Column("min_commission", sa.Float(), nullable=False, server_default="5.0"),
            sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("description", sa.String(200), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("account_id"),
            schema=SCHEMA,
        )
    else:
        # 表已存在时补齐新增的费率字段（兼容存量环境）
        for col in [
            sa.Column("transfer_fee_rate", sa.Float(), nullable=False, server_default="0.00001"),
            sa.Column("stamp_duty_rate", sa.Float(), nullable=False, server_default="0.001"),
            sa.Column("min_commission", sa.Float(), nullable=False, server_default="5.0"),
        ]:
            _add_column_if_missing("trading_accounts", col)


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, SCHEMA, "trading_accounts"):
        op.drop_table("trading_accounts", schema=SCHEMA)
