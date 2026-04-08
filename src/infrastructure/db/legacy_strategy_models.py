"""Legacy strategy ORM models kept only for optional offline access.

These models are intentionally excluded from runtime metadata creation,
Meta DB synchronization, and package-level exports.
"""

from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, Index, Integer, MetaData, String, Text
from sqlalchemy.ext.declarative import declarative_base

from src.infrastructure.db.meta_db import get_meta_db_trading_schema

TRADING_SCHEMA = get_meta_db_trading_schema()
LegacyStrategyBase = declarative_base(metadata=MetaData(schema=TRADING_SCHEMA))


class StrategyRegimeState(LegacyStrategyBase):
    __tablename__ = "strategy_regime_state"

    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(50), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    regime = Column(String(20), nullable=False)
    ma20 = Column(Float)
    ma60 = Column(Float)
    trend_spread = Column(Float)
    confirmation_days = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_strategy_date", "strategy_name", "trade_date"),)


class StrategySignalHistory(LegacyStrategyBase):
    __tablename__ = "strategy_signal_history"

    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(50), nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    signal_time = Column(DateTime, nullable=False)
    regime = Column(String(20))
    signal_action = Column(String(30))
    branch_locked = Column(String(20), nullable=True)
    stock_code = Column(String(20))
    price = Column(Float)
    suggested_volume = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_strategy_date_time", "strategy_name", "trade_date", "signal_time"),
    )


class StrategyPositionState(LegacyStrategyBase):
    __tablename__ = "strategy_positions"

    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(50), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    total_position = Column(Integer, nullable=False, default=0)
    available_volume = Column(Integer, nullable=False, default=0)
    cost_price = Column(Float, nullable=False, default=0.0)
    base_position = Column(Integer, nullable=False, default=0)
    tactical_position = Column(Integer, nullable=False, default=0)
    max_position = Column(Integer, nullable=False, default=0)
    t0_sell_available = Column(Integer, nullable=False, default=0)
    t0_buy_capacity = Column(Integer, nullable=False, default=0)
    last_sync_time = Column(DateTime, nullable=True)
    last_sync_source = Column(String(50), nullable=False, default="default")
    last_qmt_sync_time = Column(DateTime, nullable=True)
    last_reconciled_fill_time = Column(DateTime, nullable=True)
    last_fill_time = Column(DateTime, nullable=True)
    position_version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_strategy_position_unique", "strategy_name", "stock_code", unique=True),
    )


class StrategyEventOutbox(LegacyStrategyBase):
    __tablename__ = "strategy_event_outbox"

    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(50), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    position_version = Column(Integer, nullable=False)
    payload = Column(Text, nullable=False)
    publish_status = Column(String(20), nullable=False, default="pending")
    published_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_strategy_outbox_status", "publish_status", "created_at"),)
