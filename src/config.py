import os
from typing import Optional

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_signal_channel: str = Field(default="trading_signals", env="REDIS_SIGNAL_CHANNEL")
    redis_trade_records_enabled: bool = Field(default=True, env="REDIS_TRADE_RECORDS_ENABLED")
    redis_trade_records_prefix: str = Field(
        default="trade_record:", env="REDIS_TRADE_RECORDS_PREFIX"
    )
    redis_trade_cleanup_time: str = Field(default="20:30", env="REDIS_TRADE_CLEANUP_TIME")

    redis_message_mode: str = Field(default="stream", env="REDIS_MESSAGE_MODE")
    redis_stream_name: str = Field(default="trading_signals_stream", env="REDIS_STREAM_NAME")
    redis_consumer_group: str = Field(default="trading_service", env="REDIS_CONSUMER_GROUP")
    redis_consumer_name: str = Field(default="consumer1", env="REDIS_CONSUMER_NAME")
    redis_list_name: str = Field(default="trading_signals_list", env="REDIS_LIST_NAME")
    redis_stream_max_len: int = Field(default=10000, env="REDIS_STREAM_MAX_LEN")
    redis_block_timeout: int = Field(default=1000, env="REDIS_BLOCK_TIMEOUT")
    redis_tick_cache_db: int = Field(default=1, env="REDIS_TICK_CACHE_DB")
    redis_tick_cache_ttl: int = Field(default=28800, env="REDIS_TICK_CACHE_TTL")
    redis_t0_signal_key: str = Field(default="t0_signal_card", env="REDIS_T0_SIGNAL_KEY")
    redis_t0_signal_ttl: int = Field(default=86400, env="REDIS_T0_SIGNAL_TTL")
    redis_quote_stream_channel: str = Field(
        default="quote_stream", env="REDIS_QUOTE_STREAM_CHANNEL"
    )
    redis_quote_subscriptions_key: str = Field(
        default="quote_subscriptions", env="REDIS_QUOTE_SUBSCRIPTIONS_KEY"
    )
    redis_quote_control_channel: str = Field(
        default="quote_subscription_events", env="REDIS_QUOTE_CONTROL_CHANNEL"
    )
    redis_quote_latest_prefix: str = Field(
        default="quote_latest:", env="REDIS_QUOTE_LATEST_PREFIX"
    )
    redis_quote_latest_ttl_seconds: int = Field(
        default=0, env="REDIS_QUOTE_LATEST_TTL_SECONDS"
    )
    redis_quote_enriched_stream_channel: str = Field(
        default="quote_stream_enriched", env="REDIS_QUOTE_ENRICHED_STREAM_CHANNEL"
    )
    redis_quote_enriched_latest_prefix: str = Field(
        default="quote_enriched_latest:", env="REDIS_QUOTE_ENRICHED_LATEST_PREFIX"
    )
    redis_quote_enriched_latest_ttl_seconds: int = Field(
        default=0, env="REDIS_QUOTE_ENRICHED_LATEST_TTL_SECONDS"
    )

    qmt_session_id: int = Field(default=123456, env="QMT_SESSION_ID")
    qmt_session_id_trading_service: Optional[int] = Field(
        default=None, env="QMT_SESSION_ID_TRADING_SERVICE"
    )
    qmt_session_id_t0_daemon: Optional[int] = Field(default=None, env="QMT_SESSION_ID_T0_DAEMON")
    qmt_session_id_t0_sync: Optional[int] = Field(default=None, env="QMT_SESSION_ID_T0_SYNC")
    qmt_path: str = Field(default="", env="QMT_PATH")
    qmt_account_id: str = Field(default="", env="QMT_ACCOUNT_ID")
    qmt_account_type: str = Field(default="STOCK", env="QMT_ACCOUNT_TYPE")

    order_timeout_seconds: int = Field(default=60, env="ORDER_TIMEOUT_SECONDS")
    auto_cancel_enabled: bool = Field(default=True, env="AUTO_CANCEL_ENABLED")
    order_submit_timeout: int = Field(default=10, env="ORDER_SUBMIT_TIMEOUT")
    order_retry_attempts: int = Field(default=3, env="ORDER_RETRY_ATTEMPTS")
    order_retry_delay: int = Field(default=2, env="ORDER_RETRY_DELAY")
    auto_cancel_timeout: int = Field(default=300, env="AUTO_CANCEL_TIMEOUT")

    feishu_webhook_url: Optional[str] = Field(default=None, env="FEISHU_WEBHOOK_URL")
    feishu_failure_notify_cooldown_seconds: int = Field(
        default=300, env="FEISHU_FAILURE_NOTIFY_COOLDOWN_SECONDS"
    )

    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_dir: str = Field(default="./logs/current", env="LOG_DIR")
    log_archive_dir: str = Field(default="./logs/archive", env="LOG_ARCHIVE_DIR")
    log_file: str = Field(default="./logs/current/app.log", env="LOG_FILE")
    log_rotation: str = Field(default="20 MB", env="LOG_ROTATION")
    log_retention: str = Field(default="30 days", env="LOG_RETENTION")
    log_compression: str = Field(default="zip", env="LOG_COMPRESSION")

    max_retry_attempts: int = Field(default=3, env="MAX_RETRY_ATTEMPTS")

    auto_reconnect_enabled: bool = Field(default=True, env="AUTO_RECONNECT_ENABLED")
    reconnect_max_attempts: int = Field(default=5, env="RECONNECT_MAX_ATTEMPTS")
    reconnect_initial_delay: int = Field(default=10, env="RECONNECT_INITIAL_DELAY")
    reconnect_max_delay: int = Field(default=300, env="RECONNECT_MAX_DELAY")
    reconnect_backoff_factor: float = Field(default=2.0, env="RECONNECT_BACKOFF_FACTOR")
    health_check_interval: int = Field(default=30, env="HEALTH_CHECK_INTERVAL")
    quote_stream_enabled: bool = Field(default=True, env="QUOTE_STREAM_ENABLED")
    quote_stream_period: str = Field(default="tick", env="QUOTE_STREAM_PERIOD")
    quote_stream_reconcile_interval_seconds: int = Field(
        default=5, env="QUOTE_STREAM_RECONCILE_INTERVAL_SECONDS"
    )
    cms_server_host: str = Field(default="127.0.0.1", env="CMS_SERVER_HOST")
    cms_server_port: int = Field(default=8780, env="CMS_SERVER_PORT")
    cms_server_timeout_seconds: int = Field(default=2, env="CMS_SERVER_TIMEOUT_SECONDS")
    cms_server_refresh_interval_seconds: int = Field(
        default=15, env="CMS_SERVER_REFRESH_INTERVAL_SECONDS"
    )
    cms_quote_position_cache_seconds: int = Field(
        default=2, env="CMS_QUOTE_POSITION_CACHE_SECONDS"
    )
    watchdog_enabled: bool = Field(default=True, env="WATCHDOG_ENABLED")
    watchdog_check_interval_seconds: int = Field(
        default=30, env="WATCHDOG_CHECK_INTERVAL_SECONDS"
    )
    watchdog_min_restart_interval_seconds: int = Field(
        default=120, env="WATCHDOG_MIN_RESTART_INTERVAL_SECONDS"
    )
    watchdog_state_path: str = Field(
        default="./output/watchdog_state.json", env="WATCHDOG_STATE_PATH"
    )
    watchdog_enforce_stop_outside_window: bool = Field(
        default=True, env="WATCHDOG_ENFORCE_STOP_OUTSIDE_WINDOW"
    )
    watchdog_enable_trading_service: bool = Field(
        default=True, env="WATCHDOG_ENABLE_TRADING_SERVICE"
    )
    watchdog_enable_t0_daemon: bool = Field(default=True, env="WATCHDOG_ENABLE_T0_DAEMON")
    watchdog_enable_t0_reconcile: bool = Field(
        default=True, env="WATCHDOG_ENABLE_T0_RECONCILE"
    )
    watchdog_trading_start_time: str = Field(
        default="08:35", env="WATCHDOG_TRADING_START_TIME"
    )
    watchdog_trading_stop_time: str = Field(default="21:05", env="WATCHDOG_TRADING_STOP_TIME")
    watchdog_t0_start_time: str = Field(default="09:20", env="WATCHDOG_T0_START_TIME")
    watchdog_t0_stop_time: str = Field(default="15:05", env="WATCHDOG_T0_STOP_TIME")
    watchdog_t0_reconcile_time: str = Field(
        default="15:10", env="WATCHDOG_T0_RECONCILE_TIME"
    )
    watchdog_job_max_delay_minutes: int = Field(
        default=120, env="WATCHDOG_JOB_MAX_DELAY_MINUTES"
    )
    trading_day_check_enabled: bool = Field(default=True, env="TRADING_DAY_CHECK_ENABLED")
    test_mode_enabled: bool = Field(default=False, env="TEST_MODE_ENABLED")
    tushare_token: Optional[str] = Field(default=None, env="TUSHARE_TOKEN")
    tushare_trade_calendar_exchange: str = Field(
        default="SSE", env="TUSHARE_TRADE_CALENDAR_EXCHANGE"
    )

    t0_strategy_enabled: bool = Field(default=False, env="T0_STRATEGY_ENABLED")
    t0_stock_code: str = Field(default="601138.SH", env="T0_STOCK_CODE")
    t0_output_dir: str = Field(default="./output", env="T0_OUTPUT_DIR")
    t0_save_signal_card: bool = Field(default=False, env="T0_SAVE_SIGNAL_CARD")
    t0_notify_observe_signals: bool = Field(default=False, env="T0_NOTIFY_OBSERVE_SIGNALS")
    t0_base_position: int = Field(default=3100, env="T0_BASE_POSITION")
    t0_tactical_position: int = Field(default=900, env="T0_TACTICAL_POSITION")
    t0_trade_unit: int = Field(default=100, env="T0_TRADE_UNIT")
    t0_max_trade_value: float = Field(default=50000, env="T0_MAX_TRADE_VALUE")
    t0_intraday_bar_period: str = Field(default="1m", env="T0_INTRADAY_BAR_PERIOD")
    t0_poll_interval_seconds: int = Field(default=60, env="T0_POLL_INTERVAL_SECONDS")
    t0_sync_connect_retry_attempts: int = Field(default=3, env="T0_SYNC_CONNECT_RETRY_ATTEMPTS")
    t0_sync_connect_retry_delay_seconds: int = Field(
        default=5, env="T0_SYNC_CONNECT_RETRY_DELAY_SECONDS"
    )
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

    ns_host: str = Field(default="ns", env="NS_HOST")
    ns_scp_remote_dir: str = Field(default="~/data/trade", env="NS_SCP_REMOTE_DIR")
    ns_ssh_username: Optional[str] = Field(default=None, env="NS_SSH_USERNAME")
    ns_ssh_key_file: Optional[str] = Field(default=None, env="NS_SSH_KEY_FILE")
    ns_ssh_port: int = Field(default=22, env="NS_SSH_PORT")
    rsync_bin: str = Field(default="rsync", env="RSYNC_BIN")
    ssh_bin: str = Field(default="ssh", env="SSH_BIN")

    meta_db_host: str = Field(default="", env="META_DB_HOST")
    meta_db_port: int = Field(default=15432, env="META_DB_PORT")
    meta_db_name: str = Field(default="", env="META_DB_NAME")
    meta_db_user: str = Field(default="", env="META_DB_USER")
    meta_db_password: str = Field(default="", env="META_DB_PASSWORD")
    meta_db_type: str = Field(default="postgresql+asyncpg", env="META_DB_TYPE")
    meta_db_sync_type: str = Field(default="postgresql+psycopg", env="META_DB_SYNC_TYPE")
    meta_db_schema: str = Field(default="", env="META_DB_SCHEMA")
    meta_db_trading_schema: str = Field(default="trading", env="META_DB_TRADING_SCHEMA")

    pythonpath: Optional[str] = Field(default=None, env="PYTHONPATH")

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
