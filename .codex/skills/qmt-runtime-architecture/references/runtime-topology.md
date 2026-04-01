# Runtime Topology

## Scope

This reference describes the runtime architecture for the `quant` service layer after the watchdog and account-data refactor.

It is the right starting point when you need to answer:

- which processes are expected to run 24x7
- which components are trading-day only
- how the health/account API is started
- where account data is sourced from

## Main Runtime Roles

- `main.py run`
  - trading engine
  - long-running, trading-day bounded
  - receives signals, places orders, monitors order state, writes local ledger rows

- `main.py t0-daemon`
  - T0 strategy engine
  - long-running, trading-day bounded
  - produces runtime signal-card output and strategy-side state

- `main.py health-server`
  - standalone HTTP health/account API server
  - intended to be always on
  - exposes `/health`, `/healthz`, `/api/*`, and `/ws`

- `main.py watchdog`
  - 24x7 process supervisor
  - always on
  - starts or stops expected services based on trading-day and time-window policy

- `main.py t0-sync-position`
  - one-shot task
  - expected once per trading day
  - synchronizes T0 strategy position state from QMT to local snapshot

- `main.py sync-meta-db`
  - one-shot task
  - expected once per trading day
  - copies local trading tables into the Meta DB target

## Process Graph

1. Windows startup task launches `scripts/start_watchdog_service.ps1`
2. That script runs `python main.py watchdog`
3. The watchdog checks trading-day and process windows
4. The watchdog ensures `health-server` stays alive all day
5. On trading days, the watchdog starts `trading_engine` and `strategy_engine` in their expected windows
6. At the configured once-per-day times, the watchdog triggers `t0-sync-position` and `sync-meta-db`
7. Operators and dashboards query `health-server` for system health and account-facing data

## Code Entry Points

- CLI dispatch: `main.py`
- watchdog runtime: `src/watchdog_service.py`
- health/account API: `src/healthcheck.py`
- account data policy and retrieval: `src/account_data_service.py`
- trading engine: `src/trading_engine.py`
- broker integration: `src/trader.py`
- strategy position cache: `src/strategy/position_syncer.py`

## Architectural Boundaries

- `watchdog_service.py`
  - responsible for process lifecycle expectations
  - not responsible for business semantics of orders or PnL

- `healthcheck.py`
  - responsible for HTTP/WebSocket request handling and system health snapshots
  - should delegate account-data sourcing decisions instead of embedding them everywhere

- `account_data_service.py`
  - responsible for source-of-truth decisions and normalized account-data reads
  - acts as the policy layer between API handlers and underlying QMT/SQLite/cache sources

- `trader.py`
  - responsible for live QMT session lifecycle and broker reads/writes
  - should remain the live broker adapter, not the sole home for API response assembly

## Startup Variants

Two startup modes matter for the API stack:

- background-thread mode
  - `start_healthcheck_server(...)`
  - used when another process wants to host the server internally

- standalone process mode
  - `serve_healthcheck(...)`
  - used by `main.py health-server`
  - must wire the same handler dependencies as background-thread mode

Any endpoint or WebSocket change should be checked against both startup variants.
