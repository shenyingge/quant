from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from src.infrastructure.config import settings
from src.infrastructure.db import AccountPosition, DEFAULT_META_DB_STRATEGY_ID, SessionLocal
from src.infrastructure.logger_config import configured_logger as logger


def resolve_account_positions_session_id() -> int:
    """Use the trading-service session when available for account snapshot refreshes."""
    return settings.qmt_session_id_trading_service or settings.qmt_session_id


def sync_account_positions_via_qmt(*, source: str, session_id: Optional[int] = None) -> Optional[int]:
    """Connect to QMT, refresh the Meta DB position snapshot, and disconnect safely."""
    from src.trading.execution.qmt_trader import QMTTrader

    resolved_session_id = session_id or resolve_account_positions_session_id()
    trader = QMTTrader(session_id=resolved_session_id)

    try:
        if not trader.connect():
            logger.warning(
                "Skipping account position sync because QMT connect failed, session_id={}",
                resolved_session_id,
            )
            return None

        return sync_account_positions_from_qmt(trader, source=source)
    finally:
        try:
            trader.disconnect()
        except Exception:
            logger.debug(
                "Ignoring QMT disconnect error after position sync, session_id={}",
                resolved_session_id,
            )


def sync_account_positions_from_qmt(trader: Any, *, source: str) -> Optional[int]:
    """Refresh the account position snapshot in Meta DB from QMT."""
    positions = trader.get_positions()
    if positions is None:
        logger.warning("Skipping account position sync because QMT positions are unavailable")
        return None

    account_id = settings.qmt_account_id
    snapshot_time = datetime.utcnow()
    session = SessionLocal()

    try:
        existing_rows = (
            session.query(AccountPosition)
            .filter(
                AccountPosition.strategy_id == DEFAULT_META_DB_STRATEGY_ID,
                AccountPosition.account_id == account_id,
            )
            .all()
        )
        existing_by_code = {row.stock_code: row for row in existing_rows}
        seen_codes = set()

        for item in positions:
            stock_code = str(item.get("stock_code") or "").strip()
            if not stock_code:
                continue

            row = existing_by_code.get(stock_code)
            if row is None:
                row = AccountPosition(
                    strategy_id=DEFAULT_META_DB_STRATEGY_ID,
                    account_id=account_id,
                    stock_code=stock_code,
                )
                session.add(row)

            row.total_volume = int(item.get("volume") or 0)
            row.available_volume = int(
                item.get("available_volume") or item.get("can_use_volume") or 0
            )
            row.avg_price = float(item.get("avg_price") or item.get("open_price") or 0.0)
            row.market_value = _to_optional_float(item.get("market_value"))
            row.last_price = _to_optional_float(item.get("last_price"))
            row.snapshot_source = source
            row.snapshot_time = snapshot_time
            seen_codes.add(stock_code)

        query = session.query(AccountPosition).filter(
            AccountPosition.strategy_id == DEFAULT_META_DB_STRATEGY_ID,
            AccountPosition.account_id == account_id,
        )
        if seen_codes:
            query = query.filter(~AccountPosition.stock_code.in_(seen_codes))
        query.delete(synchronize_session=False)

        session.commit()
        logger.info(
            "Synced {} account position row(s) from QMT into Meta DB, source={}",
            len(seen_codes),
            source,
        )
        return len(seen_codes)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _to_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
