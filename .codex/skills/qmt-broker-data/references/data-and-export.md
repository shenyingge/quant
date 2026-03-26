# Data And Export

## Strategy-Facing Market Data

- The documented standard input shape is a pandas DataFrame indexed by datetime.
- Expected core columns:
  `open`, `high`, `low`, `close`, `volume`, `amount`.
- Optional fields documented in `docs/market_data_format.md` include:
  `pre_close`, `high_limit`, `low_limit`, `turnover_rate`, `pe_ratio`, `pb_ratio`.
- Strategy callbacks are expected to receive normalized data instead of raw QMT payloads.

## Time And Symbol Conventions

- Use Beijing market hours semantics for A-share workflows.
- Keep timestamps explicit and consistent; market-data docs assume `YYYY-MM-DD HH:MM:SS`.
- Broker/data docs use symbols such as `000001.SZ` and `600036.SH`.
- Service signal ingestion is different: it uses `stock_code` and may arrive without exchange suffix. Do not conflate the two contracts accidentally.

## Data Manager Surface

- `src/data_manager/` exposes:
  `MarketDataStorage`, `DataDownloader`, `DataValidator`, `StockUniverse`.
- Use this package when the task is about historical/market dataset lifecycle rather than live order execution.

## Daily Export Behavior

- `src/daily_exporter.py` exports to `data/daily_export/`.
- `export_positions()` writes `positions_YYYYMMDD.csv`.
- `export_trades()` writes `trades_YYYYMMDD.csv`.
- `export_all()` connects to QMT, tries Redis, exports both datasets, then disconnects.

## Redis Export Contract

- Key prefix is `daily_export`.
- Position key: `daily_export:positions:YYYYMMDD`
- Trade key: `daily_export:trades:YYYYMMDD`
- TTL is 7 days.
- Redis payloads are JSON with `ensure_ascii=False`.
- Existing keys are deleted before writing fresh data for the same day.

## Export Invariants

- CSV files are encoded with `utf-8-sig`.
- Redis failure should not block CSV export.
- Position payload includes `trade_date`, `stock_code`, volume fields, pricing, market value, and floating profit metrics.
- Trade payload includes `trade_date`, `order_id`, `stock_code`, order/trade quantities, price fields, raw order status, and `status_desc`.

## Where To Read Next

- `docs/market_data_format.md` for the intended normalized DataFrame contract.
- `docs/daily_export.md` for operator-facing export expectations.
- `src/daily_exporter.py` for the actual CSV and Redis payload logic.
