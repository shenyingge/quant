---
name: qmt-broker-data
description: "Understand, extend, or debug the broker abstraction, data manager, market-data normalization, and daily export workflows in this repository. Use when working on src/broker, src/data_manager, src/market_data, src/daily_exporter.py, docs/unified_broker_guide.md, or docs/market_data_format.md."
---

# QMT Broker Data

Use this skill when the task is about broker-facing contracts or strategy-facing data, not the main service loop.

## Start Here

- `src/broker/`
- `src/data_manager/`
- `src/market_data/`          # high-frequency realtime ingestion (tick / snapshot)
- `src/daily_exporter.py`
- `docs/unified_broker_guide.md`
- `docs/market_data_format.md`
- `docs/daily_export.md`

## Working Rules

- Preserve the broker abstraction instead of adding direct environment-specific branching across the codebase.
- Keep symbol format, timestamp handling, and normalized DataFrame columns consistent.
- Keep export behavior backward compatible where possible, especially CSV fields and Redis payload shape.
- Avoid making Redis export failures fatal unless the user asks for stricter guarantees.
