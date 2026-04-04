from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from sqlalchemy import inspect, or_, text

from src.config import settings
from src.database import OrderRecord, SessionLocal, TRADING_SCHEMA, engine
from src.logger_config import logger
from src.trading_costs import (
    TradingFeeSchedule,
    apply_trade_cost_fields,
    hydrate_trade_breakdown,
    infer_trade_breakdown_from_logs,
    set_trade_breakdown,
)


ORDER_RECORD_COST_COLUMNS = (
    ("trade_amount", "FLOAT"),
    ("commission", "FLOAT"),
    ("transfer_fee", "FLOAT"),
    ("stamp_duty", "FLOAT"),
    ("total_fee", "FLOAT"),
    ("transaction_cost", "FLOAT"),
    ("settlement_amount", "FLOAT"),
    ("net_cash_effect", "FLOAT"),
)

ORDER_RECORD_AUX_COLUMNS = (("trade_breakdown", "TEXT"),)


@dataclass(frozen=True)
class OrderRecordCostBackfillResult:
    inspected: int
    updated: int
    skipped: int
    failed: int
    dry_run: bool
    recalculate: bool
    batch_size: int
    limit: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_order_record_cost_columns(connection=None) -> list[str]:
    if connection is not None:
        return _ensure_order_record_cost_columns(connection)

    with engine.begin() as managed_connection:
        return _ensure_order_record_cost_columns(managed_connection)


def backfill_order_record_costs(
    *,
    batch_size: int = 500,
    limit: Optional[int] = None,
    dry_run: bool = False,
    recalculate: bool = False,
    fee_schedule: Optional[TradingFeeSchedule] = None,
) -> OrderRecordCostBackfillResult:
    fee_schedule = fee_schedule or TradingFeeSchedule.from_settings(settings)
    batch_size = max(int(batch_size), 1)
    ensure_order_record_cost_columns()

    session = SessionLocal()
    inspected = updated = skipped = failed = 0
    pending_updates = 0

    try:
        query = session.query(OrderRecord).filter(
            OrderRecord.filled_volume > 0,
            OrderRecord.filled_price > 0,
        )
        if not recalculate:
            query = query.filter(
                or_(
                    OrderRecord.trade_amount.is_(None),
                    OrderRecord.total_fee.is_(None),
                    OrderRecord.net_cash_effect.is_(None),
                    OrderRecord.transaction_cost.is_(None),
                    OrderRecord.settlement_amount.is_(None),
                    OrderRecord.trade_breakdown.is_(None),
                )
            )

        query = query.order_by(OrderRecord.id.asc())
        if limit is not None:
            query = query.limit(max(int(limit), 0))

        for order_record in query:
            inspected += 1
            try:
                _hydrate_order_record_trade_breakdown(order_record)
                before_state = _snapshot_cost_fields(order_record)
                apply_trade_cost_fields(order_record, fee_schedule=fee_schedule)
                after_state = _snapshot_cost_fields(order_record)
                if before_state == after_state:
                    skipped += 1
                    continue

                updated += 1
                pending_updates += 1
                if not dry_run and pending_updates >= batch_size:
                    session.commit()
                    pending_updates = 0
            except Exception as exc:
                failed += 1
                logger.warning(
                    "Failed to backfill trade cost for order_id={} stock_code={}: {}",
                    getattr(order_record, "order_id", None),
                    getattr(order_record, "stock_code", None),
                    exc,
                )

        if not dry_run and pending_updates > 0:
            session.commit()
        elif dry_run:
            session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    result = OrderRecordCostBackfillResult(
        inspected=inspected,
        updated=updated,
        skipped=skipped,
        failed=failed,
        dry_run=dry_run,
        recalculate=recalculate,
        batch_size=batch_size,
        limit=limit,
    )
    logger.info("Trade cost backfill finished: {}", result.to_dict())
    return result


def _qualified_order_records_table_name(connection) -> str:
    if connection.dialect.name == "sqlite":
        return "order_records"
    return f'"{TRADING_SCHEMA}"."order_records"'


def _ensure_order_record_cost_columns(connection) -> list[str]:
    schema = None if connection.dialect.name == "sqlite" else TRADING_SCHEMA
    inspector = inspect(connection)
    if not inspector.has_table("order_records", schema=schema):
        return []

    existing_columns = {
        column["name"] for column in inspector.get_columns("order_records", schema=schema)
    }
    added_columns: list[str] = []
    table_name = _qualified_order_records_table_name(connection)

    for column_name, column_type in ORDER_RECORD_COST_COLUMNS + ORDER_RECORD_AUX_COLUMNS:
        if column_name in existing_columns:
            continue
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
        added_columns.append(column_name)

    if added_columns:
        logger.info(
            "Added order_records cost column(s) in Meta DB: {}",
            ", ".join(added_columns),
        )

    return added_columns


def _snapshot_cost_fields(order_record: OrderRecord) -> tuple[Any, ...]:
    return tuple(
        getattr(order_record, field_name, None)
        for field_name, _ in ORDER_RECORD_COST_COLUMNS + ORDER_RECORD_AUX_COLUMNS
    )


def _hydrate_order_record_trade_breakdown(order_record: OrderRecord) -> None:
    breakdown = hydrate_trade_breakdown(order_record)
    if breakdown:
        return

    inferred = infer_trade_breakdown_from_logs(
        stock_code=str(getattr(order_record, "stock_code", "") or ""),
        filled_price=float(getattr(order_record, "filled_price", 0.0) or 0.0),
        filled_volume=int(getattr(order_record, "filled_volume", 0) or 0),
        target_time=getattr(order_record, "filled_time", None)
        or getattr(order_record, "order_time", None),
    )
    if inferred:
        set_trade_breakdown(order_record, inferred)
