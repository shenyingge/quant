---
name: qmt-service-dev
description: "Understand, modify, or debug the QMT automated trading service in this repository. Use when working on main.py, src/trading_service.py, src/trader.py, Redis signal ingestion, QMT order execution, scheduled jobs, notifications, configuration, or Windows task operations."
---

# QMT Service Dev

Use this skill for the live service layer rather than strategy-rule work.

## Start Here

- `main.py`
- `src/trading_service.py`
- `src/trader.py`
- `src/redis_listener.py`
- `src/config.py`
- `scripts/`

## Working Rules

- Trace behavior from CLI entrypoints before changing internals.
- Treat QMT connectivity and order placement as high-risk changes.
- Preserve field normalization and deduplication in trading-signal ingestion.
- Keep startup, retry, scheduler, and shutdown behavior safe for Windows task execution.

## Related Docs

- `CLAUDE.md`
- `README.md`
- `docs/daily_export.md`
