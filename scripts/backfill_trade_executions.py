#!/usr/bin/env python
# scripts/backfill_trade_executions.py
"""
One-shot backfill: reads trade_breakdown JSON from order_records
and creates corresponding trade_executions rows.

Usage:
    uv run python scripts/backfill_trade_executions.py --dry-run
    uv run python scripts/backfill_trade_executions.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any, List, Optional

# Ensure project root on path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.db import OrderRecord, SessionLocal, TradeExecution
from src.logger_config import logger
from src.trading.attribution import build_dedupe_key
from src.uid import new_ulid


def parse_trade_breakdown(raw: Optional[str]) -> List[dict[str, Any]]:
    """Parse trade_breakdown JSON string into a list of leg dicts."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def backfill(*, dry_run: bool = False, batch_size: int = 200) -> dict[str, int]:
    session = SessionLocal()
    inspected = inserted = skipped = failed = 0

    try:
        orders = (
            session.query(OrderRecord)
            .filter(OrderRecord.trade_breakdown.isnot(None))
            .order_by(OrderRecord.id.asc())
            .all()
        )

        for order in orders:
            legs = parse_trade_breakdown(order.trade_breakdown)
            for leg in legs:
                inspected += 1
                try:
                    broker_trade_id = str(leg.get("trade_id") or "") or None
                    broker_order_id = str(order.order_id or "") or None
                    filled_volume = int(leg.get("volume") or 0)
                    filled_price = float(leg.get("price") or 0.0)

                    if filled_volume <= 0 or filled_price <= 0:
                        skipped += 1
                        continue

                    dedupe_key = build_dedupe_key(
                        broker_trade_id,
                        broker_order_id,
                        filled_volume,
                        filled_price,
                    )
                    existing = (
                        session.query(TradeExecution)
                        .filter(TradeExecution.dedupe_key == dedupe_key)
                        .first()
                    )
                    if existing is not None:
                        skipped += 1
                        continue

                    # Parse fill time
                    raw_time = leg.get("filled_time")
                    if raw_time:
                        try:
                            filled_time = datetime.fromisoformat(str(raw_time))
                        except ValueError:
                            filled_time = order.filled_time or order.order_time or datetime.utcnow()
                    else:
                        filled_time = order.filled_time or order.order_time or datetime.utcnow()

                    execution = TradeExecution(
                        execution_uid=new_ulid(),
                        order_uid=order.order_uid,
                        broker_trade_id=broker_trade_id,
                        broker_order_id=broker_order_id,
                        stock_code=order.stock_code,
                        direction=order.direction,
                        filled_volume=filled_volume,
                        filled_price=filled_price,
                        filled_amount=filled_volume * filled_price,
                        filled_time=filled_time,
                        commission=getattr(order, "commission", None),
                        transfer_fee=getattr(order, "transfer_fee", None),
                        stamp_duty=getattr(order, "stamp_duty", None),
                        total_fee=getattr(order, "total_fee", None),
                        execution_source="order_polling_backfill",
                        dedupe_key=dedupe_key,
                    )
                    if not dry_run:
                        session.add(execution)
                    inserted += 1

                    if not dry_run and inserted % batch_size == 0:
                        session.commit()

                except Exception as exc:
                    failed += 1
                    logger.warning("Backfill failed for order_id={}: {}", order.order_id, exc)

        if not dry_run:
            session.commit()
        else:
            session.rollback()

    finally:
        session.close()

    return {"inspected": inspected, "inserted": inserted, "skipped": skipped, "failed": failed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill trade_executions from trade_breakdown JSON")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    result = backfill(dry_run=args.dry_run, batch_size=args.batch_size)
    print(json.dumps(result, indent=2))
    if result["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
