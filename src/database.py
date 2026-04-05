"""Backward compatibility wrapper for src.database -> src.infrastructure.db migration.

All model definitions and session management have been migrated to
src.infrastructure.db. This module now re-exports them for backward compatibility.
"""

# Re-export all models and session utilities from new location
from src.infrastructure.db.models import (
    Base,
    TRADING_SCHEMA,
    TradingSignal,
    OrderRecord,
    TradeExecution,
    OrderCancellation,
    TradingCalendar,
    StockInfo,
    StrategyRegimeState,
    StrategySignalHistory,
    AccountPosition,
    StrategyPositionState,
    StrategyEventOutbox,
)
from src.infrastructure.db.session import (
    create_tables,
    engine,
    get_database_details,
    get_db_session,
    get_db,
    SessionLocal,
)

__all__ = [
    "Base",
    "TRADING_SCHEMA",
    "TradingSignal",
    "OrderRecord",
    "TradeExecution",
    "OrderCancellation",
    "TradingCalendar",
    "StockInfo",
    "StrategyRegimeState",
    "StrategySignalHistory",
    "AccountPosition",
    "StrategyPositionState",
    "StrategyEventOutbox",
    "create_tables",
    "engine",
    "get_database_details",
    "get_db_session",
    "get_db",
    "SessionLocal",
]
