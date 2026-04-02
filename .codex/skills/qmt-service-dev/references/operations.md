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
- Print a one-shot CMS snapshot: `uv run python main.py cms-check`
- Run the standalone CMS HTTP service: `uv run python main.py cms-server`

## Key Environment Variables

- Redis: `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_MESSAGE_MODE`, `REDIS_SIGNAL_CHANNEL`, `REDIS_STREAM_NAME`, `REDIS_CONSUMER_GROUP`
- QMT: `QMT_SESSION_ID`, `QMT_PATH`, `QMT_ACCOUNT_ID`, `QMT_ACCOUNT_TYPE`
- Order behavior: `ORDER_TIMEOUT_SECONDS`, `ORDER_SUBMIT_TIMEOUT`, `ORDER_RETRY_ATTEMPTS`, `ORDER_RETRY_DELAY`, `AUTO_CANCEL_ENABLED`, `AUTO_CANCEL_TIMEOUT`
- Notifications: `FEISHU_WEBHOOK_URL`
- Service recovery: `AUTO_RECONNECT_ENABLED`, `RECONNECT_MAX_ATTEMPTS`, `RECONNECT_INITIAL_DELAY`, `RECONNECT_MAX_DELAY`, `RECONNECT_BACKOFF_FACTOR`, `HEALTH_CHECK_INTERVAL`
- CMS service: `CMS_SERVER_HOST`, `CMS_SERVER_PORT`, `CMS_SERVER_TIMEOUT_SECONDS`, `CMS_SERVER_REFRESH_INTERVAL_SECONDS`
- Quote stream: `QUOTE_STREAM_ENABLED`, `QUOTE_STREAM_PERIOD`, `QUOTE_STREAM_RECONCILE_INTERVAL_SECONDS`, `REDIS_QUOTE_STREAM_CHANNEL`, `REDIS_QUOTE_SUBSCRIPTIONS_KEY`, `REDIS_QUOTE_CONTROL_CHANNEL`, `REDIS_QUOTE_LATEST_PREFIX`, `REDIS_QUOTE_LATEST_TTL_SECONDS`
- Trading-day behavior: `TRADING_DAY_CHECK_ENABLED`, `TEST_MODE_ENABLED`
- Backup/logging: `BACKUP_ENABLED`, `BACKUP_TIME`, `BACKUP_DIR`, `LOG_LEVEL`, `LOG_DIR`, `LOG_ARCHIVE_DIR`, `LOG_FILE`, `LOG_ROTATION`, `LOG_RETENTION`, `LOG_COMPRESSION`

## Logs And State

- Active process logs usually live under `logs/current/`.
- Rolled and compressed archives usually live under `logs/archive/<role>/`.
- Scheduled-task wrapper logs usually land in `logs/task_execution_trading.log`, `logs/task_execution_t0_daemon.log`, or `logs/task_execution_t0_sync.log`.
- The standalone CMS service usually logs through the main process logger and listens on `http://127.0.0.1:8780/health` unless overridden by env.
- The latest quote cache lives in Redis under `REDIS_QUOTE_LATEST_PREFIX*`; default operation keeps the last payload across restarts and uses timestamps in the payload to judge freshness.
- Runtime persistence uses Meta DB directly.
- Daily export output goes to `data/daily_export/`.
- Runtime T+0 snapshots are written under `output/` and should be treated as generated local state.
- If a manual QMT order filled while the engine was on an older build or missed persistence, you can safely backfill `order_records` by querying QMT orders/trades in a read-only session and inserting the corresponding Meta DB row afterward.

## Scheduled Operation

- Windows task helpers are in `scripts/`.
- `scripts/register_watchdog_service_task.ps1` is the primary repo-level automation entrypoint.
- `scripts/run_console.bat` is the main manual Windows execution path.
- Scheduled-task and watchdog-managed services now launch `python main.py ...` directly.
- `scripts/start_cms_service.bat` remains as a manual helper for the standalone CMS service.
- `scripts/setup_minute_history_task.bat` remains as the separate installer for the optional minute-history export task.

## Safe Testing

- Safe to run locally: config inspection, calendar tooling, backup config, most pure-Python unit tests.
- Potentially unsafe: QMT connectivity tests, `test_passorder.py`, async/concurrent trading tests, stress tests, and anything that submits or monitors real orders.
- Assume `src/trader.py` talks to a real client unless the user explicitly states a simulated account or isolated environment.

## Common Failure Points

- QMT client not started or not logged in.
- Wrong `QMT_SESSION_ID`, `QMT_PATH`, or account id.
- Redis unavailable or wrong message-mode config.
- Redis quote keys are part of the live quote pipeline; do not clear them during normal stop/restart troubleshooting unless you intentionally want to reset frontend subscription demand.
- Keep PnL terminology straight during debugging: `realized` should follow `order_records`, while `unrealized` should follow `account_positions`. If one side looks wrong, inspect the underlying table before changing formulas.
- Running on a non-trading day with trading-day checks still enabled.
- Windows terminal encoding issues; `main.py` explicitly reconfigures UTF-8 behavior on Windows.
- Proxy settings on Windows may interfere with `urllib`-style localhost checks; use direct socket or browser/curl validation when testing `127.0.0.1:8780`.
