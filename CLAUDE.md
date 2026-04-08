# CLAUDE.md

This file provides guidance to coding agents working in this repository.

## Project Overview

This repository is now a pure QMT trading engine.

Only two runtime chains are in scope:

1. `QMT quote -> Redis publish`
2. `Redis order signal -> QMT order execution`

The repository scope is intentionally limited to the live trading engine, quote publishing, health checks, and related operations.

## Effective Entrypoints

Preferred operator entrypoints:

```bash
make                      # default entrypoint, starts watchdog
make watchdog-bg          # background watchdog
make trading-engine       # direct trading engine
make trading-engine-bg    # background trading engine
make trading-engine-test  # non-trading-day test mode
make cms-check            # health snapshot
make cms-server           # standalone CMS
```

Direct CLI entrypoints that still exist:

```bash
uv run python main.py run
uv run python main.py test-run
uv run python main.py test
uv run python main.py cms-check
uv run python main.py cms-server
uv run python main.py watchdog
uv run python main.py sync-account-positions
uv run python main.py export-minute-history --trade-date today --listed-only
uv run python main.py export-minute-daily
uv run python main.py ingest-minute-history
uv run python main.py ingest-minute-daily
```

Notes:

- `make` defaults to `watchdog`
- `make watchdog` and `make watchdog-bg` guard against duplicate watchdog startup
- `python main.py run` is a low-level direct engine entrypoint, not the default production operator flow

## Architecture

Key runtime components:

1. `main.py`
   - single CLI entrypoint
2. `src/trading/runtime/engine.py`
   - trading engine runtime
3. `src/trading/execution/qmt_trader.py`
   - QMT order execution and callbacks
4. `src/infrastructure/redis/signal_listener.py`
   - Redis signal consumption
5. `src/market_data/`
   - quote ingestion and Redis publishing
6. `src/infrastructure/runtime/cms_server.py`
   - CMS health snapshot and HTTP service
7. `src/infrastructure/runtime/watchdog_service.py`
   - long-running process supervision
8. `src/infrastructure/db/`
   - Meta DB models and session management
9. `src/infrastructure/config/__init__.py`
   - settings and environment variables

Current watchdog target inventory:

- `cms-server`
- `trading_engine`
- `minute_history_ingest_daily`

Current CMS `/health` focus:

- trading day
- database
- Redis
- QMT client process
- trading engine process
- watchdog process

## Runtime Data Rules

- QMT is the live broker dependency and is not auto-launched by this repo
- Redis is the transport layer for order signals and quote publishing
- Meta DB is the durable runtime source of truth for orders, signals, positions, and fills
- CMS and account-facing views should read Meta DB rather than querying QMT on demand

## Development Commands

```bash
uv sync
uv run pytest
uv run pytest --cov=src --cov-report=term-missing
```

Useful targeted checks:

```bash
make help
make cms-check
uv run pytest tests/integration/test_trading_engine_signal_flow.py -q
```

## Testing Expectations

- Prefer unit tests for local logic changes
- Add integration tests for cross-component behavior
- Semi-real integration testing is allowed:
  - real Redis
  - real Meta DB
  - mock QMT
- The reference end-to-end simulated trading flow test is:
  - `tests/integration/test_trading_engine_signal_flow.py`

## Constraints

- Keep repository guidance and runtime entrypoints aligned with the pure trading-engine scope
- Keep `main.py` as the single entrypoint and avoid moving business logic into it
- Use absolute imports from `src.*`
- Keep configuration in `src/infrastructure/config/` and `.env`
- When changing public commands, docs, or interfaces, update tests and docs together
