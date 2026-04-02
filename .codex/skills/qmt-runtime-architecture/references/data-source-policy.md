# Data Source Policy

## Core Principle

The project uses a broker-source plus Meta DB persistence model:

- QMT is authoritative at ingest time for broker account state and trade callbacks
- Meta DB is authoritative for persisted strategy history and broker-synced snapshots

This rule should be preserved unless there is a very strong reason to redesign the whole system.

## Why Not QMT For Everything

QMT is the broker-side truth for current holdings and assets, but it is not the best home for:

- strategy signal lineage
- custom order metadata
- business audit trails
- replay and debugging context
- strategy-specific PnL attribution

If you pull everything from QMT, you lose too much application-specific history.

## By Data Type

### Positions

- primary source for persistence: Meta DB `account_positions`
- update trigger: trading-engine startup and filled-trade callbacks
- ingest source: QMT via `QMTTrader`

Use for:

- available volume
- latest holdings
- API-side account inspection without live broker coupling

### Orders

- primary source: Meta DB `order_records`

Use for:

- paging in operator UIs
- audit history
- troubleshooting placement and fill lifecycle

### Signals

- primary source: Meta DB `trading_signals`

Use for:

- replay and debugging
- strategy attribution
- mapping from external signal to internal order flow

### Trades

- primary source: Meta DB `order_records` filtered to filled rows

Use for:

- strategy execution history
- realized-trade review
- local reporting

### Strategy PnL

- primary source: Meta DB `DailyPnLCalculator`
- built from Meta DB filled order rows

Use for:

- per-stock attribution
- daily summary
- strategy-side realized PnL estimates

### Account PnL / Asset View

- primary source: transient QMT runtime queries when explicitly needed
- not persisted as a high-frequency ledger

Use for:

- actual broker-side account value
- live operator checks outside the core CMS/account API

## API Mapping

- `/api/positions`
  - Meta DB snapshot endpoint
  - should not query QMT directly

- `/api/orders`
  - local ledger

- `/api/signals`
  - local ledger

- `/api/trades`
  - local ledger

- `/api/pnl`
  - local strategy PnL breakdown

- `/api/strategy-pnl-summary`
  - local daily strategy summary

- `/api/data-policy`
  - explains the policy itself

- `/api/account-overview`
  - combines policy, strategy summary, and the Meta DB position snapshot

## Safe Change Rules

- Do not silently switch Meta DB ledger endpoints back to QMT just because broker data exists
- Do not add quote-driven high-frequency writes for positions or PnL without an explicit architecture change
- Keep API reads broker-decoupled so QMT outages do not take down the CMS/account server
- When in doubt, ask whether the data should be persisted business history or transient broker runtime state
