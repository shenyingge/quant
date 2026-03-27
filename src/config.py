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

    # Redis消息持久化配置
    redis_message_mode: str = Field(
        default="stream", env="REDIS_MESSAGE_MODE"
    )  # 消息模式: pubsub, list, stream
    redis_stream_name: str = Field(
        default="trading_signals_stream", env="REDIS_STREAM_NAME"
    )  # Stream名称
    redis_consumer_group: str = Field(
        default="trading_service", env="REDIS_CONSUMER_GROUP"
    )  # 消费者组名称
    redis_consumer_name: str = Field(default="consumer1", env="REDIS_CONSUMER_NAME")  # 消费者名称
    redis_list_name: str = Field(default="trading_signals_list", env="REDIS_LIST_NAME")  # List名称
    redis_stream_max_len: int = Field(default=10000, env="REDIS_STREAM_MAX_LEN")  # Stream最大长度
    redis_block_timeout: int = Field(default=1000, env="REDIS_BLOCK_TIMEOUT")  # 阻塞等待超时(毫秒)

    # 数据库配置
    db_url: str = Field(default="sqlite:///./trading.db", env="DATABASE_URL")

    # QMT配置
    qmt_session_id: int = Field(default=123456, env="QMT_SESSION_ID")
    qmt_session_id_trading_service: Optional[int] = Field(
        default=None, env="QMT_SESSION_ID_TRADING_SERVICE"
    )
    qmt_session_id_t0_daemon: Optional[int] = Field(default=None, env="QMT_SESSION_ID_T0_DAEMON")
    qmt_session_id_t0_sync: Optional[int] = Field(default=None, env="QMT_SESSION_ID_T0_SYNC")
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
    feishu_failure_notify_cooldown_seconds: int = Field(
        default=300, env="FEISHU_FAILURE_NOTIFY_COOLDOWN_SECONDS"
    )

    # 日志配置
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="./logs/trading_engine.log", env="LOG_FILE")

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

    # T+0策略配置
    t0_strategy_enabled: bool = Field(default=False, env="T0_STRATEGY_ENABLED")
    t0_stock_code: str = Field(default="601138.SH", env="T0_STOCK_CODE")
    t0_output_dir: str = Field(default="./output", env="T0_OUTPUT_DIR")
    t0_notify_observe_signals: bool = Field(default=False, env="T0_NOTIFY_OBSERVE_SIGNALS")
    t0_base_position: int = Field(default=2600, env="T0_BASE_POSITION")
    t0_tactical_position: int = Field(default=900, env="T0_TACTICAL_POSITION")
    t0_trade_unit: int = Field(default=100, env="T0_TRADE_UNIT")
    t0_max_trade_value: float = Field(default=70000, env="T0_MAX_TRADE_VALUE")
    t0_intraday_bar_period: str = Field(default="1m", env="T0_INTRADAY_BAR_PERIOD")
    t0_poll_interval_seconds: int = Field(default=60, env="T0_POLL_INTERVAL_SECONDS")
    t0_min_hold_minutes: int = Field(default=20, env="T0_MIN_HOLD_MINUTES")
    t0_positive_sell_start_time: str = Field(default="09:45", env="T0_POSITIVE_SELL_START_TIME")
    t0_positive_sell_end_time: str = Field(default="11:20", env="T0_POSITIVE_SELL_END_TIME")
    t0_positive_buyback_start_time: str = Field(
        default="13:30", env="T0_POSITIVE_BUYBACK_START_TIME"
    )
    t0_positive_buyback_end_time: str = Field(default="14:56", env="T0_POSITIVE_BUYBACK_END_TIME")
    t0_reverse_buy_start_time: str = Field(default="09:50", env="T0_REVERSE_BUY_START_TIME")
    t0_reverse_buy_end_time: str = Field(default="13:20", env="T0_REVERSE_BUY_END_TIME")
    t0_reverse_sell_start_time: str = Field(default="13:20", env="T0_REVERSE_SELL_START_TIME")
    t0_reverse_sell_end_time: str = Field(default="14:56", env="T0_REVERSE_SELL_END_TIME")
    t0_positive_sell_min_rise: float = Field(default=1.0, env="T0_POSITIVE_SELL_MIN_RISE")
    t0_positive_sell_min_pullback: float = Field(default=0.5, env="T0_POSITIVE_SELL_MIN_PULLBACK")
    t0_reverse_buy_min_drop: float = Field(default=1.5, env="T0_REVERSE_BUY_MIN_DROP")
    t0_reverse_buy_min_bounce: float = Field(default=0.4, env="T0_REVERSE_BUY_MIN_BOUNCE")
    t0_reverse_sell_min_profit: float = Field(default=1.2, env="T0_REVERSE_SELL_MIN_PROFIT")
    t0_reverse_sell_max_vwap_distance: float = Field(
        default=0.5, env="T0_REVERSE_SELL_MAX_VWAP_DISTANCE"
    )

    # NS主机每日导出配置
    ns_host: str = Field(default="ns", env="NS_HOST")
    ns_scp_remote_dir: str = Field(default="~/data/trade", env="NS_SCP_REMOTE_DIR")
    ns_ssh_username: Optional[str] = Field(default=None, env="NS_SSH_USERNAME")
    ns_ssh_key_file: Optional[str] = Field(default=None, env="NS_SSH_KEY_FILE")
    ns_ssh_port: int = Field(default=22, env="NS_SSH_PORT")
    rsync_bin: str = Field(default="rsync", env="RSYNC_BIN")
    ssh_bin: str = Field(default="ssh", env="SSH_BIN")

    # Meta DB配置
    meta_db_host: str = Field(default="", env="META_DB_HOST")
    meta_db_port: int = Field(default=15432, env="META_DB_PORT")
    meta_db_name: str = Field(default="", env="META_DB_NAME")
    meta_db_user: str = Field(default="", env="META_DB_USER")
    meta_db_password: str = Field(default="", env="META_DB_PASSWORD")
    meta_db_type: str = Field(default="postgresql+asyncpg", env="META_DB_TYPE")
    meta_db_schema: str = Field(default="", env="META_DB_SCHEMA")

    # Python路径配置
    pythonpath: Optional[str] = Field(default=None, env="PYTHONPATH")

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
