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

# Run with Windows batch script
scripts\run_console.bat

# Test mode (skip trading day check)
uv run python main.py test-run

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

### Signal Processing Flow

1. Redis publishes trading signal to configured channel
2. RedisSignalListener receives and validates JSON signal
3. Signal saved to SQLite database via SQLAlchemy
4. Trader executes order through QMT passorder API
5. Order status monitored with callbacks
6. Notifications sent to Feishu for key events
7. Database updated with order results

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

- **Redis**: REDIS_HOST, REDIS_PORT, REDIS_SIGNAL_CHANNEL
- **QMT**: QMT_SESSION_ID, QMT_PATH, QMT_ACCOUNT_ID
- **Notifications**: FEISHU_WEBHOOK_URL, FEISHU_SECRET
- **Trading**: ORDER_TIMEOUT_SECONDS, AUTO_CANCEL_ENABLED
- **Backup**: BACKUP_ENABLED, BACKUP_TIME, BACKUP_DIR

### Windows Service Integration

The system can run as a Windows scheduled task using scripts in the `scripts/` directory:
- `setup_task.bat`: Creates scheduled task for daily automated trading
- `task_runner.sh`: MINGW64 runner script for the scheduled task
- Session ID auto-detection for QMT connection

### Important Considerations

1. **Environment**: Requires MINGW64/MSYS2 for proper UTF-8 handling on Windows
2. **QMT Session**: Must have QMT client running and logged in before starting service
3. **Real Trading**: passorder tests will execute real orders - use test accounts
4. **Concurrent Orders**: System handles multiple simultaneous trading signals
5. **Error Recovery**: Automatic retry logic for connection failures
6. **Trading Days**: Uses akshare to fetch and cache trading calendar in database
   - Automatically checks if current day is a trading day before starting
   - Use `python main.py test-run` to run on non-trading days for testing
   - Set `TEST_MODE_ENABLED=true` in .env to permanently enable test mode
   - Calendar auto-updates in December for next year
7. **QMT Constants**: Uses xtconstant enumeration values instead of hardcoded strings
   - Order statuses, operation types, and price types use standard QMT constants
   - See src/qmt_constants.py for mappings and utility functions
   - Avoids hardcoded Chinese strings like "已成交", "已撤销" etc.