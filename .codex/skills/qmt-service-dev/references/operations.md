# Operations

## Core Commands

- Install dependencies: `uv sync`
- Start service: `uv run python main.py run`
- Start in test mode on non-trading days: `uv run python main.py test-run`
- Test infrastructure connectivity: `uv run python main.py test`
- Manual backup: `uv run python main.py backup`
- Show backup config: `uv run python main.py backup-config`
- Manage stock cache: `uv run python main.py stock-info`
- Manage trading calendar: `uv run python main.py calendar`
- Send daily summary manually: `uv run python main.py pnl-summary`
- Export daily holdings and trades: `uv run python main.py export-daily`
- Run T+0 once: `uv run python main.py t0-strategy`
- Run T+0 daemon: `uv run python main.py t0-daemon`
- Sync T+0 position: `uv run python main.py t0-sync-position`
- Run file-driven T+0 backtest: `uv run python main.py t0-backtest --minute-data minute.csv --daily-data daily.csv`
- Print a one-shot health snapshot: `uv run python main.py health-check`
- Run the standalone health HTTP service: `uv run python main.py health-server`

## Key Environment Variables

- Redis: `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_MESSAGE_MODE`, `REDIS_SIGNAL_CHANNEL`, `REDIS_STREAM_NAME`, `REDIS_CONSUMER_GROUP`
- QMT: `QMT_SESSION_ID`, `QMT_PATH`, `QMT_ACCOUNT_ID`, `QMT_ACCOUNT_TYPE`
- Order behavior: `ORDER_TIMEOUT_SECONDS`, `ORDER_SUBMIT_TIMEOUT`, `ORDER_RETRY_ATTEMPTS`, `ORDER_RETRY_DELAY`, `AUTO_CANCEL_ENABLED`, `AUTO_CANCEL_TIMEOUT`
- Notifications: `FEISHU_WEBHOOK_URL`
- Service recovery: `AUTO_RECONNECT_ENABLED`, `RECONNECT_MAX_ATTEMPTS`, `RECONNECT_INITIAL_DELAY`, `RECONNECT_MAX_DELAY`, `RECONNECT_BACKOFF_FACTOR`, `HEALTH_CHECK_INTERVAL`
- Health service: `HEALTHCHECK_HOST`, `HEALTHCHECK_PORT`, `HEALTHCHECK_TIMEOUT_SECONDS`, `HEALTHCHECK_REFRESH_INTERVAL_SECONDS`
- Trading-day behavior: `TRADING_DAY_CHECK_ENABLED`, `TEST_MODE_ENABLED`
- Backup/logging: `BACKUP_ENABLED`, `BACKUP_TIME`, `BACKUP_DIR`, `LOG_LEVEL`, `LOG_FILE`

## Logs And State

- Main log file is usually `logs/trading_service.log`.
- Scheduled-task wrapper logs usually land in `logs/task_execution_trading.log`, `logs/task_execution_t0_daemon.log`, or `logs/task_execution_t0_sync.log`.
- The standalone health service usually logs through the main process logger and listens on `http://127.0.0.1:8780/health` unless overridden by env.
- SQLite DB defaults to `trading.db`.
- Daily export output goes to `data/daily_export/`.
- Runtime T+0 snapshots are written under `output/` and should be treated as generated local state.

## Scheduled Operation

- Windows task helpers are in `scripts/`.
- `scripts/setup_task_simple.bat` is the primary repo-level automation entrypoint.
- `scripts/setup_t0_tasks.bat` manages the T+0 scheduled tasks.
- `scripts/run_console.bat`, `scripts/task_runner.ps1`, and the `task_wrapper_*.bat` files are the main Windows execution path.
- `scripts/register_healthcheck_service_task.ps1` registers the 24x7 startup task `Quant_Healthcheck_Service`.
- `scripts/start_healthcheck_service.ps1` and `scripts/start_healthcheck_service.bat` launch the standalone health service.
- `scripts/task_runner.sh` and `scripts/load_env.sh` remain relevant for older shell-based environments.

## Safe Testing

- Safe to run locally: config inspection, calendar tooling, backup config, most pure-Python unit tests.
- Potentially unsafe: QMT connectivity tests, `test_passorder.py`, async/concurrent trading tests, stress tests, and anything that submits or monitors real orders.
- Assume `src/trader.py` talks to a real client unless the user explicitly states a simulated account or isolated environment.

## Common Failure Points

- QMT client not started or not logged in.
- Wrong `QMT_SESSION_ID`, `QMT_PATH`, or account id.
- Redis unavailable or wrong message-mode config.
- Running on a non-trading day with trading-day checks still enabled.
- Windows terminal encoding issues; `main.py` explicitly reconfigures UTF-8 behavior on Windows.
- Proxy settings on Windows may interfere with `urllib`-style localhost checks; use direct socket or browser/curl validation when testing `127.0.0.1:8780`.
