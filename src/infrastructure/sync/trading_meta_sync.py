from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, inspect, text

from src.infrastructure.db.meta_db import get_meta_db_sync_url, get_meta_db_trading_schema

SYNC_TABLES = (
    "trading_calendar",
    "stock_info",
    "trading_signals",
    "order_records",
    "trade_executions",
    "order_cancellations",
    "account_positions",
)


@dataclass
class TradingMetaSyncResult:
    schema: str
    source_db_url: str
    target_db_url: str
    table_row_counts: dict[str, int]

    @property
    def total_rows(self) -> int:
        return sum(self.table_row_counts.values())


def _resolve_source_db_url() -> str:
    env_db_url = os.getenv("DB_URL")
    if env_db_url:
        return env_db_url
    return "sqlite:///./trading.db"


def _read_source_rows() -> dict[str, list[dict[str, Any]]]:
    source_db_url = _resolve_source_db_url()
    engine = create_engine(source_db_url)
    rows_by_table: dict[str, list[dict[str, Any]]] = {name: [] for name in SYNC_TABLES}

    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        with engine.connect() as connection:
            for table_name in SYNC_TABLES:
                if table_name not in table_names:
                    continue
                result = connection.execute(text(f'SELECT * FROM "{table_name}"'))
                rows_by_table[table_name] = [dict(row._mapping) for row in result]
    finally:
        engine.dispose()

    return rows_by_table


async def _sync_rows_to_meta_db(
    rows_by_table: dict[str, list[dict[str, Any]]],
) -> TradingMetaSyncResult:
    try:
        target_db_url = get_meta_db_sync_url(hide_password=True)
    except Exception:
        target_db_url = ""

    return TradingMetaSyncResult(
        schema=get_meta_db_trading_schema(),
        source_db_url=_resolve_source_db_url(),
        target_db_url=target_db_url,
        table_row_counts={name: len(rows) for name, rows in rows_by_table.items()},
    )


def sync_sqlite_to_meta_db() -> TradingMetaSyncResult:
    rows_by_table = _read_source_rows()
    return asyncio.run(_sync_rows_to_meta_db(rows_by_table))
