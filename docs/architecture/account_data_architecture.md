# Account Data Architecture

This project now uses Meta DB as the only persistent store for runtime business data.

## Core Rule

- QMT remains the live broker connection and callback source.
- Meta DB is the only durable store for runtime business history and broker-synced snapshots.
- The CMS/account API reads Meta DB only and does not query QMT directly.

## What Is Stored

- Orders
  - stored in `trading.order_records`
  - updated when orders are submitted, updated, or filled
- Signals
  - stored in `trading.trading_signals`
  - updated when a strategy signal is accepted by the trading engine
- Positions
  - stored in `trading.account_positions`
  - refreshed on trading-engine startup, after filled-trade callbacks, and by a one-time CMS startup bootstrap when no snapshot exists yet
- Trading calendar and stock info
  - stored in Meta DB through the normal service helpers

## What Is Not Stored Frequently

- Market data / quote streams
  - not persisted by this runtime path
- Real-time broker PnL
  - not written to Meta DB
  - operator views should treat it as transient runtime data if needed

## API Behavior

- `/api/positions`
  - reads the broker-synced snapshot in `trading.account_positions`
  - does not query QMT on demand
- `/api/orders`
  - reads `trading.order_records`
- `/api/signals`
  - reads `trading.trading_signals`
- `/api/trades`
  - reads filled rows from `trading.order_records`
- `/api/pnl`
  - derives strategy realized PnL from filled orders in Meta DB
- `/api/account-overview`
  - combines Meta DB policy, Meta DB strategy summary, and optional Meta DB positions

## Update Timing

- Startup
  - after the trading engine connects to QMT, it syncs the full broker position snapshot into Meta DB
- CMS startup bootstrap
  - if the CMS starts and Meta DB still has no position snapshot, it performs one read-only QMT refresh before serving account APIs
- Filled trades
  - after a trade callback, the runtime refreshes the broker position snapshot into Meta DB again
- No quote-driven writes
  - the runtime does not write positions or PnL on every market tick
