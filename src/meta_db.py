from __future__ import annotations

from typing import Iterable

from sqlalchemy import MetaData
from sqlalchemy.engine import URL

from src.config import settings

TRADING_META_TABLE_NAMES = (
    "trading_signals",
    "order_records",
    "trading_calendar",
    "stock_info",
    "strategy_regime_state",
    "strategy_signal_history",
    "account_positions",
    "strategy_positions",
    "strategy_event_outbox",
)


def get_meta_db_trading_schema() -> str:
    schema = (settings.meta_db_trading_schema or "").strip()
    return schema or "trading"


def validate_meta_db_config(required_keys: Iterable[str] | None = None) -> None:
    fields = {
        "META_DB_HOST": settings.meta_db_host,
        "META_DB_NAME": settings.meta_db_name,
        "META_DB_USER": settings.meta_db_user,
        "META_DB_PASSWORD": settings.meta_db_password,
    }

    missing = [
        key
        for key, value in fields.items()
        if (required_keys is None or key in required_keys) and not value
    ]
    if missing:
        raise RuntimeError(f"Missing Meta DB config: {', '.join(missing)}")


def get_meta_db_details() -> dict[str, object]:
    return {
        "host": settings.meta_db_host,
        "port": settings.meta_db_port,
        "database": settings.meta_db_name,
        "schema": get_meta_db_trading_schema(),
    }


def _resolve_meta_db_sync_drivername() -> str:
    configured = (settings.meta_db_sync_type or "").strip()
    if configured:
        return configured

    async_driver = (settings.meta_db_type or "").strip() or "postgresql+asyncpg"
    if async_driver.endswith("+asyncpg"):
        return async_driver[: -len("+asyncpg")] + "+psycopg"
    return async_driver


def get_meta_db_url(*, hide_password: bool = False) -> str:
    validate_meta_db_config()
    return URL.create(
        drivername=settings.meta_db_type,
        username=settings.meta_db_user,
        password=settings.meta_db_password,
        host=settings.meta_db_host,
        port=settings.meta_db_port,
        database=settings.meta_db_name,
    ).render_as_string(hide_password=hide_password)


def get_meta_db_sync_url(*, hide_password: bool = False) -> str:
    validate_meta_db_config()
    return URL.create(
        drivername=_resolve_meta_db_sync_drivername(),
        username=settings.meta_db_user,
        password=settings.meta_db_password,
        host=settings.meta_db_host,
        port=settings.meta_db_port,
        database=settings.meta_db_name,
    ).render_as_string(hide_password=hide_password)


def build_meta_db_trading_metadata(schema: str | None = None) -> MetaData:
    from src.database import Base

    target_schema = schema or get_meta_db_trading_schema()
    metadata = MetaData()
    for table_name in TRADING_META_TABLE_NAMES:
        table = Base.metadata.tables.get(table_name) or Base.metadata.tables.get(
            f"{target_schema}.{table_name}"
        )
        if table is None:
            raise KeyError(f"Table metadata not found for {table_name}")
        table.to_metadata(metadata, schema=target_schema)
    return metadata
