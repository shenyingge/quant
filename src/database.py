from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
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
    error_message = Column(Text, nullable=True)  # 错误信息
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ServiceLog(Base):
    __tablename__ = "service_logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(10), nullable=False)
    message = Column(Text, nullable=False)
    module = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

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
