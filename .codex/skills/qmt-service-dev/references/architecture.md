# Architecture

## Entry Points

- `main.py` is the only CLI entry. It dispatches `run`, `test-run`, `test`, `backup`, `backup-config`, `stock-info`, `calendar`, `pnl-summary`, `export-daily`, `t0-strategy`, `t0-daemon`, `t0-sync-position`, `t0-backtest`, `cms-check`, and `cms-server`.
- `run` and `test-run` both end up in `run_service()`, which creates `TradingService` and manages startup retries.
- Trading-day gating happens before the service loop unless test mode is enabled.
- `cms-server` runs independently of the trading and strategy engines and should be treated as a separate always-on operator service.

## Runtime Graph

- `TradingService` is the orchestrator.
- `QuoteStreamService` is the Redis-driven QMT quote subscription worker hosted by `TradingService`.
- `ProjectCmsChecker` builds standardized CMS snapshots.
- `CmsSnapshotStore` refreshes CMS data in the background so `/health` returns cached snapshots quickly.
- `RedisSignalListener` receives messages from Redis.
- `QMTTrader` submits orders and exposes order health/status helpers.
- `FeishuNotifier` sends operator notifications.
- `DatabaseBackupService` schedules backup jobs.
- `schedule.Scheduler` inside `TradingService` sends the daily PnL summary.
- `trading_calendar_manager` initializes and refreshes cached trading days.

## Signal Lifecycle

1. Redis message arrives in `RedisSignalListener`.
2. `TradingService._handle_trading_signal()` normalizes field aliases to the service schema:
   `signal_id`, `stock_code`, `direction`, `volume`, optional `price`.
3. The service checks required fields and deduplicates on `TradingSignal.signal_id`.
4. The signal is persisted into `trading_signals`.
5. A Feishu "signal received" notification is sent.
6. The order is submitted asynchronously through `QMTTrader.place_order_async()`.
7. Callback code writes `order_records`, updates signal state, and sends success or error notifications.
   Trade callbacks must also persist standalone Meta DB records for fills that arrive without a pre-existing `order_records` row, such as manual QMT orders or callbacks whose raw order id is unusable.
8. `_monitor_orders()` polls pending orders every 30 seconds and fills in final status, fill quantity, price, and timeout-cancel metadata.

## Persistence Model

- `TradingSignal`: inbound signal record, dedupe key, processed flag, error message.
- `OrderRecord`: order id, stock code, direction, requested volume/price, fill stats, final status, error message.
- `TradingCalendar`: cached trading-day lookup table used by trading-day checks.
- `StockInfo`: stock name/cache table used in notifications and summaries.
- `AccountPosition`: broker-synced position snapshot in Meta DB. CMS-side unrealized PnL is derived from this table, not from `order_records`.

## Important Behavior

- Auto reconnect is optional but enabled by default through `ConnectionManager` and `MultiConnectionManager`.
- Redis supports multiple message modes via config, but service changes should preserve the configured mode instead of assuming pub/sub only.
- `TradingService.start()` blocks in `start_listening()`. Background work runs on threads.
- Quote streaming is separate from order ingestion: the CMS server writes desired symbols into Redis, and the trading engine owns the live QMT quote subscription lifecycle.
- Latest quote snapshots are intentionally kept in Redis on shutdown; freshness comes from timestamps in the payload, not from deleting Redis keys.
- Order monitoring relies on QMT status semantics from `src/qmt_constants.py`; do not replace them with ad hoc string comparisons.
- Feishu fill notifications are not a substitute for persistence. If the engine receives a fill callback, Meta DB should be updated even when the order was entered manually outside the service.
- `/api/pnl` is now split by accounting purpose: `realized` comes from the Meta DB execution ledger (`order_records`), while `unrealized` comes from the Meta DB broker position snapshot (`account_positions`).

## High-Risk Files

- `src/trader.py`: broker connectivity and actual order placement.
- `src/trading_service.py`: orchestration, callbacks, retry behavior, monitoring, notifications.
- `src/redis_listener.py`: message parsing, delivery guarantees, Redis mode behavior.
- `src/config.py`: environment contract for the rest of the repo.
- `src/cms_server.py`: standalone CMS endpoint, cached snapshot refresh loop, and process-level checks.
- `src/quote_stream_service.py`: Redis-controlled QMT quote subscription loop and quote normalization.
- `src/database.py`: tables used by live workflows and operator tooling.
- `src/daily_exporter.py`: end-of-day positions and trades export flow.
