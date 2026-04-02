---
name: qmt-service-dev
description: Understand, modify, or debug the QMT automated trading service in this repository. Use when working on `main.py`, `src/trading_service.py`, `src/trading_engine.py`, `src/cms_server.py`, `src/quote_stream_service.py`, Redis signal ingestion, QMT order execution, `.env` or `src/config.py`, notifications, backups, trading-day checks, Meta DB persistence, CMS endpoints, or Windows task based operations and troubleshooting.
---

# QMT Service Dev

Use this skill to onboard quickly to the live service layer of this repo.

Start by reading [references/architecture.md](references/architecture.md) for the runtime graph and [references/operations.md](references/operations.md) for commands, environment variables, logs, and safety constraints.

## Workflow

1. Identify whether the task is about startup, signal handling, order lifecycle, configuration, notifications, scheduled jobs, or production troubleshooting.
2. Trace the CLI entry in `main.py` before editing internals. Most user-facing behavior starts there.
3. For service changes, follow the path `main.py` -> `TradingService` -> `RedisSignalListener` / `QMTTrader` / database models instead of changing one file in isolation.
4. For config changes, add or update the field in `src/config.py`, then confirm every call site and any `.env.example` implications.
5. For operational questions, prefer logs, command entrypoints, the health endpoint, and the scheduler scripts before touching trading logic.

## Safety Rules

- Treat QMT connectivity and order-placement tests as potentially real trading activity.
- Do not run `test_passorder.py`, concurrent trading tests, or stress tests unless the user explicitly wants live or simulated order execution.
- Preserve signal idempotency. `TradingSignal.signal_id` is unique and duplicates are intentionally skipped.
- Preserve field normalization in `_handle_trading_signal`; upstream publishers may send aliases like `symbol`, `side`, or `quantity`.
- Keep service-stop behavior safe. `stop()` is used during normal shutdown and exception cleanup.

## Editing Guidance

- Prefer incremental edits around `TradingService` because it coordinates backup scheduling, daily PnL summary, calendar setup, order monitoring, and connection recovery.
- When changing order-state logic, check both `src/qmt_constants.py` and `_monitor_orders()` so notification behavior stays aligned with QMT status codes.
- When changing persistence, inspect `src/database.py` first; the service relies on `trading_signals`, `order_records`, `trading_calendar`, and `stock_info`.
- When changing startup or operator workflows, inspect `scripts/` and `main.py` together.
- For quote-stream changes, trace the full path `cms_server WebSocket` -> `Redis quote subscription keys/channels` -> `quote_stream_service` -> `xtdata.subscribe_quote()`.
- When changing the `/health` endpoint or its scheduled-task wrapper, inspect `src/cms_server.py`, `main.py`, and `scripts/start_cms_service.*` together.

## References

- `references/architecture.md`: runtime structure, data flow, persistence, and high-risk edit points.
- `references/operations.md`: commands, env vars, logs, scheduled tasks, and safe testing guidance.
