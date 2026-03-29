from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List

from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import settings
from src.database import Base
from src.meta_db import build_meta_db_trading_metadata, get_meta_db_trading_schema, get_meta_db_url

SYNC_TABLE_NAMES = (
    "trading_calendar",
    "stock_info",
    "trading_signals",
    "order_records",
    "strategy_regime_state",
    "strategy_signal_history",
)


@dataclass
class TradingMetaSyncResult:
    schema: str
    source_db_url: str
    target_db_url: str
    table_row_counts: Dict[str, int]

    @property
    def total_rows(self) -> int:
        return sum(self.table_row_counts.values())


def _build_source_metadata() -> MetaData:
    metadata = MetaData()
    for table_name in SYNC_TABLE_NAMES:
        Base.metadata.tables[table_name].to_metadata(metadata)
    return metadata


def _read_source_rows() -> Dict[str, List[dict]]:
    source_engine = create_engine(settings.db_url)
    source_metadata = _build_source_metadata()

    try:
        with source_engine.connect() as connection:
            rows_by_table: Dict[str, List[dict]] = {}
            for table_name in SYNC_TABLE_NAMES:
                table = source_metadata.tables[table_name]
                rows = connection.execute(select(table)).mappings().all()
                rows_by_table[table_name] = [dict(row) for row in rows]
            return rows_by_table
    finally:
        source_engine.dispose()


async def _sync_rows_to_meta_db(rows_by_table: Dict[str, List[dict]]) -> TradingMetaSyncResult:
    schema = get_meta_db_trading_schema()
    target_metadata = build_meta_db_trading_metadata(schema=schema)
    target_engine = create_async_engine(get_meta_db_url())

    try:
        async with target_engine.begin() as connection:
            qualified_tables = ", ".join(
                f'"{schema}"."{table_name}"' for table_name in SYNC_TABLE_NAMES
            )
            await connection.execute(text(f"TRUNCATE TABLE {qualified_tables} RESTART IDENTITY"))

            for table_name in SYNC_TABLE_NAMES:
                table: Table = target_metadata.tables[f"{schema}.{table_name}"]
                rows = rows_by_table[table_name]
                if rows:
                    await connection.execute(table.insert(), rows)

        return TradingMetaSyncResult(
            schema=schema,
            source_db_url=settings.db_url,
            target_db_url=get_meta_db_url(),
            table_row_counts={
                table_name: len(rows_by_table[table_name]) for table_name in SYNC_TABLE_NAMES
            },
        )
    finally:
        await target_engine.dispose()


def sync_sqlite_to_meta_db() -> TradingMetaSyncResult:
    rows_by_table = _read_source_rows()
    return asyncio.run(_sync_rows_to_meta_db(rows_by_table))
