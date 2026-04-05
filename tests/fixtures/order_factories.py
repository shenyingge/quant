# tests/fixtures/order_factories.py
"""
Factory helpers for creating test ORM instances without hitting the DB.
"""
from datetime import datetime

from src.infrastructure.db import OrderRecord


def make_order_record(
    *,
    signal_id: str = "SIG001",
    order_id: str = "ORD001",
    stock_code: str = "000001.SZ",
    direction: str = "BUY",
    volume: int = 100,
    price: float = 10.0,
    order_status: str = "PENDING",
    filled_volume: int = 0,
    filled_price: float | None = None,
    error_message: str | None = None,
) -> OrderRecord:
    return OrderRecord(
        signal_id=signal_id,
        order_id=order_id,
        stock_code=stock_code,
        direction=direction,
        volume=volume,
        price=price,
        order_status=order_status,
        order_time=datetime(2026, 4, 4, 9, 30, 0),
        filled_volume=filled_volume,
        filled_price=filled_price,
        error_message=error_message,
    )
