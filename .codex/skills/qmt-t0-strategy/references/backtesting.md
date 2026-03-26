# T+0 Backtesting

## Goal

Backtesting in this repo is meant to reuse the exact same core signal logic as realtime T+0 generation.

The expected approach is:

- load minute/day data from files
- normalize it into the standard DataFrame format
- replay bars using the pure strategy core
- emit signal/fill logs for later analysis

## Current Files

- `src/backtest/data_loader.py`
- `src/backtest/simulator.py`
- `src/backtest/cli.py`

## Data Format

The loader expects a tabular file with at least:

- `open`
- `high`
- `low`
- `close`
- `volume`

And one datetime-like column named one of:

- `datetime`
- `timestamp`
- `time`
- `date`

Optional fields:

- `amount`
- `pre_close`
- `symbol`

Normalization behavior:

- index becomes `datetime`
- timestamps are localized or converted to `Asia/Shanghai`
- missing `amount` is backfilled as `close * volume`
- missing `pre_close` is derived from previous close

## CLI Usage

Command:

```bash
uv run python main.py t0-backtest \
  --minute-data ./data/minute_601138.parquet \
  --daily-data ./data/daily_601138.parquet \
  --symbol 601138.SH \
  --output-dir ./output/backtest
```

Outputs:

- `signals.csv`
- `fills.csv`
- `summary.json`

## Simulator Behavior

`T0BacktestSimulator` currently:

- computes regime once per run from the supplied daily data
- replays minute bars in order
- calculates a `FeatureSnapshot` on the expanding minute window
- feeds prior fills back into the core as `SignalEvent` history
- updates a `PortfolioState` after each non-observe signal

This is intentionally simple. It is a replay skeleton, not a full exchange-matching engine.

## Constraints

- Keep backtest logic file-driven and pure-python.
- Do not add QMT dependencies to `src/backtest/`.
- Reuse `T0StrategyParams` instead of inventing parallel backtest-only parameter names.
- If you change signal semantics in the core, update backtest tests immediately.

## Good Next Extensions

- richer summary metrics in `summary.json`
- batch replay across multiple trading dates
- alternate fill models like next-bar open
- fee/slippage accounting in simulator outputs
- per-day grouped replay runners
