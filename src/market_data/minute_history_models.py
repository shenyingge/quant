from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, Index, Integer, MetaData, String, UniqueConstraint
from sqlalchemy.orm import declarative_base

from src.config import settings

MINUTE_BAR_SCHEMA = (settings.meta_db_schema or "").strip() or "gold"

MinuteBarBase = declarative_base(metadata=MetaData())


class StockMinuteBar(MinuteBarBase):
    __tablename__ = "stock_minute_bars_1m"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(32), nullable=False)
    trade_date = Column(Date, nullable=False)
    bar_time = Column(DateTime, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    source = Column(String(32), nullable=False, default="qmt_1m")
    ingested_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "bar_time", name="uq_stock_minute_1m_symbol_bar_time"),
        Index("idx_stock_minute_1m_trade_date", "trade_date"),
        Index("idx_stock_minute_1m_symbol_trade_date", "symbol", "trade_date"),
        {"schema": MINUTE_BAR_SCHEMA},
    )
