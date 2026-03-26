# Quant Repo Instructions

This repository mixes three different concerns that should stay separated when making changes:

1. Live trading service and operations.
2. Broker and market-data abstractions.
3. T+0 strategy core and backtesting.

## Architectural Rules

- Keep strategy logic pure where possible. Files under `src/strategy/core/` must not depend on QMT SDKs, Redis, SQLAlchemy sessions, or notification code.
- Treat `src/strategy/core/models.py` as the typed contract for strategy-side code. Prefer `FeatureSnapshot`, `PortfolioState`, `StrategyDecision`, `SignalCard`, and related typed models over ad hoc dicts when adding new logic.
- Keep the runtime dependency direction explicit:
  adapters/repositories -> strategy core -> persistence/notification/output adapters.
- Do not move business rules from `src/strategy/core/engine.py` into orchestrators, notifiers, or repository code.
- Backtest code under `src/backtest/` must remain file-driven and Linux-friendly. Do not add QMT-only dependencies there.

## Change Routing

- If the task is about CLI entrypoints, service startup, Redis ingestion, QMT order execution, scheduled jobs, or operator workflows, inspect `main.py`, `src/trading_service.py`, `src/trader.py`, and `scripts/` first.
- If the task is about broker abstraction, daily export, or normalized market-data shape, inspect `src/broker/`, `src/data_manager/`, `src/daily_exporter.py`, `docs/unified_broker_guide.md`, and `docs/market_data_format.md` first.
- If the task is about T+0 signals, branch state, signal-card output, typed models, or Linux backtests, inspect `src/strategy/core/`, `src/strategy/`, `src/backtest/`, and `docs/strategy/t0_strategy_implementation.md` first.

## Safety Notes

- Assume QMT-related code can touch real or simulated trading accounts. Avoid changing live order behavior casually.
- Do not run order-placement tests or scripts unless the user explicitly wants live or simulated trading validation.
- Preserve configuration symmetry. When adding strategy or runtime parameters, update `src/config.py`, `.env.example`, and the consuming adapter/core code together.
- Preserve existing JSON and notification contracts when editing signal-card or export payloads.

## Testing Guidance

- Prefer targeted tests around the affected layer instead of broad live-system commands.
- Keep typed-model tests, signal-state tests, and backtest CLI tests aligned with any T+0 behavior changes.
- When changing data normalization or timestamp handling, verify both realtime and backtest paths.
