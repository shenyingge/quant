from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
    # Redis配置
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_signal_channel: str = Field(default="trading_signals", env="REDIS_SIGNAL_CHANNEL")
    redis_trade_records_enabled: bool = Field(default=True, env="REDIS_TRADE_RECORDS_ENABLED")  # 是否启用Redis交易记录存储
    redis_trade_records_prefix: str = Field(default="trade_record:", env="REDIS_TRADE_RECORDS_PREFIX")  # 交易记录key前缀
    redis_trade_cleanup_time: str = Field(default="20:30", env="REDIS_TRADE_CLEANUP_TIME")  # 每日清理时间
    
    # 数据库配置
    db_url: str = Field(default="sqlite:///./trading.db", env="DATABASE_URL")
    
    # QMT配置
    qmt_session_id: int = Field(default=123456, env="QMT_SESSION_ID")
    qmt_path: str = Field(default="", env="QMT_PATH")
    qmt_account_id: str = Field(default="", env="QMT_ACCOUNT_ID")
    qmt_account_type: str = Field(default="STOCK", env="QMT_ACCOUNT_TYPE")
    
    # 交易配置
    order_timeout_seconds: int = Field(default=60, env="ORDER_TIMEOUT_SECONDS")  # 订单超时时间（秒）
    auto_cancel_enabled: bool = Field(default=True, env="AUTO_CANCEL_ENABLED")  # 是否启用自动撤单
    order_submit_timeout: int = Field(default=10, env="ORDER_SUBMIT_TIMEOUT")  # 下单操作超时时间（秒）
    
    # 飞书配置
    feishu_webhook_url: Optional[str] = Field(default=None, env="FEISHU_WEBHOOK_URL")
    
    # 日志配置
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="./logs/trading_service.log", env="LOG_FILE")
    
    # 服务配置
    max_retry_attempts: int = Field(default=3, env="MAX_RETRY_ATTEMPTS")
    
    # 交易日检查配置
    trading_day_check_enabled: bool = Field(default=True, env="TRADING_DAY_CHECK_ENABLED")  # 是否启用交易日检查
    
    # Python路径配置
    pythonpath: Optional[str] = Field(default=None, env="PYTHONPATH")
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra='ignore'
    )

settings = Settings()