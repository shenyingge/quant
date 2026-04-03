# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a QMT (迅投量化交易系统) automated trading service that listens to Redis channels for trading signals and executes orders automatically through the QMT platform. The system runs on Windows with MSYS2/MINGW64 environment and uses SQLAlchemy for database management.

## Development Commands

### Package Management (using uv)
```bash
# Install/update dependencies
uv sync

# Add new dependency
uv add <package_name>

# Run Python scripts with project dependencies
uv run python <script.py>
```

### Running the Service
```bash
# Start trading service (console mode)
uv run python main.py run

# Start with custom retry settings
uv run python main.py run --max-retries=5 --retry-delay=30

# Run with Windows batch script
scripts\run_console.bat

# Test mode (skip trading day check)
uv run python main.py test-run

# Test mode with custom retry settings
uv run python main.py test-run --max-retries=2 --retry-delay=120

# Test system connections
uv run python main.py test

# Manual backup
uv run python main.py backup

# View backup configuration
uv run python main.py backup-config

# Manage stock info cache
uv run python main.py stock-info

# Manage trading calendar
uv run python main.py calendar

# Send daily P&L summary notification
uv run python main.py pnl-summary

# Export daily holdings and trades
uv run python main.py export-daily

# 导出分钟历史行情包
uv run python main.py export-minute-history --trade-date today --listed-only

# 按日任务默认参数拉取当日分钟行情
uv run python main.py export-minute-daily

# Run T+0 once
uv run python main.py t0-strategy

# Run T+0 daemon
uv run python main.py t0-daemon

# Sync T+0 position from QMT
uv run python main.py t0-sync-position

# Run T+0 strategy diagnostics (detailed decision process)
uv run python main.py t0-diagnose

# Run file-driven T+0 backtest
uv run python main.py t0-backtest --minute-data minute.csv --daily-data daily.csv

# Database migration (run after updates)
uv run python migrate_db.py
```

### Testing
```bash
# Run all tests
uv run python tests/run_tests.py

# Run specific test
uv run python tests/test_redis_integration.py
uv run python tests/test_passorder.py

# List available tests
uv run python tests/run_tests.py --list

# Run tests with pytest (if installed)
uv run python tests/run_tests.py --pytest
```

## Architecture

### Core Components

1. **main.py**: Entry point that handles commands and initializes the trading service
2. **src/trading_service.py**: Core service orchestrator that manages Redis listener, trader, and notifications
3. **src/redis_listener.py**: Listens to Redis channels for trading signals in JSON format
4. **src/trader.py**: QMT trading interface using xtquant SDK for order execution
5. **src/database.py**: SQLAlchemy models for signals and orders persistence
6. **src/notifications.py**: Feishu (飞书) webhook notifications for trading events
7. **src/backup_service.py**: Automated daily backup of trading data
8. **src/config.py**: Pydantic settings management from environment variables
9. **src/daily_pnl_calculator.py**: Daily profit/loss calculation and summary generation
10. **src/stock_info.py**: Stock information cache and name display management

### Signal Processing Flow

1. Redis publishes trading signal to configured channel
2. RedisSignalListener receives and validates JSON signal
3. Signal saved to SQLite database via SQLAlchemy
4. Trader executes order through QMT passorder API
5. Order status monitored with callbacks
6. Notifications sent to Feishu for key events
7. Database updated with order results
8. Daily P&L summary calculated and sent at 15:10 automatically

### Trading Signal Format
```json
{
    "signal_id": "unique_identifier",
    "stock_code": "000001",
    "direction": "BUY|SELL",
    "volume": 100,
    "price": 10.50,
    "order_type": 23
}
```

### Key Configuration (via .env)

- **Redis**: REDIS_HOST, REDIS_PORT, REDIS_SIGNAL_CHANNEL, REDIS_MESSAGE_MODE, REDIS_STREAM_NAME, REDIS_CONSUMER_GROUP
- **QMT**: QMT_SESSION_ID, QMT_PATH, QMT_ACCOUNT_ID
- **Notifications**: FEISHU_WEBHOOK_URL, FEISHU_SECRET
- **Trading**: ORDER_TIMEOUT_SECONDS, AUTO_CANCEL_ENABLED, ORDER_RETRY_ATTEMPTS, AUTO_CANCEL_TIMEOUT
- **Backup**: BACKUP_ENABLED, BACKUP_TIME, BACKUP_DIR
- **Auto Reconnect**: AUTO_RECONNECT_ENABLED, RECONNECT_MAX_ATTEMPTS, RECONNECT_INITIAL_DELAY, HEALTH_CHECK_INTERVAL

### Windows Service Integration

The system can run as a Windows scheduled task using scripts in the `scripts/` directory:
- `register_watchdog_service_task.ps1`: Registers the single-entry startup task `Quant_Watchdog_Service`
- `setup_minute_history_task.bat`: Creates a scheduled task for daily minute-history export
- The watchdog scheduled task and managed services now launch `python main.py ...` directly without a PowerShell startup wrapper
- Mode-specific QMT session IDs are supported for trading service, T+0 daemon, and T+0 sync

## T+0 Strategy And Backtest

The repository now contains a separated T+0 stack:

- `src/strategy/core/`: pure strategy models, params, regime classifier, and state machine
- `src/strategy/`: realtime adapters, repositories, notifier/output integration
- `src/backtest/`: file-driven Linux-friendly backtest loader, simulator, and CLI

Key T+0 commands:

- `python main.py t0-strategy`: run once and write the latest signal card
- `python main.py t0-daemon`: poll every minute during market hours
- `python main.py t0-sync-position`: sync current QMT position into local T+0 state
- `python main.py t0-backtest ...`: run file-driven backtests that emit `signals.csv`, `fills.csv`, and `summary.json`

Runtime outputs under `output/` are generated local state, not source files to keep under version control.

### Important Considerations

1. **Environment**: Requires MINGW64/MSYS2 for proper UTF-8 handling on Windows
2. **QMT Session**: Must have QMT client running and logged in before starting service
3. **Real Trading**: passorder tests will execute real orders - use test accounts
4. **Concurrent Orders**: System handles multiple simultaneous trading signals
5. **Auto Reconnect**: Automatic reconnection for Redis and QMT connection failures
   - Enabled by default with exponential backoff retry strategy
   - Health check monitoring every 30 seconds
   - Intelligent connection recovery with detailed notifications
6. **Trading Days**: Uses akshare to fetch and cache trading calendar in database
   - Automatically checks if current day is a trading day before starting
   - Use `python main.py test-run` to run on non-trading days for testing
   - Set `TEST_MODE_ENABLED=true` in .env to permanently enable test mode
   - Calendar auto-updates in December for next year
7. **QMT Constants**: Uses xtconstant enumeration values instead of hardcoded strings
   - Order statuses, operation types, and price types use standard QMT constants
   - Account status mapping with proper Chinese descriptions
   - See src/qmt_constants.py for mappings and utility functions
   - Avoids hardcoded Chinese strings like "已成交", "已撤销" etc.
   - Internal processing uses status codes, notifications use descriptions
8. **Daily P&L Summary**: Automated daily trading summary sent to Feishu at 15:10
   - Includes trading overview, time distribution, stock breakdown, and P&L estimates
   - Manual trigger available with `python main.py pnl-summary`
   - Stock names automatically resolved and displayed alongside codes
   - Simple P&L estimation based on matched buy/sell orders
9. **Order Retry & Timeout Management**: Advanced order execution with automatic retry and timeout controls
   - Automatic retry up to 3 times for failed orders with configurable delay
   - Timeout-based automatic order cancellation for pending orders
   - Real-time monitoring and notification of retry attempts and timeout cancellations
   - Comprehensive error tracking and status reporting

## Auto Reconnection Configuration

The system includes intelligent auto-reconnection capabilities for both Redis and QMT connections during trading days.

### Configuration Variables (.env)

```bash
# Auto Reconnect Settings
AUTO_RECONNECT_ENABLED=true                # Enable auto reconnection (default: true)
RECONNECT_MAX_ATTEMPTS=5                   # Maximum reconnection attempts (default: 5)
RECONNECT_INITIAL_DELAY=10                 # Initial delay in seconds (default: 10)
RECONNECT_MAX_DELAY=300                    # Maximum delay in seconds (default: 300)
RECONNECT_BACKOFF_FACTOR=2.0              # Delay multiplier for exponential backoff (default: 2.0)
HEALTH_CHECK_INTERVAL=30                   # Health check interval in seconds (default: 30)
```

### Features

1. **Exponential Backoff**: Reconnection delays increase progressively (10s → 20s → 40s → 80s → 160s → 300s max)
2. **Health Monitoring**: Continuous connection health checks every 30 seconds
3. **Intelligent Recovery**: Automatic detection and recovery from connection failures
4. **Real-time Notifications**: Feishu alerts for connection status changes:
   - Connection lost warnings
   - Connection restored confirmations
   - Reconnection failure alerts
5. **Graceful Degradation**: Service continues running even during connection issues
6. **Trading Day Aware**: Auto-reconnection only active during trading hours

### Connection States

- **Connected**: Normal operation with active monitoring
- **Reconnecting**: Attempting to restore connection with exponential backoff
- **Failed**: Maximum attempts reached, manual intervention required

### Manual Control

```bash
# Disable auto-reconnection for troubleshooting
AUTO_RECONNECT_ENABLED=false

# Adjust reconnection aggressiveness
RECONNECT_MAX_ATTEMPTS=3          # Fewer attempts
RECONNECT_INITIAL_DELAY=5         # Faster initial retry
HEALTH_CHECK_INTERVAL=60          # Less frequent health checks
```

## Order Retry & Timeout Configuration

The system provides robust order execution with automatic retry and timeout management.

### Configuration Variables (.env)

```bash
# Order Retry Settings
ORDER_RETRY_ATTEMPTS=3             # Number of retry attempts for failed orders (default: 3)
ORDER_RETRY_DELAY=2                # Delay between retries in seconds (default: 2)

# Timeout Management
AUTO_CANCEL_ENABLED=true           # Enable automatic order cancellation (default: true)
AUTO_CANCEL_TIMEOUT=300            # Timeout for automatic order cancellation in seconds (default: 300)
ORDER_TIMEOUT_SECONDS=60           # General order timeout (default: 60)
ORDER_SUBMIT_TIMEOUT=10            # Order submission timeout (default: 10)
```

### Features

1. **Automatic Retry**: Failed orders are automatically retried up to 3 times
   - Configurable retry attempts and delay between attempts
   - Exponential backoff can be implemented if needed
   - Each retry attempt is logged and tracked

2. **Timeout Management**: Orders that remain pending too long are automatically cancelled
   - Background monitoring thread checks for timeout orders every 30 seconds
   - Configurable timeout duration (default: 5 minutes)
   - Automatic cancellation with notification alerts

3. **Status Tracking**: Comprehensive tracking of order states and retry attempts
   - Failed orders are marked with retry count and error details
   - Timeout cancellations are clearly identified in order history
   - Real-time notifications for retry attempts and timeout events

4. **Error Recovery**: Intelligent error handling and recovery mechanisms
   - Different retry strategies for different types of failures
   - Graceful degradation when maximum retries are reached
   - Detailed error logging for troubleshooting

### Manual Control

```bash
# Disable retry mechanism
ORDER_RETRY_ATTEMPTS=1             # No retries

# Disable timeout cancellation
AUTO_CANCEL_ENABLED=false

# Adjust timeout aggressiveness
AUTO_CANCEL_TIMEOUT=120            # 2 minutes timeout
ORDER_RETRY_DELAY=5                # 5 seconds between retries
```

## QMT Status Code Mappings

The system uses standardized status codes for consistent processing and user-friendly notifications.

### Order Status Codes

Standard QMT order status constants are mapped to Chinese descriptions:

- `48` (ORDER_UNREPORTED): "未报"
- `49` (ORDER_WAIT_REPORTING): "待报"
- `50` (ORDER_REPORTED): "已报"
- `56` (ORDER_SUCCEEDED): "已成交"
- `54` (ORDER_CANCELED): "已撤销"
- `55` (ORDER_PART_SUCC): "部分成交"
- `53` (ORDER_PART_CANCEL): "部分撤销"
- `57` (ORDER_JUNK): "废单"

### Account Status Codes

Account status constants with Chinese descriptions:

- `-1`: "无效" (Invalid)
- `0`: "正常" (Normal/OK)
- `1`: "连接中" (Connecting/Waiting Login)
- `2`: "登录中" (Logging in)
- `3`: "失败" (Failed)
- `4`: "初始化中" (Initializing)
- `5`: "数据刷新校正中" (Data Correcting)
- `6`: "收盘后" (Market Closed)
- `7`: "穿透副链接断开" (Assistant Connection Failed)
- `8`: "系统停用" (System Disabled)
- `9`: "用户停用" (User Disabled)

### Status Processing Strategy

- **Internal Logic**: Uses numeric status codes for precise condition checking
- **Database Storage**: Stores original status codes for data integrity
- **Logging**: Displays format "status_code(description)" for debugging
- **Notifications**: Shows user-friendly Chinese descriptions only
- **Error Detection**: Automatic classification of normal vs error states

## Redis 消息持久化配置

系统支持三种Redis消息模式，提供不同级别的消息可靠性保证。

### 消息模式配置 (.env)

```bash
# Redis消息持久化模式选择
REDIS_MESSAGE_MODE=stream              # 消息模式: pubsub, list, stream (推荐: stream)

# Stream模式配置 (推荐生产环境)
REDIS_STREAM_NAME=trading_signals_stream            # Stream名称
REDIS_CONSUMER_GROUP=trading_service                # 消费者组名称
REDIS_CONSUMER_NAME=consumer1                       # 消费者名称
REDIS_STREAM_MAX_LEN=10000                         # Stream最大长度
REDIS_BLOCK_TIMEOUT=1000                           # 阻塞等待超时(毫秒)

# List模式配置 (简单队列)
REDIS_LIST_NAME=trading_signals_list               # List队列名称

# Pub/Sub模式配置 (向后兼容)
REDIS_SIGNAL_CHANNEL=trading_signals               # 发布订阅频道名称
```

### 模式特性对比

| 模式 | 持久化 | 多消费者 | 顺序保证 | 消息回溯 | 推荐场景 |
|------|--------|----------|----------|----------|----------|
| **Stream** | ✅ | ✅ | ✅ | ✅ | **生产环境推荐** |
| **List** | ✅ | ❌ | ✅ | ❌ | 简单队列场景 |
| **Pub/Sub** | ❌ | ✅ | ❌ | ❌ | 实时通知/向后兼容 |

### Stream模式优势

1. **消息持久化**: 服务重启后消息不丢失
2. **消费者组**: 支持多个消费者协同处理，消息不重复
3. **自动确认**: 处理完成后自动ACK确认消息
4. **消息回溯**: 可从任意位置重新消费消息
5. **故障恢复**: 消费者崩溃重启后继续处理未确认消息

### 使用建议

- **生产环境**: 使用Stream模式，提供最高的消息可靠性
- **开发测试**: 可使用List模式，配置简单
- **兼容性**: 保持Pub/Sub模式支持老版本兼容

### 迁移指南

从Pub/Sub迁移到Stream模式:

1. 在`.env`中设置: `REDIS_MESSAGE_MODE=stream`
2. 配置Stream相关参数（使用默认值即可）
3. 重启交易服务
4. 验证消息处理正常

**注意**: Stream模式首次启动会自动创建消费者组，无需手动干预。
