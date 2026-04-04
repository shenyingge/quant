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
    create_engine,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from src.meta_db import get_meta_db_details, get_meta_db_sync_url, get_meta_db_trading_schema

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


class StrategyRegimeState(Base):
    """策略市场状态表"""

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


class StrategySignalHistory(Base):
    """策略信号历史表"""

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


class StrategyPositionState(Base):
    """Versioned strategy position snapshot used by the T+0 runtime."""

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


class StrategyEventOutbox(Base):
    """Reliable event outbox for post-commit strategy position notifications."""

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


engine = create_engine(get_meta_db_sync_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TRADING_SCHEMA}"'))
        Base.metadata.create_all(bind=connection)
        from src.order_record_costs import ensure_order_record_cost_columns

        ensure_order_record_cost_columns(connection)


def get_database_details():
    details = get_meta_db_details()
    details["url"] = get_meta_db_sync_url(hide_password=True)
    return details


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
