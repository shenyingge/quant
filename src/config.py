import os
from typing import Optional

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis配置
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_signal_channel: str = Field(default="trading_signals", env="REDIS_SIGNAL_CHANNEL")
    redis_trade_records_enabled: bool = Field(
        default=True, env="REDIS_TRADE_RECORDS_ENABLED"
    )  # 是否启用Redis交易记录存储
    redis_trade_records_prefix: str = Field(
        default="trade_record:", env="REDIS_TRADE_RECORDS_PREFIX"
    )  # 交易记录key前缀
    redis_trade_cleanup_time: str = Field(
        default="20:30", env="REDIS_TRADE_CLEANUP_TIME"
    )  # 每日清理时间

    # 数据库配置
    db_url: str = Field(default="sqlite:///./trading.db", env="DATABASE_URL")

    # QMT配置
    qmt_session_id: int = Field(default=123456, env="QMT_SESSION_ID")
    qmt_path: str = Field(default="", env="QMT_PATH")
    qmt_account_id: str = Field(default="", env="QMT_ACCOUNT_ID")
    qmt_account_type: str = Field(default="STOCK", env="QMT_ACCOUNT_TYPE")

    # 交易配置
    order_timeout_seconds: int = Field(
        default=60, env="ORDER_TIMEOUT_SECONDS"
    )  # 订单超时时间（秒）
    auto_cancel_enabled: bool = Field(default=True, env="AUTO_CANCEL_ENABLED")  # 是否启用自动撤单
    order_submit_timeout: int = Field(
        default=10, env="ORDER_SUBMIT_TIMEOUT"
    )  # 下单操作超时时间（秒）
    order_retry_attempts: int = Field(default=3, env="ORDER_RETRY_ATTEMPTS")  # 下单重试次数
    order_retry_delay: int = Field(default=2, env="ORDER_RETRY_DELAY")  # 下单重试间隔（秒）
    auto_cancel_timeout: int = Field(
        default=300, env="AUTO_CANCEL_TIMEOUT"
    )  # 超时自动撤单时间（秒）

    # 飞书配置
    feishu_webhook_url: Optional[str] = Field(default=None, env="FEISHU_WEBHOOK_URL")

    # 日志配置
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="./logs/trading_service.log", env="LOG_FILE")

    # 服务配置
    max_retry_attempts: int = Field(default=3, env="MAX_RETRY_ATTEMPTS")

    # 自动重连配置
    auto_reconnect_enabled: bool = Field(
        default=True, env="AUTO_RECONNECT_ENABLED"
    )  # 是否启用自动重连
    reconnect_max_attempts: int = Field(default=5, env="RECONNECT_MAX_ATTEMPTS")  # 最大重连尝试次数
    reconnect_initial_delay: int = Field(
        default=10, env="RECONNECT_INITIAL_DELAY"
    )  # 初始重连延迟（秒）
    reconnect_max_delay: int = Field(default=300, env="RECONNECT_MAX_DELAY")  # 最大重连延迟（秒）
    reconnect_backoff_factor: float = Field(
        default=2.0, env="RECONNECT_BACKOFF_FACTOR"
    )  # 重连延迟递增因子
    health_check_interval: int = Field(
        default=30, env="HEALTH_CHECK_INTERVAL"
    )  # 连接健康检查间隔（秒）

    # 交易日检查配置
    trading_day_check_enabled: bool = Field(
        default=True, env="TRADING_DAY_CHECK_ENABLED"
    )  # 是否启用交易日检查
    test_mode_enabled: bool = Field(
        default=False, env="TEST_MODE_ENABLED"
    )  # 测试模式（可在非交易日启动服务）

    # Python路径配置
    pythonpath: Optional[str] = Field(default=None, env="PYTHONPATH")

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
