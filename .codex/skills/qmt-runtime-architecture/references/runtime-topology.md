# Runtime Topology

## Scope

This reference describes the runtime architecture for the `quant` service layer after the watchdog and account-data refactor.

It is the right starting point when you need to answer:

- which processes are expected to run 24x7
- which components are trading-day only
- how the CMS/account API is started
- where account data is sourced from

## Main Runtime Roles

- `main.py run`
  - trading engine
  - long-running, trading-day bounded
  - receives signals, places orders, monitors order state, writes Meta DB ledger rows
  - hosts the Redis-driven QMT quote subscription loop that feeds CMS WebSocket quotes

- `main.py t0-daemon`
  - T0 strategy engine
  - long-running, trading-day bounded
  - produces runtime signal-card output and strategy-side state

- `main.py cms-server`
  - standalone HTTP CMS/account API server
  - intended to be always on
  - exposes `/health`, `/healthz`, `/api/*`, and `/ws`

- `main.py watchdog`
  - 24x7 process supervisor
  - always on
  - starts or stops expected services based on trading-day and time-window policy

- `main.py t0-reconcile`
  - one-shot task
  - expected once per trading day
  - validates T0 position and filled-trade consistency across QMT, Meta DB, and local strategy state

## Process Graph

1. Windows startup task launches `python main.py watchdog` directly
2. The watchdog checks trading-day and process windows
3. The watchdog ensures `cms-server` stays alive all day
4. On trading days, the watchdog starts `trading_engine` and `strategy_engine` in their expected windows
5. At the configured once-per-day time, the watchdog triggers `t0-reconcile`
6. Operators and dashboards query `cms-server` for system health, account-facing data, and WebSocket quotes
7. Frontend quote subscriptions flow through Redis to the trading engine; latest quote snapshots stay in Redis across process restarts and are judged by timestamp rather than stop-time cleanup

## Code Entry Points

- CLI dispatch: `main.py`
- watchdog runtime: `src/watchdog_service.py`
- CMS/account API: `src/cms_server.py`
- account data policy and retrieval: `src/account_data_service.py`
- trading engine: `src/trading_engine.py`
- broker integration: `src/trader.py`
- strategy position cache: `src/strategy/position_syncer.py`

## Architectural Boundaries

- `watchdog_service.py`
  - responsible for process lifecycle expectations
  - not responsible for business semantics of orders or PnL

- `cms_server.py`
  - responsible for HTTP/WebSocket request handling and CMS snapshots
  - should delegate account-data sourcing decisions instead of embedding them everywhere

- `account_data_service.py`
  - responsible for source-of-truth decisions and normalized account-data reads
  - acts as the policy layer between API handlers and underlying Meta DB snapshots and ledgers

- `trader.py`
  - responsible for live QMT session lifecycle and broker reads/writes
  - should remain the live broker adapter, not the sole home for API response assembly

## Startup Variants

Two startup modes matter for the API stack:

- background-thread mode
  - `start_cms_server(...)`
  - used when another process wants to host the server internally

- standalone process mode
  - `serve_cms_server(...)`
  - used by `main.py cms-server`
  - must wire the same handler dependencies as background-thread mode

Any endpoint or WebSocket change should be checked against both startup variants.
