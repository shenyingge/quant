# Data Source Policy

## Core Principle

The project uses a hybrid source-of-truth model:

- QMT is authoritative for live account state
- local storage is authoritative for strategy business history

This rule should be preserved unless there is a very strong reason to redesign the whole system.

## Why Not QMT For Everything

QMT is the broker-side truth for current holdings and assets, but it is not the best home for:

- strategy signal lineage
- custom order metadata
- business audit trails
- replay and debugging context
- strategy-specific PnL attribution

If you pull everything from QMT, you lose too much application-specific history.

## Why Not SQLite For Everything

Local state alone drifts when:

- manual trades happen in QMT
- the service is restarted mid-session
- callbacks are missed or delayed
- broker state changes outside the app

If you use local storage alone for positions and funds, runtime risk checks become unsafe.

## By Data Type

### Positions

- primary source: QMT live query via `QMTTrader`
- first fallback: local account positions snapshot
- secondary strategy-specific fallback: `PositionSyncer` state for T0 logic

Use for:

- available volume
- latest holdings
- runtime decision support

### Orders

- primary source: local `order_records`

Use for:

- paging in operator UIs
- audit history
- troubleshooting placement and fill lifecycle

### Signals

- primary source: local `trading_signals`

Use for:

- replay and debugging
- strategy attribution
- mapping from external signal to internal order flow

### Trades

- primary source: local `order_records` filtered to filled rows

Use for:

- strategy execution history
- realized-trade review
- local reporting

### Strategy PnL

- primary source: local `DailyPnLCalculator`
- built from local filled order rows

Use for:

- per-stock attribution
- daily summary
- strategy-side realized PnL estimates

### Account PnL / Asset View

- primary source: QMT

Use for:

- actual broker-side account value
- live account inspection

## API Mapping

- `/api/positions`
  - live state endpoint
  - may return fallback-derived data if live QMT is unavailable

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
  - combines policy, strategy summary, and best-effort position snapshot

## Safe Change Rules

- Do not silently switch local-ledger endpoints to QMT just because broker data exists
- Do not silently switch live account endpoints to SQLite just because it is easier
- If you add a fallback, expose that fallback in metadata so operators know what they are seeing
- When in doubt, ask whether the endpoint answers "what is true now?" or "what happened in my strategy history?"
