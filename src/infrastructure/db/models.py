"""Database ORM models (migrated from src/database.py)."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base

from src.infrastructure.db.meta_db import get_meta_db_trading_schema

TRADING_SCHEMA = get_meta_db_trading_schema()
Base = declarative_base(metadata=MetaData(schema=TRADING_SCHEMA))


class TradingSignal(Base):
    __tablename__ = "trading_signals"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(String(50), unique=True, index=True)
    stock_code = Column(String(20), nullable=False)  # 证券代码
    direction = Column(String(10), nullable=False)  # 买卖方向: BUY, SELL
    volume = Column(Integer, nullable=False)  # 委托数量
    price = Column(Float, nullable=True)  # 委托价格
    signal_time = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)  # 错误信息
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderRecord(Base):
    __tablename__ = "order_records"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(String(50), index=True)
    order_id = Column(String(50), unique=True)  # 委托编号
    order_uid = Column(String(50), unique=True, index=True, nullable=True)
    order_type = Column(String(50), nullable=False, default="LIMIT")
    submit_request_id = Column(String(50), index=True, nullable=True)
    order_source = Column(String(50), default="signal_submit")
    stock_code = Column(String(20), nullable=False)  # 证券代码
    direction = Column(String(10), nullable=False)  # 买卖方向: BUY, SELL
    volume = Column(Integer, nullable=False)  # 委托数量
    price = Column(Float, nullable=True)  # 委托价格
    order_status = Column(String(20), default="PENDING")  # 委托状态
    order_time = Column(DateTime, default=datetime.utcnow)  # 委托时间
    filled_price = Column(Float, nullable=True)  # 成交价格
    filled_volume = Column(Integer, default=0)  # 成交数量
    filled_time = Column(DateTime, nullable=True)  # 成交时间
    trade_amount = Column(Float, nullable=True)
    commission = Column(Float, nullable=True)
    transfer_fee = Column(Float, nullable=True)
    stamp_duty = Column(Float, nullable=True)
    total_fee = Column(Float, nullable=True)
    transaction_cost = Column(Float, nullable=True)
    settlement_amount = Column(Float, nullable=True)
    net_cash_effect = Column(Float, nullable=True)
    trade_breakdown = Column(Text, nullable=True)
    fill_notified = Column(Boolean, default=False)  # 是否已发送成交通知
    error_message = Column(Text, nullable=True)  # 错误信息
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TradeExecution(Base):
    """Each fill from QMT gets its own immutable row."""

    __tablename__ = "trade_executions"

    id = Column(Integer, primary_key=True)
    execution_uid = Column(String(50), unique=True, index=True, nullable=False)
    order_uid = Column(String(50), index=True, nullable=True)
    broker_trade_id = Column(String(50), index=True, nullable=True)
    broker_order_id = Column(String(50), index=True, nullable=True)
    stock_code = Column(String(20), nullable=False)
    direction = Column(String(10), nullable=False)
    filled_volume = Column(Integer, nullable=False)
    filled_price = Column(Float, nullable=False)
    filled_amount = Column(Float, nullable=False)
    filled_time = Column(DateTime, nullable=False)
    commission = Column(Float, nullable=True)
    transfer_fee = Column(Float, nullable=True)
    stamp_duty = Column(Float, nullable=True)
    total_fee = Column(Float, nullable=True)
    execution_source = Column(String(50), default="qmt_trade_callback")
    dedupe_key = Column(String(100), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderCancellation(Base):
    """Each cancellation event gets its own row."""

    __tablename__ = "order_cancellations"

    id = Column(Integer, primary_key=True)
    order_uid = Column(String(50), index=True, nullable=False)
    broker_order_id = Column(String(50), index=True, nullable=True)
    stock_code = Column(String(20), nullable=False)
    cancelled_volume = Column(Integer, nullable=False)
    cancel_time = Column(DateTime, nullable=False)
    cancel_reason = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class TradingCalendar(Base):
    """交易日历表，缓存交易日数据"""

    __tablename__ = "trading_calendar"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, nullable=False, index=True)  # 日期
    is_trading = Column(Boolean, nullable=False)  # 是否为交易日
    year = Column(Integer, nullable=False, index=True)  # 年份，便于查询
    market = Column(String(10), nullable=False, default="SSE")  # 市场：SSE(上交所), SZSE(深交所)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 添加复合索引，提高查询效率
    __table_args__ = (Index("idx_year_market", "year", "market"),)


class StockInfo(Base):
    """股票信息表，缓存股票基本信息"""

    __tablename__ = "stock_info"

    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(
        String(20), unique=True, nullable=False, index=True
    )  # 股票代码（含市场后缀，如000001.SZ）
    stock_name = Column(String(100), nullable=False)  # 股票名称
    market = Column(String(10), nullable=True)  # 市场：SZ(深圳), SH(上海)
    industry = Column(String(100), nullable=True)  # 行业
    list_date = Column(Date, nullable=True)  # 上市日期
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AccountPosition(Base):
    """Broker-synced account position snapshot."""

    __tablename__ = "account_positions"

    id = Column(Integer, primary_key=True)
    account_id = Column(String(50), nullable=False, index=True)
    stock_code = Column(String(20), nullable=False, index=True)
    total_volume = Column(Integer, nullable=False, default=0)
    available_volume = Column(Integer, nullable=False, default=0)
    avg_price = Column(Float, nullable=False, default=0.0)
    market_value = Column(Float, nullable=True)
    last_price = Column(Float, nullable=True)
    snapshot_source = Column(String(50), nullable=False, default="qmt")
    snapshot_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_account_position_account_stock", "account_id", "stock_code", unique=True),
    )
