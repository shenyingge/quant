from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from src.config import settings

Base = declarative_base()


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


engine = create_engine(settings.db_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
