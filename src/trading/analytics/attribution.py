# src/trading/attribution.py
"""
AttributionService: routes QMT trade callbacks to trade_executions rows.

Attribution priority:
  1. Exact match by broker_order_id → order_records.order_id
  2. Match by submit_request_id → order_records.submit_request_id
  3. Return None → caller must create a synthetic order record
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.infrastructure.db import OrderRecord, TradeExecution
from src.infrastructure.logger_config import logger
from src.infrastructure.common.uid import new_ulid


def build_dedupe_key(
    broker_trade_id: Optional[str],
    broker_order_id: Optional[str],
    filled_volume: int,
    filled_price: float,
) -> str:
    """
    Build a stable deduplication key for a trade execution.
    Prefer broker_trade_id; fall back to broker_order_id + volume + price hash.
    """
    if broker_trade_id:
        return f"tid:{broker_trade_id}"
    raw = f"{broker_order_id}:{filled_volume}:{filled_price:.4f}"
    digest = hashlib.sha1(raw.encode()).hexdigest()[:12]
    return f"oid:{broker_order_id}:{digest}"


class AttributionService:
    """
    Writes TradeExecution rows and resolves order_uid attribution.
    Must be called within an active SQLAlchemy session.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve_order_uid(
        self,
        broker_order_id: Optional[str],
        submit_request_id: Optional[str],
    ) -> Optional[str]:
        """
        Return the order_uid of the matching OrderRecord, or None if no match.
        """
        # Priority 1: match by broker_order_id (stored as order_id in order_records)
        if broker_order_id:
            record = (
                self._session.query(OrderRecord)
                .filter(OrderRecord.order_id == broker_order_id)
                .first()
            )
            if record is not None:
                return record.order_uid

        # Priority 2: match by submit_request_id
        if submit_request_id:
            record = (
                self._session.query(OrderRecord)
                .filter(OrderRecord.submit_request_id == submit_request_id)
                .first()
            )
            if record is not None:
                return record.order_uid

        return None

    def record_execution(
        self,
        *,
        broker_trade_id: Optional[str],
        broker_order_id: Optional[str],
        submit_request_id: Optional[str],
        stock_code: str,
        direction: str,
        filled_volume: int,
        filled_price: float,
        filled_amount: float,
        filled_time: datetime,
        commission: Optional[float] = None,
        transfer_fee: Optional[float] = None,
        stamp_duty: Optional[float] = None,
        total_fee: Optional[float] = None,
        execution_source: str = "qmt_trade_callback",
    ) -> Optional[TradeExecution]:
        """
        Insert a TradeExecution row. Returns None if the dedupe_key already exists.
        """
        dedupe_key = build_dedupe_key(broker_trade_id, broker_order_id, filled_volume, filled_price)

        existing = (
            self._session.query(TradeExecution)
            .filter(TradeExecution.dedupe_key == dedupe_key)
            .first()
        )
        if existing is not None:
            logger.debug(
                "AttributionService: skipped duplicate trade execution dedupe_key={}",
                dedupe_key,
            )
            return None

        order_uid = self.resolve_order_uid(broker_order_id, submit_request_id)

        if order_uid is None:
            logger.warning(
                "AttributionService: no matching order for broker_order_id={}, creating unattributed execution",
                broker_order_id,
            )

        execution = TradeExecution(
            execution_uid=new_ulid(),
            order_uid=order_uid,
            broker_trade_id=broker_trade_id,
            broker_order_id=broker_order_id,
            stock_code=stock_code,
            direction=direction,
            filled_volume=filled_volume,
            filled_price=filled_price,
            filled_amount=filled_amount,
            filled_time=filled_time,
            commission=commission,
            transfer_fee=transfer_fee,
            stamp_duty=stamp_duty,
            total_fee=total_fee,
            execution_source=execution_source,
            dedupe_key=dedupe_key,
        )
        self._session.add(execution)
        return execution
