# Account Data Architecture

This project now follows a hybrid source-of-truth policy for account data.

## Core Rule

- QMT is the real-time source of truth for live account state.
- Local storage is the source of truth for strategy business history.

## By Data Type

- Positions
  - primary source: QMT live query
  - fallback: local `output/account_positions_snapshot.json`
  - use for: runtime risk checks, available volume, latest holdings

- Orders
  - primary source: local SQLite `order_records`
  - use for: paging, audit, troubleshooting, strategy-side history

- Signals
  - primary source: local SQLite `trading_signals`
  - use for: signal ledger, replay, debugging, attribution

- Trades
  - primary source: local SQLite `order_records`
  - use for: filled-order history and strategy execution review

- Strategy PnL
  - primary source: local SQLite `order_records`
  - use for: realized PnL estimate, daily summary, per-stock attribution

- Account PnL / broker assets
  - primary source: QMT
  - use for: actual broker-side account view

## Why

- Only using local storage makes positions drift after manual trades, restarts, or callback gaps.
- Only using QMT makes it hard to preserve signal lineage, strategy attribution, and audit history.
- The mixed model gives reliable live trading state plus a complete local strategy ledger.

## API Surface

The health/account API now exposes explicit source-policy endpoints:

- `/api/data-policy`
  - returns the source-of-truth policy by data type
- `/api/account-overview`
  - returns policy + live/fallback position snapshot + local strategy daily PnL summary
- `/api/strategy-pnl-summary`
  - returns the local daily strategy summary from `DailyPnLCalculator`

Existing endpoints keep their original responsibilities:

- `/api/positions`
  - live positions, preferring QMT and falling back to cached position snapshot
- `/api/orders`
  - local order ledger
- `/api/signals`
  - local signal ledger
- `/api/trades`
  - local filled-order ledger
- `/api/pnl`
  - local per-stock strategy PnL breakdown
