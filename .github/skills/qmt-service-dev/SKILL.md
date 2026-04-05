---
name: qmt-service-dev
description: "Understand, modify, or debug the QMT automated trading service in this repository. Use when working on main.py, src/trading_service.py, src/trading/execution/qmt_trader.py, Redis signal ingestion, QMT order execution, scheduled jobs, notifications, configuration, or Windows task operations."
---

# QMT Service Dev

Use this skill for the live service layer rather than strategy-rule work.

## Start Here

- `main.py`
- `src/trading_service.py`
- `src/trading/execution/qmt_trader.py`  (canonical; `src/trader.py` is a compat wrapper)
- `src/infrastructure/redis/signal_listener.py`  (canonical; `src/redis_listener.py` is a compat wrapper)
- `src/trading/runtime/engine.py`  (canonical; `src/trading_engine.py` is a compat wrapper)
- `src/config.py`
- `scripts/`

## Working Rules

- Trace behavior from CLI entrypoints before changing internals.
- Treat QMT connectivity and order placement as high-risk changes.
- Preserve field normalization and deduplication in trading-signal ingestion.
- Keep startup, retry, scheduler, and shutdown behavior safe for Windows task execution.
- New imports should target canonical paths (`src/trading/...`, `src/infrastructure/...`), not the compat wrappers in `src/`.

## Related Docs

- `CLAUDE.md`
- `README.md`
- `docs/daily_export.md`
