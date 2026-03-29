"""create meta db trading tables

Revision ID: 20260329_180000
Revises:
Create Date: 2026-03-29 18:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from src.meta_db import build_meta_db_trading_metadata, get_meta_db_trading_schema

# revision identifiers, used by Alembic.
revision = "20260329_180000"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    schema = get_meta_db_trading_schema()
    op.execute(sa.schema.CreateSchema(schema, if_not_exists=True))

    metadata = build_meta_db_trading_metadata(schema=schema)
    metadata.create_all(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    schema = get_meta_db_trading_schema()
    metadata = build_meta_db_trading_metadata(schema=schema)
    metadata.drop_all(bind=bind, checkfirst=False)
