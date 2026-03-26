---
name: qmt-t0-strategy
description: Understand, extend, or debug the T+0 strategy, signal-card output, typed strategy models, and Linux backtesting flow in this repository. Use when working on `src/strategy/*`, `src/strategy/core/*`, `src/backtest/*`, `output/live_signal_card.json`, T+0 position rules, regime identification, FeatureSnapshot or PortfolioState models, typed SignalCard/StrategyDecision paths, or file-driven backtests.
---

# QMT T+0 Strategy

Use this skill for tasks about the T+0 strategy itself rather than the live service loop or the generic broker layer.

Start with [references/core-and-runtime.md](references/core-and-runtime.md) for the current architecture and [references/backtesting.md](references/backtesting.md) for Linux/file-driven backtest usage and invariants.

## Workflow

1. Decide whether the task belongs to:
   strategy core, realtime T+0 orchestration, typed models/output contracts, or Linux backtesting.
2. Preserve the current dependency direction:
   data adapters -> strategy core -> output/persistence adapters.
3. For signal-rule work, inspect `src/strategy/core/engine.py`, `src/strategy/core/params.py`, and `src/strategy/core/models.py` before editing adapters.
4. For realtime behavior, trace `main.py` -> `run_t0_strategy` / `run_t0_daemon` -> `src/strategy/t0_orchestrator.py`.
5. For backtests, use `src/backtest/data_loader.py`, `src/backtest/simulator.py`, and `src/backtest/cli.py` rather than reimplementing a parallel replay path.
6. When changing output fields, keep `SignalCard`, notifier formatting, repository persistence, tests, and `output/live_signal_card.json` expectations aligned.

## Safety Rules

- Keep the strategy core platform-neutral. Files under `src/strategy/core/` must not depend on QMT, Redis, SQLAlchemy sessions, or notification code.
- Preserve the typed-model boundary. `FeatureSnapshot`, `PortfolioState`, `StrategyDecision`, `MarketSnapshot`, `PositionSnapshot`, and `SignalCard` are the stable contract for strategy-side code.
- Treat T+0 capacity rules as business constraints, not UI details. The current model assumes `base_position + tactical_position = max_position` and computes `t0_sell_available` / `t0_buy_capacity` from that structure.
- Do not silently change trading windows, minimum hold minutes, or branch semantics without updating tests and configuration defaults.
- Avoid introducing new real-trading side effects into strategy work. Realtime orchestration may notify and persist; the core and backtest layers must remain side-effect free.

## Editing Guidance

- Prefer adding or changing typed models first, then adapt realtime and backtest consumers.
- Keep `SignalGenerator` as a thin adapter. Business logic belongs in `src/strategy/core/engine.py`.
- Keep `RegimeClassifier` pure; `RegimeIdentifier` is the cache/persistence adapter.
- For Linux portability, favor file-driven data flows and pure pandas transformations.
- When adding parameters, update all three places together:
  `src/config.py`, `.env.example`, and `src/strategy/core/params.py`.
- When changing signal-card output, update both realtime tests and notifier expectations.
- Treat `output/` files as generated runtime artifacts. They are useful for inspection, but should not be treated as durable source files.

## References

- `references/core-and-runtime.md`: current T+0 layering, typed models, adapters, persistence, and realtime path.
- `references/backtesting.md`: file formats, CLI usage, simulator behavior, and Linux-oriented workflow.
